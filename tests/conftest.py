"""Shared test fixtures."""

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from deal_hunter.sources.base import Deal
from deal_hunter.storage.models import Base
from deal_hunter.storage.repositories import OfferRepository


@pytest.fixture
def sample_deal() -> Deal:
    """A realistic Deal fixture."""
    return Deal(
        id="pepper:12345",
        title="Giant Defy Advanced 2 2024 rower szosowy XL carbon",
        price=8500,
        link="https://www.pepper.pl/promocje/giant-defy-12345",
        source="pepper",
        description="Rower szosowy Giant Defy Advanced 2, carbon, Shimano 105, 40mm tires",
        temperature=120,
        image_url="https://example.com/image.jpg",
        published_at="2026-03-20T10:00:00+00:00",
    )


@pytest.fixture
def sample_profile() -> dict:
    """A minimal valid profile dict."""
    return {
        "name": "test_profile",
        "emoji": "\U0001f50d",
        "sources": {
            "pepper": {"urls": ["https://www.pepper.pl/search?q=test"]},
        },
        "budget": {"min": 5000, "max": 15000},
        "score_rules": {
            "carbon": 30,
            "shimano": 20,
            "105": 10,
        },
        "penalties": {
            "broken": -50,
            "damaged": -30,
        },
        "excluded_words": ["stolen", "parts only"],
        "required_any": [],
        "score_threshold": 40,
        "score_threshold_alert": 80,
        "telegram": {"topic_id": 31, "max_alerts": 5},
        "currency": "PLN",
    }


@pytest.fixture
def tmp_state_dir(tmp_path: Path) -> Path:
    """Temporary directory for state files."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir


# ──────────────── Dashboard fixtures ────────────────


@pytest.fixture
def dashboard_session(tmp_path):
    """SQLAlchemy session seeded with test data for dashboard tests."""
    eng = create_engine(f"sqlite:///{tmp_path / 'deal_hunter.api.db'}")

    @event.listens_for(eng, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(eng)
    session = Session(eng)

    today = datetime.now().isoformat()
    deal_repo = OfferRepository(session)

    # Deal 1: high-score bike, active (set first_seen/last_seen early so price history
    # manual inserts come after the upsert's initial price)
    deal_repo.upsert(
        id="pepper:99999",
        title="Test Carbon Bike XL",
        price=8500,
        link="https://example.com/deal/99999",
        source="pepper",
        description="A great carbon bike",
        image_url="https://example.com/img.jpg",
        profile="bikes",
        score=85,
        category="road",
        first_seen="2026-03-15T10:00:00",
        last_seen="2026-03-15T10:00:00",
    )

    # Deal 2: mid-score NAS, watching
    deal_repo.upsert(
        id="ceneo:88888",
        title="NAS HDD Seagate IronWolf 8TB",
        price=1200,
        link="https://ceneo.pl/88888",
        source="ceneo",
        description="Seagate IronWolf 8TB",
        image_url="https://example.com/hdd.jpg",
        profile="nas_hdd",
        score=55,
        category="storage",
    )
    deal_repo.update_status("ceneo:88888", "watching")

    # Deal 3: low-score bike, rejected, no category
    deal_repo.upsert(
        id="pepper:77777",
        title="Cheap Broken Bike Parts",
        price=200,
        link="https://example.com/deal/77777",
        source="pepper",
        description="Spare parts only",
        image_url="",
        profile="bikes",
        score=20,
        category="",
    )
    deal_repo.update_status("pepper:77777", "rejected")

    # Deal 4: seen today (for new_today metric)
    deal_repo.upsert(
        id="pepper:66666",
        title="Brand New Road Bike Today",
        price=5000,
        link="https://example.com/deal/66666",
        source="pepper",
        description="Fresh deal",
        image_url="",
        profile="bikes",
        score=72,
        category="road",
        first_seen=today,
    )

    session.flush()

    # Price history for deal1 (two prices — enables drop detection)
    session.execute(
        text(
            "INSERT OR IGNORE INTO price_points (offer_id, price_pln, recorded_at)"
            " VALUES (:offer_id, :price_pln, :recorded_at)"
        ),
        {"offer_id": "pepper:99999", "price_pln": 9500, "recorded_at": "2026-03-20T10:00:00"},
    )
    session.execute(
        text(
            "INSERT OR IGNORE INTO price_points (offer_id, price_pln, recorded_at)"
            " VALUES (:offer_id, :price_pln, :recorded_at)"
        ),
        {"offer_id": "pepper:99999", "price_pln": 8500, "recorded_at": "2026-03-25T10:00:00"},
    )

    session.commit()

    yield session
    session.close()


class _CsrfTestClient:
    """Wrapper around TestClient that auto-adds HX-Request header on mutating methods."""

    def __init__(self, inner):
        self._inner = inner

    def _inject_csrf(self, kwargs):
        headers = dict(kwargs.get("headers") or {})
        # Don't override if caller already set a CSRF header
        if "HX-Request" not in headers and "X-Requested-With" not in headers:
            headers["HX-Request"] = "true"
        kwargs["headers"] = headers
        return kwargs

    def get(self, *args, **kwargs):
        return self._inner.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        return self._inner.post(*args, **self._inject_csrf(kwargs))

    def put(self, *args, **kwargs):
        return self._inner.put(*args, **self._inject_csrf(kwargs))

    def patch(self, *args, **kwargs):
        return self._inner.patch(*args, **self._inject_csrf(kwargs))

    def delete(self, *args, **kwargs):
        return self._inner.delete(*args, **self._inject_csrf(kwargs))

    def __getattr__(self, name):
        return getattr(self._inner, name)


@pytest.fixture
def raw_client(dashboard_session):
    """FastAPI TestClient WITHOUT auto CSRF headers (for CSRF-specific tests)."""
    from fastapi.testclient import TestClient

    from deal_hunter.api import app, get_db

    def _override():
        yield dashboard_session
        # Flush pending ORM writes so subsequent raw-SQL reads see them
        dashboard_session.flush()

    app.dependency_overrides[get_db] = _override
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


@pytest.fixture
def client(dashboard_session):
    """FastAPI TestClient with dashboard_session injected and auto CSRF headers."""
    from fastapi.testclient import TestClient

    from deal_hunter.api import app, get_db

    def _override():
        yield dashboard_session
        # Flush pending ORM writes so subsequent raw-SQL reads see them
        dashboard_session.flush()

    app.dependency_overrides[get_db] = _override
    yield _CsrfTestClient(TestClient(app, follow_redirects=False))
    app.dependency_overrides.clear()


@pytest.fixture
def sample_health_data():
    """Health data dict matching health.json structure."""
    return {
        "last_run": datetime.now().isoformat(timespec="seconds"),
        "status": "partial",
        "duration_seconds": 12.5,
        "version": "0.4.3",
        "profile_results": {
            "bikes": {
                "status": "ok",
                "deals_found": 15,
                "new_alerts": 3,
                "errors": [],
            },
            "nas_hdd": {
                "status": "error",
                "deals_found": 0,
                "new_alerts": 0,
                "errors": ["Connection timeout", "Parser failed"],
            },
        },
        "sources_health": {
            "pepper": {
                "status": "ok",
                "last_success": datetime.now().isoformat(),
                "consecutive_failures": 0,
            },
            "ceneo": {
                "status": "degraded",
                "last_success": "2026-04-05T22:00:00",
                "consecutive_failures": 2,
            },
        },
    }

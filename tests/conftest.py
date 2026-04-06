"""Shared test fixtures."""

from datetime import datetime
from pathlib import Path

import pytest

from sources.base import Deal
from storage.sqlite import SQLiteStorage


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
def dashboard_db(tmp_path):
    """SQLiteStorage seeded with test data for dashboard tests."""
    db = SQLiteStorage(tmp_path / "dashboard.db")
    today = datetime.now().isoformat()

    # Deal 1: high-score bike, active, seen today
    deal1 = Deal(
        id="pepper:99999",
        title="Test Carbon Bike XL",
        price=8500,
        link="https://example.com/deal/99999",
        source="pepper",
        description="A great carbon bike",
        temperature=120,
        image_url="https://example.com/img.jpg",
        published_at="2026-04-01T10:00:00",
    )
    db.upsert_deal(deal1, "bikes", 85, category="road")

    # Deal 2: mid-score NAS, watching
    deal2 = Deal(
        id="ceneo:88888",
        title="NAS HDD Seagate IronWolf 8TB",
        price=1200,
        link="https://ceneo.pl/88888",
        source="ceneo",
        description="Seagate IronWolf 8TB",
        temperature=0,
        image_url="https://example.com/hdd.jpg",
        published_at="2026-04-02T12:00:00",
    )
    db.upsert_deal(deal2, "nas_hdd", 55, category="storage")
    db.update_deal_status("ceneo:88888", "watching")

    # Deal 3: low-score bike, rejected, no category
    deal3 = Deal(
        id="pepper:77777",
        title="Cheap Broken Bike Parts",
        price=200,
        link="https://example.com/deal/77777",
        source="pepper",
        description="Spare parts only",
        temperature=0,
        image_url="",
        published_at="2026-03-15T08:00:00",
    )
    db.upsert_deal(deal3, "bikes", 20, category="")
    db.update_deal_status("pepper:77777", "rejected")

    # Deal 4: seen today (for new_today metric)
    deal4 = Deal(
        id="pepper:66666",
        title="Brand New Road Bike Today",
        price=5000,
        link="https://example.com/deal/66666",
        source="pepper",
        description="Fresh deal",
        temperature=50,
        image_url="",
        published_at=today,
    )
    db.upsert_deal(deal4, "bikes", 72, category="road")

    # Price history for deal1 (two prices → enables drop detection)
    db.record_price("pepper:99999", 9500)
    # Small delay not needed — record_price uses datetime.now() each call
    db.record_price("pepper:99999", 8500)

    yield db
    db.close()


@pytest.fixture
def client(dashboard_db):
    """FastAPI TestClient with dashboard_db injected."""
    from fastapi.testclient import TestClient

    from dashboard import app, get_db

    def _override():
        yield dashboard_db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app, follow_redirects=False)
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

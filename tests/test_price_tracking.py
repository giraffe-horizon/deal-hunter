"""Tests for price tracking via SQLAlchemy repositories."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from services.price_tracker import PriceTracker
from sources.base import Deal
from storage.models import Base, PriceHistory
from storage.models import Deal as DealModel
from storage.repositories import PriceRepository


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def price_repo(session):
    return PriceRepository(session)


def _make_deal(**kwargs) -> Deal:
    defaults = {
        "id": "test:1",
        "title": "Test Deal",
        "price": 10000,
        "link": "https://example.com",
        "source": "pepper",
        "description": "",
        "temperature": 0,
        "image_url": "",
        "published_at": "",
    }
    defaults.update(kwargs)
    return Deal(**defaults)


def _seed_deal_with_prices(session, deal_id="test:1", prices=None):
    """Insert a deal and its price history."""
    now = datetime.now().isoformat()
    deal = DealModel(
        id=deal_id,
        title="Test Deal",
        price=prices[-1] if prices else 0,
        source="pepper",
        description="",
        image_url="",
        profile="test",
        score=80,
        status="active",
        first_seen=now,
        last_seen=now,
    )
    session.add(deal)
    session.flush()
    if prices:
        for i, p in enumerate(prices):
            ts = f"2026-04-{10 + i:02d}T10:00:00"
            ph = PriceHistory(deal_id=deal_id, price=p, recorded_at=ts)
            session.add(ph)
    session.flush()


def test_price_drop_detected(session, price_repo):
    """Price decrease returns PriceChange dataclass."""
    _seed_deal_with_prices(session, "test:1", prices=[10000, 8000])
    deal = _make_deal(title="Test Deal", price=8000)
    tracker = PriceTracker(price_repo)
    result = tracker.check_price_change(deal)
    assert result is not None
    assert result.type == "drop"
    assert result.old_price == 10000
    assert result.new_price == 8000
    assert result.diff_pln == 2000


def test_price_increase_ignored(session, price_repo):
    """Price increase returns None by default."""
    _seed_deal_with_prices(session, "test:1", prices=[8000, 10000])
    deal = _make_deal(title="Test Deal", price=10000)
    tracker = PriceTracker(price_repo)
    result = tracker.check_price_change(deal)
    assert result is None


def test_no_previous_price(session, price_repo):
    """First time seen (single price entry) — no previous price."""
    _seed_deal_with_prices(session, "test:1", prices=[5000])
    deal = _make_deal(title="Brand New Deal", price=5000)
    tracker = PriceTracker(price_repo)
    result = tracker.check_price_change(deal)
    assert result is None

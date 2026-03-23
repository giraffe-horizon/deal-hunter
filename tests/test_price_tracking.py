"""Tests for price tracking."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from deal_hunter import check_price_changes
from sources.base import Deal


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


def test_price_drop_detected():
    """Price decrease adds bonus reason."""
    state = {
        "seen": {},
        "prices": {
            "test deal|pepper": [{"price": 10000, "ts": "2026-03-19T10:00:00"}],
        },
    }
    deal = _make_deal(title="Test Deal", price=8000)
    reasons = check_price_changes(deal, state, "test")
    assert len(reasons) == 1
    assert "price drop" in reasons[0]


def test_price_increase_ignored():
    """Price increase is logged but returns no bonus."""
    state = {
        "seen": {},
        "prices": {
            "test deal|pepper": [{"price": 8000, "ts": "2026-03-19T10:00:00"}],
        },
    }
    deal = _make_deal(title="Test Deal", price=10000)
    reasons = check_price_changes(deal, state, "test")
    assert reasons == []


def test_no_previous_price():
    """First time seen — no tracking, just records price."""
    state = {"seen": {}, "prices": {}}
    deal = _make_deal(title="Brand New Deal", price=5000)
    reasons = check_price_changes(deal, state, "test")
    assert reasons == []
    # Price should be recorded
    assert len(state["prices"]) == 1

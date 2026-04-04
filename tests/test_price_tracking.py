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
    """Price decrease returns structured dict."""
    state = {
        "seen": {},
        "prices": {
            "test deal|pepper": [{"price": 10000, "ts": "2026-03-19T10:00:00"}],
        },
    }
    deal = _make_deal(title="Test Deal", price=8000)
    result = check_price_changes(deal, state, "test")
    assert result is not None
    assert result["type"] == "drop"
    assert result["old_price"] == 10000
    assert result["new_price"] == 8000
    assert result["diff_pln"] == 2000


def test_price_increase_ignored():
    """Price increase is logged but returns None by default."""
    state = {
        "seen": {},
        "prices": {
            "test deal|pepper": [{"price": 8000, "ts": "2026-03-19T10:00:00"}],
        },
    }
    deal = _make_deal(title="Test Deal", price=10000)
    result = check_price_changes(deal, state, "test")
    assert result is None


def test_no_previous_price():
    """First time seen — no tracking, just records price."""
    state = {"seen": {}, "prices": {}}
    deal = _make_deal(title="Brand New Deal", price=5000)
    result = check_price_changes(deal, state, "test")
    assert result is None
    # Price should be recorded
    assert len(state["prices"]) == 1

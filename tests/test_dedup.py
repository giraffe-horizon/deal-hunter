"""Tests for deal deduplication."""

import sys
from pathlib import Path

# Ensure project root is on path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from deal_hunter import deduplicate
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


def test_exact_dedup():
    """Same ID is deduplicated."""
    deals = [
        _make_deal(id="pepper:123", title="Deal A"),
        _make_deal(id="pepper:123", title="Deal A"),
    ]
    result = deduplicate(deals)
    assert len(result) == 1


def test_cross_source_dedup():
    """Same title+price from different sources is deduplicated."""
    deals = [
        _make_deal(id="pepper:1", title="Giant Defy Advanced 2", price=8500, source="pepper"),
        _make_deal(id="ceneo:2", title="Giant Defy Advanced 2", price=8500, source="ceneo"),
    ]
    result = deduplicate(deals)
    assert len(result) == 1


def test_fuzzy_dedup():
    """Similar titles (>70% overlap) with same price are deduplicated."""
    deals = [
        _make_deal(
            id="pepper:1",
            title="Giant Defy Advanced 2 2024 carbon rower szosowy",
            price=8500,
        ),
        _make_deal(
            id="ceneo:2",
            title="Giant Defy Advanced 2 2024 carbon szosowy rower",
            price=8500,
        ),
    ]
    result = deduplicate(deals)
    assert len(result) == 1


def test_different_price_not_deduped():
    """Same title but different price is NOT deduplicated."""
    deals = [
        _make_deal(id="pepper:1", title="Giant Defy Advanced 2", price=8500),
        _make_deal(id="ceneo:2", title="Giant Defy Advanced 2", price=9000),
    ]
    result = deduplicate(deals)
    assert len(result) == 2

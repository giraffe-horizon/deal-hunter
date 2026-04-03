"""Tests for Deal dataclass validation (__post_init__)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from sources.base import Deal


def _make_deal(**kwargs) -> Deal:
    defaults = {
        "id": "test:1",
        "title": "Test Deal",
        "price": 100,
        "link": "https://example.com",
        "source": "test",
        "description": "",
        "temperature": 0,
        "image_url": "",
        "published_at": "",
    }
    defaults.update(kwargs)
    return Deal(**defaults)


class TestDealPostInit:
    def test_valid_deal(self):
        deal = _make_deal()
        assert deal.title == "Test Deal"
        assert deal.price == 100

    def test_empty_title_raises(self):
        with pytest.raises(ValueError, match="empty title"):
            _make_deal(title="")

    def test_whitespace_title_raises(self):
        with pytest.raises(ValueError, match="empty title"):
            _make_deal(title="   ")

    def test_negative_price_clamped_to_zero(self):
        deal = _make_deal(price=-50)
        assert deal.price == 0

    def test_zero_price_allowed(self):
        deal = _make_deal(price=0)
        assert deal.price == 0

    def test_none_temperature_becomes_zero(self):
        deal = _make_deal(temperature=None)
        assert deal.temperature == 0

    def test_regular_price_default(self):
        deal = _make_deal()
        assert deal.regular_price == 0

    def test_regular_price_set(self):
        deal = _make_deal(regular_price=200)
        assert deal.regular_price == 200

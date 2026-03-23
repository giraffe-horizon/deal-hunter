"""Tests for the bike-specific filter."""

from filters.bike_filter import BikeFilter
from sources.base import Deal


def _bike_profile(**overrides) -> dict:
    base = {
        "name": "bikes",
        "sources": {"pepper": {}},
        "budget": {"min": 5000, "max": 15000},
        "score_rules": {"carbon": 30},
        "penalties": {},
        "excluded_words": [],
        "required_any": [],
        "score_threshold": 40,
        "score_threshold_alert": 80,
        "telegram": {},
        "custom_data": {
            "brand_sizes": {
                "giant": ["XL", "L"],
                "trek": ["58", "60"],
            },
            "generic_good_sizes": ["XL", "58", "59", "60"],
            "excluded_colors": ["yellow", "pink"],
            "race_keywords": ["aero", "race", "sprint"],
        },
    }
    base.update(overrides)
    return base


def _make_deal(**kwargs) -> Deal:
    defaults = {
        "id": "test:1",
        "title": "Test Bike",
        "price": 10000,
        "link": "https://example.com",
        "source": "pepper",
        "description": "",
        "temperature": 0,
        "image_url": "",
        "published_at": "2026-03-20T10:00:00+00:00",
    }
    defaults.update(kwargs)
    return Deal(**defaults)


def test_bike_good_size():
    """Correct size for a known brand passes and gets bonus."""
    f = BikeFilter(_bike_profile())
    deal = _make_deal(title="Giant Defy Advanced carbon XL frame")
    result = f.score_deal(deal)
    assert not result.rejected
    assert any("good size" in p for p in result.plus)


def test_bike_wrong_size():
    """Wrong size for a known brand is rejected."""
    f = BikeFilter(_bike_profile())
    deal = _make_deal(title="Giant Defy Advanced carbon S frame rozmiar S")
    result = f.score_deal(deal)
    assert result.rejected
    assert "wrong size" in result.reject_reason


def test_bike_color_penalty():
    """Excluded color gets -100 penalty."""
    f = BikeFilter(_bike_profile())
    deal = _make_deal(title="Trek Domane 58 cm carbon yellow frame")
    result = f.score_deal(deal)
    assert any("-100" in m and "yellow" in m for m in result.minus)


def test_bike_tire_width_scoring():
    """Ideal/ok/narrow tire widths get different scores."""
    f = BikeFilter(_bike_profile())

    # Ideal: 38-50mm
    ideal = _make_deal(title="Bike XL carbon 40mm tires")
    r = f.score_deal(ideal)
    assert any("ideal" in p for p in r.plus)

    # OK: 32-37mm
    ok = _make_deal(title="Bike XL carbon 35mm tires")
    r = f.score_deal(ok)
    assert any("OK" in p for p in r.plus)

    # Narrow: 23-27mm
    narrow = _make_deal(title="Bike XL carbon 25mm tires")
    r = f.score_deal(narrow)
    assert any("narrow" in m for m in r.minus)

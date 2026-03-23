"""Tests for the base scoring engine."""

from filters.base import BaseFilter
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
        "published_at": "2026-03-20T10:00:00+00:00",
    }
    defaults.update(kwargs)
    return Deal(**defaults)


def test_base_filter_positive_scoring(sample_profile):
    """score_rules add points for matching keywords."""
    f = BaseFilter(sample_profile)
    deal = _make_deal(title="Giant carbon frame Shimano 105")
    result = f.score_deal(deal)
    assert not result.rejected
    # carbon +30, shimano +20, 105 +10 = 60 base + budget bonus
    assert result.score >= 60
    assert any("carbon" in p for p in result.plus)


def test_base_filter_penalties(sample_profile):
    """Penalties subtract points for matching keywords."""
    f = BaseFilter(sample_profile)
    deal = _make_deal(title="Carbon bike broken frame")
    result = f.score_deal(deal)
    assert any("broken" in m for m in result.minus)
    # carbon +30, broken -50
    assert result.score < 30


def test_base_filter_budget_in_range(sample_profile):
    """In-budget deals get +5."""
    f = BaseFilter(sample_profile)
    deal = _make_deal(title="Some deal", price=10000)
    result = f.score_deal(deal)
    assert any("+5 in budget" in p for p in result.plus)


def test_base_filter_budget_too_cheap(sample_profile):
    """Under-budget deals get -20."""
    f = BaseFilter(sample_profile)
    deal = _make_deal(title="Some deal", price=1000)
    result = f.score_deal(deal)
    assert any("too cheap" in m for m in result.minus)


def test_base_filter_budget_too_expensive(sample_profile):
    """Over-budget deals get -30."""
    f = BaseFilter(sample_profile)
    deal = _make_deal(title="Some deal", price=20000)
    result = f.score_deal(deal)
    assert any("too expensive" in m for m in result.minus)


def test_base_filter_excluded_words_reject(sample_profile):
    """Excluded words cause hard rejection."""
    f = BaseFilter(sample_profile)
    deal = _make_deal(title="Stolen bike carbon")
    result = f.score_deal(deal)
    assert result.rejected
    assert "stolen" in result.reject_reason


def test_base_filter_required_any_reject():
    """Required_any rejects if none match."""
    profile = {
        "name": "test",
        "sources": {"pepper": {}},
        "budget": {"min": 100, "max": 50000},
        "score_threshold": 40,
        "score_threshold_alert": 80,
        "telegram": {},
        "required_any": ["12tb", "12 tb"],
    }
    f = BaseFilter(profile)
    deal = _make_deal(title="8TB HDD drive")
    result = f.score_deal(deal)
    assert result.rejected
    assert "required_any" in result.reject_reason


def test_base_filter_required_any_pass():
    """Required_any passes if at least one matches."""
    profile = {
        "name": "test",
        "sources": {"pepper": {}},
        "budget": {"min": 100, "max": 50000},
        "score_threshold": 40,
        "score_threshold_alert": 80,
        "telegram": {},
        "required_any": ["12tb", "12 tb"],
    }
    f = BaseFilter(profile)
    deal = _make_deal(title="Seagate IronWolf 12TB NAS HDD")
    result = f.score_deal(deal)
    assert not result.rejected


def test_regex_scoring():
    """r/pattern/ syntax works in score_rules."""
    profile = {
        "name": "test",
        "sources": {"pepper": {}},
        "budget": {"min": 100, "max": 50000},
        "score_threshold": 40,
        "score_threshold_alert": 80,
        "telegram": {},
        "score_rules": {"r/\\b(xl|58|59)\\b/": 15},
    }
    f = BaseFilter(profile)

    deal_match = _make_deal(title="Giant bike XL frame")
    result = f.score_deal(deal_match)
    assert result.score >= 15

    deal_no_match = _make_deal(title="Giant bike M frame")
    result2 = f.score_deal(deal_no_match)
    assert not any("xl" in p.lower() for p in result2.plus)


def test_temperature_bonus():
    """Hot/warm/cold temperature scoring."""
    profile = {
        "name": "test",
        "sources": {"pepper": {}},
        "budget": {"min": 100, "max": 50000},
        "score_threshold": 40,
        "score_threshold_alert": 80,
        "telegram": {},
    }
    f = BaseFilter(profile)

    # Hot deal
    hot = _make_deal(title="Deal", temperature=150)
    r = f.score_deal(hot)
    assert any("hot" in p for p in r.plus)

    # Warm deal
    warm = _make_deal(title="Deal", temperature=60)
    r = f.score_deal(warm)
    assert any("warm" in p for p in r.plus)

    # Cold deal
    cold = _make_deal(title="Deal", temperature=-20, published_at="2026-03-20T10:00:00+00:00")
    r = f.score_deal(cold)
    assert any("cold" in m for m in r.minus)

"""Tests for profile validation."""

from deal_hunter.utils.validation import validate_profile


def _valid_profile() -> dict:
    """Return a minimal valid profile dict for use in standalone tests."""
    return {
        "name": "test_profile",
        "sources": {"pepper": {"urls": ["https://www.pepper.pl/search?q=test"]}},
        "budget": {"min": 5000, "max": 15000},
        "score_threshold": 40,
        "score_threshold_alert": 80,
        "telegram": {"topic_id": 31, "max_alerts": 5},
    }


def test_valid_profile(sample_profile):
    """A complete valid profile returns no errors."""
    errors = validate_profile(sample_profile)
    assert errors == []


def test_missing_name(sample_profile):
    """Missing 'name' field is reported."""
    del sample_profile["name"]
    errors = validate_profile(sample_profile)
    assert any("name" in e for e in errors)


def test_missing_sources(sample_profile):
    """Missing 'sources' field is reported."""
    del sample_profile["sources"]
    errors = validate_profile(sample_profile)
    assert any("sources" in e for e in errors)


def test_budget_min_gt_max(sample_profile):
    """budget.min >= budget.max is reported."""
    sample_profile["budget"] = {"min": 20000, "max": 5000}
    errors = validate_profile(sample_profile)
    assert any("budget" in e.lower() for e in errors)


def test_threshold_gt_alert(sample_profile):
    """score_threshold >= score_threshold_alert is reported."""
    sample_profile["score_threshold"] = 100
    sample_profile["score_threshold_alert"] = 80
    errors = validate_profile(sample_profile)
    assert any("score_threshold" in e for e in errors)


def test_dedup_config_valid():
    """Valid dedup config passes validation."""
    profile = _valid_profile()
    profile["dedup"] = {"enabled": True, "price_tolerance": 0.05, "title_similarity": 0.85}
    errors = validate_profile(profile)
    assert not errors


def test_dedup_config_invalid_tolerance():
    """dedup.price_tolerance must be 0-1."""
    profile = _valid_profile()
    profile["dedup"] = {"price_tolerance": 1.5}
    errors = validate_profile(profile)
    assert any("price_tolerance" in e for e in errors)


def test_dedup_config_invalid_similarity():
    """dedup.title_similarity must be 0-1."""
    profile = _valid_profile()
    profile["dedup"] = {"title_similarity": -0.1}
    errors = validate_profile(profile)
    assert any("title_similarity" in e for e in errors)

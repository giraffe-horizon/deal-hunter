"""Tests for profile validation."""

from utils.validation import validate_profile


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

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


def test_validate_profile_accepts_cooldown_days():
    """price_tracking.cooldown_days (int 0-365) is accepted."""
    profile = _valid_profile()
    profile["price_tracking"] = {
        "enabled": True,
        "cooldown_days": 14,
        "alert_through_cooldown_if_ath_low": False,
    }
    errors = validate_profile(profile)
    assert errors == []


def test_validate_profile_rejects_negative_cooldown_days():
    """price_tracking.cooldown_days must not be negative."""
    profile = _valid_profile()
    profile["price_tracking"] = {"cooldown_days": -1}
    errors = validate_profile(profile)
    assert any("cooldown_days" in e for e in errors)


def test_validate_profile_rejects_cooldown_days_over_365():
    """price_tracking.cooldown_days must not exceed 365."""
    profile = _valid_profile()
    profile["price_tracking"] = {"cooldown_days": 366}
    errors = validate_profile(profile)
    assert any("cooldown_days" in e for e in errors)


def test_validate_profile_rejects_cooldown_days_wrong_type():
    """price_tracking.cooldown_days must be int, not bool or str."""
    profile = _valid_profile()
    profile["price_tracking"] = {"cooldown_days": "14"}
    errors = validate_profile(profile)
    assert any("cooldown_days" in e for e in errors)


def test_validate_profile_rejects_cooldown_days_as_bool():
    """price_tracking.cooldown_days must not accept bool (bool is subclass of int)."""
    profile = _valid_profile()
    profile["price_tracking"] = {"cooldown_days": True}
    errors = validate_profile(profile)
    assert any("cooldown_days" in e for e in errors)


def test_validate_profile_accepts_alert_through_cooldown_if_ath_low():
    """price_tracking.alert_through_cooldown_if_ath_low (bool) is accepted."""
    profile = _valid_profile()
    profile["price_tracking"] = {
        "enabled": True,
        "alert_through_cooldown_if_ath_low": True,
    }
    errors = validate_profile(profile)
    assert errors == []


def test_validate_profile_rejects_alert_through_cooldown_if_ath_low_wrong_type():
    """price_tracking.alert_through_cooldown_if_ath_low must be bool."""
    profile = _valid_profile()
    profile["price_tracking"] = {"alert_through_cooldown_if_ath_low": "true"}
    errors = validate_profile(profile)
    assert any("alert_through_cooldown_if_ath_low" in e for e in errors)

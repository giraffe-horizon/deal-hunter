"""Profile validation — checks structure, types, and sanity of YAML profiles."""

import logging

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["name", "sources", "budget", "score_threshold", "telegram"]


def validate_profile(profile: dict) -> list[str]:
    """Validate a profile dict. Returns list of error strings (empty = valid)."""
    errors: list[str] = []

    # Required fields
    for field_name in REQUIRED_FIELDS:
        if field_name not in profile:
            errors.append(f"Missing required field: '{field_name}'")

    if errors:
        return errors

    # Type checks
    if not isinstance(profile["name"], str):
        errors.append("'name' must be a string")

    if not isinstance(profile["sources"], dict):
        errors.append("'sources' must be a dict")
    elif not profile["sources"]:
        errors.append("'sources' must not be empty")

    if not isinstance(profile["budget"], dict):
        errors.append("'budget' must be a dict with 'min' and 'max'")
    else:
        budget = profile["budget"]
        if "min" not in budget or "max" not in budget:
            errors.append("'budget' must have 'min' and 'max' keys")
        elif not isinstance(budget["min"], (int, float)) or not isinstance(
            budget["max"], (int, float)
        ):
            errors.append("'budget.min' and 'budget.max' must be numbers")
        elif budget["min"] >= budget["max"]:
            errors.append(
                f"'budget.min' ({budget['min']}) must be less than 'budget.max' ({budget['max']})"
            )

    if not isinstance(profile["score_threshold"], (int, float)):
        errors.append("'score_threshold' must be a number")

    if not isinstance(profile["telegram"], dict):
        errors.append("'telegram' must be a dict")

    # Sanity: score_threshold < score_threshold_alert
    threshold = profile.get("score_threshold")
    threshold_alert = profile.get("score_threshold_alert")
    if (
        isinstance(threshold, (int, float))
        and isinstance(threshold_alert, (int, float))
        and threshold >= threshold_alert
    ):
        errors.append(
            f"'score_threshold' ({threshold}) must be less than "
            f"'score_threshold_alert' ({threshold_alert})"
        )

    # Optional field type checks
    if "score_rules" in profile and not isinstance(profile["score_rules"], dict):
        errors.append("'score_rules' must be a dict")

    if "penalties" in profile and not isinstance(profile["penalties"], dict):
        errors.append("'penalties' must be a dict")

    if "required_any" in profile and not isinstance(profile["required_any"], list):
        errors.append("'required_any' must be a list")

    if "excluded_words" in profile and not isinstance(profile["excluded_words"], list):
        errors.append("'excluded_words' must be a list")

    if "currency" in profile and not isinstance(profile["currency"], str):
        errors.append("'currency' must be a string")

    # price_tracking validation
    if "price_tracking" in profile:
        pt = profile["price_tracking"]
        if not isinstance(pt, dict):
            errors.append("'price_tracking' must be a dict")
        else:
            if "enabled" in pt and not isinstance(pt["enabled"], bool):
                errors.append("'price_tracking.enabled' must be a boolean")
            if "min_drop_percent" in pt:
                if not isinstance(pt["min_drop_percent"], (int, float)):
                    errors.append("'price_tracking.min_drop_percent' must be a number")
                elif pt["min_drop_percent"] < 0 or pt["min_drop_percent"] > 100:
                    errors.append("'price_tracking.min_drop_percent' must be between 0 and 100")
            if "min_drop_amount" in pt:
                if not isinstance(pt["min_drop_amount"], (int, float)):
                    errors.append("'price_tracking.min_drop_amount' must be a number")
                elif pt["min_drop_amount"] < 0:
                    errors.append("'price_tracking.min_drop_amount' must be non-negative")
            if "track_increases" in pt and not isinstance(pt["track_increases"], bool):
                errors.append("'price_tracking.track_increases' must be a boolean")

    # quiet_hours validation
    if "quiet_hours" in profile:
        qh = profile["quiet_hours"]
        if not isinstance(qh, dict):
            errors.append("'quiet_hours' must be a dict")
        else:
            if "start" not in qh:
                errors.append("'quiet_hours' must have 'start' key")
            if "end" not in qh:
                errors.append("'quiet_hours' must have 'end' key")
            for key in ("start", "end"):
                val = qh.get(key)
                if val is not None:
                    import re as _re

                    if not isinstance(val, str) or not _re.match(r"^\d{2}:\d{2}$", val):
                        errors.append(f"'quiet_hours.{key}' must be in HH:MM format")

    return errors

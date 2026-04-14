"""Scoring tuner business logic — simulate rule changes and persist them."""

from pathlib import Path

from sqlalchemy.orm import Session

from deal_hunter.api.view_services.deal_service import DealService
from deal_hunter.storage.repositories import OfferRepository
from deal_hunter.utils.validation import validate_profile

# Keys that the tuner UI is allowed to override.
_TUNABLE_KEYS = (
    "score_rules",
    "penalties",
    "budget",
    "score_threshold",
    "score_threshold_alert",
    "excluded_words",
    "required_any",
)


class TunerService:
    """Encapsulates scoring-tuner business logic."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def _merge_overrides(profile_data: dict, overrides: dict) -> dict:
        """Return a copy of *profile_data* with tunable keys replaced by *overrides*."""
        merged = dict(profile_data)
        for key in _TUNABLE_KEYS:
            if key in overrides:
                merged[key] = overrides[key]
        return merged

    # ── public API ──────────────────────────────────────────

    def simulate(self, profile_name: str, profile_data: dict, overrides: dict) -> list[dict]:
        """Re-score stored deals with *overrides* applied and return result dicts.

        Each result contains: id, title, price, current_score, new_score, diff,
        rejected, reject_reason, breakdown.
        """
        modified = self._merge_overrides(profile_data, overrides)
        deals = OfferRepository(self.session).get_filtered(profile=profile_name, limit=50)
        scored = DealService(self.session).score_deals_with_profile(deals, modified)
        return [
            {
                "id": s["id"],
                "title": s["title"],
                "price": s["price"],
                "current_score": s["score"],
                "new_score": s["new_score"],
                "diff": s["diff"],
                "rejected": s["rejected"],
                "reject_reason": s["reject_reason"],
                "breakdown": s["breakdown"],
            }
            for s in scored
        ]

    @staticmethod
    def save_rules(profile_path: Path, profile_data: dict, overrides: dict) -> list[str]:
        """Apply *overrides* to *profile_data*, validate, and write YAML.

        Returns a list of validation errors (empty on success).
        """
        for key in _TUNABLE_KEYS:
            if key in overrides:
                profile_data[key] = overrides[key]

        errors = validate_profile(profile_data)
        if errors:
            return errors

        import yaml as _yaml_save

        profile_path.write_text(
            _yaml_save.dump(
                profile_data,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return []

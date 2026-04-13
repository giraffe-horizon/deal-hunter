"""Scoring orchestration and category detection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from filters.base import BaseFilter

if TYPE_CHECKING:
    from sources.base import Deal

from services.types import ScoredDeal


class ScoringService:
    """Orchestrates deal scoring using filter registry."""

    def __init__(self, filter_registry: dict[str, Any]) -> None:
        self.filter_registry = filter_registry

    def get_filter(self, profile: dict) -> BaseFilter:
        """Get the appropriate filter for a profile."""
        custom_filter = profile.get("custom_filter")
        if custom_filter and custom_filter in self.filter_registry:
            return self.filter_registry[custom_filter](profile)
        return BaseFilter(profile)

    def score_deals(
        self,
        deals: list[Deal],
        profile: dict,
        profile_name: str = "",
    ) -> tuple[list[ScoredDeal], list[ScoredDeal]]:
        """Score all deals. Returns (scored, rejected) lists sorted by score desc."""
        deal_filter = self.get_filter(profile)
        scored: list[ScoredDeal] = []
        rejected: list[ScoredDeal] = []

        for deal in deals:
            result = deal_filter.score_deal(deal)
            category = self.detect_category(deal, profile, profile_name)
            sd = ScoredDeal(deal=deal, result=result, category=category)
            if result.rejected:
                rejected.append(sd)
            else:
                scored.append(sd)

        scored.sort(key=lambda x: x.result.score, reverse=True)
        return scored, rejected

    @staticmethod
    def detect_category(deal: Deal, profile: dict, profile_name: str = "") -> str:
        """Detect product category from deal title+description."""
        categories = profile.get("categories", {})
        if not categories:
            return profile_name if profile_name else ""

        text = (deal.title + " " + deal.description).lower()
        for category, keywords in categories.items():
            if any(kw.lower() in text for kw in keywords):
                return str(category)
        return profile_name if profile_name else ""

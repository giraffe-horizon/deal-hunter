"""Price change detection service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from deal_hunter.core.types import PriceChange, PriceTrackingConfig

if TYPE_CHECKING:
    from deal_hunter.sources.base import Deal
    from deal_hunter.storage.repositories import PriceRepository

logger = logging.getLogger(__name__)


class PriceTracker:
    """Detects significant price changes using SQLite price history."""

    def __init__(self, price_repo: PriceRepository) -> None:
        self.price_repo = price_repo

    @staticmethod
    def get_config(profile: dict) -> PriceTrackingConfig:
        """Extract price tracking config from profile with defaults."""
        pt = profile.get("price_tracking", {})
        return PriceTrackingConfig(
            enabled=pt.get("enabled", True),
            min_drop_percent=pt.get("min_drop_percent", 10),
            min_drop_amount=pt.get("min_drop_amount", 200),
            track_increases=pt.get("track_increases", False),
            cooldown_days=pt.get("cooldown_days"),
            alert_through_cooldown_if_ath_low=pt.get("alert_through_cooldown_if_ath_low"),
        )

    def check_price_change(self, deal: Deal, profile: dict | None = None) -> PriceChange | None:
        """Check if price changed significantly. Returns PriceChange or None."""
        if deal.price <= 0:
            return None

        config = self.get_config(profile) if profile else PriceTrackingConfig()
        if not config.enabled:
            return None

        prev_price = self.price_repo.get_previous_price(deal.id)
        if prev_price is None or deal.price == prev_price:
            return None

        if deal.price < prev_price:
            drop_abs = prev_price - deal.price
            drop_pct = (drop_abs / prev_price) * 100 if prev_price > 0 else 0

            if drop_pct >= config.min_drop_percent or drop_abs >= config.min_drop_amount:
                lowest = self.price_repo.get_lowest(deal.id)
                is_lowest = lowest is not None and deal.price <= lowest
                return PriceChange(
                    deal_id=deal.id,
                    type="drop",
                    old_price=prev_price,
                    new_price=deal.price,
                    diff_pln=drop_abs,
                    diff_percent=round(drop_pct, 1),
                    is_lowest_ever=is_lowest,
                )
        elif config.track_increases:
            increase_abs = deal.price - prev_price
            increase_pct = (increase_abs / prev_price) * 100 if prev_price > 0 else 0
            return PriceChange(
                deal_id=deal.id,
                type="increase",
                old_price=prev_price,
                new_price=deal.price,
                diff_pln=increase_abs,
                diff_percent=round(increase_pct, 1),
                is_lowest_ever=False,
            )
        return None

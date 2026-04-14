"""Shared typed dataclasses for service layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from deal_hunter.domain.scoring.base import ScoreResult
    from deal_hunter.sources.base import Deal


@dataclass
class PriceTrackingConfig:
    enabled: bool = True
    min_drop_percent: int = 10
    min_drop_amount: int = 200
    track_increases: bool = False


@dataclass
class PriceChange:
    deal_id: str
    type: Literal["drop", "increase"]
    old_price: int
    new_price: int
    diff_pln: int
    diff_percent: float
    is_lowest_ever: bool


@dataclass
class ScoredDeal:
    deal: Deal
    result: ScoreResult
    category: str


@dataclass
class FetchResult:
    deals: list[Deal]
    source_results: dict[str, bool]
    errors: list[str]

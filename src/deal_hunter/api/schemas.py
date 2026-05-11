"""Pydantic models for dashboard API validation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class StatusUpdate(BaseModel):
    status: Literal["watching", "rejected", "active"]


class WatchlistAdd(BaseModel):
    deal_id: str = Field(min_length=1)
    target_price: int = Field(gt=0)


class WatchlistUpdate(BaseModel):
    target_price: int = Field(gt=0)


class ProfileCreate(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    sources: dict = Field(default_factory=dict)
    budget: dict = Field(default_factory=dict)
    score_threshold: int = 50
    score_threshold_alert: int = 80
    telegram: dict = Field(default_factory=dict)


class FilterParams(BaseModel):
    """Deal-list filter set — reused for selection payloads."""

    profile: str | None = None
    source: str | None = None
    min_score: int | None = None
    category: str | None = None
    status: str | None = None

    def to_kwargs(self) -> dict:
        """Unpack as keyword args for OfferRepository filter methods."""
        return {
            "profile": self.profile,
            "source": self.source,
            "min_score": self.min_score,
            "category": self.category,
            "status": self.status,
        }


BulkAction = Literal["set-status", "set-target", "compare"]
BulkStatus = Literal["watching", "rejected", "active"]

# Keep in sync with routes.deals.BULK_MAX_ROWS — cheap pre-parse rejection
# so pydantic refuses multi-MB payloads before the handler inspects them.
BULK_PAYLOAD_MAX_IDS = 100_000


class BulkRequest(BaseModel):
    """Unified bulk-op payload. Either `ids` OR `filter` must be present."""

    action: BulkAction
    ids: list[str] | None = Field(default=None, max_length=BULK_PAYLOAD_MAX_IDS)
    filter: FilterParams | None = None
    excluded: list[str] = Field(default_factory=list, max_length=BULK_PAYLOAD_MAX_IDS)
    status: BulkStatus | None = None
    target_price: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _check_payload(self) -> BulkRequest:
        if self.ids is None and self.filter is None:
            raise ValueError("Either 'ids' or 'filter' must be provided")
        if self.ids is not None and self.filter is not None:
            raise ValueError("Provide 'ids' or 'filter', not both")
        if self.action == "set-status" and self.status is None:
            raise ValueError("action='set-status' requires 'status'")
        if self.action == "set-target" and self.target_price is None:
            raise ValueError("action='set-target' requires 'target_price'")
        return self


class GlobalNotificationConfig(BaseModel):
    cooldown_days: int = Field(ge=0, le=365)
    alert_through_cooldown_if_ath_low: bool
    default_snooze_days: int = Field(ge=1, le=365)


class MuteRequest(BaseModel):
    """`days` empty/None → permanent mute; positive int → snooze that many days."""

    days: int | None = Field(default=None, ge=1, le=365)

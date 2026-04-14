"""Pydantic models for dashboard API validation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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

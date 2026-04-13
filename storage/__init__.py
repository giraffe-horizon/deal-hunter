# storage/__init__.py
"""Storage layer — SQLAlchemy ORM models, session management, and repositories."""

from storage.database import SessionLocal, engine, get_session
from storage.models import (
    AlertQueue,
    Base,
    Deal,
    Feedback,
    PriceHistory,
    SeenDeal,
    WatchlistItem,
)
from storage.repositories import (
    AlertQueueRepository,
    DealRepository,
    FeedbackRepository,
    PriceRepository,
    SeenDealRepository,
    WatchlistRepository,
)
from storage.sqlite import SQLiteStorage  # kept until all consumers migrated

__all__ = [
    "AlertQueue",
    "AlertQueueRepository",
    "Base",
    "Deal",
    "DealRepository",
    "Feedback",
    "FeedbackRepository",
    "PriceHistory",
    "PriceRepository",
    "SQLiteStorage",
    "SeenDeal",
    "SeenDealRepository",
    "SessionLocal",
    "WatchlistItem",
    "WatchlistRepository",
    "engine",
    "get_session",
]

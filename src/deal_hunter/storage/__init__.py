# storage/__init__.py
"""Storage layer — SQLAlchemy ORM models, session management, and repositories."""

from deal_hunter.storage.database import SessionLocal, engine, get_session
from deal_hunter.storage.models import (
    AlertQueue,
    Base,
    Feedback,
    Offer,
    PricePoint,
    SeenDeal,
    WatchlistItem,
)
from deal_hunter.storage.repositories import (
    AlertQueueRepository,
    FeedbackRepository,
    OfferRepository,
    PriceRepository,
    SeenDealRepository,
    WatchlistRepository,
)

__all__ = [
    "AlertQueue",
    "AlertQueueRepository",
    "Base",
    "Feedback",
    "FeedbackRepository",
    "Offer",
    "OfferRepository",
    "PricePoint",
    "PriceRepository",
    "SeenDeal",
    "SeenDealRepository",
    "SessionLocal",
    "WatchlistItem",
    "WatchlistRepository",
    "engine",
    "get_session",
]

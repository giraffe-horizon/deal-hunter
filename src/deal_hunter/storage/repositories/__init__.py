"""Domain-organized repository classes for Deal Hunter.

Each aggregate lives in its own submodule; this package re-exports the
public surface so existing callers keep working unchanged:

    from deal_hunter.storage.repositories import OfferRepository, PriceRepository, ...
"""

from deal_hunter.storage.repositories.alert_queue import AlertQueueRepository
from deal_hunter.storage.repositories.deal_event import DealEventRepository
from deal_hunter.storage.repositories.feedback import FeedbackRepository
from deal_hunter.storage.repositories.fx import FxRateRepository
from deal_hunter.storage.repositories.match import (
    MatchDecisionRepository,
    MatchReviewRepository,
)
from deal_hunter.storage.repositories.offer import OfferRepository
from deal_hunter.storage.repositories.offer_payload_history import (
    OFFER_PAYLOAD_HISTORY_MAX,
    OfferPayloadHistoryRepository,
)
from deal_hunter.storage.repositories.price import PriceRepository
from deal_hunter.storage.repositories.product import (
    ProductAliasRepository,
    ProductRepository,
)
from deal_hunter.storage.repositories.seen_deal import SeenDealRepository
from deal_hunter.storage.repositories.sent_notification import SentNotificationRepository
from deal_hunter.storage.repositories.watchlist import WatchlistRepository

__all__ = [
    "OFFER_PAYLOAD_HISTORY_MAX",
    "AlertQueueRepository",
    "DealEventRepository",
    "FeedbackRepository",
    "FxRateRepository",
    "MatchDecisionRepository",
    "MatchReviewRepository",
    "OfferPayloadHistoryRepository",
    "OfferRepository",
    "PriceRepository",
    "ProductAliasRepository",
    "ProductRepository",
    "SeenDealRepository",
    "SentNotificationRepository",
    "WatchlistRepository",
]

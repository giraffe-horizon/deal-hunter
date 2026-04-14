"""Business logic for the Deal Hunter dashboard, decoupled from HTTP routing."""

import os

from deal_hunter.api.view_services.deal_service import DealService, DealsPageData, PriceDropsData
from deal_hunter.api.view_services.profile_service import ProfileService
from deal_hunter.api.view_services.tuner_service import TunerService

DEALS_PER_PAGE = int(os.getenv("DEALS_PER_PAGE", "50"))
SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD", "70"))

__all__ = [
    "DealService",
    "DealsPageData",
    "PriceDropsData",
    "ProfileService",
    "TunerService",
    "DEALS_PER_PAGE",
    "SCORE_THRESHOLD",
]

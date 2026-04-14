"""Business logic for the Deal Hunter dashboard, decoupled from HTTP routing."""

from deal_hunter.api.view_services.deal_service import DealService, DealsPageData, PriceDropsData
from deal_hunter.api.view_services.profile_service import ProfileService
from deal_hunter.api.view_services.tuner_service import TunerService
from deal_hunter.core.settings import Settings

# Read settings fresh at module-import time so `importlib.reload(view_services)`
# picks up new env values in tests. Runs only once per module load.
_settings = Settings()
DEALS_PER_PAGE = _settings.deals_per_page
SCORE_THRESHOLD = _settings.score_threshold

__all__ = [
    "DealService",
    "DealsPageData",
    "PriceDropsData",
    "ProfileService",
    "TunerService",
    "DEALS_PER_PAGE",
    "SCORE_THRESHOLD",
]

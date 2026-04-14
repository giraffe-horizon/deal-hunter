"""Shared service singletons for the CLI / batch runtime.

These factories lazily construct the top-level services that live for the
process lifetime (ProfileManager, DealFetcher, ScoringService, HealthTracker)
and the short-lived TelegramNotifier created from settings. Using
``lru_cache`` makes them effectively singletons without global mutable state.

Tests that need isolation can call ``reset_runtime()``.
"""

from __future__ import annotations

from functools import lru_cache

from deal_hunter.core.settings import get_settings
from deal_hunter.domain.scoring import FILTER_REGISTRY
from deal_hunter.notifiers.telegram import TelegramNotifier
from deal_hunter.services.fetcher import DealFetcher
from deal_hunter.services.health_tracker import HealthTracker
from deal_hunter.services.profile_manager import ProfileManager
from deal_hunter.services.scorer import ScoringService
from deal_hunter.sources import SOURCE_REGISTRY


@lru_cache(maxsize=1)
def get_profile_manager() -> ProfileManager:
    return ProfileManager(get_settings().profiles_dir)


@lru_cache(maxsize=1)
def get_fetcher() -> DealFetcher:
    return DealFetcher(SOURCE_REGISTRY)


@lru_cache(maxsize=1)
def get_scoring_service() -> ScoringService:
    return ScoringService(FILTER_REGISTRY)


@lru_cache(maxsize=1)
def get_health_tracker() -> HealthTracker:
    return HealthTracker(get_settings().state_dir / "health.json")


def get_telegram() -> TelegramNotifier | None:
    """Build a TelegramNotifier if credentials are configured, else None."""
    s = get_settings()
    if s.telegram_configured:
        return TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id)
    return None


def get_topic_id() -> int | None:
    """Return TELEGRAM_TOPIC_ID from settings (already parsed)."""
    return get_settings().telegram_topic_id


def reset_runtime() -> None:
    """Clear all cached singletons — for tests."""
    get_profile_manager.cache_clear()
    get_fetcher.cache_clear()
    get_scoring_service.cache_clear()
    get_health_tracker.cache_clear()

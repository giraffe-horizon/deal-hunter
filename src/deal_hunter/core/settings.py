"""Centralized application settings (env vars + derived paths).

All runtime configuration from `.env` / environment is loaded here via
pydantic-settings. Call `get_settings()` anywhere — the result is cached
for the lifetime of the process.

Direct `os.environ.get(...)` reads should be replaced with `get_settings()`
access so that config lives in one place and is easy to mock in tests.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root — this file lives at src/deal_hunter/core/settings.py,
# so parents[3] == repo root (deal-hunter/).
BASE_DIR: Path = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Application configuration loaded from environment / `.env`.

    Fields map 1:1 to env vars (case-insensitive). Unknown env vars are ignored.
    """

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_topic_id: int | None = None

    # --- Quiet hours (global default; profile YAML can override) ---
    quiet_hours_start: str | None = None  # "HH:MM"
    quiet_hours_end: str | None = None

    # --- Paths / storage ---
    deal_hunter_state_dir: Path | None = None
    deal_hunter_profiles_dir: Path | None = None
    database_url: str | None = None

    # --- Dashboard defaults ---
    deals_per_page: int = 50
    score_threshold: int = 70

    @field_validator("telegram_topic_id", mode="before")
    @classmethod
    def _parse_topic_id(cls, v: object) -> int | None:
        """Accept empty string / "0" as None; tolerate non-numeric values."""
        if v is None or v == "":
            return None
        if isinstance(v, int):
            return v or None
        try:
            parsed = int(str(v).strip())
        except (ValueError, TypeError):
            return None
        return parsed or None

    # --- Derived paths ---
    @property
    def base_dir(self) -> Path:
        return BASE_DIR

    @property
    def state_dir(self) -> Path:
        return self.deal_hunter_state_dir or (BASE_DIR / "state")

    @property
    def profiles_dir(self) -> Path:
        return self.deal_hunter_profiles_dir or (BASE_DIR / "profiles")

    @property
    def default_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.state_dir / 'deals.db'}"

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings instance (cached)."""
    return Settings()


def reload_settings() -> Settings:
    """Clear the cache and reload settings — useful in tests."""
    get_settings.cache_clear()
    return get_settings()

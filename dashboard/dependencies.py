# dashboard/dependencies.py
"""Shared dependencies for dashboard routes."""

import os
from collections.abc import Iterator
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.profile_manager import _PROFILE_NAME_RE as _PROFILE_NAME_RE
from services.profile_manager import ProfileManager
from storage.database import get_session

BASE_DIR = Path(__file__).parent.parent
PROFILES_DIR = Path(os.environ.get("DEAL_HUNTER_PROFILES_DIR", str(BASE_DIR / "profiles")))


def _get_mgr() -> ProfileManager:
    """Return a ProfileManager bound to current PROFILES_DIR (respects patching)."""
    return ProfileManager(PROFILES_DIR)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a SQLAlchemy session with auto commit/rollback."""
    with get_session() as session:
        yield session


def safe_profile_path(name: str) -> Path:
    """Validate profile name and return resolved path, or raise 400."""
    path = _get_mgr().safe_path(name)
    if path is None:
        raise HTTPException(status_code=400, detail="Invalid profile name")
    return path


def safe_load_profile(name: str) -> dict | None:
    """Load profile YAML via ProfileManager."""
    return _get_mgr().load(name)


def get_profiles() -> list[str]:
    """Get available profile names via ProfileManager."""
    return _get_mgr().list_all()

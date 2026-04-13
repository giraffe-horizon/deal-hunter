# dashboard/dependencies.py
"""Shared dependencies for dashboard routes."""

import os
import re
from collections.abc import Iterator
from pathlib import Path

import yaml
from fastapi import HTTPException
from sqlalchemy.orm import Session

from storage.database import get_session

BASE_DIR = Path(__file__).parent.parent
PROFILES_DIR = Path(os.environ.get("DEAL_HUNTER_PROFILES_DIR", str(BASE_DIR / "profiles")))

_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a SQLAlchemy session with auto commit/rollback."""
    with get_session() as session:
        yield session


def safe_profile_path(name: str) -> Path:
    """Validate profile name and return resolved path, or raise 400."""
    if not _PROFILE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid profile name")
    path = (PROFILES_DIR / f"{name}.yaml").resolve()
    if not path.is_relative_to(PROFILES_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid profile name")
    return path


def safe_load_profile(name: str) -> dict | None:
    """Load profile YAML directly from PROFILES_DIR (respects env var override)."""
    path = safe_profile_path(name)
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return dict(data) if data else None
    except (yaml.YAMLError, OSError):
        return None


def get_profiles() -> list[str]:
    """Get available profile names from PROFILES_DIR (respects env var override)."""
    if not PROFILES_DIR.exists():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.yaml"))

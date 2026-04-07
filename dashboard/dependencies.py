"""Shared dependencies for dashboard routes."""

import os
import re
from pathlib import Path

import yaml
from fastapi import HTTPException

from storage.sqlite import SQLiteStorage

BASE_DIR = Path(__file__).parent.parent
DB_PATH = Path(os.environ.get("DEAL_HUNTER_DB_PATH", str(BASE_DIR / "state" / "deals.db")))
PROFILES_DIR = Path(os.environ.get("DEAL_HUNTER_PROFILES_DIR", str(BASE_DIR / "profiles")))

_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def get_db():
    """FastAPI dependency: yields SQLiteStorage instance, closes after request."""
    db = SQLiteStorage(DB_PATH)
    try:
        yield db
    finally:
        db.close()


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
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return dict(data) if data else None
    except (yaml.YAMLError, OSError):
        return None


def get_profiles() -> list[str]:
    """Get available profile names from PROFILES_DIR (respects env var override)."""
    if not PROFILES_DIR.exists():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.yaml"))

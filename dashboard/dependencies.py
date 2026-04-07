"""Shared dependencies for dashboard routes."""

import re
from pathlib import Path

from fastapi import HTTPException

from storage.sqlite import SQLiteStorage

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "state" / "deals.db"
PROFILES_DIR = BASE_DIR / "profiles"

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
    """Load profile without sys.exit on missing files."""
    try:
        from deal_hunter import load_profile

        return load_profile(name)
    except SystemExit:
        return None


def get_profiles() -> list[str]:
    """Get available profile names, gracefully handling missing profiles dir."""
    try:
        from deal_hunter import list_profiles

        return sorted(list_profiles())
    except Exception:
        return []

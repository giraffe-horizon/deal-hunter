"""Deal Hunter Web Dashboard — FastAPI application.

Package layout:

* ``templating.py`` — Jinja2 environment + filters + version constant
* ``middleware.py`` — ASGI middlewares (CSRF check)
* ``app.py`` — ``create_app()`` factory
* ``routes/`` — per-feature routers

The package-level ``app`` is the default instance wired up via ``create_app()``
— used by uvicorn and tests that patch dependencies onto a shared app.
"""

from deal_hunter.api.app import create_app

# Re-export dependencies so legacy `from deal_hunter.api import get_db, ...` still works.
from deal_hunter.api.dependencies import (
    get_db,
    get_profiles,
    safe_load_profile,
    safe_profile_path,
)
from deal_hunter.api.dependencies import get_profiles as _get_profiles  # legacy alias
from deal_hunter.api.templating import API_DIR, APP_VERSION, format_pln, templates

# Default application instance (used by uvicorn target `deal_hunter.api:app`)
app = create_app()

__all__ = [
    "API_DIR",
    "APP_VERSION",
    "_get_profiles",
    "app",
    "create_app",
    "format_pln",
    "get_db",
    "get_profiles",
    "safe_load_profile",
    "safe_profile_path",
    "templates",
]

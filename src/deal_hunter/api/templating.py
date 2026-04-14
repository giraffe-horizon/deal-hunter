"""Jinja2 template environment + custom filters and globals.

Separate from `api/app.py` so that route modules can import `templates`
without triggering the full FastAPI app construction.
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

from fastapi.templating import Jinja2Templates

API_DIR = Path(__file__).parent  # src/deal_hunter/api/

try:
    APP_VERSION = importlib.metadata.version("deal-hunter")
except importlib.metadata.PackageNotFoundError:
    from deal_hunter import __version__

    APP_VERSION = __version__


def format_pln(value: int | None) -> str:
    """Format integer price as PLN string: 8500 -> '8 500 zl'."""
    if value is None or value == 0:
        return "0 zl"
    formatted = f"{value:,}".replace(",", " ")
    return f"{formatted} zl"


templates = Jinja2Templates(directory=str(API_DIR / "templates"))
templates.env.autoescape = True
templates.env.filters["format_pln"] = format_pln
templates.env.globals["app_version"] = APP_VERSION

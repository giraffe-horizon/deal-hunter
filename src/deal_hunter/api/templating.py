"""Jinja2 template environment + custom filters and globals.

Separate from `api/app.py` so that route modules can import `templates`
without triggering the full FastAPI app construction.
"""

from __future__ import annotations

import importlib.metadata
from datetime import datetime
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


def humanize_age(iso: str | None, now: datetime | None = None) -> str:
    """Return a compact relative age string: '3d ago', '5m ago', 'now', '—' for missing."""
    if not iso:
        return "—"
    try:
        ts = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return "—"
    current = now or datetime.now()
    if ts.tzinfo is not None and current.tzinfo is None:
        current = current.replace(tzinfo=ts.tzinfo)
    elif ts.tzinfo is None and current.tzinfo is not None:
        ts = ts.replace(tzinfo=current.tzinfo)
    delta = current - ts
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    months = days // 30
    if months < 12:
        return f"{months}mo ago"
    return f"{days // 365}y ago"


templates = Jinja2Templates(directory=str(API_DIR / "templates"))
templates.env.autoescape = True
templates.env.filters["format_pln"] = format_pln
templates.env.filters["humanize_age"] = humanize_age
templates.env.globals["app_version"] = APP_VERSION

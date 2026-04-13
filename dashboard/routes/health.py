"""Health and price trends routes."""

import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dashboard import templates
from services.health_tracker import HealthTracker

router = APIRouter()

_BASE_DIR = Path(__file__).parent.parent.parent
_state_dir = Path(os.environ.get("DEAL_HUNTER_STATE_DIR", str(_BASE_DIR / "state")))
_tracker = HealthTracker(_state_dir / "health.json")


@router.get("/health")
def health_page(request: Request) -> HTMLResponse:
    health = _tracker.load()

    # Compute summary metrics from health data
    total_deals = 0
    total_alerts = 0
    errors = []
    if health and "profile_results" in health:
        for name, result in health["profile_results"].items():
            total_deals += result.get("deals_found", 0)
            total_alerts += result.get("new_alerts", 0)
            for err in result.get("errors", []):
                errors.append({"profile": name, "message": err})

    return templates.TemplateResponse(
        request,
        "health.html",
        {
            "health": health,
            "total_deals": total_deals,
            "total_alerts": total_alerts,
            "errors": errors,
        },
    )


@router.get("/api/health-status")
def api_health_status(request: Request) -> HTMLResponse:
    """Compact health status for sidebar indicator."""
    from datetime import datetime

    health = _tracker.load()
    status = health.get("status") if health else None
    age = None
    if health and health.get("last_run"):
        try:
            last_run = datetime.fromisoformat(health["last_run"])
            delta = datetime.now() - last_run
            if delta.days > 0:
                age = f"{delta.days}d ago"
            elif delta.seconds >= 3600:
                age = f"{delta.seconds // 3600}h ago"
            else:
                age = f"{delta.seconds // 60}m ago"
        except (ValueError, TypeError):
            pass

    return templates.TemplateResponse(
        request,
        "partials/health_indicator.html",
        {"health_status": status, "health_age": age or "unknown"},
    )


@router.get("/price-trends")
def price_trends_redirect(days: int = 7) -> RedirectResponse:
    """Redirect old Price Trends page to Deals Explorer drops view."""
    return RedirectResponse(f"/deals?view=drops&days={days}", status_code=302)

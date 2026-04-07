"""Health and price trends routes."""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from dashboard import templates

router = APIRouter()


@router.get("/health")
def health_page(request: Request):
    from health import load_health

    health = load_health()

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


@router.get("/price-trends")
def price_trends_redirect(days: int = 7):
    """Redirect old Price Trends page to Deals Explorer drops view."""
    return RedirectResponse(f"/deals?view=drops&days={days}", status_code=302)

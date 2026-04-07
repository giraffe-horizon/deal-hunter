"""Health and price trends routes."""

from fastapi import APIRouter, Depends, Request

from dashboard import templates
from dashboard.dependencies import get_db
from storage.sqlite import SQLiteStorage

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
def price_trends_page(
    request: Request,
    days: int = 7,
    db: SQLiteStorage = Depends(get_db),
):
    drops = db.get_price_drops(days=days)
    all_deals = db.get_deals()

    # Compute summary metrics
    total_drops = len(drops)
    avg_drop_pct = (
        round(sum(d["diff_percent"] for d in drops) / total_drops, 1) if total_drops else 0
    )
    biggest_drop = max((d["diff_pln"] for d in drops), default=0)

    # Category distribution from all deals
    categories: dict[str, int] = {}
    for deal in all_deals:
        cat = deal.get("category") or "Uncategorized"
        categories[cat] = categories.get(cat, 0) + 1
    categories = dict(sorted(categories.items(), key=lambda x: x[1], reverse=True))

    # Sparkline data for top 3 categories
    category_trends: dict[str, list[dict]] = {}
    for cat_name in list(categories.keys())[:3]:
        trend = db.get_category_price_trend(cat_name, days=30)
        if trend:
            category_trends[cat_name] = trend

    return templates.TemplateResponse(
        request,
        "price_trends.html",
        {
            "drops": drops,
            "days": days,
            "total_drops": total_drops,
            "avg_drop_pct": avg_drop_pct,
            "biggest_drop": biggest_drop,
            "categories": categories,
            "category_trends": category_trends,
        },
    )

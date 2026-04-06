"""Deal Hunter Web Dashboard — FastAPI application."""

import importlib.metadata
import math
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from storage.sqlite import SQLiteStorage

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "state" / "deals.db"

DEALS_PER_PAGE = 50
SCORE_THRESHOLD = 70

try:
    APP_VERSION = importlib.metadata.version("deal-hunter")
except importlib.metadata.PackageNotFoundError:
    from deal_hunter import __version__

    APP_VERSION = __version__

app = FastAPI(title="Deal Hunter Dashboard", version=APP_VERSION)
templates = Jinja2Templates(directory=str(BASE_DIR / "dashboard" / "templates"))


def format_pln(value: int | None) -> str:
    """Format integer price as PLN string: 8500 -> '8 500 zl'."""
    if value is None or value == 0:
        return "0 zl"
    formatted = f"{value:,}".replace(",", " ")
    return f"{formatted} zl"


templates.env.filters["format_pln"] = format_pln
templates.env.globals["app_version"] = APP_VERSION


def get_db():
    """FastAPI dependency: yields SQLiteStorage instance, closes after request."""
    db = SQLiteStorage(DB_PATH)
    try:
        yield db
    finally:
        db.close()


def safe_load_profile(name: str) -> dict | None:
    """Load profile without sys.exit on missing files."""
    try:
        from deal_hunter import load_profile

        return load_profile(name)
    except SystemExit:
        return None


def _get_profiles() -> list[str]:
    """Get available profile names, gracefully handling missing profiles dir."""
    try:
        from deal_hunter import list_profiles

        return sorted(list_profiles())
    except Exception:
        return []


@app.get("/")
def index():
    return RedirectResponse(url="/deals", status_code=302)


@app.get("/deals")
def deals_page(
    request: Request,
    profile: str | None = None,
    source: str | None = None,
    min_score: int | None = None,
    category: str | None = None,
    status: str | None = None,
    page: int = 1,
    db: SQLiteStorage = Depends(get_db),
):
    # Normalize empty string params to None
    profile = profile or None
    source = source or None
    category = category or None
    status = status or None
    page = max(1, page)

    offset = (page - 1) * DEALS_PER_PAGE
    deals = db.get_deals(
        profile=profile,
        source=source,
        min_score=min_score,
        category=category,
        status=status,
        limit=DEALS_PER_PAGE,
        offset=offset,
    )
    total_filtered = db.count_deals(
        profile=profile,
        source=source,
        min_score=min_score,
        category=category,
        status=status,
    )
    total_pages = max(1, math.ceil(total_filtered / DEALS_PER_PAGE))

    # Build filter query string for pagination links
    filter_params = ""
    if profile:
        filter_params += f"&profile={profile}"
    if source:
        filter_params += f"&source={source}"
    if min_score is not None:
        filter_params += f"&min_score={min_score}"
    if category:
        filter_params += f"&category={category}"
    if status:
        filter_params += f"&status={status}"

    # HTMX partial refresh — return only the table fragment
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "partials/deals_table.html",
            {
                "deals": deals,
                "page": page,
                "total_pages": total_pages,
                "total_filtered": total_filtered,
                "filter_params": filter_params,
            },
        )

    # Compute metrics via SQL aggregates (no full table scan)
    stats = db.get_deal_stats(score_threshold=SCORE_THRESHOLD)
    total_deals = stats["total"]
    high_score_pct = round(stats["high_score"] / total_deals * 100) if total_deals else 0
    new_today = stats["new_today"]
    drops_count = len(db.get_price_drops(days=7))

    # Filter dropdown options via SQL
    filter_opts = db.get_filter_options()
    profiles = _get_profiles()

    return templates.TemplateResponse(
        request,
        "deals.html",
        {
            "deals": deals,
            "total_deals": total_deals,
            "high_score_pct": high_score_pct,
            "score_threshold": SCORE_THRESHOLD,
            "new_today": new_today,
            "drops_count": drops_count,
            "profiles": profiles,
            "sources": filter_opts["sources"],
            "categories": filter_opts["categories"],
            "selected_profile": profile,
            "selected_source": source,
            "selected_min_score": min_score,
            "selected_category": category,
            "selected_status": status,
            "page": page,
            "total_pages": total_pages,
            "total_filtered": total_filtered,
            "filter_params": filter_params,
        },
    )


@app.get("/health")
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


@app.get("/price-trends")
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


@app.get("/deals/{deal_id}")
def deal_detail_page(
    request: Request,
    deal_id: str,
    db: SQLiteStorage = Depends(get_db),
):
    deal = db.get_deal(deal_id)
    if not deal:
        return HTMLResponse(content="Deal not found", status_code=404)

    price_history = db.get_price_history(deal_id)
    lowest_price = db.get_lowest_price(deal_id)
    previous_price = db.get_previous_price(deal_id)

    return templates.TemplateResponse(
        request,
        "deal_detail.html",
        {
            "deal": deal,
            "price_history": price_history,
            "lowest_price": lowest_price,
            "previous_price": previous_price,
        },
    )


@app.get("/api/price-history/{deal_id}")
def api_price_history(deal_id: str, db: SQLiteStorage = Depends(get_db)):
    history = db.get_price_history(deal_id)
    if not history:
        return {"labels": [], "prices": [], "lowest": None, "highest": None}

    labels = [h["recorded_at"][:10] for h in history]  # YYYY-MM-DD
    prices = [h["price"] for h in history]

    return {
        "labels": labels,
        "prices": prices,
        "lowest": min(prices),
        "highest": max(prices),
    }


@app.post("/api/deals/{deal_id}/status")
def api_update_deal_status(
    deal_id: str,
    status: str = Form(...),
    db: SQLiteStorage = Depends(get_db),
):
    if status not in ("watching", "rejected", "active"):
        return JSONResponse({"error": "Invalid status"}, status_code=400)
    ok = db.update_deal_status(deal_id, status)
    if not ok:
        return JSONResponse({"error": "Deal not found"}, status_code=404)
    # Return HTML fragment for HTMX swap — must include full action buttons
    # so the user can change status again
    deal = db.get_deal(deal_id)
    link = deal["link"] if deal else "#"
    encoded_id = deal_id.replace(":", "%3A")

    status_badge = {
        "watching": '<span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-primary-container text-primary">Watching</span>',
        "rejected": '<span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-error-container/30 text-error">Skipped</span>',
        "active": '<span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-tertiary-container/30 text-tertiary">Active</span>',
    }[status]

    return HTMLResponse(
        f'<a href="{link}" target="_blank" rel="noopener noreferrer"'
        f'   class="inline-flex items-center gap-2 px-4 py-2.5 bg-primary text-on-primary rounded-card text-sm font-medium hover:bg-primary-dim transition-colors">'
        f'  <span class="material-symbols-outlined text-[18px]">open_in_new</span>Open Link</a>'
        f'<button hx-post="/api/deals/{encoded_id}/status" hx-vals=\'{{"status": "watching"}}\''
        f'        hx-target="#action-buttons" hx-swap="innerHTML"'
        f'        class="inline-flex items-center gap-2 px-4 py-2.5 bg-surface-container-high text-on-surface rounded-card text-sm font-medium hover:bg-surface-container-highest transition-colors">'
        f'  <span class="material-symbols-outlined text-[18px]">visibility</span>Watch</button>'
        f'<button hx-post="/api/deals/{encoded_id}/status" hx-vals=\'{{"status": "rejected"}}\''
        f'        hx-target="#action-buttons" hx-swap="innerHTML"'
        f'        class="inline-flex items-center gap-2 px-4 py-2.5 bg-surface-container-high text-on-surface-variant rounded-card text-sm font-medium hover:bg-error-container/20 hover:text-error transition-colors">'
        f'  <span class="material-symbols-outlined text-[18px]">block</span>Skip</button>'
        f"{status_badge}"
    )


@app.get("/api/deals")
def api_deals(
    profile: str | None = None,
    source: str | None = None,
    min_score: int | None = None,
    category: str | None = None,
    status: str | None = None,
    db: SQLiteStorage = Depends(get_db),
):
    return db.get_deals(
        profile=profile or None,
        source=source or None,
        min_score=min_score,
        category=category or None,
        status=status or None,
    )


@app.get("/api/stats")
def api_stats(db: SQLiteStorage = Depends(get_db)):
    stats = db.get_deal_stats(score_threshold=SCORE_THRESHOLD)
    total = stats["total"]
    drops = db.get_price_drops(days=7)
    return {
        "total_deals": total,
        "high_score_pct": round(stats["high_score"] / total * 100) if total else 0,
        "new_today": stats["new_today"],
        "drops_count": len(drops),
    }


@app.get("/watchlist", response_class=HTMLResponse)
async def watchlist_page(request: Request, db: SQLiteStorage = Depends(get_db)):
    """Watchlist page — deals with target price alerts."""
    items = db.get_watchlist()
    return templates.TemplateResponse(
        request,
        "watchlist.html",
        {"items": items},
    )


@app.post("/api/watchlist")
async def add_to_watchlist_api(
    request: Request,
    db: SQLiteStorage = Depends(get_db),
):
    """Add a deal to the watchlist."""
    form = await request.form()
    deal_id = form.get("deal_id", "")
    target_price = int(form.get("target_price", 0))
    if deal_id and target_price > 0:
        db.add_to_watchlist(deal_id, target_price)
    return HTMLResponse('<span class="text-sm text-tertiary font-medium">\u2713 Target set</span>')


@app.delete("/api/watchlist/{deal_id:path}")
async def remove_from_watchlist_api(
    deal_id: str,
    db: SQLiteStorage = Depends(get_db),
):
    """Remove a deal from the watchlist."""
    db.remove_from_watchlist(deal_id)
    return HTMLResponse("")

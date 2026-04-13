"""Deal-related routes: listing, detail, compare, API endpoints."""

import math

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from dashboard import templates
from dashboard.dependencies import get_db, get_profiles
from dashboard.services import DEALS_PER_PAGE, SCORE_THRESHOLD, DealService
from storage.repositories import DealRepository, PriceRepository

router = APIRouter()


@router.get("/deals")
def deals_page(
    request: Request,
    view: str = "",
    profile: str | None = None,
    source: str | None = None,
    min_score: int | None = None,
    category: str | None = None,
    status: str | None = None,
    page: int = 1,
    days: int = 7,
    session: Session = Depends(get_db),
):
    # Price Drops view
    if view == "drops":
        return _price_drops_view(request, days, session)

    # Normalize empty string params to None
    profile = profile or None
    source = source or None
    category = category or None
    status = status or None
    page = max(1, page)

    offset = (page - 1) * DEALS_PER_PAGE
    deals = DealRepository(session).get_filtered(
        profile=profile,
        source=source,
        min_score=min_score,
        category=category,
        status=status,
        limit=DEALS_PER_PAGE,
        offset=offset,
    )
    total_filtered = DealRepository(session).count(
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

    sparklines = DealService(session).get_sparklines(deals)

    # HTMX partial refresh — return only the table fragment
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "partials/deals_table.html",
            {
                "deals": deals,
                "sparklines": sparklines,
                "page": page,
                "total_pages": total_pages,
                "total_filtered": total_filtered,
                "filter_params": filter_params,
            },
        )

    # Compute metrics via SQL aggregates (no full table scan)
    stats = DealRepository(session).get_stats(score_threshold=SCORE_THRESHOLD)
    total_deals = stats["total"]
    high_score_pct = round(stats["high_score"] / total_deals * 100) if total_deals else 0
    new_today = stats["new_today"]
    drops_count = PriceRepository(session).count_drops(days=7)

    # Filter dropdown options via SQL
    filter_opts = DealRepository(session).get_filter_options()
    profiles = get_profiles()

    return templates.TemplateResponse(
        request,
        "deals.html",
        {
            "deals": deals,
            "sparklines": sparklines,
            "view": "",
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


def _price_drops_view(request: Request, days: int, session: Session):
    """Build the price drops view (shared by /deals?view=drops and redirect)."""
    drops = PriceRepository(session).get_drops(days=days)
    all_deals = DealRepository(session).get_filtered()

    total_drops = len(drops)
    avg_drop_pct = (
        round(sum(d["diff_percent"] for d in drops) / total_drops, 1) if total_drops else 0
    )
    biggest_drop = max((d["diff_pln"] for d in drops), default=0)

    categories: dict[str, int] = {}
    for deal in all_deals:
        cat = deal.get("category") or "Uncategorized"
        categories[cat] = categories.get(cat, 0) + 1
    categories = dict(sorted(categories.items(), key=lambda x: x[1], reverse=True))

    category_trends: dict[str, list[dict]] = {}
    for cat_name in list(categories.keys())[:3]:
        trend = DealRepository(session).get_category_price_trend(cat_name, days=30)
        if trend:
            category_trends[cat_name] = trend

    context = {
        "drops": drops,
        "days": days,
        "view": "drops",
        "total_drops": total_drops,
        "avg_drop_pct": avg_drop_pct,
        "biggest_drop": biggest_drop,
        "categories": categories,
        "category_trends": category_trends,
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "partials/price_drops_view.html", context)

    return templates.TemplateResponse(request, "deals.html", context)


@router.get("/deals/{deal_id}")
def deal_detail_page(
    request: Request,
    deal_id: str,
    session: Session = Depends(get_db),
):
    deal = DealRepository(session).get_by_id(deal_id)
    if not deal:
        return HTMLResponse(content="Deal not found", status_code=404)

    price_history = PriceRepository(session).get_history(deal_id)
    lowest_price = PriceRepository(session).get_lowest(deal_id)
    previous_price = PriceRepository(session).get_previous_price(deal_id)
    score_data = DealService(session).score_single_deal(deal)

    return templates.TemplateResponse(
        request,
        "deal_detail.html",
        {
            "deal": deal,
            "price_history": price_history,
            "lowest_price": lowest_price,
            "previous_price": previous_price,
            "score_data": score_data,
        },
    )


@router.get("/compare", response_class=HTMLResponse)
def compare_deals(request: Request, ids: str = "", session: Session = Depends(get_db)):
    deal_ids = [i.strip() for i in ids.split(",") if i.strip()] if ids else []
    data = DealService(session).get_comparison_data(deal_ids)
    return templates.TemplateResponse(
        request,
        "compare.html",
        {"active_page": "deals", **data},
    )


@router.get("/api/price-history/{deal_id}")
def api_price_history(deal_id: str, session: Session = Depends(get_db)):
    history = PriceRepository(session).get_history(deal_id)
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


@router.post("/api/deals/{deal_id}/status")
def api_update_deal_status(
    request: Request,
    deal_id: str,
    status: str = Form(...),
    inline: str = Form(""),
    session: Session = Depends(get_db),
):
    if status not in ("watching", "rejected", "active"):
        return JSONResponse({"error": "Invalid status"}, status_code=400)
    ok = DealRepository(session).update_status(deal_id, status)
    if not ok:
        return JSONResponse({"error": "Deal not found"}, status_code=404)
    if inline:
        return templates.TemplateResponse(
            request,
            "partials/deal_row_status.html",
            {"current_status": status},
        )
    # Return HTML fragment for HTMX swap — must include full action buttons
    # so the user can change status again
    deal = DealRepository(session).get_by_id(deal_id)
    link = deal["link"] if deal else "#"
    encoded_id = deal_id.replace(":", "%3A")

    return templates.TemplateResponse(
        request,
        "partials/deal_action_buttons.html",
        {
            "deal_link": link,
            "deal_id_encoded": encoded_id,
            "current_status": status,
        },
    )


@router.get("/api/deals")
def api_deals(
    profile: str | None = None,
    source: str | None = None,
    min_score: int | None = None,
    category: str | None = None,
    status: str | None = None,
    session: Session = Depends(get_db),
):
    return DealRepository(session).get_filtered(
        profile=profile or None,
        source=source or None,
        min_score=min_score,
        category=category or None,
        status=status or None,
    )


@router.get("/api/stats")
def api_stats(session: Session = Depends(get_db)):
    stats = DealRepository(session).get_stats(score_threshold=SCORE_THRESHOLD)
    total = stats["total"]
    drops = PriceRepository(session).get_drops(days=7)
    return {
        "total_deals": total,
        "high_score_pct": round(stats["high_score"] / total * 100) if total else 0,
        "new_today": stats["new_today"],
        "drops_count": len(drops),
    }

"""Deal-related routes: listing, detail, compare, API endpoints."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from dashboard import templates
from dashboard.dependencies import get_db, get_profiles
from dashboard.schemas import StatusUpdate
from dashboard.services import DEALS_PER_PAGE, SCORE_THRESHOLD, DealService
from storage.repositories import OfferRepository, PriceRepository

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
) -> HTMLResponse:
    svc = DealService(session)

    # Price Drops view
    if view == "drops":
        return _price_drops_view(request, svc, days)

    is_htmx = bool(request.headers.get("HX-Request"))
    data = svc.get_deals_page(
        profile=profile,
        source=source,
        min_score=min_score,
        category=category,
        status=status,
        page=page,
        per_page=DEALS_PER_PAGE,
        score_threshold=SCORE_THRESHOLD,
        include_stats=not is_htmx,
    )

    # HTMX partial refresh — return only the table fragment
    if is_htmx:
        return templates.TemplateResponse(
            request,
            "partials/deals_table.html",
            {
                "deals": data.deals,
                "sparklines": data.sparklines,
                "page": data.page,
                "total_pages": data.total_pages,
                "total_filtered": data.total_filtered,
                "filter_params": data.filter_params,
            },
        )

    return templates.TemplateResponse(
        request,
        "deals.html",
        {
            "deals": data.deals,
            "sparklines": data.sparklines,
            "view": "",
            "total_deals": data.total_deals,
            "high_score_pct": data.high_score_pct,
            "score_threshold": SCORE_THRESHOLD,
            "new_today": data.new_today,
            "drops_count": data.drops_count,
            "profiles": get_profiles(),
            "sources": data.sources,
            "categories": data.categories,
            "selected_profile": profile or None,
            "selected_source": source or None,
            "selected_min_score": min_score,
            "selected_category": category or None,
            "selected_status": status or None,
            "page": data.page,
            "total_pages": data.total_pages,
            "total_filtered": data.total_filtered,
            "filter_params": data.filter_params,
        },
    )


def _price_drops_view(request: Request, svc: DealService, days: int) -> HTMLResponse:
    """Build the price drops view (shared by /deals?view=drops and redirect)."""
    data = svc.get_price_drops(days=days)
    context = {**asdict(data), "view": "drops"}

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "partials/price_drops_view.html", context)

    return templates.TemplateResponse(request, "deals.html", context)


@router.get("/deals/{deal_id}")
def deal_detail_page(
    request: Request,
    deal_id: str,
    session: Session = Depends(get_db),
) -> HTMLResponse:
    deal = OfferRepository(session).get_by_id(deal_id)
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
def compare_deals(
    request: Request, ids: str = "", session: Session = Depends(get_db)
) -> HTMLResponse:
    deal_ids = [i.strip() for i in ids.split(",") if i.strip()] if ids else []
    data = DealService(session).get_comparison_data(deal_ids)
    return templates.TemplateResponse(
        request,
        "compare.html",
        {"active_page": "deals", **data},
    )


@router.get("/api/price-history/{deal_id}")
def api_price_history(deal_id: str, session: Session = Depends(get_db)) -> dict:
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
) -> Response:
    try:
        validated = StatusUpdate(status=status)
    except Exception:
        return JSONResponse({"error": "Invalid status"}, status_code=400)
    ok = OfferRepository(session).update_status(deal_id, validated.status)
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
    deal = OfferRepository(session).get_by_id(deal_id)
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
) -> list:
    return OfferRepository(session).get_filtered(
        profile=profile or None,
        source=source or None,
        min_score=min_score,
        category=category or None,
        status=status or None,
    )


@router.get("/api/stats")
def api_stats(session: Session = Depends(get_db)) -> dict:
    return DealService(session).get_stats(score_threshold=SCORE_THRESHOLD)

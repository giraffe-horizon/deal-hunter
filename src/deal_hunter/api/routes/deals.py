"""Deal-related routes: listing, detail, compare, API endpoints."""

import csv
import io
import json
from collections.abc import Iterator
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from deal_hunter.api import templates
from deal_hunter.api.dependencies import get_db, get_profiles
from deal_hunter.api.schemas import BulkRequest, StatusUpdate
from deal_hunter.api.view_services import DEALS_PER_PAGE, SCORE_THRESHOLD, DealService
from deal_hunter.storage.repositories import (
    FeedbackRepository,
    OfferRepository,
    PriceRepository,
    WatchlistRepository,
)

SortColumn = Literal["title", "price", "source", "profile", "score", "status", "date"]
SortDirection = Literal["asc", "desc"]
BULK_MAX_ROWS = 100_000
COMPARE_MAX_IDS = 4

# Map dashboard status changes to the feedback-log "action" string used by the
# Telegram bot. Keeping the vocabulary aligned lets /status stats aggregate
# across both surfaces.
_STATUS_TO_FEEDBACK_ACTION = {
    "watching": "watch",
    "rejected": "skip",
    "active": "restore",
}


def _parse_optional_int(raw: str | None) -> int | None:
    # HTMX <select> sends `name=` (empty string) when "All" is picked. FastAPI
    # would 422 on `int | None`; treat empty/whitespace as "no filter".
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


router = APIRouter()


@router.get("/deals")
def deals_page(
    request: Request,
    view: str = "",
    profile: str | None = None,
    source: str | None = None,
    min_score: str | None = None,
    category: str | None = None,
    status: str | None = None,
    sort: SortColumn | None = None,
    dir: SortDirection | None = None,  # noqa: A002
    page: int = 1,
    days: int = 7,
    session: Session = Depends(get_db),
) -> HTMLResponse:
    svc = DealService(session)

    # Price Drops view
    if view == "drops":
        return _price_drops_view(request, svc, days)

    min_score_int = _parse_optional_int(min_score)
    is_htmx = bool(request.headers.get("HX-Request"))
    data = svc.get_deals_page(
        profile=profile,
        source=source,
        min_score=min_score_int,
        category=category,
        status=status,
        sort=sort,
        direction=dir,
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
                "filter_params_no_sort": data.filter_params_no_sort,
                "sort": sort,
                "direction": dir,
                "page_url": "/deals",
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
            "selected_min_score": min_score_int,
            "selected_category": category or None,
            "selected_status": status or None,
            "sort": sort,
            "direction": dir,
            "page": data.page,
            "total_pages": data.total_pages,
            "total_filtered": data.total_filtered,
            "filter_params": data.filter_params,
            "filter_params_no_sort": data.filter_params_no_sort,
            "page_url": "/deals",
        },
    )


@router.get("/watchlist", response_class=HTMLResponse)
def watchlist_page(
    request: Request,
    page: int = 1,
    session: Session = Depends(get_db),
) -> HTMLResponse:
    """Bookmark-style watchlist — lists offers with status='watching'."""
    data = DealService(session).get_deals_page(
        status="watching",
        page=page,
        per_page=DEALS_PER_PAGE,
        score_threshold=SCORE_THRESHOLD,
        include_stats=False,
    )
    is_htmx = bool(request.headers.get("HX-Request"))
    template_name = "partials/deals_table.html" if is_htmx else "watchlist.html"
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "page_url": "/watchlist",
            "deals": data.deals,
            "sparklines": data.sparklines,
            "page": data.page,
            "total_pages": data.total_pages,
            "total_filtered": data.total_filtered,
            "filter_params": data.filter_params,
            "filter_params_no_sort": data.filter_params_no_sort,
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
    FeedbackRepository(session).record(deal_id, _STATUS_TO_FEEDBACK_ACTION[validated.status])
    encoded_id = deal_id.replace(":", "%3A")
    dom_id = deal_id.replace(":", "-")
    if inline:
        return templates.TemplateResponse(
            request,
            "partials/deal_row_actions.html",
            {
                "deal_id_encoded": encoded_id,
                "deal_dom_id": dom_id,
                "current_status": validated.status,
            },
        )
    # Return HTML fragment for HTMX swap — must include full action buttons
    # so the user can change status again
    deal = OfferRepository(session).get_by_id(deal_id)
    link = deal["link"] if deal else "#"

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
    min_score: str | None = None,
    category: str | None = None,
    status: str | None = None,
    session: Session = Depends(get_db),
) -> list:
    return OfferRepository(session).get_filtered(
        profile=profile or None,
        source=source or None,
        min_score=_parse_optional_int(min_score),
        category=category or None,
        status=status or None,
    )


@router.get("/api/stats")
def api_stats(session: Session = Depends(get_db)) -> dict:
    return DealService(session).get_stats(score_threshold=SCORE_THRESHOLD)


def _filters_from_query(
    profile: str | None,
    source: str | None,
    min_score: str | None,
    category: str | None,
    status: str | None,
) -> dict:
    """Normalize query-string filter args to OfferRepository keyword args."""
    return {
        "profile": profile or None,
        "source": source or None,
        "min_score": _parse_optional_int(min_score),
        "category": category or None,
        "status": status or None,
    }


@router.get("/api/deals/count")
def api_deals_count(
    profile: str | None = None,
    source: str | None = None,
    min_score: str | None = None,
    category: str | None = None,
    status: str | None = None,
    session: Session = Depends(get_db),
) -> dict:
    count = OfferRepository(session).count(
        **_filters_from_query(profile, source, min_score, category, status)
    )
    return {"count": count}


@router.get("/api/deals/ids")
def api_deals_ids(
    profile: str | None = None,
    source: str | None = None,
    min_score: str | None = None,
    category: str | None = None,
    status: str | None = None,
    session: Session = Depends(get_db),
) -> dict:
    ids = OfferRepository(session).get_filtered_ids(
        **_filters_from_query(profile, source, min_score, category, status)
    )
    return {"ids": ids, "count": len(ids)}


def _resolve_bulk_ids(payload: BulkRequest, session: Session) -> list[str]:
    """Materialize the list of deal ids referenced by an ids-mode or filter-mode request."""
    if payload.ids is not None:
        return list(payload.ids)
    assert payload.filter is not None
    ids = OfferRepository(session).get_filtered_ids(**payload.filter.to_kwargs())
    excluded = set(payload.excluded)
    return [i for i in ids if i not in excluded]


@router.post("/api/deals/bulk")
def api_deals_bulk(
    payload: BulkRequest,
    session: Session = Depends(get_db),
) -> Response:
    ids = _resolve_bulk_ids(payload, session)
    if len(ids) > BULK_MAX_ROWS:
        raise HTTPException(status_code=413, detail=f"Too many rows ({len(ids)} > {BULK_MAX_ROWS})")

    if payload.action == "compare":
        capped = ids[:COMPARE_MAX_IDS]
        if not capped:
            raise HTTPException(status_code=400, detail="No ids to compare")
        redirect = "/compare?ids=" + ",".join(capped)
        return JSONResponse({"redirect": redirect})

    if not ids:
        return JSONResponse({"updated": 0})

    if payload.action == "set-status":
        assert payload.status is not None
        updated = OfferRepository(session).bulk_update_status(ids, payload.status)
        FeedbackRepository(session).record_many(ids, _STATUS_TO_FEEDBACK_ACTION[payload.status])
        return JSONResponse({"updated": updated, "action": "set-status", "status": payload.status})

    if payload.action == "set-target":
        assert payload.target_price is not None
        updated = WatchlistRepository(session).bulk_upsert(ids, payload.target_price)
        return JSONResponse(
            {"updated": updated, "action": "set-target", "target_price": payload.target_price}
        )

    raise HTTPException(status_code=400, detail="Unknown action")


_EXPORT_COLUMNS = [
    "id",
    "title",
    "price",
    "source",
    "profile",
    "category",
    "status",
    "score",
    "first_seen_at",
    "last_seen_at",
    "link",
]


def _project(row: dict) -> dict:
    return {col: row.get(col) for col in _EXPORT_COLUMNS}


def _export_csv_iter(session: Session, filters: dict) -> Iterator[str]:
    """Yield CSV chunks from a live request session, cursor-streaming under yield_per."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_EXPORT_COLUMNS)
    writer.writeheader()
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate()

    for row in OfferRepository(session).iter_filtered(chunk=1000, **filters):
        writer.writerow(_project(row))
        if buf.tell() >= 8192:
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()
    if buf.tell():
        yield buf.getvalue()


def _export_json_iter(session: Session, filters: dict) -> Iterator[str]:
    """Yield a JSON array one element at a time — no full materialization."""
    yield "["
    first = True
    for row in OfferRepository(session).iter_filtered(chunk=1000, **filters):
        sep = "" if first else ","
        first = False
        yield sep + json.dumps(_project(row), default=str)
    yield "]"


@router.get("/api/deals/export")
def api_deals_export(
    format: str = "csv",  # noqa: A002
    profile: str | None = None,
    source: str | None = None,
    min_score: str | None = None,
    category: str | None = None,
    status: str | None = None,
    session: Session = Depends(get_db),
) -> StreamingResponse:
    if format not in {"csv", "json"}:
        raise HTTPException(status_code=422, detail="format must be csv or json")

    filters = _filters_from_query(profile, source, min_score, category, status)

    if format == "csv":
        return StreamingResponse(
            _export_csv_iter(session, filters),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=deals.csv"},
        )

    return StreamingResponse(
        _export_json_iter(session, filters),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=deals.json"},
    )

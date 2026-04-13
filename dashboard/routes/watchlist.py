"""Watchlist routes: view, add, remove, update target price."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from dashboard import templates
from dashboard.dependencies import get_db
from dashboard.schemas import WatchlistAdd, WatchlistUpdate
from dashboard.services import DealService
from storage.repositories import WatchlistRepository

router = APIRouter()


@router.get("/watchlist", response_class=HTMLResponse)
def watchlist_page(request: Request, session: Session = Depends(get_db)) -> HTMLResponse:
    """Watchlist page — deals with target price alerts."""
    items = WatchlistRepository(session).get_all()
    sparklines = DealService(session).get_sparklines(items)
    return templates.TemplateResponse(
        request,
        "watchlist.html",
        {"items": items, "sparklines": sparklines},
    )


@router.post("/api/watchlist")
async def add_to_watchlist_api(
    request: Request,
    session: Session = Depends(get_db),
) -> HTMLResponse:
    """Add a deal to the watchlist."""
    form = await request.form()
    try:
        validated = WatchlistAdd(
            deal_id=str(form.get("deal_id", "")),
            target_price=int(form.get("target_price", 0)),
        )
    except Exception:
        return HTMLResponse(
            '<span class="text-sm text-tertiary font-medium">\u2713 Target set</span>'
        )
    WatchlistRepository(session).add(validated.deal_id, validated.target_price)
    return HTMLResponse('<span class="text-sm text-tertiary font-medium">\u2713 Target set</span>')


@router.delete("/api/watchlist/{deal_id:path}")
def remove_from_watchlist_api(
    deal_id: str,
    session: Session = Depends(get_db),
) -> HTMLResponse:
    """Remove a deal from the watchlist."""
    WatchlistRepository(session).remove(deal_id)
    return HTMLResponse("")


@router.patch("/api/watchlist/{deal_id:path}")
async def update_watchlist_api(
    request: Request,
    deal_id: str,
    target_price: int = Form(...),
    session: Session = Depends(get_db),
) -> Response:
    """Update target price for a watchlist item."""
    try:
        WatchlistUpdate(target_price=target_price)
    except Exception:
        return JSONResponse({"error": "Target price must be positive"}, status_code=400)
    ok = WatchlistRepository(session).update_target_price(deal_id, target_price)
    if not ok:
        return JSONResponse({"error": "Item not found"}, status_code=404)
    item = WatchlistRepository(session).get_item(deal_id)
    sparklines = DealService(session).get_sparklines([item]) if item else {}
    return templates.TemplateResponse(
        request,
        "partials/watchlist_row.html",
        {"item": item, "sparklines": sparklines},
    )

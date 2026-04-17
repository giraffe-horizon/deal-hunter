"""Price-alert routes: view, add, remove, update target price.

Internally persisted in the ``watchlist`` SQLite table via
``WatchlistRepository``; user-facing URLs and labels use "alerts" to
distinguish from the bookmark-style Watchlist (offers with
``status='watching'``, served by ``routes/deals.py``).
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from deal_hunter.api import templates
from deal_hunter.api.dependencies import get_db
from deal_hunter.api.schemas import WatchlistAdd, WatchlistUpdate
from deal_hunter.api.view_services import DealService
from deal_hunter.storage.repositories import WatchlistRepository

router = APIRouter()


@router.get("/alerts", response_class=HTMLResponse)
def alerts_page(request: Request, session: Session = Depends(get_db)) -> HTMLResponse:
    """Price Alerts page — deals with target-price watches."""
    items = WatchlistRepository(session).get_all()
    sparklines = DealService(session).get_sparklines(items)
    return templates.TemplateResponse(
        request,
        "alerts.html",
        {"items": items, "sparklines": sparklines},
    )


@router.post("/api/alerts")
async def add_alert_api(
    request: Request,
    session: Session = Depends(get_db),
) -> HTMLResponse:
    """Add a deal to the price-alert list."""
    form = await request.form()
    try:
        validated = WatchlistAdd(
            deal_id=str(form.get("deal_id", "")),
            target_price=int(str(form.get("target_price", 0))),
        )
    except Exception:
        return HTMLResponse(
            '<span class="text-sm text-tertiary font-medium">\u2713 Target set</span>'
        )
    WatchlistRepository(session).add(validated.deal_id, validated.target_price)
    return HTMLResponse('<span class="text-sm text-tertiary font-medium">\u2713 Target set</span>')


@router.delete("/api/alerts/{deal_id:path}")
def remove_alert_api(
    deal_id: str,
    session: Session = Depends(get_db),
) -> HTMLResponse:
    """Remove a deal from the price-alert list."""
    WatchlistRepository(session).remove(deal_id)
    return HTMLResponse("")


@router.patch("/api/alerts/{deal_id:path}")
async def update_alert_api(
    request: Request,
    deal_id: str,
    target_price: int = Form(...),
    session: Session = Depends(get_db),
) -> Response:
    """Update target price for a price-alert item."""
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
        "partials/alert_row.html",
        {"item": item, "sparklines": sparklines},
    )

"""Watchlist routes: view, add, remove, update target price."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from dashboard import templates
from dashboard.dependencies import get_db
from dashboard.services import DealService
from storage.sqlite import SQLiteStorage

router = APIRouter()


@router.get("/watchlist", response_class=HTMLResponse)
def watchlist_page(request: Request, db: SQLiteStorage = Depends(get_db)):
    """Watchlist page — deals with target price alerts."""
    items = db.get_watchlist()
    sparklines = DealService(db).get_sparklines(items)
    return templates.TemplateResponse(
        request,
        "watchlist.html",
        {"items": items, "sparklines": sparklines},
    )


@router.post("/api/watchlist")
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


@router.delete("/api/watchlist/{deal_id:path}")
def remove_from_watchlist_api(
    deal_id: str,
    db: SQLiteStorage = Depends(get_db),
):
    """Remove a deal from the watchlist."""
    db.remove_from_watchlist(deal_id)
    return HTMLResponse("")


@router.patch("/api/watchlist/{deal_id:path}")
async def update_watchlist_api(
    request: Request,
    deal_id: str,
    target_price: int = Form(...),
    db: SQLiteStorage = Depends(get_db),
):
    """Update target price for a watchlist item."""
    if target_price <= 0:
        return JSONResponse({"error": "Target price must be positive"}, status_code=400)
    ok = db.update_watchlist_target_price(deal_id, target_price)
    if not ok:
        return JSONResponse({"error": "Item not found"}, status_code=404)
    item = db.get_watchlist_item(deal_id)
    sparklines = DealService(db).get_sparklines([item]) if item else {}
    return templates.TemplateResponse(
        request,
        "partials/watchlist_row.html",
        {"item": item, "sparklines": sparklines},
    )

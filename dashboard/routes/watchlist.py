"""Watchlist routes: view, add, remove."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from dashboard import templates
from dashboard.dependencies import get_db
from storage.sqlite import SQLiteStorage

router = APIRouter()


@router.get("/watchlist", response_class=HTMLResponse)
def watchlist_page(request: Request, db: SQLiteStorage = Depends(get_db)):
    """Watchlist page — deals with target price alerts."""
    items = db.get_watchlist()
    return templates.TemplateResponse(
        request,
        "watchlist.html",
        {"items": items},
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

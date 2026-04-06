"""Deal Hunter Web Dashboard — FastAPI application."""

from pathlib import Path
from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from storage.sqlite import SQLiteStorage

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "state" / "deals.db"

app = FastAPI(title="Deal Hunter Dashboard")
templates = Jinja2Templates(directory=str(BASE_DIR / "dashboard" / "templates"))


def format_pln(value: int) -> str:
    """Format integer price as PLN string: 8500 -> '8 500 zl'."""
    if not value:
        return "0 zl"
    formatted = f"{value:,}".replace(",", " ")
    return f"{formatted} zl"


templates.env.filters["format_pln"] = format_pln


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


@app.get("/")
def index():
    return RedirectResponse(url="/deals", status_code=302)


@app.get("/deals")
def deals_page(request: Request, db: SQLiteStorage = Depends(get_db)):
    return templates.TemplateResponse("deals.html", {
        "request": request,
        "active_page": "deals",
        "deals": [],
    })

"""Deal Hunter Web Dashboard — FastAPI application."""

import importlib.metadata
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

API_DIR = Path(__file__).parent  # src/deal_hunter/api/

try:
    APP_VERSION = importlib.metadata.version("deal-hunter")
except importlib.metadata.PackageNotFoundError:
    from deal_hunter import __version__

    APP_VERSION = __version__

app = FastAPI(title="Deal Hunter Dashboard", version=APP_VERSION)
app.mount("/static", StaticFiles(directory=str(API_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(API_DIR / "templates"))
templates.env.autoescape = True


def format_pln(value: int | None) -> str:
    """Format integer price as PLN string: 8500 -> '8 500 zl'."""
    if value is None or value == 0:
        return "0 zl"
    formatted = f"{value:,}".replace(",", " ")
    return f"{formatted} zl"


templates.env.filters["format_pln"] = format_pln
templates.env.globals["app_version"] = APP_VERSION


# CSRF middleware
@app.middleware("http")
async def csrf_check(request: Request, call_next):  # noqa: ANN001
    """Require HX-Request or X-Requested-With header on mutating requests."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        has_htmx = request.headers.get("HX-Request")
        has_xhr = request.headers.get("X-Requested-With")
        if not has_htmx and not has_xhr:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "CSRF check failed — missing HX-Request or X-Requested-With header"
                },
            )
    return await call_next(request)


# Re-export dependencies for backward compatibility (tests import from dashboard)
from deal_hunter.api.dependencies import get_db as get_db  # noqa: E402,F401
from deal_hunter.api.dependencies import get_profiles as _get_profiles  # noqa: E402,F401
from deal_hunter.api.dependencies import safe_load_profile as safe_load_profile  # noqa: E402
from deal_hunter.api.dependencies import safe_profile_path as safe_profile_path  # noqa: E402

# Import and include routers AFTER app and templates are defined
from deal_hunter.api.routes import deals, health, profiles, tuner, watchlist  # noqa: E402

app.include_router(deals.router)
app.include_router(profiles.router)
app.include_router(watchlist.router)
app.include_router(tuner.router)
app.include_router(health.router)


@app.get("/")
def index() -> RedirectResponse:
    return RedirectResponse(url="/deals", status_code=302)

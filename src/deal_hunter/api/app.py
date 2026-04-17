"""FastAPI application factory.

Use `create_app()` for tests and alternative deployments.  The package-level
default app is built once in `deal_hunter.api.__init__` via this factory.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

from deal_hunter.api.middleware import csrf_check
from deal_hunter.api.templating import API_DIR, APP_VERSION


def create_app() -> FastAPI:
    """Construct a fully-wired FastAPI app: static, middleware, routers, root redirect."""
    app = FastAPI(title="Deal Hunter Dashboard", version=APP_VERSION)

    # Static assets
    app.mount("/static", StaticFiles(directory=str(API_DIR / "static")), name="static")

    # Middleware
    app.middleware("http")(csrf_check)

    # Routers — imported locally to avoid eager import at package load time.
    from deal_hunter.api.routes import alerts, deals, health, profiles, tuner

    app.include_router(deals.router)
    app.include_router(profiles.router)
    app.include_router(alerts.router)
    app.include_router(tuner.router)
    app.include_router(health.router)

    @app.get("/")
    def index() -> RedirectResponse:
        return RedirectResponse(url="/deals", status_code=302)

    return app

"""Profile management routes: CRUD, toggle, run."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from dashboard import templates
from dashboard.dependencies import (
    _get_mgr,
    get_db,
    safe_load_profile,
    safe_profile_path,
)
from dashboard.schemas import ProfileCreate
from dashboard.services.profile_service import ProfileService

BASE_DIR = Path(__file__).parent.parent.parent

router = APIRouter()


def _get_profile_service() -> ProfileService:
    """Build a ProfileService from the current ProfileManager."""
    return ProfileService(_get_mgr())


@router.get("/profiles", response_class=HTMLResponse)
def profiles_page(request: Request) -> HTMLResponse:
    """Profile list page."""
    svc = _get_profile_service()
    profiles = svc.get_profile_summaries()
    return templates.TemplateResponse(
        request,
        "profiles.html",
        {"profiles": profiles},
    )


@router.get("/profiles/new", response_class=HTMLResponse)
def profile_create_page(request: Request) -> HTMLResponse:
    """Profile create page."""
    from sources import SOURCE_REGISTRY

    available_sources = sorted(SOURCE_REGISTRY.keys())
    return templates.TemplateResponse(
        request,
        "profile_create.html",
        {"available_sources": available_sources},
    )


@router.get("/profiles/{name}", response_class=HTMLResponse)
def profile_detail_page(
    request: Request, name: str, tab: str = "overview", session: Session = Depends(get_db)
) -> HTMLResponse:
    """Unified profile page with tabs."""
    safe_profile_path(name)
    profile = safe_load_profile(name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    profile.setdefault("emoji", "\U0001f50d")
    profile.setdefault("currency", "PLN")

    tab_map = {
        "overview": "partials/profile_tab_overview.html",
        "edit": "partials/profile_tab_edit.html",
        "yaml": "partials/profile_tab_yaml.html",
        "tuner": "partials/profile_tab_tuner.html",
    }
    tab = tab if tab in tab_map else "overview"

    context: dict = {"profile": profile, "active_tab": tab}

    # YAML tab needs raw content
    if tab == "yaml":
        profile_path = safe_profile_path(name)
        context["name"] = name
        context["yaml_content"] = profile_path.read_text(encoding="utf-8")

    # Tuner tab needs scored deals
    if tab == "tuner":
        from dashboard.services import DealService
        from storage.repositories import DealRepository

        deals = DealRepository(session).get_filtered(profile=name, limit=50)
        scored = DealService(session).score_deals_with_profile(deals, profile)
        context["deals"] = scored
        context["profile_data"] = profile
        context["selected_profile"] = name

    # HTMX request: return only the tab partial
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, tab_map[tab], context)

    # Full page load: render the unified shell with the tab included
    context["active_tab_template"] = tab_map[tab]
    return templates.TemplateResponse(request, "profile_unified.html", context)


@router.get("/profiles/{name}/edit", response_class=HTMLResponse)
def profile_edit_redirect(name: str) -> RedirectResponse:
    """Redirect old edit URL to unified profile page edit tab."""
    return RedirectResponse(f"/profiles/{name}?tab=edit", status_code=302)


@router.get("/profiles/{name}/edit/yaml", response_class=HTMLResponse)
def profile_yaml_redirect(name: str) -> RedirectResponse:
    """Redirect old YAML editor URL to unified profile page yaml tab."""
    return RedirectResponse(f"/profiles/{name}?tab=yaml", status_code=302)


@router.put("/api/profiles/{name}/yaml")
async def api_update_profile_yaml(request: Request, name: str) -> JSONResponse:
    """Update a profile from raw YAML text."""
    profile_path = safe_profile_path(name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")

    body = await request.body()
    yaml_text = body.decode("utf-8")

    svc = _get_profile_service()
    errors = svc.save_yaml_text(profile_path, yaml_text)
    if errors:
        return JSONResponse({"errors": errors})

    return JSONResponse({"ok": True})


@router.post("/api/profiles")
async def api_create_profile(request: Request) -> JSONResponse:
    """Create a new profile."""
    body = await request.json()

    try:
        validated = ProfileCreate.model_validate(body)
    except Exception as e:
        return JSONResponse({"errors": [str(e)]})

    profile_path = safe_profile_path(validated.name)
    if profile_path.exists():
        return JSONResponse({"errors": [f"Profile '{validated.name}' already exists."]})

    profile_path.parent.mkdir(parents=True, exist_ok=True)

    svc = _get_profile_service()
    errors = svc.save_profile_dict(profile_path, body)
    if errors:
        return JSONResponse({"errors": errors})

    return JSONResponse({"ok": True})


@router.put("/api/profiles/{name}")
async def api_update_profile(request: Request, name: str) -> JSONResponse:
    """Update a profile from form data (JSON body)."""
    safe_profile_path(name)
    body = await request.json()

    existing = safe_load_profile(name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")

    # Preserve sources from existing profile if not in body
    if "sources" not in body or not body["sources"]:
        body["sources"] = existing.get("sources", {})

    # Preserve fields not in the form
    for key in ("custom_filter", "custom_data", "price_tracking", "quiet_hours", "dedup"):
        if key in existing and key not in body:
            body[key] = existing[key]

    svc = _get_profile_service()
    profile_path = safe_profile_path(name)
    errors = svc.save_profile_dict(profile_path, body)
    if errors:
        return JSONResponse({"errors": errors})

    return JSONResponse({"ok": True})


@router.delete("/api/profiles/{name}")
def api_delete_profile(name: str) -> JSONResponse:
    """Delete a profile YAML file."""
    profile_path = safe_profile_path(name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    profile_path.unlink()
    return JSONResponse({"ok": True})


@router.patch("/api/profiles/{name}/toggle")
def api_toggle_profile(name: str) -> JSONResponse:
    """Toggle a profile's enabled state."""
    profile_path = safe_profile_path(name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")

    svc = _get_profile_service()
    new_enabled = svc.toggle_enabled(profile_path)

    return JSONResponse({"ok": True, "enabled": new_enabled})


@router.post("/api/profiles/{name}/run")
def api_run_profile(name: str) -> HTMLResponse:
    """Trigger a profile run (dry-run with --verify)."""
    profile_path = safe_profile_path(name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")

    svc = _get_profile_service()
    safe_output = svc.run_verify(name)

    pre_cls = (
        "text-xs text-on-surface-variant whitespace-pre-wrap"
        " overflow-x-auto bg-surface-container rounded-lg p-4"
    )
    return HTMLResponse(
        f'<div class="bg-surface-container-low rounded-card p-6 mt-4">'
        f'<h3 class="font-headline text-base font-semibold text-on-surface mb-3">'
        f"Run Output</h3>"
        f'<pre class="{pre_cls}">{safe_output}</pre>'
        f"</div>"
    )


@router.get("/api/profiles")
def api_profiles_list() -> JSONResponse:
    """JSON list of profiles."""
    svc = _get_profile_service()
    profiles = svc.get_profile_summaries()
    return JSONResponse(profiles)

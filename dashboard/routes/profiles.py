"""Profile management routes: CRUD, toggle, run."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from dashboard import templates
from dashboard.dependencies import (
    _PROFILE_NAME_RE,
    get_db,
    get_profiles,
    safe_load_profile,
    safe_profile_path,
)

BASE_DIR = Path(__file__).parent.parent.parent

router = APIRouter()


@router.get("/profiles", response_class=HTMLResponse)
def profiles_page(request: Request):
    """Profile list page."""
    profile_names = get_profiles()
    profiles = []
    for name in profile_names:
        prof = safe_load_profile(name)
        if prof:
            profiles.append(
                {
                    "name": name,
                    "emoji": prof.get("emoji", "\U0001f50d"),
                    "enabled": prof.get("enabled", True),
                    "source_count": len(prof.get("sources", {})),
                    "budget_min": prof.get("budget", {}).get("min", 0),
                    "budget_max": prof.get("budget", {}).get("max", 0),
                    "score_threshold": prof.get("score_threshold", 0),
                }
            )
    return templates.TemplateResponse(
        request,
        "profiles.html",
        {"profiles": profiles},
    )


@router.get("/profiles/new", response_class=HTMLResponse)
def profile_create_page(request: Request):
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
):
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
def profile_edit_redirect(name: str):
    """Redirect old edit URL to unified profile page edit tab."""
    return RedirectResponse(f"/profiles/{name}?tab=edit", status_code=302)


@router.get("/profiles/{name}/edit/yaml", response_class=HTMLResponse)
def profile_yaml_redirect(name: str):
    """Redirect old YAML editor URL to unified profile page yaml tab."""
    return RedirectResponse(f"/profiles/{name}?tab=yaml", status_code=302)


@router.put("/api/profiles/{name}/yaml")
async def api_update_profile_yaml(request: Request, name: str):
    """Update a profile from raw YAML text."""
    import yaml as _yaml

    from utils.validation import validate_profile as _validate

    profile_path = safe_profile_path(name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")

    body = await request.body()
    yaml_text = body.decode("utf-8")

    try:
        profile = _yaml.safe_load(yaml_text)
    except _yaml.YAMLError as e:
        return JSONResponse({"errors": [f"YAML parse error: {e}"]})

    if not isinstance(profile, dict):
        return JSONResponse({"errors": ["YAML must be a mapping (dict)"]})

    errors = _validate(profile)
    if errors:
        return JSONResponse({"errors": errors})

    with profile_path.open("w", encoding="utf-8") as f:
        f.write(yaml_text)

    return JSONResponse({"ok": True})


@router.post("/api/profiles")
async def api_create_profile(request: Request):
    """Create a new profile."""
    import yaml as _yaml

    from utils.validation import validate_profile as _validate

    body = await request.json()
    name = body.get("name", "")

    if not name or not _PROFILE_NAME_RE.match(name):
        return JSONResponse(
            {
                "errors": [
                    "Invalid profile name. Use lowercase letters, numbers, hyphens, underscores."
                ]
            }
        )

    profile_path = safe_profile_path(name)
    if profile_path.exists():
        return JSONResponse({"errors": [f"Profile '{name}' already exists."]})

    errors = _validate(body)
    if errors:
        return JSONResponse({"errors": errors})

    profile_path.parent.mkdir(parents=True, exist_ok=True)

    with profile_path.open("w", encoding="utf-8") as f:
        _yaml.dump(body, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return JSONResponse({"ok": True})


@router.put("/api/profiles/{name}")
async def api_update_profile(request: Request, name: str):
    """Update a profile from form data (JSON body)."""
    import yaml as _yaml

    from utils.validation import validate_profile as _validate

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

    errors = _validate(body)
    if errors:
        return JSONResponse({"errors": errors})

    profile_path = safe_profile_path(name)
    with profile_path.open("w", encoding="utf-8") as f:
        _yaml.dump(body, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return JSONResponse({"ok": True})


@router.delete("/api/profiles/{name}")
def api_delete_profile(name: str):
    """Delete a profile YAML file."""
    profile_path = safe_profile_path(name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    profile_path.unlink()
    return JSONResponse({"ok": True})


@router.patch("/api/profiles/{name}/toggle")
def api_toggle_profile(name: str):
    """Toggle a profile's enabled state."""
    import yaml as _yaml

    profile_path = safe_profile_path(name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")

    with profile_path.open(encoding="utf-8") as f:
        profile = _yaml.safe_load(f)

    profile["enabled"] = not profile.get("enabled", True)

    with profile_path.open("w", encoding="utf-8") as f:
        _yaml.dump(profile, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return JSONResponse({"ok": True, "enabled": profile["enabled"]})


@router.post("/api/profiles/{name}/run")
def api_run_profile(name: str):
    """Trigger a profile run (dry-run with --verify)."""
    import html as _html
    import subprocess

    profile_path = safe_profile_path(name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")

    try:
        result = subprocess.run(  # noqa: S603, S607
            ["python", "deal_hunter.py", "--profile", name, "--verify"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(BASE_DIR),
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        output = "Run timed out after 120 seconds."
    except Exception as e:
        output = f"Error: {e}"

    safe_output = _html.escape(output)
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
def api_profiles_list():
    """JSON list of profiles."""
    profile_names = get_profiles()
    profiles = []
    for name in profile_names:
        prof = safe_load_profile(name)
        if prof:
            profiles.append(
                {
                    "name": name,
                    "emoji": prof.get("emoji", "\U0001f50d"),
                    "enabled": prof.get("enabled", True),
                    "source_count": len(prof.get("sources", {})),
                }
            )
    return JSONResponse(profiles)

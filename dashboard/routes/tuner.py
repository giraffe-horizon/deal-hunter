"""Scoring Tuner routes: index, profile view (redirect), simulate, save."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from dashboard import templates
from dashboard.dependencies import get_db, get_profiles, safe_load_profile, safe_profile_path
from dashboard.services import TunerService

router = APIRouter()


@router.get("/tuner", response_class=HTMLResponse)
def tuner_index(request: Request) -> HTMLResponse:
    """Scoring Tuner index — profile selector."""
    profiles = get_profiles()
    return templates.TemplateResponse(
        request,
        "tuner.html",
        {
            "active_page": "tuner",
            "profiles": profiles,
            "selected_profile": None,
            "deals": [],
            "profile_data": None,
        },
    )


@router.get("/tuner/{profile}", response_class=HTMLResponse)
def tuner_profile(request: Request, profile: str) -> RedirectResponse:
    """Redirect to unified profile page tuner tab."""
    return RedirectResponse(f"/profiles/{profile}?tab=tuner", status_code=302)


@router.post("/api/tuner/{profile}/simulate")
async def tuner_simulate(
    request: Request, profile: str, session: Session = Depends(get_db)
) -> JSONResponse:
    """Re-score deals with modified rules and return JSON results."""
    safe_profile_path(profile)
    profile_data = safe_load_profile(profile)
    if profile_data is None:
        return JSONResponse({"error": "Profile not found"}, status_code=404)
    body = await request.json()
    results = TunerService(session).simulate(profile, profile_data, body)
    return JSONResponse({"results": results})


@router.post("/api/tuner/{profile}/save")
async def tuner_save(request: Request, profile: str) -> JSONResponse:
    """Save modified scoring rules to the profile YAML file."""
    profile_path = safe_profile_path(profile)
    profile_data = safe_load_profile(profile)
    if profile_data is None:
        return JSONResponse({"error": "Profile not found"}, status_code=404)
    body = await request.json()
    errors = TunerService.save_rules(profile_path, profile_data, body)
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=400)
    return JSONResponse({"ok": True})

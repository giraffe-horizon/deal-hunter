"""Scoring Tuner routes: index, profile view, simulate, save."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from dashboard import templates
from dashboard.dependencies import get_db, get_profiles, safe_load_profile, safe_profile_path
from dashboard.services import DealService
from storage.sqlite import SQLiteStorage

router = APIRouter()


@router.get("/tuner", response_class=HTMLResponse)
def tuner_index(request: Request):
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
def tuner_profile(request: Request, profile: str, db: SQLiteStorage = Depends(get_db)):
    """Scoring Tuner for a specific profile — loads and scores 50 deals."""
    safe_profile_path(profile)
    profile_data = safe_load_profile(profile)
    if profile_data is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Profile not found")
    deals = db.get_deals(profile=profile, limit=50)
    scored = DealService(db).score_deals_with_profile(deals, profile_data)
    return templates.TemplateResponse(
        request,
        "tuner.html",
        {
            "active_page": "tuner",
            "profiles": get_profiles(),
            "selected_profile": profile,
            "deals": scored,
            "profile_data": profile_data,
        },
    )


@router.post("/api/tuner/{profile}/simulate")
async def tuner_simulate(request: Request, profile: str, db: SQLiteStorage = Depends(get_db)):
    """Re-score deals with modified rules and return JSON results."""
    safe_profile_path(profile)
    body = await request.json()
    profile_data = safe_load_profile(profile)
    if profile_data is None:
        return JSONResponse({"error": "Profile not found"}, status_code=404)
    modified = dict(profile_data)
    for key in (
        "score_rules",
        "penalties",
        "budget",
        "score_threshold",
        "score_threshold_alert",
        "excluded_words",
        "required_any",
    ):
        if key in body:
            modified[key] = body[key]
    deals = db.get_deals(profile=profile, limit=50)
    scored = DealService(db).score_deals_with_profile(deals, modified)
    results = []
    for s in scored:
        results.append(
            {
                "id": s["id"],
                "title": s["title"],
                "price": s["price"],
                "current_score": s["score"],
                "new_score": s["new_score"],
                "diff": s["diff"],
                "rejected": s["rejected"],
                "reject_reason": s["reject_reason"],
                "breakdown": s["breakdown"],
            }
        )
    return JSONResponse({"results": results})


@router.post("/api/tuner/{profile}/save")
async def tuner_save(request: Request, profile: str):
    """Save modified scoring rules to the profile YAML file."""
    profile_path = safe_profile_path(profile)
    body = await request.json()
    profile_data = safe_load_profile(profile)
    if profile_data is None:
        return JSONResponse({"error": "Profile not found"}, status_code=404)
    for key in (
        "score_rules",
        "penalties",
        "budget",
        "score_threshold",
        "score_threshold_alert",
        "excluded_words",
        "required_any",
    ):
        if key in body:
            profile_data[key] = body[key]
    from utils.validation import validate_profile

    errors = validate_profile(profile_data)
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=400)
    import yaml as _yaml_save

    profile_path.write_text(
        _yaml_save.dump(
            profile_data, allow_unicode=True, default_flow_style=False, sort_keys=False
        ),
        encoding="utf-8",
    )
    return JSONResponse({"ok": True})

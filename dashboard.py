"""Deal Hunter Web Dashboard — FastAPI application."""

import importlib.metadata
import math
import re
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from storage.sqlite import SQLiteStorage

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "state" / "deals.db"

DEALS_PER_PAGE = 50
SCORE_THRESHOLD = 70

try:
    APP_VERSION = importlib.metadata.version("deal-hunter")
except importlib.metadata.PackageNotFoundError:
    from deal_hunter import __version__

    APP_VERSION = __version__

app = FastAPI(title="Deal Hunter Dashboard", version=APP_VERSION)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "dashboard" / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "dashboard" / "templates"))
templates.env.autoescape = True


@app.middleware("http")
async def csrf_check(request: Request, call_next):
    """Require HX-Request or X-Requested-With header on mutating requests."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        has_htmx = request.headers.get("HX-Request")
        has_xhr = request.headers.get("X-Requested-With")
        if not has_htmx and not has_xhr:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF check failed — missing HX-Request or X-Requested-With header"},
            )
    return await call_next(request)


def format_pln(value: int | None) -> str:
    """Format integer price as PLN string: 8500 -> '8 500 zl'."""
    if value is None or value == 0:
        return "0 zl"
    formatted = f"{value:,}".replace(",", " ")
    return f"{formatted} zl"


templates.env.filters["format_pln"] = format_pln
templates.env.globals["app_version"] = APP_VERSION


def get_db():
    """FastAPI dependency: yields SQLiteStorage instance, closes after request."""
    db = SQLiteStorage(DB_PATH)
    try:
        yield db
    finally:
        db.close()


_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
PROFILES_DIR = BASE_DIR / "profiles"


def safe_profile_path(name: str) -> Path:
    """Validate profile name and return resolved path, or raise 400."""
    if not _PROFILE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid profile name")
    path = (PROFILES_DIR / f"{name}.yaml").resolve()
    if not path.is_relative_to(PROFILES_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid profile name")
    return path


def safe_load_profile(name: str) -> dict | None:
    """Load profile without sys.exit on missing files."""
    try:
        from deal_hunter import load_profile

        return load_profile(name)
    except SystemExit:
        return None


def _get_profiles() -> list[str]:
    """Get available profile names, gracefully handling missing profiles dir."""
    try:
        from deal_hunter import list_profiles

        return sorted(list_profiles())
    except Exception:
        return []


@app.get("/")
def index():
    return RedirectResponse(url="/deals", status_code=302)


@app.get("/deals")
def deals_page(
    request: Request,
    profile: str | None = None,
    source: str | None = None,
    min_score: int | None = None,
    category: str | None = None,
    status: str | None = None,
    page: int = 1,
    db: SQLiteStorage = Depends(get_db),
):
    # Normalize empty string params to None
    profile = profile or None
    source = source or None
    category = category or None
    status = status or None
    page = max(1, page)

    offset = (page - 1) * DEALS_PER_PAGE
    deals = db.get_deals(
        profile=profile,
        source=source,
        min_score=min_score,
        category=category,
        status=status,
        limit=DEALS_PER_PAGE,
        offset=offset,
    )
    total_filtered = db.count_deals(
        profile=profile,
        source=source,
        min_score=min_score,
        category=category,
        status=status,
    )
    total_pages = max(1, math.ceil(total_filtered / DEALS_PER_PAGE))

    # Build filter query string for pagination links
    filter_params = ""
    if profile:
        filter_params += f"&profile={profile}"
    if source:
        filter_params += f"&source={source}"
    if min_score is not None:
        filter_params += f"&min_score={min_score}"
    if category:
        filter_params += f"&category={category}"
    if status:
        filter_params += f"&status={status}"

    # HTMX partial refresh — return only the table fragment
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "partials/deals_table.html",
            {
                "deals": deals,
                "page": page,
                "total_pages": total_pages,
                "total_filtered": total_filtered,
                "filter_params": filter_params,
            },
        )

    # Compute metrics via SQL aggregates (no full table scan)
    stats = db.get_deal_stats(score_threshold=SCORE_THRESHOLD)
    total_deals = stats["total"]
    high_score_pct = round(stats["high_score"] / total_deals * 100) if total_deals else 0
    new_today = stats["new_today"]
    drops_count = len(db.get_price_drops(days=7))

    # Filter dropdown options via SQL
    filter_opts = db.get_filter_options()
    profiles = _get_profiles()

    return templates.TemplateResponse(
        request,
        "deals.html",
        {
            "deals": deals,
            "total_deals": total_deals,
            "high_score_pct": high_score_pct,
            "score_threshold": SCORE_THRESHOLD,
            "new_today": new_today,
            "drops_count": drops_count,
            "profiles": profiles,
            "sources": filter_opts["sources"],
            "categories": filter_opts["categories"],
            "selected_profile": profile,
            "selected_source": source,
            "selected_min_score": min_score,
            "selected_category": category,
            "selected_status": status,
            "page": page,
            "total_pages": total_pages,
            "total_filtered": total_filtered,
            "filter_params": filter_params,
        },
    )


@app.get("/health")
def health_page(request: Request):
    from health import load_health

    health = load_health()

    # Compute summary metrics from health data
    total_deals = 0
    total_alerts = 0
    errors = []
    if health and "profile_results" in health:
        for name, result in health["profile_results"].items():
            total_deals += result.get("deals_found", 0)
            total_alerts += result.get("new_alerts", 0)
            for err in result.get("errors", []):
                errors.append({"profile": name, "message": err})

    return templates.TemplateResponse(
        request,
        "health.html",
        {
            "health": health,
            "total_deals": total_deals,
            "total_alerts": total_alerts,
            "errors": errors,
        },
    )


@app.get("/price-trends")
def price_trends_page(
    request: Request,
    days: int = 7,
    db: SQLiteStorage = Depends(get_db),
):
    drops = db.get_price_drops(days=days)
    all_deals = db.get_deals()

    # Compute summary metrics
    total_drops = len(drops)
    avg_drop_pct = (
        round(sum(d["diff_percent"] for d in drops) / total_drops, 1) if total_drops else 0
    )
    biggest_drop = max((d["diff_pln"] for d in drops), default=0)

    # Category distribution from all deals
    categories: dict[str, int] = {}
    for deal in all_deals:
        cat = deal.get("category") or "Uncategorized"
        categories[cat] = categories.get(cat, 0) + 1
    categories = dict(sorted(categories.items(), key=lambda x: x[1], reverse=True))

    # Sparkline data for top 3 categories
    category_trends: dict[str, list[dict]] = {}
    for cat_name in list(categories.keys())[:3]:
        trend = db.get_category_price_trend(cat_name, days=30)
        if trend:
            category_trends[cat_name] = trend

    return templates.TemplateResponse(
        request,
        "price_trends.html",
        {
            "drops": drops,
            "days": days,
            "total_drops": total_drops,
            "avg_drop_pct": avg_drop_pct,
            "biggest_drop": biggest_drop,
            "categories": categories,
            "category_trends": category_trends,
        },
    )


@app.get("/deals/{deal_id}")
def deal_detail_page(
    request: Request,
    deal_id: str,
    db: SQLiteStorage = Depends(get_db),
):
    deal = db.get_deal(deal_id)
    if not deal:
        return HTMLResponse(content="Deal not found", status_code=404)

    price_history = db.get_price_history(deal_id)
    lowest_price = db.get_lowest_price(deal_id)
    previous_price = db.get_previous_price(deal_id)

    return templates.TemplateResponse(
        request,
        "deal_detail.html",
        {
            "deal": deal,
            "price_history": price_history,
            "lowest_price": lowest_price,
            "previous_price": previous_price,
        },
    )


@app.get("/compare", response_class=HTMLResponse)
async def compare_deals(request: Request, ids: str = "", db: SQLiteStorage = Depends(get_db)):
    deal_ids = [i.strip() for i in ids.split(",") if i.strip()] if ids else []
    deal_ids = deal_ids[:5]  # max 5
    deals = db.get_deals_by_ids(deal_ids) if deal_ids else []
    price_histories = {}
    lowest_prices = {}
    for deal in deals:
        price_histories[deal["id"]] = db.get_price_history(deal["id"])
        lowest_prices[deal["id"]] = db.get_lowest_price(deal["id"])
    return templates.TemplateResponse(
        request,
        "compare.html",
        {
            "active_page": "deals",
            "deals": deals,
            "price_histories": price_histories,
            "lowest_prices": lowest_prices,
        },
    )


@app.get("/api/price-history/{deal_id}")
def api_price_history(deal_id: str, db: SQLiteStorage = Depends(get_db)):
    history = db.get_price_history(deal_id)
    if not history:
        return {"labels": [], "prices": [], "lowest": None, "highest": None}

    labels = [h["recorded_at"][:10] for h in history]  # YYYY-MM-DD
    prices = [h["price"] for h in history]

    return {
        "labels": labels,
        "prices": prices,
        "lowest": min(prices),
        "highest": max(prices),
    }


@app.post("/api/deals/{deal_id}/status")
def api_update_deal_status(
    request: Request,
    deal_id: str,
    status: str = Form(...),
    db: SQLiteStorage = Depends(get_db),
):
    if status not in ("watching", "rejected", "active"):
        return JSONResponse({"error": "Invalid status"}, status_code=400)
    ok = db.update_deal_status(deal_id, status)
    if not ok:
        return JSONResponse({"error": "Deal not found"}, status_code=404)
    # Return HTML fragment for HTMX swap — must include full action buttons
    # so the user can change status again
    deal = db.get_deal(deal_id)
    link = deal["link"] if deal else "#"
    encoded_id = deal_id.replace(":", "%3A")

    return templates.TemplateResponse(
        request,
        "partials/deal_action_buttons.html",
        {
            "deal_link": link,
            "deal_id_encoded": encoded_id,
            "current_status": status,
        },
    )


@app.get("/api/deals")
def api_deals(
    profile: str | None = None,
    source: str | None = None,
    min_score: int | None = None,
    category: str | None = None,
    status: str | None = None,
    db: SQLiteStorage = Depends(get_db),
):
    return db.get_deals(
        profile=profile or None,
        source=source or None,
        min_score=min_score,
        category=category or None,
        status=status or None,
    )


@app.get("/api/stats")
def api_stats(db: SQLiteStorage = Depends(get_db)):
    stats = db.get_deal_stats(score_threshold=SCORE_THRESHOLD)
    total = stats["total"]
    drops = db.get_price_drops(days=7)
    return {
        "total_deals": total,
        "high_score_pct": round(stats["high_score"] / total * 100) if total else 0,
        "new_today": stats["new_today"],
        "drops_count": len(drops),
    }


@app.get("/watchlist", response_class=HTMLResponse)
async def watchlist_page(request: Request, db: SQLiteStorage = Depends(get_db)):
    """Watchlist page — deals with target price alerts."""
    items = db.get_watchlist()
    return templates.TemplateResponse(
        request,
        "watchlist.html",
        {"items": items},
    )


@app.post("/api/watchlist")
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


@app.delete("/api/watchlist/{deal_id:path}")
async def remove_from_watchlist_api(
    deal_id: str,
    db: SQLiteStorage = Depends(get_db),
):
    """Remove a deal from the watchlist."""
    db.remove_from_watchlist(deal_id)
    return HTMLResponse("")


@app.get("/profiles", response_class=HTMLResponse)
async def profiles_page(request: Request):
    """Profile list page."""
    profile_names = _get_profiles()
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


@app.get("/profiles/{name}/edit/yaml", response_class=HTMLResponse)
async def profile_yaml_page(request: Request, name: str):
    """Raw YAML editor page."""
    profile_path = safe_profile_path(name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    yaml_content = profile_path.read_text(encoding="utf-8")
    return templates.TemplateResponse(
        request,
        "profile_yaml.html",
        {"name": name, "yaml_content": yaml_content},
    )


@app.put("/api/profiles/{name}/yaml")
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

    with open(profile_path, "w", encoding="utf-8") as f:
        f.write(yaml_text)

    return JSONResponse({"ok": True})


@app.get("/profiles/new", response_class=HTMLResponse)
async def profile_create_page(request: Request):
    """Profile create page."""
    from sources import SOURCE_REGISTRY

    available_sources = sorted(SOURCE_REGISTRY.keys())
    return templates.TemplateResponse(
        request,
        "profile_create.html",
        {"available_sources": available_sources},
    )


@app.post("/api/profiles")
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

    with open(profile_path, "w", encoding="utf-8") as f:
        _yaml.dump(body, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return JSONResponse({"ok": True})


@app.get("/profiles/{name}", response_class=HTMLResponse)
async def profile_detail_page(request: Request, name: str):
    """Profile detail page (read-only view)."""
    safe_profile_path(name)
    profile = safe_load_profile(name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    profile.setdefault("emoji", "\U0001f50d")
    profile.setdefault("currency", "PLN")
    return templates.TemplateResponse(
        request,
        "profile_detail.html",
        {"profile": profile},
    )


@app.get("/profiles/{name}/edit", response_class=HTMLResponse)
async def profile_edit_page(request: Request, name: str):
    """Profile form editor page."""
    safe_profile_path(name)
    profile = safe_load_profile(name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    profile.setdefault("emoji", "\U0001f50d")
    profile.setdefault("currency", "PLN")
    return templates.TemplateResponse(
        request,
        "profile_edit.html",
        {"profile": profile},
    )


@app.put("/api/profiles/{name}")
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
    with open(profile_path, "w", encoding="utf-8") as f:
        _yaml.dump(body, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return JSONResponse({"ok": True})


@app.delete("/api/profiles/{name}")
async def api_delete_profile(name: str):
    """Delete a profile YAML file."""
    profile_path = safe_profile_path(name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    profile_path.unlink()
    return JSONResponse({"ok": True})


@app.patch("/api/profiles/{name}/toggle")
async def api_toggle_profile(name: str):
    """Toggle a profile's enabled state."""
    import yaml as _yaml

    profile_path = safe_profile_path(name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")

    with open(profile_path, encoding="utf-8") as f:
        profile = _yaml.safe_load(f)

    profile["enabled"] = not profile.get("enabled", True)

    with open(profile_path, "w", encoding="utf-8") as f:
        _yaml.dump(profile, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return JSONResponse({"ok": True, "enabled": profile["enabled"]})


@app.post("/api/profiles/{name}/run")
async def api_run_profile(name: str):
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
    return HTMLResponse(
        f'<div class="bg-surface-container-low rounded-card p-6 mt-4">'
        f'<h3 class="font-headline text-base font-semibold text-on-surface mb-3">Run Output</h3>'
        f'<pre class="text-xs text-on-surface-variant whitespace-pre-wrap overflow-x-auto bg-surface-container rounded-lg p-4">{safe_output}</pre>'
        f"</div>"
    )


def _score_deals_with_profile(deals: list[dict], profile_data: dict) -> list[dict]:
    """Score a list of deal dicts using the given profile config. Returns enriched dicts."""
    from filters.base import BaseFilter
    from sources.base import Deal

    scorer = BaseFilter(profile_data)
    scored = []
    for d in deals:
        deal_obj = Deal(
            id=d["id"],
            title=d["title"],
            price=d["price"] or 0,
            link=d["link"] or "",
            source=d["source"] or "",
            description=d["description"] or "",
            temperature=0,
            image_url=d["image_url"] or "",
            published_at="",
        )
        result = scorer.score_deal(deal_obj)
        scored.append(
            {
                **d,
                "new_score": result.score,
                "diff": result.score - (d["score"] or 0),
                "breakdown": result.breakdown,
                "rejected": result.rejected,
                "reject_reason": result.reject_reason,
            }
        )
    scored.sort(key=lambda x: x["new_score"], reverse=True)
    return scored


@app.get("/tuner", response_class=HTMLResponse)
async def tuner_index(request: Request):
    """Scoring Tuner index — profile selector."""
    profiles = _get_profiles()
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


@app.get("/tuner/{profile}", response_class=HTMLResponse)
async def tuner_profile(request: Request, profile: str, db: SQLiteStorage = Depends(get_db)):
    """Scoring Tuner for a specific profile — loads and scores 50 deals."""
    safe_profile_path(profile)
    profile_data = safe_load_profile(profile)
    if profile_data is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    deals = db.get_deals(profile=profile, limit=50)
    scored = _score_deals_with_profile(deals, profile_data)
    return templates.TemplateResponse(
        request,
        "tuner.html",
        {
            "active_page": "tuner",
            "profiles": _get_profiles(),
            "selected_profile": profile,
            "deals": scored,
            "profile_data": profile_data,
        },
    )


@app.post("/api/tuner/{profile}/simulate")
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
    scored = _score_deals_with_profile(deals, modified)
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


@app.post("/api/tuner/{profile}/save")
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


@app.get("/api/profiles")
async def api_profiles_list():
    """JSON list of profiles."""
    profile_names = _get_profiles()
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

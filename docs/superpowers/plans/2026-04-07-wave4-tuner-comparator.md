# Wave 4: Scoring Tuner (A.1) + Deal Comparator (C.2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Live scoring rule editor with in-memory simulation ("what-if" for rules), and side-by-side deal comparison view. These are the final two features of Roadmap v2.

**Architecture:** Extends `dashboard.py` with ~6 new routes. Two new templates (tuner, compare). Tuner re-uses `BaseFilter.score_deal()` with a temporary profile dict for simulation. Comparator fetches deals by ID list and renders side-by-side with inline Chart.js sparklines.

**Tech Stack:** Python 3.12+, FastAPI, Jinja2/HTMX, Chart.js (CDN), pytest

**Security notes:** All templates use Jinja2 auto-escaping. JavaScript error display uses `textContent` (no innerHTML). Tuner simulation is read-only against SQLite — no state changes during simulate.

---

## File Structure

- Modify: `dashboard.py` — ~6 new routes for tuner + comparator
- Modify: `dashboard/templates/base.html` — add Scoring Tuner to sidebar nav
- Create: `dashboard/templates/tuner.html` — scoring rule editor + simulation results
- Create: `dashboard/templates/compare.html` — side-by-side deal comparison
- Modify: `dashboard/templates/partials/deals_table.html` — add checkboxes for comparison selection
- Modify: `storage/sqlite.py` — add `get_deals_by_ids()` method
- Modify: `tests/test_dashboard.py` — tuner + comparator tests

---

## Task 1: SQLite `get_deals_by_ids()` + Compare Route + Template

Add a method to fetch multiple deals by ID list, create the compare route and template.

**Files:**
- Modify: `storage/sqlite.py` — add `get_deals_by_ids(ids: list[str]) -> list[dict]`
- Modify: `dashboard.py` — add `GET /compare` route
- Create: `dashboard/templates/compare.html` — side-by-side comparison view
- Test: `tests/test_sqlite_storage.py` — test `get_deals_by_ids`
- Test: `tests/test_dashboard.py` — add TestComparePage class

**SQLite method** (add in `storage/sqlite.py` after `get_deals()`):
```python
def get_deals_by_ids(self, ids: list[str]) -> list[dict]:
    """Fetch multiple deals by their IDs."""
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    query = f"SELECT * FROM deals WHERE id IN ({placeholders})"
    rows = self.conn.execute(query, ids).fetchall()
    return [dict(row) for row in rows]
```

**Route** (add in `dashboard.py`):
```python
@app.get("/compare", response_class=HTMLResponse)
async def compare_deals(request: Request, ids: str = "", db: SQLiteStorage = Depends(get_db)):
    deal_ids = [i.strip() for i in ids.split(",") if i.strip()] if ids else []
    deals = db.get_deals_by_ids(deal_ids) if deal_ids else []
    # Fetch price history for each deal
    price_histories = {}
    for deal in deals:
        history = db.get_price_history(deal["id"])
        price_histories[deal["id"]] = history
    lowest_prices = {}
    for deal in deals:
        lowest_prices[deal["id"]] = db.get_lowest_price(deal["id"])
    return templates.TemplateResponse(request, "compare.html", {
        "active_page": "deals",
        "deals": deals,
        "price_histories": price_histories,
        "lowest_prices": lowest_prices,
    })
```

**Template** (`compare.html`): Side-by-side cards. Each card shows: title, price (highlight best in green), score (highlight highest in gold), source, profile, first_seen, lowest_price, mini sparkline via Chart.js. Share link shown at top. Empty state if no IDs. Max 5 deals enforced in route.

The template should follow the existing Material Design 3 style:
- `{% extends "base.html" %}`, `{% set active_page = "deals" %}`
- Cards use `bg-surface-container-low rounded-card p-6`
- Price uses `font-headline font-bold text-primary`
- Score color-coding: `text-tertiary` (>=70), `text-[#b8860b]` (>=40), `text-error` (<40)
- Each card gets a `<canvas>` for sparkline, rendered via a shared JS function
- Best price highlighted with `bg-tertiary-container/20` background
- Highest score highlighted with `bg-primary-container/20` background

**Sparkline JS pattern** (inside `<script>` block):
```javascript
const histories = {{ price_histories | tojson }};
document.querySelectorAll('[data-sparkline]').forEach(el => {
    const dealId = el.dataset.sparkline;
    const history = histories[dealId] || [];
    if (!history.length) return;
    const prices = history.map(h => h.price);
    new Chart(el, {
        type: 'line',
        data: {
            labels: history.map(h => h.recorded_at.slice(0, 10)),
            datasets: [{
                data: prices,
                borderColor: '#005db5',
                borderWidth: 1.5,
                pointRadius: 0,
                tension: 0.3,
                fill: false,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: { x: { display: false }, y: { display: false } },
        }
    });
});
```

**Tests:**
- `test_get_deals_by_ids_empty` — empty list returns empty
- `test_get_deals_by_ids_found` — returns matching deals
- `test_get_deals_by_ids_partial` — only returns deals that exist
- `test_compare_page_loads` — GET /compare returns 200
- `test_compare_page_with_ids` — GET /compare?ids=x,y returns 200 with deal data

---

## Task 2: Deals Table Checkboxes + Compare Button

Add checkboxes to the deals table for selecting deals to compare, with a floating "Compare" bar.

**Files:**
- Modify: `dashboard/templates/partials/deals_table.html` — add checkbox column
- Modify: `dashboard/templates/deals.html` — add floating compare bar + JS logic

**Deals table changes** (in `partials/deals_table.html`):
- Add a new `<th>` as the first column header (empty, narrow)
- Add a checkbox `<td>` as the first cell in each row:
```html
<td class="py-3 pl-4 pr-1 w-8" onclick="event.stopPropagation()">
    <input type="checkbox" class="compare-cb rounded border-outline-variant text-primary focus:ring-primary/30"
           value="{{ deal.id }}" onchange="updateCompareBar()">
</td>
```
- Adjust existing first column `pl-4` to `pl-2`

**Floating compare bar** (add at bottom of `deals.html`, before `{% endblock %}`):
```html
<div id="compare-bar" class="hidden fixed bottom-0 left-0 lg:left-64 right-0 z-20 bg-primary-container border-t border-surface-variant/30 px-6 py-3">
    <div class="flex items-center justify-between max-w-7xl mx-auto">
        <span class="text-sm font-label text-on-primary-container">
            <span id="compare-count">0</span> deals selected
        </span>
        <div class="flex items-center gap-3">
            <button onclick="clearCompare()" class="text-sm font-label text-on-primary-container/70 hover:text-on-primary-container">
                Clear
            </button>
            <button onclick="goCompare()" id="compare-btn"
                    class="px-4 py-2 bg-primary text-on-primary rounded-card text-sm font-medium hover:bg-primary-dim transition-colors">
                Compare
            </button>
        </div>
    </div>
</div>
```

**JS logic** (in `deals.html`):
```javascript
function updateCompareBar() {
    const checked = document.querySelectorAll('.compare-cb:checked');
    const bar = document.getElementById('compare-bar');
    const countEl = document.getElementById('compare-count');
    const btn = document.getElementById('compare-btn');
    countEl.textContent = checked.length;
    bar.classList.toggle('hidden', checked.length === 0);
    btn.disabled = checked.length < 2 || checked.length > 5;
    btn.classList.toggle('opacity-50', checked.length < 2 || checked.length > 5);
}

function clearCompare() {
    document.querySelectorAll('.compare-cb:checked').forEach(cb => cb.checked = false);
    updateCompareBar();
}

function goCompare() {
    const ids = Array.from(document.querySelectorAll('.compare-cb:checked')).map(cb => cb.value);
    if (ids.length >= 2 && ids.length <= 5) {
        window.location = '/compare?ids=' + ids.join(',');
    }
}
```

**Tests:**
- `test_deals_table_has_checkboxes` — response contains `compare-cb`
- `test_deals_page_has_compare_bar` — response contains `compare-bar`

---

## Task 3: Scoring Tuner Page + Simulate API

Add the tuner page with rule editor and live simulation endpoint.

**Files:**
- Modify: `dashboard/templates/base.html` — add Scoring Tuner to sidebar nav (after Profiles, before System Health)
- Create: `dashboard/templates/tuner.html` — rule editor + results table
- Modify: `dashboard.py` — add `GET /tuner`, `GET /tuner/{profile}`, `POST /api/tuner/{profile}/simulate`
- Test: `tests/test_dashboard.py` — add TestTunerPage class

**Sidebar link** (add in `base.html` nav, after Profiles link):
```html
<a href="/tuner" class="flex items-center gap-3 px-4 py-3 rounded-card text-sm font-medium transition-colors {% if active_page == 'tuner' %}bg-surface-container-high text-primary{% else %}text-on-surface-variant hover:bg-surface-container{% endif %}">
    <span class="material-symbols-outlined text-[20px]">labs</span>
    Scoring Tuner
</a>
```

**Routes:**

1. `GET /tuner` — profile selector page. Lists profiles with links to `/tuner/{name}`.

2. `GET /tuner/{profile}` — loads profile YAML, fetches up to 50 recent deals from SQLite for that profile, scores them with current rules, renders the tuner template.

```python
@app.get("/tuner", response_class=HTMLResponse)
async def tuner_index(request: Request):
    profiles = _get_profiles()
    return templates.TemplateResponse(request, "tuner.html", {
        "active_page": "tuner",
        "profiles": profiles,
        "selected_profile": None,
        "deals": [],
        "profile_data": None,
    })

@app.get("/tuner/{profile}", response_class=HTMLResponse)
async def tuner_profile(request: Request, profile: str, db: SQLiteStorage = Depends(get_db)):
    profile_data = safe_load_profile(profile)
    if profile_data is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    deals = db.get_deals(profile=profile, limit=50)
    # Score each deal with current rules
    from filters.base import BaseFilter
    from sources.base import Deal
    scorer = BaseFilter(profile_data)
    scored = []
    for d in deals:
        deal_obj = Deal(
            id=d["id"], title=d["title"], price=d["price"] or 0,
            link=d["link"] or "", source=d["source"] or "",
            description=d["description"] or "", temperature=0,
            image_url=d["image_url"] or "", published_at="",
        )
        result = scorer.score_deal(deal_obj)
        scored.append({
            **d,
            "new_score": result.score,
            "diff": result.score - (d["score"] or 0),
            "breakdown": result.breakdown,
            "rejected": result.rejected,
            "reject_reason": result.reject_reason,
        })
    scored.sort(key=lambda x: x["new_score"], reverse=True)
    return templates.TemplateResponse(request, "tuner.html", {
        "active_page": "tuner",
        "profiles": _get_profiles(),
        "selected_profile": profile,
        "deals": scored,
        "profile_data": profile_data,
    })
```

3. `POST /api/tuner/{profile}/simulate` — accepts JSON body with modified rules, re-scores deals in memory, returns JSON results.

```python
@app.post("/api/tuner/{profile}/simulate")
async def tuner_simulate(request: Request, profile: str, db: SQLiteStorage = Depends(get_db)):
    body = await request.json()
    profile_data = safe_load_profile(profile)
    if profile_data is None:
        return JSONResponse({"error": "Profile not found"}, status_code=404)
    # Override with submitted rules
    modified = dict(profile_data)
    if "score_rules" in body:
        modified["score_rules"] = body["score_rules"]
    if "penalties" in body:
        modified["penalties"] = body["penalties"]
    if "budget" in body:
        modified["budget"] = body["budget"]
    if "score_threshold" in body:
        modified["score_threshold"] = body["score_threshold"]
    if "score_threshold_alert" in body:
        modified["score_threshold_alert"] = body["score_threshold_alert"]
    if "excluded_words" in body:
        modified["excluded_words"] = body["excluded_words"]
    if "required_any" in body:
        modified["required_any"] = body["required_any"]

    deals = db.get_deals(profile=profile, limit=50)
    from filters.base import BaseFilter
    from sources.base import Deal
    scorer = BaseFilter(modified)
    results = []
    for d in deals:
        deal_obj = Deal(
            id=d["id"], title=d["title"], price=d["price"] or 0,
            link=d["link"] or "", source=d["source"] or "",
            description=d["description"] or "", temperature=0,
            image_url=d["image_url"] or "", published_at="",
        )
        result = scorer.score_deal(deal_obj)
        results.append({
            "id": d["id"],
            "title": d["title"],
            "price": d["price"],
            "current_score": d["score"],
            "new_score": result.score,
            "diff": result.score - (d["score"] or 0),
            "rejected": result.rejected,
            "reject_reason": result.reject_reason,
            "breakdown": result.breakdown,
        })
    results.sort(key=lambda x: x["new_score"], reverse=True)
    return JSONResponse({"results": results})
```

4. `POST /api/tuner/{profile}/save` — saves modified rules to profile YAML.

```python
@app.post("/api/tuner/{profile}/save")
async def tuner_save(request: Request, profile: str):
    body = await request.json()
    profile_data = safe_load_profile(profile)
    if profile_data is None:
        return JSONResponse({"error": "Profile not found"}, status_code=404)
    # Update only tunable fields
    for key in ("score_rules", "penalties", "budget", "score_threshold",
                "score_threshold_alert", "excluded_words", "required_any"):
        if key in body:
            profile_data[key] = body[key]
    # Validate
    from utils.validation import validate_profile
    errors = validate_profile(profile_data)
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=400)
    import yaml
    profile_path = Path(__file__).parent / "profiles" / f"{profile}.yaml"
    profile_path.write_text(yaml.dump(profile_data, allow_unicode=True, default_flow_style=False, sort_keys=False), encoding="utf-8")
    return JSONResponse({"ok": True})
```

IMPORTANT: Register `GET /tuner` BEFORE `GET /tuner/{profile}` in dashboard.py — though since "/tuner" has no path param this should route correctly regardless.

**Template** (`tuner.html`):

Layout: `{% extends "base.html" %}`, `{% set active_page = "tuner" %}`

When `selected_profile` is None: show profile selector grid (same card style as profiles.html).

When `selected_profile` is set, show two-column layout:
- **Left column (editor):** Profile selector dropdown at top. Then sections for:
  - Score Rules table — keyword + points, add/remove rows dynamically via JS
  - Penalties table — keyword + penalty, add/remove rows
  - Budget — min/max inputs
  - Thresholds — score_threshold + score_threshold_alert inputs
  - Excluded words — comma-separated textarea
  - Required any — comma-separated textarea
  - Buttons: "Simulate" (POST to simulate API, update results table) and "Save Profile" (POST to save API)

- **Right column (results):** Table of deals sorted by new score. Columns:
  - Title (truncated, links to deal detail)
  - Price (format_pln)
  - Current Score
  - New Score (color-coded)
  - Diff (green +N / red -N / gray 0)
  - Status (rejected badge if applicable)

Results table updated via JS after simulate API call. DOM-safe rendering:
```javascript
function renderResults(results) {
    const tbody = document.getElementById('results-body');
    tbody.replaceChildren();
    results.forEach(r => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-surface-container transition-colors';

        const tdTitle = document.createElement('td');
        tdTitle.className = 'py-2 pl-4 pr-2';
        const titleLink = document.createElement('a');
        titleLink.href = '/deals/' + encodeURIComponent(r.id);
        titleLink.className = 'text-sm text-primary hover:underline line-clamp-1';
        titleLink.textContent = r.title;
        tdTitle.appendChild(titleLink);
        tr.appendChild(tdTitle);

        // ... similar for other columns using textContent ...

        const tdDiff = document.createElement('td');
        tdDiff.className = 'py-2 pr-2';
        const diffSpan = document.createElement('span');
        diffSpan.className = 'text-sm font-headline font-bold ' +
            (r.diff > 0 ? 'text-tertiary' : r.diff < 0 ? 'text-error' : 'text-on-surface-variant');
        diffSpan.textContent = (r.diff > 0 ? '+' : '') + r.diff;
        tdDiff.appendChild(diffSpan);
        tr.appendChild(tdDiff);

        tbody.appendChild(tr);
    });
}
```

**Error display** — same safe DOM pattern as profile editor (createElement + textContent).

**Tests:**
- `test_tuner_index_loads` — GET /tuner returns 200
- `test_tuner_profile_loads` — GET /tuner/{profile} returns 200 with deals
- `test_tuner_profile_404` — GET /tuner/nonexistent returns 404
- `test_tuner_simulate` — POST /api/tuner/{profile}/simulate returns results JSON
- `test_tuner_save` — POST /api/tuner/{profile}/save writes profile YAML

---

## Task 4: Final Integration — Lint, Tests, Docs, Push

- Run full test suite: `./venv/bin/python -m pytest tests/ --tb=short -q`
- Lint/format: `./venv/bin/ruff check . --fix && ./venv/bin/ruff format .`
- Update CLAUDE.md: mention Scoring Tuner and Comparator in dashboard description, add test modules
- Update ROADMAP-v2.md: mark A.1 and C.2 as Done
- Commit and push

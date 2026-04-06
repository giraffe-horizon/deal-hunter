# Deal Hunter — Refactoring & Cleanup Design Spec

**Date:** 2026-04-07
**Status:** Approved
**Scope:** Full-stack refactoring — tooling, security, frontend DRY, backend architecture, directory structure

---

## Current State

| Metric | Value |
|--------|-------|
| Python backend | 3,781 LOC across 6 core files |
| Templates | 2,745 LOC across 14 HTML files |
| Inline JS in templates | ~1,100 lines |
| Static asset directory | Does not exist |
| Jinja2 macros/includes | 1 partial, 0 macros |
| CSRF protection | None |
| ORM | None — raw parameterized SQL |
| Dependency pinning | Loose in pyproject.toml, pinned in requirements.txt |

### Key Problem Files

| File | Lines | Issues |
|------|-------|--------|
| `deal_hunter.py` | 1,344 | `_run_normal()` is 250 lines mixing fetch/score/persist/notify |
| `dashboard.py` | 826 | 24 routes with inline business logic, N+1 queries, no CSRF |
| `storage/sqlite.py` | 617 | N+1 in `get_price_drops()`, no batch query methods |
| `feedback_bot.py` | 245 | 5 identical try/finally DB access patterns |
| Templates (14 files) | 2,745 | 0 macros, ~1,100 lines inline JS, heavy duplication |

---

## Phase 1: Tooling, Formatting & Environment Hardening

**Goal:** Safety net before touching architecture. Config-level only — zero runtime risk.

### 1.1 Tighten dependency pinning in `pyproject.toml`

Pin core dependencies to minimum versions:

```toml
dependencies = [
    "requests>=2.31",
    "beautifulsoup4>=4.12",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "fastapi>=0.109",
    "uvicorn[standard]>=0.25",
    "jinja2>=3.1",
    "python-multipart>=0.0.6",
]
```

### 1.2 Strengthen Mypy configuration

Replace blanket `ignore_missing_imports` with per-module overrides:

```toml
[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[[tool.mypy.overrides]]
module = ["telegram.*", "matplotlib.*"]
ignore_missing_imports = true
```

### 1.3 Add missing `.gitignore` entries

```
.mypy_cache/
.pytest_cache/
.ruff_cache/
```

### 1.4 Expand Ruff rules for security & complexity

```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "S", "C90", "B", "A"]
ignore = ["E501", "S101"]
```

New rule groups: S (bandit security), C90 (mccabe complexity), B (bugbear), A (builtins shadowing).

### 1.5 Add Dockerfile HEALTHCHECK

```dockerfile
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD python deal_hunter.py --health || exit 1
```

### Validation

- `ruff check .` passes
- `mypy .` passes (or only known exclusions fail)
- `pytest tests/ -v` passes
- Docker build succeeds

---

## Phase 2: Security Fixes

**Goal:** Fix two critical vulnerabilities before structural changes.

### 2.1 Path traversal protection

Create centralized profile name validator in `dashboard.py`:

```python
import re
from fastapi import HTTPException

_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")

def safe_profile_path(name: str) -> Path:
    if not _PROFILE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid profile name")
    path = (PROFILES_DIR / f"{name}.yaml").resolve()
    if not path.is_relative_to(PROFILES_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid profile name")
    return path
```

Apply to all 9 profile endpoints that accept `{name}` path parameters:
- `GET /profiles/{name}` (line ~541)
- `GET /profiles/{name}/edit` (line ~554)
- `GET /profiles/{name}/edit/yaml` (line ~450)
- `PUT /api/profiles/{name}/yaml` (line ~467)
- `PUT /api/profiles/{name}` (line ~568)
- `DELETE /api/profiles/{name}` (line ~601)
- `PATCH /api/profiles/{name}/toggle` (line ~611)
- `POST /api/profiles/{name}/run` (line ~631)
- `POST /api/profiles` already validates on creation (line ~515)

### 2.2 CSRF protection

Add middleware that requires `HX-Request` or `X-Requested-With` header on all mutating requests:

```python
@app.middleware("http")
async def csrf_check(request: Request, call_next):
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if not request.headers.get("HX-Request") and not request.headers.get("X-Requested-With"):
            return JSONResponse(status_code=403, content={"detail": "CSRF check failed"})
    return await call_next(request)
```

HTMX sends `HX-Request: true` automatically. Add `X-Requested-With: XMLHttpRequest` to any non-HTMX fetch calls in templates.

### 2.3 Explicit Jinja2 autoescape

```python
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.autoescape = True
```

### Validation

- `GET /profiles/../../etc/passwd` returns 400
- All POST/PUT/DELETE work with HTMX (HX-Request header present)
- Direct form submissions without headers return 403
- `pytest tests/test_dashboard.py` passes

---

## Phase 3: Frontend — Template DRY & Static Assets

**Goal:** Eliminate ~60% of template duplication, create proper static asset structure.

### 3.1 Create `dashboard/static/` and mount it

Directory structure:
```
dashboard/static/
  js/
    charts.js          # Chart.js helpers (from deal_detail, compare, price_trends)
    compare.js         # Compare bar (from deals.html)
    tuner.js           # Scoring simulator (from tuner.html, 200 lines)
    profile-form.js    # Shared form logic (from profile_create + profile_edit)
    sidebar.js         # toggleSidebar() (from base.html)
```

Mount in FastAPI:
```python
from starlette.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=BASE_DIR / "dashboard" / "static"), name="static")
```

Extraction targets by inline JS line count:

| Source template | Target file | Lines |
|----------------|-------------|-------|
| `tuner.html:281-481` | `tuner.js` | 200 |
| `deal_detail.html:235-369` | `charts.js` | 135 |
| `profile_create.html:136-246` | `profile-form.js` | 111 |
| `profile_edit.html:177-283` | `profile-form.js` | 107 |
| `compare.html:155-184` | `charts.js` | 30 |
| `price_trends.html:157-210` | `charts.js` | 54 |
| `deals.html:145-169` | `compare.js` | 25 |
| `base.html:155-170` | `sidebar.js` | 16 |

### 3.2 Jinja2 macro library

Create `dashboard/templates/macros.html` with these macros:

| Macro | Signature | Eliminates |
|-------|-----------|------------|
| `metric_card` | `(icon, label, value, sublabel="")` | 12+ duplicated card blocks |
| `section_card` | `(title)` — callable | 38+ card header patterns |
| `breadcrumb` | `(items)` — list of `{href, label}` | 6 duplicated breadcrumbs |
| `form_field` | `(label, name, type, value, placeholder, required)` | 30+ input patterns |
| `status_badge` | `(text, variant="primary")` | 10+ badge patterns |
| `empty_state` | `(icon, message, action_href, action_label)` | 4+ empty state blocks |

Usage pattern:
```jinja2
{% from "macros.html" import metric_card, breadcrumb, empty_state %}
```

### 3.3 Extract inline HTML from Python

Move HTML string in `dashboard.py:333-351` (`api_update_deal_status`) to partial template `partials/deal_status_badge.html`.

### Validation

- Visual check of all 12 pages (no regressions)
- HTMX interactions work (deals filtering, watchlist delete, profile run)
- `pytest tests/test_dashboard.py` passes
- All JS functionality works (charts render, tuner simulates, forms submit)

---

## Phase 4: Backend Architecture — Separation of Concerns

**Goal:** Decouple business logic from routing, break up largest files.

### 4.1 Service layer: `dashboard/services.py`

Extract business logic from route handlers:

```python
class DealService:
    def __init__(self, db: SQLiteStorage):
        self.db = db

    def get_deals_page(self, profile, source, sort, page, per_page) -> dict:
        """Deals + pagination + stats for the deals page."""

    def get_comparison_data(self, deal_ids: list[str]) -> dict:
        """Batch-fetch deals, price histories, lowest prices (fixes N+1)."""

    def score_deals_with_profile(self, profile_name, profile_data) -> list[dict]:
        """Score deals using a profile configuration."""
```

Routes become thin wrappers:
```python
@app.get("/deals")
async def deals_page(request: Request, db = Depends(get_db), ...):
    data = DealService(db).get_deals_page(profile, source, sort, page, per_page)
    return templates.TemplateResponse("deals.html", {"request": request, **data})
```

### 4.2 Fix N+1 queries

**Batch price history** — new method in `storage/sqlite.py`:
```python
def get_price_histories_batch(self, deal_ids: list[str]) -> dict[str, list[dict]]:
    placeholders = ",".join("?" for _ in deal_ids)
    rows = self._conn.execute(
        f"SELECT * FROM price_history WHERE deal_id IN ({placeholders}) ORDER BY recorded_at",
        deal_ids
    ).fetchall()
    result = {did: [] for did in deal_ids}
    for row in rows:
        result[row["deal_id"]].append(dict(row))
    return result
```

**Window function for price drops** — replace nested loop in `get_price_drops()`:
```sql
WITH ranked AS (
    SELECT deal_id, price, recorded_at,
           LAG(price) OVER (PARTITION BY deal_id ORDER BY recorded_at) as prev_price
    FROM price_history WHERE recorded_at >= ?
)
SELECT * FROM ranked WHERE prev_price IS NOT NULL AND price < prev_price
```

### 4.3 Break up `_run_normal()` (250 lines -> 5 functions)

```python
def _run_normal(profile, profile_name, args):
    deals = _fetch_and_score(profile, profile_name, args)
    new_deals = _filter_new_deals(deals, state, db)
    _persist_deals(new_deals, db, state, profile_name)
    _handle_price_changes(deals, profile, db, notifier)
    _send_alerts(new_deals, profile, notifier, db)
    _save_state(state, state_file)
```

Each sub-function: 30-50 lines, single responsibility, independently testable.

### 4.4 DB context manager for `feedback_bot.py`

Replace 5 identical try/finally blocks:

```python
from contextlib import contextmanager

@contextmanager
def get_storage():
    db = SQLiteStorage(DB_PATH)
    try:
        yield db
    finally:
        db.close()
```

### 4.5 Fix async/sync inconsistency in dashboard

Rules:
- Sync `def` for routes doing SQLite/file I/O (FastAPI threadpools these automatically)
- `async def` only for routes that actually `await` something
- No `async def` that never awaits

### Validation

- `pytest tests/ -v` (full suite)
- `python deal_hunter.py --profile bikes --verify` works
- Dashboard pages load, HTMX works
- Performance: compare page loads faster (no N+1)

---

## Phase 5: Directory Structure Reorganization

**Goal:** Scalable package structure. This is the largest and riskiest phase.

### 5.1 Target structure

```
deal_hunter/                    # package (from deal_hunter.py)
  __init__.py                   # __version__, main()
  cli.py                        # argparse, entry point
  orchestrator.py               # run_profile, _run_normal and sub-functions
  scoring.py                    # score/filter orchestration
  dedup.py                      # deduplicate()
  config.py                     # load_profile(), env loading, path constants
  sources/                      # unchanged
  filters/                      # unchanged
  notifiers/                    # unchanged
  storage/                      # unchanged
  utils/                        # unchanged
dashboard/
  __init__.py                   # create_app() factory
  app.py                        # FastAPI app, middleware, static mount
  routes/
    deals.py                    # /deals, /deals/{id}, /api/deals/*
    profiles.py                 # /profiles/*, /api/profiles/*
    watchlist.py                # /watchlist, /api/watchlist/*
    tuner.py                    # /tuner/*
    health.py                   # /health
  services.py                   # from Phase 4.1
  dependencies.py               # get_db(), safe_profile_path()
  templates/                    # unchanged
  static/                       # from Phase 3.1
feedback_bot.py                 # stays standalone
```

### 5.2 Migration strategy

1. Create `deal_hunter/` package, move functions incrementally
2. Keep `deal_hunter.py` as thin import wrapper for backward compat
3. Update `pyproject.toml`: `deal-hunter = "deal_hunter.cli:main"`
4. Split `dashboard.py` into route modules using `APIRouter`
5. Update all test imports
6. Verify: `python deal_hunter.py --list` still works

### Validation

- `python deal_hunter.py --list`, `--verify`, `--health` all work
- `pytest tests/ -v` passes
- Docker build succeeds
- Dashboard fully functional

---

## Phase 6: Polish & Performance

**Goal:** Final quality pass after restructuring.

### 6.1 Telegram message builder

Extract formatting to `notifiers/message_builder.py`:
- `format_deal_alert(deal, score, profile) -> str`
- `format_price_drop(deal, old_price, new_price) -> str`
- `format_digest(drops) -> str`

### 6.2 Environment validation on startup

```python
def validate_environment():
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        logger.warning("Missing env vars: %s — Telegram alerts disabled", missing)
```

### 6.3 Dead code audit

Run `ruff check --select F841,F811` and review. Clean up anything orphaned by the restructuring.

### Validation

- Full test suite green
- Docker build + compose up
- End-to-end: fetch -> score -> alert flow works

---

## Execution Priority

| Phase | Risk | Effort | Value | Depends On |
|-------|------|--------|-------|-----------|
| 1 — Tooling | None | Small | Medium | — |
| 2 — Security | Low | Small | Critical | — |
| 3 — Templates | Low | Medium | High | Phase 1 |
| 4 — Backend | Medium | Medium | High | Phase 1 |
| 5 — Directory | Medium | Large | Medium | Phase 4 |
| 6 — Polish | Low | Small | Medium | Phase 4 |

Phases 1+2 can run in parallel. Phases 3+4 are independent of each other. Phase 5 requires Phase 4. Phase 6 can overlap with Phase 5.

---

## Out of Scope

- ORM migration (raw SQL with parameterized queries is fine for this project size)
- Frontend framework migration (HTMX + vanilla JS is appropriate)
- API versioning (single consumer, internal dashboard)
- Async SQLite driver (sqlite3 with sync FastAPI routes in threadpool is adequate)
- New features or profile changes

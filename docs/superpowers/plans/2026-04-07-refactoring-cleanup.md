# Deal Hunter Refactoring & Cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Incrementally refactor Deal Hunter across tooling, security, frontend DRY, backend architecture, and directory structure — without breaking existing functionality.

**Architecture:** Six phases executed sequentially. Each phase is independently testable. Phases 1-2 are config/security (low risk). Phases 3-4 are the bulk of the work (frontend DRY + backend separation). Phases 5-6 are structural reorganization and polish.

**Tech Stack:** Python 3.12+, FastAPI, Jinja2, HTMX, Chart.js, Tailwind CSS (CDN), SQLite, pytest

**Spec:** `docs/superpowers/specs/2026-04-07-refactoring-cleanup-design.md`

---

## Phase 1: Tooling, Formatting & Environment Hardening

### Task 1: Tighten dependency pinning and Ruff/Mypy config

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`

- [ ] **Step 1: Update dependency pinning in pyproject.toml**

Change `[project] dependencies` (lines 26-35) from unpinned to minimum-version pinned:

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

- [ ] **Step 2: Expand Ruff lint rules**

Change `[tool.ruff.lint]` (lines 72-74) to add security, complexity, and bugbear checks:

```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "S", "C90", "B", "A"]
ignore = ["E501", "S101"]
```

- [ ] **Step 3: Strengthen Mypy configuration**

Replace `[tool.mypy]` block (lines 79-83) with per-module overrides:

```toml
[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = false

[[tool.mypy.overrides]]
module = ["telegram.*", "matplotlib.*"]
ignore_missing_imports = true
```

- [ ] **Step 4: Add missing .gitignore entries**

Append to `.gitignore`:

```
.mypy_cache/
.pytest_cache/
.ruff_cache/
```

- [ ] **Step 5: Run linting to verify**

Run: `cd /home/liske/Projects/deal-hunter && source venv/bin/activate && ruff check . 2>&1 | head -30`

Fix any new violations introduced by the expanded rule set (S, C90, B, A). Common fixes:
- `S603`/`S607` (subprocess): add `# noqa: S603, S607` to the subprocess.run call in `dashboard.py:642`
- `A001`/`A002` (shadowing builtins): rename `status` params if flagged, or `# noqa` if intentional
- `C901` (complexity): ignore for `_run_normal` — we'll refactor it in Phase 4

- [ ] **Step 6: Run mypy to verify**

Run: `mypy . 2>&1 | head -30`

Fix or suppress any new errors. The `ignore_missing_imports = false` will surface missing stubs — add per-module overrides as needed.

- [ ] **Step 7: Run tests to verify nothing broke**

Run: `pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: All existing tests pass.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore
git commit -m "chore: tighten dependency pinning, expand ruff/mypy config, update gitignore"
```

---

### Task 2: Add Dockerfile HEALTHCHECK

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Add HEALTHCHECK instruction**

Add before the `ENTRYPOINT` line (before line 46 in `Dockerfile`):

```dockerfile
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD python deal_hunter.py --health || exit 1
```

- [ ] **Step 2: Verify Docker build**

Run: `docker build -t deal-hunter-test . 2>&1 | tail -5`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "chore: add Docker HEALTHCHECK instruction"
```

---

## Phase 2: Security Fixes

### Task 3: Add centralized profile name validator

**Files:**
- Modify: `dashboard.py:447-661` (all profile endpoints)
- Create: `tests/test_profile_security.py`

- [ ] **Step 1: Write failing tests for path traversal protection**

Create `tests/test_profile_security.py`:

```python
"""Tests for profile name validation and path traversal protection."""

from starlette.testclient import TestClient


def test_profile_path_traversal_dot_dot(client: TestClient):
    """Profile names with '..' must return 400."""
    resp = client.get("/profiles/../../etc/passwd")
    assert resp.status_code == 400


def test_profile_path_traversal_slash(client: TestClient):
    """Profile names with '/' must return 400."""
    resp = client.get("/profiles/foo/bar")
    # This might be 404 (route not matched) or 400 — either is acceptable
    assert resp.status_code in (400, 404)


def test_profile_valid_name_accepted(client: TestClient):
    """Valid profile names pass validation (404 because profile doesn't exist)."""
    resp = client.get("/profiles/test-profile-123")
    assert resp.status_code == 404  # valid name, but profile doesn't exist


def test_profile_delete_traversal(client: TestClient):
    """DELETE with path traversal name must return 400."""
    resp = client.delete("/api/profiles/..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code == 400


def test_profile_yaml_edit_traversal(client: TestClient):
    """YAML edit with path traversal name must return 400."""
    resp = client.get("/profiles/..%2F..%2Fetc%2Fpasswd/edit/yaml")
    assert resp.status_code == 400


def test_profile_toggle_traversal(client: TestClient):
    """PATCH toggle with path traversal name must return 400."""
    resp = client.patch("/api/profiles/..%2F..%2Fetc%2Fpasswd/toggle")
    assert resp.status_code == 400


def test_profile_run_traversal(client: TestClient):
    """POST run with path traversal name must return 400."""
    resp = client.post("/api/profiles/..%2F..%2Fetc%2Fpasswd/run")
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_profile_security.py -v 2>&1 | tail -20`
Expected: Most tests FAIL (traversal names currently not validated).

- [ ] **Step 3: Implement safe_profile_path validator in dashboard.py**

Add after the `get_db()` function (after line 48) in `dashboard.py`:

```python
import re

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
```

- [ ] **Step 4: Apply safe_profile_path to all profile endpoints**

Replace raw path construction in each endpoint. For each endpoint that uses `name: str` path parameter and constructs `BASE_DIR / "profiles" / f"{name}.yaml"`:

**`profile_yaml_page` (line 448):** Replace `profile_path = BASE_DIR / "profiles" / f"{name}.yaml"` with `profile_path = safe_profile_path(name)`.

**`api_update_profile_yaml` (line 461):** Replace `profile_path = BASE_DIR / "profiles" / f"{name}.yaml"` with `profile_path = safe_profile_path(name)`.

**`profile_detail_page` (line 541):** Add `safe_profile_path(name)` as first line (for validation only — profile loading still uses `safe_load_profile`).

**`profile_edit_page` (line 554):** Add `safe_profile_path(name)` as first line.

**`api_update_profile` (line 568):** Add `safe_profile_path(name)` as first line. Replace `profile_path = BASE_DIR / "profiles" / f"{name}.yaml"` (line 594) with `profile_path = safe_profile_path(name)`.

**`api_delete_profile` (line 601):** Replace `profile_path = BASE_DIR / "profiles" / f"{name}.yaml"` with `profile_path = safe_profile_path(name)`.

**`api_toggle_profile` (line 611):** Replace `profile_path = BASE_DIR / "profiles" / f"{name}.yaml"` with `profile_path = safe_profile_path(name)`.

**`api_run_profile` (line 631):** Replace `profile_path = BASE_DIR / "profiles" / f"{name}.yaml"` with `profile_path = safe_profile_path(name)`.

**`tuner_profile` (line 715):** Add `safe_profile_path(profile)` as first line.

**`tuner_simulate` (line 736):** Add `safe_profile_path(profile)` as first line.

**`tuner_save` (line 775):** Replace `profile_path = BASE_DIR / "profiles" / f"{profile}.yaml"` (line 800) with `profile_path = safe_profile_path(profile)`.

- [ ] **Step 5: Run security tests**

Run: `pytest tests/test_profile_security.py -v 2>&1`
Expected: All PASS.

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add dashboard.py tests/test_profile_security.py
git commit -m "fix(security): add path traversal protection to all profile endpoints"
```

---

### Task 4: Add CSRF protection middleware

**Files:**
- Modify: `dashboard.py` (add middleware)
- Modify: `dashboard/templates/profile_create.html` (add header to fetch)
- Modify: `dashboard/templates/profile_edit.html` (add header to fetch)
- Modify: `dashboard/templates/tuner.html` (add header to fetch)
- Create: `tests/test_csrf.py`

- [ ] **Step 1: Write failing CSRF tests**

Create `tests/test_csrf.py`:

```python
"""Tests for CSRF protection middleware."""

from starlette.testclient import TestClient


def test_post_without_csrf_header_rejected(client: TestClient):
    """POST without HX-Request or X-Requested-With must return 403."""
    resp = client.post(
        "/api/watchlist",
        data={"deal_id": "test:1", "target_price": "100"},
        headers={},  # no CSRF headers
    )
    assert resp.status_code == 403


def test_post_with_hx_request_allowed(client: TestClient):
    """POST with HX-Request header must be allowed."""
    resp = client.post(
        "/api/watchlist",
        data={"deal_id": "test:1", "target_price": "100"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200


def test_post_with_x_requested_with_allowed(client: TestClient):
    """POST with X-Requested-With header must be allowed."""
    resp = client.post(
        "/api/watchlist",
        data={"deal_id": "test:1", "target_price": "100"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200


def test_get_without_csrf_header_allowed(client: TestClient):
    """GET requests must not require CSRF headers."""
    resp = client.get("/deals")
    assert resp.status_code == 200


def test_delete_without_csrf_header_rejected(client: TestClient):
    """DELETE without CSRF headers must return 403."""
    resp = client.delete("/api/watchlist/test:1", headers={})
    assert resp.status_code == 403


def test_put_with_content_type_json_allowed(client: TestClient):
    """PUT with Content-Type: application/json should be allowed (browser forms can't send JSON)."""
    resp = client.put(
        "/api/profiles/nonexistent/yaml",
        content="name: test",
        headers={"Content-Type": "application/octet-stream", "X-Requested-With": "XMLHttpRequest"},
    )
    # 400 or 404, not 403
    assert resp.status_code != 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_csrf.py -v 2>&1 | tail -20`
Expected: `test_post_without_csrf_header_rejected` FAILS (currently returns 200).

- [ ] **Step 3: Add CSRF middleware to dashboard.py**

Add after the `app = FastAPI(...)` line (line 26) in `dashboard.py`:

```python
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
```

- [ ] **Step 4: Add X-Requested-With header to fetch calls in templates**

HTMX requests already send `HX-Request: true` automatically. But vanilla `fetch()` calls in templates need the header.

**`dashboard/templates/profile_create.html` line 229:** Change the fetch headers:
```javascript
    fetch('/api/profiles', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        body: JSON.stringify(data),
    })
```

**`dashboard/templates/profile_edit.html` line 266:** Change the fetch headers:
```javascript
    fetch('/api/profiles/' + encodeURIComponent(name), {
        method: 'PUT',
        headers: {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        body: JSON.stringify(body)
    })
```

**`dashboard/templates/tuner.html` line 289 (simulate):** Change the fetch headers:
```javascript
        const resp = await fetch('/api/tuner/{{ selected_profile }}/simulate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
            body: JSON.stringify(rules),
        });
```

**`dashboard/templates/tuner.html` line 452 (save):** Change the fetch headers:
```javascript
        const resp = await fetch('/api/tuner/{{ selected_profile }}/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
            body: JSON.stringify(rules),
        });
```

**`dashboard/templates/profile_yaml.html`:** Find the fetch call for saving YAML and add the same header.

- [ ] **Step 5: Run CSRF tests**

Run: `pytest tests/test_csrf.py -v 2>&1`
Expected: All PASS.

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: All tests pass. Some existing tests may fail if they POST without headers — fix by adding `headers={"HX-Request": "true"}` or `headers={"X-Requested-With": "XMLHttpRequest"}` to those test calls.

- [ ] **Step 7: Commit**

```bash
git add dashboard.py dashboard/templates/profile_create.html dashboard/templates/profile_edit.html dashboard/templates/tuner.html dashboard/templates/profile_yaml.html tests/test_csrf.py
git commit -m "fix(security): add CSRF protection middleware, require HX-Request or X-Requested-With on mutations"
```

---

### Task 5: Enable explicit Jinja2 autoescape

**Files:**
- Modify: `dashboard.py:27,38`

- [ ] **Step 1: Set explicit autoescape**

In `dashboard.py`, after the `templates = Jinja2Templates(...)` line (line 27), add:

```python
templates.env.autoescape = True
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -v --tb=short 2>&1 | tail -20`
Expected: All pass (autoescape was already the default, this just makes it explicit).

- [ ] **Step 3: Commit**

```bash
git add dashboard.py
git commit -m "fix(security): enable explicit Jinja2 autoescape"
```

---

## Phase 3: Frontend — Template DRY & Static Assets

### Task 6: Create static directory and extract sidebar JS

**Files:**
- Create: `dashboard/static/js/sidebar.js`
- Modify: `dashboard.py` (mount static files)
- Modify: `dashboard/templates/base.html:155-170` (replace inline script)

- [ ] **Step 1: Create static directory structure**

Run: `mkdir -p /home/liske/Projects/deal-hunter/dashboard/static/js`

- [ ] **Step 2: Extract sidebar JS**

Create `dashboard/static/js/sidebar.js`:

```javascript
function toggleSidebar() {
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebar-overlay');
    var isOpen = !sidebar.classList.contains('-translate-x-full');
    if (isOpen) {
        sidebar.classList.add('-translate-x-full');
        overlay.classList.add('hidden');
        document.body.classList.remove('overflow-hidden');
    } else {
        sidebar.classList.remove('-translate-x-full');
        overlay.classList.remove('hidden');
        document.body.classList.add('overflow-hidden');
    }
}
```

- [ ] **Step 3: Mount static files in dashboard.py**

Add after the `app = FastAPI(...)` line (but before the CSRF middleware):

```python
from starlette.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "dashboard" / "static")), name="static")
```

- [ ] **Step 4: Replace inline script in base.html**

In `dashboard/templates/base.html`, replace lines 155-170 (the `<script>` block with `toggleSidebar()`) with:

```html
    <script src="/static/js/sidebar.js"></script>
```

- [ ] **Step 5: Run tests and verify**

Run: `pytest tests/test_dashboard.py -v --tb=short 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add dashboard/static/js/sidebar.js dashboard.py dashboard/templates/base.html
git commit -m "refactor(frontend): create static dir, extract sidebar JS from base.html"
```

---

### Task 7: Extract compare bar JS

**Files:**
- Create: `dashboard/static/js/compare.js`
- Modify: `dashboard/templates/deals.html:145-169`

- [ ] **Step 1: Create compare.js**

Create `dashboard/static/js/compare.js`:

```javascript
function updateCompareBar() {
    const checked = document.querySelectorAll('.compare-cb:checked');
    const bar = document.getElementById('compare-bar');
    const countEl = document.getElementById('compare-count');
    const btn = document.getElementById('compare-btn');
    if (!bar || !countEl || !btn) return;
    countEl.textContent = checked.length;
    bar.classList.toggle('hidden', checked.length === 0);
    btn.disabled = checked.length < 2 || checked.length > 5;
    btn.classList.toggle('opacity-50', checked.length < 2 || checked.length > 5);
}

function clearCompare() {
    document.querySelectorAll('.compare-cb:checked').forEach(cb => { cb.checked = false; });
    updateCompareBar();
}

function goCompare() {
    const ids = Array.from(document.querySelectorAll('.compare-cb:checked')).map(cb => cb.value);
    if (ids.length >= 2 && ids.length <= 5) {
        window.location = '/compare?ids=' + ids.join(',');
    }
}
```

- [ ] **Step 2: Replace inline script in deals.html**

Replace lines 145-169 (the `<script>` block) in `deals.html` with:

```html
<script src="/static/js/compare.js"></script>
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_dashboard.py -v --tb=short 2>&1 | tail -10`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard/static/js/compare.js dashboard/templates/deals.html
git commit -m "refactor(frontend): extract compare bar JS to static file"
```

---

### Task 8: Extract Chart.js helpers

**Files:**
- Create: `dashboard/static/js/charts.js`
- Modify: `dashboard/templates/deal_detail.html:235-369`
- Modify: `dashboard/templates/compare.html:155-184`
- Modify: `dashboard/templates/price_trends.html:157-210`

- [ ] **Step 1: Create shared chart configuration**

Create `dashboard/static/js/charts.js`:

```javascript
/**
 * Shared Chart.js configuration and helpers for Deal Hunter dashboard.
 */

const DH_CHART_COLORS = {
    primary: '#005db5',
    primaryFill: 'rgba(0, 93, 181, 0.08)',
    secondary: '#526074',
    tertiary: '#006b62',
    error: '#9f403d',
    label: '#445d99',
    grid: 'rgba(152, 177, 242, 0.15)',
    tooltip: '#060e20',
};

const DH_CHART_FONT = 'Inter';

/**
 * Create a price history line chart.
 * @param {HTMLCanvasElement} canvas
 * @param {string[]} labels
 * @param {number[]} prices
 * @param {number|null} lowest
 * @param {number|null} highest
 * @returns {Chart}
 */
function createPriceChart(canvas, labels, prices, lowest, highest) {
    const lowestIdx = lowest !== null ? prices.indexOf(lowest) : -1;
    const highestIdx = highest !== null ? prices.indexOf(highest) : -1;

    const pointBg = prices.map((p, i) => {
        if (i === lowestIdx && lowest !== highest) return DH_CHART_COLORS.error;
        if (i === highestIdx && lowest !== highest) return DH_CHART_COLORS.tertiary;
        return DH_CHART_COLORS.primary;
    });
    const pointRadius = prices.map((p, i) => {
        if (i === lowestIdx || i === highestIdx) return 6;
        return 3;
    });

    return new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Price (PLN)',
                data: prices,
                borderColor: DH_CHART_COLORS.primary,
                backgroundColor: DH_CHART_COLORS.primaryFill,
                fill: true,
                tension: 0.3,
                pointBackgroundColor: pointBg,
                pointBorderColor: pointBg,
                pointRadius: pointRadius,
                pointHoverRadius: 7,
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: DH_CHART_COLORS.tooltip,
                    titleFont: { family: DH_CHART_FONT },
                    bodyFont: { family: DH_CHART_FONT },
                    callbacks: {
                        label: function(ctx) {
                            return ctx.parsed.y.toLocaleString('pl-PL') + ' zl';
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: {
                        font: { family: DH_CHART_FONT, size: 11 },
                        color: DH_CHART_COLORS.label,
                        maxTicksLimit: 10
                    }
                },
                y: {
                    grid: { color: DH_CHART_COLORS.grid },
                    ticks: {
                        font: { family: DH_CHART_FONT, size: 11 },
                        color: DH_CHART_COLORS.label,
                        callback: function(v) { return v.toLocaleString('pl-PL') + ' zl'; }
                    }
                }
            }
        }
    });
}

/**
 * Create a sparkline (no axes, no legend, no tooltip).
 * @param {HTMLCanvasElement} canvas
 * @param {string[]} labels
 * @param {number[]} data
 * @param {string} color
 * @param {boolean} fill
 * @returns {Chart}
 */
function createSparkline(canvas, labels, data, color, fill) {
    color = color || DH_CHART_COLORS.primary;
    return new Chart(canvas, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                borderColor: color,
                backgroundColor: fill ? (color + '15') : 'transparent',
                fill: !!fill,
                tension: 0.3,
                borderWidth: 1.5,
                pointRadius: 0,
                pointHitRadius: 8,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: { x: { display: false }, y: { display: false } },
        }
    });
}

/**
 * Create a sparkline with tooltip enabled.
 * @param {HTMLCanvasElement} canvas
 * @param {string[]} labels
 * @param {number[]} data
 * @param {string} color
 * @returns {Chart}
 */
function createTrendSparkline(canvas, labels, data, color) {
    return new Chart(canvas, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                borderColor: color,
                backgroundColor: color + '15',
                fill: true,
                tension: 0.4,
                borderWidth: 2,
                pointRadius: 0,
                pointHitRadius: 8,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: DH_CHART_COLORS.tooltip,
                    titleFont: { family: DH_CHART_FONT, size: 11 },
                    bodyFont: { family: DH_CHART_FONT, size: 11 },
                    callbacks: {
                        label: function(ctx) {
                            return ctx.parsed.y.toLocaleString('pl-PL') + ' zl';
                        }
                    }
                }
            },
            scales: { x: { display: false }, y: { display: false } }
        }
    });
}
```

- [ ] **Step 2: Rewrite deal_detail.html script block**

Replace lines 235-369 in `deal_detail.html` with:

```html
<script src="/static/js/charts.js"></script>
<script>
(function() {
    let allLabels = [];
    let allPrices = [];
    let chart = null;

    fetch('/api/price-history/{{ deal.id | urlencode }}')
        .then(r => r.json())
        .then(data => {
            allLabels = data.labels;
            allPrices = data.prices;

            if (!allLabels.length) {
                document.getElementById('chart-container').classList.add('hidden');
                document.getElementById('chart-empty').classList.remove('hidden');
                document.getElementById('period-buttons').classList.add('hidden');
                return;
            }

            chart = createPriceChart(
                document.getElementById('priceChart'),
                allLabels, allPrices, data.lowest, data.highest
            );
        })
        .catch(() => {
            document.getElementById('chart-container').classList.add('hidden');
            document.getElementById('chart-empty').classList.remove('hidden');
            document.getElementById('period-buttons').classList.add('hidden');
        });

    window.filterChart = function(period) {
        document.querySelectorAll('.period-btn').forEach(btn => {
            if (btn.dataset.period === period) {
                btn.className = 'period-btn px-3 py-1.5 text-xs font-label rounded-card transition-colors bg-primary text-on-primary';
            } else {
                btn.className = 'period-btn px-3 py-1.5 text-xs font-label rounded-card transition-colors bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest';
            }
        });

        if (!allLabels.length) return;

        let filteredLabels = allLabels;
        let filteredPrices = allPrices;

        if (period !== 'all') {
            const now = new Date();
            const months = period === '1m' ? 1 : 3;
            const cutoff = new Date(now.getFullYear(), now.getMonth() - months, now.getDate());
            const cutoffStr = cutoff.toISOString().slice(0, 10);
            const startIdx = allLabels.findIndex(l => l >= cutoffStr);
            if (startIdx >= 0) {
                filteredLabels = allLabels.slice(startIdx);
                filteredPrices = allPrices.slice(startIdx);
            }
        }

        if (chart) chart.destroy();
        const lowest = filteredPrices.length ? Math.min(...filteredPrices) : null;
        const highest = filteredPrices.length ? Math.max(...filteredPrices) : null;
        chart = createPriceChart(
            document.getElementById('priceChart'),
            filteredLabels, filteredPrices, lowest, highest
        );
    };
})();
</script>
```

- [ ] **Step 3: Rewrite compare.html script block**

Replace lines 155-184 in `compare.html` with:

```html
<script src="/static/js/charts.js"></script>
<script>
(function() {
    const histories = {{ price_histories | tojson }};
    document.querySelectorAll('[data-sparkline]').forEach(el => {
        const dealId = el.dataset.sparkline;
        const history = histories[dealId] || [];
        if (!history.length) return;
        createSparkline(
            el,
            history.map(h => h.recorded_at.slice(0, 10)),
            history.map(h => h.price),
            null,
            false
        );
    });
})();
</script>
```

- [ ] **Step 4: Rewrite price_trends.html script block**

Replace lines 156-211 in `price_trends.html` with:

```html
{% if category_trends %}
<script src="/static/js/charts.js"></script>
<script>
(function() {
    const colors = [DH_CHART_COLORS.primary, DH_CHART_COLORS.secondary, DH_CHART_COLORS.tertiary];
    const trends = {{ category_trends | tojson }};
    let idx = 0;
    for (const [cat, data] of Object.entries(trends)) {
        idx++;
        const canvas = document.getElementById('sparkline-' + idx);
        if (!canvas || !data.length) continue;
        createTrendSparkline(
            canvas,
            data.map(d => d.day),
            data.map(d => d.avg_price),
            colors[(idx - 1) % colors.length]
        );
    }
})();
</script>
{% endif %}
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_dashboard.py -v --tb=short 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add dashboard/static/js/charts.js dashboard/templates/deal_detail.html dashboard/templates/compare.html dashboard/templates/price_trends.html
git commit -m "refactor(frontend): extract Chart.js helpers to shared static file"
```

---

### Task 9: Extract tuner and profile form JS

**Files:**
- Create: `dashboard/static/js/tuner.js`
- Create: `dashboard/static/js/profile-form.js`
- Modify: `dashboard/templates/tuner.html:281-481`
- Modify: `dashboard/templates/profile_create.html:136-246`
- Modify: `dashboard/templates/profile_edit.html:177-283`

- [ ] **Step 1: Create tuner.js**

Create `dashboard/static/js/tuner.js` with the content from `tuner.html` lines 282-481. Replace the hardcoded `{{ selected_profile }}` template variable with a data attribute approach:

In `tuner.html`, add a data attribute to the grid container (around line 44):
```html
<div class="grid grid-cols-1 xl:grid-cols-2 gap-6" data-profile="{{ selected_profile }}">
```

In `tuner.js`, get the profile name from the DOM:
```javascript
const TUNER_PROFILE = document.querySelector('[data-profile]')?.dataset.profile;
```

And replace all `{{ selected_profile }}` references with `TUNER_PROFILE`.

The full `tuner.js` content (all functions: `simulate`, `showError`, `renderResults`, `collectRules`, `addRuleRow`, `saveProfile`) should be extracted as-is, with the template variable replacement above.

- [ ] **Step 2: Create profile-form.js with shared functions**

Create `dashboard/static/js/profile-form.js` with the `showErrors` and `addRule`/`removeRow`/`collectRules` functions shared between `profile_create.html` and `profile_edit.html`:

```javascript
/**
 * Display error messages in a container.
 * @param {string} containerId
 * @param {string[]} errors
 */
function showErrors(containerId, errors) {
    var container = document.getElementById(containerId);
    while (container.firstChild) container.removeChild(container.firstChild);
    if (!errors || !errors.length) return;
    var wrapper = document.createElement('div');
    wrapper.className = 'bg-error-container/20 text-error rounded-card p-4 text-sm';
    errors.forEach(function(e) {
        var item = document.createElement('div');
        item.textContent = '\u2022 ' + e;
        wrapper.appendChild(item);
    });
    container.appendChild(wrapper);
}

/**
 * Add a keyword/points rule row to a list container.
 * @param {string} listId - ID of the container element
 * @param {string} [key] - Pre-filled keyword
 * @param {string} [val] - Pre-filled points value
 */
function addRule(listId, key, val) {
    var list = document.getElementById(listId);
    var row = document.createElement('div');
    row.className = 'flex items-center gap-2 rule-row';

    var keyInput = document.createElement('input');
    keyInput.type = 'text';
    keyInput.placeholder = 'keyword';
    keyInput.value = key || '';
    keyInput.className = 'rule-key flex-1 px-3 py-2 rounded-card border border-outline-variant bg-surface-container-lowest text-on-surface text-sm focus:outline-none focus:border-primary';

    var valInput = document.createElement('input');
    valInput.type = 'number';
    valInput.placeholder = 'points';
    valInput.value = val || '';
    valInput.className = 'rule-val w-24 px-3 py-2 rounded-card border border-outline-variant bg-surface-container-lowest text-on-surface text-sm focus:outline-none focus:border-primary';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'text-on-surface-variant hover:text-error transition-colors flex-shrink-0';
    btn.onclick = function() { removeRow(btn); };
    var icon = document.createElement('span');
    icon.className = 'material-symbols-outlined text-[18px]';
    icon.textContent = 'remove_circle';
    btn.appendChild(icon);

    row.appendChild(keyInput);
    row.appendChild(valInput);
    row.appendChild(btn);
    list.appendChild(row);
    keyInput.focus();
}

/**
 * Remove a rule row from the DOM.
 * @param {HTMLElement} btn - The remove button clicked
 */
function removeRow(btn) {
    var row = btn.closest('.rule-row');
    if (row) row.remove();
}

/**
 * Collect keyword/points rules from a list container.
 * @param {string} listId
 * @returns {Object<string, number>}
 */
function collectRulesFromList(listId) {
    var rules = {};
    var rows = document.querySelectorAll('#' + listId + ' .rule-row');
    rows.forEach(function(row) {
        var key = row.querySelector('.rule-key').value.trim();
        var val = parseInt(row.querySelector('.rule-val').value, 10);
        if (key) {
            rules[key] = isNaN(val) ? 0 : val;
        }
    });
    return rules;
}

/**
 * Split comma-separated string into trimmed array.
 * @param {string} str
 * @returns {string[]}
 */
function splitComma(str) {
    return str.split(',').map(function(s) { return s.trim(); }).filter(Boolean);
}
```

- [ ] **Step 3: Update template script blocks**

**`tuner.html`:** Replace lines 281-481 with:
```html
<script src="/static/js/tuner.js"></script>
```

**`profile_create.html`:** Replace lines 136-246 with:
```html
<script src="/static/js/profile-form.js"></script>
<script>
/* profile_create.html uses addRule as addScoreRule — alias it */
function addScoreRule(key, val) { addRule('score-rules-list', key, val); }

document.getElementById('create-form').addEventListener('submit', function(e) {
    e.preventDefault();
    var form = new FormData(this);
    var data = {
        name: form.get('name'),
        emoji: form.get('emoji') || '\ud83d\udd0d',
        budget: {min: parseInt(form.get('budget_min')), max: parseInt(form.get('budget_max'))},
        score_threshold: parseInt(form.get('score_threshold')),
        telegram: {
            topic_id: form.get('telegram_topic_id') ? parseInt(form.get('telegram_topic_id')) : null,
            max_alerts: parseInt(form.get('telegram_max_alerts')) || 5,
        },
        sources: {},
    };
    var alertThresh = form.get('score_threshold_alert');
    if (alertThresh) data.score_threshold_alert = parseInt(alertThresh);

    for (var pair of form.entries()) {
        if (pair[0].startsWith('source_') && !pair[0].endsWith('_url') && pair[1] === 'on') {
            var srcName = pair[0].replace('source_', '');
            var url = form.get('source_' + srcName + '_url');
            if (url) {
                if (srcName === 'rss') {
                    data.sources[srcName] = {feeds: [{url: url}]};
                } else {
                    data.sources[srcName] = {urls: [url]};
                }
            } else {
                data.sources[srcName] = {};
            }
        }
    }

    var keys = form.getAll('score_rule_key[]');
    var vals = form.getAll('score_rule_val[]');
    if (keys.length) {
        data.score_rules = {};
        keys.forEach(function(k, i) { if (k.trim()) data.score_rules[k.trim()] = parseInt(vals[i]) || 0; });
    }

    fetch('/api/profiles', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        body: JSON.stringify(data),
    })
    .then(function(resp) { return resp.json(); })
    .then(function(result) {
        if (result.errors) {
            showErrors('create-errors', result.errors);
        } else {
            location.href = '/profiles/' + data.name;
        }
    })
    .catch(function(err) {
        showErrors('create-errors', ['Create failed: ' + err.message]);
    });
});
</script>
```

**`profile_edit.html`:** Replace lines 177-283 with:
```html
<script src="/static/js/profile-form.js"></script>
<script>
document.getElementById('profile-form').addEventListener('submit', function(e) {
    e.preventDefault();
    var name = document.getElementById('field-name').value;
    var topicVal = document.getElementById('field-topic-id').value;
    var maxAlertsVal = document.getElementById('field-max-alerts').value;
    var body = {
        name: name,
        emoji: document.getElementById('field-emoji').value.trim() || '\ud83d\udd0d',
        budget: {
            min: parseInt(document.getElementById('field-budget-min').value, 10) || 0,
            max: parseInt(document.getElementById('field-budget-max').value, 10) || 0
        },
        currency: document.getElementById('field-currency').value.trim() || 'PLN',
        score_threshold: parseInt(document.getElementById('field-score-threshold').value, 10) || 0,
        score_threshold_alert: parseInt(document.getElementById('field-score-alert').value, 10) || 0,
        score_rules: collectRulesFromList('score-rules-list'),
        penalties: collectRulesFromList('penalties-list'),
        excluded_words: splitComma(document.getElementById('field-excluded').value),
        required_any: splitComma(document.getElementById('field-required').value),
        telegram: {
            topic_id: topicVal !== '' ? parseInt(topicVal, 10) : null,
            max_alerts: maxAlertsVal !== '' ? parseInt(maxAlertsVal, 10) : 5
        }
    };

    fetch('/api/profiles/' + encodeURIComponent(name), {
        method: 'PUT',
        headers: {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        body: JSON.stringify(body)
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
        if (data.ok) {
            window.location.href = '/profiles/' + encodeURIComponent(name);
        } else {
            showErrors('error-container', data.errors || ['Unknown error']);
        }
    })
    .catch(function(err) {
        showErrors('error-container', ['Network error: ' + err.message]);
    });
});
</script>
```

Note: `profile_edit.html` used `collectRules()` — now it's `collectRulesFromList()`. Update the `onclick` attributes in the template HTML too (the `addRule` calls in the template use `addRule('score-rules-list')` and `addRule('penalties-list')` which match the new shared function).

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_dashboard.py -v --tb=short 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add dashboard/static/js/tuner.js dashboard/static/js/profile-form.js dashboard/templates/tuner.html dashboard/templates/profile_create.html dashboard/templates/profile_edit.html
git commit -m "refactor(frontend): extract tuner and profile form JS to static files"
```

---

### Task 10: Create Jinja2 macro library

**Files:**
- Create: `dashboard/templates/macros.html`
- Modify: `dashboard/templates/deals.html` (metric cards)
- Modify: `dashboard/templates/deal_detail.html` (breadcrumb)
- Modify: `dashboard/templates/compare.html` (breadcrumb, empty state)
- Modify: `dashboard/templates/price_trends.html` (metric cards)
- Modify: `dashboard/templates/health.html` (metric cards)
- Modify: `dashboard/templates/watchlist.html` (empty state)
- Modify: `dashboard/templates/profile_create.html` (breadcrumb)
- Modify: `dashboard/templates/profile_edit.html` (breadcrumb)
- Modify: `dashboard/templates/profiles.html` (empty state)
- Modify: `dashboard/templates/tuner.html` (empty state)

- [ ] **Step 1: Create macros.html**

Create `dashboard/templates/macros.html`:

```jinja2
{# ── Metric Card ── #}
{% macro metric_card(icon, label, value, icon_color="text-primary") %}
<div class="bg-surface-container-low rounded-card p-6">
    <div class="flex items-start gap-3">
        <span class="material-symbols-outlined {{ icon_color }} text-[28px]">{{ icon }}</span>
        <div>
            <p class="text-xs font-label text-on-surface-variant uppercase tracking-wider mb-1">{{ label }}</p>
            <p class="font-headline text-2xl font-bold text-on-surface">{{ value }}</p>
        </div>
    </div>
</div>
{% endmacro %}

{# ── Breadcrumb ── #}
{% macro breadcrumb(items) %}
<div class="flex items-center gap-2 text-sm font-label text-on-surface-variant min-w-0">
    {% for item in items %}
        {% if not loop.last %}
            <a href="{{ item.href }}" class="hover:text-primary transition-colors flex-shrink-0">{{ item.label }}</a>
            <span class="material-symbols-outlined text-[16px] flex-shrink-0">chevron_right</span>
        {% else %}
            <span class="text-on-surface truncate">{{ item.label }}</span>
        {% endif %}
    {% endfor %}
</div>
{% endmacro %}

{# ── Empty State ── #}
{% macro empty_state(icon, title, description="", action_href="", action_label="") %}
<div class="bg-surface-container-low rounded-card p-12 text-center">
    <span class="material-symbols-outlined text-[48px] text-outline-variant mb-4 block">{{ icon }}</span>
    <h2 class="font-headline text-lg font-semibold text-on-surface mb-2">{{ title }}</h2>
    {% if description %}
    <p class="text-sm text-on-surface-variant mb-4">{{ description }}</p>
    {% endif %}
    {% if action_href %}
    <a href="{{ action_href }}"
       class="inline-flex items-center gap-2 px-4 py-2.5 bg-primary text-on-primary rounded-card text-sm font-medium hover:bg-primary-dim transition-colors">
        {{ action_label }}
    </a>
    {% endif %}
</div>
{% endmacro %}

{# ── Status Badge ── #}
{% macro status_badge(status) %}
{% if status == 'watching' %}
    <span class="text-xs font-label px-2.5 py-1 rounded-full bg-primary-container text-primary font-medium">Watching</span>
{% elif status == 'rejected' %}
    <span class="text-xs font-label px-2.5 py-1 rounded-full bg-error-container/30 text-error font-medium">Rejected</span>
{% else %}
    <span class="text-xs font-label px-2.5 py-1 rounded-full bg-tertiary-container/30 text-tertiary font-medium">Active</span>
{% endif %}
{% endmacro %}

{# ── Score Display ── #}
{% macro score_display(score, size="text-lg") %}
{% if score is not none %}
    {% if score >= 70 %}
        <span class="font-headline font-bold text-tertiary {{ size }}">{{ score }}</span>
    {% elif score >= 40 %}
        <span class="font-headline font-bold text-[#b8860b] {{ size }}">{{ score }}</span>
    {% else %}
        <span class="font-headline font-bold text-error {{ size }}">{{ score }}</span>
    {% endif %}
{% else %}
    <span class="text-sm text-on-surface-variant">&mdash;</span>
{% endif %}
{% endmacro %}

{# ── Section Card ── #}
{% macro section_card(title, icon="") %}
<div class="bg-surface-container-low rounded-card p-6">
    {% if icon %}
    <div class="flex items-center gap-2 mb-4">
        <span class="material-symbols-outlined text-primary text-[20px]">{{ icon }}</span>
        <h3 class="font-headline text-base font-semibold">{{ title }}</h3>
    </div>
    {% else %}
    <h2 class="font-headline text-lg font-semibold text-on-surface mb-4">{{ title }}</h2>
    {% endif %}
    {{ caller() }}
</div>
{% endmacro %}
```

- [ ] **Step 2: Apply metric_card macro to deals.html**

At the top of `deals.html` (after `{% block content %}`), add:
```jinja2
{% from "macros.html" import metric_card %}
```

Replace lines 8-52 (the 4 metric cards) with:
```jinja2
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
    {{ metric_card("inventory_2", "Total Deals", total_deals) }}
    {{ metric_card("trending_up", "Score " ~ score_threshold ~ "+", high_score_pct ~ "%", "text-tertiary") }}
    {{ metric_card("new_releases", "New Today", new_today) }}
    {{ metric_card("price_change", "Price Drops (7d)", drops_count, "text-error") }}
</div>
```

- [ ] **Step 3: Apply breadcrumb macro to deal_detail.html**

Add import and replace lines 4-10:
```jinja2
{% from "macros.html" import breadcrumb, status_badge, score_display %}
```

Replace the page_title block:
```jinja2
{% block page_title %}
{{ breadcrumb([
    {"href": "/deals", "label": "Deals Explorer"},
    {"label": deal.title[:60] ~ ("..." if deal.title|length > 60 else "")}
]) }}
{% endblock %}
```

- [ ] **Step 4: Apply macros to compare.html**

Add import and replace breadcrumb (lines 4-10) and empty state (lines 13-24):
```jinja2
{% from "macros.html" import breadcrumb, empty_state, status_badge, score_display %}
```

Breadcrumb:
```jinja2
{% block page_title %}
{{ breadcrumb([{"href": "/deals", "label": "Deals Explorer"}, {"label": "Compare"}]) }}
{% endblock %}
```

Empty state:
```jinja2
{% if not deals %}
{{ empty_state("compare_arrows", "No Deals to Compare", "Select deals from the Deals Explorer to compare them side by side.", "/deals", "Back to Deals") }}
{% else %}
```

- [ ] **Step 5: Apply macros to remaining templates**

**`watchlist.html`:** Replace lines 59-63 empty state with:
```jinja2
{% from "macros.html" import empty_state %}
...
{{ empty_state("bookmark_border", "No watchlist items", "Set target prices on deal pages to start tracking.") }}
```

**`profile_create.html`:** Replace breadcrumb block with:
```jinja2
{% from "macros.html" import breadcrumb %}
{% block page_title %}
{{ breadcrumb([{"href": "/profiles", "label": "Profiles"}, {"label": "New Profile"}]) }}
{% endblock %}
```

**`profile_edit.html`:** Replace breadcrumb block with:
```jinja2
{% from "macros.html" import breadcrumb %}
{% block page_title %}
{{ breadcrumb([
    {"href": "/profiles", "label": "Profiles"},
    {"href": "/profiles/" ~ profile.name, "label": profile.emoji ~ " " ~ profile.name},
    {"label": "Edit"}
]) }}
{% endblock %}
```

**`tuner.html`:** Replace empty state (lines 27-35) with:
```jinja2
{% from "macros.html" import empty_state %}
...
{{ empty_state("labs", "No profiles found", "Create a profile first to use the Scoring Tuner.", "/profiles/new", "Create Profile") }}
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_dashboard.py -v --tb=short 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add dashboard/templates/macros.html dashboard/templates/deals.html dashboard/templates/deal_detail.html dashboard/templates/compare.html dashboard/templates/watchlist.html dashboard/templates/profile_create.html dashboard/templates/profile_edit.html dashboard/templates/tuner.html
git commit -m "refactor(frontend): create Jinja2 macro library, apply to all templates"
```

---

### Task 11: Move inline HTML from dashboard.py to partial template

**Files:**
- Create: `dashboard/templates/partials/deal_action_buttons.html`
- Modify: `dashboard.py:332-352`

- [ ] **Step 1: Create the partial template**

Create `dashboard/templates/partials/deal_action_buttons.html`:

```jinja2
{% from "macros.html" import status_badge %}
<a href="{{ deal_link }}" target="_blank" rel="noopener noreferrer"
   class="inline-flex items-center gap-2 px-4 py-2.5 bg-primary text-on-primary rounded-card text-sm font-medium hover:bg-primary-dim transition-colors">
    <span class="material-symbols-outlined text-[18px]">open_in_new</span>Open Link</a>
<button hx-post="/api/deals/{{ deal_id_encoded }}/status" hx-vals='{"status": "watching"}'
        hx-target="#action-buttons" hx-swap="innerHTML"
        class="inline-flex items-center gap-2 px-4 py-2.5 bg-surface-container-high text-on-surface rounded-card text-sm font-medium hover:bg-surface-container-highest transition-colors">
    <span class="material-symbols-outlined text-[18px]">visibility</span>Watch</button>
<button hx-post="/api/deals/{{ deal_id_encoded }}/status" hx-vals='{"status": "rejected"}'
        hx-target="#action-buttons" hx-swap="innerHTML"
        class="inline-flex items-center gap-2 px-4 py-2.5 bg-surface-container-high text-on-surface-variant rounded-card text-sm font-medium hover:bg-error-container/20 hover:text-error transition-colors">
    <span class="material-symbols-outlined text-[18px]">block</span>Skip</button>
{{ status_badge(current_status) }}
```

- [ ] **Step 2: Update api_update_deal_status in dashboard.py**

Replace lines 327-352 in `dashboard.py` (the inline HTML generation) with:

```python
    # Return HTML fragment for HTMX swap
    deal = db.get_deal(deal_id)
    link = deal["link"] if deal else "#"
    encoded_id = deal_id.replace(":", "%3A")

    return templates.TemplateResponse(
        "partials/deal_action_buttons.html",
        {
            "request": request,
            "deal_link": link,
            "deal_id_encoded": encoded_id,
            "current_status": status,
        },
    )
```

Also add `request: Request` to the function signature if not already there (it's not — line 317 needs it added).

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_dashboard.py -v --tb=short 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard/templates/partials/deal_action_buttons.html dashboard.py
git commit -m "refactor(frontend): move inline HTML from api_update_deal_status to partial template"
```

---

## Phase 4: Backend Architecture — Separation of Concerns

### Task 12: Add batch price history method to SQLiteStorage

**Files:**
- Modify: `storage/sqlite.py`
- Create: `tests/test_batch_queries.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_batch_queries.py`:

```python
"""Tests for batch query methods in SQLiteStorage."""

from storage.sqlite import SQLiteStorage


def test_get_price_histories_batch(tmp_path):
    db = SQLiteStorage(tmp_path / "test.db")
    try:
        # Insert test deals
        from sources.base import Deal

        deal1 = Deal(id="test:1", title="Deal 1", price=100, link="", source="test",
                     description="", temperature=0, image_url="", published_at="")
        deal2 = Deal(id="test:2", title="Deal 2", price=200, link="", source="test",
                     description="", temperature=0, image_url="", published_at="")
        db.upsert_deal(deal1, "test_profile", 50)
        db.upsert_deal(deal2, "test_profile", 60)

        # Record some prices
        db.record_price("test:1", 100)
        db.record_price("test:1", 90)
        db.record_price("test:2", 200)

        result = db.get_price_histories_batch(["test:1", "test:2", "test:nonexistent"])

        assert "test:1" in result
        assert "test:2" in result
        assert "test:nonexistent" in result
        assert len(result["test:1"]) == 2
        assert len(result["test:2"]) == 1
        assert len(result["test:nonexistent"]) == 0
    finally:
        db.close()


def test_get_price_histories_batch_empty(tmp_path):
    db = SQLiteStorage(tmp_path / "test.db")
    try:
        result = db.get_price_histories_batch([])
        assert result == {}
    finally:
        db.close()


def test_get_lowest_prices_batch(tmp_path):
    db = SQLiteStorage(tmp_path / "test.db")
    try:
        from sources.base import Deal

        deal1 = Deal(id="test:1", title="Deal 1", price=100, link="", source="test",
                     description="", temperature=0, image_url="", published_at="")
        db.upsert_deal(deal1, "test_profile", 50)
        db.record_price("test:1", 100)
        db.record_price("test:1", 80)
        db.record_price("test:1", 90)

        result = db.get_lowest_prices_batch(["test:1", "test:nonexistent"])
        assert result["test:1"] == 80
        assert result["test:nonexistent"] is None
    finally:
        db.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_batch_queries.py -v 2>&1 | tail -10`
Expected: FAIL — `get_price_histories_batch` and `get_lowest_prices_batch` don't exist.

- [ ] **Step 3: Implement batch methods in storage/sqlite.py**

Add to the `SQLiteStorage` class:

```python
    def get_price_histories_batch(self, deal_ids: list[str]) -> dict[str, list[dict]]:
        """Fetch price history for multiple deals in one query."""
        if not deal_ids:
            return {}
        result: dict[str, list[dict]] = {did: [] for did in deal_ids}
        try:
            placeholders = ",".join("?" for _ in deal_ids)
            rows = self._conn.execute(
                f"SELECT * FROM price_history WHERE deal_id IN ({placeholders}) ORDER BY recorded_at",
                deal_ids,
            ).fetchall()
            for row in rows:
                result[row["deal_id"]].append(dict(row))
        except sqlite3.Error as e:
            logger.error(f"Failed to batch get price histories: {e}")
        return result

    def get_lowest_prices_batch(self, deal_ids: list[str]) -> dict[str, int | None]:
        """Fetch lowest price for multiple deals in one query."""
        if not deal_ids:
            return {}
        result: dict[str, int | None] = {did: None for did in deal_ids}
        try:
            placeholders = ",".join("?" for _ in deal_ids)
            rows = self._conn.execute(
                f"SELECT deal_id, MIN(price) as lowest FROM price_history WHERE deal_id IN ({placeholders}) GROUP BY deal_id",
                deal_ids,
            ).fetchall()
            for row in rows:
                result[row["deal_id"]] = int(row["lowest"])
        except sqlite3.Error as e:
            logger.error(f"Failed to batch get lowest prices: {e}")
        return result
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_batch_queries.py -v 2>&1`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add storage/sqlite.py tests/test_batch_queries.py
git commit -m "feat: add batch price history and lowest price query methods to SQLiteStorage"
```

---

### Task 13: Fix N+1 in compare_deals route

**Files:**
- Modify: `dashboard.py:277-296`

- [ ] **Step 1: Replace per-deal loops with batch queries**

In `dashboard.py`, replace the `compare_deals` function body (lines 278-296) with:

```python
async def compare_deals(request: Request, ids: str = "", db: SQLiteStorage = Depends(get_db)):
    deal_ids = [i.strip() for i in ids.split(",") if i.strip()] if ids else []
    deal_ids = deal_ids[:5]  # max 5
    deals = db.get_deals_by_ids(deal_ids) if deal_ids else []
    id_list = [d["id"] for d in deals]
    price_histories = db.get_price_histories_batch(id_list)
    lowest_prices = db.get_lowest_prices_batch(id_list)
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
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_dashboard.py -v -k compare 2>&1`
Expected: Compare tests pass.

- [ ] **Step 3: Commit**

```bash
git add dashboard.py
git commit -m "perf: fix N+1 query in compare_deals using batch methods"
```

---

### Task 14: Create dashboard service layer

**Files:**
- Create: `dashboard/services.py`
- Modify: `dashboard.py` (thin routes delegate to service)

- [ ] **Step 1: Create dashboard/services.py**

Create `dashboard/services.py`:

```python
"""Business logic for the Deal Hunter dashboard, decoupled from HTTP routing."""

from storage.sqlite import SQLiteStorage

DEALS_PER_PAGE = 50
SCORE_THRESHOLD = 70


class DealService:
    """Encapsulates deal-related business logic."""

    def __init__(self, db: SQLiteStorage) -> None:
        self.db = db

    def get_comparison_data(self, deal_ids: list[str]) -> dict:
        """Batch-fetch deals, price histories, and lowest prices."""
        deal_ids = deal_ids[:5]
        deals = self.db.get_deals_by_ids(deal_ids) if deal_ids else []
        id_list = [d["id"] for d in deals]
        return {
            "deals": deals,
            "price_histories": self.db.get_price_histories_batch(id_list),
            "lowest_prices": self.db.get_lowest_prices_batch(id_list),
        }

    def score_deals_with_profile(self, deals: list[dict], profile_data: dict) -> list[dict]:
        """Score a list of deal dicts using the given profile config."""
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
```

- [ ] **Step 2: Update dashboard.py to use DealService**

At the top of `dashboard.py`, add:
```python
from dashboard.services import DealService
```

Replace `compare_deals` to use the service:
```python
async def compare_deals(request: Request, ids: str = "", db: SQLiteStorage = Depends(get_db)):
    deal_ids = [i.strip() for i in ids.split(",") if i.strip()] if ids else []
    data = DealService(db).get_comparison_data(deal_ids)
    return templates.TemplateResponse(
        request,
        "compare.html",
        {"active_page": "deals", **data},
    )
```

Replace `_score_deals_with_profile` usage in `tuner_profile` and `tuner_simulate`:
```python
    scored = DealService(db).score_deals_with_profile(deals, profile_data)
```

Remove the standalone `_score_deals_with_profile` function (lines 664-695) from `dashboard.py`.

Remove the `DEALS_PER_PAGE` and `SCORE_THRESHOLD` constants from `dashboard.py` top level and import from services:
```python
from dashboard.services import DealService, DEALS_PER_PAGE, SCORE_THRESHOLD
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_dashboard.py -v --tb=short 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard/services.py dashboard.py
git commit -m "refactor: extract business logic from dashboard routes to service layer"
```

---

### Task 15: Add DB context manager to feedback_bot.py

**Files:**
- Modify: `feedback_bot.py`

- [ ] **Step 1: Replace try/finally blocks with context manager**

The `get_storage()` function (line 37-39) already exists but returns a raw instance. Since `SQLiteStorage` already supports `__enter__`/`__exit__` (lines 82-87 of sqlite.py), the handlers should use `with` statements.

Replace the handlers that use try/finally with `with` blocks:

**`handle_callback` (lines 62-77):**
```python
    with get_storage() as storage:
        status = "watching" if action == "watch" else "rejected"
        found = storage.update_deal_status(deal_id, status)
        if not found:
            await query.answer("Nie znaleziono oferty w bazie")
            return
        storage.record_feedback(deal_id, action)
        if action == "watch":
            await query.answer("\u2b50 Dodano do obserwowanych")
        else:
            await query.answer("\U0001f44e Pominięto")
```

**`cmd_watch` (lines 90-101):**
```python
    with get_storage() as storage:
        found = storage.update_deal_status(deal_id, "watching")
        if not found:
            await update.message.reply_text(f"Nie znaleziono oferty: {html.escape(deal_id)}")
            return
        storage.record_feedback(deal_id, "watch")
        await update.message.reply_text(f"\u2b50 Oferta {html.escape(deal_id)} dodana do obserwowanych")
```

**`cmd_skip` (lines 111-120):**
```python
    with get_storage() as storage:
        found = storage.update_deal_status(deal_id, "rejected")
        if not found:
            await update.message.reply_text(f"Nie znaleziono oferty: {html.escape(deal_id)}")
            return
        storage.record_feedback(deal_id, "skip")
        await update.message.reply_text(f"\U0001f44e Oferta {html.escape(deal_id)} pominięta")
```

**`cmd_status` (lines 125-144):**
```python
    with get_storage() as storage:
        stats = storage.get_feedback_stats()
        watching = len(storage.get_deals_by_status("watching", limit=10000))
        rejected = len(storage.get_deals_by_status("rejected", limit=10000))
        total = len(storage.get_deals())
        # ... rest of message building and reply
```

**`cmd_watchlist` (lines 185-209):**
```python
    with get_storage() as storage:
        deals = storage.get_deals_by_status("watching", limit=20)
        # ... rest of message building and reply
```

Note: `cmd_target` (line 167) already uses `with get_storage() as db:` — no change needed.

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_feedback_bot.py -v --tb=short 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add feedback_bot.py
git commit -m "refactor: replace try/finally DB pattern in feedback_bot with context manager"
```

---

### Task 16: Fix async/sync inconsistency in dashboard routes

**Files:**
- Modify: `dashboard.py`

- [ ] **Step 1: Audit and fix async/sync**

Routes that should be sync `def` (they do synchronous I/O, FastAPI runs them in threadpool):
- `deals_page` (line 77) — currently `def` ✓
- `health_page` (line 178) — currently `def` ✓
- `price_trends_page` (line 207) — currently `def` ✓
- `deal_detail_page` (line 252) — currently `def` ✓
- `api_price_history` (line 300) — currently `def` ✓
- `api_update_deal_status` (line 317) — currently `def` ✓
- `api_deals` (line 356) — currently `def` ✓
- `api_stats` (line 374) — currently `def` ✓

Routes that use `async def` but should be `def` (they never `await` anything... actually check each):
- `compare_deals` (line 278) — `async def` but doesn't await → change to `def`
- `watchlist_page` (line 387) — `async def` but doesn't await → change to `def`
- `profiles_page` (line 422) — `async def` but doesn't await → change to `def`
- `profile_detail_page` (line 541) — `async def` but doesn't await → change to `def`
- `profile_edit_page` (line 554) — `async def` but doesn't await → change to `def`
- `tuner_index` (line 699) — `async def` but doesn't await → change to `def`
- `tuner_profile` (line 715) — `async def` but doesn't await → change to `def`
- `api_profiles_list` (line 811) — `async def` but doesn't await → change to `def`

Routes that correctly use `async def` (they `await request.form()`, `request.json()`, or `request.body()`):
- `add_to_watchlist_api` (line 398) — awaits `request.form()` ✓
- `remove_from_watchlist_api` (line 412) — no await but simple DELETE, can be `def`
- `profile_yaml_page` (line 448) — no await → change to `def`
- `api_update_profile_yaml` (line 461) — awaits `request.body()` ✓
- `profile_create_page` (line 493) — no await → change to `def`
- `api_create_profile` (line 506) — awaits `request.json()` ✓
- `api_update_profile` (line 569) — awaits `request.json()` ✓
- `api_delete_profile` (line 601) — no await → change to `def`
- `api_toggle_profile` (line 611) — no await → change to `def`
- `api_run_profile` (line 631) — no await → change to `def`
- `tuner_simulate` (line 737) — awaits `request.json()` ✓
- `tuner_save` (line 776) — awaits `request.json()` ✓

Change all identified `async def` to `def` where there's no `await`.

- [ ] **Step 2: Run tests**

Run: `pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add dashboard.py
git commit -m "refactor: fix async/sync inconsistency in dashboard routes"
```

---

## Phase 5: Directory Structure Reorganization

### Task 17: Split dashboard.py into route modules

**Files:**
- Create: `dashboard/routes/__init__.py`
- Create: `dashboard/routes/deals.py`
- Create: `dashboard/routes/profiles.py`
- Create: `dashboard/routes/watchlist.py`
- Create: `dashboard/routes/tuner.py`
- Create: `dashboard/routes/health.py`
- Create: `dashboard/dependencies.py`
- Modify: `dashboard.py` (slim down to app factory + mount)
- Modify: `tests/conftest.py` (update imports if needed)

This is a large task. The implementation should:

1. Move `get_db`, `safe_profile_path`, `safe_load_profile`, `_get_profiles` to `dashboard/dependencies.py`
2. Create an `APIRouter` in each route module
3. Move routes to the appropriate module by domain
4. `dashboard.py` becomes the app factory: creates `FastAPI`, mounts static, adds middleware, includes routers

- [ ] **Step 1: Create dashboard/dependencies.py**

```python
"""Shared dependencies for dashboard routes."""

import re
from pathlib import Path

from fastapi import HTTPException

from storage.sqlite import SQLiteStorage

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "state" / "deals.db"
PROFILES_DIR = BASE_DIR / "profiles"

_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def get_db():
    """FastAPI dependency: yields SQLiteStorage instance, closes after request."""
    db = SQLiteStorage(DB_PATH)
    try:
        yield db
    finally:
        db.close()


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


def get_profiles() -> list[str]:
    """Get available profile names."""
    try:
        from deal_hunter import list_profiles
        return sorted(list_profiles())
    except Exception:
        return []
```

- [ ] **Step 2: Create route modules with APIRouter**

Create `dashboard/routes/__init__.py` (empty).

Create `dashboard/routes/deals.py` — move `deals_page`, `deal_detail_page`, `compare_deals`, `api_deals`, `api_stats`, `api_price_history`, `api_update_deal_status` here.

Create `dashboard/routes/profiles.py` — move all `/profiles/*` and `/api/profiles/*` endpoints here.

Create `dashboard/routes/watchlist.py` — move `watchlist_page`, `add_to_watchlist_api`, `remove_from_watchlist_api` here.

Create `dashboard/routes/tuner.py` — move `tuner_index`, `tuner_profile`, `tuner_simulate`, `tuner_save` here.

Create `dashboard/routes/health.py` — move `health_page` here.

Each module uses `APIRouter`:
```python
from fastapi import APIRouter, Depends, Request
from dashboard.dependencies import get_db, safe_profile_path, safe_load_profile, get_profiles

router = APIRouter()

@router.get("/deals")
def deals_page(...):
    ...
```

- [ ] **Step 3: Slim down dashboard.py to app factory**

```python
"""Deal Hunter Web Dashboard — FastAPI application."""

import importlib.metadata
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from dashboard.routes import deals, profiles, watchlist, tuner, health

BASE_DIR = Path(__file__).parent

try:
    APP_VERSION = importlib.metadata.version("deal-hunter")
except importlib.metadata.PackageNotFoundError:
    from deal_hunter import __version__
    APP_VERSION = __version__

app = FastAPI(title="Deal Hunter Dashboard", version=APP_VERSION)

# Static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "dashboard" / "static")), name="static")

# Templates
templates = Jinja2Templates(directory=str(BASE_DIR / "dashboard" / "templates"))
templates.env.autoescape = True


def format_pln(value: int | None) -> str:
    if value is None or value == 0:
        return "0 zl"
    formatted = f"{value:,}".replace(",", " ")
    return f"{formatted} zl"


templates.env.filters["format_pln"] = format_pln
templates.env.globals["app_version"] = APP_VERSION


# CSRF middleware
@app.middleware("http")
async def csrf_check(request: Request, call_next):
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if not request.headers.get("HX-Request") and not request.headers.get("X-Requested-With"):
            return JSONResponse(status_code=403, content={"detail": "CSRF check failed"})
    return await call_next(request)


# Routes
app.include_router(deals.router)
app.include_router(profiles.router)
app.include_router(watchlist.router)
app.include_router(tuner.router)
app.include_router(health.router)


@app.get("/")
def index():
    return RedirectResponse(url="/deals", status_code=302)
```

Each route module needs access to `templates`. Options:
- Pass `templates` as a module-level import from dashboard.py
- Create a shared `dashboard/config.py` with templates setup

The cleanest approach: each route module imports `templates` from the main `dashboard` module:
```python
from dashboard import templates
```

- [ ] **Step 4: Update test imports**

Review `tests/conftest.py` — the `TestClient` fixture imports `app` from `dashboard`. This should continue to work since `dashboard.py` still exports `app`.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add dashboard/ tests/conftest.py
git commit -m "refactor: split dashboard.py into route modules with APIRouter"
```

---

## Phase 6: Polish

### Task 18: Add environment validation on startup

**Files:**
- Modify: `deal_hunter.py`

- [ ] **Step 1: Add validate_environment function**

Add near the top of `deal_hunter.py`, after the dotenv loading:

```python
def validate_environment() -> None:
    """Check required environment variables and warn about missing ones."""
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        logger.warning("Missing env vars: %s — Telegram alerts will be disabled", ", ".join(missing))
```

Call it from `main()` before processing commands.

- [ ] **Step 2: Run tests**

Run: `pytest tests/ -v --tb=short 2>&1 | tail -10`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add deal_hunter.py
git commit -m "feat: add environment variable validation on startup"
```

---

### Task 19: Dead code audit

**Files:**
- Various

- [ ] **Step 1: Run Ruff for unused variables**

Run: `ruff check . --select F841,F811 2>&1`

Fix any findings.

- [ ] **Step 2: Check for unused imports**

Run: `ruff check . --select F401 2>&1`

Fix any findings.

- [ ] **Step 3: Run full test suite one final time**

Run: `pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: dead code cleanup after refactoring"
```

---

## Summary

| Task | Phase | What |
|------|-------|------|
| 1 | 1 | Tighten deps, ruff, mypy, gitignore |
| 2 | 1 | Dockerfile HEALTHCHECK |
| 3 | 2 | Path traversal protection |
| 4 | 2 | CSRF middleware |
| 5 | 2 | Explicit autoescape |
| 6 | 3 | Static dir + sidebar JS |
| 7 | 3 | Compare bar JS |
| 8 | 3 | Chart.js helpers |
| 9 | 3 | Tuner + profile form JS |
| 10 | 3 | Jinja2 macros |
| 11 | 3 | Inline HTML to partial |
| 12 | 4 | Batch SQLite methods |
| 13 | 4 | Fix N+1 in compare |
| 14 | 4 | Service layer |
| 15 | 4 | Feedback bot context manager |
| 16 | 4 | Async/sync fix |
| 17 | 5 | Route module split |
| 18 | 6 | Env validation |
| 19 | 6 | Dead code audit |

# Wave 3: Profile Management (C.4) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Full CRUD for profiles via the web dashboard. Zero SSH, zero editor needed. Browse, create, edit (form + raw YAML), delete, and manually trigger profiles.

**Architecture:** Extends `dashboard.py` with ~15 new routes. New templates for profiles list, detail, form editor, YAML editor, and create wizard. File system reads/writes for profile YAML files.

**Tech Stack:** Python 3.12+, FastAPI, Jinja2/HTMX, PyYAML, CodeMirror (CDN), pytest

**Security notes:** All HTML templates use Jinja2 auto-escaping. JavaScript error display uses `textContent` instead of `innerHTML` to prevent XSS. Server-side validation via `validate_profile()` before any file write.

---

## File Structure

- Modify: `dashboard.py` — ~15 new routes for profile CRUD
- Modify: `dashboard/templates/base.html` — add Profiles to sidebar
- Create: `dashboard/templates/profiles.html` — profile list/grid
- Create: `dashboard/templates/profile_detail.html` — read-only profile view
- Create: `dashboard/templates/profile_edit.html` — tabbed form editor
- Create: `dashboard/templates/profile_yaml.html` — raw YAML editor
- Create: `dashboard/templates/profile_create.html` — create wizard
- Modify: `tests/test_dashboard.py` — profile management tests

---

## Task 1: Sidebar + Profile List Page + API

Add Profiles link to sidebar nav, create profiles list page, add JSON API endpoint.

**Files:**
- Modify: `dashboard/templates/base.html` — add Profiles nav link after Watchlist, before System Health
- Create: `dashboard/templates/profiles.html` — card grid of profiles
- Modify: `dashboard.py` — add `GET /profiles` and `GET /api/profiles` routes
- Test: `tests/test_dashboard.py` — add TestProfilePages class

**Sidebar link** (add in base.html nav after Watchlist):
```html
<a href="/profiles" class="...{% if active_page == 'profiles' %}...{% endif %}">
    <span class="material-symbols-outlined text-[20px]">tune</span>
    Profiles
</a>
```

**Profiles page** shows a card grid. Each card: emoji, name, enabled badge, source count, budget range, score threshold. Links to `/profiles/{name}`.

**Routes:**
- `GET /profiles` → `profiles.html` with profile metadata list
- `GET /api/profiles` → JSON list of `{name, emoji, enabled, source_count}`

**Tests:** profiles page loads (200), sidebar has /profiles link, API returns JSON list.

---

## Task 2: Profile Detail Page (Read-Only)

**Files:**
- Create: `dashboard/templates/profile_detail.html` — read-only view of all profile sections
- Modify: `dashboard.py` — add `GET /profiles/{name}` route
- Test: `tests/test_dashboard.py`

**Template:** 4-card grid showing Basic Info (name, emoji, budget, currency), Scoring (threshold, rules, penalties), Sources (name + config JSON), Filters (excluded_words, required_any, telegram settings). Action buttons: Edit, Edit YAML, Run Now, Delete.

**Route:** `GET /profiles/{name}` → loads profile via `safe_load_profile()`, returns 404 if not found.

IMPORTANT: Route order matters — `/profiles/new` (Task 5) must be defined BEFORE `/profiles/{name}` to avoid "new" being treated as a profile name. Plan the route registration order accordingly.

**Tests:** detail page loads for existing profile, 404 for missing profile.

---

## Task 3: Profile Form Editor + Update API

**Files:**
- Create: `dashboard/templates/profile_edit.html` — tabbed form with JS submission
- Modify: `dashboard.py` — add `GET /profiles/{name}/edit` and `PUT /api/profiles/{name}` routes
- Test: `tests/test_dashboard.py`

**Template:** Form sections for Basic (name readonly, emoji, budget, currency), Scoring (thresholds, dynamic score_rules table with add/remove, penalties table), Filters (excluded_words and required_any as comma-separated inputs), Telegram (topic_id, max_alerts). Submit button sends JSON PUT to `/api/profiles/{name}`.

**Error display:** Create error list elements using `document.createElement()` and `textContent` (no innerHTML). Example pattern:
```javascript
const errDiv = document.getElementById('edit-errors');
errDiv.replaceChildren(); // clear
if (result.errors) {
    const container = document.createElement('div');
    container.className = 'bg-error-container/20 text-error rounded-card p-4 text-sm';
    result.errors.forEach(e => {
        const item = document.createElement('div');
        item.textContent = '• ' + e;
        container.appendChild(item);
    });
    errDiv.appendChild(container);
}
```

**Update API:** `PUT /api/profiles/{name}` accepts JSON body. Preserves existing `sources` if not in body (form doesn't edit sources — use YAML editor for that). Preserves `custom_filter`, `custom_data`, `price_tracking`, `quiet_hours`, `dedup` from existing profile. Validates via `validate_profile()`, saves with `yaml.dump()`.

**Tests:** edit page loads (200), PUT updates profile.

---

## Task 4: Raw YAML Editor

**Files:**
- Create: `dashboard/templates/profile_yaml.html` — CodeMirror editor (CDN)
- Modify: `dashboard.py` — add `GET /profiles/{name}/edit/yaml` and `PUT /api/profiles/{name}/yaml`
- Test: `tests/test_dashboard.py`

**Template:** CodeMirror v5 via CDN (codemirror.min.js + yaml mode + material-darker theme). Textarea pre-filled with raw YAML file content. Save button sends PUT with `Content-Type: text/plain`.

**YAML Update API:** `PUT /api/profiles/{name}/yaml` — receives raw YAML text, parses with `yaml.safe_load()`, validates with `validate_profile()`, writes original text to file (preserves comments/formatting).

**Error display:** Same safe DOM pattern as Task 3 (textContent, no innerHTML).

**Tests:** YAML editor page loads (200), response contains "CodeMirror" or "yaml".

---

## Task 5: Profile Create Page + API

**Files:**
- Create: `dashboard/templates/profile_create.html` — single-page create form
- Modify: `dashboard.py` — add `GET /profiles/new` and `POST /api/profiles`
- Test: `tests/test_dashboard.py`

IMPORTANT: Register `GET /profiles/new` BEFORE `GET /profiles/{name}` in dashboard.py.

**Template:** Similar to edit form but with all fields editable. Sources section: checkboxes for each available source from `SOURCE_REGISTRY`, with URL/query input per source. Name field with pattern validation (lowercase alphanumeric + hyphens + underscores).

**Create API:** `POST /api/profiles` — validates name format, checks file doesn't exist, validates profile, creates `profiles/{name}.yaml`, ensures profiles dir exists.

**Tests:** create page loads (200), POST creates profile (checks response.json() has ok=True).

---

## Task 6: Delete + Toggle + Manual Run

**Files:**
- Modify: `dashboard.py` — add DELETE, PATCH toggle, POST run routes
- Test: `tests/test_dashboard.py`

**Routes:**
- `DELETE /api/profiles/{name}` — unlinks profile YAML file, returns `{"ok": true}`
- `PATCH /api/profiles/{name}/toggle` — toggles `enabled` field in YAML, saves
- `POST /api/profiles/{name}/run` — runs `deal_hunter.py --profile {name} --verify` via `subprocess.run()` (timeout 120s), returns output as HTML pre block

**Run output:** Returned as an HTMX HTML fragment (pre-rendered server-side with Jinja2 escaping or `html.escape()`). No innerHTML in client JS.

**Tests:** DELETE removes profile, PATCH toggles, POST run returns 200.

---

## Task 7: Final Integration — Lint, Docs, Push

- Run full test suite: `./venv/bin/python -m pytest tests/ --tb=short -q`
- Lint/format: `./venv/bin/ruff check . --fix && ./venv/bin/ruff format .`
- Update CLAUDE.md: mention profile management in dashboard description
- Update ROADMAP-v2.md: mark C.4 as ✅ Done
- Commit and push

# Phase 4: Dashboard Route Cleanup & API Layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract business logic from dashboard route handlers into service classes, add return type annotations, and consolidate duplicate YAML persistence.

**Architecture:** Expand `dashboard/services.py` into a package with focused service classes. Route handlers become thin wrappers: parse params → call service → return response.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0, existing repository + service layers.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `dashboard/services/__init__.py` | Create | Package init, re-exports |
| `dashboard/services/deal_service.py` | Create | Deal listing, detail, stats, comparison |
| `dashboard/services/profile_service.py` | Create | Profile CRUD, YAML I/O, toggle, run |
| `dashboard/services/tuner_service.py` | Create | Scoring simulation/preview |
| `dashboard/services.py` | Delete | Replaced by services package |
| `dashboard/routes/deals.py` | Modify | Slim handlers using DealService |
| `dashboard/routes/profiles.py` | Modify | Slim handlers using ProfileService |
| `dashboard/routes/tuner.py` | Modify | Slim handlers using TunerService |
| `dashboard/routes/*.py` | Modify | Add return type annotations |
| `tests/test_dashboard.py` | Modify | Update any patches |

---

### Task 1: Dashboard Services Package Scaffold

**Files:**
- Create: `dashboard/services/__init__.py`
- Move: `dashboard/services.py` → `dashboard/services/deal_service.py`

- [ ] **Step 1: Create dashboard/services/ package**

Move existing `dashboard/services.py` (DealService class with comparison, sparklines, scoring) to `dashboard/services/deal_service.py`. Create `__init__.py` with re-exports. Update all imports.

- [ ] **Step 2: Run dashboard tests**
- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(dashboard): convert services.py to services package"
```

---

### Task 2: ProfileService — YAML CRUD

**Files:**
- Create: `dashboard/services/profile_service.py`
- Modify: `dashboard/routes/profiles.py`

- [ ] **Step 1: Create ProfileService**

Extract from `profiles.py` routes: YAML loading, saving, validation, field preservation, toggle enabled, delete, create, and run-profile subprocess logic.

- [ ] **Step 2: Slim profile route handlers**
- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "refactor(dashboard): extract ProfileService from profile routes"
```

---

### Task 3: TunerService — Scoring Simulation

**Files:**
- Create: `dashboard/services/tuner_service.py`
- Modify: `dashboard/routes/tuner.py`

- [ ] **Step 1: Create TunerService**

Extract simulation logic: merge profile config with form overrides, score deals, return results.

- [ ] **Step 2: Slim tuner route handlers**
- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "refactor(dashboard): extract TunerService from tuner routes"
```

---

### Task 4: Expand DealService — Deals Page Logic

**Files:**
- Modify: `dashboard/services/deal_service.py`
- Modify: `dashboard/routes/deals.py`

- [ ] **Step 1: Move filtering/pagination logic**

Extract from `deals_page` handler: filter parameter parsing, query building, pagination math, category aggregation, stats computation.

- [ ] **Step 2: Slim deals_page and _price_drops_view handlers**
- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "refactor(dashboard): move deals page logic to DealService"
```

---

### Task 5: Return Type Annotations

**Files:**
- Modify: `dashboard/routes/deals.py`
- Modify: `dashboard/routes/profiles.py`
- Modify: `dashboard/routes/tuner.py`
- Modify: `dashboard/routes/watchlist.py`
- Modify: `dashboard/routes/health.py`

- [ ] **Step 1: Add return types to all route handlers**

Add explicit return type annotations (HTMLResponse, JSONResponse, RedirectResponse, Response) to all 33 route handlers across 5 route files.

- [ ] **Step 2: Run tests + linters, commit**

```bash
git commit -m "refactor(dashboard): add return type annotations to all route handlers"
```

---

### Task 6: Delete old services.py + Final Cleanup

**Files:**
- Delete: `dashboard/services.py` (if not already removed in Task 1)
- Modify: `CLAUDE.md`

- [ ] **Step 1: Verify no old imports remain**
- [ ] **Step 2: Update CLAUDE.md**
- [ ] **Step 3: Run full test suite + linters, commit**

```bash
git commit -m "docs: update CLAUDE.md for Phase 4 dashboard service layer"
```

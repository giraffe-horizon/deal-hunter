# Phase 1: Tooling, Formatting & Environment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish consistent code formatting, strict linting, and environment variable hygiene as the baseline before any structural changes begin in Phase 2+.

**Architecture:** No structural changes. This phase tightens the existing Ruff and Mypy configuration, adds new lint rule sets (RET, SIM, PTH), fixes the ~42 resulting violations, makes two hardcoded constants configurable via env vars, and ensures the pre-commit hook covers the new rules. All 673 existing tests must still pass at the end.

**Tech Stack:** Ruff, Mypy, pre-commit, python-dotenv

**Spec:** `docs/superpowers/specs/2026-04-13-refactoring-cleanup-design.md` (Phase 1)

**Deferred from spec (intentionally):**
- `"ANN"` (type annotation) Ruff rules — 1,391 violations exist today. Adding before Phase 6 (when annotations are written) creates noise with no value. Will be enabled in Phase 6.
- `DATABASE_URL` env var — nothing reads it until Phase 2 creates the SQLAlchemy engine. Will be added in Phase 2 plan.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `pyproject.toml` | Ruff rules, Mypy overrides, new deps |
| Modify | `.pre-commit-config.yaml` | Add mypy hook |
| Modify | `.env.example` | Add new env vars |
| Modify | `dashboard/services.py` | Read constants from env |
| Modify | `dashboard/routes/deals.py` | Import updated constants |
| Modify | `deal_hunter.py` | Fix PTH123, SIM105, RET505 |
| Modify | `health.py` | Fix PTH123 |
| Modify | `sources/yaml_source.py` | Fix PTH123, SIM105 |
| Modify | `sources/rss.py` | Fix RET505 |
| Modify | `filters/bike_filter.py` | Fix RET505 |
| Modify | `notifiers/telegram.py` | Fix PTH123, RET505 |
| Modify | `dashboard/dependencies.py` | Fix PTH123 |
| Modify | `dashboard/routes/profiles.py` | Fix PTH123 |
| Modify | `utils/init_profile.py` | Fix PTH123 |
| Modify | `scripts/migrate_state_to_sqlite.py` | Fix PTH123 |
| Modify | `tests/test_charts.py` | Fix PTH123 |
| Modify | `tests/test_dashboard.py` | Fix PTH118, PTH120, PTH110, PTH108 |
| Modify | `tests/test_feedback_bot.py` | Fix SIM117 |
| Modify | `tests/test_rss_source.py` | Fix SIM117 |
| Modify | `tests/test_xkom_morele.py` | Fix SIM117 |
| Modify | `tests/test_yaml_source.py` | Fix SIM117 |

---

### Task 1: Update Ruff Configuration

**Files:**
- Modify: `pyproject.toml:74-83`

- [ ] **Step 1: Update Ruff lint rules in pyproject.toml**

Open `pyproject.toml` and replace the `[tool.ruff.lint]` section:

```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "S", "C90", "B", "A", "RET", "SIM", "PTH"]
ignore = ["S101", "B008", "C901"]
```

Changes:
- Added `"RET"` (superfluous else/elif after return), `"SIM"` (simplifiable constructs), `"PTH"` (use pathlib)
- Removed `"E501"` from ignore — `line-length = 100` is now enforced
- Kept `"S101"` (assert in tests), `"B008"` (function call in default arg — FastAPI Depends), `"C901"` (complexity)

- [ ] **Step 2: Verify the new rules detect violations**

Run: `ruff check --statistics 2>&1 | head -20`

Expected: ~42 errors across PTH123, SIM117, SIM105, RET505, PTH120, PTH118, PTH110, PTH108 (same as before, since these rules were already detected but not in the config's select list — they were being picked up via the existing broad E/F/W selectors running implicitly).

- [ ] **Step 3: Commit config change**

```bash
git add pyproject.toml
git commit -m "chore: tighten ruff lint rules — add RET, SIM, PTH; enforce line-length"
```

---

### Task 2: Fix Auto-Fixable Lint Violations

**Files:**
- Modify: `filters/bike_filter.py`, `sources/rss.py`, `notifiers/telegram.py`, `deal_hunter.py`
- Modify: `tests/test_feedback_bot.py`, `tests/test_yaml_source.py`

- [ ] **Step 1: Run ruff auto-fix**

```bash
ruff check --fix
```

This auto-fixes ~10 violations:
- `RET505`: 5x superfluous `else`/`elif` after `return` (bike_filter, rss, telegram, deal_hunter)
- `SIM117`: 5x of the nested `with` statements that are auto-fixable (test files)

- [ ] **Step 2: Run ruff format to ensure consistency**

```bash
ruff format
```

- [ ] **Step 3: Verify remaining violations**

Run: `ruff check --statistics 2>&1`

Expected: ~32 remaining errors (the non-auto-fixable ones: PTH123, SIM105, SIM117 non-fixable, PTH120, PTH118, PTH110, PTH108).

- [ ] **Step 4: Run tests to confirm nothing broke**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/ -x -q 2>&1 | tail -10`

Expected: All 673 tests pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "fix: apply ruff auto-fixes for RET505 and SIM117 violations"
```

---

### Task 3: Fix PTH123 Violations (builtin `open()` to `Path.open()`)

**Files:**
- Modify: `deal_hunter.py:151,178,337,352`
- Modify: `health.py:25,37`
- Modify: `sources/yaml_source.py:31,42`
- Modify: `notifiers/telegram.py:247`
- Modify: `dashboard/dependencies.py:44`
- Modify: `dashboard/routes/profiles.py:149,184,218,243,248`
- Modify: `utils/init_profile.py:312`
- Modify: `scripts/migrate_state_to_sqlite.py:40`
- Modify: `tests/test_charts.py:99`

These are all `open(filepath, ...)` calls that should use `Path(filepath).open(...)` or since most variables are already `Path` objects, just `filepath.open(...)`.

- [ ] **Step 1: Fix all PTH123 violations**

For each file, replace `open(path, mode)` with `path.open(mode)`. The pattern is always the same — the first argument is already a `Path` object in all cases.

Examples of the transformation:

```python
# Before
with open(state_file) as f:
# After
with state_file.open() as f:

# Before
with open(state_file, "w") as f:
# After
with state_file.open("w") as f:

# Before
with open(path, "rb") as f:
# After
with path.open("rb") as f:
```

Apply to all 18 PTH123 occurrences across the files listed above.

- [ ] **Step 2: Verify PTH123 violations are gone**

Run: `ruff check --select PTH123 2>&1`

Expected: No violations found (exit code 0 or "All checks passed!").

- [ ] **Step 3: Run tests**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/ -x -q 2>&1 | tail -10`

Expected: All 673 tests pass.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "fix: replace builtin open() with Path.open() (PTH123)"
```

---

### Task 4: Fix Remaining Lint Violations (SIM105, SIM117, PTH108/110/118/120)

**Files:**
- Modify: `deal_hunter.py:36` (SIM105)
- Modify: `sources/yaml_source.py:373` (SIM105)
- Modify: `tests/test_feedback_bot.py:211` (SIM117 — non-auto-fixable)
- Modify: `tests/test_rss_source.py:115,149,161` (SIM117)
- Modify: `tests/test_xkom_morele.py:36,192` (SIM117)
- Modify: `tests/test_yaml_source.py:849` (SIM117 — if not already fixed)
- Modify: `tests/test_dashboard.py:981-985` (PTH118, PTH120, PTH110, PTH108)

- [ ] **Step 1: Fix SIM105 — contextlib.suppress**

In `deal_hunter.py:36`, replace try/except/pass with contextlib.suppress:

```python
# Before
try:
    __version__ = importlib.metadata.version("deal-hunter")
except importlib.metadata.PackageNotFoundError:
    pass

# After
import contextlib

with contextlib.suppress(importlib.metadata.PackageNotFoundError):
    __version__ = importlib.metadata.version("deal-hunter")
```

In `sources/yaml_source.py:373`, apply the same pattern for the ValueError/TypeError suppress.

- [ ] **Step 2: Fix SIM117 — merge nested `with` statements**

For each non-auto-fixed SIM117, merge nested `with` into a single statement. Example:

```python
# Before
with patch("sources.rss.RssSource._fetch_page") as mock_fetch:
    with patch("sources.rss.RssSource._rate_limit"):
        ...

# After
with (
    patch("sources.rss.RssSource._fetch_page") as mock_fetch,
    patch("sources.rss.RssSource._rate_limit"),
):
    ...
```

Apply to all remaining SIM117 occurrences in test files.

- [ ] **Step 3: Fix PTH violations in test_dashboard.py**

```python
# Before (lines 981-985)
db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state", "deals.db")
if os.path.exists(db_path):
    os.unlink(db_path)

# After
db_path = Path(__file__).parent.parent / "state" / "deals.db"
if db_path.exists():
    db_path.unlink()
```

Add `from pathlib import Path` to the imports if not already present.

- [ ] **Step 4: Verify zero lint violations**

Run: `ruff check 2>&1`

Expected: "All checks passed!" or exit code 0.

- [ ] **Step 5: Run tests**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/ -x -q 2>&1 | tail -10`

Expected: All 673 tests pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "fix: resolve SIM105, SIM117, PTH108/110/118/120 lint violations"
```

---

### Task 5: Run Ruff Format Across Entire Codebase

**Files:**
- All `.py` files

- [ ] **Step 1: Run ruff format**

```bash
ruff format
```

- [ ] **Step 2: Check what changed**

```bash
git diff --stat
```

Expected: Formatting-only changes (quote style, trailing commas, line wrapping). No behavioral changes.

- [ ] **Step 3: Run tests**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/ -x -q 2>&1 | tail -10`

Expected: All 673 tests pass.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "style: run ruff format across entire codebase"
```

---

### Task 6: Update Mypy Configuration

**Files:**
- Modify: `pyproject.toml:85-93`

- [ ] **Step 1: Update mypy config in pyproject.toml**

Replace the `[tool.mypy]` section and overrides:

```toml
[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = false
disallow_untyped_defs = true

[[tool.mypy.overrides]]
module = ["telegram.*", "matplotlib.*", "rich.*"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["dashboard.routes.*", "tests.*"]
disallow_untyped_defs = false
```

Changes:
- Added `disallow_untyped_defs = true` globally
- Added override to relax it for `dashboard.routes.*` and `tests.*` (those get typed in Phase 4/6)

- [ ] **Step 2: Run mypy to see current state**

```bash
/home/liske/Projects/deal-hunter/venv/bin/python -m mypy storage/ filters/ sources/ health.py --no-error-summary 2>&1 | head -30
```

Review output. If there are errors in core modules, note them — they'll be addressed if non-trivial, or they may already be clean.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: enable mypy disallow_untyped_defs for core modules"
```

---

### Task 7: Update Pre-commit Configuration

**Files:**
- Modify: `.pre-commit-config.yaml`

- [ ] **Step 1: Update .pre-commit-config.yaml**

Replace the file content:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.11.6
    hooks:
      - id: ruff-format
      - id: ruff
        args: [--fix]
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.15.0
    hooks:
      - id: mypy
        additional_dependencies:
          - types-requests
          - types-beautifulsoup4
          - types-PyYAML
        args: [--ignore-missing-imports]
        stages: [pre-push]
```

Changes:
- Added mypy hook running on `pre-push` (not on every commit — it's slower)
- Included type stub dependencies so mypy can check against them

- [ ] **Step 2: Verify pre-commit runs clean**

```bash
pre-commit run --all-files 2>&1 | tail -10
```

Expected: ruff-format and ruff both pass. Mypy won't run (it's configured for pre-push stage only).

- [ ] **Step 3: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "chore: add mypy pre-push hook to pre-commit config"
```

---

### Task 8: Make DEALS_PER_PAGE and SCORE_THRESHOLD Configurable

**Files:**
- Modify: `dashboard/services.py:5-6`
- Modify: `.env.example`

- [ ] **Step 1: Write the test**

Create a test to verify the constants can be overridden via environment:

```python
# In tests/test_dashboard.py — add at the end of the file

def test_deals_per_page_env_override(monkeypatch):
    """DEALS_PER_PAGE reads from env var with fallback to 50."""
    monkeypatch.setenv("DEALS_PER_PAGE", "25")
    # Re-import to pick up env var
    import importlib
    import dashboard.services
    importlib.reload(dashboard.services)
    assert dashboard.services.DEALS_PER_PAGE == 25
    # Restore default
    monkeypatch.delenv("DEALS_PER_PAGE")
    importlib.reload(dashboard.services)
    assert dashboard.services.DEALS_PER_PAGE == 50


def test_score_threshold_env_override(monkeypatch):
    """SCORE_THRESHOLD reads from env var with fallback to 70."""
    monkeypatch.setenv("SCORE_THRESHOLD", "60")
    import importlib
    import dashboard.services
    importlib.reload(dashboard.services)
    assert dashboard.services.SCORE_THRESHOLD == 60
    # Restore default
    monkeypatch.delenv("SCORE_THRESHOLD")
    importlib.reload(dashboard.services)
    assert dashboard.services.SCORE_THRESHOLD == 70
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_dashboard.py::test_deals_per_page_env_override -v 2>&1 | tail -10`

Expected: FAIL — currently the constants are hardcoded and don't read from env.

- [ ] **Step 3: Update dashboard/services.py to read from env**

Replace lines 1-6 of `dashboard/services.py`:

```python
"""Business logic for the Deal Hunter dashboard, decoupled from HTTP routing."""

import os

from storage.sqlite import SQLiteStorage

DEALS_PER_PAGE = int(os.getenv("DEALS_PER_PAGE", "50"))
SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD", "70"))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_dashboard.py::test_deals_per_page_env_override tests/test_dashboard.py::test_score_threshold_env_override -v 2>&1 | tail -10`

Expected: Both PASS.

- [ ] **Step 5: Update .env.example**

Add to the end of `.env.example`:

```
# Dashboard settings (optional)
# DEALS_PER_PAGE=50
# SCORE_THRESHOLD=70
```

- [ ] **Step 6: Run full test suite**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/ -x -q 2>&1 | tail -10`

Expected: All tests pass (673+2 new = 675).

- [ ] **Step 7: Commit**

```bash
git add dashboard/services.py .env.example tests/test_dashboard.py
git commit -m "feat: make DEALS_PER_PAGE and SCORE_THRESHOLD configurable via env vars"
```

---

### Task 9: Add Phase 2 Dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml:26-35`

- [ ] **Step 1: Add sqlalchemy and alembic to dependencies**

Add to the `dependencies` list in `pyproject.toml`:

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
    "sqlalchemy>=2.0",
    "alembic>=1.13",
]
```

- [ ] **Step 2: Install the new dependencies**

```bash
/home/liske/Projects/deal-hunter/venv/bin/pip install sqlalchemy>=2.0 alembic>=1.13
```

- [ ] **Step 3: Verify import works**

```bash
/home/liske/Projects/deal-hunter/venv/bin/python -c "import sqlalchemy; print(sqlalchemy.__version__); import alembic; print(alembic.__version__)"
```

Expected: Version numbers printed (e.g., `2.0.x`, `1.13.x`).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add sqlalchemy and alembic dependencies for Phase 2"
```

---

### Task 10: Final Verification

- [ ] **Step 1: Run full lint check**

```bash
ruff check && ruff format --check
```

Expected: Both pass with zero errors.

- [ ] **Step 2: Run full test suite**

```bash
/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: All 675 tests pass.

- [ ] **Step 3: Verify git status is clean**

```bash
git status
```

Expected: Clean working tree.

- [ ] **Step 4: Log summary**

Phase 1 complete. Summary of changes:
- Ruff: Added RET, SIM, PTH rule sets; removed E501 from ignore; fixed all 42 violations
- Mypy: Enabled `disallow_untyped_defs` for core modules; relaxed for routes/tests
- Pre-commit: Added mypy on pre-push
- Dependencies: Pinned FastAPI/Uvicorn/Jinja2 versions, added sqlalchemy + alembic
- Environment: DEALS_PER_PAGE and SCORE_THRESHOLD now configurable via env vars
- All 675 tests pass, zero lint violations

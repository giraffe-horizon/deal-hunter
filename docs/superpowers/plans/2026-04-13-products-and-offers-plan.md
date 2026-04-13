# Products & Offers Implementation Plan (unified A1 + A2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Supersedes:** `docs/superpowers/plans/2026-04-13-phase-a1-rename-deals-to-offers.md`. Tasks 0–2 of that plan have already shipped in the `phase-a1-rename` worktree (commits `2e1cf04`, `bf9df9c`, `cdd7aba`); the A1 plan stays on disk as historical record but is NOT the execution target. Pick up from Task 1 below.

**Goal:** Take the refactor from "`deals` table renamed" to "`offers`/`price_points` with full product model (Product/ProductAlias/OfferPayloadHistory/DealEvent/MatchReview/MatchDecision/FxRate) and event emission on ingest" — across two Alembic revisions (`003` already landed, `004` to ship here).

**Architecture:** Strangler-pattern schema migration on SQLite via Alembic. Phase A1 (table/class rename with column names preserved) is finished at the DB + ORM layer; callers still need migration. Phase A2 ships column renames, additive new columns, and seven new tables atomically in revision `004`, then wires ingest to emit `DealEvent` and append `OfferPayloadHistory` (FIFO N=10). No matching pipeline yet — `offers.product_id` stays NULL until Phase B/C. No dashboard product UI — that's Phase D.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x ORM, Alembic, SQLite (WAL, `render_as_batch=True`), pytest, FastAPI, Jinja2.

**Reference design spec:** [docs/superpowers/specs/2026-04-13-products-and-offers-design.md](docs/superpowers/specs/2026-04-13-products-and-offers-design.md).

**Scope boundary (what this plan does NOT do):**
- No matching pipeline (L1/L2/L3) — Phase C plan, separate file.
- No NBP FX client — Phase B plan, separate file. `fx_rates` table exists; rows are not yet populated.
- No `/products` or `/review` dashboard routes — Phase D/E plans.
- No feature-flag flipping — `PRODUCT_MODEL_ENABLED` stays opt-in until Phase F.
- No backfill of `product_id` onto existing offers — Phase C.

**Current repo state at plan start:**
- Worktree: `/home/liske/Projects/deal-hunter-phase-a1` on branch `phase-a1-rename`.
- Last commit: `cdd7aba refactor(models): rename Deal->Offer, PriceHistory->PricePoint`.
- Alembic head: `003` (applied in test fixtures, not in your local `state/deals.db`).
- Test suite: **broken at collection time** (tests/conftest.py imports the now-gone `DealRepository`). Task 1 restores green.

---

## File Structure

**Files created in this plan:**
- `storage/migrations/versions/004_products_schema.py` — column renames + new columns + new tables + `source_native_id` backfill.
- `tests/test_migration_004_products_schema.py` — round-trip + backfill test for revision 004.
- `tests/test_offer_payload_history.py` — repository FIFO + retention test.
- `tests/test_deal_events.py` — repository + emission test.
- `tests/test_products_models.py` — schema sanity for Product/ProductAlias/MatchReview/MatchDecision/FxRate.
- `tests/test_ingest_event_emission.py` — integration: fetcher emits events + appends payload history.
- `CHANGELOG.md` entry (file already exists).

**Files modified in this plan:**
- `storage/models.py` — rename `Offer` attributes (`title`→`raw_title`, `price`→`current_price_pln`, `link`→`url`, `first_seen`→`first_seen_at`, `last_seen`→`last_seen_at`); rename `PricePoint.deal_id`→`offer_id` and `PricePoint.price`→`price_pln`; add new columns; add new model classes `Product`, `ProductAlias`, `OfferPayloadHistory`, `DealEvent`, `MatchReview`, `MatchDecision`, `FxRate`.
- `storage/repositories.py` — `DealRepository`→`OfferRepository`; raw SQL updated; `_to_dict` emits new keys; new repositories: `ProductRepository`, `ProductAliasRepository`, `OfferPayloadHistoryRepository` (with FIFO eviction), `DealEventRepository`, `MatchReviewRepository`, `MatchDecisionRepository`, `FxRateRepository`.
- `services/fetcher.py` — on upsert, append payload history + emit `new_listing` / `back_in_stock` events.
- `services/price_tracker.py` — emit `price_drop` / `price_increase` DealEvent rows alongside existing alert path.
- `services/alerter.py` — unchanged call signature; adapt to new PricePoint column names.
- `dashboard/services/deal_service.py`, `dashboard/routes/deals.py`, `dashboard/routes/profiles.py`, `dashboard/services/tuner_service.py` — consume new `_to_dict` keys; raw SQL updated.
- `dashboard/templates/partials/*.html`, `dashboard/templates/deals.html` — `deal.title`/`deal.price`/`deal.link` continue to work via adapter layer (see Task 6).
- `visualization/charts.py` — use new column names; raw SQL migrated.
- `deal_hunter.py`, `feedback_bot.py` — imports + dict key consumers.
- `scripts/migrate_json_state.py` — raw SQL to `price_points`.
- `tests/conftest.py`, `tests/e2e/conftest.py` — fixtures produce new column shape.
- Test files under `tests/` referencing the old ORM / raw SQL — sweeping in Task 8, Task 13.

**Files deliberately NOT modified:**
- `sources/base.py` — `Deal` dataclass (in-flight fetch DTO) stays named `Deal`. Confirmed in spec §1.
- `notifiers/telegram.py` — uses dict keys from the adapter; unchanged.
- `dashboard/schemas.py` — Pydantic API schemas stay shaped around the output-adapter keys; unchanged.

---

## Task 1: Finish A1 rename — `OfferRepository` + raw SQL + caller sweep

**Files:**
- Modify: [storage/repositories.py](storage/repositories.py)
- Modify: [tests/conftest.py](tests/conftest.py), [tests/e2e/conftest.py](tests/e2e/conftest.py)
- Modify: [services/price_tracker.py](services/price_tracker.py), [services/fetcher.py](services/fetcher.py), [services/alerter.py](services/alerter.py)
- Modify: [dashboard/services/deal_service.py](dashboard/services/deal_service.py), [dashboard/services/tuner_service.py](dashboard/services/tuner_service.py), [dashboard/routes/deals.py](dashboard/routes/deals.py), [dashboard/routes/profiles.py](dashboard/routes/profiles.py)
- Modify: [visualization/charts.py](visualization/charts.py)
- Modify: [deal_hunter.py](deal_hunter.py), [feedback_bot.py](feedback_bot.py)
- Modify: [scripts/migrate_json_state.py](scripts/migrate_json_state.py)
- Modify: tests referencing `DealRepository`, `Deal as DealModel`, `PriceHistory`, or raw SQL against `deals`/`price_history` (see grep in Step 1.1).

This is the mechanical end of the A1 rename. Pure substitution; no behavior change. Landed as one commit after the full suite is green — smaller commits here fragment the rename and leave the tree uncompilable for long stretches.

- [ ] **Step 1.1: Inventory (read-only)**

Run:
```bash
grep -rn --include='*.py' -E '\bDealRepository\b|\bPriceHistory\b|from storage\.models import .*\bDeal\b|(FROM|JOIN|INTO|UPDATE)\s+(deals|price_history)\b' . \
  | grep -v venv | grep -v '\.git' | grep -v test_migration_003_rename
```

Expected: callers in repositories.py, conftest.py, e2e/conftest.py, services/, dashboard/, visualization/, deal_hunter.py, feedback_bot.py, scripts/migrate_json_state.py, and tests test_charts.py, test_database.py, test_feedback_bot.py, test_models.py, test_price_drops.py, test_price_tracking.py.

- [ ] **Step 1.2: Update `storage/repositories.py` imports block**

Replace the top import block with:
```python
from storage.models import (
    AlertQueue,
    Feedback,
    Offer,
    PricePoint,
    SeenDeal,
    WatchlistItem,
)
```

- [ ] **Step 1.3: Rename `class DealRepository` → `class OfferRepository`; replace every `Deal` type reference inside with `Offer`**

Inside the class body, substitute:
- `session.get(Deal, id)` → `session.get(Offer, id)`
- `select(Deal)` → `select(Offer)`
- `func.count().select_from(Deal)` → `func.count().select_from(Offer)`
- `.where(Deal.xxx ...)` → `.where(Offer.xxx ...)`
- `deal: Deal` parameter types → `offer: Offer` (local cosmetic; dict keys inside `_to_dict` stay as-is for A1 — they get renamed in Task 6)
- `Deal | None` return/param annotations → `Offer | None`

Keep `_to_dict`'s returned keys exactly as they are today (`{"title": ..., "price": ..., "link": ..., "first_seen": ..., "last_seen": ..., ...}`). Column renames happen in Task 6.

- [ ] **Step 1.4: Update raw SQL in `OfferRepository`**

- `repositories.py:81` and `:281`: `INSERT OR IGNORE INTO price_history (...)` → `INSERT OR IGNORE INTO price_points (...)`
- `repositories.py:160`: `FROM deals` → `FROM offers`
- `repositories.py:215-216`: `FROM price_history ph JOIN deals d ON ph.deal_id = d.id` → `FROM price_points ph JOIN offers d ON ph.deal_id = d.id`

- [ ] **Step 1.5: Update `class PriceRepository` — type references + raw SQL**

Leave the class name `PriceRepository` as-is (rename to `PricePointRepository` is cosmetic and is deferred to Phase B to avoid a second class-rename wave here). Inside its methods:
- All `PriceHistory` symbol references → `PricePoint`
- `repositories.py:364`: `FROM price_history` → `FROM price_points`
- `repositories.py:400`: `FROM price_history ph JOIN deals d ON ph.deal_id = d.id` → `FROM price_points ph JOIN offers d ON ph.deal_id = d.id`
- `repositories.py:404`: `FROM ranked JOIN deals d ON d.id = ranked.deal_id` → `FROM ranked JOIN offers d ON d.id = ranked.deal_id`
- `repositories.py:462`: `FROM price_history ph` → `FROM price_points ph`

- [ ] **Step 1.6: Update `WatchlistRepository` raw SQL**

- `repositories.py:508, 525`: `LEFT JOIN deals d ON w.deal_id = d.id` → `LEFT JOIN offers d ON w.deal_id = d.id`

- [ ] **Step 1.7: Keep a backward-compat alias so the Task runs one-shot without dangling callers**

At the bottom of `storage/repositories.py`, after all class definitions, append:
```python
# Backward-compat alias — removed in Task 9 after all external callers migrate.
DealRepository = OfferRepository
```

(This shrinks the blast radius during Steps 1.8–1.14.)

- [ ] **Step 1.8: Update `tests/conftest.py`**

- Line 12: `from storage.repositories import DealRepository` → `from storage.repositories import OfferRepository`
- Line 86: `deal_repo = DealRepository(session)` → `deal_repo = OfferRepository(session)` (keep the local name `deal_repo` — minimal diff)
- Lines 155, 162: `INSERT OR IGNORE INTO price_history (...)` → `INSERT OR IGNORE INTO price_points (...)`

- [ ] **Step 1.9: Update `tests/e2e/conftest.py`**

- Lines 115, 122: same `price_history` → `price_points` substitution.

- [ ] **Step 1.10: Update services/ layer**

- `services/price_tracker.py`: `from storage.repositories import PriceRepository` stays; any internal `PriceHistory` reference → `PricePoint`.
- `services/fetcher.py`: if it imports `DealRepository`, change to `OfferRepository`. Leave the in-flight `Deal` dataclass from `sources.base` alone.
- `services/alerter.py`: no repository imports expected; double-check with the grep from Step 1.1.

- [ ] **Step 1.11: Update dashboard/ layer**

Substitute in each file identified in Step 1.1:
- `from storage.repositories import DealRepository` → `... OfferRepository`
- `DealRepository(session)` → `OfferRepository(session)`
- If `.title`/`.price`/`.link` attributes are accessed on the ORM row directly (not via `_to_dict`), keep them — column names are unchanged in A1. Attribute renames happen in Task 6.

Raw SQL audit in this pass — there should be no `FROM deals`/`FROM price_history` inside `dashboard/` after Step 1.1 mapped it. If grep surfaces any, apply the same substitution rules as Step 1.4.

- [ ] **Step 1.12: Update `visualization/charts.py`**

- Line 11: `from storage.models import Base, PriceHistory` (if present) → `... PricePoint`
- Line 44, 195: `from storage.repositories import DealRepository, PriceRepository` → `from storage.repositories import OfferRepository, PriceRepository`
- Lines 48, 201: `DealRepository(session)` → `OfferRepository(session)`
- Raw SQL: `price_history` → `price_points`, `deals` → `offers` where they appear.

- [ ] **Step 1.13: Update `deal_hunter.py`, `feedback_bot.py`, `scripts/migrate_json_state.py`**

- `feedback_bot.py` lines 25, 61, 85, 103, 114, 173: `DealRepository` → `OfferRepository`.
- `deal_hunter.py`: follow grep output from Step 1.1; substitute `DealRepository` → `OfferRepository`, `PriceHistory` → `PricePoint`.
- `scripts/migrate_json_state.py` line 86: `INSERT OR IGNORE INTO price_history (...)` → `INSERT OR IGNORE INTO price_points (...)`. Line 28 is unaffected (imports `Base, SeenDeal` only).

- [ ] **Step 1.14: Update tests that reference the old ORM / raw SQL**

From Step 1.1 grep, the test files to edit:
- `tests/test_charts.py:11-12`: `from storage.models import Base, PriceHistory` → `... PricePoint`; `from storage.models import Deal as DealModel` → `from storage.models import Offer as DealModel` (keep the local alias `DealModel` — it already shadows, and callers inside the test use it; no wider diff).
- `tests/test_database.py:8`: `from storage.models import Base, Deal` → `from storage.models import Base, Offer as Deal` (same aliasing trick — the test body uses the short name).
- `tests/test_feedback_bot.py:12, 32, 42, 250, 281, 364`: `DealRepository` → `OfferRepository`; keep local variable names unchanged.
- `tests/test_price_drops.py:374, 380, 402, 409, 426, 432, 453, 459`: `INSERT INTO price_history (...)` → `INSERT INTO price_points (...)`.
- `tests/test_price_tracking.py:11-13`: `from storage.models import Base, PriceHistory` → `... PricePoint`; `from storage.models import Deal as DealModel` → `from storage.models import Offer as DealModel`.
- `tests/test_models.py:7-…`: the import list — every `Deal` → `Offer`, every `PriceHistory` → `PricePoint`. Test bodies that assert `assert Deal.__tablename__ == "deals"` must flip to `"offers"` (new contract); same for `PriceHistory` / `"price_history"` → `PricePoint` / `"price_points"`.

Use aliasing (`Offer as Deal`) sparingly — only where the old name appears many times in the test body. Otherwise just rename in place.

- [ ] **Step 1.15: Run the full suite**

Run:
```bash
source venv/bin/activate
python -m pytest tests/ --ignore=tests/e2e -q 2>&1 | tail -12
```

Expected: pass count matches the pre-A1 baseline (use `git stash && git checkout main && pytest tests/ --ignore=tests/e2e -q 2>&1 | tail -3` in a separate shell to capture the baseline if you don't already have it). Any failure here points back to a missed call-site — re-grep and fix.

- [ ] **Step 1.16: Commit**

```bash
git add storage/repositories.py tests/conftest.py tests/e2e/conftest.py \
        services/ dashboard/ visualization/ deal_hunter.py feedback_bot.py \
        scripts/migrate_json_state.py \
        tests/test_charts.py tests/test_database.py tests/test_feedback_bot.py \
        tests/test_price_drops.py tests/test_price_tracking.py tests/test_models.py
git commit -m "refactor(repos): rename DealRepository->OfferRepository, update all callers & raw SQL"
```

---

## Task 2: Drop the `DealRepository` alias + A1 checkpoint

**Files:**
- Modify: [storage/repositories.py](storage/repositories.py)
- Modify: `CHANGELOG.md`

- [ ] **Step 2.1: Confirm no caller references `DealRepository`**

Run:
```bash
grep -rn --include='*.py' '\bDealRepository\b' . \
  | grep -v 'DealRepository = OfferRepository' | grep -v venv | grep -v '\.git'
```

Expected: empty. If not, fix call-sites before removing the alias.

- [ ] **Step 2.2: Remove the alias line from `storage/repositories.py`**

Delete:
```python
# Backward-compat alias — removed in Task 9 after all external callers migrate.
DealRepository = OfferRepository
```

- [ ] **Step 2.3: Run suite**

Run:
```bash
python -m pytest tests/ --ignore=tests/e2e -q 2>&1 | tail -5
```

Expected: unchanged pass count from Task 1.15.

- [ ] **Step 2.4: A1 changelog entry**

Edit `CHANGELOG.md`. Under the next `## [Unreleased]` section (add one if absent), append:
```markdown
### Changed
- **Database**: renamed tables `deals` → `offers` and `price_history` → `price_points` (Alembic `003`). Column names, PK values, and FK relationships preserved. Python classes renamed: `Deal` → `Offer`, `PriceHistory` → `PricePoint`, `DealRepository` → `OfferRepository`. First step of products-and-offers migration.
```

- [ ] **Step 2.5: Commit**

```bash
git add storage/repositories.py CHANGELOG.md
git commit -m "refactor(repos): drop DealRepository alias; CHANGELOG for A1 rename"
```

At this point A1 is fully shipped on the branch. A2 begins.

---

## Task 3: Alembic 004 round-trip test — schema shape only

**Files:**
- Create: [tests/test_migration_004_products_schema.py](tests/test_migration_004_products_schema.py)

Test lands first and fails with "revision 004 not found" — drives Task 4.

- [ ] **Step 3.1: Write the failing test**

Create `tests/test_migration_004_products_schema.py`:
```python
"""Round-trip + backfill test for Alembic revision 004_products_schema."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


@pytest.fixture
def alembic_db(tmp_path: Path) -> tuple[Config, str]:
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    cfg = Config("storage/migrations/alembic.ini")
    return cfg, db_url


def _columns(db_url: str, table: str) -> set[str]:
    eng = create_engine(db_url)
    try:
        return {c["name"] for c in inspect(eng).get_columns(table)}
    finally:
        eng.dispose()


def _tables(db_url: str) -> set[str]:
    eng = create_engine(db_url)
    try:
        return set(inspect(eng).get_table_names())
    finally:
        eng.dispose()


def test_004_upgrade_renames_offer_columns(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "004")
    cols = _columns(db_url, "offers")
    assert {"raw_title", "current_price_pln", "url", "first_seen_at", "last_seen_at"} <= cols
    assert {"title", "price", "link", "first_seen", "last_seen"}.isdisjoint(cols)


def test_004_upgrade_renames_pricepoint_columns(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "004")
    cols = _columns(db_url, "price_points")
    assert {"offer_id", "price_pln", "recorded_at"} <= cols
    assert "deal_id" not in cols
    assert "price" not in cols or "price_pln" in cols  # only price_pln, not bare price


def test_004_adds_new_offer_columns(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "004")
    cols = _columns(db_url, "offers")
    assert {
        "product_id",
        "source_native_id",
        "current_price_original",
        "currency_original",
        "fx_rate_used",
        "availability",
        "attributes_hint",
        "is_active",
    } <= cols


def test_004_adds_new_pricepoint_columns(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "004")
    cols = _columns(db_url, "price_points")
    assert {
        "product_id",
        "price_original",
        "currency_original",
        "fx_rate_used",
        "availability",
    } <= cols


def test_004_creates_new_tables(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "004")
    tables = _tables(db_url)
    assert {
        "products",
        "product_aliases",
        "offer_payload_history",
        "deal_events",
        "match_reviews",
        "match_decisions",
        "fx_rates",
    } <= tables


def test_004_backfills_source_native_id(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "003")
    eng = create_engine(db_url)
    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO offers (id, title, price, source, status,"
                " first_seen, last_seen)"
                " VALUES ('pepper:abc123', 't', 100, 'pepper', 'active',"
                " '2026-01-01', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO offers (id, title, source, status,"
                " first_seen, last_seen)"
                " VALUES ('proshop:9#size=54', 't', 'proshop', 'active',"
                " '2026-01-01', '2026-01-01')"
            )
        )
    command.upgrade(cfg, "004")
    with eng.connect() as conn:
        rows = dict(
            conn.execute(text("SELECT id, source_native_id FROM offers")).all()
        )
    assert rows["pepper:abc123"] == "abc123"
    assert rows["proshop:9#size=54"] == "9#size=54"
    eng.dispose()


def test_004_roundtrip_upgrade_downgrade_upgrade(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "004")
    assert {"products", "deal_events"} <= _tables(db_url)

    command.downgrade(cfg, "003")
    tables_after_down = _tables(db_url)
    assert "products" not in tables_after_down
    assert "deal_events" not in tables_after_down
    assert "offers" in tables_after_down  # 003 survives
    cols_after_down = _columns(db_url, "offers")
    assert "raw_title" not in cols_after_down
    assert "title" in cols_after_down

    command.upgrade(cfg, "004")
    assert {"products", "deal_events"} <= _tables(db_url)
```

- [ ] **Step 3.2: Run to see it fail**

Run: `python -m pytest tests/test_migration_004_products_schema.py -v`

Expected: all 7 tests FAIL with `Can't locate revision identified by '004'`.

No commit — Task 4 makes these green.

---

## Task 4: Alembic 004 migration — implementation

**Files:**
- Create: `storage/migrations/versions/004_products_schema.py`

- [ ] **Step 4.1: Write the migration file**

Create `storage/migrations/versions/004_products_schema.py`:
```python
"""Phase A2 — column renames on offers/price_points, additive columns, new tables.

Revision ID: 004
Revises: 003
Create Date: 2026-04-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- offers: column renames + additive columns ------------------------
    with op.batch_alter_table("offers") as b:
        b.alter_column("title", new_column_name="raw_title")
        b.alter_column("price", new_column_name="current_price_pln")
        b.alter_column("link", new_column_name="url")
        b.alter_column("first_seen", new_column_name="first_seen_at")
        b.alter_column("last_seen", new_column_name="last_seen_at")
        b.add_column(sa.Column("product_id", sa.String(), nullable=True))
        b.add_column(sa.Column("source_native_id", sa.String(), nullable=True))
        b.add_column(sa.Column("current_price_original", sa.Integer(), nullable=True))
        b.add_column(
            sa.Column(
                "currency_original",
                sa.String(),
                nullable=False,
                server_default="PLN",
            )
        )
        b.add_column(sa.Column("fx_rate_used", sa.Float(), nullable=True))
        b.add_column(sa.Column("availability", sa.String(), nullable=True))
        b.add_column(sa.Column("attributes_hint", sa.JSON(), nullable=True))
        b.add_column(
            sa.Column(
                "is_active",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )

    # --- price_points: column renames + additive columns ------------------
    with op.batch_alter_table("price_points") as b:
        b.alter_column("deal_id", new_column_name="offer_id")
        b.alter_column("price", new_column_name="price_pln")
        b.add_column(sa.Column("product_id", sa.String(), nullable=True))
        b.add_column(sa.Column("price_original", sa.Integer(), nullable=True))
        b.add_column(
            sa.Column(
                "currency_original",
                sa.String(),
                nullable=False,
                server_default="PLN",
            )
        )
        b.add_column(sa.Column("fx_rate_used", sa.Float(), nullable=True))
        b.add_column(sa.Column("availability", sa.String(), nullable=True))

    # --- backfill offers.source_native_id from id (split on first ':') ----
    op.execute(
        "UPDATE offers SET source_native_id = substr(id, instr(id, ':') + 1)"
        " WHERE source_native_id IS NULL"
    )

    # --- new tables -------------------------------------------------------
    op.create_table(
        "products",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("canonical_title", sa.Text(), nullable=False),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("canonical_image_url", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(), nullable=False, server_default="auto"),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("merged_from", sa.JSON(), nullable=True),
        sa.Column("archived", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index("ix_products_brand_model", "products", ["brand", "model"])
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index(
        "ix_products_archived_updated", "products", ["archived", "updated_at"]
    )

    op.create_table(
        "product_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "product_id",
            sa.String(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("identifier_type", sa.String(), nullable=False),
        sa.Column("identifier_value", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.UniqueConstraint(
            "identifier_type",
            "identifier_value",
            "source",
            name="uq_alias_type_value_source",
        ),
    )
    op.create_index("ix_aliases_product", "product_aliases", ["product_id"])

    op.create_table(
        "offer_payload_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "offer_id",
            sa.String(),
            sa.ForeignKey("offers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("captured_at", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_payload_offer_captured",
        "offer_payload_history",
        ["offer_id", "captured_at"],
    )

    op.create_table(
        "deal_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "offer_id",
            sa.String(),
            sa.ForeignKey("offers.id"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.String(),
            sa.ForeignKey("products.id"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("price_at_event", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("notified", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_events_offer_created", "deal_events", ["offer_id", "created_at"]
    )
    op.create_index(
        "ix_events_product_created", "deal_events", ["product_id", "created_at"]
    )
    op.create_index(
        "ix_events_type_created", "deal_events", ["event_type", "created_at"]
    )
    op.create_index("ix_events_notified", "deal_events", ["notified"])

    op.create_table(
        "match_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "offer_id",
            sa.String(),
            sa.ForeignKey("offers.id"),
            nullable=False,
        ),
        sa.Column(
            "candidate_product_id",
            sa.String(),
            sa.ForeignKey("products.id"),
            nullable=True,
        ),
        sa.Column("suggested_products", sa.JSON(), nullable=True),
        sa.Column("best_confidence", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("decided_at", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_reviews_status_priority", "match_reviews", ["status", "priority"]
    )
    op.create_index("ix_reviews_offer", "match_reviews", ["offer_id"])

    op.create_table(
        "match_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "offer_id", sa.String(), sa.ForeignKey("offers.id"), nullable=True
        ),
        sa.Column(
            "product_id",
            sa.String(),
            sa.ForeignKey("products.id"),
            nullable=True,
        ),
        sa.Column("decision_type", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("signals", sa.JSON(), nullable=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("undo_snapshot", sa.JSON(), nullable=True),
    )
    op.create_index("ix_decisions_offer", "match_decisions", ["offer_id"])
    op.create_index("ix_decisions_product", "match_decisions", ["product_id"])
    op.create_index("ix_decisions_created", "match_decisions", ["created_at"])

    op.create_table(
        "fx_rates",
        sa.Column("currency", sa.String(), primary_key=True),
        sa.Column("rate_to_pln", sa.Float(), nullable=False),
        sa.Column("fetched_at", sa.String(), nullable=False),
        sa.Column("table_no", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("fx_rates")
    op.drop_index("ix_decisions_created", table_name="match_decisions")
    op.drop_index("ix_decisions_product", table_name="match_decisions")
    op.drop_index("ix_decisions_offer", table_name="match_decisions")
    op.drop_table("match_decisions")
    op.drop_index("ix_reviews_offer", table_name="match_reviews")
    op.drop_index("ix_reviews_status_priority", table_name="match_reviews")
    op.drop_table("match_reviews")
    op.drop_index("ix_events_notified", table_name="deal_events")
    op.drop_index("ix_events_type_created", table_name="deal_events")
    op.drop_index("ix_events_product_created", table_name="deal_events")
    op.drop_index("ix_events_offer_created", table_name="deal_events")
    op.drop_table("deal_events")
    op.drop_index("ix_payload_offer_captured", table_name="offer_payload_history")
    op.drop_table("offer_payload_history")
    op.drop_index("ix_aliases_product", table_name="product_aliases")
    op.drop_table("product_aliases")
    op.drop_index("ix_products_archived_updated", table_name="products")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_index("ix_products_brand_model", table_name="products")
    op.drop_table("products")

    with op.batch_alter_table("price_points") as b:
        b.drop_column("availability")
        b.drop_column("fx_rate_used")
        b.drop_column("currency_original")
        b.drop_column("price_original")
        b.drop_column("product_id")
        b.alter_column("price_pln", new_column_name="price")
        b.alter_column("offer_id", new_column_name="deal_id")

    with op.batch_alter_table("offers") as b:
        b.drop_column("is_active")
        b.drop_column("attributes_hint")
        b.drop_column("availability")
        b.drop_column("fx_rate_used")
        b.drop_column("currency_original")
        b.drop_column("current_price_original")
        b.drop_column("source_native_id")
        b.drop_column("product_id")
        b.alter_column("last_seen_at", new_column_name="last_seen")
        b.alter_column("first_seen_at", new_column_name="first_seen")
        b.alter_column("url", new_column_name="link")
        b.alter_column("current_price_pln", new_column_name="price")
        b.alter_column("raw_title", new_column_name="title")
```

- [ ] **Step 4.2: Run Task 3's test suite**

Run: `python -m pytest tests/test_migration_004_products_schema.py -v`

Expected: 7/7 PASS.

- [ ] **Step 4.3: Commit**

```bash
git add storage/migrations/versions/004_products_schema.py \
        tests/test_migration_004_products_schema.py
git commit -m "feat(db): add alembic 004 — column renames, new product schema, backfill"
```

---

## Task 5: Update ORM models — rename columns + add new columns

**Files:**
- Modify: [storage/models.py](storage/models.py)

Schema is already in the DB (Task 4). Now the ORM must match, or reads will silently break when the Python attribute doesn't map to the renamed column.

- [ ] **Step 5.1: Update `Offer` model**

In `storage/models.py`, replace the `Offer` class body with:
```python
class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    raw_title: Mapped[str] = mapped_column(Text, nullable=False)
    current_price_pln: Mapped[int | None] = mapped_column(default=None)
    url: Mapped[str | None] = mapped_column(Text, default=None)
    source: Mapped[str | None] = mapped_column(String, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    image_url: Mapped[str | None] = mapped_column(Text, default=None)
    profile: Mapped[str | None] = mapped_column(String, default=None)
    score: Mapped[int | None] = mapped_column(default=None)
    category: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String, default="active")
    first_seen_at: Mapped[str | None] = mapped_column(String, default=None)
    last_seen_at: Mapped[str | None] = mapped_column(String, default=None)

    # New in A2:
    product_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("products.id"), default=None
    )
    source_native_id: Mapped[str | None] = mapped_column(String, default=None)
    current_price_original: Mapped[int | None] = mapped_column(default=None)
    currency_original: Mapped[str] = mapped_column(String, default="PLN")
    fx_rate_used: Mapped[float | None] = mapped_column(default=None)
    availability: Mapped[str | None] = mapped_column(String, default=None)
    attributes_hint: Mapped[dict | None] = mapped_column(JSON, default=None)
    is_active: Mapped[int] = mapped_column(default=1)

    prices: Mapped[list["PricePoint"]] = relationship(back_populates="offer")
    feedback_entries: Mapped[list["Feedback"]] = relationship(back_populates="offer")
    watchlist_entry: Mapped["WatchlistItem | None"] = relationship(
        back_populates="offer"
    )
    payload_history: Mapped[list["OfferPayloadHistory"]] = relationship(
        back_populates="offer", cascade="all, delete-orphan"
    )
    events: Mapped[list["DealEvent"]] = relationship(back_populates="offer")
    product: Mapped["Product | None"] = relationship(back_populates="offers")

    __table_args__ = (Index("idx_offers_profile_score", "profile", "score"),)
```

Add `from sqlalchemy import JSON` at the top of the file if not already imported.

- [ ] **Step 5.2: Update `PricePoint` model**

Replace with:
```python
class PricePoint(Base):
    __tablename__ = "price_points"

    offer_id: Mapped[str] = mapped_column(
        String, ForeignKey("offers.id"), primary_key=True
    )
    price_pln: Mapped[int] = mapped_column(nullable=False)
    recorded_at: Mapped[str] = mapped_column(String, primary_key=True)

    # New in A2:
    product_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("products.id"), default=None
    )
    price_original: Mapped[int | None] = mapped_column(default=None)
    currency_original: Mapped[str] = mapped_column(String, default="PLN")
    fx_rate_used: Mapped[float | None] = mapped_column(default=None)
    availability: Mapped[str | None] = mapped_column(String, default=None)

    offer: Mapped["Offer"] = relationship(back_populates="prices")
    product: Mapped["Product | None"] = relationship(back_populates="price_points")
```

- [ ] **Step 5.3: Commit**

Run the schema tests to confirm the ORM matches:
```bash
python -m pytest tests/test_migration_004_products_schema.py tests/test_models.py -q
```

Expected: pass (test_models.py may need attribute-name updates — if so, do them now; the rename is part of the same commit).

```bash
git add storage/models.py tests/test_models.py
git commit -m "refactor(models): rename Offer/PricePoint columns; add A2 columns"
```

At this point the suite is **broken again** in the caller layer — any code that does `offer.title` or `price_point.deal_id` crashes. Task 6 fixes it.

---

## Task 6: Migrate repository + caller layer to new attribute names

**Files:**
- Modify: [storage/repositories.py](storage/repositories.py)
- Modify: [dashboard/services/deal_service.py](dashboard/services/deal_service.py), [dashboard/routes/deals.py](dashboard/routes/deals.py), [dashboard/services/tuner_service.py](dashboard/services/tuner_service.py)
- Modify: [services/price_tracker.py](services/price_tracker.py), [services/fetcher.py](services/fetcher.py), [services/alerter.py](services/alerter.py)
- Modify: [visualization/charts.py](visualization/charts.py)
- Modify: [deal_hunter.py](deal_hunter.py), [feedback_bot.py](feedback_bot.py)
- Modify: tests that touch these fields.

### Adapter strategy

The external contract visible to Jinja templates, Telegram alert payloads, Pydantic response schemas, and feedback-bot commands stays on the legacy dict key names (`title`, `price`, `link`, `first_seen`, `last_seen`). This is a deliberate scope limit: the rename goes all the way to the repository, but `_to_dict` remaps at the boundary so templates/alerts/bots keep working.

- [ ] **Step 6.1: Update `OfferRepository.upsert` signature + body**

In `storage/repositories.py`:
- Rename parameters: `title` → `raw_title`, `price` → `current_price_pln`, `link` → `url`, `first_seen` → `first_seen_at`, `last_seen` → `last_seen_at`.
- Rewire attribute access inside the method: `existing.price` → `existing.current_price_pln`, `existing.last_seen` → `existing.last_seen_at`, `existing.score` stays, etc.
- Where the method does `Offer(id=id, title=title, price=price, ...)`, substitute the new attribute names.
- Keep callers green by also accepting the legacy parameter names as kwargs — add a short adapter at the top of `upsert`:
  ```python
  def upsert(  # noqa: A002
      self,
      *,
      id: str,  # noqa: A002
      raw_title: str | None = None,
      title: str | None = None,  # legacy
      current_price_pln: int | None = None,
      price: int | None = None,  # legacy
      url: str = "",
      link: str = "",  # legacy
      source: str = "",
      description: str = "",
      image_url: str = "",
      profile: str = "",
      score: int = 0,
      category: str = "",
      status: str = "active",
      first_seen_at: str = "",
      first_seen: str = "",  # legacy
      last_seen_at: str = "",
      last_seen: str = "",  # legacy
  ) -> Offer:
      raw_title = raw_title if raw_title is not None else title
      current_price_pln = (
          current_price_pln if current_price_pln is not None else price
      )
      url = url or link
      first_seen_at = first_seen_at or first_seen
      last_seen_at = last_seen_at or last_seen
      if raw_title is None:
          raise TypeError("OfferRepository.upsert requires raw_title or title")
      ...
  ```
  This lets every existing caller keep working without a sweeping kwarg rename — they migrate opportunistically when touched later.

- [ ] **Step 6.2: Update `OfferRepository._to_dict` to emit both new and legacy keys**

```python
def _to_dict(self, offer: Offer) -> dict[str, Any]:
    return {
        # Legacy keys — preserved for template/Telegram/bot contract:
        "id": offer.id,
        "title": offer.raw_title,
        "price": offer.current_price_pln,
        "link": offer.url,
        "source": offer.source,
        "description": offer.description,
        "image_url": offer.image_url,
        "profile": offer.profile,
        "score": offer.score,
        "category": offer.category,
        "status": offer.status,
        "first_seen": offer.first_seen_at,
        "last_seen": offer.last_seen_at,
        # New keys — surfaced for product-aware callers:
        "raw_title": offer.raw_title,
        "current_price_pln": offer.current_price_pln,
        "url": offer.url,
        "first_seen_at": offer.first_seen_at,
        "last_seen_at": offer.last_seen_at,
        "product_id": offer.product_id,
        "source_native_id": offer.source_native_id,
        "currency_original": offer.currency_original,
        "current_price_original": offer.current_price_original,
        "fx_rate_used": offer.fx_rate_used,
        "availability": offer.availability,
        "is_active": offer.is_active,
    }
```

- [ ] **Step 6.3: Update all raw SQL in `OfferRepository` + `PriceRepository` + `WatchlistRepository`**

Attribute-level substitutions in raw SQL strings:
- `SELECT ... price ...` on offers → `SELECT ... current_price_pln AS price ...` (keep the alias so the dict key contract holds).
- `SELECT ... title ...` on offers → `SELECT ... raw_title AS title ...`.
- `WHERE first_seen LIKE ...` → `WHERE first_seen_at LIKE ...`.
- In `price_points`: `price` → `price_pln AS price` (preserve alias); `deal_id` → `offer_id AS deal_id`.
- In joins on `price_points`: every `ph.deal_id` → `ph.offer_id`; keep the external alias `deal_id` in the SELECT if consumers read it.
- `ORDER BY recorded_at` stays.

Audit each raw-SQL block visually after editing — a SELECT that returns mismatched key names will crash consumers silently.

- [ ] **Step 6.4: Update `OfferRepository.get_filtered` / `get_by_id` / `get_by_status` / `update_status`**

These already return dicts via `_to_dict` — Step 6.2 covers them. If any returns a detached ORM row directly (e.g., `.get_by_id` returning `Offer`), keep the ORM return but document in a docstring that callers must use `_to_dict` or accept attribute renaming.

- [ ] **Step 6.5: Update caller attribute access**

Grep for direct attribute access on ORM instances:
```bash
grep -rn --include='*.py' -E '\.(title|price|link|first_seen|last_seen)\b' \
  dashboard/ services/ visualization/ deal_hunter.py feedback_bot.py \
  | grep -v '_to_dict' | grep -v 'deal\[' | grep -v 'offer\[' \
  | grep -v venv
```

For each match, decide:
- If operating on a dict (key access `deal["title"]`) → unchanged (adapter serves the legacy key).
- If operating on an ORM instance (attribute access `offer.title`) → rename to `offer.raw_title`, `offer.current_price_pln`, `offer.url`, `offer.first_seen_at`, `offer.last_seen_at`.

- [ ] **Step 6.6: Update templates quickly — sanity check only**

Templates use `{{ deal.title }}` / `{{ deal.price }}` / `{{ deal.link }}` / `{{ deal.first_seen }}` / `{{ deal.last_seen }}`. They consume dicts, which still provide the legacy keys via Step 6.2. No template edits needed in this plan. Verify with:
```bash
grep -rn --include='*.html' -E 'deal\.(title|price|link|first_seen|last_seen)' dashboard/templates
```
This must return matches (that's fine) — but any match using ORM-attribute-like paths that the adapter doesn't cover must be re-checked.

- [ ] **Step 6.7: Run suite**

Run:
```bash
python -m pytest tests/ --ignore=tests/e2e -q 2>&1 | tail -12
```

Expected: back to the pre-A1 baseline pass count. Investigate every failure.

- [ ] **Step 6.8: Commit**

```bash
git add storage/repositories.py dashboard/ services/ visualization/ \
        deal_hunter.py feedback_bot.py tests/
git commit -m "refactor: migrate callers to renamed offer/price_point columns, keep legacy dict keys"
```

---

## Task 7: New ORM models — `Product`, `ProductAlias`

**Files:**
- Modify: [storage/models.py](storage/models.py)
- Modify: [storage/repositories.py](storage/repositories.py)
- Create: [tests/test_products_models.py](tests/test_products_models.py)

- [ ] **Step 7.1: Write the failing test**

Create `tests/test_products_models.py`:
```python
"""Schema sanity tests for Product/ProductAlias ORM models."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models import Base, Product, ProductAlias


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_product_roundtrip(session: Session) -> None:
    now = datetime.now().isoformat()
    p = Product(
        id="prod-1",
        canonical_title="Rondo Ruut",
        brand="Rondo",
        model="Ruut",
        category="bikes",
        attributes={"size": "M", "year": 2025},
        review_status="auto",
        created_at=now,
        updated_at=now,
    )
    session.add(p)
    session.commit()
    loaded = session.get(Product, "prod-1")
    assert loaded is not None
    assert loaded.attributes == {"size": "M", "year": 2025}
    assert loaded.archived == 0


def test_product_alias_fk(session: Session) -> None:
    now = datetime.now().isoformat()
    session.add(
        Product(
            id="p1",
            canonical_title="t",
            category="bikes",
            attributes={},
            review_status="auto",
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        ProductAlias(
            product_id="p1",
            identifier_type="ean",
            identifier_value="5900000000001",
            confidence=1.0,
            created_by="auto",
            created_at=now,
        )
    )
    session.commit()
    aliases = session.query(ProductAlias).filter_by(product_id="p1").all()
    assert len(aliases) == 1
    assert aliases[0].identifier_type == "ean"
```

- [ ] **Step 7.2: Run — fails with `cannot import name 'Product'`**

Run: `python -m pytest tests/test_products_models.py -v`

- [ ] **Step 7.3: Add `Product` + `ProductAlias` models**

Append to `storage/models.py` (after `PricePoint`):
```python
class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    canonical_title: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(String, default=None)
    model: Mapped[str | None] = mapped_column(String, default=None)
    category: Mapped[str] = mapped_column(String, nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False)
    canonical_image_url: Mapped[str | None] = mapped_column(Text, default=None)
    review_status: Mapped[str] = mapped_column(String, default="auto")
    confidence_score: Mapped[float | None] = mapped_column(default=None)
    merged_from: Mapped[list | None] = mapped_column(JSON, default=None)
    archived: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    aliases: Mapped[list["ProductAlias"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    offers: Mapped[list["Offer"]] = relationship(back_populates="product")
    price_points: Mapped[list["PricePoint"]] = relationship(back_populates="product")


class ProductAlias(Base):
    __tablename__ = "product_aliases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    identifier_type: Mapped[str] = mapped_column(String, nullable=False)
    identifier_value: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str | None] = mapped_column(String, default=None)
    confidence: Mapped[float] = mapped_column(nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="aliases")
```

- [ ] **Step 7.4: Minimal repositories**

Append to `storage/repositories.py`:
```python
class ProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        id: str,  # noqa: A002
        canonical_title: str,
        category: str,
        attributes: dict,
        brand: str | None = None,
        model: str | None = None,
        review_status: str = "auto",
        confidence_score: float | None = None,
    ) -> Product:
        now = datetime.now().isoformat()
        p = Product(
            id=id,
            canonical_title=canonical_title,
            category=category,
            attributes=attributes,
            brand=brand,
            model=model,
            review_status=review_status,
            confidence_score=confidence_score,
            created_at=now,
            updated_at=now,
        )
        self.session.add(p)
        return p

    def get(self, product_id: str) -> Product | None:
        return self.session.get(Product, product_id)


class ProductAliasRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        *,
        product_id: str,
        identifier_type: str,
        identifier_value: str,
        confidence: float,
        source: str | None = None,
        created_by: str = "auto",
    ) -> ProductAlias:
        now = datetime.now().isoformat()
        alias = ProductAlias(
            product_id=product_id,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            source=source,
            confidence=confidence,
            created_by=created_by,
            created_at=now,
        )
        self.session.add(alias)
        return alias

    def find(
        self,
        *,
        identifier_type: str,
        identifier_value: str,
        source: str | None = None,
    ) -> ProductAlias | None:
        q = select(ProductAlias).where(
            ProductAlias.identifier_type == identifier_type,
            ProductAlias.identifier_value == identifier_value,
        )
        if source is not None:
            q = q.where(ProductAlias.source == source)
        else:
            q = q.where(ProductAlias.source.is_(None))
        return self.session.execute(q).scalars().first()
```

Import `Product, ProductAlias` at the top of `repositories.py`.

- [ ] **Step 7.5: Test + commit**

```bash
python -m pytest tests/test_products_models.py -v
git add storage/models.py storage/repositories.py tests/test_products_models.py
git commit -m "feat(products): add Product + ProductAlias models + minimal repositories"
```

---

## Task 8: `OfferPayloadHistory` — model, FIFO repository, tests

**Files:**
- Modify: [storage/models.py](storage/models.py), [storage/repositories.py](storage/repositories.py)
- Create: [tests/test_offer_payload_history.py](tests/test_offer_payload_history.py)

- [ ] **Step 8.1: Write the failing test**

Create `tests/test_offer_payload_history.py`:
```python
"""FIFO retention test for OfferPayloadHistory."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from storage.models import Base, Offer, OfferPayloadHistory
from storage.repositories import OfferPayloadHistoryRepository


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        now = datetime.now().isoformat()
        s.add(
            Offer(
                id="pepper:1",
                raw_title="t",
                source="pepper",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        s.commit()
        yield s


def test_append_keeps_newest_ten(session: Session) -> None:
    repo = OfferPayloadHistoryRepository(session)
    base = datetime(2026, 1, 1)
    for i in range(15):
        ts = (base + timedelta(minutes=i)).isoformat()
        repo.append(offer_id="pepper:1", raw_payload={"seq": i}, captured_at=ts)
    session.commit()

    rows = (
        session.execute(
            select(OfferPayloadHistory)
            .where(OfferPayloadHistory.offer_id == "pepper:1")
            .order_by(OfferPayloadHistory.captured_at.asc())
        )
        .scalars()
        .all()
    )
    assert len(rows) == 10
    # Oldest 5 evicted:
    assert rows[0].raw_payload == {"seq": 5}
    assert rows[-1].raw_payload == {"seq": 14}


def test_append_per_offer_isolated(session: Session) -> None:
    now = datetime.now().isoformat()
    session.add(
        Offer(
            id="pepper:2",
            raw_title="t2",
            source="pepper",
            first_seen_at=now,
            last_seen_at=now,
        )
    )
    session.commit()
    repo = OfferPayloadHistoryRepository(session)
    for i in range(12):
        repo.append(offer_id="pepper:1", raw_payload={"x": i}, captured_at=f"t-{i}")
    for i in range(3):
        repo.append(offer_id="pepper:2", raw_payload={"y": i}, captured_at=f"u-{i}")
    session.commit()

    n1 = session.scalar(
        select(OfferPayloadHistory)
        .where(OfferPayloadHistory.offer_id == "pepper:1")
        .count()
        if False  # pragma: no cover
        else select(OfferPayloadHistory).where(
            OfferPayloadHistory.offer_id == "pepper:1"
        )
    )
    assert (
        session.query(OfferPayloadHistory)
        .filter_by(offer_id="pepper:1")
        .count()
        == 10
    )
    assert (
        session.query(OfferPayloadHistory)
        .filter_by(offer_id="pepper:2")
        .count()
        == 3
    )
```

- [ ] **Step 8.2: Run — fails with `cannot import name 'OfferPayloadHistory'`**

Run: `python -m pytest tests/test_offer_payload_history.py -v`

- [ ] **Step 8.3: Add model**

Append to `storage/models.py`:
```python
class OfferPayloadHistory(Base):
    __tablename__ = "offer_payload_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    offer_id: Mapped[str] = mapped_column(
        String, ForeignKey("offers.id", ondelete="CASCADE"), nullable=False
    )
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    captured_at: Mapped[str] = mapped_column(String, nullable=False)

    offer: Mapped["Offer"] = relationship(back_populates="payload_history")
```

- [ ] **Step 8.4: Add repository with FIFO retention**

Append to `storage/repositories.py`:
```python
OFFER_PAYLOAD_HISTORY_MAX = 10


class OfferPayloadHistoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(
        self, *, offer_id: str, raw_payload: dict, captured_at: str
    ) -> OfferPayloadHistory:
        row = OfferPayloadHistory(
            offer_id=offer_id, raw_payload=raw_payload, captured_at=captured_at
        )
        self.session.add(row)
        self.session.flush()
        self._evict_beyond_limit(offer_id)
        return row

    def _evict_beyond_limit(self, offer_id: str) -> None:
        subq = (
            select(OfferPayloadHistory.id)
            .where(OfferPayloadHistory.offer_id == offer_id)
            .order_by(OfferPayloadHistory.captured_at.desc())
            .offset(OFFER_PAYLOAD_HISTORY_MAX)
        )
        ids_to_delete = list(self.session.execute(subq).scalars().all())
        if ids_to_delete:
            self.session.execute(
                text(
                    "DELETE FROM offer_payload_history WHERE id IN :ids"
                ).bindparams(sa_text_bindparam("ids", expanding=True)),
                {"ids": ids_to_delete},
            )
```

Note: SQLAlchemy's expanding bindparam is cleaner — replace the raw `text(...).bindparams(...)` block with an in-clause construction. Use:
```python
from sqlalchemy import delete

if ids_to_delete:
    self.session.execute(
        delete(OfferPayloadHistory).where(OfferPayloadHistory.id.in_(ids_to_delete))
    )
```
(Drop the `sa_text_bindparam` line and the `text(...)` above; the single `delete()` call is simpler and is what this step lands with.)

Import `OfferPayloadHistory` at top of `storage/repositories.py` and add `from sqlalchemy import delete` to the sqlalchemy import line.

- [ ] **Step 8.5: Test + commit**

```bash
python -m pytest tests/test_offer_payload_history.py -v
```
Expected: 2/2 PASS.

```bash
git add storage/models.py storage/repositories.py tests/test_offer_payload_history.py
git commit -m "feat(events): OfferPayloadHistory model + FIFO N=10 repository"
```

---

## Task 9: `DealEvent` — model, repository, tests

**Files:**
- Modify: [storage/models.py](storage/models.py), [storage/repositories.py](storage/repositories.py)
- Create: [tests/test_deal_events.py](tests/test_deal_events.py)

- [ ] **Step 9.1: Write the failing test**

Create `tests/test_deal_events.py`:
```python
"""Tests for DealEvent repository."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models import Base, DealEvent, Offer
from storage.repositories import DealEventRepository


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        now = datetime.now().isoformat()
        s.add(
            Offer(
                id="pepper:10",
                raw_title="t",
                source="pepper",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        s.commit()
        yield s


def test_emit_new_listing(session: Session) -> None:
    repo = DealEventRepository(session)
    evt = repo.emit(
        offer_id="pepper:10",
        event_type="new_listing",
        price_at_event=100,
        payload={"first_price": 100},
    )
    session.commit()
    assert evt.id is not None
    assert evt.notified == 0


def test_get_unnotified(session: Session) -> None:
    repo = DealEventRepository(session)
    e1 = repo.emit(offer_id="pepper:10", event_type="new_listing", price_at_event=100)
    e2 = repo.emit(offer_id="pepper:10", event_type="price_drop", price_at_event=80)
    session.commit()
    unread = repo.get_unnotified(limit=10)
    assert {e.id for e in unread} == {e1.id, e2.id}

    repo.mark_notified([e1.id])
    session.commit()
    unread_again = repo.get_unnotified(limit=10)
    assert {e.id for e in unread_again} == {e2.id}
```

- [ ] **Step 9.2: Run — fails**

Run: `python -m pytest tests/test_deal_events.py -v`

- [ ] **Step 9.3: Add model**

Append to `storage/models.py`:
```python
class DealEvent(Base):
    __tablename__ = "deal_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    offer_id: Mapped[str] = mapped_column(
        String, ForeignKey("offers.id"), nullable=False
    )
    product_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("products.id"), default=None
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    price_at_event: Mapped[int | None] = mapped_column(default=None)
    payload: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    notified: Mapped[int] = mapped_column(default=0)

    offer: Mapped["Offer"] = relationship(back_populates="events")
```

- [ ] **Step 9.4: Add repository**

Append to `storage/repositories.py`:
```python
class DealEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def emit(
        self,
        *,
        offer_id: str,
        event_type: str,
        price_at_event: int | None = None,
        payload: dict | None = None,
        product_id: str | None = None,
        created_at: str | None = None,
    ) -> DealEvent:
        evt = DealEvent(
            offer_id=offer_id,
            product_id=product_id,
            event_type=event_type,
            price_at_event=price_at_event,
            payload=payload,
            created_at=created_at or datetime.now().isoformat(),
        )
        self.session.add(evt)
        self.session.flush()
        return evt

    def get_unnotified(self, limit: int = 50) -> list[DealEvent]:
        return list(
            self.session.execute(
                select(DealEvent)
                .where(DealEvent.notified == 0)
                .order_by(DealEvent.created_at.asc())
                .limit(limit)
            )
            .scalars()
        )

    def mark_notified(self, ids: list[int]) -> None:
        if not ids:
            return
        self.session.execute(
            text(
                "UPDATE deal_events SET notified = 1 WHERE id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": ids},
        )
```

Alternative form (preferred — no raw SQL needed):
```python
def mark_notified(self, ids: list[int]) -> None:
    if not ids:
        return
    self.session.execute(
        update(DealEvent).where(DealEvent.id.in_(ids)).values(notified=1)
    )
```
Use this second form. Import `update` from sqlalchemy.

Import `DealEvent` at top of repositories.py.

- [ ] **Step 9.5: Test + commit**

```bash
python -m pytest tests/test_deal_events.py -v
git add storage/models.py storage/repositories.py tests/test_deal_events.py
git commit -m "feat(events): DealEvent model + repository"
```

---

## Task 10: `MatchReview`, `MatchDecision`, `FxRate` — models + thin repositories

**Files:**
- Modify: [storage/models.py](storage/models.py), [storage/repositories.py](storage/repositories.py)
- Modify: [tests/test_products_models.py](tests/test_products_models.py) (extend)

No pipeline logic yet — just the tables, minimal repo methods, one smoke test each. Pipeline comes in Phase C.

- [ ] **Step 10.1: Extend test**

Append to `tests/test_products_models.py`:
```python
def test_match_review_roundtrip(session: Session) -> None:
    from storage.models import MatchReview, Offer

    now = datetime.now().isoformat()
    session.add(
        Offer(
            id="pepper:50",
            raw_title="t",
            source="pepper",
            first_seen_at=now,
            last_seen_at=now,
        )
    )
    session.commit()
    session.add(
        MatchReview(
            offer_id="pepper:50",
            status="pending",
            priority=42,
            created_at=now,
        )
    )
    session.commit()
    row = session.query(MatchReview).one()
    assert row.status == "pending"
    assert row.priority == 42


def test_match_decision_roundtrip(session: Session) -> None:
    from storage.models import MatchDecision

    now = datetime.now().isoformat()
    session.add(
        MatchDecision(
            decision_type="auto_strong",
            actor="auto",
            confidence=0.95,
            signals={"brand": "matched"},
            created_at=now,
        )
    )
    session.commit()
    row = session.query(MatchDecision).one()
    assert row.decision_type == "auto_strong"
    assert row.signals == {"brand": "matched"}


def test_fx_rate_roundtrip(session: Session) -> None:
    from storage.models import FxRate

    now = datetime.now().isoformat()
    session.add(
        FxRate(currency="EUR", rate_to_pln=4.30, fetched_at=now, table_no="A/076/2026")
    )
    session.commit()
    row = session.query(FxRate).one()
    assert row.rate_to_pln == 4.30
```

Run: `python -m pytest tests/test_products_models.py -v` — three new tests FAIL.

- [ ] **Step 10.2: Add models**

Append to `storage/models.py`:
```python
class MatchReview(Base):
    __tablename__ = "match_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    offer_id: Mapped[str] = mapped_column(
        String, ForeignKey("offers.id"), nullable=False
    )
    candidate_product_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("products.id"), default=None
    )
    suggested_products: Mapped[list | None] = mapped_column(JSON, default=None)
    best_confidence: Mapped[float | None] = mapped_column(default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String, default="pending")
    priority: Mapped[int] = mapped_column(default=0)
    decided_by: Mapped[str | None] = mapped_column(String, default=None)
    decided_at: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class MatchDecision(Base):
    __tablename__ = "match_decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    offer_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("offers.id"), default=None
    )
    product_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("products.id"), default=None
    )
    decision_type: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float | None] = mapped_column(default=None)
    signals: Mapped[dict | None] = mapped_column(JSON, default=None)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    undo_snapshot: Mapped[dict | None] = mapped_column(JSON, default=None)


class FxRate(Base):
    __tablename__ = "fx_rates"

    currency: Mapped[str] = mapped_column(String, primary_key=True)
    rate_to_pln: Mapped[float] = mapped_column(nullable=False)
    fetched_at: Mapped[str] = mapped_column(String, nullable=False)
    table_no: Mapped[str | None] = mapped_column(String, default=None)
```

- [ ] **Step 10.3: Thin repositories**

Append to `storage/repositories.py`:
```python
class MatchReviewRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(
        self,
        *,
        offer_id: str,
        candidate_product_id: str | None = None,
        suggested_products: list | None = None,
        best_confidence: float | None = None,
        reason: str | None = None,
        priority: int = 0,
    ) -> MatchReview:
        review = MatchReview(
            offer_id=offer_id,
            candidate_product_id=candidate_product_id,
            suggested_products=suggested_products,
            best_confidence=best_confidence,
            reason=reason,
            priority=priority,
            status="pending",
            created_at=datetime.now().isoformat(),
        )
        self.session.add(review)
        return review


class MatchDecisionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        decision_type: str,
        actor: str,
        offer_id: str | None = None,
        product_id: str | None = None,
        confidence: float | None = None,
        signals: dict | None = None,
        undo_snapshot: dict | None = None,
    ) -> MatchDecision:
        decision = MatchDecision(
            offer_id=offer_id,
            product_id=product_id,
            decision_type=decision_type,
            confidence=confidence,
            signals=signals,
            actor=actor,
            created_at=datetime.now().isoformat(),
            undo_snapshot=undo_snapshot,
        )
        self.session.add(decision)
        return decision


class FxRateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, currency: str) -> FxRate | None:
        return self.session.get(FxRate, currency)

    def upsert(
        self,
        *,
        currency: str,
        rate_to_pln: float,
        fetched_at: str,
        table_no: str | None = None,
    ) -> FxRate:
        existing = self.session.get(FxRate, currency)
        if existing:
            existing.rate_to_pln = rate_to_pln
            existing.fetched_at = fetched_at
            existing.table_no = table_no
            return existing
        row = FxRate(
            currency=currency,
            rate_to_pln=rate_to_pln,
            fetched_at=fetched_at,
            table_no=table_no,
        )
        self.session.add(row)
        return row
```

Import `MatchReview, MatchDecision, FxRate` at the top.

- [ ] **Step 10.4: Test + commit**

```bash
python -m pytest tests/test_products_models.py -v
git add storage/models.py storage/repositories.py tests/test_products_models.py
git commit -m "feat(matching): add MatchReview/MatchDecision/FxRate models + thin repos"
```

---

## Task 11: Wire `OfferPayloadHistory` into `services/fetcher.py`

**Files:**
- Modify: [services/fetcher.py](services/fetcher.py)
- Create: [tests/test_ingest_event_emission.py](tests/test_ingest_event_emission.py)

- [ ] **Step 11.1: Locate the upsert path in fetcher**

Read [services/fetcher.py](services/fetcher.py) and find where `OfferRepository.upsert(...)` is called. That's the single site where every fresh fetch lands. Also note where the fetch produces the raw source payload (the DTO returned by `Source.fetch_deals()` — a `Deal` dataclass from `sources/base.py`).

- [ ] **Step 11.2: Write the integration test**

Create `tests/test_ingest_event_emission.py`:
```python
"""Integration test: ingesting a fresh fetch appends payload history + emits events."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from sources.base import Deal as FetchDTO
from storage.models import Base, DealEvent, OfferPayloadHistory
from storage.repositories import OfferRepository
from services.fetcher import DealFetcher


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_first_ingest_emits_new_listing_and_appends_payload(session: Session) -> None:
    dto = FetchDTO(
        id="pepper:111",
        title="Super deal",
        price=100,
        link="https://pepper.pl/111",
        source="pepper",
        description="d",
        temperature=42,
        image_url="",
        published_at="2026-01-01T00:00:00",
    )
    fetcher = DealFetcher(profile_name="bikes")
    fetcher.ingest_one(session, dto, profile={})  # method added in Step 11.3
    session.commit()

    events = session.query(DealEvent).all()
    assert [e.event_type for e in events] == ["new_listing"]
    assert events[0].price_at_event == 100

    payloads = session.query(OfferPayloadHistory).all()
    assert len(payloads) == 1
    assert payloads[0].offer_id == "pepper:111"
    assert payloads[0].raw_payload["title"] == "Super deal"


def test_second_ingest_with_same_price_does_not_duplicate_event(
    session: Session,
) -> None:
    dto = FetchDTO(
        id="pepper:112",
        title="t",
        price=50,
        link="",
        source="pepper",
        description="",
        temperature=0,
        image_url="",
        published_at="",
    )
    fetcher = DealFetcher(profile_name="bikes")
    fetcher.ingest_one(session, dto, profile={})
    fetcher.ingest_one(session, dto, profile={})
    session.commit()
    events = session.query(DealEvent).all()
    # one new_listing, no price_drop
    assert [e.event_type for e in events] == ["new_listing"]
    # payload history appended each ingest:
    assert session.query(OfferPayloadHistory).count() == 2


def test_reingest_with_lower_price_emits_price_drop(session: Session) -> None:
    fetcher = DealFetcher(profile_name="bikes")
    dto1 = FetchDTO(
        id="pepper:113",
        title="t",
        price=100,
        link="",
        source="pepper",
        description="",
        temperature=0,
        image_url="",
        published_at="",
    )
    fetcher.ingest_one(session, dto1, profile={})
    session.commit()
    dto2 = FetchDTO(
        id="pepper:113",
        title="t",
        price=80,
        link="",
        source="pepper",
        description="",
        temperature=0,
        image_url="",
        published_at="",
    )
    fetcher.ingest_one(session, dto2, profile={})
    session.commit()
    types = [
        e.event_type
        for e in session.query(DealEvent).order_by(DealEvent.id.asc()).all()
    ]
    assert types == ["new_listing", "price_drop"]
    drop_payload = (
        session.query(DealEvent).filter_by(event_type="price_drop").one().payload
    )
    assert drop_payload["old_price"] == 100
    assert drop_payload["new_price"] == 80
```

- [ ] **Step 11.3: Add `ingest_one` + hooks to `services/fetcher.py`**

Inside `DealFetcher`, add a new method that encapsulates single-DTO persistence; existing batch paths call it in a loop. Keep existing behavior — this is a seam for testing, not a rewrite.

```python
def ingest_one(self, session: Session, dto: Deal, profile: dict) -> Offer:
    """Upsert one DTO, append payload history, emit appropriate DealEvent."""
    from storage.repositories import (
        DealEventRepository,
        OfferPayloadHistoryRepository,
        OfferRepository,
    )

    repo = OfferRepository(session)
    payloads = OfferPayloadHistoryRepository(session)
    events = DealEventRepository(session)

    existing = session.get(Offer, dto.id)
    old_price = existing.current_price_pln if existing else None
    old_availability = existing.availability if existing else None

    offer = repo.upsert(
        id=dto.id,
        raw_title=dto.title,
        current_price_pln=dto.price,
        url=dto.link,
        source=dto.source,
        description=dto.description,
        image_url=dto.image_url,
        profile=self.profile_name,
        score=getattr(dto, "score", 0) or 0,
        category=profile.get("category", ""),
        first_seen_at="",  # repo defaults now()
        last_seen_at="",
    )

    captured_at = datetime.now().isoformat()
    payloads.append(
        offer_id=offer.id,
        raw_payload=_dto_to_payload(dto),
        captured_at=captured_at,
    )

    if existing is None:
        events.emit(
            offer_id=offer.id,
            event_type="new_listing",
            price_at_event=offer.current_price_pln,
            payload={"first_price": offer.current_price_pln},
            created_at=captured_at,
        )
    else:
        new_price = offer.current_price_pln
        if old_price and new_price and new_price < old_price:
            events.emit(
                offer_id=offer.id,
                event_type="price_drop",
                price_at_event=new_price,
                payload={
                    "old_price": old_price,
                    "new_price": new_price,
                    "diff_pln": old_price - new_price,
                },
                created_at=captured_at,
            )
        elif old_price and new_price and new_price > old_price:
            events.emit(
                offer_id=offer.id,
                event_type="price_increase",
                price_at_event=new_price,
                payload={
                    "old_price": old_price,
                    "new_price": new_price,
                    "diff_pln": new_price - old_price,
                },
                created_at=captured_at,
            )
        if (
            old_availability == "out_of_stock"
            and offer.availability == "in_stock"
        ):
            events.emit(
                offer_id=offer.id,
                event_type="back_in_stock",
                price_at_event=new_price,
                created_at=captured_at,
            )

    return offer


def _dto_to_payload(dto: Deal) -> dict:
    return {
        "id": dto.id,
        "title": dto.title,
        "price": dto.price,
        "link": dto.link,
        "source": dto.source,
        "description": dto.description,
        "temperature": dto.temperature,
        "image_url": dto.image_url,
        "published_at": dto.published_at,
    }
```

Add `from datetime import datetime` import and `from storage.models import Offer` at the top of fetcher.py. Keep the existing batch-path methods calling `repo.upsert(...)` directly for now — they'll migrate to `ingest_one` in a separate cleanup (out of scope here to avoid touching the orchestration seam).

Actually — to get end-to-end event emission on every normal run, wire `ingest_one` into the existing caller in `deal_hunter.py`. Grep for the current upsert call-site and substitute; the current call looks like (from the existing codebase):
```python
for dto in deals:
    deal_repo.upsert(
        id=dto.id,
        title=dto.title,
        price=dto.price,
        link=dto.link,
        source=dto.source,
        description=dto.description,
        image_url=dto.image_url,
        profile=profile_name,
        score=...,
        category=...,
        first_seen=...,
        last_seen=...,
    )
```
Replace with:
```python
fetcher = DealFetcher(profile_name=profile_name)
for dto in deals:
    fetcher.ingest_one(session, dto, profile=profile)
```

If the existing batch method is `DealFetcher.fetch_and_store()` (or similar), rewrite its inner loop to call `self.ingest_one(session, dto, profile)`.

- [ ] **Step 11.4: Run**

```bash
python -m pytest tests/test_ingest_event_emission.py -v
```
Expected: 3/3 PASS.

Also run the full suite to catch regressions:
```bash
python -m pytest tests/ --ignore=tests/e2e -q 2>&1 | tail -10
```
Expected: pre-A2 baseline + new tests. Fix any breakage (usually template-level contract drift).

- [ ] **Step 11.5: Commit**

```bash
git add services/fetcher.py deal_hunter.py tests/test_ingest_event_emission.py
git commit -m "feat(fetcher): emit DealEvent + append OfferPayloadHistory on ingest"
```

---

## Task 12: End-to-end validation + A2 changelog

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 12.1: Full-stack smoke**

```bash
python deal_hunter.py --list              # must print without ImportError
python deal_hunter.py --health 2>&1 | head -5  # must read state/health.json or say missing
python -c "import feedback_bot"           # clean import
```

- [ ] **Step 12.2: Migration round-trip on a real-shaped DB copy**

```bash
cp state/deals.db /tmp/pre-a2.db  # if the local DB has data
DATABASE_URL="sqlite:////tmp/pre-a2.db" \
  alembic -c storage/migrations/alembic.ini upgrade 004
DATABASE_URL="sqlite:////tmp/pre-a2.db" \
  alembic -c storage/migrations/alembic.ini downgrade 003
DATABASE_URL="sqlite:////tmp/pre-a2.db" \
  alembic -c storage/migrations/alembic.ini upgrade 004
sqlite3 /tmp/pre-a2.db "PRAGMA foreign_key_check;"
```
Expected: last command prints nothing (no FK violations).

- [ ] **Step 12.3: Grep for stragglers**

```bash
grep -rn --include='*.py' -E '(FROM|JOIN|INTO|UPDATE)\s+(deals|price_history)\b' . \
  | grep -v docs/ | grep -v venv | grep -v test_migration_003_rename
```
Expected: empty.

```bash
grep -rn --include='*.py' '\bDealRepository\b\|\bPriceHistory\b' . \
  | grep -v docs/ | grep -v venv | grep -v 'as DealModel' | grep -v 'as Deal'
```
Expected: empty (aside from aliases explicitly preserved during Task 1.14 for test readability).

- [ ] **Step 12.4: Full suite**

```bash
python -m pytest tests/ --ignore=tests/e2e -q
```
Expected: pre-A1 baseline + the new tests added in this plan (roughly +20 tests).

- [ ] **Step 12.5: A2 changelog entry**

Append to `CHANGELOG.md` under the same `## [Unreleased]`:
```markdown
- **Database**: Alembic `004` — renamed `offers.title/price/link/first_seen/last_seen` to `raw_title/current_price_pln/url/first_seen_at/last_seen_at`; renamed `price_points.deal_id/price` to `offer_id/price_pln`; added product-model columns (`product_id`, `source_native_id`, `currency_original`, `fx_rate_used`, `availability`, `attributes_hint`, `is_active`) and parallel columns on `price_points`. Backfilled `source_native_id`.
- **New schema**: `products`, `product_aliases`, `offer_payload_history` (FIFO N=10 per offer), `deal_events` (event log), `match_reviews`, `match_decisions`, `fx_rates`.
- **Ingest**: every upsert now appends to `offer_payload_history` and emits a `DealEvent` (`new_listing` / `price_drop` / `price_increase` / `back_in_stock`) via `DealFetcher.ingest_one`.
- **Compat**: dashboard, Telegram, feedback bot, Jinja templates continue to use legacy dict keys (`title`, `price`, `link`, `first_seen`, `last_seen`) via `OfferRepository._to_dict`'s dual-key output — no external contract change.
```

- [ ] **Step 12.6: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): record phase A2 products schema + event emission"
```

---

## Definition of Done

- `alembic upgrade head` applies `001`→`002`→`003`→`004` cleanly; `downgrade -1` reverses `004`; `upgrade` is idempotent.
- `grep -rn --include='*.py' -E '(FROM|JOIN|INTO|UPDATE)\s+(deals|price_history)\b' .` returns only the `003` round-trip test.
- `grep -rn --include='*.py' '\bDealRepository\b' .` returns zero matches outside docs.
- `storage.models` exports `Offer`, `PricePoint`, `Product`, `ProductAlias`, `OfferPayloadHistory`, `DealEvent`, `MatchReview`, `MatchDecision`, `FxRate`.
- `storage.repositories` exports `OfferRepository`, `PriceRepository`, `WatchlistRepository`, `AlertQueueRepository`, `FeedbackRepository`, `SeenDealRepository`, `ProductRepository`, `ProductAliasRepository`, `OfferPayloadHistoryRepository`, `DealEventRepository`, `MatchReviewRepository`, `MatchDecisionRepository`, `FxRateRepository`.
- `python -m pytest tests/ --ignore=tests/e2e -q` passes.
- `OfferPayloadHistory` never has more than 10 rows per `offer_id` after any number of ingests.
- On a real run (`python deal_hunter.py --profile bikes --verify`, or any ingest path), `DealEvent` rows appear for new offers and price changes; no exceptions; templates render.

---

## Follow-up plans (NOT this plan)

- **Phase B** — NBP FX client + attribute/identifier extractor + store YAML `identifiers:` + `attributes:` sections. Populates `fx_rates` rows, `offers.currency_original` / `fx_rate_used` correctly, `offers.attributes_hint` populated.
- **Phase C** — L1/L2 matching pipeline, golden-set evaluation, `cli/backfill_products.py`. Populates `offers.product_id`, `match_decisions`, enqueues `match_reviews`.
- **Phase D** — `/products` + `/products/{uuid}` dashboard routes, cross-source timeline.
- **Phase E** — `/review` queue UI, approve/reject/merge/split, 7-day undo.
- **Phase F** — Cutover (`PRODUCT_MODEL_ENABLED` default on, Telegram "Product" deep-link button, product-level watchlist).
- **Phase G** — Background re-match sweep.

Each gets its own plan file under `docs/superpowers/plans/`.

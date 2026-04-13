# Phase A1 — Rename `deals` → `offers` refactor (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the `deals` table to `offers` and `price_history` to `price_points` at the database and ORM layer, plus rename the corresponding Python classes (`Deal`→`Offer`, `PriceHistory`→`PricePoint`, `DealRepository`→`OfferRepository`), with the full test suite green before and after, and Alembic `upgrade`/`downgrade` round-tripping cleanly.

**Architecture:** Conservative first step of the larger products-and-offers migration (see `docs/superpowers/specs/2026-04-13-products-and-offers-design.md`). This plan changes only table names, class names, and `__tablename__` mappings. Column names inside the tables stay the same — `title`, `price`, `link`, `first_seen`, `last_seen`, `deal_id`, `recorded_at` are all preserved. That keeps `_to_dict()` keys, templates, Telegram payloads, and the entire dashboard API shape unchanged. Column renames (`title`→`raw_title`, `price`→`current_price_pln`, `link`→`url`, etc.) are deferred to Phase A2 along with the new schema (products, product_aliases, deal_events, offer_payload_history, etc.).

**Scope boundary (what this plan does NOT do):**
- No new tables (`products`, `product_aliases`, `deal_events`, `offer_payload_history`, `match_reviews`, `match_decisions`, `fx_rates`) — Phase A2.
- No column renames — Phase A2.
- No event emission on upsert — Phase A2.
- No FIFO payload history — Phase A2.
- No new behavior. Pure structural rename.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x ORM, Alembic, SQLite, pytest, FastAPI.

**Reference paths in current repo:**
- ORM models: [storage/models.py](storage/models.py)
- Repositories: [storage/repositories.py](storage/repositories.py)
- Migrations: [storage/migrations/versions/](storage/migrations/versions/) (existing: `001_baseline.py`, `002_seen_deals.py`)
- Test fixtures: [tests/conftest.py](tests/conftest.py)
- Dashboard deal reads: [dashboard/services/deal_service.py](dashboard/services/deal_service.py), [dashboard/routes/deals.py](dashboard/routes/deals.py), [dashboard/routes/watchlist.py](dashboard/routes/watchlist.py)
- Services: [services/fetcher.py](services/fetcher.py), [services/price_tracker.py](services/price_tracker.py), [services/alerter.py](services/alerter.py)
- Chart raw SQL: [visualization/charts.py](visualization/charts.py)
- CLI + bot: [deal_hunter.py](deal_hunter.py), [feedback_bot.py](feedback_bot.py)
- Migration script (referenced in tests): [scripts/migrate_json_state.py](scripts/migrate_json_state.py)

---

## File Structure

**Files created:**
- `storage/migrations/versions/003_rename_deals_to_offers.py` — Alembic revision, table renames only.
- `tests/test_migration_003_rename.py` — round-trip test for the new revision.

**Files modified (rename-only, narrow changes):**
- `storage/models.py` — rename classes + `__tablename__` strings.
- `storage/repositories.py` — rename classes + update raw-SQL table names (`FROM deals` → `FROM offers`, `FROM price_history` → `FROM price_points`, `INSERT INTO price_history` → `INSERT INTO price_points`, joins updated).
- `tests/conftest.py` — import renames + raw-SQL updates in fixture.
- `services/price_tracker.py`, `services/fetcher.py`, `services/alerter.py` — import renames + any raw SQL.
- `dashboard/services/deal_service.py`, `dashboard/routes/deals.py`, `dashboard/routes/watchlist.py` — import renames + raw SQL.
- `visualization/charts.py` — raw SQL table names.
- `deal_hunter.py`, `feedback_bot.py` — import renames.
- `scripts/migrate_json_state.py` — raw SQL table names.
- All existing test files that import `Deal`, `DealRepository`, `PriceHistory`, or contain raw SQL referencing `deals`/`price_history`. Detected via grep in Task 0.

**Files NOT modified:**
- `sources/base.py` — `Deal` dataclass (raw fetch DTO) stays named `Deal`.
- `dashboard/templates/` — templates reference `deal.title`, `deal.price` etc. (column names unchanged → dict keys unchanged → templates unchanged).
- `dashboard/schemas.py` — Pydantic schemas reference legacy field names which are dict keys, unchanged.
- `notifiers/telegram.py` — uses dict keys, unchanged.

---

## Task 0: Baseline — capture current state and collect work list

**Files:**
- Read only.

- [ ] **Step 0.1: Verify we are on a clean branch**

Run:
```bash
git status
git log --oneline -1
```

Expected: clean working tree on branch `main` (or a feature branch), most recent commit is `197f3cf docs(spec): re-align products-and-offers design to current repo`.

- [ ] **Step 0.2: Record current test count**

Run:
```bash
source venv/bin/activate
python -m pytest tests/ --ignore=tests/e2e -q 2>&1 | tail -5
```

Expected: all tests pass. Record the pass count (e.g. `250 passed`) in a scratch note — this is the target number after the rename.

- [ ] **Step 0.3: List every call-site that needs updating**

Run:
```bash
grep -rn --include='*.py' -E '\b(from storage\.models import|from storage\.repositories import)\b' .
```

Expected: list of files that import `Deal`, `PriceHistory`, `DealRepository`, or `PriceRepository` — these are the files that need import updates. Note there will also be raw SQL files found in the next grep.

Run:
```bash
grep -rn --include='*.py' -E '(FROM|JOIN|INTO|UPDATE)\s+(deals|price_history)\b' . \
  | grep -v docs/superpowers | grep -v .venv | grep -v venv
```

Expected: list of Python files with raw SQL that references `deals` or `price_history` by name. These need updating in Task 6+.

- [ ] **Step 0.4: Verify Alembic is at head**

Run:
```bash
alembic -c alembic.ini current 2>&1 || python -c "from alembic.config import Config; from alembic import command; cfg=Config('alembic.ini'); command.current(cfg)"
```

Expected: current revision is `002` (head).

No commit for Task 0 — this is reconnaissance only.

---

## Task 1: Alembic migration 003 — round-trip test first

**Files:**
- Test: `tests/test_migration_003_rename.py` (create)

- [ ] **Step 1.1: Write the failing test**

Create `tests/test_migration_003_rename.py`:

```python
"""Round-trip test for Alembic revision 003_rename_deals_to_offers."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


@pytest.fixture
def alembic_db(tmp_path: Path) -> tuple[Config, str]:
    """Fresh SQLite DB with a pre-wired Alembic config pointing to it."""
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg, db_url


def _table_names(db_url: str) -> set[str]:
    eng = create_engine(db_url)
    return set(inspect(eng).get_table_names())


def test_003_upgrade_renames_tables(alembic_db):
    cfg, db_url = alembic_db
    command.upgrade(cfg, "002")
    assert {"deals", "price_history"} <= _table_names(db_url)
    assert "offers" not in _table_names(db_url)

    command.upgrade(cfg, "003")
    tables = _table_names(db_url)
    assert "offers" in tables
    assert "price_points" in tables
    assert "deals" not in tables
    assert "price_history" not in tables


def test_003_downgrade_restores_tables(alembic_db):
    cfg, db_url = alembic_db
    command.upgrade(cfg, "003")
    command.downgrade(cfg, "002")
    tables = _table_names(db_url)
    assert "deals" in tables
    assert "price_history" in tables
    assert "offers" not in tables
    assert "price_points" not in tables


def test_003_roundtrip_preserves_row_data(alembic_db):
    """Upgrade, insert a row, downgrade, upgrade again — data survives the final upgrade."""
    cfg, db_url = alembic_db
    command.upgrade(cfg, "002")

    eng = create_engine(db_url)
    with eng.begin() as conn:
        from sqlalchemy import text

        conn.execute(
            text(
                "INSERT INTO deals (id, title, price, source, status, first_seen, last_seen)"
                " VALUES ('pepper:abc', 'Test', 100, 'pepper', 'active', '2026-01-01', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO price_history (deal_id, price, recorded_at)"
                " VALUES ('pepper:abc', 100, '2026-01-01')"
            )
        )

    command.upgrade(cfg, "003")

    with eng.connect() as conn:
        from sqlalchemy import text

        row = conn.execute(text("SELECT id, title FROM offers WHERE id='pepper:abc'")).first()
        assert row is not None
        assert row[1] == "Test"
        pp = conn.execute(
            text("SELECT deal_id, price FROM price_points WHERE deal_id='pepper:abc'")
        ).first()
        assert pp is not None
        assert pp[1] == 100
```

- [ ] **Step 1.2: Run the test to see it fail**

Run:
```bash
python -m pytest tests/test_migration_003_rename.py -v
```

Expected: FAIL with something like `Can't locate revision identified by '003'` or `ModuleNotFoundError: No module named '...003_rename_deals_to_offers'`.

- [ ] **Step 1.3: Create the Alembic revision**

Create `storage/migrations/versions/003_rename_deals_to_offers.py`:

```python
"""Rename deals -> offers, price_history -> price_points.

Revision ID: 003
Revises: 002
Create Date: 2026-04-13

Structural rename only. Column names, FK relationships, indices, and PK
values are preserved. Watchlist/feedback/seen_deals retain the column
name ``deal_id`` (it still holds the same offer id values).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Rename index first (SQLite batch-rename quirks around the old name).
    op.execute("DROP INDEX IF EXISTS idx_deals_profile_score")
    op.rename_table("deals", "offers")
    op.rename_table("price_history", "price_points")
    op.create_index("idx_offers_profile_score", "offers", ["profile", "score"])


def downgrade() -> None:
    op.drop_index("idx_offers_profile_score", table_name="offers")
    op.rename_table("price_points", "price_history")
    op.rename_table("offers", "deals")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_deals_profile_score"
        " ON deals (profile, score DESC)"
    )
```

- [ ] **Step 1.4: Re-run the round-trip test**

Run:
```bash
python -m pytest tests/test_migration_003_rename.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 1.5: Commit**

```bash
git add storage/migrations/versions/003_rename_deals_to_offers.py \
        tests/test_migration_003_rename.py
git commit -m "feat(db): add alembic revision 003 renaming deals->offers"
```

---

## Task 2: Rename ORM classes and `__tablename__`

**Files:**
- Modify: [storage/models.py](storage/models.py)

- [ ] **Step 2.1: Update `storage/models.py`**

Replace the `Deal` and `PriceHistory` class definitions. Full new file content for the affected classes (leave `Feedback`, `AlertQueue`, `WatchlistItem`, `SeenDeal` unchanged):

```python
class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[int | None] = mapped_column(default=None)
    link: Mapped[str | None] = mapped_column(Text, default=None)
    source: Mapped[str | None] = mapped_column(String, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    image_url: Mapped[str | None] = mapped_column(Text, default=None)
    profile: Mapped[str | None] = mapped_column(String, default=None)
    score: Mapped[int | None] = mapped_column(default=None)
    category: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String, default="active")
    first_seen: Mapped[str | None] = mapped_column(String, default=None)
    last_seen: Mapped[str | None] = mapped_column(String, default=None)

    prices: Mapped[list["PricePoint"]] = relationship(back_populates="offer")
    feedback_entries: Mapped[list["Feedback"]] = relationship(back_populates="offer")
    watchlist_entry: Mapped["WatchlistItem | None"] = relationship(back_populates="offer")

    __table_args__ = (Index("idx_offers_profile_score", "profile", "score"),)


class PricePoint(Base):
    __tablename__ = "price_points"

    deal_id: Mapped[str] = mapped_column(String, ForeignKey("offers.id"), primary_key=True)
    price: Mapped[int] = mapped_column(nullable=False)
    recorded_at: Mapped[str] = mapped_column(String, primary_key=True)

    offer: Mapped["Offer"] = relationship(back_populates="prices")
```

Then update the two ForeignKey targets in `Feedback` and `WatchlistItem` (same file):

```python
class Feedback(Base):
    __tablename__ = "feedback"

    deal_id: Mapped[str] = mapped_column(String, ForeignKey("offers.id"), primary_key=True)
    action: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[str] = mapped_column(String, primary_key=True)

    offer: Mapped["Offer"] = relationship(back_populates="feedback_entries")
```

```python
class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    deal_id: Mapped[str] = mapped_column(
        String, ForeignKey("offers.id"), nullable=False, unique=True
    )
    target_price: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    triggered_at: Mapped[str | None] = mapped_column(String, default=None)

    offer: Mapped["Offer"] = relationship(back_populates="watchlist_entry")
```

**Preserve `deal_id` column name** in `PricePoint`, `Feedback`, `WatchlistItem` — it still holds offer ids verbatim; only the FK target table changes.

**Preserve attribute name `price` on `PricePoint`** — column renames are Phase A2.

- [ ] **Step 2.2: Quick smoke check — import the new classes**

Run:
```bash
python -c "from storage.models import Offer, PricePoint; print(Offer.__tablename__, PricePoint.__tablename__)"
```

Expected: `offers price_points`. Any ImportError means a typo — fix before proceeding.

- [ ] **Step 2.3: Commit (tests still broken at this point; that's fine — next task fixes them)**

```bash
git add storage/models.py
git commit -m "refactor(models): rename Deal->Offer, PriceHistory->PricePoint"
```

---

## Task 3: Rename `DealRepository` to `OfferRepository` and update raw SQL

**Files:**
- Modify: [storage/repositories.py](storage/repositories.py)

This is the biggest mechanical change. Work it as a sequence of narrow edits, then one test run.

- [ ] **Step 3.1: Update imports block**

Replace the existing `from storage.models import (...)` block at the top of [storage/repositories.py](storage/repositories.py) with:

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

- [ ] **Step 3.2: Rename `class DealRepository` to `class OfferRepository`**

Change `class DealRepository:` → `class OfferRepository:`.
Change every `Deal` reference inside the class body to `Offer` (the type used in `session.get(Deal, id)`, `select(Deal)`, `func.count().select_from(Deal)`, `.where(Deal.profile == ...)`, `_to_dict(deal: Deal) -> dict`, etc.).

Also rename the local variable `deal` on the ORM row to `offer` where convenient, but this is cosmetic — keep `_to_dict`'s parameter name `deal` to avoid touching the dict keys further.

- [ ] **Step 3.3: Update raw SQL table names in `OfferRepository`**

Inside `OfferRepository.get_stats()` — change `FROM deals` → `FROM offers`:

```python
text(
    """SELECT
        COUNT(*) as total,
        COALESCE(SUM(CASE WHEN score >= :threshold THEN 1 ELSE 0 END), 0) as high_score,
        COALESCE(SUM(CASE WHEN first_seen LIKE :today THEN 1 ELSE 0 END), 0) as new_today
    FROM offers"""
)
```

Inside `OfferRepository.get_category_price_trend()` — change `FROM price_history ph JOIN deals d ON ph.deal_id = d.id` to `FROM price_points ph JOIN offers d ON ph.deal_id = d.id`.

Inside `OfferRepository._record_price()` — change `INSERT OR IGNORE INTO price_history (...)` to `INSERT OR IGNORE INTO price_points (...)`.

- [ ] **Step 3.4: Update `PriceRepository`**

**Do not rename the class** (column name `price` is unchanged in Phase A1; class name rename is cosmetic and is deferred to A2 along with `PricePoint` column rename to `price_pln`). Just update raw SQL and the internal type references.

Change every `PriceHistory` reference to `PricePoint` inside `PriceRepository` (in `select(PriceHistory)`, `.where(PriceHistory.deal_id ...)`, `func.min(PriceHistory.price)`, etc.).

Update every raw SQL reference in `PriceRepository`:
- `INSERT OR IGNORE INTO price_history (...)` → `INSERT OR IGNORE INTO price_points (...)`
- `FROM price_history` → `FROM price_points`
- `JOIN deals d ON ph.deal_id = d.id` → `JOIN offers d ON ph.deal_id = d.id`
- In `get_drops()` and `count_drops()`: inline SQL has `FROM price_history ph JOIN deals d ON ph.deal_id = d.id` — both sides updated.

- [ ] **Step 3.5: Update `WatchlistRepository` raw SQL**

In `WatchlistRepository.get_all()` and `.get_item()`, change:
```
LEFT JOIN deals d ON w.deal_id = d.id
```
to:
```
LEFT JOIN offers d ON w.deal_id = d.id
```

The `deal_id` *column* on `watchlist` stays as-is.

- [ ] **Step 3.6: Update `SeenDealRepository` raw SQL**

Inside `SeenDealRepository.cleanup_expired()`, the raw SQL deletes from `seen_deals` — that table name is unchanged. No changes needed in this method.

- [ ] **Step 3.7: Preserve the `DealRepository` export as a backward-compat alias**

At the bottom of [storage/repositories.py](storage/repositories.py), **after** the class definitions, add:

```python
# Backward-compat alias — remove after all callers migrate to OfferRepository.
DealRepository = OfferRepository
```

This avoids touching every caller in a single commit; subsequent tasks remove the alias after call-sites migrate.

- [ ] **Step 3.8: Update repository-level imports in `storage/__init__.py` if any**

Run:
```bash
grep -n 'DealRepository\|PriceRepository' storage/__init__.py 2>/dev/null || echo "no matches"
```

If matches, extend the `__init__.py` re-exports to include `OfferRepository`. Otherwise skip.

- [ ] **Step 3.9: Run the full test suite to check rename is internally consistent**

Run:
```bash
python -m pytest tests/ --ignore=tests/e2e -q 2>&1 | tail -20
```

Expected: most tests pass thanks to the `DealRepository = OfferRepository` alias. Any failures are in tests that use raw SQL `FROM deals`/`FROM price_history` — those are handled in Tasks 5–10.

- [ ] **Step 3.10: Commit**

```bash
git add storage/repositories.py storage/__init__.py
git commit -m "refactor(repos): rename DealRepository->OfferRepository, keep alias"
```

---

## Task 4: Update `tests/conftest.py`

**Files:**
- Modify: [tests/conftest.py](tests/conftest.py)

- [ ] **Step 4.1: Swap imports**

At the top of [tests/conftest.py](tests/conftest.py), change:
```python
from storage.repositories import DealRepository
```
to:
```python
from storage.repositories import OfferRepository
```

- [ ] **Step 4.2: Rename the local variable in the fixture**

Inside `dashboard_session`, change `deal_repo = DealRepository(session)` to `deal_repo = OfferRepository(session)` (keep local name `deal_repo` for minimal diff — it's idiomatic for what the callers do).

- [ ] **Step 4.3: Update raw SQL in the fixture**

The fixture inserts into `price_history` directly. Replace both occurrences of:

```python
"INSERT OR IGNORE INTO price_history (deal_id, price, recorded_at)"
```

with:

```python
"INSERT OR IGNORE INTO price_points (deal_id, price, recorded_at)"
```

- [ ] **Step 4.4: Run the full suite**

Run:
```bash
python -m pytest tests/ --ignore=tests/e2e -q 2>&1 | tail -10
```

Expected: pass count closer to baseline. Remaining failures will be in service / dashboard / chart modules still using raw SQL.

- [ ] **Step 4.5: Commit**

```bash
git add tests/conftest.py
git commit -m "test(conftest): migrate fixtures to OfferRepository and price_points"
```

---

## Task 5: Update `services/` layer raw SQL and imports

**Files:**
- Modify: [services/fetcher.py](services/fetcher.py), [services/price_tracker.py](services/price_tracker.py), [services/alerter.py](services/alerter.py), [services/types.py](services/types.py)

- [ ] **Step 5.1: Grep for what needs fixing in services/**

Run:
```bash
grep -n -E '(FROM|JOIN|INTO|UPDATE)\s+(deals|price_history)\b|DealRepository|PriceHistory\b' services/*.py
```

- [ ] **Step 5.2: Mechanical updates for each match**

For every match found in Step 5.1:

- Raw SQL `FROM deals` → `FROM offers`
- Raw SQL `JOIN deals` → `JOIN offers`
- Raw SQL `INSERT INTO price_history` → `INSERT INTO price_points`
- Raw SQL `FROM price_history` → `FROM price_points`
- Python import `from storage.repositories import DealRepository` → `from storage.repositories import OfferRepository`
- Python import `from storage.models import ... Deal ...` → `from storage.models import ... Offer ...`
- Python `from storage.models import PriceHistory` → `from storage.models import PricePoint`
- Attribute access on ORM instances: if any code reads `.title`/`.price`/`.link` on a `Deal` instance, no change needed — column names are preserved in A1.

Note: `services/types.py` has `from sources.base import Deal` — that import references the fetch-DTO dataclass in `sources/base.py`, which is **unchanged**. Leave it.

- [ ] **Step 5.3: Run the suite**

Run:
```bash
python -m pytest tests/ --ignore=tests/e2e -q 2>&1 | tail -10
```

Expected: fewer failures, approaching the baseline count.

- [ ] **Step 5.4: Commit**

```bash
git add services/
git commit -m "refactor(services): point fetcher/price_tracker/alerter at offers/price_points"
```

---

## Task 6: Update `dashboard/` layer raw SQL and imports

**Files:**
- Modify: [dashboard/services/deal_service.py](dashboard/services/deal_service.py), [dashboard/routes/deals.py](dashboard/routes/deals.py), [dashboard/routes/watchlist.py](dashboard/routes/watchlist.py), [dashboard/schemas.py](dashboard/schemas.py) (if it imports ORM types).

- [ ] **Step 6.1: Grep for work**

Run:
```bash
grep -n -E '(FROM|JOIN|INTO|UPDATE)\s+(deals|price_history)\b|DealRepository|PriceHistory\b|from storage\.models import.*\bDeal\b' dashboard/**/*.py dashboard/*.py
```

- [ ] **Step 6.2: Apply the same mechanical substitutions as Task 5**

- `FROM deals` → `FROM offers`
- `JOIN deals` → `JOIN offers`
- `INTO price_history` → `INTO price_points`
- `FROM price_history` → `FROM price_points`
- Imports: `Deal` → `Offer`, `PriceHistory` → `PricePoint`, `DealRepository` → `OfferRepository` at the import level.

**Important for `dashboard/services/deal_service.py`**: this file likely has several raw SQL window-function queries that reference `deals d` and `price_history ph` — update each. Do not change any dict key names produced by the service (`{"title": ..., "price": ...}` etc.) — that is the external contract.

- [ ] **Step 6.3: Run the suite**

Run:
```bash
python -m pytest tests/ --ignore=tests/e2e -q 2>&1 | tail -10
```

Expected: baseline pass count restored, except for visualization/charts tests (Task 7) and any migration-script tests (Task 9).

- [ ] **Step 6.4: Commit**

```bash
git add dashboard/
git commit -m "refactor(dashboard): update raw SQL and imports for offers/price_points"
```

---

## Task 7: Update `visualization/charts.py` raw SQL

**Files:**
- Modify: [visualization/charts.py](visualization/charts.py)

- [ ] **Step 7.1: Grep for raw SQL**

Run:
```bash
grep -n -E '(FROM|JOIN|INTO|UPDATE)\s+(deals|price_history)\b|PriceHistory\b' visualization/*.py
```

- [ ] **Step 7.2: Apply substitutions**

Same mechanical substitutions as Task 5: `FROM deals` → `FROM offers`, `FROM price_history` → `FROM price_points`, `JOIN deals d` → `JOIN offers d`, etc.

- [ ] **Step 7.3: Run the chart tests**

Run:
```bash
python -m pytest tests/test_charts.py -v
```

Expected: all pass.

- [ ] **Step 7.4: Commit**

```bash
git add visualization/
git commit -m "refactor(charts): update raw SQL to offers/price_points"
```

---

## Task 8: Update CLI entrypoints (`deal_hunter.py`, `feedback_bot.py`)

**Files:**
- Modify: [deal_hunter.py](deal_hunter.py), [feedback_bot.py](feedback_bot.py)

- [ ] **Step 8.1: Grep**

Run:
```bash
grep -n -E '(FROM|JOIN|INTO|UPDATE)\s+(deals|price_history)\b|DealRepository|PriceHistory\b|from storage\.models import.*\bDeal\b' deal_hunter.py feedback_bot.py
```

- [ ] **Step 8.2: Apply substitutions**

Same as Task 5. Keep CLI callback_data, command names, and any user-facing strings exactly as they were.

- [ ] **Step 8.3: Smoke test the CLI**

Run (no real fetch, just arg parsing + import health):
```bash
python deal_hunter.py --list
```

Expected: profile list prints without `ImportError` or `AttributeError`. (No profiles is fine — just no crash.)

Run:
```bash
python -c "import feedback_bot"
```

Expected: imports cleanly.

- [ ] **Step 8.4: Commit**

```bash
git add deal_hunter.py feedback_bot.py
git commit -m "refactor(cli): update deal_hunter/feedback_bot for offers/price_points"
```

---

## Task 9: Update `scripts/migrate_json_state.py` raw SQL

**Files:**
- Modify: [scripts/migrate_json_state.py](scripts/migrate_json_state.py)

- [ ] **Step 9.1: Grep**

Run:
```bash
grep -n -E '(FROM|JOIN|INTO|UPDATE)\s+(deals|price_history)\b' scripts/migrate_json_state.py
```

- [ ] **Step 9.2: Apply substitutions**

Same mechanical updates. This script is a one-shot historic JSON→SQLite migration; after rename it targets the renamed tables.

- [ ] **Step 9.3: Run the accompanying test**

Run:
```bash
python -m pytest tests/test_migrate_json_state.py -v
```

Expected: all pass.

- [ ] **Step 9.4: Commit**

```bash
git add scripts/migrate_json_state.py
git commit -m "refactor(scripts): migrate_json_state targets offers/price_points"
```

---

## Task 10: Sweep remaining tests for stray raw-SQL references

**Files:**
- Modify: any test file still using `deals` or `price_history` in raw SQL or `DealRepository`/`PriceHistory` in imports.

- [ ] **Step 10.1: Final grep**

Run:
```bash
grep -rn --include='*.py' -E '(FROM|JOIN|INTO|UPDATE)\s+(deals|price_history)\b|from storage\.models import.*\b(Deal|PriceHistory)\b|from storage\.repositories import.*\bDealRepository\b' tests/
```

Expected remaining legitimate references: the migration round-trip test (`tests/test_migration_003_rename.py`) which intentionally inserts into pre-rename tables and asserts on both pre- and post-rename names. All other matches are bugs — fix them inline.

- [ ] **Step 10.2: Apply substitutions to each offender**

For each file returned by the grep (excluding `test_migration_003_rename.py`):
- Raw SQL: `deals` → `offers`, `price_history` → `price_points`
- Imports: `Deal` → `Offer`, `PriceHistory` → `PricePoint`, `DealRepository` → `OfferRepository`

- [ ] **Step 10.3: Full test suite**

Run:
```bash
python -m pytest tests/ --ignore=tests/e2e -q 2>&1 | tail -10
```

Expected: pass count equals the baseline recorded in Task 0.2.

- [ ] **Step 10.4: Commit**

```bash
git add tests/
git commit -m "test: sweep remaining deals/price_history references to offers/price_points"
```

---

## Task 11: Remove the backward-compat `DealRepository` alias

**Files:**
- Modify: [storage/repositories.py](storage/repositories.py)

- [ ] **Step 11.1: Grep for remaining uses of `DealRepository`**

Run:
```bash
grep -rn --include='*.py' '\bDealRepository\b' . \
  | grep -v 'DealRepository = OfferRepository' \
  | grep -v docs/
```

Expected: empty output (aside from possibly the scripts / docs folders — docs are fine to keep with historical names).

If output non-empty, fix each call-site to use `OfferRepository` before proceeding.

- [ ] **Step 11.2: Remove the alias**

Delete the `DealRepository = OfferRepository` line at the bottom of [storage/repositories.py](storage/repositories.py).

- [ ] **Step 11.3: Full test suite**

Run:
```bash
python -m pytest tests/ --ignore=tests/e2e -q 2>&1 | tail -10
```

Expected: same baseline pass count.

- [ ] **Step 11.4: Commit**

```bash
git add storage/repositories.py
git commit -m "refactor(repos): drop DealRepository backward-compat alias"
```

---

## Task 12: End-to-end validation + changelog

**Files:**
- Modify: `CHANGELOG.md` (append entry).

- [ ] **Step 12.1: Alembic round-trip on a real-shaped DB**

Run:
```bash
python -m pytest tests/test_migration_003_rename.py -v
```

Expected: 3/3 pass.

- [ ] **Step 12.2: Full test suite including e2e if Playwright is available**

Run (skip e2e if browser not installed — that's a CI concern):
```bash
python -m pytest tests/ --ignore=tests/e2e -q
```

Expected: pass count matches Task 0.2 baseline.

- [ ] **Step 12.3: CLI smoke**

Run:
```bash
python deal_hunter.py --health 2>&1 | head -5
```

Expected: reads `state/health.json` (or says missing) without `no such table` errors.

- [ ] **Step 12.4: Grep for any missed references**

Run:
```bash
grep -rn --include='*.py' -E '(FROM|JOIN|INTO|UPDATE)\s+(deals|price_history)\b' . \
  | grep -v docs/ | grep -v venv | grep -v test_migration_003_rename.py
```

Expected: empty (only the migration test should knowingly reference pre-rename table names).

- [ ] **Step 12.5: Add a `CHANGELOG.md` entry**

Under the next `## [Unreleased]` or the current in-progress version section, add:

```markdown
### Changed

- **Database**: renamed tables `deals` → `offers` and `price_history` → `price_points` (Alembic revision `003_rename_deals_to_offers`). Column names, PK values, and FK relationships are preserved — watchlist/feedback/seen_deals keep the `deal_id` column name, still holding the same offer ids. Python classes renamed: `Deal` → `Offer`, `PriceHistory` → `PricePoint`, `DealRepository` → `OfferRepository`. First step of the products-and-offers migration (`docs/superpowers/specs/2026-04-13-products-and-offers-design.md`).
```

- [ ] **Step 12.6: Commit the changelog + close out**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): record phase A1 rename (deals->offers)"
```

---

## Definition of Done

- Alembic revisions `001` → `002` → `003` apply on an empty DB; `003` → `002` downgrades cleanly; `003` re-applies idempotently (`tests/test_migration_003_rename.py` green).
- ORM classes `Offer`, `PricePoint`, `OfferRepository` exported from `storage.models` / `storage.repositories`.
- `grep -rn --include='*.py' -E '(FROM|JOIN|INTO|UPDATE)\s+(deals|price_history)\b'` returns only the migration test.
- `grep -rn --include='*.py' '\bDealRepository\b'` returns zero matches outside docs.
- `python -m pytest tests/ --ignore=tests/e2e -q` pass count = baseline recorded in Task 0.2.
- CLI entrypoints (`deal_hunter.py --list`, `deal_hunter.py --health`) and `feedback_bot.py` import cleanly.

---

## Follow-up (not this plan)

- **Phase A2** — column renames (`title`→`raw_title`, `price`→`current_price_pln`, `link`→`url`, `first_seen`→`first_seen_at`, `last_seen`→`last_seen_at` on offers; `price`→`price_pln`, `deal_id`→`offer_id` on price_points), new tables (`products`, `product_aliases`, `offer_payload_history`, `deal_events`, `match_reviews`, `match_decisions`, `fx_rates`), FIFO payload history, event emission in `services/fetcher.py`. Will be a separate plan in `docs/superpowers/plans/2026-04-13-phase-a2-products-schema.md`.
- **Phase B** — attribute + identifier extractor + NBP FX (separate plan).
- **Phase C–G** — matching pipeline, dashboard, review queue, cutover, background sweep (each their own plan).

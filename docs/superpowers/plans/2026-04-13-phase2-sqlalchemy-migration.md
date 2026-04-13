# Phase 2: SQLAlchemy ORM Migration & State Consolidation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 690-line raw-SQL `storage/sqlite.py` with SQLAlchemy ORM models, session management, and domain-organized repositories. Consolidate JSON state files into SQLite. Fix N+1 query patterns.

**Architecture:** Bottom-up build: ORM models → session management → Alembic → repositories (with tests) → consumer migration → JSON state consolidation → retire `storage/sqlite.py`. Each repository is tested independently before any consumer is touched. The existing `SQLiteStorage` class stays functional until all consumers are migrated, then is deleted.

**Tech Stack:** SQLAlchemy 2.0 (Mapped types), Alembic 1.13+, pytest

**Spec:** `docs/superpowers/specs/2026-04-13-refactoring-cleanup-design.md` (Phase 2)

**Baseline:** 675 tests passing. All must still pass at end of phase.

**Key facts from codebase analysis:**
- `storage/sqlite.py`: 5 tables, 37+ public methods, single `sqlite3.Connection` with `check_same_thread=False`
- 18 files import `SQLiteStorage` (10 production, 8 test files)
- `deal_hunter.py` has dual JSON/SQLite state: `load_state()`/`save_state()` for seen-deals + price history in `state/*.json`
- N+1 hotspot: `get_price_drops()` does 2N+1 queries (per-deal `SELECT` for previous price + lowest price)
- Tests: 152 tests touch SQLiteStorage, 17 locations with direct `_conn` access in 3 test files
- Dashboard uses FastAPI `Depends(get_db)` yielding `SQLiteStorage` per request
- `feedback_bot.py` uses `with get_storage() as storage:` context manager pattern

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `storage/models.py` | SQLAlchemy ORM models (6 tables) |
| Create | `storage/database.py` | Engine, SessionLocal, `get_session()` context manager |
| Create | `storage/repositories.py` | Domain-organized repository classes |
| Create | `storage/migrations/alembic.ini` | Alembic configuration |
| Create | `storage/migrations/env.py` | Alembic environment |
| Create | `storage/migrations/script.py.mako` | Alembic template |
| Create | `storage/migrations/versions/001_baseline.py` | Baseline migration (existing 5 tables) |
| Create | `storage/migrations/versions/002_seen_deals.py` | New `seen_deals` table |
| Create | `tests/test_models.py` | ORM model tests |
| Create | `tests/test_database.py` | Session lifecycle tests |
| Create | `tests/test_repositories.py` | Repository layer tests |
| Modify | `storage/__init__.py` | Export new modules |
| Modify | `dashboard/dependencies.py` | `get_db()` → session-based |
| Modify | `dashboard/__init__.py` | Re-export updated `get_db` |
| Modify | `dashboard/services.py` | Use repositories instead of SQLiteStorage |
| Modify | `dashboard/routes/deals.py` | Use repositories + session |
| Modify | `dashboard/routes/watchlist.py` | Use repositories + session |
| Modify | `dashboard/routes/tuner.py` | Use repositories + session |
| Modify | `dashboard/routes/profiles.py` | Use repositories + session |
| Modify | `deal_hunter.py` | Replace SQLiteStorage + JSON state with repos |
| Modify | `feedback_bot.py` | Replace SQLiteStorage with repos + session |
| Modify | `visualization/charts.py` | Accept session, use repos |
| Modify | `tests/conftest.py` | Session-based fixtures |
| Modify | `tests/test_sqlite_storage.py` → rename to `tests/test_repositories.py` | Rewrite for repos |
| Modify | `tests/test_price_drops.py` | Update fixtures and assertions |
| Modify | `tests/test_feedback_bot.py` | Update fixtures |
| Modify | `tests/test_watchlist.py` | Update fixtures |
| Modify | `tests/test_quiet_hours.py` | Update fixtures |
| Modify | `tests/test_batch_queries.py` | Merge into `test_repositories.py` |
| Modify | `tests/test_charts.py` | Update mock interface |
| Modify | `tests/test_dashboard.py` | Update fixtures |
| Modify | `tests/e2e/conftest.py` | Update fixtures |
| Modify | `pyproject.toml` | Add `DATABASE_URL` env var mention |
| Modify | `.env.example` | Add `DATABASE_URL` |
| Delete | `storage/sqlite.py` | Replaced by models + database + repositories |
| Delete | `scripts/migrate_state_to_sqlite.py` | Superseded by Alembic migration |
| Delete | `tests/test_state.py` | Tests load_state/save_state which are removed |

---

### Task 1: ORM Models

**Files:**
- Create: `storage/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test for model table mapping**

```python
# tests/test_models.py
"""Tests for SQLAlchemy ORM models."""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from storage.models import (
    AlertQueue,
    Base,
    Deal,
    Feedback,
    PriceHistory,
    SeenDeal,
    WatchlistItem,
)


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


class TestTableCreation:
    def test_all_tables_created(self, engine):
        tables = inspect(engine).get_table_names()
        assert set(tables) == {
            "deals",
            "price_history",
            "feedback",
            "alert_queue",
            "watchlist",
            "seen_deals",
        }

    def test_deals_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("deals")}
        assert cols == {
            "id", "title", "price", "link", "source", "description",
            "image_url", "profile", "score", "category", "status",
            "first_seen", "last_seen",
        }

    def test_seen_deals_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("seen_deals")}
        assert cols == {"id", "deal_id", "profile", "dedup_key", "first_seen_at"}


class TestDealModel:
    def test_create_deal(self, session):
        deal = Deal(
            id="pepper:123",
            title="Test Deal",
            price=1000,
            link="https://example.com",
            source="pepper",
            description="desc",
            image_url="",
            profile="bikes",
            score=80,
            category="road",
            status="active",
            first_seen="2026-04-13T10:00:00",
            last_seen="2026-04-13T10:00:00",
        )
        session.add(deal)
        session.commit()

        loaded = session.get(Deal, "pepper:123")
        assert loaded is not None
        assert loaded.title == "Test Deal"
        assert loaded.price == 1000
        assert loaded.status == "active"

    def test_deal_relationships(self, session):
        deal = Deal(
            id="pepper:456",
            title="Bike",
            price=5000,
            link="https://example.com",
            source="pepper",
            description="",
            image_url="",
            profile="bikes",
            score=70,
            category="",
            status="active",
            first_seen="2026-04-13T10:00:00",
            last_seen="2026-04-13T10:00:00",
        )
        session.add(deal)
        session.flush()

        ph = PriceHistory(deal_id="pepper:456", price=5000, recorded_at="2026-04-13T10:00:00")
        session.add(ph)
        session.commit()

        loaded = session.get(Deal, "pepper:456")
        assert len(loaded.prices) == 1
        assert loaded.prices[0].price == 5000


class TestSeenDealModel:
    def test_create_seen_deal(self, session):
        seen = SeenDeal(
            deal_id="pepper:789",
            profile="bikes",
            dedup_key="test bike|5000",
            first_seen_at="2026-04-13T10:00:00",
        )
        session.add(seen)
        session.commit()

        result = session.query(SeenDeal).filter_by(deal_id="pepper:789").first()
        assert result is not None
        assert result.profile == "bikes"
        assert result.dedup_key == "test bike|5000"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'storage.models'`

- [ ] **Step 3: Create ORM models**

```python
# storage/models.py
"""SQLAlchemy ORM models for Deal Hunter."""

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Deal(Base):
    __tablename__ = "deals"

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

    prices: Mapped[list["PriceHistory"]] = relationship(back_populates="deal")
    feedback_entries: Mapped[list["Feedback"]] = relationship(back_populates="deal")
    watchlist_entry: Mapped["WatchlistItem | None"] = relationship(back_populates="deal")

    __table_args__ = (
        Index("idx_deals_profile_score", "profile", "score"),
    )


class PriceHistory(Base):
    __tablename__ = "price_history"

    deal_id: Mapped[str] = mapped_column(
        String, ForeignKey("deals.id"), primary_key=True
    )
    price: Mapped[int] = mapped_column(nullable=False)
    recorded_at: Mapped[str] = mapped_column(String, primary_key=True)

    deal: Mapped["Deal"] = relationship(back_populates="prices")


class Feedback(Base):
    __tablename__ = "feedback"

    # feedback table has no explicit PK in the old schema; use rowid
    deal_id: Mapped[str] = mapped_column(
        String, ForeignKey("deals.id"), primary_key=True
    )
    action: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[str] = mapped_column(String, primary_key=True)

    deal: Mapped["Deal"] = relationship(back_populates="feedback_entries")


class AlertQueue(Base):
    __tablename__ = "alert_queue"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile: Mapped[str] = mapped_column(String, nullable=False)
    alert_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    sent_at: Mapped[str | None] = mapped_column(String, default=None)


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    deal_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    target_price: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    triggered_at: Mapped[str | None] = mapped_column(String, default=None)

    deal: Mapped["Deal"] = relationship(back_populates="watchlist_entry", foreign_keys=[deal_id])


class SeenDeal(Base):
    """Replaces JSON state files for seen-deal tracking."""

    __tablename__ = "seen_deals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    deal_id: Mapped[str] = mapped_column(String, nullable=False)
    profile: Mapped[str] = mapped_column(String, nullable=False)
    dedup_key: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index("idx_seen_deals_profile_deal", "profile", "deal_id"),
    )
```

**Design notes:**
- Datetime columns are `Mapped[str]` (not `Mapped[datetime]`) to match the existing schema which stores ISO strings. Avoids data migration risk.
- `Deal.price` and other fields are `Mapped[int | None]` because the existing schema allows NULL.
- `Feedback` uses composite PK `(deal_id, created_at)` since the old schema has no explicit PK.
- `WatchlistItem.deal` relationship uses explicit `foreign_keys` because `deal_id` lacks a formal FK constraint in the old schema (added via ORM relationship only).
- `SeenDeal` is a new table — will be created via Alembic migration in Task 3.

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_models.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add storage/models.py tests/test_models.py
git commit -m "feat(storage): add SQLAlchemy ORM models for all 6 tables"
```

---

### Task 2: Database Session Management

**Files:**
- Create: `storage/database.py`
- Create: `tests/test_database.py`
- Modify: `.env.example`

- [ ] **Step 1: Write the failing test for session management**

```python
# tests/test_database.py
"""Tests for database session management."""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from storage.database import SessionLocal, engine, get_session
from storage.models import Base, Deal


@pytest.fixture(autouse=True)
def _setup_tables():
    """Create tables for each test, drop after."""
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


class TestEngine:
    def test_engine_connects(self):
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    def test_wal_mode_enabled(self):
        with engine.connect() as conn:
            mode = conn.execute(text("PRAGMA journal_mode")).scalar()
            assert mode == "wal"


class TestGetSession:
    def test_yields_session(self):
        with get_session() as session:
            assert isinstance(session, Session)

    def test_auto_commits_on_success(self):
        with get_session() as session:
            deal = Deal(
                id="test:1", title="Test", price=100, source="test",
                description="", image_url="", profile="test", score=50,
                status="active", first_seen="2026-04-13", last_seen="2026-04-13",
            )
            session.add(deal)

        # Verify committed — open new session to check
        with get_session() as session:
            loaded = session.get(Deal, "test:1")
            assert loaded is not None
            assert loaded.title == "Test"

    def test_auto_rollback_on_exception(self):
        with pytest.raises(ValueError, match="boom"):
            with get_session() as session:
                deal = Deal(
                    id="test:2", title="Fail", price=0, source="test",
                    description="", image_url="", profile="test", score=0,
                    status="active", first_seen="2026-04-13", last_seen="2026-04-13",
                )
                session.add(deal)
                session.flush()
                raise ValueError("boom")

        # Verify rolled back
        with get_session() as session:
            assert session.get(Deal, "test:2") is None


class TestSessionLocal:
    def test_creates_session(self):
        session = SessionLocal()
        assert isinstance(session, Session)
        session.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_database.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'storage.database'`

- [ ] **Step 3: Create database session module**

```python
# storage/database.py
"""SQLAlchemy engine and session management for Deal Hunter."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

_BASE_DIR = Path(__file__).parent.parent
_DEFAULT_DB = f"sqlite:///{_BASE_DIR / 'state' / 'deals.db'}"
DATABASE_URL = os.environ.get("DATABASE_URL", _DEFAULT_DB)

# Ensure the database directory exists
_db_path = DATABASE_URL.replace("sqlite:///", "")
if _db_path:
    Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):  # noqa: ANN001
    """Enable WAL mode and foreign keys for every new SQLite connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine)


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a transactional session. Commits on success, rolls back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 4: Add DATABASE_URL to .env.example**

Append to `.env.example`:
```
# Database (default: sqlite:///state/deals.db)
# DATABASE_URL=sqlite:///state/deals.db
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_database.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add storage/database.py tests/test_database.py .env.example
git commit -m "feat(storage): add SQLAlchemy session management with auto commit/rollback"
```

---

### Task 3: Alembic Initialization

**Files:**
- Create: `storage/migrations/alembic.ini`
- Create: `storage/migrations/env.py`
- Create: `storage/migrations/script.py.mako`
- Create: `storage/migrations/versions/001_baseline.py`
- Create: `storage/migrations/versions/002_seen_deals.py`

- [ ] **Step 1: Initialize Alembic directory structure**

Run:
```bash
mkdir -p storage/migrations/versions
```

- [ ] **Step 2: Create alembic.ini**

```ini
# storage/migrations/alembic.ini
[alembic]
script_location = %(here)s
sqlalchemy.url = sqlite:///state/deals.db

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 3: Create env.py**

```python
# storage/migrations/env.py
"""Alembic environment configuration."""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

# Add project root to path so models can be imported
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from storage.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_BASE_DIR = Path(__file__).parent.parent.parent
_DEFAULT_DB = f"sqlite:///{_BASE_DIR / 'state' / 'deals.db'}"


def get_url() -> str:
    return os.environ.get("DATABASE_URL", _DEFAULT_DB)


def run_migrations_offline() -> None:
    context.configure(url=get_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url())
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Create script.py.mako**

```mako
# storage/migrations/script.py.mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 5: Create baseline migration (existing 5 tables)**

```python
# storage/migrations/versions/001_baseline.py
"""Baseline — existing schema (deals, price_history, feedback, alert_queue, watchlist).

Revision ID: 001
Revises: None
Create Date: 2026-04-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deals",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("price", sa.Integer),
        sa.Column("link", sa.Text),
        sa.Column("source", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("image_url", sa.Text),
        sa.Column("profile", sa.Text),
        sa.Column("score", sa.Integer),
        sa.Column("category", sa.Text),
        sa.Column("first_seen", sa.Text),
        sa.Column("last_seen", sa.Text),
        sa.Column("status", sa.Text, server_default="active"),
    )
    op.create_index("idx_deals_profile_score", "deals", ["profile", "score"])

    op.create_table(
        "price_history",
        sa.Column("deal_id", sa.Text, sa.ForeignKey("deals.id")),
        sa.Column("price", sa.Integer, nullable=False),
        sa.Column("recorded_at", sa.Text),
        sa.PrimaryKeyConstraint("deal_id", "recorded_at"),
    )

    op.create_table(
        "feedback",
        sa.Column("deal_id", sa.Text, sa.ForeignKey("deals.id")),
        sa.Column("action", sa.Text),
        sa.Column("created_at", sa.Text),
    )

    op.create_table(
        "alert_queue",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("profile", sa.Text, nullable=False),
        sa.Column("alert_type", sa.Text, nullable=False),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("sent_at", sa.Text),
    )

    op.create_table(
        "watchlist",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("deal_id", sa.Text, nullable=False, unique=True),
        sa.Column("target_price", sa.Integer, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("triggered_at", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("watchlist")
    op.drop_table("alert_queue")
    op.drop_table("feedback")
    op.drop_table("price_history")
    op.drop_index("idx_deals_profile_score", "deals")
    op.drop_table("deals")
```

- [ ] **Step 6: Create seen_deals migration**

```python
# storage/migrations/versions/002_seen_deals.py
"""Add seen_deals table for JSON state consolidation.

Revision ID: 002
Revises: 001
Create Date: 2026-04-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seen_deals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("deal_id", sa.Text, nullable=False),
        sa.Column("profile", sa.Text, nullable=False),
        sa.Column("dedup_key", sa.Text, nullable=False),
        sa.Column("first_seen_at", sa.Text, nullable=False),
    )
    op.create_index("idx_seen_deals_profile_deal", "seen_deals", ["profile", "deal_id"])


def downgrade() -> None:
    op.drop_index("idx_seen_deals_profile_deal", "seen_deals")
    op.drop_table("seen_deals")
```

- [ ] **Step 7: Verify Alembic can run migrations on a fresh database**

Run:
```bash
cd /home/liske/Projects/deal-hunter/.claude/worktrees/refactor
DATABASE_URL="sqlite:///$(mktemp -d)/test_alembic.db" /home/liske/Projects/deal-hunter/venv/bin/python -c "
import os, sys
sys.path.insert(0, '.')
from alembic.config import Config
from alembic import command
cfg = Config('storage/migrations/alembic.ini')
cfg.set_main_option('script_location', 'storage/migrations')
cfg.set_main_option('sqlalchemy.url', os.environ['DATABASE_URL'])
command.upgrade(cfg, 'head')
print('Alembic migration to head: OK')
from sqlalchemy import create_engine, inspect
eng = create_engine(os.environ['DATABASE_URL'])
tables = inspect(eng).get_table_names()
print(f'Tables: {sorted(tables)}')
assert 'seen_deals' in tables, 'seen_deals table missing'
assert 'deals' in tables, 'deals table missing'
print('All tables present: OK')
"
```

Expected output:
```
Alembic migration to head: OK
Tables: ['alert_queue', 'alembic_version', 'deals', 'feedback', 'price_history', 'seen_deals', 'watchlist']
All tables present: OK
```

- [ ] **Step 8: Commit**

```bash
git add storage/migrations/
git commit -m "feat(storage): add Alembic migrations — baseline schema + seen_deals table"
```

---

### Task 4: DealRepository

**Files:**
- Create: `storage/repositories.py`
- Create: `tests/test_repositories.py`

- [ ] **Step 1: Write failing tests for DealRepository**

```python
# tests/test_repositories.py
"""Tests for repository layer."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models import Base, Deal, PriceHistory
from storage.repositories import DealRepository


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def deal_repo(session):
    return DealRepository(session)


def _make_deal(**overrides):
    """Helper to build Deal kwargs with defaults."""
    defaults = {
        "id": "pepper:123",
        "title": "Test Bike",
        "price": 5000,
        "link": "https://example.com",
        "source": "pepper",
        "description": "A test deal",
        "image_url": "",
        "profile": "bikes",
        "score": 80,
        "category": "road",
        "status": "active",
        "first_seen": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
    }
    defaults.update(overrides)
    return defaults


class TestDealRepositoryUpsert:
    def test_insert_new_deal(self, session, deal_repo):
        deal_repo.upsert(**_make_deal())
        session.flush()
        loaded = session.get(Deal, "pepper:123")
        assert loaded is not None
        assert loaded.title == "Test Bike"
        assert loaded.score == 80

    def test_update_existing_deal(self, session, deal_repo):
        deal_repo.upsert(**_make_deal())
        session.flush()
        deal_repo.upsert(**_make_deal(score=90, price=4500))
        session.flush()
        loaded = session.get(Deal, "pepper:123")
        assert loaded.score == 90
        assert loaded.price == 4500

    def test_upsert_preserves_status(self, session, deal_repo):
        """Upsert must NOT reset status to 'active' on update."""
        deal_repo.upsert(**_make_deal())
        session.flush()
        loaded = session.get(Deal, "pepper:123")
        loaded.status = "watching"
        session.flush()
        deal_repo.upsert(**_make_deal(score=90))
        session.flush()
        loaded = session.get(Deal, "pepper:123")
        assert loaded.status == "watching"

    def test_upsert_records_initial_price(self, session, deal_repo):
        deal_repo.upsert(**_make_deal(price=5000))
        session.flush()
        prices = session.query(PriceHistory).filter_by(deal_id="pepper:123").all()
        assert len(prices) == 1
        assert prices[0].price == 5000

    def test_upsert_records_price_change(self, session, deal_repo):
        deal_repo.upsert(**_make_deal(price=5000))
        session.flush()
        deal_repo.upsert(**_make_deal(price=4500))
        session.flush()
        prices = session.query(PriceHistory).filter_by(deal_id="pepper:123").all()
        assert len(prices) == 2

    def test_upsert_no_price_no_history(self, session, deal_repo):
        deal_repo.upsert(**_make_deal(price=0))
        session.flush()
        prices = session.query(PriceHistory).filter_by(deal_id="pepper:123").all()
        assert len(prices) == 0


class TestDealRepositoryQuery:
    @pytest.fixture(autouse=True)
    def _seed(self, session, deal_repo):
        deal_repo.upsert(**_make_deal(id="pepper:1", title="Bike A", score=90, profile="bikes", source="pepper", category="road"))
        deal_repo.upsert(**_make_deal(id="ceneo:2", title="HDD B", score=60, profile="nas_hdd", source="ceneo", category="storage"))
        deal_repo.upsert(**_make_deal(id="pepper:3", title="Bike C", score=40, profile="bikes", source="pepper", category="mtb"))
        session.flush()

    def test_get_by_id(self, deal_repo):
        deal = deal_repo.get_by_id("pepper:1")
        assert deal is not None
        assert deal["title"] == "Bike A"

    def test_get_by_id_not_found(self, deal_repo):
        assert deal_repo.get_by_id("nope:0") is None

    def test_get_filtered_by_profile(self, deal_repo):
        deals = deal_repo.get_filtered(profile="bikes")
        assert len(deals) == 2

    def test_get_filtered_by_source(self, deal_repo):
        deals = deal_repo.get_filtered(source="ceneo")
        assert len(deals) == 1

    def test_get_filtered_by_min_score(self, deal_repo):
        deals = deal_repo.get_filtered(min_score=80)
        assert len(deals) == 1

    def test_get_filtered_ordered_by_score_desc(self, deal_repo):
        deals = deal_repo.get_filtered()
        scores = [d["score"] for d in deals]
        assert scores == sorted(scores, reverse=True)

    def test_get_filtered_with_limit_offset(self, deal_repo):
        deals = deal_repo.get_filtered(limit=1, offset=1)
        assert len(deals) == 1
        assert deals[0]["score"] == 60  # second by score desc

    def test_get_by_ids(self, deal_repo):
        deals = deal_repo.get_by_ids(["pepper:1", "ceneo:2"])
        assert len(deals) == 2

    def test_get_by_ids_empty(self, deal_repo):
        assert deal_repo.get_by_ids([]) == []

    def test_count(self, deal_repo):
        assert deal_repo.count() == 3
        assert deal_repo.count(profile="bikes") == 2
        assert deal_repo.count(min_score=80) == 1

    def test_get_stats(self, deal_repo):
        stats = deal_repo.get_stats(score_threshold=70)
        assert stats["total"] == 3
        assert stats["high_score"] == 1  # score >= 70: only 90

    def test_update_status(self, session, deal_repo):
        assert deal_repo.update_status("pepper:1", "watching") is True
        session.flush()
        deal = deal_repo.get_by_id("pepper:1")
        assert deal["status"] == "watching"

    def test_update_status_not_found(self, deal_repo):
        assert deal_repo.update_status("nope:0", "watching") is False

    def test_get_filter_options(self, deal_repo):
        opts = deal_repo.get_filter_options()
        assert "pepper" in opts["sources"]
        assert "ceneo" in opts["sources"]
        assert "road" in opts["categories"]

    def test_get_by_status(self, session, deal_repo):
        deal = session.get(Deal, "pepper:1")
        deal.status = "watching"
        session.flush()
        result = deal_repo.get_by_status("watching")
        assert len(result) == 1
        assert result[0]["id"] == "pepper:1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_repositories.py::TestDealRepositoryUpsert -v`
Expected: FAIL — `ImportError: cannot import name 'DealRepository' from 'storage.repositories'`

- [ ] **Step 3: Create DealRepository**

```python
# storage/repositories.py
"""Domain-organized repository classes for Deal Hunter."""

from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from storage.models import (
    AlertQueue,
    Deal,
    Feedback,
    PriceHistory,
    SeenDeal,
    WatchlistItem,
)


class DealRepository:
    """Query and mutation wrapper for the deals table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        *,
        id: str,
        title: str,
        price: int,
        link: str = "",
        source: str = "",
        description: str = "",
        image_url: str = "",
        profile: str = "",
        score: int = 0,
        category: str = "",
        status: str = "active",
        first_seen: str = "",
        last_seen: str = "",
    ) -> Deal:
        """Insert a new deal or update last_seen, score, and price if changed."""
        now = last_seen or datetime.now().isoformat()
        existing = self.session.get(Deal, id)

        if existing:
            old_price = existing.price
            existing.last_seen = now
            existing.score = score
            existing.price = price
            # Do NOT reset status — preserve user-set status (watching, rejected, etc.)
            if old_price and price and old_price != price:
                self._record_price(id, price, now)
            return existing

        deal = Deal(
            id=id,
            title=title,
            price=price,
            link=link,
            source=source,
            description=description,
            image_url=image_url,
            profile=profile,
            score=score,
            category=category,
            status=status,
            first_seen=first_seen or now,
            last_seen=now,
        )
        self.session.add(deal)
        if price:
            self._record_price(id, price, now)
        return deal

    def _record_price(self, deal_id: str, price: int, recorded_at: str) -> None:
        """Append price to history, ignoring duplicates."""
        self.session.execute(
            text(
                "INSERT OR IGNORE INTO price_history (deal_id, price, recorded_at)"
                " VALUES (:deal_id, :price, :recorded_at)"
            ),
            {"deal_id": deal_id, "price": price, "recorded_at": recorded_at},
        )

    def get_by_id(self, deal_id: str) -> dict | None:
        """Get a single deal as dict, or None."""
        deal = self.session.get(Deal, deal_id)
        return self._to_dict(deal) if deal else None

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        """Fetch multiple deals by ID."""
        if not ids:
            return []
        stmt = select(Deal).where(Deal.id.in_(ids))
        return [self._to_dict(d) for d in self.session.scalars(stmt)]

    def get_filtered(
        self,
        *,
        profile: str | None = None,
        source: str | None = None,
        min_score: int | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict]:
        """Query deals with optional filters and pagination."""
        stmt = select(Deal)
        stmt = self._apply_filters(stmt, profile=profile, source=source, min_score=min_score, category=category, status=status)
        stmt = stmt.order_by(Deal.score.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
            if offset is not None:
                stmt = stmt.offset(offset)
        return [self._to_dict(d) for d in self.session.scalars(stmt)]

    def count(
        self,
        *,
        profile: str | None = None,
        source: str | None = None,
        min_score: int | None = None,
        category: str | None = None,
        status: str | None = None,
    ) -> int:
        """Count deals matching filters."""
        stmt = select(func.count()).select_from(Deal)
        stmt = self._apply_filters(stmt, profile=profile, source=source, min_score=min_score, category=category, status=status)
        return self.session.execute(stmt).scalar() or 0

    def get_stats(self, score_threshold: int = 70) -> dict:
        """Get aggregate deal statistics."""
        today = datetime.now().strftime("%Y-%m-%d")
        row = self.session.execute(
            text(
                """SELECT
                    COUNT(*) as total,
                    COALESCE(SUM(CASE WHEN score >= :threshold THEN 1 ELSE 0 END), 0) as high_score,
                    COALESCE(SUM(CASE WHEN first_seen LIKE :today THEN 1 ELSE 0 END), 0) as new_today
                FROM deals"""
            ),
            {"threshold": score_threshold, "today": f"{today}%"},
        ).mappings().first()
        return dict(row) if row else {"total": 0, "high_score": 0, "new_today": 0}

    def update_status(self, deal_id: str, status: str) -> bool:
        """Update a deal's status. Returns True if deal existed."""
        deal = self.session.get(Deal, deal_id)
        if not deal:
            return False
        deal.status = status
        return True

    def get_by_status(self, status: str, limit: int = 20) -> list[dict]:
        """Get deals filtered by status, ordered by last_seen descending."""
        stmt = (
            select(Deal)
            .where(Deal.status == status)
            .order_by(Deal.last_seen.desc())
            .limit(limit)
        )
        return [self._to_dict(d) for d in self.session.scalars(stmt)]

    def get_filter_options(self) -> dict:
        """Get distinct sources and categories for filter dropdowns."""
        sources = [
            r[0]
            for r in self.session.execute(
                select(Deal.source).where(Deal.source.isnot(None), Deal.source != "").distinct().order_by(Deal.source)
            )
        ]
        categories = [
            r[0]
            for r in self.session.execute(
                select(Deal.category).where(Deal.category.isnot(None), Deal.category != "").distinct().order_by(Deal.category)
            )
        ]
        return {"sources": sources, "categories": categories}

    def get_category_price_trend(self, category: str, days: int = 30) -> list[dict]:
        """Get daily average price for a category over the last N days."""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = self.session.execute(
            text(
                """SELECT DATE(ph.recorded_at) as day, AVG(ph.price) as avg_price
                FROM price_history ph
                JOIN deals d ON ph.deal_id = d.id
                WHERE d.category = :category AND ph.recorded_at >= :cutoff
                GROUP BY DATE(ph.recorded_at)
                ORDER BY day"""
            ),
            {"category": category, "cutoff": cutoff},
        ).mappings().all()
        return [{"day": r["day"], "avg_price": round(r["avg_price"])} for r in rows]

    def _apply_filters(self, stmt, *, profile, source, min_score, category, status):
        """Apply optional WHERE clauses to a statement."""
        if profile is not None:
            stmt = stmt.where(Deal.profile == profile)
        if source is not None:
            stmt = stmt.where(Deal.source == source)
        if min_score is not None:
            stmt = stmt.where(Deal.score >= min_score)
        if category is not None:
            stmt = stmt.where(Deal.category == category)
        if status is not None:
            stmt = stmt.where(Deal.status == status)
        return stmt

    @staticmethod
    def _to_dict(deal: Deal) -> dict:
        return {
            "id": deal.id,
            "title": deal.title,
            "price": deal.price,
            "link": deal.link,
            "source": deal.source,
            "description": deal.description,
            "image_url": deal.image_url,
            "profile": deal.profile,
            "score": deal.score,
            "category": deal.category,
            "status": deal.status,
            "first_seen": deal.first_seen,
            "last_seen": deal.last_seen,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_repositories.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add storage/repositories.py tests/test_repositories.py
git commit -m "feat(storage): add DealRepository with upsert, query, stats, and status"
```

---

### Task 5: PriceRepository

**Files:**
- Modify: `storage/repositories.py`
- Modify: `tests/test_repositories.py`

- [ ] **Step 1: Write failing tests for PriceRepository**

Append to `tests/test_repositories.py`:

```python
from storage.repositories import PriceRepository


@pytest.fixture
def price_repo(session):
    return PriceRepository(session)


def _seed_deal_with_prices(session, deal_id="pepper:100", prices=None):
    """Insert a deal and its price history for testing."""
    now = datetime.now().isoformat()
    deal = Deal(
        id=deal_id, title="Price Test", price=prices[-1] if prices else 1000,
        source="pepper", description="", image_url="", profile="bikes",
        score=80, category="road", status="active", first_seen=now, last_seen=now,
    )
    session.add(deal)
    session.flush()
    if prices:
        for i, p in enumerate(prices):
            ts = f"2026-04-{10+i:02d}T10:00:00"
            ph = PriceHistory(deal_id=deal_id, price=p, recorded_at=ts)
            session.add(ph)
    session.flush()


class TestPriceRepositoryBasic:
    def test_record_price(self, session, price_repo):
        _seed_deal_with_prices(session, prices=[])
        price_repo.record("pepper:100", 5000)
        session.flush()
        history = price_repo.get_history("pepper:100")
        assert len(history) == 1
        assert history[0]["price"] == 5000

    def test_get_history_chronological(self, session, price_repo):
        _seed_deal_with_prices(session, prices=[5000, 4500, 4000])
        history = price_repo.get_history("pepper:100")
        assert [h["price"] for h in history] == [5000, 4500, 4000]

    def test_get_lowest(self, session, price_repo):
        _seed_deal_with_prices(session, prices=[5000, 3000, 4000])
        assert price_repo.get_lowest("pepper:100") == 3000

    def test_get_lowest_nonexistent(self, price_repo):
        assert price_repo.get_lowest("nope:0") is None

    def test_get_previous_price(self, session, price_repo):
        _seed_deal_with_prices(session, prices=[5000, 4500, 4000])
        assert price_repo.get_previous_price("pepper:100") == 4500

    def test_get_previous_price_single_entry(self, session, price_repo):
        _seed_deal_with_prices(session, prices=[5000])
        assert price_repo.get_previous_price("pepper:100") is None


class TestPriceRepositoryBatch:
    def test_get_histories_batch(self, session, price_repo):
        _seed_deal_with_prices(session, deal_id="p:1", prices=[100, 200])
        _seed_deal_with_prices(session, deal_id="p:2", prices=[300])
        result = price_repo.get_histories_batch(["p:1", "p:2"])
        assert len(result["p:1"]) == 2
        assert len(result["p:2"]) == 1

    def test_get_histories_batch_empty(self, price_repo):
        assert price_repo.get_histories_batch([]) == {}

    def test_get_lowest_prices_batch(self, session, price_repo):
        _seed_deal_with_prices(session, deal_id="p:1", prices=[100, 50])
        _seed_deal_with_prices(session, deal_id="p:2", prices=[300, 200])
        result = price_repo.get_lowest_prices_batch(["p:1", "p:2"])
        assert result["p:1"] == 50
        assert result["p:2"] == 200

    def test_get_sparkline_data_batch(self, session, price_repo):
        _seed_deal_with_prices(session, deal_id="p:1", prices=[100, 200, 300, 400, 500])
        result = price_repo.get_sparkline_data_batch(["p:1"], limit=3)
        assert len(result["p:1"]) == 3


class TestPriceRepositoryDrops:
    """Tests for get_drops() — the N+1 fix using window functions."""

    @pytest.fixture(autouse=True)
    def _seed(self, session):
        # Deal with price drop: 5000 -> 4000
        _seed_deal_with_prices(session, deal_id="p:drop", prices=[5000, 4000])
        # Deal with price increase: 3000 -> 4000
        _seed_deal_with_prices(session, deal_id="p:up", prices=[3000, 4000])
        # Deal with single price (no change)
        _seed_deal_with_prices(session, deal_id="p:flat", prices=[2000])

    def test_finds_drops(self, price_repo):
        drops = price_repo.get_drops(days=30)
        drop_ids = [d["id"] for d in drops]
        assert "p:drop" in drop_ids
        assert "p:up" not in drop_ids
        assert "p:flat" not in drop_ids

    def test_drop_fields(self, price_repo):
        drops = price_repo.get_drops(days=30)
        drop = next(d for d in drops if d["id"] == "p:drop")
        assert drop["old_price"] == 5000
        assert drop["new_price"] == 4000
        assert drop["diff_pln"] == 1000
        assert drop["diff_percent"] == 20.0
        assert "is_lowest_ever" in drop

    def test_count_drops(self, price_repo):
        assert price_repo.count_drops(days=30) >= 1

    def test_drops_with_profile_filter(self, price_repo):
        drops = price_repo.get_drops(days=30, profile="bikes")
        # All seeded deals have profile "bikes"
        assert len(drops) >= 1

    def test_drops_with_min_percent_filter(self, price_repo):
        drops = price_repo.get_drops(days=30, min_drop_percent=50)
        assert len(drops) == 0  # 20% drop doesn't meet 50% threshold
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_repositories.py::TestPriceRepositoryBasic -v`
Expected: FAIL — `ImportError: cannot import name 'PriceRepository'`

- [ ] **Step 3: Add PriceRepository to repositories.py**

Append to `storage/repositories.py`:

```python
class PriceRepository:
    """Query and mutation wrapper for price_history table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, deal_id: str, price: int) -> None:
        """Append a price entry to history."""
        now = datetime.now().isoformat()
        self.session.execute(
            text(
                "INSERT OR IGNORE INTO price_history (deal_id, price, recorded_at)"
                " VALUES (:deal_id, :price, :recorded_at)"
            ),
            {"deal_id": deal_id, "price": price, "recorded_at": now},
        )

    def get_history(self, deal_id: str) -> list[dict]:
        """Get price history ordered chronologically."""
        stmt = (
            select(PriceHistory)
            .where(PriceHistory.deal_id == deal_id)
            .order_by(PriceHistory.recorded_at)
        )
        return [
            {"deal_id": p.deal_id, "price": p.price, "recorded_at": p.recorded_at}
            for p in self.session.scalars(stmt)
        ]

    def get_lowest(self, deal_id: str) -> int | None:
        """Get lowest price ever recorded for a deal."""
        result = self.session.execute(
            select(func.min(PriceHistory.price)).where(PriceHistory.deal_id == deal_id)
        ).scalar()
        return int(result) if result is not None else None

    def get_previous_price(self, deal_id: str) -> int | None:
        """Get the most recent price before the current one."""
        rows = self.session.execute(
            select(PriceHistory.price)
            .where(PriceHistory.deal_id == deal_id)
            .order_by(PriceHistory.recorded_at.desc())
            .limit(2)
        ).scalars().all()
        return int(rows[1]) if len(rows) >= 2 else None

    def get_histories_batch(self, deal_ids: list[str]) -> dict[str, list[dict]]:
        """Fetch price history for multiple deals in one query."""
        if not deal_ids:
            return {}
        result: dict[str, list[dict]] = {did: [] for did in deal_ids}
        stmt = (
            select(PriceHistory)
            .where(PriceHistory.deal_id.in_(deal_ids))
            .order_by(PriceHistory.recorded_at)
        )
        for p in self.session.scalars(stmt):
            result[p.deal_id].append(
                {"deal_id": p.deal_id, "price": p.price, "recorded_at": p.recorded_at}
            )
        return result

    def get_lowest_prices_batch(self, deal_ids: list[str]) -> dict[str, int | None]:
        """Fetch lowest price for multiple deals in one query."""
        if not deal_ids:
            return {}
        result: dict[str, int | None] = {did: None for did in deal_ids}
        rows = self.session.execute(
            select(PriceHistory.deal_id, func.min(PriceHistory.price).label("lowest"))
            .where(PriceHistory.deal_id.in_(deal_ids))
            .group_by(PriceHistory.deal_id)
        ).all()
        for row in rows:
            result[row[0]] = int(row[1])
        return result

    def get_sparkline_data_batch(
        self, deal_ids: list[str], limit: int = 10
    ) -> dict[str, list[int]]:
        """Fetch last N price points per deal for sparkline rendering."""
        if not deal_ids:
            return {}
        placeholders = ",".join(f":id_{i}" for i in range(len(deal_ids)))
        params = {f"id_{i}": did for i, did in enumerate(deal_ids)}
        params["limit"] = limit
        rows = self.session.execute(
            text(
                f"SELECT deal_id, price FROM ("  # noqa: S608
                f" SELECT deal_id, price, recorded_at,"
                f" ROW_NUMBER() OVER (PARTITION BY deal_id ORDER BY recorded_at DESC) as rn"
                f" FROM price_history"
                f" WHERE deal_id IN ({placeholders})"
                f") WHERE rn <= :limit ORDER BY deal_id, recorded_at"
            ),
            params,
        ).all()
        result: dict[str, list[int]] = {}
        for row in rows:
            result.setdefault(row[0], []).append(row[1])
        return result

    def get_drops(
        self,
        *,
        days: int = 7,
        profile: str | None = None,
        min_drop_percent: float = 0,
    ) -> list[dict]:
        """Get price drops in the last N days using window functions (single query, no N+1).

        Uses LAG() for previous price and MIN() OVER for lowest-ever detection.
        """
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        profile_filter = "AND d.profile = :profile" if profile else ""
        params: dict = {"cutoff": cutoff}
        if profile:
            params["profile"] = profile

        rows = self.session.execute(
            text(
                f"""WITH ranked AS (
                    SELECT ph.deal_id, ph.price, ph.recorded_at,
                           LAG(ph.price) OVER (PARTITION BY ph.deal_id ORDER BY ph.recorded_at) as prev_price,
                           MIN(ph.price) OVER (PARTITION BY ph.deal_id) as lowest_price,
                           ROW_NUMBER() OVER (PARTITION BY ph.deal_id ORDER BY ph.recorded_at DESC) as rn
                    FROM price_history ph
                    JOIN deals d ON ph.deal_id = d.id
                    WHERE 1=1 {profile_filter}
                )
                SELECT d.*, ranked.price as new_price, ranked.prev_price,
                       ranked.lowest_price, ranked.recorded_at as drop_date
                FROM ranked
                JOIN deals d ON d.id = ranked.deal_id
                WHERE ranked.prev_price IS NOT NULL
                  AND ranked.price < ranked.prev_price
                  AND ranked.recorded_at >= :cutoff
                  AND ranked.rn = 1
                ORDER BY ranked.recorded_at DESC"""
            ),
            params,
        ).mappings().all()

        results = []
        for row in rows:
            old_price = row["prev_price"]
            new_price = row["new_price"]
            diff_pln = old_price - new_price
            diff_percent = (diff_pln / old_price) * 100 if old_price > 0 else 0

            if diff_percent < min_drop_percent:
                continue

            results.append({
                "id": row["id"],
                "title": row["title"],
                "price": row["price"],
                "link": row["link"],
                "source": row["source"],
                "description": row["description"],
                "image_url": row["image_url"],
                "profile": row["profile"],
                "score": row["score"],
                "category": row["category"],
                "status": row["status"],
                "first_seen": row["first_seen"],
                "last_seen": row["last_seen"],
                "old_price": old_price,
                "new_price": new_price,
                "diff_pln": diff_pln,
                "diff_percent": round(diff_percent, 1),
                "is_lowest_ever": new_price <= row["lowest_price"],
                "drop_date": row["drop_date"],
            })
        return results

    def count_drops(self, days: int = 7) -> int:
        """Count deals with price drops in last N days (efficient COUNT)."""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        result = self.session.execute(
            text(
                """WITH ranked AS (
                    SELECT ph.deal_id, ph.price,
                           LAG(ph.price) OVER (PARTITION BY ph.deal_id ORDER BY ph.recorded_at) as prev_price,
                           ROW_NUMBER() OVER (PARTITION BY ph.deal_id ORDER BY ph.recorded_at DESC) as rn
                    FROM price_history ph
                    WHERE ph.recorded_at >= :cutoff
                )
                SELECT COUNT(*) FROM ranked
                WHERE prev_price IS NOT NULL AND price < prev_price AND rn = 1"""
            ),
            {"cutoff": cutoff},
        ).scalar()
        return result or 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_repositories.py -v -k "Price"`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add storage/repositories.py tests/test_repositories.py
git commit -m "feat(storage): add PriceRepository with N+1-free get_drops using window functions"
```

---

### Task 6: WatchlistRepository

**Files:**
- Modify: `storage/repositories.py`
- Modify: `tests/test_repositories.py`

- [ ] **Step 1: Write failing tests for WatchlistRepository**

Append to `tests/test_repositories.py`:

```python
from storage.repositories import WatchlistRepository
from storage.models import WatchlistItem


@pytest.fixture
def watchlist_repo(session):
    return WatchlistRepository(session)


def _seed_deal(session, deal_id="pepper:w1"):
    """Insert a deal for FK reference in watchlist tests."""
    deal = Deal(
        id=deal_id, title="Watchlist Test", price=5000, source="pepper",
        description="", image_url="", profile="bikes", score=80,
        category="road", status="active",
        first_seen=datetime.now().isoformat(), last_seen=datetime.now().isoformat(),
    )
    session.add(deal)
    session.flush()


class TestWatchlistRepository:
    def test_add(self, session, watchlist_repo):
        _seed_deal(session)
        result = watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        assert result is True

    def test_add_duplicate(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        assert watchlist_repo.add("pepper:w1", 3000) is False

    def test_remove(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        assert watchlist_repo.remove("pepper:w1") is True

    def test_remove_nonexistent(self, watchlist_repo):
        assert watchlist_repo.remove("nope:0") is False

    def test_get_all(self, session, watchlist_repo):
        _seed_deal(session, "pepper:w1")
        _seed_deal(session, "pepper:w2")
        watchlist_repo.add("pepper:w1", 4000)
        watchlist_repo.add("pepper:w2", 3000)
        session.flush()
        items = watchlist_repo.get_all()
        assert len(items) == 2

    def test_get_item(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        item = watchlist_repo.get_item("pepper:w1")
        assert item is not None
        assert item["target_price"] == 4000
        assert item["title"] == "Watchlist Test"

    def test_update_target_price(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        assert watchlist_repo.update_target_price("pepper:w1", 3500) is True
        item = watchlist_repo.get_item("pepper:w1")
        assert item["target_price"] == 3500

    def test_check_trigger_met(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        result = watchlist_repo.check_trigger("pepper:w1", current_price=3500)
        assert result is not None
        assert result["target_price"] == 4000

    def test_check_trigger_not_met(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        assert watchlist_repo.check_trigger("pepper:w1", current_price=5000) is None

    def test_mark_triggered(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        watchlist_repo.mark_triggered("pepper:w1")
        session.flush()
        # After triggering, check_trigger should return None
        assert watchlist_repo.check_trigger("pepper:w1", current_price=3000) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_repositories.py::TestWatchlistRepository -v`
Expected: FAIL — `ImportError: cannot import name 'WatchlistRepository'`

- [ ] **Step 3: Add WatchlistRepository to repositories.py**

Append to `storage/repositories.py`:

```python
class WatchlistRepository:
    """Query and mutation wrapper for watchlist table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, deal_id: str, target_price: int) -> bool:
        """Add a deal to watchlist. Returns False if already exists."""
        existing = self.session.query(WatchlistItem).filter_by(deal_id=deal_id).first()
        if existing:
            return False
        item = WatchlistItem(
            deal_id=deal_id,
            target_price=target_price,
            created_at=datetime.now().isoformat(),
        )
        self.session.add(item)
        return True

    def remove(self, deal_id: str) -> bool:
        """Remove from watchlist. Returns True if found and removed."""
        item = self.session.query(WatchlistItem).filter_by(deal_id=deal_id).first()
        if not item:
            return False
        self.session.delete(item)
        return True

    def get_all(self) -> list[dict]:
        """Get all watchlist items with deal info."""
        rows = self.session.execute(
            text(
                """SELECT w.deal_id, w.target_price, w.created_at, w.triggered_at,
                          d.title, d.price as current_price, d.link, d.source
                   FROM watchlist w
                   LEFT JOIN deals d ON w.deal_id = d.id
                   ORDER BY w.created_at DESC"""
            )
        ).mappings().all()
        return [dict(r) for r in rows]

    def get_item(self, deal_id: str) -> dict | None:
        """Get a single watchlist item with deal info."""
        row = self.session.execute(
            text(
                """SELECT w.deal_id, w.target_price, w.created_at, w.triggered_at,
                          d.title, d.price as current_price, d.link, d.source
                   FROM watchlist w
                   LEFT JOIN deals d ON w.deal_id = d.id
                   WHERE w.deal_id = :deal_id"""
            ),
            {"deal_id": deal_id},
        ).mappings().first()
        return dict(row) if row else None

    def update_target_price(self, deal_id: str, target_price: int) -> bool:
        """Update target price. Returns True if found."""
        item = self.session.query(WatchlistItem).filter_by(deal_id=deal_id).first()
        if not item:
            return False
        item.target_price = target_price
        return True

    def check_trigger(self, deal_id: str, current_price: int) -> dict | None:
        """Check if current price meets watchlist target. Returns entry if triggered."""
        item = (
            self.session.query(WatchlistItem)
            .filter_by(deal_id=deal_id)
            .filter(WatchlistItem.triggered_at.is_(None))
            .first()
        )
        if item and current_price <= item.target_price:
            return {"deal_id": item.deal_id, "target_price": item.target_price}
        return None

    def mark_triggered(self, deal_id: str) -> None:
        """Mark a watchlist entry as triggered."""
        item = self.session.query(WatchlistItem).filter_by(deal_id=deal_id).first()
        if item:
            item.triggered_at = datetime.now().isoformat()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_repositories.py::TestWatchlistRepository -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add storage/repositories.py tests/test_repositories.py
git commit -m "feat(storage): add WatchlistRepository with CRUD and trigger checking"
```

---

### Task 7: AlertQueueRepository + FeedbackRepository

**Files:**
- Modify: `storage/repositories.py`
- Modify: `tests/test_repositories.py`

- [ ] **Step 1: Write failing tests for both repositories**

Append to `tests/test_repositories.py`:

```python
from storage.repositories import AlertQueueRepository, FeedbackRepository


@pytest.fixture
def alert_repo(session):
    return AlertQueueRepository(session)


@pytest.fixture
def feedback_repo(session):
    return FeedbackRepository(session)


class TestAlertQueueRepository:
    def test_queue_alert(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", '{"title": "test"}')
        session.flush()
        pending = alert_repo.get_pending()
        assert len(pending) == 1
        assert pending[0]["profile"] == "bikes"

    def test_get_pending_filters_by_profile(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", '{"a": 1}')
        alert_repo.queue("nas_hdd", "deal", '{"b": 2}')
        session.flush()
        assert len(alert_repo.get_pending(profile="bikes")) == 1

    def test_get_pending_excludes_sent(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", '{"a": 1}')
        session.flush()
        pending = alert_repo.get_pending()
        alert_repo.mark_sent([p["id"] for p in pending])
        session.flush()
        assert len(alert_repo.get_pending()) == 0

    def test_mark_sent_empty_list(self, alert_repo):
        alert_repo.mark_sent([])  # should not error

    def test_get_pending_ordered_by_created_at(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", '{"first": true}')
        alert_repo.queue("bikes", "deal", '{"second": true}')
        session.flush()
        pending = alert_repo.get_pending()
        assert len(pending) == 2


class TestFeedbackRepository:
    @pytest.fixture(autouse=True)
    def _seed_deal(self, session):
        _seed_deal_with_prices(session, deal_id="pepper:fb1", prices=[])

    def test_record_feedback(self, session, feedback_repo):
        feedback_repo.record("pepper:fb1", "watch")
        session.flush()

    def test_get_stats(self, session, feedback_repo):
        feedback_repo.record("pepper:fb1", "watch")
        feedback_repo.record("pepper:fb1", "watch")
        feedback_repo.record("pepper:fb1", "skip")
        session.flush()
        stats = feedback_repo.get_stats()
        assert stats["watch"] == 2
        assert stats["skip"] == 1

    def test_get_stats_empty(self, feedback_repo):
        assert feedback_repo.get_stats() == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_repositories.py::TestAlertQueueRepository -v`
Expected: FAIL — `ImportError: cannot import name 'AlertQueueRepository'`

- [ ] **Step 3: Add both repositories to repositories.py**

Append to `storage/repositories.py`:

```python
class AlertQueueRepository:
    """Query and mutation wrapper for alert_queue table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def queue(self, profile: str, alert_type: str, payload_json: str, topic_id: str | None = None) -> None:
        """Queue an alert for later sending."""
        alert = AlertQueue(
            profile=profile,
            alert_type=alert_type,
            payload=payload_json,
            created_at=datetime.now().isoformat(),
        )
        self.session.add(alert)

    def get_pending(self, profile: str | None = None) -> list[dict]:
        """Get unsent alerts, ordered by creation time."""
        stmt = select(AlertQueue).where(AlertQueue.sent_at.is_(None))
        if profile is not None:
            stmt = stmt.where(AlertQueue.profile == profile)
        stmt = stmt.order_by(AlertQueue.created_at.asc())
        return [
            {
                "id": a.id,
                "profile": a.profile,
                "alert_type": a.alert_type,
                "payload": a.payload,
                "created_at": a.created_at,
            }
            for a in self.session.scalars(stmt)
        ]

    def mark_sent(self, alert_ids: list[int]) -> None:
        """Mark alerts as sent."""
        if not alert_ids:
            return
        now = datetime.now().isoformat()
        self.session.execute(
            text(
                f"UPDATE alert_queue SET sent_at = :now"  # noqa: S608
                f" WHERE id IN ({','.join(f':id_{i}' for i in range(len(alert_ids)))})"
            ),
            {"now": now, **{f"id_{i}": aid for i, aid in enumerate(alert_ids)}},
        )


class FeedbackRepository:
    """Query and mutation wrapper for feedback table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, deal_id: str, action: str) -> None:
        """Record user feedback on a deal."""
        fb = Feedback(
            deal_id=deal_id,
            action=action,
            created_at=datetime.now().isoformat(),
        )
        self.session.add(fb)

    def get_stats(self) -> dict[str, int]:
        """Get counts of feedback actions."""
        rows = self.session.execute(
            select(Feedback.action, func.count().label("cnt")).group_by(Feedback.action)
        ).all()
        return {row[0]: row[1] for row in rows}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_repositories.py -v -k "AlertQueue or Feedback"`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add storage/repositories.py tests/test_repositories.py
git commit -m "feat(storage): add AlertQueueRepository and FeedbackRepository"
```

---

### Task 8: SeenDealRepository

**Files:**
- Modify: `storage/repositories.py`
- Modify: `tests/test_repositories.py`

- [ ] **Step 1: Write failing tests for SeenDealRepository**

Append to `tests/test_repositories.py`:

```python
from storage.repositories import SeenDealRepository


@pytest.fixture
def seen_repo(session):
    return SeenDealRepository(session)


class TestSeenDealRepository:
    def test_mark_seen(self, session, seen_repo):
        seen_repo.mark_seen("pepper:100", "bikes", "test bike|5000")
        session.flush()
        assert seen_repo.is_seen("pepper:100", "bikes") is True

    def test_is_seen_false(self, seen_repo):
        assert seen_repo.is_seen("pepper:999", "bikes") is False

    def test_is_seen_wrong_profile(self, session, seen_repo):
        seen_repo.mark_seen("pepper:100", "bikes", "test|5000")
        session.flush()
        assert seen_repo.is_seen("pepper:100", "nas_hdd") is False

    def test_cleanup_expired(self, session, seen_repo):
        # Insert an old entry
        old_seen = SeenDeal(
            deal_id="pepper:old",
            profile="bikes",
            dedup_key="old|1000",
            first_seen_at="2020-01-01T00:00:00",
        )
        session.add(old_seen)
        # Insert a recent entry
        seen_repo.mark_seen("pepper:new", "bikes", "new|2000")
        session.flush()

        seen_repo.cleanup_expired(ttl_days=14)
        session.flush()

        assert seen_repo.is_seen("pepper:old", "bikes") is False
        assert seen_repo.is_seen("pepper:new", "bikes") is True

    def test_get_seen_ids(self, session, seen_repo):
        seen_repo.mark_seen("pepper:1", "bikes", "a|1000")
        seen_repo.mark_seen("pepper:2", "bikes", "b|2000")
        seen_repo.mark_seen("pepper:3", "nas_hdd", "c|3000")
        session.flush()
        ids = seen_repo.get_seen_ids("bikes")
        assert "pepper:1" in ids
        assert "pepper:2" in ids
        assert "pepper:3" not in ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_repositories.py::TestSeenDealRepository -v`
Expected: FAIL — `ImportError: cannot import name 'SeenDealRepository'`

- [ ] **Step 3: Add SeenDealRepository to repositories.py**

Append to `storage/repositories.py`:

```python
class SeenDealRepository:
    """Replaces JSON state files for seen-deal tracking."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def mark_seen(self, deal_id: str, profile: str, dedup_key: str) -> None:
        """Mark a deal as seen for a profile."""
        seen = SeenDeal(
            deal_id=deal_id,
            profile=profile,
            dedup_key=dedup_key,
            first_seen_at=datetime.now().isoformat(),
        )
        self.session.add(seen)

    def is_seen(self, deal_id: str, profile: str) -> bool:
        """Check if a deal has been seen for a profile (within TTL)."""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=14)).isoformat()
        result = (
            self.session.query(SeenDeal)
            .filter(
                SeenDeal.deal_id == deal_id,
                SeenDeal.profile == profile,
                SeenDeal.first_seen_at > cutoff,
            )
            .first()
        )
        return result is not None

    def get_seen_ids(self, profile: str) -> set[str]:
        """Get all seen deal IDs for a profile (within TTL)."""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=14)).isoformat()
        rows = self.session.execute(
            select(SeenDeal.deal_id)
            .where(SeenDeal.profile == profile, SeenDeal.first_seen_at > cutoff)
        ).scalars().all()
        return set(rows)

    def cleanup_expired(self, ttl_days: int = 14) -> int:
        """Delete entries older than TTL. Returns count deleted."""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=ttl_days)).isoformat()
        result = self.session.execute(
            text("DELETE FROM seen_deals WHERE first_seen_at <= :cutoff"),
            {"cutoff": cutoff},
        )
        return result.rowcount
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_repositories.py::TestSeenDealRepository -v`
Expected: All PASS

- [ ] **Step 5: Run ALL repository tests to confirm nothing broke**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_repositories.py tests/test_models.py tests/test_database.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add storage/repositories.py tests/test_repositories.py
git commit -m "feat(storage): add SeenDealRepository — replaces JSON state file tracking"
```

---

### Task 9: Update storage/__init__.py and Dashboard Dependencies

**Files:**
- Modify: `storage/__init__.py`
- Modify: `dashboard/dependencies.py`
- Modify: `dashboard/__init__.py`

- [ ] **Step 1: Update storage/__init__.py to export new modules**

Read `storage/__init__.py` first. Then update to export both old (for backward compat during transition) and new:

```python
# storage/__init__.py
"""Storage layer — SQLAlchemy ORM models, session management, and repositories."""

from storage.database import SessionLocal, engine, get_session
from storage.models import (
    AlertQueue,
    Base,
    Deal,
    Feedback,
    PriceHistory,
    SeenDeal,
    WatchlistItem,
)
from storage.repositories import (
    AlertQueueRepository,
    DealRepository,
    FeedbackRepository,
    PriceRepository,
    SeenDealRepository,
    WatchlistRepository,
)
from storage.sqlite import SQLiteStorage  # kept until all consumers migrated

__all__ = [
    "AlertQueue",
    "AlertQueueRepository",
    "Base",
    "Deal",
    "DealRepository",
    "Feedback",
    "FeedbackRepository",
    "PriceHistory",
    "PriceRepository",
    "SQLiteStorage",
    "SeenDeal",
    "SeenDealRepository",
    "SessionLocal",
    "WatchlistItem",
    "WatchlistRepository",
    "engine",
    "get_session",
]
```

- [ ] **Step 2: Update dashboard/dependencies.py**

Replace `get_db()` to yield a session instead of `SQLiteStorage`. Keep backward compatibility by providing `get_db` as an alias that the route files can use during the transition:

```python
# dashboard/dependencies.py
"""Shared dependencies for dashboard routes."""

import os
import re
from collections.abc import Iterator
from pathlib import Path

import yaml
from fastapi import HTTPException
from sqlalchemy.orm import Session

from storage.database import get_session

BASE_DIR = Path(__file__).parent.parent
PROFILES_DIR = Path(os.environ.get("DEAL_HUNTER_PROFILES_DIR", str(BASE_DIR / "profiles")))

_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a SQLAlchemy session with auto commit/rollback."""
    with get_session() as session:
        yield session


def safe_profile_path(name: str) -> Path:
    """Validate profile name and return resolved path, or raise 400."""
    if not _PROFILE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid profile name")
    path = (PROFILES_DIR / f"{name}.yaml").resolve()
    if not path.is_relative_to(PROFILES_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid profile name")
    return path


def safe_load_profile(name: str) -> dict | None:
    """Load profile YAML directly from PROFILES_DIR (respects env var override)."""
    path = safe_profile_path(name)
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return dict(data) if data else None
    except (yaml.YAMLError, OSError):
        return None


def get_profiles() -> list[str]:
    """Get available profile names from PROFILES_DIR (respects env var override)."""
    if not PROFILES_DIR.exists():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.yaml"))
```

- [ ] **Step 3: Update dashboard/__init__.py re-exports**

The re-export line `from dashboard.dependencies import get_db as get_db` stays — tests import `get_db` from `dashboard`. No changes needed since the function name didn't change, only the return type (Session instead of SQLiteStorage).

- [ ] **Step 4: Commit**

```bash
git add storage/__init__.py dashboard/dependencies.py
git commit -m "refactor(dashboard): switch get_db() from SQLiteStorage to SQLAlchemy session"
```

---

### Task 10: Migrate Dashboard Routes

**Files:**
- Modify: `dashboard/routes/deals.py`
- Modify: `dashboard/routes/watchlist.py`
- Modify: `dashboard/routes/tuner.py`
- Modify: `dashboard/routes/profiles.py`
- Modify: `dashboard/services.py`

This task replaces all `SQLiteStorage` method calls in dashboard routes with repository calls. Every route handler that receives `db: SQLiteStorage = Depends(get_db)` changes to `session: Session = Depends(get_db)` and creates repositories from the session.

- [ ] **Step 1: Update dashboard/services.py**

Replace `SQLiteStorage` dependency with `Session`:

```python
# dashboard/services.py
"""Business logic for the Deal Hunter dashboard, decoupled from HTTP routing."""

import os

from sqlalchemy.orm import Session

from storage.repositories import DealRepository, PriceRepository

DEALS_PER_PAGE = int(os.getenv("DEALS_PER_PAGE", "50"))
SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD", "70"))


class DealService:
    """Encapsulates deal-related business logic."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.deals = DealRepository(session)
        self.prices = PriceRepository(session)

    def get_comparison_data(self, deal_ids: list[str]) -> dict:
        """Batch-fetch deals, price histories, and lowest prices."""
        deal_ids = deal_ids[:5]
        deals = self.deals.get_by_ids(deal_ids) if deal_ids else []
        id_list = [d["id"] for d in deals]
        return {
            "deals": deals,
            "price_histories": self.prices.get_histories_batch(id_list),
            "lowest_prices": self.prices.get_lowest_prices_batch(id_list),
        }

    def get_sparklines(self, deals: list[dict]) -> dict[str, list[int]]:
        """Get sparkline price data for a list of deals."""
        ids = [d.get("id") or d.get("deal_id") for d in deals]
        return self.prices.get_sparkline_data_batch([i for i in ids if i])

    def score_single_deal(self, deal_dict: dict) -> dict | None:
        """Re-score a deal using its profile config. Returns breakdown or None."""
        from dashboard.dependencies import safe_load_profile

        profile_data = safe_load_profile(deal_dict.get("profile", ""))
        if not profile_data:
            return None
        from filters.base import BaseFilter
        from sources.base import Deal

        deal_obj = Deal(
            id=deal_dict["id"],
            title=deal_dict["title"],
            price=deal_dict["price"] or 0,
            link=deal_dict["link"] or "",
            source=deal_dict["source"] or "",
            description=deal_dict["description"] or "",
            temperature=0,
            image_url=deal_dict.get("image_url") or "",
            published_at="",
        )
        result = BaseFilter(profile_data).score_deal(deal_obj)
        return {
            "score": result.score,
            "breakdown": result.breakdown,
            "rejected": result.rejected,
            "reject_reason": result.reject_reason,
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

- [ ] **Step 2: Update dashboard/routes/deals.py**

Replace every `db: SQLiteStorage = Depends(get_db)` with `session: Session = Depends(get_db)`. Replace every `db.method()` call with the corresponding repository call. The pattern is:

```python
# Before:
from storage.sqlite import SQLiteStorage
db: SQLiteStorage = Depends(get_db)
db.get_deals(profile=..., limit=...)
db.get_deal_stats(score_threshold=...)
db.get_price_drops(days=7)

# After:
from sqlalchemy.orm import Session
session: Session = Depends(get_db)
deal_repo = DealRepository(session)
price_repo = PriceRepository(session)
deal_repo.get_filtered(profile=..., limit=...)
deal_repo.get_stats(score_threshold=...)
price_repo.get_drops(days=7)
```

Key method mappings for `deals.py`:
| Old (`db.`) | New |
|---|---|
| `db.get_deals(...)` | `DealRepository(session).get_filtered(...)` |
| `db.count_deals(...)` | `DealRepository(session).count(...)` |
| `db.get_deal_stats(...)` | `DealRepository(session).get_stats(...)` |
| `db.get_price_drops(...)` | `PriceRepository(session).get_drops(...)` |
| `db.get_filter_options()` | `DealRepository(session).get_filter_options()` |
| `db.get_deal(id)` | `DealRepository(session).get_by_id(id)` |
| `db.get_price_history(id)` | `PriceRepository(session).get_history(id)` |
| `db.get_lowest_price(id)` | `PriceRepository(session).get_lowest(id)` |
| `db.get_previous_price(id)` | `PriceRepository(session).get_previous_price(id)` |
| `db.update_deal_status(id, s)` | `DealRepository(session).update_status(id, s)` |
| `db.get_category_price_trend(cat, d)` | `DealRepository(session).get_category_price_trend(cat, d)` |
| `DealService(db)` | `DealService(session)` |

- [ ] **Step 3: Update dashboard/routes/watchlist.py**

Replace `SQLiteStorage` with session + `WatchlistRepository`:

| Old (`db.`) | New |
|---|---|
| `db.get_watchlist()` | `WatchlistRepository(session).get_all()` |
| `db.add_to_watchlist(id, p)` | `WatchlistRepository(session).add(id, p)` |
| `db.remove_from_watchlist(id)` | `WatchlistRepository(session).remove(id)` |
| `db.update_watchlist_target_price(id, p)` | `WatchlistRepository(session).update_target_price(id, p)` |
| `db.get_watchlist_item(id)` | `WatchlistRepository(session).get_item(id)` |
| `DealService(db)` | `DealService(session)` |

- [ ] **Step 4: Update dashboard/routes/tuner.py**

Replace:
| Old | New |
|---|---|
| `db.get_deals(profile=p, limit=50)` | `DealRepository(session).get_filtered(profile=p, limit=50)` |
| `DealService(db)` | `DealService(session)` |

- [ ] **Step 5: Update dashboard/routes/profiles.py**

This file has a special case — it constructs `SQLiteStorage(DB_PATH)` directly on line 92. Replace with `get_session()`:

```python
# Before (line 92):
db = SQLiteStorage(DB_PATH)
deals = db.get_deals(profile=name, limit=50)
db.close()

# After:
from storage.database import get_session
from storage.repositories import DealRepository
with get_session() as session:
    deals = DealRepository(session).get_filtered(profile=name, limit=50)
```

- [ ] **Step 6: Run existing dashboard tests**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_dashboard.py -v`
Expected: FAIL — tests use `SQLiteStorage` fixtures. We'll fix these in Task 14.

- [ ] **Step 7: Commit**

```bash
git add dashboard/services.py dashboard/routes/
git commit -m "refactor(dashboard): migrate all routes from SQLiteStorage to repositories"
```

---

### Task 11: Migrate deal_hunter.py

**Files:**
- Modify: `deal_hunter.py`

This is the largest consumer migration. Two parts:
1. Replace `SQLiteStorage` method calls with repository equivalents
2. Replace `load_state()`/`save_state()` JSON logic with `SeenDealRepository`

- [ ] **Step 1: Replace import and construction**

```python
# Before (line 34):
from storage.sqlite import SQLiteStorage

# After:
from storage.database import get_session
from storage.repositories import (
    AlertQueueRepository,
    DealRepository,
    PriceRepository,
    SeenDealRepository,
    WatchlistRepository,
)
```

- [ ] **Step 2: Update _run_normal() — replace state loading with SeenDealRepository**

Replace lines 549-551:
```python
# Before:
state = load_state(profile_name)
seen = state.get("seen", {})
now = datetime.now().isoformat()

# After:
with get_session() as session:
    seen_repo = SeenDealRepository(session)
    deal_repo = DealRepository(session)
    price_repo = PriceRepository(session)
    watchlist_repo = WatchlistRepository(session)
    alert_repo = AlertQueueRepository(session)
    seen_ids = seen_repo.get_seen_ids(profile_name)
    now = datetime.now().isoformat()
```

Replace the seen-deal check (line 610):
```python
# Before:
if deal.id in seen:
    ...
    continue
seen[deal.id] = now

# After:
if deal.id in seen_ids:
    ...
    continue
seen_repo.mark_seen(deal.id, profile_name, f"{deal.title[:60]}|{deal.price}")
```

Replace persistence calls (line 631):
```python
# Before:
db.upsert_deal(deal, profile_name, result.score, category)
trigger = db.check_watchlist_triggers(deal.id, deal.price)
db.mark_watchlist_triggered(deal.id)

# After:
deal_repo.upsert(
    id=deal.id, title=deal.title, price=deal.price, link=deal.link,
    source=deal.source, description=deal.description, image_url=deal.image_url,
    profile=profile_name, score=result.score, category=category,
)
trigger = watchlist_repo.check_trigger(deal.id, deal.price)
if trigger:
    watchlist_repo.mark_triggered(deal.id)
```

- [ ] **Step 3: Remove load_state, save_state, _state_path**

Delete the functions `load_state()` (lines 143-169), `save_state()` (lines 172-179), and `_state_path()` (lines 138-140). Also remove `STATE_TTL_DAYS` constant.

Remove the save call (line 667-668):
```python
# Delete these lines:
state["seen"] = seen
save_state(profile_name, state)
```

- [ ] **Step 4: Update check_price_changes() — remove JSON state dependency**

Replace the function to use `PriceRepository` instead of the `state` dict:

```python
def check_price_changes(
    deal,
    price_repo: PriceRepository,
    profile: dict | None = None,
) -> dict | None:
    """Check if price changed for a known deal using SQLite price history.

    Returns a structured dict on significant change, None otherwise.
    """
    if deal.price <= 0:
        return None

    pt_config = (
        get_price_tracking_config(profile)
        if profile
        else {"enabled": True, "min_drop_percent": 10, "min_drop_amount": 200, "track_increases": False}
    )
    if not pt_config["enabled"]:
        return None

    prev_price = price_repo.get_previous_price(deal.id)
    if prev_price is None or deal.price == prev_price:
        return None

    if deal.price < prev_price:
        drop_abs = prev_price - deal.price
        drop_pct = (drop_abs / prev_price) * 100 if prev_price > 0 else 0

        if drop_pct >= pt_config["min_drop_percent"] or drop_abs >= pt_config["min_drop_amount"]:
            lowest = price_repo.get_lowest(deal.id)
            is_lowest = lowest is not None and deal.price <= lowest

            return {
                "type": "drop",
                "old_price": prev_price,
                "new_price": deal.price,
                "diff_pln": drop_abs,
                "diff_percent": round(drop_pct, 1),
                "is_lowest_ever": is_lowest,
            }
    elif pt_config["track_increases"]:
        increase_abs = deal.price - prev_price
        increase_pct = (increase_abs / prev_price) * 100 if prev_price > 0 else 0
        return {
            "type": "increase",
            "old_price": prev_price,
            "new_price": deal.price,
            "diff_pln": increase_abs,
            "diff_percent": round(increase_pct, 1),
            "is_lowest_ever": False,
        }
    return None
```

**Note:** The original `check_price_changes()` had a 24-hour cooldown that suppressed rapid re-alerts for the same deal. This cooldown relied on JSON state timestamps. In the new implementation, the cooldown is intentionally dropped — `PriceRepository.record()` uses `INSERT OR IGNORE` which naturally deduplicates same-second entries, and the scoring/alerting pipeline already has `max_alerts` limits. If cooldown behavior is needed later, it can be re-added via a `last_alerted_at` column on the `deals` table.

- [ ] **Step 5: Update all callers of check_price_changes()**

```python
# Before (line 612):
price_change = check_price_changes(deal, state, profile_name, profile, db)

# After:
price_change = check_price_changes(deal, price_repo, profile)
```

- [ ] **Step 6: Update run_digest(), run_price_chart(), run_trend_chart()**

Replace `SQLiteStorage` construction with `get_session()` + repositories:

```python
# run_digest() — Before:
db = SQLiteStorage(DB_PATH)
drops = db.get_price_drops(days=7)
db.close()

# After:
with get_session() as session:
    drops = PriceRepository(session).get_drops(days=7)
```

```python
# run_price_chart() — Before:
db = SQLiteStorage(DB_PATH)
chart_path = generate_price_chart(deal_id, db)
db.close()

# After:
with get_session() as session:
    chart_path = generate_price_chart(deal_id, session)
```

```python
# run_trend_chart() — Before:
db = SQLiteStorage(DB_PATH)
chart_path = generate_trend_chart(profile_name, db)
db.close()

# After:
with get_session() as session:
    chart_path = generate_trend_chart(profile_name, session)
```

- [ ] **Step 7: Update alert queue flush logic**

Replace `db.get_pending_alerts()` / `db.mark_alerts_sent()` / `db.queue_alert()` with `AlertQueueRepository`:

```python
# Before:
pending = db.get_pending_alerts(profile=profile_name)
db.mark_alerts_sent([p["id"] for p in pending[:flush_count]])
db.queue_alert(profile_name, "price_drop", payload)

# After:
pending = alert_repo.get_pending(profile=profile_name)
alert_repo.mark_sent([p["id"] for p in pending[:flush_count]])
alert_repo.queue(profile_name, "price_drop", payload)
```

- [ ] **Step 8: Commit**

```bash
git add deal_hunter.py
git commit -m "refactor: migrate deal_hunter.py from SQLiteStorage + JSON state to repositories"
```

---

### Task 12: Migrate feedback_bot.py

**Files:**
- Modify: `feedback_bot.py`

- [ ] **Step 1: Replace SQLiteStorage with session + repositories**

```python
# Before:
from storage.sqlite import SQLiteStorage

def get_storage() -> SQLiteStorage:
    return SQLiteStorage(DB_PATH)

# After:
from storage.database import get_session
from storage.repositories import (
    DealRepository,
    FeedbackRepository,
    WatchlistRepository,
)
```

Replace every `with get_storage() as storage:` block:

```python
# Before:
with get_storage() as storage:
    storage.update_deal_status(deal_id, status)
    storage.record_feedback(deal_id, action)

# After:
with get_session() as session:
    DealRepository(session).update_status(deal_id, status)
    FeedbackRepository(session).record(deal_id, action)
```

```python
# cmd_status — Before:
with get_storage() as storage:
    stats = storage.get_feedback_stats()
    watching = storage.get_deals_by_status("watching", limit=10000)
    rejected = storage.get_deals_by_status("rejected", limit=10000)
    total = storage.get_deals()

# After:
with get_session() as session:
    deal_repo = DealRepository(session)
    stats = FeedbackRepository(session).get_stats()
    watching = deal_repo.get_by_status("watching", limit=10000)
    rejected = deal_repo.get_by_status("rejected", limit=10000)
    total = deal_repo.get_filtered()
```

```python
# cmd_target — Before:
with get_storage() as storage:
    storage.add_to_watchlist(deal_id, target_price)

# After:
with get_session() as session:
    WatchlistRepository(session).add(deal_id, target_price)
```

```python
# cmd_watchlist — Before:
with get_storage() as storage:
    deals = storage.get_deals_by_status("watching", limit=20)

# After:
with get_session() as session:
    deals = DealRepository(session).get_by_status("watching", limit=20)
```

- [ ] **Step 2: Remove get_storage() function and DB_PATH import**

- [ ] **Step 3: Commit**

```bash
git add feedback_bot.py
git commit -m "refactor: migrate feedback_bot.py from SQLiteStorage to repositories"
```

---

### Task 13: Migrate visualization/charts.py

**Files:**
- Modify: `visualization/charts.py`

- [ ] **Step 1: Update function signatures to accept Session**

```python
# Before:
def generate_price_chart(deal_id: str, db, ...) -> Path:
    deal = db.get_deal(deal_id)
    history = db.get_price_history(deal_id)

# After:
def generate_price_chart(deal_id: str, session, ...) -> Path:
    from storage.repositories import DealRepository, PriceRepository
    deal_repo = DealRepository(session)
    price_repo = PriceRepository(session)
    deal = deal_repo.get_by_id(deal_id)
    history = price_repo.get_history(deal_id)
```

```python
# Before:
def generate_trend_chart(profile: str, db, ...) -> Path:
    deals = db.get_deals(profile=profile)
    for deal_id in deal_ids:
        history = db.get_price_history(deal_id)

# After:
def generate_trend_chart(profile: str, session, ...) -> Path:
    from storage.repositories import DealRepository, PriceRepository
    deal_repo = DealRepository(session)
    price_repo = PriceRepository(session)
    deals = deal_repo.get_filtered(profile=profile)
    # Use batch query instead of N+1 loop:
    histories = price_repo.get_histories_batch(deal_ids)
    for deal_id in deal_ids:
        history = histories.get(deal_id, [])
```

**Note:** The `generate_trend_chart` function currently does D+1 queries (one `get_price_history()` per deal). The migration to `get_histories_batch()` fixes this N+1 pattern.

- [ ] **Step 2: Commit**

```bash
git add visualization/charts.py
git commit -m "refactor: migrate charts.py to session + repositories, fix N+1 in trend_chart"
```

---

### Task 14: Migrate Test Suite

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_price_drops.py`
- Modify: `tests/test_feedback_bot.py`
- Modify: `tests/test_watchlist.py`
- Modify: `tests/test_quiet_hours.py`
- Modify: `tests/test_charts.py`
- Delete: `tests/test_sqlite_storage.py` (replaced by `tests/test_repositories.py`)
- Delete: `tests/test_batch_queries.py` (merged into `tests/test_repositories.py`)
- Delete: `tests/test_state.py` (tests load_state/save_state which are removed)
- Modify: `tests/e2e/conftest.py`

This is the largest test-migration task. The core change: everywhere that creates/uses `SQLiteStorage`, switch to `Session` + repositories.

- [ ] **Step 1: Update tests/conftest.py — replace dashboard_db fixture**

```python
# Before:
from storage.sqlite import SQLiteStorage

@pytest.fixture
def dashboard_db(tmp_path):
    db = SQLiteStorage(tmp_path / "dashboard.db")
    ...
    yield db
    db.close()

# After:
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from storage.models import Base
from storage.repositories import DealRepository

@pytest.fixture
def dashboard_session(tmp_path):
    """SQLAlchemy session seeded with test data for dashboard tests."""
    eng = create_engine(f"sqlite:///{tmp_path / 'dashboard.db'}")
    Base.metadata.create_all(eng)
    session = Session(eng)

    deal_repo = DealRepository(session)
    # ... (same seeding logic as before, using deal_repo.upsert())
    ...

    yield session
    session.close()
```

Update `client` and `raw_client` fixtures to use `dashboard_session` instead of `dashboard_db`. Update the dependency override:

```python
@pytest.fixture
def client(dashboard_session):
    from fastapi.testclient import TestClient
    from dashboard import app, get_db

    def _override():
        yield dashboard_session

    app.dependency_overrides[get_db] = _override
    yield _CsrfTestClient(TestClient(app, follow_redirects=False))
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Update tests/test_price_drops.py — replace SQLiteStorage fixtures**

```python
# Before:
from storage.sqlite import SQLiteStorage

@pytest.fixture
def db(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    yield storage
    storage.close()

# After:
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from storage.models import Base
from storage.repositories import DealRepository, PriceRepository

@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(eng)
    return eng

@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s

@pytest.fixture
def deal_repo(session):
    return DealRepository(session)

@pytest.fixture
def price_repo(session):
    return PriceRepository(session)
```

Replace all `db._conn.execute()` calls with repository calls or session.execute() for test setup. Replace `db.get_lowest_price()` with `price_repo.get_lowest()`, etc.

- [ ] **Step 3: Update tests/test_feedback_bot.py — replace SQLiteStorage fixtures**

Same pattern: replace `SQLiteStorage` fixture with engine + session + repositories.

- [ ] **Step 4: Update tests/test_watchlist.py — replace SQLiteStorage fixtures**

Same pattern. Replace `db.add_to_watchlist()` with `WatchlistRepository(session).add()`, etc.

- [ ] **Step 5: Update tests/test_quiet_hours.py — replace SQLiteStorage fixtures**

Replace `SQLiteStorage` fixture with session + `AlertQueueRepository`.

- [ ] **Step 6: Update tests/test_charts.py — update mock interface**

The mock db needs to match the new interface (session + repositories). Since charts.py now creates repositories internally from the session, the mock needs to provide the right query results when the repository executes queries. Alternatively, mock the repositories directly.

- [ ] **Step 7: Delete old test files replaced by new structure**

```bash
git rm tests/test_sqlite_storage.py
git rm tests/test_batch_queries.py
git rm tests/test_state.py
```

`test_sqlite_storage.py` and `test_batch_queries.py` are replaced by `test_repositories.py`. `test_state.py` tested `load_state()`/`save_state()` which no longer exist (replaced by `SeenDealRepository`).

- [ ] **Step 8: Update tests/e2e/conftest.py**

Replace `SQLiteStorage` fixture with session-based seeding.

- [ ] **Step 9: Run full test suite**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/ -v --tb=short`
Expected: All tests PASS. Total count should be ~675 (same as before — some old tests deleted, replaced by new `test_repositories.py` tests).

- [ ] **Step 10: Commit**

```bash
git add tests/
git commit -m "test: migrate all test fixtures from SQLiteStorage to SQLAlchemy sessions"
```

---

### Task 15: JSON State Migration Script

**Files:**
- Create: `scripts/migrate_json_state.py`

This one-time script reads existing `state/*_state.json` files and imports their `seen` entries into the `seen_deals` table and their `prices` entries into `price_history` (deduplicating against existing records).

- [ ] **Step 1: Write the migration script**

```python
#!/usr/bin/env python3
"""One-time migration: import state/*.json seen-deals and prices into SQLite.

Usage:
    python scripts/migrate_json_state.py [--dry-run]

Reads state/*_state.json files, imports:
- "seen" entries -> seen_deals table
- "prices" entries -> price_history table (dedup against existing)

Safe to run multiple times (idempotent via INSERT OR IGNORE).
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.database import get_session  # noqa: E402
from storage.models import Base, SeenDeal  # noqa: E402
from storage.database import engine  # noqa: E402
from sqlalchemy import text  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

STATE_DIR = Path(__file__).parent.parent / "state"


def migrate_file(path: Path, session, dry_run: bool = False) -> dict:
    """Migrate a single state JSON file. Returns counts."""
    profile = path.stem.replace("_state", "")
    counts = {"seen": 0, "prices": 0, "skipped": 0}

    try:
        with path.open(encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Skipping {path.name}: {e}")
        return counts

    # Handle legacy formats
    if isinstance(state, list):
        state = {"seen": {item: datetime.now().isoformat() for item in state}, "prices": {}}
    if "seen" not in state:
        state = {"seen": {k: v for k, v in state.items() if isinstance(v, str)}, "prices": {}}

    # Migrate seen entries
    for deal_id, timestamp in state.get("seen", {}).items():
        if dry_run:
            counts["seen"] += 1
            continue
        # Check if already migrated
        exists = session.query(SeenDeal).filter_by(
            deal_id=deal_id, profile=profile
        ).first()
        if exists:
            counts["skipped"] += 1
            continue
        session.add(SeenDeal(
            deal_id=deal_id,
            profile=profile,
            dedup_key=deal_id,  # best available dedup key from legacy data
            first_seen_at=timestamp,
        ))
        counts["seen"] += 1

    # Migrate price history
    for deal_id, entries in state.get("prices", {}).items():
        for entry in entries:
            price = entry.get("price", 0)
            ts = entry.get("ts", "")
            if not price or not ts:
                continue
            if dry_run:
                counts["prices"] += 1
                continue
            session.execute(
                text(
                    "INSERT OR IGNORE INTO price_history (deal_id, price, recorded_at)"
                    " VALUES (:deal_id, :price, :ts)"
                ),
                {"deal_id": deal_id, "price": price, "ts": ts},
            )
            counts["prices"] += 1

    return counts


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    # Ensure seen_deals table exists
    Base.metadata.create_all(engine)

    json_files = sorted(STATE_DIR.glob("*_state.json"))
    if not json_files:
        logger.info("No state JSON files found in %s", STATE_DIR)
        return

    logger.info(
        "%s %d state files from %s",
        "DRY RUN:" if dry_run else "Migrating",
        len(json_files),
        STATE_DIR,
    )

    total = {"seen": 0, "prices": 0, "skipped": 0}
    with get_session() as session:
        for path in json_files:
            counts = migrate_file(path, session, dry_run=dry_run)
            logger.info(
                "  %s: %d seen, %d prices, %d skipped",
                path.name, counts["seen"], counts["prices"], counts["skipped"],
            )
            for k in total:
                total[k] += counts[k]

    logger.info(
        "Total: %d seen entries, %d price entries, %d skipped",
        total["seen"], total["prices"], total["skipped"],
    )
    if not dry_run:
        logger.info("Migration complete. State JSON files can be removed (keep health.json).")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write a test for the migration script**

```python
# tests/test_migrate_json_state.py
"""Tests for JSON state migration script."""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models import Base, SeenDeal, PriceHistory


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


def test_migrate_new_format(tmp_path, session, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_file = state_dir / "bikes_state.json"
    state_file.write_text(json.dumps({
        "seen": {"pepper:1": "2026-04-13T10:00:00", "pepper:2": "2026-04-13T11:00:00"},
        "prices": {"pepper:1": [{"price": 5000, "ts": "2026-04-10T10:00:00"}]},
    }))

    # Import and run migration
    import scripts.migrate_json_state as mig
    monkeypatch.setattr(mig, "STATE_DIR", state_dir)
    monkeypatch.setattr(mig, "get_session", lambda: session)

    # Use session directly instead of context manager
    counts = mig.migrate_file(state_file, session)
    session.commit()

    assert counts["seen"] == 2
    assert counts["prices"] == 1

    seen = session.query(SeenDeal).all()
    assert len(seen) == 2

    prices = session.query(PriceHistory).filter_by(deal_id="pepper:1").all()
    assert len(prices) == 1


def test_migrate_idempotent(tmp_path, session, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_file = state_dir / "bikes_state.json"
    state_file.write_text(json.dumps({
        "seen": {"pepper:1": "2026-04-13T10:00:00"},
        "prices": {},
    }))

    import scripts.migrate_json_state as mig
    monkeypatch.setattr(mig, "STATE_DIR", state_dir)

    # Run twice
    mig.migrate_file(state_file, session)
    session.commit()
    counts2 = mig.migrate_file(state_file, session)
    assert counts2["skipped"] == 1
```

- [ ] **Step 3: Run migration test**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_migrate_json_state.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/migrate_json_state.py tests/test_migrate_json_state.py
git commit -m "feat: add JSON state migration script for seen_deals consolidation"
```

---

### Task 16: Delete storage/sqlite.py and Old Migration Script

**Files:**
- Delete: `storage/sqlite.py`
- Delete: `scripts/migrate_state_to_sqlite.py`
- Modify: `storage/__init__.py`

- [ ] **Step 1: Remove SQLiteStorage re-export from storage/__init__.py**

Remove the line:
```python
from storage.sqlite import SQLiteStorage  # kept until all consumers migrated
```
And remove `"SQLiteStorage"` from `__all__`.

- [ ] **Step 2: Verify no remaining imports of storage.sqlite**

Run: `grep -r "from storage.sqlite" --include="*.py" .`
Expected: No matches (or only in test files that we'll also clean).

Run: `grep -r "from storage import SQLiteStorage" --include="*.py" .`
Expected: No matches.

- [ ] **Step 3: Delete the files**

```bash
git rm storage/sqlite.py
git rm scripts/migrate_state_to_sqlite.py
```

- [ ] **Step 4: Run full test suite**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/ -v --tb=short`
Expected: All tests PASS. No test should import `SQLiteStorage` anymore.

- [ ] **Step 5: Commit**

```bash
git add storage/__init__.py
git commit -m "chore: delete storage/sqlite.py and old migration script — fully replaced by ORM"
```

---

### Task 17: Final Verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/ -v --tb=short`
Expected: All tests PASS. Count should be ~675.

- [ ] **Step 2: Run ruff check**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m ruff check .`
Expected: No errors.

- [ ] **Step 3: Run ruff format check**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m ruff format --check .`
Expected: No reformatting needed.

- [ ] **Step 4: Verify no remaining SQLiteStorage references**

Run: `grep -r "SQLiteStorage" --include="*.py" .`
Expected: No matches.

Run: `grep -r "storage.sqlite" --include="*.py" .`
Expected: No matches.

- [ ] **Step 5: Verify no remaining JSON state references in production code**

Run: `grep -rn "load_state\|save_state\|_state_path\|STATE_TTL_DAYS" --include="*.py" . | grep -v tests/ | grep -v scripts/ | grep -v __pycache__`
Expected: No matches in production code. Test files may still reference these in `test_state.py` (which tests the now-removed functions — this file should also be deleted or updated).

- [ ] **Step 6: Verify Alembic migrations are consistent**

Run:
```bash
DATABASE_URL="sqlite:///$(mktemp -d)/verify.db" /home/liske/Projects/deal-hunter/venv/bin/python -c "
import os, sys
sys.path.insert(0, '.')
from alembic.config import Config
from alembic import command
cfg = Config('storage/migrations/alembic.ini')
cfg.set_main_option('script_location', 'storage/migrations')
cfg.set_main_option('sqlalchemy.url', os.environ['DATABASE_URL'])
command.upgrade(cfg, 'head')
print('Alembic upgrade to head: OK')
"
```
Expected: `Alembic upgrade to head: OK`

- [ ] **Step 7: Commit any final fixes**

If any issues were found in steps 1-6, fix and commit.

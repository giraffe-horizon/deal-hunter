# Sent Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every successful Telegram send into a new `sent_notifications` table, switch the per-deal cooldown query at the new table (fixing a latent bug where it only fires during quiet hours), and add a `/notifications/history` dashboard page.

**Architecture:** New `sent_notifications` SQLite table written via a fire-and-forget recorder. Typed Telegram `send_*` methods record themselves after a successful HTTP call; generic `send_text` / `send_photo` callers record explicitly. `notification_filter` reads `last_sent_at` from the new table instead of `alert_queue`. Dashboard route mirrors the existing `/watchlist` HTMX pattern; sub-nav links Settings ↔ History.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, Alembic, FastAPI + Jinja2 + HTMX, requests, pytest.

**Spec:** [docs/superpowers/specs/2026-05-12-sent-notifications-design.md](../specs/2026-05-12-sent-notifications-design.md)

---

## File Structure

**New files:**
- `src/deal_hunter/storage/migrations/versions/007_sent_notifications.py` — Alembic migration adding the table + two indexes.
- `src/deal_hunter/storage/repositories/sent_notification.py` — `SentNotificationRepository`.
- `src/deal_hunter/notifiers/telegram/recorder.py` — fire-and-forget `record_sent_notification(...)`.
- `src/deal_hunter/api/templates/notifications_history.html` — page template.
- `src/deal_hunter/api/templates/partials/notifications_history_table.html` — table rendered by full page and by HTMX swap.
- `src/deal_hunter/api/templates/partials/notifications_subnav.html` — shared `Settings | History` sub-nav.
- `tests/test_migration_007_sent_notifications.py`
- `tests/test_sent_notification_repository.py`
- `tests/test_recorder.py`

**Modified files:**
- `src/deal_hunter/storage/models.py` — add `SentNotification` ORM class + indexes.
- `src/deal_hunter/storage/repositories/__init__.py` — re-export `SentNotificationRepository`.
- `src/deal_hunter/storage/repositories/alert_queue.py` — delete `last_price_drop_sent_at`.
- `src/deal_hunter/notifiers/telegram/transport.py` — `_send_message`, `send_photo`, `send_text` return `bool`; typed senders take `profile` kwarg and record on success.
- `src/deal_hunter/services/notification_filter.py` — rename `alert_repo` → `sent_repo`, call `last_sent_at(deal_id, "price_drop")`.
- `src/deal_hunter/services/alerter.py` — `AlertService` accepts and threads `sent_repo`; passes filter the right object; passes `profile` kwarg to typed sends; `flush_queued` and `send_source_failure_alert` record via the call site.
- `src/deal_hunter/services/hunt_service.py` — construct `SentNotificationRepository`, pass into `AlertService`, pass `profile=profile_name` to direct `telegram.send_watchlist_alert`.
- `src/deal_hunter/services/digest_service.py` — record chart send after `send_photo`.
- `src/deal_hunter/services/chart_service.py` — record chart send after `send_photo`; accept optional `deal_id`/`profile` from callers.
- `src/deal_hunter/api/routes/notifications.py` — add `/notifications/history` route; render sub-nav on Settings page too.
- `src/deal_hunter/api/templates/notifications.html` — include sub-nav partial at top.
- `tests/test_models.py` — add `test_sent_notifications_columns`.
- `tests/test_notification_filter.py` — rename `alert_repo` → `sent_repo`, update helper.
- `tests/test_quiet_hours.py` — delete `TestAlertQueueDealId::test_last_price_drop_sent_at_*` tests.
- `tests/test_services.py` — update filter test signature; add recording tests.
- `tests/test_dashboard_notifications.py` — add `TestNotificationsHistoryPage`.

**Conventions in play (don't violate):**
- English code/comments/logs; Polish only for user-facing dashboard / Telegram strings.
- ISO datetime strings everywhere `sent_at` flows; lexical comparisons are intentional.
- Recording is fire-and-forget: never raise from `record_sent_notification`; never let recording failure mask a successful send.
- Watchdog Telegram send in `src/deal_hunter/cli/main.py:116` is **NOT** recorded — out of scope per spec (the seven alert types listed do not include `watchdog`).

---

## Task 1: Migration `007` + `SentNotification` model

**Files:**
- Create: `src/deal_hunter/storage/migrations/versions/007_sent_notifications.py`
- Modify: `src/deal_hunter/storage/models.py`
- Test: `tests/test_migration_007_sent_notifications.py`, `tests/test_models.py`

- [ ] **Step 1: Write the failing migration tests**

Create `tests/test_migration_007_sent_notifications.py`:

```python
"""Round-trip test for Alembic revision 007_sent_notifications."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


@pytest.fixture
def alembic_db(tmp_path: Path) -> tuple[Config, str]:
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    cfg = Config("src/deal_hunter/storage/migrations/alembic.ini")
    return cfg, db_url


def _columns(db_url: str, table: str) -> set[str]:
    eng = create_engine(db_url)
    try:
        return {c["name"] for c in inspect(eng).get_columns(table)}
    finally:
        eng.dispose()


def _indexes(db_url: str, table: str) -> set[str]:
    eng = create_engine(db_url)
    try:
        return {idx["name"] for idx in inspect(eng).get_indexes(table)}
    finally:
        eng.dispose()


def _tables(db_url: str) -> set[str]:
    eng = create_engine(db_url)
    try:
        return set(inspect(eng).get_table_names())
    finally:
        eng.dispose()


def test_007_creates_sent_notifications_table(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "007")
    assert "sent_notifications" in _tables(db_url)
    cols = _columns(db_url, "sent_notifications")
    assert cols == {"id", "alert_type", "deal_id", "profile", "payload", "sent_at"}


def test_007_creates_indexes(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "007")
    idx = _indexes(db_url, "sent_notifications")
    assert "ix_sent_notifications_deal_id_alert_type" in idx
    assert "ix_sent_notifications_sent_at" in idx


def test_007_downgrade_drops_table(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "007")
    command.downgrade(cfg, "006")
    assert "sent_notifications" not in _tables(db_url)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_migration_007_sent_notifications.py -v`
Expected: FAIL — revision 007 does not exist.

- [ ] **Step 3: Write the migration**

Create `src/deal_hunter/storage/migrations/versions/007_sent_notifications.py`:

```python
"""Add sent_notifications table for persistent dispatch history.

Revision ID: 007
Revises: 006
Create Date: 2026-05-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sent_notifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_type", sa.String(), nullable=False),
        sa.Column("deal_id", sa.String(), nullable=True),
        sa.Column("profile", sa.String(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_sent_notifications_deal_id_alert_type",
        "sent_notifications",
        ["deal_id", "alert_type", "sent_at"],
    )
    op.create_index(
        "ix_sent_notifications_sent_at",
        "sent_notifications",
        ["sent_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sent_notifications_sent_at", table_name="sent_notifications")
    op.drop_index("ix_sent_notifications_deal_id_alert_type", table_name="sent_notifications")
    op.drop_table("sent_notifications")
```

- [ ] **Step 4: Add ORM model**

In `src/deal_hunter/storage/models.py`, append after the last existing model class (after `FxRate`, around line 235):

```python
class SentNotification(Base):
    __tablename__ = "sent_notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    alert_type: Mapped[str] = mapped_column(String, nullable=False)
    deal_id: Mapped[str | None] = mapped_column(String, default=None)
    profile: Mapped[str | None] = mapped_column(String, default=None)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index("ix_sent_notifications_deal_id_alert_type", "deal_id", "alert_type", "sent_at"),
        Index("ix_sent_notifications_sent_at", "sent_at"),
    )
```

- [ ] **Step 5: Add column-set test**

Append to `tests/test_models.py` (inside the existing `TestTableCreation` class, after `test_alert_queue_round_trip` or similar — find the position via `grep -n "class TestTableCreation\|def test_alert_queue" tests/test_models.py`):

```python
    def test_sent_notifications_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("sent_notifications")}
        assert cols == {
            "id",
            "alert_type",
            "deal_id",
            "profile",
            "payload",
            "sent_at",
        }
```

Also update the existing `test_tables_exist` (around line 30-52) to include `"sent_notifications"` in the expected set. The exact set already includes `"alert_queue"`, `"offers"`, etc. — just add the new table name.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_migration_007_sent_notifications.py tests/test_models.py -v`
Expected: all PASSED.

- [ ] **Step 7: Commit**

```bash
git add src/deal_hunter/storage/migrations/versions/007_sent_notifications.py \
        src/deal_hunter/storage/models.py \
        tests/test_migration_007_sent_notifications.py \
        tests/test_models.py
git commit -m "feat(db): add sent_notifications table (migration 007)"
```

---

## Task 2: `SentNotificationRepository`

**Files:**
- Create: `src/deal_hunter/storage/repositories/sent_notification.py`
- Modify: `src/deal_hunter/storage/repositories/__init__.py`
- Test: `tests/test_sent_notification_repository.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sent_notification_repository.py`:

```python
"""Tests for SentNotificationRepository."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from deal_hunter.storage.models import Base
from deal_hunter.storage.repositories import SentNotificationRepository


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
def repo(session):
    return SentNotificationRepository(session)


class TestRecord:
    def test_record_writes_row(self, session, repo):
        repo.record(
            alert_type="price_drop",
            payload_json='{"x": 1}',
            deal_id="pepper:1",
            profile="bikes",
            sent_at="2026-05-12T10:00:00",
        )
        session.flush()
        rows = repo.list_recent(limit=10)
        assert len(rows) == 1
        assert rows[0]["alert_type"] == "price_drop"
        assert rows[0]["deal_id"] == "pepper:1"
        assert rows[0]["profile"] == "bikes"
        assert rows[0]["payload"] == {"x": 1}  # decoded
        assert rows[0]["sent_at"] == "2026-05-12T10:00:00"

    def test_record_defaults_sent_at_to_now(self, session, repo):
        before = datetime.now().isoformat()
        repo.record(alert_type="deal", payload_json="{}")
        session.flush()
        rows = repo.list_recent(limit=1)
        assert rows[0]["sent_at"] >= before

    def test_record_with_nullable_fields(self, session, repo):
        # digest / source_failure have no deal_id and no profile
        repo.record(alert_type="digest", payload_json='{"drop_count": 3}')
        session.flush()
        rows = repo.list_recent(limit=1)
        assert rows[0]["deal_id"] is None
        assert rows[0]["profile"] is None


class TestLastSentAt:
    def test_returns_none_when_no_rows(self, repo):
        assert repo.last_sent_at("pepper:1", "price_drop") is None

    def test_returns_max_for_pair(self, session, repo):
        repo.record(
            alert_type="price_drop",
            payload_json="{}",
            deal_id="pepper:1",
            sent_at="2026-05-10T10:00:00",
        )
        repo.record(
            alert_type="price_drop",
            payload_json="{}",
            deal_id="pepper:1",
            sent_at="2026-05-12T10:00:00",
        )
        session.flush()
        assert repo.last_sent_at("pepper:1", "price_drop") == "2026-05-12T10:00:00"

    def test_ignores_other_deal_ids(self, session, repo):
        repo.record(
            alert_type="price_drop",
            payload_json="{}",
            deal_id="pepper:other",
            sent_at="2026-05-12T10:00:00",
        )
        session.flush()
        assert repo.last_sent_at("pepper:1", "price_drop") is None

    def test_ignores_other_alert_types(self, session, repo):
        repo.record(
            alert_type="deal",
            payload_json="{}",
            deal_id="pepper:1",
            sent_at="2026-05-12T10:00:00",
        )
        session.flush()
        assert repo.last_sent_at("pepper:1", "price_drop") is None


class TestListRecent:
    def test_orders_by_sent_at_desc(self, session, repo):
        repo.record(alert_type="a", payload_json="{}", sent_at="2026-05-10T10:00:00")
        repo.record(alert_type="b", payload_json="{}", sent_at="2026-05-12T10:00:00")
        repo.record(alert_type="c", payload_json="{}", sent_at="2026-05-11T10:00:00")
        session.flush()
        rows = repo.list_recent(limit=10)
        assert [r["alert_type"] for r in rows] == ["b", "c", "a"]

    def test_filter_by_alert_type(self, session, repo):
        repo.record(alert_type="deal", payload_json="{}")
        repo.record(alert_type="price_drop", payload_json="{}")
        repo.record(alert_type="deal", payload_json="{}")
        session.flush()
        rows = repo.list_recent(alert_type="deal", limit=10)
        assert len(rows) == 2
        assert all(r["alert_type"] == "deal" for r in rows)

    def test_filter_by_profile(self, session, repo):
        repo.record(alert_type="deal", payload_json="{}", profile="bikes")
        repo.record(alert_type="deal", payload_json="{}", profile="hifi")
        session.flush()
        rows = repo.list_recent(profile="bikes", limit=10)
        assert len(rows) == 1
        assert rows[0]["profile"] == "bikes"

    def test_filter_by_since(self, session, repo):
        repo.record(alert_type="a", payload_json="{}", sent_at="2026-05-10T00:00:00")
        repo.record(alert_type="b", payload_json="{}", sent_at="2026-05-12T00:00:00")
        session.flush()
        rows = repo.list_recent(since="2026-05-11T00:00:00", limit=10)
        assert [r["alert_type"] for r in rows] == ["b"]

    def test_limit_and_offset(self, session, repo):
        for i in range(5):
            repo.record(
                alert_type="a",
                payload_json="{}",
                sent_at=f"2026-05-{10 + i:02d}T00:00:00",
            )
        session.flush()
        page1 = repo.list_recent(limit=2, offset=0)
        page2 = repo.list_recent(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        # Newest first, no overlap
        assert page1[0]["sent_at"] > page2[0]["sent_at"]


class TestCount:
    def test_count_matches_list_recent(self, session, repo):
        for _ in range(7):
            repo.record(alert_type="deal", payload_json="{}", profile="bikes")
        repo.record(alert_type="price_drop", payload_json="{}", profile="hifi")
        session.flush()

        assert repo.count() == 8
        assert repo.count(alert_type="deal") == 7
        assert repo.count(profile="bikes") == 7
        assert repo.count(alert_type="price_drop", profile="hifi") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sent_notification_repository.py -v`
Expected: FAIL — `SentNotificationRepository` does not exist in `deal_hunter.storage.repositories`.

- [ ] **Step 3: Write the repository**

Create `src/deal_hunter/storage/repositories/sent_notification.py`:

```python
"""Sent-notifications repository — persistent dispatch history."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from deal_hunter.storage.models import SentNotification


class SentNotificationRepository:
    """Query and mutation wrapper for sent_notifications."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        alert_type: str,
        payload_json: str,
        deal_id: str | None = None,
        profile: str | None = None,
        sent_at: str | None = None,
    ) -> None:
        """Insert a row. Caller commits via the session."""
        row = SentNotification(
            alert_type=alert_type,
            deal_id=deal_id,
            profile=profile,
            payload=payload_json,
            sent_at=sent_at or datetime.now().isoformat(),
        )
        self.session.add(row)

    def last_sent_at(self, deal_id: str, alert_type: str) -> str | None:
        """MAX(sent_at) for the given deal + alert_type, or None."""
        stmt = select(func.max(SentNotification.sent_at)).where(
            SentNotification.deal_id == deal_id,
            SentNotification.alert_type == alert_type,
        )
        return self.session.execute(stmt).scalar()

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        alert_type: str | None = None,
        profile: str | None = None,
        since: str | None = None,
    ) -> list[dict]:
        """Return rows newest-first, with payload JSON-decoded."""
        stmt = select(SentNotification).order_by(SentNotification.sent_at.desc())
        if alert_type is not None:
            stmt = stmt.where(SentNotification.alert_type == alert_type)
        if profile is not None:
            stmt = stmt.where(SentNotification.profile == profile)
        if since is not None:
            stmt = stmt.where(SentNotification.sent_at >= since)
        stmt = stmt.limit(limit).offset(offset)
        return [self._to_dict(r) for r in self.session.scalars(stmt)]

    def count(
        self,
        *,
        alert_type: str | None = None,
        profile: str | None = None,
        since: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(SentNotification)
        if alert_type is not None:
            stmt = stmt.where(SentNotification.alert_type == alert_type)
        if profile is not None:
            stmt = stmt.where(SentNotification.profile == profile)
        if since is not None:
            stmt = stmt.where(SentNotification.sent_at >= since)
        return self.session.execute(stmt).scalar() or 0

    @staticmethod
    def _to_dict(row: SentNotification) -> dict:
        try:
            payload = json.loads(row.payload)
        except (TypeError, ValueError):
            payload = {"_raw": row.payload}
        return {
            "id": row.id,
            "alert_type": row.alert_type,
            "deal_id": row.deal_id,
            "profile": row.profile,
            "payload": payload,
            "sent_at": row.sent_at,
        }
```

- [ ] **Step 4: Export from package**

In `src/deal_hunter/storage/repositories/__init__.py`, add to the imports (alphabetical):

```python
from deal_hunter.storage.repositories.sent_notification import SentNotificationRepository
```

And add to `__all__` alphabetically (after `SeenDealRepository`):

```python
    "SentNotificationRepository",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sent_notification_repository.py -v`
Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/deal_hunter/storage/repositories/sent_notification.py \
        src/deal_hunter/storage/repositories/__init__.py \
        tests/test_sent_notification_repository.py
git commit -m "feat(repo): add SentNotificationRepository"
```

---

## Task 3: `recorder.py` — fire-and-forget recorder

**Files:**
- Create: `src/deal_hunter/notifiers/telegram/recorder.py`
- Test: `tests/test_recorder.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_recorder.py`:

```python
"""Tests for record_sent_notification — fire-and-forget recorder."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from deal_hunter.notifiers.telegram.recorder import record_sent_notification
from deal_hunter.storage.models import Base
from deal_hunter.storage.repositories import SentNotificationRepository


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


def test_record_writes_row(engine):
    @contextmanager
    def _factory():
        with Session(engine) as s:
            yield s
            s.commit()

    with patch("deal_hunter.notifiers.telegram.recorder.get_session", _factory):
        record_sent_notification(
            alert_type="price_drop",
            payload={"title": "x", "old_price": 200, "new_price": 100},
            deal_id="pepper:1",
            profile="bikes",
        )

    with Session(engine) as s:
        rows = SentNotificationRepository(s).list_recent(limit=10)
    assert len(rows) == 1
    assert rows[0]["alert_type"] == "price_drop"
    assert rows[0]["deal_id"] == "pepper:1"
    assert rows[0]["profile"] == "bikes"
    assert rows[0]["payload"]["title"] == "x"


def test_record_swallows_db_errors(caplog):
    """A DB blip must not propagate — log WARNING and move on."""

    @contextmanager
    def _broken_factory():
        raise OperationalError("boom", {}, Exception("boom"))
        yield  # unreachable

    with patch("deal_hunter.notifiers.telegram.recorder.get_session", _broken_factory):
        with caplog.at_level(logging.WARNING):
            record_sent_notification(
                alert_type="deal",
                payload={"x": 1},
            )

    assert any(
        "sent_notifications insert failed" in rec.message
        for rec in caplog.records
        if rec.levelno == logging.WARNING
    )


def test_record_swallows_repository_errors(caplog, engine):
    """If the repository raises mid-insert, recording still swallows."""

    @contextmanager
    def _factory():
        with Session(engine) as s:
            yield s
            s.commit()

    with patch("deal_hunter.notifiers.telegram.recorder.get_session", _factory), patch(
        "deal_hunter.notifiers.telegram.recorder.SentNotificationRepository.record",
        side_effect=OperationalError("boom", {}, Exception("boom")),
    ):
        with caplog.at_level(logging.WARNING):
            record_sent_notification(alert_type="deal", payload={})

    assert any("sent_notifications insert failed" in rec.message for rec in caplog.records)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_recorder.py -v`
Expected: FAIL — `deal_hunter.notifiers.telegram.recorder` does not exist.

- [ ] **Step 3: Write the module**

Create `src/deal_hunter/notifiers/telegram/recorder.py`:

```python
"""Fire-and-forget recorder for successful Telegram sends.

`TelegramNotifier.send_*` methods call this after a 200 response from the
Telegram API. The recorder builds its own short-lived session via
`get_session` (the project's existing context manager) so that HTTP I/O
stays decoupled from the per-hunt transactional boundary.

A DB error here MUST NOT bubble up. A successful Telegram message that
fails to record is still a successful message; we log at WARNING and
move on.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.exc import SQLAlchemyError

from deal_hunter.storage.database import get_session
from deal_hunter.storage.repositories import SentNotificationRepository

logger = logging.getLogger(__name__)


def record_sent_notification(
    *,
    alert_type: str,
    payload: dict,
    deal_id: str | None = None,
    profile: str | None = None,
) -> None:
    """Insert one row into sent_notifications. Errors are logged, never raised."""
    try:
        with get_session() as session:
            SentNotificationRepository(session).record(
                alert_type=alert_type,
                payload_json=json.dumps(payload),
                deal_id=deal_id,
                profile=profile,
            )
    except SQLAlchemyError as exc:
        logger.warning("sent_notifications insert failed: %s", exc)
    except Exception as exc:  # noqa: BLE001 — final safety net for fire-and-forget
        logger.warning("sent_notifications insert failed: %s", exc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_recorder.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/deal_hunter/notifiers/telegram/recorder.py tests/test_recorder.py
git commit -m "feat(telegram): add fire-and-forget sent-notification recorder"
```

---

## Task 4: Transport methods return `bool` (success)

**Files:**
- Modify: `src/deal_hunter/notifiers/telegram/transport.py`
- Test: `tests/test_charts.py` (existing — verify the `send_photo` tests still pass), new tests at `tests/test_transport_returns.py` (or extend an existing telegram test file — see Step 5).

This task makes a foundational change so Task 5 can record only on success. Existing typed `send_*` methods still return `None` for now — Task 5 wires recording.

- [ ] **Step 1: Write the failing test**

Create `tests/test_transport_returns.py`:

```python
"""Tests asserting that low-level transport methods return bool (True = success)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from deal_hunter.notifiers.telegram.transport import TelegramNotifier


@pytest.fixture
def notifier():
    return TelegramNotifier(bot_token="t", chat_id="42")


def _mock_response(status_code: int, json_body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = "ok"
    resp.json.return_value = json_body or {"ok": True}
    return resp


def test_send_message_returns_true_on_200(notifier):
    with patch("deal_hunter.notifiers.telegram.transport.time.sleep"), patch(
        "deal_hunter.notifiers.telegram.transport.requests.post",
        return_value=_mock_response(200),
    ):
        ok = notifier._send_message("hi")
    assert ok is True


def test_send_message_returns_false_after_failures(notifier):
    with patch("deal_hunter.notifiers.telegram.transport.time.sleep"), patch(
        "deal_hunter.notifiers.telegram.transport.requests.post",
        return_value=_mock_response(500),
    ):
        ok = notifier._send_message("hi")
    assert ok is False


def test_send_text_forwards_send_message_return(notifier):
    with patch("deal_hunter.notifiers.telegram.transport.time.sleep"), patch(
        "deal_hunter.notifiers.telegram.transport.requests.post",
        return_value=_mock_response(200),
    ):
        assert notifier.send_text("hi") is True

    with patch("deal_hunter.notifiers.telegram.transport.time.sleep"), patch(
        "deal_hunter.notifiers.telegram.transport.requests.post",
        return_value=_mock_response(500),
    ):
        assert notifier.send_text("hi") is False


def test_send_photo_returns_true_on_200(notifier, tmp_path):
    fake = tmp_path / "x.png"
    fake.write_bytes(b"x")
    with patch("deal_hunter.notifiers.telegram.transport.time.sleep"), patch(
        "deal_hunter.notifiers.telegram.transport.requests.post",
        return_value=_mock_response(200),
    ):
        assert notifier.send_photo(str(fake)) is True


def test_send_photo_returns_false_after_failures(notifier, tmp_path):
    fake = tmp_path / "x.png"
    fake.write_bytes(b"x")
    with patch("deal_hunter.notifiers.telegram.transport.time.sleep"), patch(
        "deal_hunter.notifiers.telegram.transport.requests.post",
        return_value=_mock_response(500),
    ):
        assert notifier.send_photo(str(fake)) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_transport_returns.py -v`
Expected: FAIL — current methods return `None`.

- [ ] **Step 3: Update transport methods**

In `src/deal_hunter/notifiers/telegram/transport.py`:

Change the `_send_message` signature and return statements:

```python
    def _send_message(
        self,
        text: str,
        topic_id: int | None = None,
        disable_preview: bool = False,
        reply_markup: dict | None = None,
    ) -> bool:
        """Send message with retry and rate limiting. Returns True iff the API returned 200."""
```

Within the retry loop, change every `return` (success path) to `return True` and add `return False` after the loop (replacing the bare `logger.error(...)` final line — keep the log, just add the explicit return).

Look for the two lines like:
```python
                if resp.status_code == 200:
                    logger.info(f"Telegram: sent message ({len(text)} chars)")
                    return
```
Replace with:
```python
                if resp.status_code == 200:
                    logger.info(f"Telegram: sent message ({len(text)} chars)")
                    return True
```

After the retry loop:
```python
        logger.error("Telegram: failed to send after 3 attempts")
        return False
```

Apply the same transformation to `send_photo` (return `True` on 200, `return False` at the end).

Update `send_text` to return the result of `_send_message`:

```python
    def send_text(self, text: str, topic_id: int | None = None) -> bool:
        """Send a plain text message, optionally to a specific topic."""
        return self._send_message(text, topic_id=topic_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_transport_returns.py tests/test_charts.py tests/test_feedback_bot.py -v --tb=short 2>&1 | tail -20`
Expected: all PASSED. (No existing test asserted that the methods returned `None`, so the return-type change is backward-safe.)

- [ ] **Step 5: Commit**

```bash
git add src/deal_hunter/notifiers/telegram/transport.py tests/test_transport_returns.py
git commit -m "feat(telegram): transport methods return bool (success)"
```

---

## Task 5: Wire recording into typed `send_*` methods

**Files:**
- Modify: `src/deal_hunter/notifiers/telegram/transport.py`
- Test: `tests/test_transport_returns.py` (extend with recording tests)

Typed methods (`send_alert`, `send_summary`, `send_price_drop_alert`, `send_watchlist_alert`, `send_digest`) each gain an optional `profile: str | None = None` kwarg and record themselves after `_send_message` returns True.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_transport_returns.py`:

```python
class TestRecordingFromTypedSends:
    """Each typed send_* method records exactly one row on success and zero on failure."""

    def _setup(self, monkeypatch, success: bool):
        """Patch HTTP + capture record_sent_notification calls."""
        from deal_hunter.notifiers.telegram import transport as tr

        resp = _mock_response(200 if success else 500)
        monkeypatch.setattr(tr.time, "sleep", lambda *_a, **_k: None)
        monkeypatch.setattr(tr.requests, "post", lambda *a, **k: resp)

        captured: list[dict] = []

        def _capture(**kw):
            captured.append(kw)

        monkeypatch.setattr(tr, "record_sent_notification", _capture)
        return captured

    def test_send_alert_records_with_deal_type(self, monkeypatch, notifier):
        from deal_hunter.sources.base import Deal

        captured = self._setup(monkeypatch, success=True)
        deal = Deal(
            id="pepper:1",
            title="x",
            price=100,
            link="https://x",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        notifier.send_alert(deal, 80, "tier", ["+a"], ["-b"], profile="bikes")
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "deal"
        assert captured[0]["deal_id"] == "pepper:1"
        assert captured[0]["profile"] == "bikes"
        payload = captured[0]["payload"]
        assert payload["title"] == "x"
        assert payload["price"] == 100
        assert payload["score"] == 80

    def test_send_price_drop_alert_records(self, monkeypatch, notifier):
        from deal_hunter.sources.base import Deal

        captured = self._setup(monkeypatch, success=True)
        deal = Deal(
            id="pepper:2",
            title="y",
            price=80,
            link="https://y",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        pc = {
            "old_price": 200,
            "new_price": 80,
            "diff_pln": 120,
            "diff_percent": 60.0,
            "is_lowest_ever": True,
        }
        notifier.send_price_drop_alert(deal, pc, profile="bikes")
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "price_drop"
        assert captured[0]["deal_id"] == "pepper:2"
        assert captured[0]["payload"]["is_lowest_ever"] is True

    def test_send_watchlist_alert_records(self, monkeypatch, notifier):
        from deal_hunter.sources.base import Deal

        captured = self._setup(monkeypatch, success=True)
        deal = Deal(
            id="pepper:3",
            title="z",
            price=70,
            link="https://z",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        notifier.send_watchlist_alert(deal, target_price=80, current_price=70, profile="bikes")
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "watchlist"
        assert captured[0]["deal_id"] == "pepper:3"
        assert captured[0]["payload"]["target_price"] == 80

    def test_send_digest_records(self, monkeypatch, notifier):
        captured = self._setup(monkeypatch, success=True)
        notifier.send_digest(
            [
                {
                    "id": "p:1",
                    "title": "x",
                    "old_price": 200,
                    "new_price": 100,
                    "diff_pln": 100,
                    "diff_percent": 50.0,
                    "is_lowest_ever": False,
                }
            ]
        )
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "digest"
        assert captured[0]["deal_id"] is None
        assert captured[0]["profile"] is None
        assert captured[0]["payload"]["drop_count"] == 1

    def test_send_summary_records(self, monkeypatch, notifier):
        from deal_hunter.sources.base import Deal

        captured = self._setup(monkeypatch, success=True)
        deals = [
            Deal(
                id=f"pepper:{i}",
                title=f"t{i}",
                price=100 + i,
                link=f"https://x/{i}",
                source="pepper",
                description="",
                temperature=0,
                image_url="",
                published_at="",
            )
            for i in range(3)
        ]
        notifier.send_summary(
            [{"deal": d, "score": 70} for d in deals],
            profile="bikes",
        )
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "summary"
        assert captured[0]["profile"] == "bikes"
        assert captured[0]["payload"]["remaining_count"] == 3

    def test_no_record_on_telegram_failure(self, monkeypatch, notifier):
        from deal_hunter.sources.base import Deal

        captured = self._setup(monkeypatch, success=False)
        deal = Deal(
            id="pepper:1",
            title="x",
            price=100,
            link="",
            source="",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        notifier.send_alert(deal, 0, "", [], [], profile="bikes")
        assert captured == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_transport_returns.py::TestRecordingFromTypedSends -v`
Expected: FAIL — methods don't record yet, `profile` kwarg unknown for some.

- [ ] **Step 3: Wire recording into each typed method**

In `src/deal_hunter/notifiers/telegram/transport.py`:

At the top, import the recorder:

```python
from deal_hunter.notifiers.telegram.recorder import record_sent_notification
```

Then change each typed method:

`send_alert`:

```python
    def send_alert(
        self,
        deal: Deal,
        score: int,
        tier: str,
        plus: list[str],
        minus: list[str],
        topic_id: int | None = None,
        emoji: str = "\U0001f525",
        size_warning: str = "",
        currency: str = "PLN",
        snooze_days: int = 30,
        profile: str | None = None,
    ) -> None:
        """Send individual deal alert (messages in Polish for end users)."""
        msg = format_deal_alert(
            deal,
            score,
            tier,
            plus,
            minus,
            emoji=emoji,
            size_warning=size_warning,
            currency=currency,
        )
        keyboard = build_deal_keyboard(deal.link, deal.id, snooze_days=snooze_days)
        if self._send_message(msg, topic_id=topic_id, reply_markup=keyboard):
            record_sent_notification(
                alert_type="deal",
                payload={
                    "title": deal.title,
                    "price": deal.price,
                    "link": deal.link,
                    "score": score,
                    "plus": list(plus)[:6],
                    "minus": list(minus)[:4],
                },
                deal_id=deal.id,
                profile=profile,
            )
```

`send_summary`:

```python
    def send_summary(
        self,
        remaining_alerts: list[dict],
        topic_id: int | None = None,
        emoji: str = "\U0001f525",
        currency: str = "PLN",
        profile: str | None = None,
    ) -> None:
        """Send summary message for overflow alerts (messages in Polish for end users)."""
        msg = format_summary(remaining_alerts, emoji=emoji, currency=currency)
        if not msg:
            return
        if self._send_message(msg, topic_id=topic_id, disable_preview=True):
            sample_titles: list[str] = []
            for a in remaining_alerts[:5]:
                deal = a.get("deal")
                title = getattr(deal, "title", "") if deal is not None else ""
                sample_titles.append(title)
            record_sent_notification(
                alert_type="summary",
                payload={
                    "remaining_count": len(remaining_alerts),
                    "sample_titles": sample_titles,
                },
                profile=profile,
            )
```

`send_price_drop_alert`:

```python
    def send_price_drop_alert(
        self,
        deal: Deal,
        price_change: dict,
        topic_id: int | None = None,
        emoji: str = "\U0001f50d",
        currency: str = "PLN",
        snooze_days: int = 30,
        profile: str | None = None,
    ) -> None:
        """Send a price drop alert (messages in Polish for end users)."""
        msg = format_price_drop(deal, price_change, emoji=emoji, currency=currency)
        keyboard = build_deal_keyboard(deal.link, deal.id, snooze_days=snooze_days)
        if self._send_message(msg, topic_id=topic_id, reply_markup=keyboard):
            record_sent_notification(
                alert_type="price_drop",
                payload={
                    "title": deal.title,
                    "link": deal.link,
                    "old_price": price_change.get("old_price"),
                    "new_price": price_change.get("new_price"),
                    "diff_pln": price_change.get("diff_pln"),
                    "diff_percent": price_change.get("diff_percent"),
                    "is_lowest_ever": bool(price_change.get("is_lowest_ever")),
                },
                deal_id=deal.id,
                profile=profile,
            )
```

`send_watchlist_alert`:

```python
    def send_watchlist_alert(
        self,
        deal: Deal,
        target_price: int,
        current_price: int,
        topic_id: int | None = None,
        currency: str = "PLN",
        snooze_days: int = 30,
        profile: str | None = None,
    ) -> None:
        """Send watchlist target price alert (messages in Polish for end users)."""
        msg = format_watchlist_alert(deal, target_price, current_price, currency=currency)
        keyboard = build_deal_keyboard(deal.link, deal.id, snooze_days=snooze_days)
        if self._send_message(msg, topic_id=topic_id, reply_markup=keyboard):
            record_sent_notification(
                alert_type="watchlist",
                payload={
                    "title": deal.title,
                    "target_price": target_price,
                    "current_price": current_price,
                },
                deal_id=deal.id,
                profile=profile,
            )
```

`send_digest`:

```python
    def send_digest(
        self,
        drops: list[dict],
        topic_id: int | None = None,
        emoji: str = "\U0001f4ca",
        currency: str = "PLN",
    ) -> None:
        """Send weekly price digest (messages in Polish for end users)."""
        msg = format_digest(drops, emoji=emoji, currency=currency)
        if not msg:
            return
        if self._send_message(msg, topic_id=topic_id, disable_preview=True):
            # Store only IDs and a tiny shape per drop — keeps the row small.
            top_drops = [
                {
                    "id": d.get("id"),
                    "title": (d.get("title") or "")[:120],
                    "old_price": d.get("old_price"),
                    "new_price": d.get("new_price"),
                    "diff_percent": d.get("diff_percent"),
                    "is_lowest_ever": bool(d.get("is_lowest_ever")),
                }
                for d in drops[:10]
            ]
            record_sent_notification(
                alert_type="digest",
                payload={"drop_count": len(drops), "top_drops": top_drops},
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_transport_returns.py tests/test_charts.py -v --tb=short 2>&1 | tail -25`
Expected: all PASSED.

Also run the full pre-e2e suite to catch any caller-side regression:

`pytest tests/ --ignore=tests/e2e -q --tb=no 2>&1 | tail -10`
Expected: no NEW failures vs. the pre-task baseline. Pre-existing failures (e2e ordering issues, the 4 `TestPriceRepositoryDrops`) may remain — they are not your responsibility unless newly introduced.

- [ ] **Step 5: Commit**

```bash
git add src/deal_hunter/notifiers/telegram/transport.py tests/test_transport_returns.py
git commit -m "feat(telegram): typed send_* methods record on success"
```

---

## Task 6: Plumb `profile` from `AlertService` + record generic sends in alerter

**Files:**
- Modify: `src/deal_hunter/services/alerter.py`
- Modify: `src/deal_hunter/services/hunt_service.py` (one call to `send_watchlist_alert`)
- Test: `tests/test_services.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_services.py`:

```python
class TestAlertServiceRecording:
    """Verifies the alerter threads `profile` and records generic sends."""

    def _setup(self, monkeypatch):
        from deal_hunter.notifiers.telegram import transport as tr

        captured: list[dict] = []

        def _capture(**kw):
            captured.append(kw)

        # Patch BOTH the transport import and the alerter import (alerter
        # imports record_sent_notification directly).
        monkeypatch.setattr(tr, "record_sent_notification", _capture)
        from deal_hunter.services import alerter as alerter_mod

        monkeypatch.setattr(alerter_mod, "record_sent_notification", _capture)
        return captured

    def test_send_deal_alerts_passes_profile(self, monkeypatch):
        from deal_hunter.services.alerter import AlertService

        captured = self._setup(monkeypatch)

        recorded_kwargs: list[dict] = []

        class FakeTG:
            def send_alert(self, *a, **k):
                recorded_kwargs.append(k)

            def send_summary(self, *a, **k):
                recorded_kwargs.append(k)

        svc = AlertService(FakeTG())
        deal = type("D", (), {"id": "pepper:1", "title": "x", "price": 100, "link": ""})()
        svc.send_deal_alerts(
            [{"deal": deal, "score": 80, "plus": [], "minus": []}],
            profile={},
            profile_name="bikes",
            topic_id=None,
            max_alerts=5,
        )
        assert recorded_kwargs[0]["profile"] == "bikes"

    def test_flush_queued_records_each_flushed_alert(self, monkeypatch):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from deal_hunter.services.alerter import AlertService
        from deal_hunter.storage.models import Base
        from deal_hunter.storage.repositories import AlertQueueRepository

        captured = self._setup(monkeypatch)
        eng = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(eng)
        with Session(eng) as session:
            alert_repo = AlertQueueRepository(session)
            alert_repo.queue(
                "bikes",
                "price_drop",
                '{"deal_id":"pepper:1","title":"x","old_price":200,"new_price":100}',
                deal_id="pepper:1",
            )
            session.commit()

            class FakeTG:
                def send_text(self, *_a, **_k):
                    return True  # success

            svc = AlertService(FakeTG(), alert_repo)
            sent = svc.flush_queued("bikes", profile={}, topic_id=None, max_alerts=5)
            assert sent == 1
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "price_drop"
        assert captured[0]["deal_id"] == "pepper:1"
        assert captured[0]["profile"] == "bikes"

    def test_flush_queued_does_not_record_or_mark_sent_on_send_failure(self, monkeypatch):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from deal_hunter.services.alerter import AlertService
        from deal_hunter.storage.models import Base
        from deal_hunter.storage.repositories import AlertQueueRepository

        captured = self._setup(monkeypatch)
        eng = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(eng)
        with Session(eng) as session:
            alert_repo = AlertQueueRepository(session)
            alert_repo.queue("bikes", "deal", "{}", deal_id="pepper:1")
            session.commit()

            class FakeTG:
                def send_text(self, *_a, **_k):
                    return False  # failure

            sent = AlertService(FakeTG(), alert_repo).flush_queued("bikes", {}, None, 5)
            # Failed send → not recorded AND not marked-sent (still pending next run).
            assert sent == 0
            assert len(alert_repo.get_pending(profile="bikes")) == 1
        assert captured == []

    def test_send_source_failure_alert_records(self, monkeypatch):
        from deal_hunter.services.alerter import AlertService

        captured = self._setup(monkeypatch)

        class FakeTG:
            def send_text(self, *_a, **_k):
                return True

        svc = AlertService(FakeTG())
        svc.send_source_failure_alert(
            ["pepper"], {"pepper": {"consecutive_failures": 5, "last_success": "n"}}, None
        )
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "source_failure"
        assert captured[0]["profile"] is None
        assert "text_preview" in captured[0]["payload"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_services.py::TestAlertServiceRecording -v`
Expected: FAIL — `flush_queued` doesn't record; `send_source_failure_alert` doesn't record; some methods don't accept/pass `profile`.

- [ ] **Step 3: Update `AlertService` to thread `profile` and record generic sends**

In `src/deal_hunter/services/alerter.py`:

Add at the top of imports (after `from deal_hunter.services.notification_filter import should_send_price_drop`):

```python
from deal_hunter.notifiers.telegram.recorder import record_sent_notification
```

In `send_price_drop_alerts`, change the dispatch loop's typed-method call so it passes `profile=profile_name`:

```python
        else:
            for pda in drops[:count]:
                self.telegram.send_price_drop_alert(
                    pda["deal"],
                    pda["price_change"],
                    topic_id=topic_id,
                    emoji=emoji,
                    currency=currency,
                    snooze_days=snooze_days,
                    profile=profile_name,
                )
```

In `send_deal_alerts`, change both typed calls (the per-deal `send_alert` loop and the trailing `send_summary`):

```python
        for a in top_alerts:
            tier = (
                "\U0001f525\U0001f525\U0001f525 GORĄCA PEREŁKA"
                if a["score"] >= threshold_alert
                else "\U0001f525 ZNALAZŁEM OKAZJĘ"
            )
            self.telegram.send_alert(
                a["deal"],
                a["score"],
                tier,
                a["plus"],
                a["minus"],
                topic_id=topic_id,
                emoji=emoji,
                currency=currency,
                profile=profile_name,
            )

        if remaining:
            self.telegram.send_summary(
                remaining,
                topic_id=topic_id,
                emoji=emoji,
                currency=currency,
                profile=profile_name,
            )
```

Update `flush_queued` so each successful `send_text` records and skips records on failure:

```python
    def flush_queued(
        self, profile_name: str, profile: dict, topic_id: int | None, max_alerts: int
    ) -> int:
        """Flush queued alerts from previous quiet hours. Returns count flushed."""
        if not self.telegram or not self.alert_repo or is_quiet_hours(profile):
            return 0

        pending = self.alert_repo.get_pending(profile=profile_name)
        if not pending:
            return 0

        flush_count = min(len(pending), max_alerts)
        flushed_ids: list[int] = []
        for alert_data in pending[:flush_count]:
            payload = json.loads(alert_data["payload"])
            if alert_data["alert_type"] == "deal":
                ok = self.telegram.send_text(
                    f"\U0001f514 Zakolejkowany alert:\n"
                    f"<b>{html.escape(payload.get('title', ''))}</b>\n"
                    f"\U0001f4b0 {payload.get('price', 0):,} PLN\n"
                    f"Score: {payload.get('score', 0)}\n"
                    f'\U0001f517 <a href="{html.escape(payload.get("link", ""))}">Link</a>',
                    topic_id=topic_id,
                )
            elif alert_data["alert_type"] == "price_drop":
                ok = self.telegram.send_text(
                    f"\U0001f514 Zakolejkowany spadek ceny:\n"
                    f"<b>{html.escape(payload.get('title', ''))}</b>\n"
                    f"{payload.get('old_price', 0):,}"
                    f" → {payload.get('new_price', 0):,} PLN",
                    topic_id=topic_id,
                )
            else:
                ok = self.telegram.send_text(
                    f"\U0001f514 Zakolejkowany alert ({alert_data['alert_type']})",
                    topic_id=topic_id,
                )

            if ok:
                record_sent_notification(
                    alert_type=alert_data["alert_type"],
                    payload=payload,
                    deal_id=alert_data.get("deal_id"),
                    profile=profile_name,
                )
                flushed_ids.append(alert_data["id"])

        if flushed_ids:
            self.alert_repo.mark_sent(flushed_ids)
        logger.info(f"Flushed {len(flushed_ids)} queued alerts for {profile_name}")
        return len(flushed_ids)
```

(Note: `mark_sent` now only marks the alerts that actually succeeded — fixes a latent issue where a transient Telegram failure marked the queue row sent even though the user never saw it.)

Update `send_source_failure_alert`:

```python
    def send_source_failure_alert(
        self, failing_sources: list[str], sources_health: dict, topic_id: int | None
    ) -> None:
        """Send Telegram alert for sources with too many consecutive failures."""
        if not self.telegram:
            return

        lines = []
        for name in failing_sources:
            data = sources_health[name]
            count = data.get("consecutive_failures", 0)
            last = data.get("last_success", "never")
            lines.append(f"  • {name}: {count} consecutive failures (last success: {last})")

        msg = "⚠️ Deal Hunter: source failures detected!\n\n" + "\n".join(lines)
        if self.telegram.send_text(msg, topic_id=topic_id):
            record_sent_notification(
                alert_type="source_failure",
                payload={"text_preview": msg[:200]},
            )
```

- [ ] **Step 4: Update `hunt_service.run_profile` to pass `profile` on direct watchlist sends**

In `src/deal_hunter/services/hunt_service.py`, around the `telegram.send_watchlist_alert(...)` call (~line 181), add `profile=profile_name`:

```python
                    telegram.send_watchlist_alert(
                        deal,
                        target_price=trigger["target_price"],
                        current_price=deal.price,
                        topic_id=tg_topic,
                        currency=currency,
                        profile=profile_name,
                    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_services.py tests/test_quiet_hours.py -v --tb=short 2>&1 | tail -30`
Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/deal_hunter/services/alerter.py \
        src/deal_hunter/services/hunt_service.py \
        tests/test_services.py
git commit -m "feat(alerter): thread profile + record flush_queued/source_failure"
```

---

## Task 7: Record chart sends in `digest_service` + `chart_service`

**Files:**
- Modify: `src/deal_hunter/services/digest_service.py`
- Modify: `src/deal_hunter/services/chart_service.py`
- Test: extend an existing test file. Use `tests/test_charts.py` since the chart-send paths already have fixtures there.

- [ ] **Step 1: Inspect existing chart tests**

Run `grep -n "send_photo\|_send_chart\|def test_" tests/test_charts.py | head -20` and read enough of the file to confirm the existing call-site mocking pattern. The patches in those tests already give a working scaffold (mock `requests.post` returning 200).

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_charts.py`:

```python
class TestChartRecording:
    """`chart_service._send_chart` and `digest_service.run_digest` record chart sends."""

    def test_chart_service_records_after_successful_send_photo(self, monkeypatch, tmp_path):
        from deal_hunter.services import chart_service

        fake_chart = tmp_path / "c.png"
        fake_chart.write_bytes(b"x")

        captured: list[dict] = []
        monkeypatch.setattr(
            chart_service,
            "record_sent_notification",
            lambda **kw: captured.append(kw),
        )

        class FakeTG:
            def send_photo(self, *_a, **_k):
                return True

        monkeypatch.setattr(chart_service, "TelegramNotifier", lambda *_a, **_k: FakeTG())
        # Bypass the configured-check by stubbing settings.
        s = chart_service.get_settings()
        monkeypatch.setattr(s, "telegram_configured", True, raising=False)

        chart_service._send_chart(fake_chart, caption="Caption A")
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "chart"
        assert captured[0]["payload"]["caption"] == "Caption A"

    def test_chart_service_does_not_record_on_failure(self, monkeypatch, tmp_path):
        from deal_hunter.services import chart_service

        fake_chart = tmp_path / "c.png"
        fake_chart.write_bytes(b"x")
        captured: list[dict] = []
        monkeypatch.setattr(
            chart_service,
            "record_sent_notification",
            lambda **kw: captured.append(kw),
        )

        class FakeTG:
            def send_photo(self, *_a, **_k):
                return False

        monkeypatch.setattr(chart_service, "TelegramNotifier", lambda *_a, **_k: FakeTG())
        s = chart_service.get_settings()
        monkeypatch.setattr(s, "telegram_configured", True, raising=False)

        chart_service._send_chart(fake_chart, caption="Caption B")
        assert captured == []

    def test_digest_service_records_chart_after_successful_send_photo(self, monkeypatch, tmp_path):
        # We don't drive the full digest service here — we test just the chart
        # branch via the helper we'll introduce in digest_service.
        from deal_hunter.services import digest_service

        captured: list[dict] = []
        monkeypatch.setattr(
            digest_service,
            "record_sent_notification",
            lambda **kw: captured.append(kw),
        )

        class FakeTG:
            def send_photo(self, *_a, **_k):
                return True

        fake_chart = tmp_path / "d.png"
        fake_chart.write_bytes(b"x")
        digest_service._send_digest_chart(FakeTG(), str(fake_chart), caption="X")
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "chart"
        assert captured[0]["payload"]["caption"] == "X"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_charts.py::TestChartRecording -v`
Expected: FAIL — `record_sent_notification` not imported in either service; `_send_digest_chart` helper does not exist.

- [ ] **Step 4: Update `chart_service`**

In `src/deal_hunter/services/chart_service.py`, add at the top of imports:

```python
from deal_hunter.notifiers.telegram.recorder import record_sent_notification
```

Replace `_send_chart` with this version (which also accepts optional `deal_id` / `profile` for future callers but defaults to None to stay backward-compatible):

```python
def _send_chart(
    chart_path: object,
    *,
    caption: str,
    deal_id: str | None = None,
    profile: str | None = None,
) -> None:
    """Send a chart file to Telegram if configured, else print a skip message."""
    s = get_settings()
    if not s.telegram_configured:
        print("Telegram not configured — chart not sent.")
        return
    telegram = TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id)
    if telegram.send_photo(str(chart_path), caption=caption, topic_id=get_topic_id()):
        record_sent_notification(
            alert_type="chart",
            payload={"caption": caption},
            deal_id=deal_id,
            profile=profile,
        )
        print("Chart sent to Telegram.")
    else:
        print("Chart send failed.")
```

- [ ] **Step 5: Update `digest_service`**

In `src/deal_hunter/services/digest_service.py`, add at the top of imports:

```python
from deal_hunter.notifiers.telegram.recorder import record_sent_notification
```

Extract the chart branch into a small helper `_send_digest_chart` so the test in Step 2 can drive it. Replace the existing block (around lines 52-66) with a call to the new helper:

```python
    # Generate and send digest bar chart
    try:
        from deal_hunter.visualization.charts import generate_digest_chart

        chart_path = generate_digest_chart(drops)
        if _send_digest_chart(
            telegram,
            str(chart_path),
            caption="\U0001f4ca Największe spadki cen (ostatni tydzień)",
        ):
            print("Digest chart sent to Telegram.")
    except ImportError:
        logger.info("matplotlib not installed — skipping digest chart")
    except Exception as e:
        logger.warning(f"Failed to generate digest chart: {e}")
```

And add the helper at module scope:

```python
def _send_digest_chart(telegram: TelegramNotifier, chart_path: str, *, caption: str) -> bool:
    """Send digest chart + record the dispatch. Returns True on success."""
    topic_id = get_topic_id()
    if telegram.send_photo(chart_path, caption=caption, topic_id=topic_id):
        record_sent_notification(alert_type="chart", payload={"caption": caption})
        return True
    return False
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_charts.py -v --tb=short 2>&1 | tail -20`
Expected: all PASSED.

- [ ] **Step 7: Commit**

```bash
git add src/deal_hunter/services/chart_service.py \
        src/deal_hunter/services/digest_service.py \
        tests/test_charts.py
git commit -m "feat(charts): record chart sends in digest_service + chart_service"
```

---

## Task 8: Switch cooldown query to `SentNotificationRepository`; delete `last_price_drop_sent_at`

**Files:**
- Modify: `src/deal_hunter/services/notification_filter.py`
- Modify: `src/deal_hunter/services/alerter.py`
- Modify: `src/deal_hunter/services/hunt_service.py`
- Modify: `src/deal_hunter/storage/repositories/alert_queue.py`
- Test: `tests/test_notification_filter.py` (rename a parameter), `tests/test_quiet_hours.py` (delete a class), `tests/test_services.py` (update existing test).

- [ ] **Step 1: Update `notification_filter.should_send_price_drop` signature + call**

Replace `src/deal_hunter/services/notification_filter.py` with:

```python
"""Pure decision logic — should a price-drop alert be sent right now?

Called by AlertService.send_price_drop_alerts before quiet-hours queuing.
A suppressed alert is dropped entirely (not queued for later).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deal_hunter.core.notification_config import NotificationConfig
    from deal_hunter.storage.repositories import (
        OfferRepository,
        SentNotificationRepository,
    )


def should_send_price_drop(
    *,
    deal_id: str,
    profile_name: str,  # noqa: ARG001 — reserved for per-profile log filtering.
    is_all_time_low: bool,
    config: NotificationConfig,
    deal_repo: OfferRepository,
    sent_repo: SentNotificationRepository,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Returns (allow, reason). reason is for logging."""
    now = now or datetime.now()

    offer = deal_repo.get_by_id(deal_id)
    muted_until = (offer or {}).get("muted_until")
    # ISO-string compare works because lexical order matches chronological for ISO 8601.
    if muted_until and muted_until > now.isoformat():
        return False, f"muted_until={muted_until}"

    if config.cooldown_days <= 0:
        return True, "ok"

    last_sent = sent_repo.last_sent_at(deal_id, "price_drop")
    if not last_sent:
        return True, "ok"

    try:
        last_sent_dt = datetime.fromisoformat(last_sent)
    except ValueError:
        return True, "ok"

    cooldown_expires = last_sent_dt + timedelta(days=config.cooldown_days)
    if now >= cooldown_expires:
        return True, "ok"

    if is_all_time_low and config.alert_through_cooldown_if_ath_low:
        return True, "ath_override"

    remaining = cooldown_expires - now
    days_remaining = max(1, int(remaining.total_seconds() // 86400))
    return False, f"cooldown:{days_remaining}d_remaining"
```

- [ ] **Step 2: Update the test helper in `tests/test_notification_filter.py`**

In `tests/test_notification_filter.py`, rename `alert_repo` → `sent_repo` and `last_price_drop_sent_at` → `last_sent_at` everywhere. The `_mock_repos` helper:

```python
def _mock_repos(muted_until=None, last_sent=None):
    deal_repo = MagicMock()
    deal_repo.get_by_id.return_value = (
        {"muted_until": muted_until} if muted_until is not None else {"muted_until": None}
    )
    sent_repo = MagicMock()
    sent_repo.last_sent_at.return_value = last_sent
    return deal_repo, sent_repo
```

Update every test that destructures `deal_repo, alert_repo = _mock_repos(...)` to `deal_repo, sent_repo = _mock_repos(...)` and every `should_send_price_drop(..., alert_repo=alert_repo, ...)` to `..., sent_repo=sent_repo, ...`.

- [ ] **Step 3: Update `AlertService` to accept and use `sent_repo`**

In `src/deal_hunter/services/alerter.py`:

Update the TYPE_CHECKING block:

```python
if TYPE_CHECKING:
    from deal_hunter.core.notification_config import NotificationConfig
    from deal_hunter.notifiers.telegram import TelegramNotifier
    from deal_hunter.storage.repositories import (
        AlertQueueRepository,
        OfferRepository,
        SentNotificationRepository,
    )
```

Add `sent_repo` to `__init__`:

```python
    def __init__(
        self,
        telegram: TelegramNotifier | None,
        alert_repo: AlertQueueRepository | None = None,
        offer_repo: OfferRepository | None = None,
        sent_repo: SentNotificationRepository | None = None,
    ) -> None:
        self.telegram = telegram
        self.alert_repo = alert_repo
        self.offer_repo = offer_repo
        self.sent_repo = sent_repo
```

Update the filter dispatch (in `send_price_drop_alerts`) to pass `sent_repo` and require both repos:

```python
        # Apply per-deal mute + per-profile cooldown filter.
        if notification_config and self.offer_repo and self.sent_repo:
            allowed: list[dict] = []
            for pda in drops:
                allow, reason = should_send_price_drop(
                    deal_id=pda["deal"].id,
                    profile_name=profile_name,
                    is_all_time_low=bool(pda["price_change"].get("is_lowest_ever")),
                    config=notification_config,
                    deal_repo=self.offer_repo,
                    sent_repo=self.sent_repo,
                )
                logger.info(
                    "price_drop_filter deal=%s allow=%s reason=%s",
                    pda["deal"].id,
                    allow,
                    reason,
                )
                if allow:
                    allowed.append(pda)
            drops = allowed
            if not drops:
                return 0
```

- [ ] **Step 4: Update `hunt_service.run_profile`**

In `src/deal_hunter/services/hunt_service.py`:

Add to imports:

```python
from deal_hunter.storage.repositories import (
    AlertQueueRepository,
    OfferRepository,
    PriceRepository,
    SeenDealRepository,
    SentNotificationRepository,
    WatchlistRepository,
)
```

In the session block, around the existing `offer_repo = OfferRepository(session)`, add:

```python
        sent_repo = SentNotificationRepository(session)
```

And update the `AlertService` construction:

```python
        alert_service = AlertService(
            telegram,
            alert_repo,
            offer_repo=offer_repo,
            sent_repo=sent_repo,
        )
```

- [ ] **Step 5: Delete `AlertQueueRepository.last_price_drop_sent_at`**

In `src/deal_hunter/storage/repositories/alert_queue.py`, remove the `last_price_drop_sent_at` method entirely.

- [ ] **Step 6: Delete the corresponding tests**

In `tests/test_quiet_hours.py`, delete the entire `TestAlertQueueDealId` class — both `test_last_price_drop_sent_at_*` cases AND `test_queue_persists_deal_id` (it's a redundant tiny class; the queue method is exercised elsewhere). Actually keep `test_queue_persists_deal_id` and `test_last_price_drop_sent_at_ignores_other_alert_types` is gone, so the class only has `test_queue_persists_deal_id` — fine to keep.

To be concrete: inside `class TestAlertQueueDealId:`, delete the three methods named `test_last_price_drop_sent_at_returns_none_when_never_sent`, `test_last_price_drop_sent_at_returns_most_recent`, and `test_last_price_drop_sent_at_ignores_other_alert_types`. Keep `test_queue_persists_deal_id`.

- [ ] **Step 7: Update the existing filter test in `tests/test_services.py`**

Find `test_alert_service_filters_muted_deal_before_send`. Update it so the `AlertService` gets a `sent_repo`:

```python
def test_alert_service_filters_muted_deal_before_send():
    """A deal with muted_until in the future must not enter alert_queue nor reach Telegram."""
    import pytest as _pytest
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from deal_hunter.core.notification_config import NotificationConfig
    from deal_hunter.services.alerter import AlertService
    from deal_hunter.storage.models import Base
    from deal_hunter.storage.repositories import (
        AlertQueueRepository,
        OfferRepository,
        SentNotificationRepository,
    )

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as session:
        offer_repo = OfferRepository(session)
        alert_repo = AlertQueueRepository(session)
        sent_repo = SentNotificationRepository(session)
        offer_repo.upsert(
            id="pepper:42", title="Test", price=100, link="", source="x",
            description="", image_url="", profile="bikes", score=0, category="",
            status="active", first_seen="2026-05-01T00:00:00",
            last_seen="2026-05-01T00:00:00",
        )
        offer_repo.set_muted_until("pepper:42", "2099-01-01T00:00:00")
        session.commit()

        telegram = type("FakeTG", (), {
            "send_price_drop_alert": lambda *a, **k: _pytest.fail("must not be called"),
        })()
        svc = AlertService(telegram, alert_repo, offer_repo=offer_repo, sent_repo=sent_repo)

        deal = type("D", (), {"id": "pepper:42", "title": "Test", "link": ""})()
        drops = [{
            "deal": deal,
            "price_change": {
                "type": "drop", "old_price": 200, "new_price": 100,
                "diff_pln": 100, "diff_percent": 50.0, "is_lowest_ever": False,
            },
        }]
        cfg = NotificationConfig(7, True, 30)
        sent = svc.send_price_drop_alerts(
            drops, profile={}, profile_name="bikes",
            topic_id=None, max_alerts=5, notification_config=cfg,
        )
        assert sent == 0
        assert alert_repo.get_pending() == []
```

- [ ] **Step 8: Add a new test asserting cooldown is read from `sent_notifications`**

Append to `tests/test_services.py`:

```python
def test_cooldown_reads_from_sent_notifications():
    """A recent row in sent_notifications must trigger cooldown suppression."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from deal_hunter.core.notification_config import NotificationConfig
    from deal_hunter.services.alerter import AlertService
    from deal_hunter.storage.models import Base
    from deal_hunter.storage.repositories import (
        AlertQueueRepository,
        OfferRepository,
        SentNotificationRepository,
    )

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as session:
        offer_repo = OfferRepository(session)
        alert_repo = AlertQueueRepository(session)
        sent_repo = SentNotificationRepository(session)

        offer_repo.upsert(
            id="pepper:99", title="x", price=100, link="", source="x",
            description="", image_url="", profile="bikes", score=0, category="",
            status="active", first_seen="2026-05-01T00:00:00",
            last_seen="2026-05-01T00:00:00",
        )
        sent_repo.record(
            alert_type="price_drop",
            payload_json='{"x": 1}',
            deal_id="pepper:99",
            sent_at=datetime.now().isoformat(),  # now → in cooldown
        )
        session.commit()

        telegram = type("FakeTG", (), {
            "send_price_drop_alert": lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("must not be called")
            ),
        })()
        svc = AlertService(telegram, alert_repo, offer_repo=offer_repo, sent_repo=sent_repo)
        deal = type("D", (), {"id": "pepper:99", "title": "x", "link": ""})()
        drops = [{
            "deal": deal,
            "price_change": {
                "type": "drop", "old_price": 200, "new_price": 100,
                "diff_pln": 100, "diff_percent": 50.0, "is_lowest_ever": False,
            },
        }]
        cfg = NotificationConfig(cooldown_days=7, alert_through_cooldown_if_ath_low=True, default_snooze_days=30)
        sent = svc.send_price_drop_alerts(
            drops, profile={}, profile_name="bikes",
            topic_id=None, max_alerts=5, notification_config=cfg,
        )
        assert sent == 0
```

Make sure `from datetime import datetime` is imported at the top of the test file; if not present, add it.

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_notification_filter.py tests/test_services.py tests/test_quiet_hours.py -v --tb=short 2>&1 | tail -30`
Expected: all PASSED.

- [ ] **Step 10: Commit**

```bash
git add src/deal_hunter/services/notification_filter.py \
        src/deal_hunter/services/alerter.py \
        src/deal_hunter/services/hunt_service.py \
        src/deal_hunter/storage/repositories/alert_queue.py \
        tests/test_notification_filter.py \
        tests/test_services.py \
        tests/test_quiet_hours.py
git commit -m "feat(filter): cooldown reads from sent_notifications; drop alert_queue lookup"
```

---

## Task 9: Dashboard `/notifications/history` page

**Files:**
- Modify: `src/deal_hunter/api/routes/notifications.py`
- Modify: `src/deal_hunter/api/templates/notifications.html` (add sub-nav)
- Create: `src/deal_hunter/api/templates/notifications_history.html`
- Create: `src/deal_hunter/api/templates/partials/notifications_history_table.html`
- Create: `src/deal_hunter/api/templates/partials/notifications_subnav.html`
- Test: `tests/test_dashboard_notifications.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_notifications.py`:

```python
class TestNotificationsHistoryPage:
    def test_history_page_renders_empty_state(self, client):
        response = client.get("/notifications/history")
        assert response.status_code == 200
        # No rows; either an "empty" element or the title
        assert "Notification history" in response.text or "Brak" in response.text

    def test_history_page_shows_recent_send(self, client, dashboard_session):
        from datetime import datetime
        from deal_hunter.storage.repositories import SentNotificationRepository

        SentNotificationRepository(dashboard_session).record(
            alert_type="price_drop",
            payload_json='{"title": "TestDeal99"}',
            deal_id="pepper:99999",
            profile="bikes",
            sent_at=datetime.now().isoformat(),
        )
        dashboard_session.flush()

        response = client.get("/notifications/history")
        assert response.status_code == 200
        assert "TestDeal99" in response.text or "pepper:99999" in response.text

    def test_history_filter_by_alert_type(self, client, dashboard_session):
        from deal_hunter.storage.repositories import SentNotificationRepository

        repo = SentNotificationRepository(dashboard_session)
        repo.record(alert_type="deal", payload_json='{"title": "Deal-A"}')
        repo.record(alert_type="price_drop", payload_json='{"title": "Drop-B"}')
        dashboard_session.flush()

        response = client.get("/notifications/history?alert_type=price_drop")
        assert response.status_code == 200
        assert "Drop-B" in response.text
        assert "Deal-A" not in response.text

    def test_history_filter_by_profile(self, client, dashboard_session):
        from deal_hunter.storage.repositories import SentNotificationRepository

        repo = SentNotificationRepository(dashboard_session)
        repo.record(alert_type="deal", payload_json='{"title": "Bikes-X"}', profile="bikes")
        repo.record(alert_type="deal", payload_json='{"title": "Hifi-Y"}', profile="hifi")
        dashboard_session.flush()

        response = client.get("/notifications/history?profile=bikes")
        assert response.status_code == 200
        assert "Bikes-X" in response.text
        assert "Hifi-Y" not in response.text

    def test_history_pagination(self, client, dashboard_session):
        from deal_hunter.storage.repositories import SentNotificationRepository

        repo = SentNotificationRepository(dashboard_session)
        for i in range(60):
            repo.record(
                alert_type="deal",
                payload_json=f'{{"title": "Row-{i:02d}"}}',
                sent_at=f"2026-05-12T{i // 60:02d}:{i % 60:02d}:00",
            )
        dashboard_session.flush()

        page1 = client.get("/notifications/history?page=1")
        page2 = client.get("/notifications/history?page=2")
        assert page1.status_code == 200
        assert page2.status_code == 200
        # Page 1 has the 50 newest; page 2 has the remaining 10.
        # The exact 'Row-NN' that appears depends on sort_order — just check
        # that the two pages have different subsets of Row IDs.
        page1_rows = {f"Row-{i:02d}" for i in range(60) if f"Row-{i:02d}" in page1.text}
        page2_rows = {f"Row-{i:02d}" for i in range(60) if f"Row-{i:02d}" in page2.text}
        assert len(page1_rows) == 50
        assert len(page2_rows) == 10
        assert page1_rows.isdisjoint(page2_rows)

    def test_subnav_present_on_both_pages(self, client):
        for path in ("/notifications", "/notifications/history"):
            response = client.get(path)
            assert response.status_code == 200
            # Sub-nav has both labels
            assert "Settings" in response.text
            assert "History" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard_notifications.py::TestNotificationsHistoryPage -v --tb=short`
Expected: FAIL — `/notifications/history` returns 404 and template doesn't have a sub-nav.

- [ ] **Step 3: Create sub-nav partial**

Create `src/deal_hunter/api/templates/partials/notifications_subnav.html`:

```html
<div class="flex gap-2 mb-4">
    <a href="/notifications"
       class="px-3 py-1 rounded-full text-sm transition-colors {% if subnav_active == 'settings' %}bg-primary text-on-primary{% else %}bg-surface-container text-on-surface-variant hover:bg-surface-container-high{% endif %}">
        Settings
    </a>
    <a href="/notifications/history"
       class="px-3 py-1 rounded-full text-sm transition-colors {% if subnav_active == 'history' %}bg-primary text-on-primary{% else %}bg-surface-container text-on-surface-variant hover:bg-surface-container-high{% endif %}">
        History
    </a>
</div>
```

- [ ] **Step 4: Create history page template**

Create `src/deal_hunter/api/templates/notifications_history.html`:

```html
{% extends "base.html" %}
{% set active_page = "notifications" %}
{% set subnav_active = "history" %}
{% block title %}Notification history — DealMonitor{% endblock %}
{% block page_title %}Notification history{% endblock %}
{% block content %}

{% include "partials/notifications_subnav.html" %}

<form method="get" action="/notifications/history"
      class="flex flex-wrap items-end gap-3 mb-4">
    <div>
        <label class="block text-xs font-medium text-on-surface-variant mb-1" for="alert_type">Type</label>
        <select name="alert_type" id="alert_type"
                class="bg-surface-container rounded-card px-3 py-2 text-sm">
            <option value="">Wszystkie</option>
            {% for t in ["deal", "price_drop", "summary", "watchlist", "digest", "source_failure", "chart"] %}
                <option value="{{ t }}" {% if alert_type == t %}selected{% endif %}>{{ t }}</option>
            {% endfor %}
        </select>
    </div>
    <div>
        <label class="block text-xs font-medium text-on-surface-variant mb-1" for="profile">Profile</label>
        <select name="profile" id="profile"
                class="bg-surface-container rounded-card px-3 py-2 text-sm">
            <option value="">Wszystkie</option>
            {% for p in profile_options %}
                <option value="{{ p }}" {% if profile == p %}selected{% endif %}>{{ p }}</option>
            {% endfor %}
        </select>
    </div>
    <button type="submit"
            class="bg-primary text-on-primary px-4 py-2 rounded-card text-sm font-medium">
        Filter
    </button>
</form>

<div id="history-table" class="bg-surface-container-low rounded-card overflow-hidden">
    {% include "partials/notifications_history_table.html" %}
</div>

{% if total_pages > 1 %}
<div class="flex justify-center gap-2 mt-4">
    {% if page > 1 %}
        <a href="?page={{ page - 1 }}{% if alert_type %}&alert_type={{ alert_type }}{% endif %}{% if profile %}&profile={{ profile }}{% endif %}"
           class="px-3 py-1 rounded-card text-sm bg-surface-container">← Prev</a>
    {% endif %}
    <span class="text-sm self-center text-on-surface-variant">Page {{ page }} of {{ total_pages }}</span>
    {% if page < total_pages %}
        <a href="?page={{ page + 1 }}{% if alert_type %}&alert_type={{ alert_type }}{% endif %}{% if profile %}&profile={{ profile }}{% endif %}"
           class="px-3 py-1 rounded-card text-sm bg-surface-container">Next →</a>
    {% endif %}
</div>
{% endif %}

{% endblock %}
```

- [ ] **Step 5: Create history table partial**

Create `src/deal_hunter/api/templates/partials/notifications_history_table.html`:

```html
{% if rows %}
<table class="w-full text-sm">
    <thead class="text-left text-xs text-on-surface-variant uppercase">
        <tr>
            <th class="px-3 py-2">Time</th>
            <th class="px-3 py-2">Type</th>
            <th class="px-3 py-2">Profile</th>
            <th class="px-3 py-2">Subject</th>
        </tr>
    </thead>
    <tbody>
        {% for r in rows %}
        <tr class="border-t border-outline-variant/30">
            <td class="px-3 py-2 text-on-surface-variant" title="{{ r.sent_at }}">{{ r.sent_at }}</td>
            <td class="px-3 py-2">
                <span class="px-2 py-0.5 rounded-full text-xs bg-secondary/10 text-secondary">{{ r.alert_type }}</span>
            </td>
            <td class="px-3 py-2">{{ r.profile or '—' }}</td>
            <td class="px-3 py-2">
                {% set title = r.payload.get('title') if r.payload is mapping else None %}
                {% if title %}
                    <span class="font-medium">{{ title }}</span>
                {% elif r.deal_id %}
                    <code class="text-xs">{{ r.deal_id }}</code>
                {% else %}
                    <span class="text-on-surface-variant text-xs">—</span>
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% else %}
<div class="px-4 py-8 text-center text-on-surface-variant text-sm">
    Brak wysłanych powiadomień.
</div>
{% endif %}
```

- [ ] **Step 6: Add sub-nav to the existing Settings template**

In `src/deal_hunter/api/templates/notifications.html`, set the sub-nav variable and include it. Edit the top of the file (after the existing `{% set active_page = "notifications" %}` line and `{% block page_title %}` block):

```html
{% extends "base.html" %}
{% set active_page = "notifications" %}
{% set subnav_active = "settings" %}
{% block title %}Notifications — DealMonitor{% endblock %}
{% block page_title %}Notifications{% endblock %}
{% block content %}

{% include "partials/notifications_subnav.html" %}

<div class="bg-surface-container-low rounded-card p-6 max-w-2xl">
... (existing form content unchanged)
```

(Confirm the file structure first via Read — leave the rest of the file untouched.)

- [ ] **Step 7: Add route**

In `src/deal_hunter/api/routes/notifications.py`, add imports at the top:

```python
from deal_hunter.api.dependencies import _get_mgr  # for profile list
from deal_hunter.storage.repositories import SentNotificationRepository
```

(If `_get_mgr` is not directly importable from `api.dependencies`, look at how it's used in `profiles.py` and follow that pattern.)

Add the route handler at the bottom of the file (before any module-level guard):

```python
_HISTORY_PER_PAGE = 50


@router.get("/notifications/history", response_class=HTMLResponse)
def notifications_history_page(
    request: Request,
    page: int = 1,
    alert_type: str | None = None,
    profile: str | None = None,
    session: Session = Depends(get_db),
) -> HTMLResponse:
    repo = SentNotificationRepository(session)
    page = max(1, page)
    rows = repo.list_recent(
        limit=_HISTORY_PER_PAGE,
        offset=(page - 1) * _HISTORY_PER_PAGE,
        alert_type=alert_type or None,
        profile=profile or None,
    )
    total = repo.count(alert_type=alert_type or None, profile=profile or None)
    total_pages = max(1, (total + _HISTORY_PER_PAGE - 1) // _HISTORY_PER_PAGE)

    # Profile dropdown: union of profiles managed by ProfileManager and any
    # historic profile values seen in the table (so retired profiles still appear).
    try:
        managed_profiles = list(_get_mgr().list_all())
    except Exception:
        managed_profiles = []
    profile_options = sorted(
        set(managed_profiles)
        | {r["profile"] for r in repo.list_recent(limit=500) if r["profile"]}
    )

    template = (
        "partials/notifications_history_table.html"
        if request.headers.get("HX-Request")
        else "notifications_history.html"
    )

    return templates.TemplateResponse(
        request,
        template,
        {
            "rows": rows,
            "page": page,
            "total_pages": total_pages,
            "alert_type": alert_type,
            "profile": profile,
            "profile_options": profile_options,
        },
    )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_dashboard_notifications.py -v --tb=short 2>&1 | tail -25`
Expected: all PASSED.

- [ ] **Step 9: Commit**

```bash
git add src/deal_hunter/api/routes/notifications.py \
        src/deal_hunter/api/templates/notifications.html \
        src/deal_hunter/api/templates/notifications_history.html \
        src/deal_hunter/api/templates/partials/notifications_history_table.html \
        src/deal_hunter/api/templates/partials/notifications_subnav.html \
        tests/test_dashboard_notifications.py
git commit -m "feat(dashboard): add /notifications/history page + Settings|History sub-nav"
```

---

## Task 10: Full-stack smoke test

Verification only — no new code.

- [ ] **Step 1: Run the full pre-e2e suite**

Run: `pytest tests/ --ignore=tests/e2e -x --tb=short 2>&1 | tail -20`
Expected: all PASSED. The four pre-existing `TestPriceRepositoryDrops` flakes from the prior branch were fixed (commit `d3a5c90`), so this should be fully green except for any e2e-coupled async tests when not excluded.

- [ ] **Step 2: Lint**

Run: `ruff check src/ tests/`
Expected: clean (or only pre-existing issues — diff against `main` if uncertain).

- [ ] **Step 3: Boot the dashboard locally**

```bash
source venv/bin/activate
uvicorn deal_hunter.api:app --reload
```

Visit:
- `http://localhost:8000/notifications` — Settings page; verify the `Settings | History` sub-nav appears with Settings active.
- `http://localhost:8000/notifications/history` — History page; verify the empty-state Polish message appears with History active.

- [ ] **Step 4: Manually trigger a recording**

In another terminal:

```bash
python -c "
from deal_hunter.notifiers.telegram.recorder import record_sent_notification
record_sent_notification(
    alert_type='price_drop',
    payload={'title': 'Manual smoke', 'old_price': 200, 'new_price': 100},
    deal_id='manual:1',
    profile='bikes',
)
print('recorded')
"
```

Refresh `/notifications/history` — the row should appear with the title `Manual smoke`. Filter by `alert_type=price_drop` and confirm it remains.

- [ ] **Step 5: No-op commit (only if smoke surfaced bugs that were fixed)**

Otherwise no commit. End of plan.

---

## Spec coverage table

| Spec requirement | Implemented in |
|---|---|
| `sent_notifications` table + indexes (migration 007) | Task 1 |
| `SentNotification` ORM model + column-set test | Task 1 |
| `SentNotificationRepository` with `record`/`last_sent_at`/`list_recent`/`count` | Task 2 |
| Fire-and-forget recorder; swallow + log DB errors | Task 3 |
| Transport methods return `bool` (`_send_message`, `send_photo`, `send_text`) | Task 4 |
| Typed `send_*` methods record on success with the per-method payload shape | Task 5 |
| `profile` kwarg threaded into typed methods from callers | Tasks 5 + 6 |
| `flush_queued` records each successful flush + only marks-sent on success | Task 6 |
| `send_source_failure_alert` records | Task 6 |
| Direct `send_watchlist_alert` in `hunt_service` passes `profile` | Task 6 |
| `digest_service` records chart send | Task 7 |
| `chart_service._send_chart` records | Task 7 |
| `notification_filter` reads `last_sent_at` from `SentNotificationRepository` | Task 8 |
| `AlertService` accepts and threads `sent_repo`; `hunt_service` constructs it | Task 8 |
| `AlertQueueRepository.last_price_drop_sent_at` deleted; tests removed | Task 8 |
| `/notifications/history` route, page, table partial, sub-nav | Task 9 |
| Filter by `alert_type` + `profile`, pagination | Task 9 |
| Dashboard tests for empty/single-row/filter/pagination/sub-nav | Task 9 |
| Watchdog send (`cli/main.py`) NOT recorded — out of scope | Documented in file-structure section + omitted from plan |

# Notification Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce price-drop alert noise by adding (a) per-deal cooldown with an all-time-low override, (b) permanent mute + temporary snooze controls, (c) global defaults overridable per profile, (d) Telegram inline buttons + bot commands + a new dashboard `/notifications` page.

**Architecture:** Per-deal mute state lives in a new `offers.muted_until` column. Cooldown is derived from a new `alert_queue.deal_id` column (backfilled from existing JSON payloads). A pure-function `services/notification_filter.py` decides per drop whether to send, called from `services/alerter.py` before the existing quiet-hours queue. Global defaults live in `config/notifications.yaml` with per-profile YAML overrides — resolved via a new `NotificationConfig` dataclass at runtime.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, Alembic, FastAPI + Jinja2 + HTMX, python-telegram-bot v21, pyyaml, pydantic v2, pytest.

**Spec:** [docs/superpowers/specs/2026-05-11-notification-management-design.md](../specs/2026-05-11-notification-management-design.md)

---

## File Structure

**New files:**
- `src/deal_hunter/storage/migrations/versions/006_notification_settings.py` — Alembic migration: `offers.muted_until` column + `alert_queue.deal_id` column + backfill.
- `src/deal_hunter/core/notification_config.py` — `NotificationConfig` dataclass + loader (global YAML + per-profile resolution) + writer.
- `src/deal_hunter/services/notification_filter.py` — pure `should_send_price_drop(...)` function.
- `src/deal_hunter/api/routes/notifications.py` — `/notifications` page + `POST /api/notifications/global` + `POST /api/deals/{id}/mute|unmute`.
- `src/deal_hunter/api/templates/notifications.html` — global settings form page.
- `src/deal_hunter/api/templates/partials/deal_mute_controls.html` — HTMX-swappable row fragment for mute/snooze buttons + badge.
- `tests/test_migration_006_notification_settings.py`
- `tests/test_notification_config.py`
- `tests/test_notification_filter.py`
- `tests/test_dashboard_notifications.py` (avoid extending the already-1600-line `test_dashboard.py`).
- `config/notifications.yaml` — auto-created on first run; checked in with defaults.

**Modified files:**
- `src/deal_hunter/storage/models.py` — add `Offer.muted_until` column + `AlertQueue.deal_id` column + index.
- `src/deal_hunter/storage/repositories/offer.py` — add `set_muted_until`, `clear_muted_until`, `get_muted`, and surface `muted_until` in `_to_dict`.
- `src/deal_hunter/storage/repositories/alert_queue.py` — `queue` accepts a `deal_id`; new `last_price_drop_sent_at(deal_id)`.
- `src/deal_hunter/core/types.py` — extend `PriceTrackingConfig` with `cooldown_days` + `alert_through_cooldown_if_ath_low`.
- `src/deal_hunter/services/price_tracker.py` — read the two new fields from profile YAML.
- `src/deal_hunter/services/alerter.py` — call the filter before queueing/sending; thread `deal_id` into `queue()`; thread profile config in.
- `src/deal_hunter/services/hunt_service.py` — pass `is_lowest_ever` and `NotificationConfig` through to `send_price_drop_alerts`.
- `src/deal_hunter/notifiers/telegram/keyboards.py` — second keyboard row with `mute:` and `snooze:` buttons; accept `snooze_days` for label.
- `src/deal_hunter/notifiers/telegram/transport.py` — `send_price_drop_alert` and `send_alert` thread `snooze_days` to the keyboard builder.
- `src/deal_hunter/bot/callbacks.py` — handle `mute:` and `snooze:` callback actions.
- `src/deal_hunter/bot/commands.py` — `/mute`, `/snooze`, `/unmute`, `/muted` commands.
- `src/deal_hunter/bot/main.py` — register new command handlers.
- `src/deal_hunter/api/app.py` — `include_router(notifications.router)`.
- `src/deal_hunter/api/templates/base.html` — sidebar link to `/notifications`.
- `src/deal_hunter/api/templates/watchlist.html` — `Wyciszone` filter chip.
- `src/deal_hunter/api/templates/partials/deal_row_actions.html` — surface mute badge + buttons (or include the new partial).
- `src/deal_hunter/utils/validation.py` — accept the two new optional `price_tracking` fields.

**Conventions in play (don't violate these):**
- Code/logs/comments in English; user-facing Telegram + dashboard strings in Polish.
- Logging via `logging` module, never `print()` (except `--verify` mode).
- Per-source 2s rate limiting, Telegram retry on 429 — leave alone, this feature touches neither.
- `Offer.first_seen_at` / `last_seen_at` etc. are stored as ISO strings (not real datetimes); `muted_until` follows the same convention.

---

## Task 1: Migration `006` — `offers.muted_until` + `alert_queue.deal_id`

**Files:**
- Create: `src/deal_hunter/storage/migrations/versions/006_notification_settings.py`
- Test: `tests/test_migration_006_notification_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migration_006_notification_settings.py
"""Round-trip + backfill test for Alembic revision 006_notification_settings."""

import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


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


def test_006_adds_muted_until_to_offers(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "006")
    assert "muted_until" in _columns(db_url, "offers")
    assert "ix_offers_muted_until" in _indexes(db_url, "offers")


def test_006_adds_deal_id_to_alert_queue(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "006")
    assert "deal_id" in _columns(db_url, "alert_queue")
    assert "ix_alert_queue_deal_id" in _indexes(db_url, "alert_queue")


def test_006_backfills_deal_id_from_payload(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)

    # Bring schema to 005 (alert_queue exists in 001, no deal_id column yet).
    command.upgrade(cfg, "005")
    eng = create_engine(db_url)
    payload = json.dumps({"deal_id": "pepper:42", "title": "x"})
    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO alert_queue (profile, alert_type, payload, created_at) "
                "VALUES (:p, :t, :pl, :c)"
            ),
            {"p": "bikes", "t": "price_drop", "pl": payload, "c": "2026-05-11T10:00:00"},
        )
    eng.dispose()

    command.upgrade(cfg, "006")

    eng = create_engine(db_url)
    with eng.begin() as conn:
        row = conn.execute(text("SELECT deal_id FROM alert_queue")).fetchone()
        assert row[0] == "pepper:42"
    eng.dispose()


def test_006_downgrade_removes_columns(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "006")
    command.downgrade(cfg, "005")
    assert "muted_until" not in _columns(db_url, "offers")
    assert "deal_id" not in _columns(db_url, "alert_queue")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_migration_006_notification_settings.py -v`
Expected: FAIL — revision 006 doesn't exist.

- [ ] **Step 3: Write the migration**

```python
# src/deal_hunter/storage/migrations/versions/006_notification_settings.py
"""Add offers.muted_until + alert_queue.deal_id, backfill deal_id from payload JSON.

Revision ID: 006
Revises: 005
Create Date: 2026-05-11
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("offers") as b:
        b.add_column(sa.Column("muted_until", sa.String(), nullable=True))
    op.create_index("ix_offers_muted_until", "offers", ["muted_until"])

    with op.batch_alter_table("alert_queue") as b:
        b.add_column(sa.Column("deal_id", sa.String(), nullable=True))
    op.create_index("ix_alert_queue_deal_id", "alert_queue", ["deal_id"])

    # Backfill deal_id from existing payload JSON.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, payload FROM alert_queue")).fetchall()
    for row in rows:
        try:
            payload = json.loads(row[1])
        except (TypeError, ValueError):
            continue
        deal_id = payload.get("deal_id") if isinstance(payload, dict) else None
        if deal_id:
            conn.execute(
                sa.text("UPDATE alert_queue SET deal_id = :did WHERE id = :id"),
                {"did": deal_id, "id": row[0]},
            )


def downgrade() -> None:
    op.drop_index("ix_alert_queue_deal_id", table_name="alert_queue")
    with op.batch_alter_table("alert_queue") as b:
        b.drop_column("deal_id")
    op.drop_index("ix_offers_muted_until", table_name="offers")
    with op.batch_alter_table("offers") as b:
        b.drop_column("muted_until")
```

- [ ] **Step 4: Update model definitions so `Base.metadata` matches**

Modify `src/deal_hunter/storage/models.py`:

In the `Offer` class — add after `callback_token` (around line 44):
```python
    muted_until: Mapped[str | None] = mapped_column(String, default=None)
```

Append to `Offer.__table_args__` (around line 55):
```python
        Index("ix_offers_muted_until", "muted_until"),
```

In the `AlertQueue` class — add after `sent_at` (around line 97):
```python
    deal_id: Mapped[str | None] = mapped_column(String, default=None)

    __table_args__ = (Index("ix_alert_queue_deal_id", "deal_id"),)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_migration_006_notification_settings.py -v`
Expected: 4 PASSED.

Also run the existing migration tests to confirm no regression:
Run: `pytest tests/test_migration_005_callback_token.py -v`
Expected: PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/deal_hunter/storage/migrations/versions/006_notification_settings.py \
        src/deal_hunter/storage/models.py \
        tests/test_migration_006_notification_settings.py
git commit -m "feat(db): add muted_until + alert_queue.deal_id (migration 006)"
```

---

## Task 2: Extend `PriceTrackingConfig` and read new fields from profile YAML

**Files:**
- Modify: `src/deal_hunter/core/types.py:14-18`
- Modify: `src/deal_hunter/services/price_tracker.py:23-32`
- Test: `tests/test_price_tracking.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_price_tracking.py`:

```python
def test_get_config_reads_cooldown_fields():
    from deal_hunter.services.price_tracker import PriceTracker

    profile = {
        "price_tracking": {
            "enabled": True,
            "cooldown_days": 14,
            "alert_through_cooldown_if_ath_low": False,
        }
    }
    cfg = PriceTracker.get_config(profile)
    assert cfg.cooldown_days == 14
    assert cfg.alert_through_cooldown_if_ath_low is False


def test_get_config_defaults_for_cooldown_fields():
    from deal_hunter.services.price_tracker import PriceTracker

    cfg = PriceTracker.get_config({})
    # Sentinel None = "fall back to global"; the resolver in notification_config
    # decides the actual value.
    assert cfg.cooldown_days is None
    assert cfg.alert_through_cooldown_if_ath_low is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_price_tracking.py::test_get_config_reads_cooldown_fields tests/test_price_tracking.py::test_get_config_defaults_for_cooldown_fields -v`
Expected: FAIL — `PriceTrackingConfig` has no `cooldown_days` attribute.

- [ ] **Step 3: Extend `PriceTrackingConfig`**

In `src/deal_hunter/core/types.py`, replace the existing dataclass (lines 13-18):

```python
@dataclass
class PriceTrackingConfig:
    enabled: bool = True
    min_drop_percent: int = 10
    min_drop_amount: int = 200
    track_increases: bool = False
    # New: notification-cooldown overrides. None = inherit from global config.
    cooldown_days: int | None = None
    alert_through_cooldown_if_ath_low: bool | None = None
```

- [ ] **Step 4: Update `PriceTracker.get_config` to read the new fields**

In `src/deal_hunter/services/price_tracker.py`, replace `get_config` (lines 23-32):

```python
    @staticmethod
    def get_config(profile: dict) -> PriceTrackingConfig:
        """Extract price tracking config from profile with defaults."""
        pt = profile.get("price_tracking", {})
        return PriceTrackingConfig(
            enabled=pt.get("enabled", True),
            min_drop_percent=pt.get("min_drop_percent", 10),
            min_drop_amount=pt.get("min_drop_amount", 200),
            track_increases=pt.get("track_increases", False),
            cooldown_days=pt.get("cooldown_days"),
            alert_through_cooldown_if_ath_low=pt.get("alert_through_cooldown_if_ath_low"),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_price_tracking.py -v`
Expected: all PASSED (including new ones).

- [ ] **Step 6: Commit**

```bash
git add src/deal_hunter/core/types.py \
        src/deal_hunter/services/price_tracker.py \
        tests/test_price_tracking.py
git commit -m "feat(price-tracking): add cooldown_days + ath-override fields"
```

---

## Task 3: `NotificationConfig` loader and global YAML file

**Files:**
- Create: `src/deal_hunter/core/notification_config.py`
- Create: `tests/test_notification_config.py`
- Create: `config/notifications.yaml`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_notification_config.py
"""Tests for NotificationConfig — global YAML + per-profile resolution."""

from pathlib import Path

import pytest
import yaml

from deal_hunter.core.notification_config import (
    DEFAULT_COOLDOWN_DAYS,
    DEFAULT_DEFAULT_SNOOZE_DAYS,
    DEFAULT_ALERT_THROUGH_COOLDOWN_IF_ATH_LOW,
    NotificationConfig,
    load_global_config,
    resolve_for_profile,
    save_global_config,
)


def test_load_global_missing_file_returns_hardcoded_defaults(tmp_path):
    cfg = load_global_config(tmp_path / "notifications.yaml")
    assert cfg.cooldown_days == DEFAULT_COOLDOWN_DAYS
    assert cfg.default_snooze_days == DEFAULT_DEFAULT_SNOOZE_DAYS
    assert cfg.alert_through_cooldown_if_ath_low == DEFAULT_ALERT_THROUGH_COOLDOWN_IF_ATH_LOW


def test_load_global_reads_existing_yaml(tmp_path):
    path = tmp_path / "notifications.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "price_drop_alerts": {
                    "cooldown_days": 14,
                    "alert_through_cooldown_if_ath_low": False,
                    "default_snooze_days": 7,
                }
            }
        )
    )
    cfg = load_global_config(path)
    assert cfg.cooldown_days == 14
    assert cfg.default_snooze_days == 7
    assert cfg.alert_through_cooldown_if_ath_low is False


def test_load_global_malformed_yaml_returns_defaults(tmp_path):
    path = tmp_path / "notifications.yaml"
    path.write_text("not: valid: yaml: at: all: [")
    cfg = load_global_config(path)
    assert cfg.cooldown_days == DEFAULT_COOLDOWN_DAYS


def test_load_global_partial_yaml_fills_in_defaults(tmp_path):
    path = tmp_path / "notifications.yaml"
    path.write_text(yaml.safe_dump({"price_drop_alerts": {"cooldown_days": 21}}))
    cfg = load_global_config(path)
    assert cfg.cooldown_days == 21
    assert cfg.default_snooze_days == DEFAULT_DEFAULT_SNOOZE_DAYS
    assert (
        cfg.alert_through_cooldown_if_ath_low
        == DEFAULT_ALERT_THROUGH_COOLDOWN_IF_ATH_LOW
    )


def test_resolve_for_profile_uses_profile_when_present():
    global_cfg = NotificationConfig(
        cooldown_days=7,
        alert_through_cooldown_if_ath_low=True,
        default_snooze_days=30,
    )
    profile = {
        "price_tracking": {
            "cooldown_days": 14,
            "alert_through_cooldown_if_ath_low": False,
        }
    }
    resolved = resolve_for_profile(global_cfg, profile)
    assert resolved.cooldown_days == 14
    assert resolved.alert_through_cooldown_if_ath_low is False
    # Snooze is global-only.
    assert resolved.default_snooze_days == 30


def test_resolve_for_profile_falls_back_to_global():
    global_cfg = NotificationConfig(
        cooldown_days=7,
        alert_through_cooldown_if_ath_low=True,
        default_snooze_days=30,
    )
    resolved = resolve_for_profile(global_cfg, {})
    assert resolved.cooldown_days == 7
    assert resolved.alert_through_cooldown_if_ath_low is True


def test_resolve_for_profile_zero_is_valid_override():
    """cooldown_days=0 must be honored (means: no cooldown)."""
    global_cfg = NotificationConfig(
        cooldown_days=7,
        alert_through_cooldown_if_ath_low=True,
        default_snooze_days=30,
    )
    resolved = resolve_for_profile(
        global_cfg, {"price_tracking": {"cooldown_days": 0}}
    )
    assert resolved.cooldown_days == 0


def test_save_global_config_writes_atomically(tmp_path):
    path = tmp_path / "notifications.yaml"
    cfg = NotificationConfig(
        cooldown_days=10,
        alert_through_cooldown_if_ath_low=False,
        default_snooze_days=45,
    )
    save_global_config(path, cfg)
    assert path.exists()
    data = yaml.safe_load(path.read_text())
    block = data["price_drop_alerts"]
    assert block["cooldown_days"] == 10
    assert block["alert_through_cooldown_if_ath_low"] is False
    assert block["default_snooze_days"] == 45
    # Roundtrip
    cfg2 = load_global_config(path)
    assert cfg2 == cfg


def test_save_global_config_does_not_leave_tmp_file(tmp_path):
    path = tmp_path / "notifications.yaml"
    save_global_config(
        path,
        NotificationConfig(
            cooldown_days=1,
            alert_through_cooldown_if_ath_low=True,
            default_snooze_days=1,
        ),
    )
    assert not any(p.name.endswith(".tmp") for p in tmp_path.iterdir())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_notification_config.py -v`
Expected: FAIL — `deal_hunter.core.notification_config` doesn't exist.

- [ ] **Step 3: Write the module**

```python
# src/deal_hunter/core/notification_config.py
"""Notification config — global YAML + per-profile resolution.

Global defaults live in `config/notifications.yaml` (auto-created on first
use). Each profile YAML may override `cooldown_days` and
`alert_through_cooldown_if_ath_low` inside its `price_tracking` block.

`default_snooze_days` is global-only — it's a UI default, not an alerting
rule, so per-profile override would be confusing without value.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN_DAYS = 7
DEFAULT_ALERT_THROUGH_COOLDOWN_IF_ATH_LOW = True
DEFAULT_DEFAULT_SNOOZE_DAYS = 30

_YAML_BLOCK = "price_drop_alerts"


@dataclass(frozen=True)
class NotificationConfig:
    cooldown_days: int
    alert_through_cooldown_if_ath_low: bool
    default_snooze_days: int


def _defaults() -> NotificationConfig:
    return NotificationConfig(
        cooldown_days=DEFAULT_COOLDOWN_DAYS,
        alert_through_cooldown_if_ath_low=DEFAULT_ALERT_THROUGH_COOLDOWN_IF_ATH_LOW,
        default_snooze_days=DEFAULT_DEFAULT_SNOOZE_DAYS,
    )


def load_global_config(path: Path) -> NotificationConfig:
    """Read the global YAML; missing or malformed → hardcoded defaults."""
    if not path.exists():
        return _defaults()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("Failed to parse %s, using defaults: %s", path, exc)
        return _defaults()
    if not isinstance(raw, dict):
        return _defaults()
    block = raw.get(_YAML_BLOCK)
    if not isinstance(block, dict):
        return _defaults()
    defaults = _defaults()
    return NotificationConfig(
        cooldown_days=_int_or(block.get("cooldown_days"), defaults.cooldown_days),
        alert_through_cooldown_if_ath_low=_bool_or(
            block.get("alert_through_cooldown_if_ath_low"),
            defaults.alert_through_cooldown_if_ath_low,
        ),
        default_snooze_days=_int_or(
            block.get("default_snooze_days"), defaults.default_snooze_days
        ),
    )


def save_global_config(path: Path, cfg: NotificationConfig) -> None:
    """Atomic write — temp + rename so a crash mid-write doesn't corrupt the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = {
        _YAML_BLOCK: {
            "cooldown_days": cfg.cooldown_days,
            "alert_through_cooldown_if_ath_low": cfg.alert_through_cooldown_if_ath_low,
            "default_snooze_days": cfg.default_snooze_days,
        }
    }
    tmp.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    os.replace(tmp, path)


def resolve_for_profile(
    global_cfg: NotificationConfig, profile: dict
) -> NotificationConfig:
    """Apply per-profile `price_tracking` overrides on top of global config."""
    pt = profile.get("price_tracking", {}) or {}
    cooldown = pt.get("cooldown_days")
    ath = pt.get("alert_through_cooldown_if_ath_low")
    return NotificationConfig(
        cooldown_days=cooldown if cooldown is not None else global_cfg.cooldown_days,
        alert_through_cooldown_if_ath_low=(
            ath if ath is not None else global_cfg.alert_through_cooldown_if_ath_low
        ),
        default_snooze_days=global_cfg.default_snooze_days,
    )


def _int_or(value: object, fallback: int) -> int:
    if isinstance(value, bool):  # bool is subclass of int — refuse it explicitly
        return fallback
    if isinstance(value, int):
        return value
    return fallback


def _bool_or(value: object, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    return fallback
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_notification_config.py -v`
Expected: 8 PASSED.

- [ ] **Step 5: Create the checked-in default config file**

Create `config/notifications.yaml`:

```yaml
# Global notification defaults. Per-profile YAML can override
# `cooldown_days` and `alert_through_cooldown_if_ath_low` in its
# `price_tracking:` block. `default_snooze_days` is global only.
price_drop_alerts:
  cooldown_days: 7
  alert_through_cooldown_if_ath_low: true
  default_snooze_days: 30
```

- [ ] **Step 6: Commit**

```bash
git add src/deal_hunter/core/notification_config.py \
        tests/test_notification_config.py \
        config/notifications.yaml
git commit -m "feat(config): add NotificationConfig loader + global defaults file"
```

---

## Task 4: Repository methods — `set_muted_until`, `clear_muted_until`, `get_muted`, and surfacing `muted_until` in `_to_dict`

**Files:**
- Modify: `src/deal_hunter/storage/repositories/offer.py`
- Test: `tests/test_repositories.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_repositories.py`:

```python
def test_set_muted_until_with_timestamp(dashboard_session):
    from deal_hunter.storage.repositories import OfferRepository

    repo = OfferRepository(dashboard_session)
    ok = repo.set_muted_until("pepper:99999", "2026-06-01T12:00:00")
    assert ok is True
    dashboard_session.flush()
    deal = repo.get_by_id("pepper:99999")
    assert deal["muted_until"] == "2026-06-01T12:00:00"


def test_set_muted_until_returns_false_for_missing_deal(dashboard_session):
    from deal_hunter.storage.repositories import OfferRepository

    assert OfferRepository(dashboard_session).set_muted_until("nope:0", "x") is False


def test_clear_muted_until_resets_to_null(dashboard_session):
    from deal_hunter.storage.repositories import OfferRepository

    repo = OfferRepository(dashboard_session)
    repo.set_muted_until("pepper:99999", "2026-06-01T12:00:00")
    dashboard_session.flush()
    ok = repo.clear_muted_until("pepper:99999")
    assert ok is True
    dashboard_session.flush()
    assert repo.get_by_id("pepper:99999")["muted_until"] is None


def test_get_muted_returns_only_future_muted_when_include_expired_false(dashboard_session):
    from deal_hunter.storage.repositories import OfferRepository

    repo = OfferRepository(dashboard_session)
    # Seed: one expired snooze, one active snooze, one unmuted.
    repo.upsert(id="muted:active", title="Active mute", price=100, link="", source="x",
                description="", image_url="", profile="bikes", score=0, category="",
                status="active", first_seen="2026-05-01T00:00:00",
                last_seen="2026-05-01T00:00:00")
    repo.upsert(id="muted:expired", title="Expired mute", price=100, link="", source="x",
                description="", image_url="", profile="bikes", score=0, category="",
                status="active", first_seen="2026-05-01T00:00:00",
                last_seen="2026-05-01T00:00:00")
    repo.set_muted_until("muted:active", "2099-01-01T00:00:00")
    repo.set_muted_until("muted:expired", "2020-01-01T00:00:00")
    dashboard_session.flush()

    active_only = repo.get_muted(now="2026-05-11T00:00:00", include_expired=False)
    all_muted = repo.get_muted(now="2026-05-11T00:00:00", include_expired=True)
    ids_active = {d["id"] for d in active_only}
    ids_all = {d["id"] for d in all_muted}
    assert "muted:active" in ids_active
    assert "muted:expired" not in ids_active
    assert {"muted:active", "muted:expired"}.issubset(ids_all)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_repositories.py -k muted -v`
Expected: FAIL — `OfferRepository` has no `set_muted_until`.

- [ ] **Step 3: Add methods + surface field in `_to_dict`**

In `src/deal_hunter/storage/repositories/offer.py`:

After `update_status` (around line 269), add:

```python
    def set_muted_until(self, deal_id: str, until: str) -> bool:
        """Set offer's muted_until ISO string. Returns False if the offer doesn't exist."""
        offer = self.session.get(Offer, deal_id)
        if not offer:
            return False
        offer.muted_until = until
        return True

    def clear_muted_until(self, deal_id: str) -> bool:
        """Clear offer's muted_until (set to NULL). Returns False if missing."""
        offer = self.session.get(Offer, deal_id)
        if not offer:
            return False
        offer.muted_until = None
        return True

    def get_muted(self, *, now: str | None = None, include_expired: bool = False) -> list[dict]:
        """Return offers with muted_until set.

        When `include_expired` is False (default), only offers whose `muted_until`
        is strictly greater than `now` (or current time) are returned.
        """
        from datetime import datetime as _dt

        stmt = select(Offer).where(Offer.muted_until.isnot(None))
        if not include_expired:
            now_str = now or _dt.now().isoformat()
            stmt = stmt.where(Offer.muted_until > now_str)
        stmt = stmt.order_by(Offer.muted_until.desc())
        return [self._to_dict(d) for d in self.session.scalars(stmt)]
```

Also in `_to_dict` (around line 395), add `muted_until` to the legacy/new key sections:

```python
            "muted_until": offer.muted_until,
```

Add it once — either block is fine; place it near `status`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_repositories.py -k muted -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/deal_hunter/storage/repositories/offer.py tests/test_repositories.py
git commit -m "feat(repo): add mute/unmute/get_muted to OfferRepository"
```

---

## Task 5: `AlertQueueRepository` — accept `deal_id` + `last_price_drop_sent_at`

**Files:**
- Modify: `src/deal_hunter/storage/repositories/alert_queue.py`
- Modify: `src/deal_hunter/services/alerter.py` (callsites)
- Test: `tests/test_quiet_hours.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_quiet_hours.py`:

```python
class TestAlertQueueDealId:
    """Tests for the new deal_id column on alert_queue."""

    def test_queue_persists_deal_id(self, session, alert_repo):
        alert_repo.queue("bikes", "price_drop", "{}", deal_id="pepper:42")
        session.flush()
        pending = alert_repo.get_pending()
        assert len(pending) == 1
        assert pending[0]["deal_id"] == "pepper:42"

    def test_last_price_drop_sent_at_returns_none_when_never_sent(self, session, alert_repo):
        assert alert_repo.last_price_drop_sent_at("pepper:42") is None

    def test_last_price_drop_sent_at_returns_most_recent(self, session, alert_repo):
        # Queue + mark sent (older).
        alert_repo.queue("bikes", "price_drop", "{}", deal_id="pepper:42")
        session.flush()
        ids_first = [a["id"] for a in alert_repo.get_pending()]
        alert_repo.mark_sent(ids_first)
        session.flush()

        # Queue + mark sent (newer).
        alert_repo.queue("bikes", "price_drop", "{}", deal_id="pepper:42")
        session.flush()
        ids_second = [a["id"] for a in alert_repo.get_pending()]
        alert_repo.mark_sent(ids_second)
        session.flush()

        sent_at = alert_repo.last_price_drop_sent_at("pepper:42")
        assert sent_at is not None  # And it's the most recent — exact value depends on clock.

    def test_last_price_drop_sent_at_ignores_other_alert_types(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", "{}", deal_id="pepper:42")
        session.flush()
        ids = [a["id"] for a in alert_repo.get_pending()]
        alert_repo.mark_sent(ids)
        session.flush()
        assert alert_repo.last_price_drop_sent_at("pepper:42") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_quiet_hours.py::TestAlertQueueDealId -v`
Expected: FAIL — `queue` doesn't accept `deal_id`; `last_price_drop_sent_at` doesn't exist.

- [ ] **Step 3: Update `AlertQueueRepository`**

Replace `queue` in `src/deal_hunter/storage/repositories/alert_queue.py`:

```python
    def queue(
        self,
        profile: str,
        alert_type: str,
        payload_json: str,
        *,
        deal_id: str | None = None,
    ) -> None:
        """Queue an alert for later sending."""
        alert = AlertQueue(
            profile=profile,
            alert_type=alert_type,
            payload=payload_json,
            created_at=datetime.now().isoformat(),
            deal_id=deal_id,
        )
        self.session.add(alert)
```

Update `get_pending` so each returned dict includes `deal_id`:

```python
        return [
            {
                "id": a.id,
                "profile": a.profile,
                "alert_type": a.alert_type,
                "payload": a.payload,
                "created_at": a.created_at,
                "deal_id": a.deal_id,
            }
            for a in self.session.scalars(stmt)
        ]
```

Add a new method at the bottom of the class:

```python
    def last_price_drop_sent_at(self, deal_id: str) -> str | None:
        """Return MAX(sent_at) for price_drop alerts on this deal, or None."""
        from sqlalchemy import func as _func

        stmt = select(_func.max(AlertQueue.sent_at)).where(
            AlertQueue.alert_type == "price_drop",
            AlertQueue.deal_id == deal_id,
            AlertQueue.sent_at.isnot(None),
        )
        return self.session.execute(stmt).scalar()
```

- [ ] **Step 4: Update `services/alerter.py` callsites to pass `deal_id`**

In `src/deal_hunter/services/alerter.py`, the two `alert_repo.queue(...)` callsites:

- Line ~135 (price drops): add `deal_id=pda["deal"].id` keyword:
```python
self.alert_repo.queue(profile_name, "price_drop", payload, deal_id=pda["deal"].id)
```
- Line ~181 (deal alerts): add `deal_id=a["deal"].id`:
```python
self.alert_repo.queue(profile_name, "deal", payload, deal_id=a["deal"].id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_quiet_hours.py -v`
Expected: all PASSED (existing + new).

- [ ] **Step 6: Commit**

```bash
git add src/deal_hunter/storage/repositories/alert_queue.py \
        src/deal_hunter/services/alerter.py \
        tests/test_quiet_hours.py
git commit -m "feat(repo): alert_queue accepts deal_id + last_price_drop_sent_at"
```

---

## Task 6: `notification_filter.py` — pure function `should_send_price_drop`

**Files:**
- Create: `src/deal_hunter/services/notification_filter.py`
- Create: `tests/test_notification_filter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_notification_filter.py
"""Tests for should_send_price_drop — pure decision logic."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from deal_hunter.core.notification_config import NotificationConfig
from deal_hunter.services.notification_filter import should_send_price_drop


def _cfg(cooldown=7, ath=True, snooze=30):
    return NotificationConfig(
        cooldown_days=cooldown,
        alert_through_cooldown_if_ath_low=ath,
        default_snooze_days=snooze,
    )


def _mock_repos(muted_until=None, last_sent=None):
    deal_repo = MagicMock()
    deal_repo.get_by_id.return_value = (
        {"muted_until": muted_until} if muted_until is not None else {"muted_until": None}
    )
    alert_repo = MagicMock()
    alert_repo.last_price_drop_sent_at.return_value = last_sent
    return deal_repo, alert_repo


def test_allows_when_never_alerted_and_not_muted():
    deal_repo, alert_repo = _mock_repos()
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=False,
        config=_cfg(),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=datetime(2026, 5, 11, 10, 0, 0),
    )
    assert allow is True
    assert reason == "ok"


def test_blocks_when_muted_permanently():
    deal_repo, alert_repo = _mock_repos(muted_until="9999-12-31T00:00:00")
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=True,  # ATH override does NOT bypass mute.
        config=_cfg(),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=datetime(2026, 5, 11, 10, 0, 0),
    )
    assert allow is False
    assert reason.startswith("muted_until=")


def test_blocks_when_snoozed_until_future():
    deal_repo, alert_repo = _mock_repos(muted_until="2026-06-01T00:00:00")
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=False,
        config=_cfg(),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=datetime(2026, 5, 11, 10, 0, 0),
    )
    assert allow is False
    assert reason.startswith("muted_until=")


def test_expired_snooze_treated_as_unmuted():
    deal_repo, alert_repo = _mock_repos(muted_until="2026-01-01T00:00:00")
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=False,
        config=_cfg(),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=datetime(2026, 5, 11, 10, 0, 0),
    )
    assert allow is True
    assert reason == "ok"


def test_blocks_within_cooldown_window():
    now = datetime(2026, 5, 11, 10, 0, 0)
    last_sent = (now - timedelta(days=3)).isoformat()
    deal_repo, alert_repo = _mock_repos(last_sent=last_sent)
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=False,
        config=_cfg(cooldown=7),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=now,
    )
    assert allow is False
    assert reason.startswith("cooldown:")


def test_ath_override_bypasses_cooldown():
    now = datetime(2026, 5, 11, 10, 0, 0)
    last_sent = (now - timedelta(days=3)).isoformat()
    deal_repo, alert_repo = _mock_repos(last_sent=last_sent)
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=True,
        config=_cfg(cooldown=7, ath=True),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=now,
    )
    assert allow is True
    assert reason == "ath_override"


def test_ath_override_disabled_still_blocks_in_cooldown():
    now = datetime(2026, 5, 11, 10, 0, 0)
    last_sent = (now - timedelta(days=3)).isoformat()
    deal_repo, alert_repo = _mock_repos(last_sent=last_sent)
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=True,
        config=_cfg(cooldown=7, ath=False),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=now,
    )
    assert allow is False
    assert reason.startswith("cooldown:")


def test_cooldown_zero_means_no_cooldown():
    now = datetime(2026, 5, 11, 10, 0, 0)
    last_sent = (now - timedelta(minutes=1)).isoformat()
    deal_repo, alert_repo = _mock_repos(last_sent=last_sent)
    allow, _ = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=False,
        config=_cfg(cooldown=0),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=now,
    )
    assert allow is True


def test_cooldown_just_expired_allows():
    now = datetime(2026, 5, 11, 10, 0, 0)
    last_sent = (now - timedelta(days=7, seconds=1)).isoformat()
    deal_repo, alert_repo = _mock_repos(last_sent=last_sent)
    allow, _ = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=False,
        config=_cfg(cooldown=7),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=now,
    )
    assert allow is True


def test_handles_missing_offer_gracefully():
    """If the offer doesn't exist yet (first time seeing it), there's nothing to mute."""
    deal_repo = MagicMock()
    deal_repo.get_by_id.return_value = None
    alert_repo = MagicMock()
    alert_repo.last_price_drop_sent_at.return_value = None
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=False,
        config=_cfg(),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=datetime(2026, 5, 11, 10, 0, 0),
    )
    assert allow is True
    assert reason == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_notification_filter.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Write the module**

```python
# src/deal_hunter/services/notification_filter.py
"""Pure decision logic — should a price-drop alert be sent right now?

Called by AlertService.send_price_drop_alerts before quiet-hours queuing.
A suppressed alert is dropped entirely (not queued for later).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deal_hunter.core.notification_config import NotificationConfig
    from deal_hunter.storage.repositories import AlertQueueRepository, OfferRepository


def should_send_price_drop(
    *,
    deal_id: str,
    profile_name: str,  # noqa: ARG001 — currently unused; reserved for per-profile log filtering.
    is_all_time_low: bool,
    config: NotificationConfig,
    deal_repo: OfferRepository,
    alert_repo: AlertQueueRepository,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Returns (allow, reason). reason is for logging."""
    now = now or datetime.now()

    offer = deal_repo.get_by_id(deal_id)
    muted_until = (offer or {}).get("muted_until")
    if muted_until:
        # ISO-string compare works because lexical order matches chronological for ISO 8601.
        if muted_until > now.isoformat():
            return False, f"muted_until={muted_until}"

    if config.cooldown_days <= 0:
        return True, "ok"

    last_sent = alert_repo.last_price_drop_sent_at(deal_id)
    if not last_sent:
        return True, "ok"

    try:
        last_sent_dt = datetime.fromisoformat(last_sent)
    except ValueError:
        # Malformed timestamp — fail open (better to alert than to suppress silently).
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_notification_filter.py -v`
Expected: 10 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/deal_hunter/services/notification_filter.py tests/test_notification_filter.py
git commit -m "feat(services): add notification_filter.should_send_price_drop"
```

---

## Task 7: Wire the filter into `AlertService.send_price_drop_alerts`

**Files:**
- Modify: `src/deal_hunter/services/alerter.py:104-147`
- Modify: `src/deal_hunter/services/hunt_service.py` (build + pass `NotificationConfig`, pass `OfferRepository` into `AlertService`)
- Test: `tests/test_services.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_services.py`:

```python
def test_alert_service_filters_muted_deal_before_send(monkeypatch):
    """A deal with muted_until in the future must not enter alert_queue nor reach Telegram."""
    from datetime import datetime
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from deal_hunter.core.notification_config import NotificationConfig
    from deal_hunter.services.alerter import AlertService
    from deal_hunter.storage.models import Base
    from deal_hunter.storage.repositories import AlertQueueRepository, OfferRepository

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as session:
        offer_repo = OfferRepository(session)
        alert_repo = AlertQueueRepository(session)
        offer_repo.upsert(
            id="pepper:42", title="Test", price=100, link="", source="x",
            description="", image_url="", profile="bikes", score=0, category="",
            status="active", first_seen="2026-05-01T00:00:00",
            last_seen="2026-05-01T00:00:00",
        )
        offer_repo.set_muted_until("pepper:42", "2099-01-01T00:00:00")
        session.commit()

        telegram = type("FakeTG", (), {
            "send_price_drop_alert": lambda *a, **k: pytest.fail("must not be called"),
        })()
        svc = AlertService(telegram, alert_repo, offer_repo=offer_repo)

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

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_services.py::test_alert_service_filters_muted_deal_before_send -v`
Expected: FAIL — `AlertService.__init__` doesn't accept `offer_repo`; `send_price_drop_alerts` doesn't accept `notification_config`.

- [ ] **Step 3: Update `AlertService`**

In `src/deal_hunter/services/alerter.py`:

Add to imports near the top:
```python
from deal_hunter.services.notification_filter import should_send_price_drop
```

Update the TYPE_CHECKING import block:
```python
if TYPE_CHECKING:
    from deal_hunter.core.notification_config import NotificationConfig
    from deal_hunter.notifiers.telegram import TelegramNotifier
    from deal_hunter.storage.repositories import AlertQueueRepository, OfferRepository
```

Update `__init__` (line 61-67):

```python
    def __init__(
        self,
        telegram: TelegramNotifier | None,
        alert_repo: AlertQueueRepository | None = None,
        offer_repo: OfferRepository | None = None,
    ) -> None:
        self.telegram = telegram
        self.alert_repo = alert_repo
        self.offer_repo = offer_repo
```

Replace `send_price_drop_alerts` (line 104-147) entirely:

```python
    def send_price_drop_alerts(
        self,
        drops: list[dict],
        profile: dict,
        profile_name: str,
        topic_id: int | None,
        max_alerts: int,
        notification_config: NotificationConfig | None = None,
    ) -> int:
        """Filter, then send or queue price drop alerts. Returns count sent/queued."""
        if not drops or not self.telegram:
            return 0

        # Apply per-deal mute + per-profile cooldown filter.
        if notification_config and self.alert_repo and self.offer_repo:
            allowed: list[dict] = []
            for pda in drops:
                allow, reason = should_send_price_drop(
                    deal_id=pda["deal"].id,
                    profile_name=profile_name,
                    is_all_time_low=bool(pda["price_change"].get("is_lowest_ever")),
                    config=notification_config,
                    deal_repo=self.offer_repo,
                    alert_repo=self.alert_repo,
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

        emoji = profile.get("emoji", "\U0001f50d")
        currency = profile.get("currency", "PLN")
        snooze_days = (
            notification_config.default_snooze_days if notification_config else 30
        )

        drops.sort(key=lambda x: x["price_change"]["diff_percent"], reverse=True)
        count = min(len(drops), max_alerts)

        if is_quiet_hours(profile) and self.alert_repo:
            for pda in drops[:count]:
                payload = json.dumps(
                    {
                        "deal_id": pda["deal"].id,
                        "title": pda["deal"].title,
                        "link": pda["deal"].link,
                        "old_price": pda["price_change"]["old_price"],
                        "new_price": pda["price_change"]["new_price"],
                        "diff_pln": pda["price_change"]["diff_pln"],
                        "diff_percent": pda["price_change"]["diff_percent"],
                    }
                )
                self.alert_repo.queue(
                    profile_name, "price_drop", payload, deal_id=pda["deal"].id
                )
            logger.info(f"Queued {count} price drop alerts (quiet hours)")
        else:
            for pda in drops[:count]:
                self.telegram.send_price_drop_alert(
                    pda["deal"],
                    pda["price_change"],
                    topic_id=topic_id,
                    emoji=emoji,
                    currency=currency,
                    snooze_days=snooze_days,
                )
            logger.info(f"Sent {count} price drop alerts for {profile_name}")
        return count
```

Note: the new `snooze_days=` kwarg passed to `send_price_drop_alert` lands in Task 8.

- [ ] **Step 4: Update hunt_service.py — build & pass config + repo**

In `src/deal_hunter/services/hunt_service.py`, near the top imports add:

```python
from deal_hunter.core.notification_config import load_global_config, resolve_for_profile
from deal_hunter.core.settings import get_settings
from deal_hunter.storage.repositories import OfferRepository as _NotifOfferRepo  # local alias
```

(Use whichever import alias avoids collision with an existing import.)

In the same function that builds `alert_service` (around line 124), change:

```python
        alert_service = AlertService(telegram, alert_repo)
```

to:

```python
        offer_repo = OfferRepository(session)
        alert_service = AlertService(telegram, alert_repo, offer_repo=offer_repo)
```

And resolve the per-profile config once near the top of the function. Add after `tg_config = profile.get("telegram", {})` (around line 107):

```python
        global_notif = load_global_config(get_settings().base_dir / "config" / "notifications.yaml")
        notification_config = resolve_for_profile(global_notif, profile)
```

Then update the call (around line 204):

```python
        alert_service.send_price_drop_alerts(
            price_drop_alerts,
            profile,
            profile_name,
            tg_topic,
            max_alerts,
            notification_config=notification_config,
        )
```

Note: `OfferRepository` may already be imported at the top of `hunt_service.py`. If yes, reuse it — do not double-import. Run `grep -n "OfferRepository" src/deal_hunter/services/hunt_service.py` to check.

- [ ] **Step 5: Run all alert-related tests**

Run: `pytest tests/test_services.py tests/test_quiet_hours.py tests/test_notification_filter.py -v`
Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/deal_hunter/services/alerter.py \
        src/deal_hunter/services/hunt_service.py \
        tests/test_services.py
git commit -m "feat(alerter): apply mute + cooldown filter before queue/send"
```

---

## Task 8: Telegram keyboard — second row with Mute + Snooze

**Files:**
- Modify: `src/deal_hunter/notifiers/telegram/keyboards.py`
- Modify: `src/deal_hunter/notifiers/telegram/transport.py` (thread `snooze_days` through to keyboard builder)
- Test: extend an existing `test_feedback_bot.py` block or create `tests/test_keyboards.py` (new — preferred to keep tests narrow)

- [ ] **Step 1: Write the failing test**

Create `tests/test_keyboards.py`:

```python
"""Tests for telegram inline keyboard builder."""

from deal_hunter.notifiers.telegram.keyboards import build_deal_keyboard


def test_keyboard_has_two_rows():
    kb = build_deal_keyboard("https://x", "pepper:1")
    rows = kb["inline_keyboard"]
    assert len(rows) == 2


def test_first_row_keeps_existing_buttons():
    rows = build_deal_keyboard("https://x", "pepper:1")["inline_keyboard"]
    labels = [b["text"] for b in rows[0]]
    assert any("Otwórz" in t for t in labels)
    assert any("Obserwuj" in t for t in labels)
    assert any("Skip" in t for t in labels)


def test_second_row_has_snooze_and_mute():
    rows = build_deal_keyboard("https://x", "pepper:1", snooze_days=30)["inline_keyboard"]
    labels = [b["text"] for b in rows[1]]
    assert any("Drzemka 30d" in t for t in labels)
    assert any("Wycisz" in t for t in labels)


def test_snooze_label_uses_configured_days():
    rows = build_deal_keyboard("https://x", "pepper:1", snooze_days=7)["inline_keyboard"]
    labels = [b["text"] for b in rows[1]]
    assert any("Drzemka 7d" in t for t in labels)


def test_callback_data_for_mute_and_snooze():
    rows = build_deal_keyboard("https://x", "pepper:1")["inline_keyboard"]
    callbacks = {b["text"]: b.get("callback_data") for b in rows[1]}
    mute_cb = next(v for k, v in callbacks.items() if "Wycisz" in k)
    snooze_cb = next(v for k, v in callbacks.items() if "Drzemka" in k)
    assert mute_cb.startswith("mute:")
    assert snooze_cb.startswith("snooze:")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_keyboards.py -v`
Expected: FAIL — keyboard only has one row.

- [ ] **Step 3: Update `build_deal_keyboard`**

Replace `src/deal_hunter/notifiers/telegram/keyboards.py`:

```python
"""Inline keyboard builders for Telegram deal alerts."""

from __future__ import annotations

from deal_hunter.storage.models import compute_callback_token

_MAX_CALLBACK_DATA_LEN = 64
_SHORT_ID_PREFIX = "id:"


def make_callback_token(deal_id: str) -> str:
    """Return a stable short token for long deal ids."""
    return compute_callback_token(deal_id)


def build_callback_data(action: str, deal_id: str) -> str:
    """Build callback_data that always respects Telegram's 64-byte limit."""
    direct = f"{action}:{deal_id}"
    if len(direct.encode("utf-8")) <= _MAX_CALLBACK_DATA_LEN:
        return direct
    return f"{action}:{_SHORT_ID_PREFIX}{make_callback_token(deal_id)}"


def build_deal_keyboard(deal_link: str, deal_id: str, snooze_days: int = 30) -> dict:
    """Build inline keyboard for a deal alert.

    Two rows:
      Row 1 — Otwórz, Obserwuj, Skip (existing behavior).
      Row 2 — Drzemka <Nd>, Wycisz   (new: notification controls).
    """
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f517 Otwórz", "url": deal_link},
                {"text": "⭐ Obserwuj", "callback_data": build_callback_data("watch", deal_id)},
                {"text": "\U0001f44e Skip", "callback_data": build_callback_data("skip", deal_id)},
            ],
            [
                {
                    "text": f"\U0001f4a4 Drzemka {snooze_days}d",
                    "callback_data": build_callback_data("snooze", deal_id),
                },
                {
                    "text": "\U0001f515 Wycisz",
                    "callback_data": build_callback_data("mute", deal_id),
                },
            ],
        ]
    }
```

- [ ] **Step 4: Update `transport.py` so `send_price_drop_alert` and `send_alert` thread `snooze_days` to the keyboard**

In `src/deal_hunter/notifiers/telegram/transport.py`:

Add `snooze_days: int = 30` to the signatures and pass it to `build_deal_keyboard`. Edit each of these methods (lines 47, 86, 99, plus `send_watchlist_alert` if it also uses the keyboard):

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
    ) -> None:
        ...
        keyboard = build_deal_keyboard(deal.link, deal.id, snooze_days=snooze_days)
        ...
```

```python
    def send_price_drop_alert(
        self,
        deal: Deal,
        price_change: dict,
        topic_id: int | None = None,
        emoji: str = "\U0001f50d",
        currency: str = "PLN",
        snooze_days: int = 30,
    ) -> None:
        ...
        keyboard = build_deal_keyboard(deal.link, deal.id, snooze_days=snooze_days)
        ...
```

Similarly for `send_watchlist_alert` (line 99): same parameter, same threading.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_keyboards.py tests/test_feedback_bot.py -v`
Expected: PASSED. Existing tests that assert keyboard contents (if any) still pass because Row 1 is unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/deal_hunter/notifiers/telegram/keyboards.py \
        src/deal_hunter/notifiers/telegram/transport.py \
        tests/test_keyboards.py
git commit -m "feat(telegram): add Drzemka/Wycisz buttons to deal keyboard"
```

---

## Task 9: Bot callbacks — `mute:` and `snooze:` actions

**Files:**
- Modify: `src/deal_hunter/bot/callbacks.py`
- Test: `tests/test_feedback_bot.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_feedback_bot.py`:

```python
@pytest.mark.asyncio
async def test_callback_mute_sets_permanent_mute():
    from contextlib import contextmanager
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from deal_hunter.bot.main import handle_callback
    from deal_hunter.storage.models import Base
    from deal_hunter.storage.repositories import OfferRepository

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as session:
        _seed_deal(session, "pepper:123", price=100)
        session.commit()

    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.data = "mute:pepper:123"
    update.callback_query.answer = AsyncMock()
    context = MagicMock()

    @contextmanager
    def _mock_session():
        with Session(eng) as s:
            yield s
            s.commit()

    with patch("deal_hunter.bot.callbacks.get_session", _mock_session):
        await handle_callback(update, context)

    update.callback_query.answer.assert_called_once()
    with Session(eng) as session:
        deal = OfferRepository(session).get_by_id("pepper:123")
        assert deal["muted_until"] is not None
        assert deal["muted_until"].startswith("9999")  # permanent sentinel


@pytest.mark.asyncio
async def test_callback_snooze_sets_future_timestamp():
    from contextlib import contextmanager
    from datetime import datetime
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from deal_hunter.bot.main import handle_callback
    from deal_hunter.storage.models import Base
    from deal_hunter.storage.repositories import OfferRepository

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as session:
        _seed_deal(session, "pepper:123", price=100)
        session.commit()

    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.data = "snooze:pepper:123"
    update.callback_query.answer = AsyncMock()
    context = MagicMock()

    @contextmanager
    def _mock_session():
        with Session(eng) as s:
            yield s
            s.commit()

    with patch("deal_hunter.bot.callbacks.get_session", _mock_session):
        await handle_callback(update, context)

    with Session(eng) as session:
        deal = OfferRepository(session).get_by_id("pepper:123")
        until = deal["muted_until"]
        assert until is not None
        # In the future, but not the permanent sentinel.
        assert until > datetime.now().isoformat()
        assert not until.startswith("9999")
```

(Reuse the existing `_seed_deal` helper if present in the test module; otherwise duplicate the pattern from earlier tests.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_feedback_bot.py -k "callback_mute or callback_snooze" -v`
Expected: FAIL — callback handler only handles `watch`/`skip`.

- [ ] **Step 3: Update `bot/callbacks.py`**

Replace the file:

```python
"""Inline-keyboard callback query handler."""

from __future__ import annotations

from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes

from deal_hunter.core.notification_config import load_global_config
from deal_hunter.core.settings import get_settings
from deal_hunter.storage.database import get_session
from deal_hunter.storage.repositories import FeedbackRepository, OfferRepository

PERMANENT_MUTE_SENTINEL = "9999-12-31T00:00:00"


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button presses on deal alerts."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    if ":" not in data:
        await query.answer("Nieznana akcja")
        return

    action, deal_ref = data.split(":", 1)

    if action not in ("watch", "skip", "mute", "snooze"):
        await query.answer("Nieznana akcja")
        return

    with get_session() as session:
        repo = OfferRepository(session)
        deal_id = repo.resolve_callback_deal_id(deal_ref)
        if not deal_id:
            await query.answer("Nie znaleziono oferty w bazie")
            return

        if action == "watch":
            if not repo.update_status(deal_id, "watching"):
                await query.answer("Nie znaleziono oferty w bazie")
                return
            FeedbackRepository(session).record(deal_id, action)
            await query.answer("⭐ Dodano do obserwowanych")
            return

        if action == "skip":
            if not repo.update_status(deal_id, "rejected"):
                await query.answer("Nie znaleziono oferty w bazie")
                return
            FeedbackRepository(session).record(deal_id, action)
            await query.answer("\U0001f44e Pominięto")
            return

        if action == "mute":
            if not repo.set_muted_until(deal_id, PERMANENT_MUTE_SENTINEL):
                await query.answer("Nie znaleziono oferty w bazie")
                return
            FeedbackRepository(session).record(deal_id, "mute")
            await query.answer("\U0001f515 Wyciszono")
            return

        if action == "snooze":
            cfg = load_global_config(
                get_settings().base_dir / "config" / "notifications.yaml"
            )
            until = (datetime.now() + timedelta(days=cfg.default_snooze_days)).isoformat()
            if not repo.set_muted_until(deal_id, until):
                await query.answer("Nie znaleziono oferty w bazie")
                return
            FeedbackRepository(session).record(deal_id, "snooze")
            await query.answer(
                f"\U0001f4a4 Wyciszono do {datetime.fromisoformat(until).strftime('%d.%m.%Y')}"
            )
            return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_feedback_bot.py -v`
Expected: all PASSED (existing + new).

- [ ] **Step 5: Commit**

```bash
git add src/deal_hunter/bot/callbacks.py tests/test_feedback_bot.py
git commit -m "feat(bot): handle mute + snooze callbacks"
```

---

## Task 10: Bot commands — `/mute`, `/snooze`, `/unmute`, `/muted`

**Files:**
- Modify: `src/deal_hunter/bot/commands.py`
- Modify: `src/deal_hunter/bot/main.py`
- Test: `tests/test_feedback_bot.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_feedback_bot.py`:

```python
@pytest.mark.asyncio
async def test_cmd_mute_sets_permanent_mute():
    from contextlib import contextmanager
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from deal_hunter.bot.main import cmd_mute
    from deal_hunter.storage.models import Base
    from deal_hunter.storage.repositories import OfferRepository

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        _seed_deal(s, "pepper:42", price=100)
        s.commit()

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["pepper:42"]

    @contextmanager
    def _mock_session():
        with Session(eng) as s:
            yield s
            s.commit()

    with patch("deal_hunter.bot.commands.get_session", _mock_session):
        await cmd_mute(update, context)

    update.message.reply_text.assert_called_once()
    with Session(eng) as s:
        assert OfferRepository(s).get_by_id("pepper:42")["muted_until"].startswith("9999")


@pytest.mark.asyncio
async def test_cmd_snooze_with_days_arg():
    from contextlib import contextmanager
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from deal_hunter.bot.main import cmd_snooze
    from deal_hunter.storage.models import Base
    from deal_hunter.storage.repositories import OfferRepository

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        _seed_deal(s, "pepper:42", price=100)
        s.commit()

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["pepper:42", "5"]

    @contextmanager
    def _mock_session():
        with Session(eng) as s:
            yield s
            s.commit()

    with patch("deal_hunter.bot.commands.get_session", _mock_session):
        await cmd_snooze(update, context)

    update.message.reply_text.assert_called_once()
    with Session(eng) as s:
        until = OfferRepository(s).get_by_id("pepper:42")["muted_until"]
        assert until and not until.startswith("9999")


@pytest.mark.asyncio
async def test_cmd_unmute_clears_mute():
    from contextlib import contextmanager
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from deal_hunter.bot.main import cmd_unmute
    from deal_hunter.storage.models import Base
    from deal_hunter.storage.repositories import OfferRepository

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        _seed_deal(s, "pepper:42", price=100)
        OfferRepository(s).set_muted_until("pepper:42", "9999-12-31T00:00:00")
        s.commit()

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["pepper:42"]

    @contextmanager
    def _mock_session():
        with Session(eng) as s:
            yield s
            s.commit()

    with patch("deal_hunter.bot.commands.get_session", _mock_session):
        await cmd_unmute(update, context)

    with Session(eng) as s:
        assert OfferRepository(s).get_by_id("pepper:42")["muted_until"] is None


@pytest.mark.asyncio
async def test_cmd_muted_lists_muted_deals():
    from contextlib import contextmanager
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from deal_hunter.bot.main import cmd_muted
    from deal_hunter.storage.models import Base
    from deal_hunter.storage.repositories import OfferRepository

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        _seed_deal(s, "pepper:42", price=100)
        OfferRepository(s).set_muted_until("pepper:42", "2099-01-01T00:00:00")
        s.commit()

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []

    @contextmanager
    def _mock_session():
        with Session(eng) as s:
            yield s
            s.commit()

    with patch("deal_hunter.bot.commands.get_session", _mock_session):
        await cmd_muted(update, context)

    update.message.reply_text.assert_called_once()
    msg = update.message.reply_text.call_args[0][0]
    assert "pepper:42" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_feedback_bot.py -k "cmd_mute or cmd_snooze or cmd_unmute or cmd_muted" -v`
Expected: FAIL — `cmd_mute` etc. not importable.

- [ ] **Step 3: Add commands**

Append to `src/deal_hunter/bot/commands.py`:

```python
from datetime import datetime, timedelta

from deal_hunter.core.notification_config import load_global_config
from deal_hunter.core.settings import get_settings

_PERMANENT_MUTE_SENTINEL = "9999-12-31T00:00:00"


async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/mute <deal_id> — permanent mute for a specific deal."""
    if not context.args:
        await update.message.reply_text("Użycie: /mute <deal_id>")
        return
    deal_id = context.args[0]
    with get_session() as session:
        ok = OfferRepository(session).set_muted_until(deal_id, _PERMANENT_MUTE_SENTINEL)
        if not ok:
            await update.message.reply_text(f"Nie znaleziono oferty: {html.escape(deal_id)}")
            return
        FeedbackRepository(session).record(deal_id, "mute")
    await update.message.reply_text(f"\U0001f515 Wyciszono ofertę {html.escape(deal_id)}")


async def cmd_snooze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/snooze <deal_id> [days] — temporary mute (defaults to global default_snooze_days)."""
    if not context.args:
        await update.message.reply_text("Użycie: /snooze <deal_id> [dni]")
        return

    deal_id = context.args[0]
    if len(context.args) >= 2:
        try:
            days = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Liczba dni musi być liczbą całkowitą.")
            return
        if days <= 0:
            await update.message.reply_text("Liczba dni musi być dodatnia.")
            return
    else:
        cfg = load_global_config(get_settings().base_dir / "config" / "notifications.yaml")
        days = cfg.default_snooze_days

    until = (datetime.now() + timedelta(days=days)).isoformat()
    with get_session() as session:
        ok = OfferRepository(session).set_muted_until(deal_id, until)
        if not ok:
            await update.message.reply_text(f"Nie znaleziono oferty: {html.escape(deal_id)}")
            return
        FeedbackRepository(session).record(deal_id, "snooze")
    nice_date = datetime.fromisoformat(until).strftime("%d.%m.%Y")
    await update.message.reply_text(
        f"\U0001f4a4 Wyciszono ofertę {html.escape(deal_id)} do {nice_date}"
    )


async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/unmute <deal_id> — clear mute on a deal."""
    if not context.args:
        await update.message.reply_text("Użycie: /unmute <deal_id>")
        return
    deal_id = context.args[0]
    with get_session() as session:
        ok = OfferRepository(session).clear_muted_until(deal_id)
        if not ok:
            await update.message.reply_text(f"Nie znaleziono oferty: {html.escape(deal_id)}")
            return
        FeedbackRepository(session).record(deal_id, "unmute")
    await update.message.reply_text(f"\U0001f50a Włączono powiadomienia: {html.escape(deal_id)}")


async def cmd_muted(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/muted — list currently muted/snoozed deals."""
    with get_session() as session:
        deals = OfferRepository(session).get_muted(include_expired=False)

    if not deals:
        await update.message.reply_text("Brak wyciszonych ofert.")
        return

    lines = [f"\U0001f515 <b>Wyciszone oferty ({len(deals)})</b>\n"]
    for d in deals[:20]:
        until = d.get("muted_until") or ""
        if until.startswith("9999"):
            tag = "(stałe)"
        else:
            try:
                tag = "(do " + datetime.fromisoformat(until).strftime("%d.%m.%Y") + ")"
            except ValueError:
                tag = ""
        title = html.escape((d.get("title") or "")[:60])
        deal_id = html.escape(d.get("id") or "")
        lines.append(f"• <code>{deal_id}</code> — {title} {tag}")

    msg = "\n".join(lines)
    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)
```

- [ ] **Step 4: Register commands in `bot/main.py`**

In `src/deal_hunter/bot/main.py`:

Update imports:
```python
from deal_hunter.bot.commands import (
    cmd_mute,
    cmd_muted,
    cmd_skip,
    cmd_snooze,
    cmd_status,
    cmd_target,
    cmd_unmute,
    cmd_watch,
    cmd_watchlist,
)
```

Update `__all__`:
```python
__all__ = [
    "cmd_mute",
    "cmd_muted",
    "cmd_skip",
    "cmd_snooze",
    "cmd_status",
    "cmd_target",
    "cmd_unmute",
    "cmd_watch",
    "cmd_watchlist",
    "handle_callback",
    "main",
]
```

Register handlers (after the existing `add_handler` calls, around line 55):
```python
    app.add_handler(CommandHandler("mute", cmd_mute))
    app.add_handler(CommandHandler("snooze", cmd_snooze))
    app.add_handler(CommandHandler("unmute", cmd_unmute))
    app.add_handler(CommandHandler("muted", cmd_muted))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_feedback_bot.py -v`
Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/deal_hunter/bot/commands.py src/deal_hunter/bot/main.py tests/test_feedback_bot.py
git commit -m "feat(bot): /mute /snooze /unmute /muted commands"
```

---

## Task 11: Profile validation accepts the new YAML fields

**Files:**
- Modify: `src/deal_hunter/utils/validation.py`
- Test: `tests/test_validation.py` (extend)

- [ ] **Step 1: Inspect current validation**

Run: `grep -n "price_tracking\|cooldown\|alert_through" src/deal_hunter/utils/validation.py`

- [ ] **Step 2: Write the failing test**

Append to `tests/test_validation.py`:

```python
def test_validate_profile_accepts_cooldown_days():
    from deal_hunter.utils.validation import validate_profile

    profile = {
        "name": "bikes",
        "sources": {"pepper": {"urls": ["x"]}},
        "budget": {"min": 100, "max": 1000},
        "score_rules": {"x": 1},
        "score_threshold": 10,
        "score_threshold_alert": 20,
        "price_tracking": {
            "enabled": True,
            "cooldown_days": 14,
            "alert_through_cooldown_if_ath_low": False,
        },
    }
    assert validate_profile(profile) == []


def test_validate_profile_rejects_negative_cooldown_days():
    from deal_hunter.utils.validation import validate_profile

    profile = {
        "name": "bikes",
        "sources": {"pepper": {"urls": ["x"]}},
        "budget": {"min": 100, "max": 1000},
        "score_rules": {"x": 1},
        "score_threshold": 10,
        "score_threshold_alert": 20,
        "price_tracking": {"cooldown_days": -1},
    }
    errors = validate_profile(profile)
    assert any("cooldown_days" in e for e in errors)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_validation.py -k cooldown -v`
Expected: FAIL on the rejection test (acceptance test may already pass if validation is loose; adapt accordingly).

- [ ] **Step 4: Add validation rules**

In `src/deal_hunter/utils/validation.py`, find the `price_tracking` validation block and add:

```python
    pt = profile.get("price_tracking", {}) or {}
    if "cooldown_days" in pt:
        v = pt["cooldown_days"]
        if not isinstance(v, int) or isinstance(v, bool) or v < 0 or v > 365:
            errors.append("price_tracking.cooldown_days must be int between 0 and 365")
    if "alert_through_cooldown_if_ath_low" in pt:
        if not isinstance(pt["alert_through_cooldown_if_ath_low"], bool):
            errors.append("price_tracking.alert_through_cooldown_if_ath_low must be bool")
```

(If there's an existing `price_tracking` validator function, add these checks inside it instead.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_validation.py -v`
Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/deal_hunter/utils/validation.py tests/test_validation.py
git commit -m "feat(validation): validate cooldown_days + ath-override fields"
```

---

## Task 12: Dashboard `/notifications` page + API + per-deal mute API

**Files:**
- Create: `src/deal_hunter/api/routes/notifications.py`
- Create: `src/deal_hunter/api/templates/notifications.html`
- Modify: `src/deal_hunter/api/app.py` (include the router)
- Modify: `src/deal_hunter/api/templates/base.html` (sidebar link)
- Modify: `src/deal_hunter/api/schemas.py` (Pydantic schemas)
- Create: `tests/test_dashboard_notifications.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dashboard_notifications.py
"""Tests for the notifications dashboard page + APIs."""

import pytest
import yaml


class TestNotificationsPage:
    def test_page_renders(self, client):
        # When the YAML file doesn't exist in test workspace, the loader returns
        # hardcoded defaults — both keys still render in the form.
        response = client.get("/notifications")
        assert response.status_code == 200
        assert "cooldown_days" in response.text
        assert "default_snooze_days" in response.text


class TestGlobalNotificationConfigApi:
    def test_post_updates_yaml(self, client, tmp_path, monkeypatch):
        # Point the config writer at tmp_path.
        from deal_hunter.api.routes import notifications as notif_routes
        monkeypatch.setattr(
            notif_routes,
            "_global_config_path",
            lambda: tmp_path / "notifications.yaml",
        )
        response = client.post(
            "/api/notifications/global",
            data={
                "cooldown_days": "10",
                "alert_through_cooldown_if_ath_low": "true",
                "default_snooze_days": "14",
            },
        )
        assert response.status_code == 200
        data = yaml.safe_load((tmp_path / "notifications.yaml").read_text())
        assert data["price_drop_alerts"]["cooldown_days"] == 10
        assert data["price_drop_alerts"]["default_snooze_days"] == 14
        assert data["price_drop_alerts"]["alert_through_cooldown_if_ath_low"] is True

    def test_post_validates_range(self, client, tmp_path, monkeypatch):
        from deal_hunter.api.routes import notifications as notif_routes
        monkeypatch.setattr(
            notif_routes,
            "_global_config_path",
            lambda: tmp_path / "notifications.yaml",
        )
        response = client.post(
            "/api/notifications/global",
            data={
                "cooldown_days": "-1",
                "alert_through_cooldown_if_ath_low": "true",
                "default_snooze_days": "14",
            },
        )
        assert response.status_code == 422


class TestPerDealMuteApi:
    def test_mute_sets_permanent(self, client):
        response = client.post(
            "/api/deals/pepper:99999/mute",
            data={"days": ""},  # empty = permanent
        )
        assert response.status_code == 200

    def test_snooze_sets_future_timestamp(self, client):
        response = client.post(
            "/api/deals/pepper:99999/mute",
            data={"days": "7"},
        )
        assert response.status_code == 200

    def test_mute_404_for_missing_deal(self, client):
        response = client.post(
            "/api/deals/nope:0/mute",
            data={"days": ""},
        )
        assert response.status_code == 404

    def test_unmute_clears_mute(self, client):
        client.post("/api/deals/pepper:99999/mute", data={"days": "5"})
        response = client.post("/api/deals/pepper:99999/unmute")
        assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard_notifications.py -v`
Expected: FAIL — routes don't exist.

- [ ] **Step 3: Add Pydantic schemas**

Append to `src/deal_hunter/api/schemas.py`:

```python
class GlobalNotificationConfig(BaseModel):
    cooldown_days: int = Field(ge=0, le=365)
    alert_through_cooldown_if_ath_low: bool
    default_snooze_days: int = Field(ge=1, le=365)


class MuteRequest(BaseModel):
    """`days` empty/None → permanent mute; positive int → snooze that many days."""

    days: int | None = Field(default=None, ge=1, le=365)
```

- [ ] **Step 4: Create the route module**

```python
# src/deal_hunter/api/routes/notifications.py
"""Notifications settings page + per-deal mute APIs."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from deal_hunter.api import templates
from deal_hunter.api.dependencies import get_db
from deal_hunter.api.schemas import GlobalNotificationConfig, MuteRequest
from deal_hunter.core.notification_config import (
    NotificationConfig,
    load_global_config,
    save_global_config,
)
from deal_hunter.core.settings import get_settings
from deal_hunter.storage.repositories import OfferRepository

PERMANENT_MUTE_SENTINEL = "9999-12-31T00:00:00"

router = APIRouter()


def _global_config_path() -> Path:
    return get_settings().base_dir / "config" / "notifications.yaml"


@router.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request) -> HTMLResponse:
    cfg = load_global_config(_global_config_path())
    return templates.TemplateResponse(
        request,
        "notifications.html",
        {"config": cfg},
    )


@router.post("/api/notifications/global")
def api_notifications_global(
    cooldown_days: str = Form(...),
    alert_through_cooldown_if_ath_low: str = Form(...),
    default_snooze_days: str = Form(...),
) -> Response:
    try:
        validated = GlobalNotificationConfig(
            cooldown_days=int(cooldown_days),
            alert_through_cooldown_if_ath_low=alert_through_cooldown_if_ath_low.lower()
            in {"true", "1", "on", "yes"},
            default_snooze_days=int(default_snooze_days),
        )
    except (ValueError, Exception) as exc:  # noqa: BLE001
        return JSONResponse(
            {"error": str(exc)}, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )

    save_global_config(
        _global_config_path(),
        NotificationConfig(
            cooldown_days=validated.cooldown_days,
            alert_through_cooldown_if_ath_low=validated.alert_through_cooldown_if_ath_low,
            default_snooze_days=validated.default_snooze_days,
        ),
    )
    return JSONResponse({"ok": True})


@router.post("/api/deals/{deal_id}/mute")
def api_deal_mute(
    deal_id: str,
    days: str = Form(""),
    session: Session = Depends(get_db),
) -> Response:
    parsed_days: int | None
    days_clean = days.strip()
    if not days_clean:
        parsed_days = None
    else:
        try:
            parsed_days = int(days_clean)
        except ValueError:
            raise HTTPException(status_code=422, detail="days must be an integer")
        try:
            MuteRequest(days=parsed_days)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(exc))

    if parsed_days is None:
        until = PERMANENT_MUTE_SENTINEL
    else:
        until = (datetime.now() + timedelta(days=parsed_days)).isoformat()

    ok = OfferRepository(session).set_muted_until(deal_id, until)
    if not ok:
        raise HTTPException(status_code=404, detail="Deal not found")
    return JSONResponse({"ok": True, "muted_until": until})


@router.post("/api/deals/{deal_id}/unmute")
def api_deal_unmute(
    deal_id: str,
    session: Session = Depends(get_db),
) -> Response:
    ok = OfferRepository(session).clear_muted_until(deal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Deal not found")
    return JSONResponse({"ok": True})
```

- [ ] **Step 5: Create the template**

```html
<!-- src/deal_hunter/api/templates/notifications.html -->
{% extends "base.html" %}
{% set active_page = "notifications" %}
{% block title %}Notifications — DealMonitor{% endblock %}
{% block page_title %}Notifications{% endblock %}
{% block content %}

<div class="bg-surface-container-low rounded-card p-6 max-w-2xl">
    <h2 class="font-headline text-lg font-semibold mb-4">Global notification defaults</h2>
    <p class="text-sm text-on-surface-variant mb-6">
        These defaults apply to every profile. Individual profile YAML files can
        override <code>cooldown_days</code> and
        <code>alert_through_cooldown_if_ath_low</code> in their
        <code>price_tracking:</code> block.
    </p>

    <form id="notif-form"
          hx-post="/api/notifications/global"
          hx-swap="none"
          hx-on::after-request="this.querySelector('#saved-msg').classList.remove('hidden')"
          class="space-y-5">
        <div>
            <label class="block text-sm font-medium mb-1" for="cooldown_days">
                Cooldown (days)
            </label>
            <input id="cooldown_days" name="cooldown_days" type="number" min="0" max="365"
                   value="{{ config.cooldown_days }}"
                   class="w-32 bg-surface-container rounded-card px-3 py-2 text-sm" />
            <p class="text-xs text-on-surface-variant mt-1">
                Silence repeat price-drop alerts for the same deal for this many days.
            </p>
        </div>

        <div>
            <label class="block text-sm font-medium mb-1">
                <input type="checkbox" name="alert_through_cooldown_if_ath_low"
                       value="true"
                       {% if config.alert_through_cooldown_if_ath_low %}checked{% endif %} />
                Alert through cooldown on new all-time low
            </label>
            <p class="text-xs text-on-surface-variant">
                If checked, a drop that hits a new historical low breaks through the
                cooldown window.
            </p>
        </div>

        <div>
            <label class="block text-sm font-medium mb-1" for="default_snooze_days">
                Default snooze (days)
            </label>
            <input id="default_snooze_days" name="default_snooze_days" type="number" min="1" max="365"
                   value="{{ config.default_snooze_days }}"
                   class="w-32 bg-surface-container rounded-card px-3 py-2 text-sm" />
            <p class="text-xs text-on-surface-variant mt-1">
                Default duration for the "Drzemka" button on Telegram alerts.
            </p>
        </div>

        <div class="pt-2">
            <button type="submit"
                    class="bg-primary text-on-primary px-4 py-2 rounded-card text-sm font-medium">
                Save
            </button>
            <span id="saved-msg" class="hidden text-sm text-on-surface-variant ml-3">Saved.</span>
        </div>
    </form>
</div>

{% endblock %}
```

The form posts plain string values; the route normalizes the checkbox (`"true"` / absent). When the checkbox is unchecked it's omitted from the form data — `alert_through_cooldown_if_ath_low` will arrive as `""`. Handle that in the route: treat absent/empty as `false`. Update the route's parsing:

```python
ath_raw = alert_through_cooldown_if_ath_low.strip().lower()
ath = ath_raw in {"true", "1", "on", "yes"}
```

(The route as written above already does this — just verify behavior in the test.)

- [ ] **Step 6: Register the router**

In `src/deal_hunter/api/app.py`, update the imports + `include_router` calls:

```python
    from deal_hunter.api.routes import alerts, deals, health, notifications, profiles, tuner

    app.include_router(deals.router)
    app.include_router(profiles.router)
    app.include_router(alerts.router)
    app.include_router(tuner.router)
    app.include_router(health.router)
    app.include_router(notifications.router)
```

- [ ] **Step 7: Add sidebar link**

In `src/deal_hunter/api/templates/base.html`, after the `Profiles` link (line 137), add:

```html
                <a href="/notifications" class="flex items-center gap-3 px-4 py-3 rounded-card text-sm font-medium transition-colors {% if active_page == 'notifications' %}bg-surface-container-high text-primary{% else %}text-on-surface-variant hover:bg-surface-container{% endif %}">
                    <span class="material-symbols-outlined text-[20px]">notifications_off</span>
                    Notifications
                </a>
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_dashboard_notifications.py -v`
Expected: all PASSED.

Also run the existing dashboard tests for sanity:
Run: `pytest tests/test_dashboard.py -k "TestIndexRedirect or TestDealsPage" -v`
Expected: PASSED (no regression).

- [ ] **Step 9: Commit**

```bash
git add src/deal_hunter/api/routes/notifications.py \
        src/deal_hunter/api/templates/notifications.html \
        src/deal_hunter/api/app.py \
        src/deal_hunter/api/templates/base.html \
        src/deal_hunter/api/schemas.py \
        tests/test_dashboard_notifications.py
git commit -m "feat(dashboard): /notifications page + per-deal mute APIs"
```

---

## Task 13: Watchlist `Wyciszone` chip + per-deal mute badge/buttons in deals UI

**Files:**
- Modify: `src/deal_hunter/api/templates/watchlist.html`
- Modify: `src/deal_hunter/api/routes/deals.py` or wherever the watchlist HTML view is rendered — surface `muted` filter param
- Modify: `src/deal_hunter/api/templates/partials/deals_table.html` (if it renders the rows) — add mute badge
- Test: `tests/test_dashboard_notifications.py` (extend)

- [ ] **Step 1: Locate watchlist route + table partial**

Run (and read the matches before proceeding):
```bash
grep -rn '@router\.get.*watchlist\|"/watchlist"' src/deal_hunter/api/routes/ src/deal_hunter/api/
grep -rn 'deal\.muted\|partials/deals_table' src/deal_hunter/api/templates/
```

The watchlist route is most likely in `src/deal_hunter/api/routes/deals.py` (search for the `watchlist_page` function or a `@router.get("/watchlist")` decorator). The row partial is `src/deal_hunter/api/templates/partials/deals_table.html` (referenced by `watchlist.html`). Write down the exact line numbers you find — you'll edit those locations in Steps 4 and 6 below.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_dashboard_notifications.py`:

```python
class TestWatchlistMutedFilter:
    def test_watchlist_with_muted_filter_shows_muted_deals(self, client, dashboard_session):
        from deal_hunter.storage.repositories import OfferRepository

        repo = OfferRepository(dashboard_session)
        repo.set_muted_until("pepper:99999", "2099-01-01T00:00:00")
        dashboard_session.flush()

        response = client.get("/watchlist?muted=1")
        assert response.status_code == 200
        # The page should render the muted deal somewhere
        assert "pepper:99999" in response.text or "Wycisz" in response.text or "muted" in response.text.lower()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_dashboard_notifications.py::TestWatchlistMutedFilter -v`
Expected: FAIL — the `muted` query param isn't honored.

- [ ] **Step 4: Update the watchlist route to honor `muted=1`**

Open the watchlist GET handler at the file:line found in Step 1. The current handler queries deals by status `'watching'`. Modify it to honor a new `muted` query parameter — when `?muted=1`, call `OfferRepository.get_muted(include_expired=False)` and pass `view_mode="muted"` to the template; otherwise keep the current behavior and pass `view_mode="watching"`. The handler shape (adapt names to match what you found):

```python
@router.get("/watchlist", response_class=HTMLResponse)
def watchlist_page(
    request: Request,
    muted: str | None = None,
    session: Session = Depends(get_db),
) -> HTMLResponse:
    repo = OfferRepository(session)
    if muted == "1":
        deals = repo.get_muted(include_expired=False)
        view_mode = "muted"
    else:
        deals = repo.get_by_status("watching", limit=200)
        view_mode = "watching"
    return templates.TemplateResponse(
        request,
        "watchlist.html",
        {"deals": deals, "view_mode": view_mode},
    )
```

(Use the existing handler's local conventions for response shape; this is illustrative.)

- [ ] **Step 5: Update `watchlist.html` to show filter chips**

Modify `src/deal_hunter/api/templates/watchlist.html`:

After the page-title block, add filter chips:

```html
<div class="flex gap-2 mb-4">
    <a href="/watchlist"
       class="px-3 py-1 rounded-full text-sm {% if view_mode != 'muted' %}bg-primary text-on-primary{% else %}bg-surface-container text-on-surface-variant{% endif %}">
        Obserwowane
    </a>
    <a href="/watchlist?muted=1"
       class="px-3 py-1 rounded-full text-sm {% if view_mode == 'muted' %}bg-primary text-on-primary{% else %}bg-surface-container text-on-surface-variant{% endif %}">
        Wyciszone
    </a>
</div>
```

(Default `view_mode` to `"watching"` in the route so the template doesn't get `None`.)

- [ ] **Step 6: Add a muted badge in the partial that renders deal rows**

Locate `src/deal_hunter/api/templates/partials/deals_table.html` (and any related row partial). Add inline near the title cell:

```html
{% if deal.muted_until %}
    {% if deal.muted_until.startswith('9999') %}
        <span class="ml-2 inline-block px-2 py-0.5 rounded-full text-xs bg-error/10 text-error">🔕 Wyciszono</span>
    {% else %}
        <span class="ml-2 inline-block px-2 py-0.5 rounded-full text-xs bg-secondary/10 text-secondary">💤 Drzemka</span>
    {% endif %}
{% endif %}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_dashboard_notifications.py -v`
Expected: all PASSED.

- [ ] **Step 8: Commit**

```bash
git add src/deal_hunter/api/templates/watchlist.html \
        src/deal_hunter/api/templates/partials/deals_table.html \
        src/deal_hunter/api/routes/ \
        tests/test_dashboard_notifications.py
git commit -m "feat(dashboard): Wyciszone filter + muted badge in deals table"
```

---

## Task 14: Smoke test the whole stack

This is a verification task — no new code; just confirm nothing is broken end-to-end.

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -x --tb=short`
Expected: all PASSED (no errors).

- [ ] **Step 2: Run ruff and mypy if configured**

Run: `ruff check src/ tests/`
Expected: clean (or only pre-existing issues — diff against `git stash` if uncertain).

Run: `mypy src/deal_hunter` (if configured)
Expected: no new errors.

- [ ] **Step 3: Manually exercise the dashboard**

Activate venv and start the dashboard:
```bash
source venv/bin/activate
uvicorn deal_hunter.api:app --reload
```

Open `http://localhost:8000/notifications`. Verify:
- Form renders with current `config/notifications.yaml` values.
- Saving with valid values updates the YAML file (`cat config/notifications.yaml`).
- `/watchlist?muted=1` chip toggles and shows muted deals (after muting one via `/api/deals/<id>/mute`).

- [ ] **Step 4: Manually exercise a deal-hunter run**

Run: `python -m deal_hunter --profile <some-profile> --verify -v`
Expected: no errors; logs show `price_drop_filter` lines if a price-drop is detected.

- [ ] **Step 5: Final commit (only if changes were made during smoke test)**

Otherwise no commit. End of plan.

---

## Spec coverage table

| Spec requirement | Implemented in |
|---|---|
| Per-profile cooldown days | Task 2 (PriceTrackingConfig) + Task 6 (filter) |
| All-time-low override during cooldown | Task 6 |
| Per-deal permanent mute | Task 4 (repo) + Task 9 (callbacks) + Task 10 (command) + Task 12 (API) |
| Per-deal temporary snooze (default 30d) | Task 4 + Task 9 + Task 10 + Task 12 |
| Global defaults in `config/notifications.yaml` | Task 3 |
| Per-profile YAML override pattern | Task 3 `resolve_for_profile` + Task 2 |
| Migration `offers.muted_until` | Task 1 |
| Conditional `alert_queue.deal_id` column + backfill | Task 1 |
| Filter in `services/notification_filter.py` | Task 6 |
| Filter integration in `alerter.py` before quiet-hours queue | Task 7 |
| Logging at INFO with allow/reason | Task 7 |
| Telegram inline keyboard adds Drzemka + Wycisz row | Task 8 |
| Snooze label reflects configured days | Task 8 |
| Bot callbacks `mute:` and `snooze:` | Task 9 |
| Bot commands `/mute`, `/snooze`, `/unmute`, `/muted` | Task 10 |
| Dashboard `/notifications` page | Task 12 |
| API endpoints (`/api/notifications/global`, `/api/deals/{id}/mute`, `/api/deals/{id}/unmute`) | Task 12 |
| Pydantic schemas for new endpoints | Task 12 |
| Watchlist `Wyciszone` filter chip | Task 13 |
| Mute badge in deal table rows | Task 13 |
| Profile YAML validation for new fields | Task 11 |
| Tests (filter, config, repo, callback, command, migration, dashboard) | Tasks 1, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13 |

## Open items deferred from spec (to verify during execution)

- **Survey assumption that `alert_queue` lacks `deal_id`** — confirmed during Task 1 by inspecting `storage/models.py`. The migration adds the column unconditionally.
- **`sent_at` semantics in `alert_queue`** — confirmed via `repositories/alert_queue.py:mark_sent`: set only at dispatch time, not enqueue. So `last_price_drop_sent_at` correctly returns "when the user last got bothered."
- **MAX_DATETIME sentinel storage** — using ISO string `"9999-12-31T00:00:00"`. Lexical comparison matches chronological for ISO 8601 dates with a 4-digit year, so the existing `muted_until > now.isoformat()` filter works. Tests cover this.

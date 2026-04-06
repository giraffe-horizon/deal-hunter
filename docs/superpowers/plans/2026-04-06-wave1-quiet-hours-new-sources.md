# Wave 1: Quiet Hours + New Sources — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement three independent features in parallel: A.3 Quiet Hours (alert queuing), B.1 x-kom/Morele stores (YAML definitions), B.2 Allegro RSS source (new Python source class).

**Architecture:** Each feature is independent with no shared code changes. A.3 adds an `alert_queue` SQLite table and quiet hours logic to `deal_hunter.py`. B.1 creates two new YAML store files auto-discovered by the existing engine. B.2 adds a new `RssSource` Python class using stdlib XML parsing.

**Tech Stack:** Python 3.12+, SQLite, xml.etree.ElementTree, existing YAML source engine, pytest

---

## File Structure

### A.3 Quiet Hours
- Modify: `storage/sqlite.py` — add `alert_queue` table + 3 methods
- Modify: `deal_hunter.py` — add `is_quiet_hours()`, modify alert flow, add flush logic
- Modify: `utils/validation.py` — validate `quiet_hours` config
- Modify: `.env.example` — add quiet hours vars
- Create: `tests/test_quiet_hours.py` — all quiet hours tests

### B.1 x-kom / Morele Stores
- Create: `stores/xkom.yaml` — x-kom store definition
- Create: `stores/morele.yaml` — morele store definition
- Create: `tests/fixtures/xkom_search.html` — HTML fixture
- Create: `tests/fixtures/morele_search.html` — HTML fixture
- Create: `tests/test_xkom_morele.py` — store parsing tests

### B.2 Allegro RSS Source
- Create: `sources/rss.py` — RssSource class
- Modify: `sources/__init__.py` — register in SOURCE_REGISTRY
- Create: `tests/fixtures/allegro_rss.xml` — RSS 2.0 fixture
- Create: `tests/fixtures/rss_atom.xml` — Atom fixture
- Create: `tests/test_rss_source.py` — RSS source tests

---

## Task 1: A.3 — Alert Queue SQLite Schema + Methods

**Files:**
- Modify: `storage/sqlite.py:10-41` (SCHEMA_SQL) and append new methods after line 498
- Create: `tests/test_quiet_hours.py`

- [ ] **Step 1: Write failing tests for alert queue SQLite methods**

Create `tests/test_quiet_hours.py`:

```python
"""Tests for quiet hours alert queuing."""

import json
from pathlib import Path

import pytest

from storage.sqlite import SQLiteStorage


@pytest.fixture
def db(tmp_path):
    """Fresh SQLite database for each test."""
    return SQLiteStorage(tmp_path / "test.db")


class TestAlertQueue:
    """Tests for alert_queue SQLite table and methods."""

    def test_queue_alert_stores_entry(self, db):
        payload = json.dumps({"deal_id": "pepper:123", "title": "Test Deal", "score": 85})
        db.queue_alert("bikes", "deal", payload)
        pending = db.get_pending_alerts()
        assert len(pending) == 1
        assert pending[0]["profile"] == "bikes"
        assert pending[0]["alert_type"] == "deal"
        assert json.loads(pending[0]["payload"])["deal_id"] == "pepper:123"

    def test_queue_multiple_alerts(self, db):
        db.queue_alert("bikes", "deal", json.dumps({"id": "1"}))
        db.queue_alert("bikes", "price_drop", json.dumps({"id": "2"}))
        db.queue_alert("nas_hdd", "deal", json.dumps({"id": "3"}))
        pending = db.get_pending_alerts()
        assert len(pending) == 3

    def test_get_pending_alerts_filters_by_profile(self, db):
        db.queue_alert("bikes", "deal", json.dumps({"id": "1"}))
        db.queue_alert("nas_hdd", "deal", json.dumps({"id": "2"}))
        pending = db.get_pending_alerts(profile="bikes")
        assert len(pending) == 1
        assert pending[0]["profile"] == "bikes"

    def test_get_pending_alerts_excludes_sent(self, db):
        db.queue_alert("bikes", "deal", json.dumps({"id": "1"}))
        db.queue_alert("bikes", "deal", json.dumps({"id": "2"}))
        pending = db.get_pending_alerts()
        db.mark_alerts_sent([pending[0]["id"]])
        remaining = db.get_pending_alerts()
        assert len(remaining) == 1
        assert remaining[0]["id"] == pending[1]["id"]

    def test_mark_alerts_sent_updates_sent_at(self, db):
        db.queue_alert("bikes", "deal", json.dumps({"id": "1"}))
        pending = db.get_pending_alerts()
        db.mark_alerts_sent([pending[0]["id"]])
        # After marking sent, get_pending_alerts should return empty
        assert db.get_pending_alerts() == []

    def test_mark_alerts_sent_empty_list(self, db):
        # Should not raise
        db.mark_alerts_sent([])

    def test_queue_alert_sets_created_at(self, db):
        db.queue_alert("bikes", "deal", json.dumps({"id": "1"}))
        pending = db.get_pending_alerts()
        assert pending[0]["created_at"] is not None

    def test_get_pending_alerts_ordered_by_created_at(self, db):
        db.queue_alert("bikes", "deal", json.dumps({"id": "first"}))
        db.queue_alert("bikes", "deal", json.dumps({"id": "second"}))
        pending = db.get_pending_alerts()
        assert json.loads(pending[0]["payload"])["id"] == "first"
        assert json.loads(pending[1]["payload"])["id"] == "second"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_quiet_hours.py -v`
Expected: FAIL — `queue_alert` method does not exist

- [ ] **Step 3: Add alert_queue table to SCHEMA_SQL**

In `storage/sqlite.py`, add to `SCHEMA_SQL` (after the `idx_deals_profile_score` index, before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS alert_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    sent_at DATETIME
);
```

- [ ] **Step 4: Add queue_alert method to SQLiteStorage**

Add after the `close()` method at the end of `storage/sqlite.py`:

```python
    def queue_alert(self, profile: str, alert_type: str, payload_json: str) -> None:
        """Queue an alert for later sending (used during quiet hours)."""
        now = datetime.now().isoformat()
        try:
            self._conn.execute(
                "INSERT INTO alert_queue (profile, alert_type, payload, created_at) VALUES (?, ?, ?, ?)",
                (profile, alert_type, payload_json, now),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to queue alert for {profile}: {e}")

    def get_pending_alerts(self, profile: str | None = None) -> list[dict]:
        """Get unsent alerts from the queue, ordered by creation time."""
        query = "SELECT * FROM alert_queue WHERE sent_at IS NULL"
        params: list = []
        if profile is not None:
            query += " AND profile = ?"
            params.append(profile)
        query += " ORDER BY created_at ASC"
        try:
            rows = self._conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to get pending alerts: {e}")
            return []

    def mark_alerts_sent(self, alert_ids: list[int]) -> None:
        """Mark alerts as sent by setting sent_at timestamp."""
        if not alert_ids:
            return
        now = datetime.now().isoformat()
        placeholders = ",".join("?" for _ in alert_ids)
        try:
            self._conn.execute(
                f"UPDATE alert_queue SET sent_at = ? WHERE id IN ({placeholders})",
                [now, *alert_ids],
            )
            self._conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to mark alerts as sent: {e}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_quiet_hours.py -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add storage/sqlite.py tests/test_quiet_hours.py
git commit -m "feat(quiet-hours): add alert_queue table and SQLite methods"
```

---

## Task 2: A.3 — Quiet Hours Time Logic

**Files:**
- Modify: `deal_hunter.py` — add `is_quiet_hours()` function
- Modify: `tests/test_quiet_hours.py` — add time logic tests

- [ ] **Step 1: Write failing tests for is_quiet_hours**

Append to `tests/test_quiet_hours.py`:

```python
from unittest.mock import patch
from datetime import datetime


class TestIsQuietHours:
    """Tests for is_quiet_hours() time checking logic."""

    def test_inside_quiet_hours_evening(self):
        from deal_hunter import is_quiet_hours

        profile = {"quiet_hours": {"start": "22:00", "end": "07:00"}}
        with patch("deal_hunter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 23, 30)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_quiet_hours(profile) is True

    def test_inside_quiet_hours_early_morning(self):
        from deal_hunter import is_quiet_hours

        profile = {"quiet_hours": {"start": "22:00", "end": "07:00"}}
        with patch("deal_hunter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 5, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_quiet_hours(profile) is True

    def test_outside_quiet_hours_afternoon(self):
        from deal_hunter import is_quiet_hours

        profile = {"quiet_hours": {"start": "22:00", "end": "07:00"}}
        with patch("deal_hunter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 14, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_quiet_hours(profile) is False

    def test_no_quiet_hours_config(self):
        from deal_hunter import is_quiet_hours

        profile = {}
        assert is_quiet_hours(profile) is False

    def test_quiet_hours_from_env(self):
        from deal_hunter import is_quiet_hours

        profile = {}  # no profile override
        with patch("deal_hunter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 23, 30)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch.dict("os.environ", {"QUIET_HOURS_START": "22:00", "QUIET_HOURS_END": "07:00"}):
                assert is_quiet_hours(profile) is True

    def test_profile_overrides_env(self):
        from deal_hunter import is_quiet_hours

        # Env says 22-07, profile says 23-06
        profile = {"quiet_hours": {"start": "23:00", "end": "06:00"}}
        with patch("deal_hunter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 22, 30)  # inside env, outside profile
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch.dict("os.environ", {"QUIET_HOURS_START": "22:00", "QUIET_HOURS_END": "07:00"}):
                assert is_quiet_hours(profile) is False  # profile wins

    def test_same_day_quiet_hours(self):
        """Quiet hours that don't span midnight: e.g., 13:00-15:00."""
        from deal_hunter import is_quiet_hours

        profile = {"quiet_hours": {"start": "13:00", "end": "15:00"}}
        with patch("deal_hunter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 14, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_quiet_hours(profile) is True

    def test_at_exact_start_time_is_quiet(self):
        from deal_hunter import is_quiet_hours

        profile = {"quiet_hours": {"start": "22:00", "end": "07:00"}}
        with patch("deal_hunter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 22, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_quiet_hours(profile) is True

    def test_at_exact_end_time_is_not_quiet(self):
        from deal_hunter import is_quiet_hours

        profile = {"quiet_hours": {"start": "22:00", "end": "07:00"}}
        with patch("deal_hunter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 7, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_quiet_hours(profile) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_quiet_hours.py::TestIsQuietHours -v`
Expected: FAIL — `is_quiet_hours` not found in `deal_hunter`

- [ ] **Step 3: Implement is_quiet_hours in deal_hunter.py**

Add after the `STATE_TTL_DAYS = 14` line (~line 49) in `deal_hunter.py`:

```python
def is_quiet_hours(profile: dict) -> bool:
    """Check if current time is within quiet hours.

    Priority: profile quiet_hours > env QUIET_HOURS_START/END > disabled.
    """
    qh = profile.get("quiet_hours")
    if qh:
        start_str = qh.get("start")
        end_str = qh.get("end")
    else:
        start_str = os.environ.get("QUIET_HOURS_START")
        end_str = os.environ.get("QUIET_HOURS_END")

    if not start_str or not end_str:
        return False

    try:
        start_h, start_m = map(int, start_str.split(":"))
        end_h, end_m = map(int, end_str.split(":"))
    except (ValueError, AttributeError):
        logger.warning(f"Invalid quiet hours format: {start_str}-{end_str}")
        return False

    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    if start_minutes <= end_minutes:
        # Same day range (e.g., 13:00-15:00)
        return start_minutes <= current_minutes < end_minutes
    else:
        # Overnight range (e.g., 22:00-07:00)
        return current_minutes >= start_minutes or current_minutes < end_minutes
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_quiet_hours.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add deal_hunter.py tests/test_quiet_hours.py
git commit -m "feat(quiet-hours): add is_quiet_hours() time logic"
```

---

## Task 3: A.3 — Integrate Quiet Hours into Alert Flow

**Files:**
- Modify: `deal_hunter.py:469-638` — modify `_run_normal()` to queue alerts during quiet hours and flush at start
- Modify: `tests/test_quiet_hours.py` — add integration tests

- [ ] **Step 1: Write failing integration tests**

Append to `tests/test_quiet_hours.py`:

```python
class TestQuietHoursIntegration:
    """Tests for quiet hours integration with alert flow."""

    def test_flush_pending_alerts_sends_and_marks(self, db):
        """flush_pending_alerts should send queued alerts and mark them sent."""
        db.queue_alert("bikes", "deal", json.dumps({
            "deal_id": "pepper:123",
            "title": "Test Deal",
            "price": 5000,
            "link": "https://example.com",
            "score": 85,
            "plus": ["keyword1"],
            "minus": [],
        }))
        db.queue_alert("bikes", "price_drop", json.dumps({
            "deal_id": "pepper:456",
            "title": "Drop Deal",
            "old_price": 10000,
            "new_price": 8000,
            "diff_pln": 2000,
            "diff_percent": 20.0,
            "link": "https://example.com/2",
        }))

        pending = db.get_pending_alerts()
        assert len(pending) == 2

        # Mark all as sent (simulating flush)
        db.mark_alerts_sent([p["id"] for p in pending])
        assert db.get_pending_alerts() == []

    def test_flush_respects_max_alerts(self, db):
        """Only first 5 alerts should be sent, rest stay queued."""
        for i in range(8):
            db.queue_alert("bikes", "deal", json.dumps({"id": str(i)}))

        pending = db.get_pending_alerts()
        assert len(pending) == 8

        # Flush only first 5
        to_send = pending[:5]
        db.mark_alerts_sent([p["id"] for p in to_send])
        remaining = db.get_pending_alerts()
        assert len(remaining) == 3
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_quiet_hours.py::TestQuietHoursIntegration -v`
Expected: PASS (these test SQLite methods, not the integration in _run_normal)

- [ ] **Step 3: Modify _run_normal to support quiet hours**

In `deal_hunter.py`, modify `_run_normal()` (starting at line 469). Add flush logic after db initialization and queue logic around alert sending.

Find the section at ~line 492-496 where `db` is initialized. After it, add:

```python
    # Flush queued alerts from previous quiet hours
    if db and telegram and not is_quiet_hours(profile):
        pending = db.get_pending_alerts(profile=profile_name)
        if pending:
            flush_count = min(len(pending), max_alerts)
            for alert_data in pending[:flush_count]:
                payload = json.loads(alert_data["payload"])
                if alert_data["alert_type"] == "deal":
                    logger.info(f"Flushing queued deal alert: {payload.get('title', '?')[:40]}")
                    telegram.send_text(
                        f"\U0001f514 Zakolejkowany alert:\n<b>{html.escape(payload.get('title', ''))}</b>\n"
                        f"\U0001f4b0 {payload.get('price', 0):,} PLN\nScore: {payload.get('score', 0)}\n"
                        f'\U0001f517 <a href="{html.escape(payload.get("link", ""))}">Link</a>',
                        topic_id=tg_topic,
                    )
                elif alert_data["alert_type"] == "price_drop":
                    logger.info(f"Flushing queued price drop: {payload.get('title', '?')[:40]}")
                    telegram.send_text(
                        f"\U0001f514 Zakolejkowany spadek ceny:\n<b>{html.escape(payload.get('title', ''))}</b>\n"
                        f"{payload.get('old_price', 0):,} \u2192 {payload.get('new_price', 0):,} PLN",
                        topic_id=tg_topic,
                    )
            db.mark_alerts_sent([p["id"] for p in pending[:flush_count]])
            logger.info(f"Flushed {flush_count} queued alerts for {profile_name}")
```

Then wrap the existing Telegram sending sections (~lines 549-613) with a quiet hours check. Replace the existing price drop sending block:

```python
    # Send price drop alerts first (higher priority), limited by max_alerts
    if price_drop_alerts:
        price_drop_alerts.sort(key=lambda x: x["price_change"]["diff_percent"], reverse=True)
    if telegram and price_drop_alerts:
        if is_quiet_hours(profile):
            # Queue instead of send
            if db:
                for pda in price_drop_alerts[:max_alerts]:
                    payload = json.dumps({
                        "deal_id": pda["deal"].id,
                        "title": pda["deal"].title,
                        "link": pda["deal"].link,
                        "old_price": pda["price_change"]["old_price"],
                        "new_price": pda["price_change"]["new_price"],
                        "diff_pln": pda["price_change"]["diff_pln"],
                        "diff_percent": pda["price_change"]["diff_percent"],
                    })
                    db.queue_alert(profile_name, "price_drop", payload)
                logger.info(f"Queued {min(len(price_drop_alerts), max_alerts)} price drop alerts (quiet hours)")
        else:
            for pda in price_drop_alerts[:max_alerts]:
                telegram.send_price_drop_alert(
                    pda["deal"],
                    pda["price_change"],
                    topic_id=tg_topic,
                    emoji=emoji,
                    currency=currency,
                )
            logger.info(
                f"Sent {min(len(price_drop_alerts), max_alerts)} price drop alerts for {profile_name}"
            )
```

And similarly wrap the deal alerts block:

```python
    # Telegram — top alerts individually, rest in summary
    if telegram:
        if is_quiet_hours(profile):
            # Queue instead of send
            if db:
                for a in alerts[:max_alerts]:
                    payload = json.dumps({
                        "deal_id": a["deal"].id,
                        "title": a["deal"].title,
                        "price": a["deal"].price,
                        "link": a["deal"].link,
                        "score": a["score"],
                        "plus": a["plus"][:6],
                        "minus": a["minus"][:4],
                    })
                    db.queue_alert(profile_name, "deal", payload)
                logger.info(f"Queued {min(len(alerts), max_alerts)} deal alerts (quiet hours)")
        else:
            top_alerts = alerts[:max_alerts]
            remaining = alerts[max_alerts:]

            for a in top_alerts:
                tier = (
                    "\U0001f525\U0001f525\U0001f525 GORĄCA PEREŁKA"
                    if a["score"] >= threshold_alert
                    else "\U0001f525 ZNALAZŁEM OKAZJĘ"
                )
                telegram.send_alert(
                    a["deal"],
                    a["score"],
                    tier,
                    a["plus"],
                    a["minus"],
                    topic_id=tg_topic,
                    emoji=emoji,
                    currency=currency,
                )

            if remaining:
                telegram.send_summary(remaining, topic_id=tg_topic, emoji=emoji, currency=currency)
```

You will also need to add `import html` at the top of `deal_hunter.py` if it's not already there.

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS (no regressions)

- [ ] **Step 5: Commit**

```bash
git add deal_hunter.py tests/test_quiet_hours.py
git commit -m "feat(quiet-hours): integrate alert queuing into run flow"
```

---

## Task 4: A.3 — Validation + .env.example

**Files:**
- Modify: `utils/validation.py:81-102` — add quiet_hours validation
- Modify: `.env.example` — add quiet hours vars
- Modify: `tests/test_quiet_hours.py` — add validation tests

- [ ] **Step 1: Write failing validation tests**

Append to `tests/test_quiet_hours.py`:

```python
from utils.validation import validate_profile


class TestQuietHoursValidation:
    """Tests for quiet_hours config validation."""

    VALID_PROFILE = {
        "name": "test",
        "sources": {"pepper": {}},
        "budget": {"min": 100, "max": 10000},
        "score_threshold": 50,
        "telegram": {"topic_id": 1},
    }

    def test_valid_quiet_hours(self):
        profile = {**self.VALID_PROFILE, "quiet_hours": {"start": "22:00", "end": "07:00"}}
        errors = validate_profile(profile)
        assert not errors

    def test_invalid_quiet_hours_not_dict(self):
        profile = {**self.VALID_PROFILE, "quiet_hours": "22:00-07:00"}
        errors = validate_profile(profile)
        assert any("quiet_hours" in e and "dict" in e for e in errors)

    def test_invalid_quiet_hours_missing_start(self):
        profile = {**self.VALID_PROFILE, "quiet_hours": {"end": "07:00"}}
        errors = validate_profile(profile)
        assert any("start" in e for e in errors)

    def test_invalid_quiet_hours_missing_end(self):
        profile = {**self.VALID_PROFILE, "quiet_hours": {"start": "22:00"}}
        errors = validate_profile(profile)
        assert any("end" in e for e in errors)

    def test_invalid_quiet_hours_bad_format(self):
        profile = {**self.VALID_PROFILE, "quiet_hours": {"start": "10pm", "end": "7am"}}
        errors = validate_profile(profile)
        assert any("HH:MM" in e for e in errors)

    def test_no_quiet_hours_is_valid(self):
        errors = validate_profile(self.VALID_PROFILE)
        assert not errors
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_quiet_hours.py::TestQuietHoursValidation -v`
Expected: FAIL — validation doesn't check quiet_hours yet

- [ ] **Step 3: Add quiet_hours validation to utils/validation.py**

Add before the `return errors` line at the end of `validate_profile()` (after the price_tracking validation block):

```python
    # quiet_hours validation
    if "quiet_hours" in profile:
        qh = profile["quiet_hours"]
        if not isinstance(qh, dict):
            errors.append("'quiet_hours' must be a dict")
        else:
            if "start" not in qh:
                errors.append("'quiet_hours' must have 'start' key")
            if "end" not in qh:
                errors.append("'quiet_hours' must have 'end' key")
            for key in ("start", "end"):
                val = qh.get(key)
                if val is not None:
                    import re as _re

                    if not isinstance(val, str) or not _re.match(r"^\d{2}:\d{2}$", val):
                        errors.append(f"'quiet_hours.{key}' must be in HH:MM format")
```

- [ ] **Step 4: Update .env.example**

Append to `.env.example`:

```
# Quiet Hours — suppress Telegram alerts during these hours (optional)
# QUIET_HOURS_START=22:00
# QUIET_HOURS_END=07:00
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_quiet_hours.py -v`
Expected: All tests PASS

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add utils/validation.py .env.example tests/test_quiet_hours.py
git commit -m "feat(quiet-hours): add validation and .env.example"
```

---

## Task 5: B.2 — RSS Source Class

**Files:**
- Create: `sources/rss.py`
- Create: `tests/fixtures/allegro_rss.xml`
- Create: `tests/fixtures/rss_atom.xml`
- Create: `tests/test_rss_source.py`

- [ ] **Step 1: Create RSS XML fixtures**

Create `tests/fixtures/allegro_rss.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Allegro - rower endurance</title>
    <link>https://allegro.pl</link>
    <description>Wyniki wyszukiwania</description>
    <item>
      <title>Rower szosowy Canyon Endurace CF 7 2025 rozmiar XL</title>
      <link>https://allegro.pl/oferta/rower-szosowy-canyon-endurace-cf-7-123456</link>
      <description>Rower szosowy Canyon Endurace CF 7, rama karbonowa, Shimano 105, rozmiar XL. Cena: 10 499 zł</description>
      <pubDate>Sun, 06 Apr 2026 12:00:00 +0200</pubDate>
      <guid>https://allegro.pl/oferta/rower-szosowy-canyon-endurace-cf-7-123456</guid>
    </item>
    <item>
      <title>Giant Defy Advanced 2 2025 - 8 999 zł</title>
      <link>https://allegro.pl/oferta/giant-defy-advanced-2-789012</link>
      <description>Giant Defy Advanced 2, Shimano Tiagra</description>
      <pubDate>Sat, 05 Apr 2026 10:30:00 +0200</pubDate>
      <guid>https://allegro.pl/oferta/giant-defy-advanced-2-789012</guid>
    </item>
    <item>
      <title>Akcesoria rowerowe zestaw - brak ceny</title>
      <link>https://allegro.pl/oferta/akcesoria-345678</link>
      <description>Zestaw akcesoriów rowerowych</description>
      <pubDate>Fri, 04 Apr 2026 08:00:00 +0200</pubDate>
      <guid>https://allegro.pl/oferta/akcesoria-345678</guid>
    </item>
  </channel>
</rss>
```

Create `tests/fixtures/rss_atom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Deals Feed</title>
  <link href="https://example.com/deals"/>
  <entry>
    <title>Laptop Dell XPS 15 - 5 499 zł</title>
    <link href="https://example.com/deals/laptop-dell-xps"/>
    <id>https://example.com/deals/laptop-dell-xps</id>
    <published>2026-04-06T10:00:00Z</published>
    <summary>Laptop Dell XPS 15, 16GB RAM, 512GB SSD</summary>
  </entry>
  <entry>
    <title>Monitor LG 27" 4K</title>
    <link href="https://example.com/deals/monitor-lg"/>
    <id>https://example.com/deals/monitor-lg</id>
    <published>2026-04-05T14:00:00Z</published>
    <summary>Cena: 1 899 zł. Monitor LG 27UK850</summary>
  </entry>
</feed>
```

- [ ] **Step 2: Write failing tests for RssSource**

Create `tests/test_rss_source.py`:

```python
"""Tests for RSS/Atom feed source."""

from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestRssSource:
    """Tests for RssSource parsing."""

    def test_parse_rss_feed(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()
        deals = source._parse_feed(xml_content, "allegro")

        assert len(deals) == 3
        assert deals[0].title == "Rower szosowy Canyon Endurace CF 7 2025 rozmiar XL"
        assert deals[0].source == "allegro"
        assert "allegro.pl" in deals[0].link
        assert deals[0].id.startswith("allegro:")

    def test_extract_price_from_title(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()
        deals = source._parse_feed(xml_content, "allegro")

        # "Giant Defy Advanced 2 2025 - 8 999 zł" -> 8999
        giant = [d for d in deals if "Giant" in d.title][0]
        assert giant.price == 8999

    def test_extract_price_from_description(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()
        deals = source._parse_feed(xml_content, "allegro")

        # Canyon: price in description "Cena: 10 499 zł"
        canyon = [d for d in deals if "Canyon" in d.title][0]
        assert canyon.price == 10499

    def test_no_price_returns_zero(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()
        deals = source._parse_feed(xml_content, "allegro")

        # "Akcesoria rowerowe zestaw - brak ceny" -> 0
        akc = [d for d in deals if "Akcesoria" in d.title][0]
        assert akc.price == 0

    def test_parse_atom_feed(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "rss_atom.xml").read_text()
        deals = source._parse_feed(xml_content, "example")

        assert len(deals) == 2
        assert deals[0].title == "Laptop Dell XPS 15 - 5 499 zł"
        assert deals[0].source == "example"
        assert deals[0].price == 5499

    def test_atom_price_from_summary(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "rss_atom.xml").read_text()
        deals = source._parse_feed(xml_content, "example")

        monitor = [d for d in deals if "Monitor" in d.title][0]
        assert monitor.price == 1899

    def test_empty_feed(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
        deals = source._parse_feed(xml_content, "test")
        assert deals == []

    def test_malformed_xml_returns_empty(self):
        from sources.rss import RssSource

        source = RssSource()
        deals = source._parse_feed("<not>valid xml", "test")
        assert deals == []

    def test_fetch_deals_multiple_feeds(self):
        from sources.rss import RssSource

        source = RssSource()
        rss_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()
        atom_content = (FIXTURES_DIR / "rss_atom.xml").read_text()

        call_count = 0

        def mock_fetch(url):
            nonlocal call_count
            call_count += 1
            if "allegro" in url:
                return rss_content
            return atom_content

        config = {
            "feeds": [
                {"url": "https://allegro.pl/rss/test", "source_name": "allegro"},
                {"url": "https://example.com/feed.xml", "source_name": "example"},
            ]
        }

        with patch.object(source, "_fetch_page", side_effect=mock_fetch):
            with patch.object(source, "_rate_limit"):
                deals = source.fetch_deals(config)

        assert len(deals) == 5  # 3 from allegro + 2 from example
        assert call_count == 2

    def test_published_at_parsed(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()
        deals = source._parse_feed(xml_content, "allegro")

        assert deals[0].published_at != ""

    def test_deal_id_uses_guid(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()
        deals = source._parse_feed(xml_content, "allegro")

        # ID should be derived from guid
        assert "123456" in deals[0].id

    def test_default_source_name(self):
        """When no source_name in feed config, default to 'rss'."""
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()

        config = {"feeds": [{"url": "https://example.com/feed.xml"}]}

        with patch.object(source, "_fetch_page", return_value=xml_content):
            with patch.object(source, "_rate_limit"):
                deals = source.fetch_deals(config)

        assert all(d.source == "rss" for d in deals)

    def test_fetch_page_returns_none_skips_feed(self):
        from sources.rss import RssSource

        source = RssSource()
        config = {"feeds": [{"url": "https://example.com/broken"}]}

        with patch.object(source, "_fetch_page", return_value=None):
            with patch.object(source, "_rate_limit"):
                deals = source.fetch_deals(config)

        assert deals == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_rss_source.py -v`
Expected: FAIL — `sources.rss` module does not exist

- [ ] **Step 4: Implement RssSource**

Create `sources/rss.py`:

```python
"""RSS/Atom feed source for deal monitoring."""

import hashlib
import logging
import xml.etree.ElementTree as ET

from .base import Deal, Source

logger = logging.getLogger(__name__)

ATOM_NS = "http://www.w3.org/2005/Atom"


class RssSource(Source):
    """Generic RSS/Atom feed source. Parses standard feeds into Deal objects."""

    def fetch_deals(self, config: dict) -> list[Deal]:
        """Fetch deals from one or more RSS/Atom feeds."""
        deals: list[Deal] = []
        for feed_cfg in config.get("feeds", []):
            self._rate_limit()
            url = feed_cfg["url"]
            source_name = feed_cfg.get("source_name", "rss")
            content = self._fetch_page(url)
            if content is None:
                logger.warning(f"Failed to fetch RSS feed: {url}")
                continue
            deals.extend(self._parse_feed(content, source_name))
        return deals

    def _parse_feed(self, xml_content: str, source_name: str) -> list[Deal]:
        """Parse RSS 2.0 or Atom feed XML into Deal objects."""
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.warning(f"Failed to parse RSS/Atom XML: {e}")
            return []

        # Detect feed type
        if root.tag == "rss":
            return self._parse_rss2(root, source_name)
        elif root.tag == f"{{{ATOM_NS}}}feed" or root.tag == "feed":
            return self._parse_atom(root, source_name)
        else:
            logger.warning(f"Unknown feed format: root tag is '{root.tag}'")
            return []

    def _parse_rss2(self, root: ET.Element, source_name: str) -> list[Deal]:
        """Parse RSS 2.0 format."""
        deals: list[Deal] = []
        channel = root.find("channel")
        if channel is None:
            return deals

        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            guid = (item.findtext("guid") or link).strip()

            if not title:
                continue

            # Extract price from title first, then description
            price = self.extract_price(title)
            if price == 0 and description:
                price = self.extract_price(description)

            # Generate stable ID from guid
            id_hash = hashlib.md5(guid.encode()).hexdigest()[:12]
            deal_id = f"{source_name}:{id_hash}"

            deals.append(Deal(
                id=deal_id,
                title=title,
                price=price,
                link=link,
                source=source_name,
                description=description,
                temperature=0,
                image_url="",
                published_at=pub_date,
            ))

        return deals

    def _parse_atom(self, root: ET.Element, source_name: str) -> list[Deal]:
        """Parse Atom format."""
        deals: list[Deal] = []

        # Handle namespaced and non-namespaced Atom
        ns = f"{{{ATOM_NS}}}" if root.tag.startswith("{") else ""

        for entry in root.findall(f"{ns}entry"):
            title = (entry.findtext(f"{ns}title") or "").strip()

            link_el = entry.find(f"{ns}link")
            link = (link_el.get("href") or "") if link_el is not None else ""

            summary = (entry.findtext(f"{ns}summary") or "").strip()
            published = (entry.findtext(f"{ns}published") or "").strip()
            entry_id = (entry.findtext(f"{ns}id") or link).strip()

            if not title:
                continue

            # Extract price from title first, then summary
            price = self.extract_price(title)
            if price == 0 and summary:
                price = self.extract_price(summary)

            id_hash = hashlib.md5(entry_id.encode()).hexdigest()[:12]
            deal_id = f"{source_name}:{id_hash}"

            deals.append(Deal(
                id=deal_id,
                title=title,
                price=price,
                link=link,
                source=source_name,
                description=summary,
                temperature=0,
                image_url="",
                published_at=published,
            ))

        return deals
```

- [ ] **Step 5: Register RssSource in sources/__init__.py**

In `sources/__init__.py`, add the import and registration:

After `from .web import WebSource` add:
```python
from .rss import RssSource
```

Add to `__all__`:
```python
"RssSource",
```

Add to `SOURCE_REGISTRY`:
```python
"rss": RssSource,
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_rss_source.py -v`
Expected: All 13 tests PASS

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add sources/rss.py sources/__init__.py tests/test_rss_source.py tests/fixtures/allegro_rss.xml tests/fixtures/rss_atom.xml
git commit -m "feat: add RSS/Atom feed source for Allegro and generic RSS"
```

---

## Task 6: B.1 — x-kom Store Definition

**Files:**
- Create: `stores/xkom.yaml`
- Create: `tests/fixtures/xkom_search.html`
- Create: `tests/test_xkom_morele.py`

- [ ] **Step 1: Inspect x-kom.pl search page to identify CSS selectors**

Run: `curl -sL -H "User-Agent: Mozilla/5.0" "https://www.x-kom.pl/szukaj?q=monitor" -o /tmp/xkom_sample.html && head -200 /tmp/xkom_sample.html`

Examine the HTML structure to find:
- Product container selector
- Title selector
- Price selector
- Link selector
- Image selector

Note: x-kom may use JavaScript rendering. If the curl response has no product data, the store cannot be scraped with simple CSS selectors and should be skipped.

- [ ] **Step 2: Create x-kom store YAML definition**

Create `stores/xkom.yaml` based on the identified selectors (exact selectors depend on Step 1 inspection):

```yaml
name: xkom
type: search
base_url: "https://www.x-kom.pl"
search_url: "https://www.x-kom.pl/szukaj?q={query}"

strategies:
  - css

selectors:
  products: "<identified container>"
  title: "<identified title selector>"
  price: "<identified price selector>"
  link: "a@href"
  image: "img@src"
```

- [ ] **Step 3: Create HTML fixture from inspected page**

Save a representative snippet of the x-kom search results HTML to `tests/fixtures/xkom_search.html`. Include 2-3 product entries with realistic structure.

- [ ] **Step 4: Write tests**

Create `tests/test_xkom_morele.py`:

```python
"""Tests for x-kom and Morele YAML store definitions."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestXkomStore:
    """Tests for x-kom YAML store parsing."""

    def test_xkom_store_registered(self):
        from sources import SOURCE_REGISTRY

        assert "xkom" in SOURCE_REGISTRY

    def test_xkom_store_parses_fixture(self):
        from sources import SOURCE_REGISTRY
        from unittest.mock import patch

        source_cls = SOURCE_REGISTRY["xkom"]
        source = source_cls()

        html = (FIXTURES_DIR / "xkom_search.html").read_text()

        with patch.object(source, "_fetch_page", return_value=html):
            with patch.object(source, "_rate_limit"):
                deals = source.fetch_deals({"query": "monitor"})

        assert len(deals) >= 1
        for deal in deals:
            assert deal.title
            assert deal.source == "xkom"
            assert deal.link
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_xkom_morele.py::TestXkomStore -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add stores/xkom.yaml tests/fixtures/xkom_search.html tests/test_xkom_morele.py
git commit -m "feat: add x-kom.pl YAML store definition"
```

---

## Task 7: B.1 — Morele Store Definition

**Files:**
- Create: `stores/morele.yaml`
- Create: `tests/fixtures/morele_search.html`
- Modify: `tests/test_xkom_morele.py`

- [ ] **Step 1: Inspect morele.net search page**

Run: `curl -sL -H "User-Agent: Mozilla/5.0" "https://www.morele.net/wyszukiwarka/?q=monitor" -o /tmp/morele_sample.html && head -200 /tmp/morele_sample.html`

Identify CSS selectors for product container, title, price, link, image.

- [ ] **Step 2: Create morele store YAML definition**

Create `stores/morele.yaml`:

```yaml
name: morele
type: search
base_url: "https://www.morele.net"
search_url: "https://www.morele.net/wyszukiwarka/?q={query}"

strategies:
  - css

selectors:
  products: "<identified container>"
  title: "<identified title selector>"
  price: "<identified price selector>"
  link: "a@href"
  image: "img@src"
```

- [ ] **Step 3: Create HTML fixture**

Save a snippet of morele.net search results to `tests/fixtures/morele_search.html`.

- [ ] **Step 4: Add tests for morele**

Append to `tests/test_xkom_morele.py`:

```python
class TestMoreleStore:
    """Tests for Morele YAML store parsing."""

    def test_morele_store_registered(self):
        from sources import SOURCE_REGISTRY

        assert "morele" in SOURCE_REGISTRY

    def test_morele_store_parses_fixture(self):
        from sources import SOURCE_REGISTRY
        from unittest.mock import patch

        source_cls = SOURCE_REGISTRY["morele"]
        source = source_cls()

        html = (FIXTURES_DIR / "morele_search.html").read_text()

        with patch.object(source, "_fetch_page", return_value=html):
            with patch.object(source, "_rate_limit"):
                deals = source.fetch_deals({"query": "monitor"})

        assert len(deals) >= 1
        for deal in deals:
            assert deal.title
            assert deal.source == "morele"
            assert deal.link
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_xkom_morele.py -v`
Expected: All tests PASS

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add stores/morele.yaml tests/fixtures/morele_search.html tests/test_xkom_morele.py
git commit -m "feat: add morele.net YAML store definition"
```

---

## Task 8: Final Integration + CLAUDE.md Update

**Files:**
- Modify: `CLAUDE.md` — update Known Limitations and Architecture sections

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS, new test count ~460+

- [ ] **Step 2: Run ruff lint and format**

Run: `ruff check . && ruff format --check .`
Expected: No errors

- [ ] **Step 3: Update CLAUDE.md**

Update the Known Limitations section — remove x-kom and Morele from "to be added" list. Add RSS to the source types. Add quiet hours to the Price Tracking section. Update Architecture section to include `sources/rss.py`.

- [ ] **Step 4: Update docs/ROADMAP-v2.md status**

Mark A.3, B.1, B.2 as done in the summary table.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/ROADMAP-v2.md
git commit -m "docs: update CLAUDE.md and roadmap for Wave 1 completion"
```

- [ ] **Step 6: Push**

```bash
git push origin main
```

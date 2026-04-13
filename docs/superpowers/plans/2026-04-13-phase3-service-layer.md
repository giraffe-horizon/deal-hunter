# Phase 3: Service Layer Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract business logic from the 1,224-line `deal_hunter.py` into focused service modules, absorb `health.py`, and slim the orchestrator to a thin CLI entrypoint (~150 lines).

**Architecture:** Six service classes + shared typed dataclasses replace tangled functions. `deal_hunter.py` becomes CLI-only: parse args, wire services, delegate. `health.py` (228 lines) is absorbed into `services/health_tracker.py`. Verbose `--verify` output moves to `cli/verify.py`. Dashboard switches to shared `ProfileManager`.

**Tech Stack:** Python 3.12+, SQLAlchemy 2.0, existing repository layer from Phase 2.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `services/__init__.py` | Create | Package init, re-exports |
| `services/types.py` | Create | Shared typed dataclasses (~60 lines) |
| `services/profile_manager.py` | Create | Profile loading, listing, validation, path safety (~80 lines) |
| `services/fetcher.py` | Create | Deal fetching & deduplication (~120 lines) |
| `services/scorer.py` | Create | Scoring orchestration & category detection (~60 lines) |
| `services/price_tracker.py` | Create | Price change detection (~80 lines) |
| `services/alerter.py` | Create | Notification dispatch, quiet hours, digest (~150 lines) |
| `services/health_tracker.py` | Create | Health state, watchdog, source failure alerts (~130 lines) |
| `cli/__init__.py` | Create | Package init |
| `cli/verify.py` | Create | `--verify` verbose output (~160 lines) |
| `deal_hunter.py` | Modify | Slim to ~150 lines CLI entrypoint |
| `dashboard/dependencies.py` | Modify | Use ProfileManager instead of local functions |
| `dashboard/routes/profiles.py` | Modify | Import from ProfileManager |
| `tests/test_services.py` | Create | Tests for all service classes |
| `tests/test_cli_verify.py` | Create | Tests for CLI verify output |
| `health.py` | Delete | Absorbed into services/health_tracker.py |

---

### Task 1: Shared Types + Services Package

**Files:**
- Create: `services/__init__.py`
- Create: `services/types.py`
- Test: `tests/test_services.py`

- [ ] **Step 1: Create `services/types.py` with shared dataclasses**

```python
# services/types.py
"""Shared typed dataclasses for service layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from filters.base import ScoreResult
    from sources.base import Deal


@dataclass
class PriceTrackingConfig:
    enabled: bool = True
    min_drop_percent: int = 10
    min_drop_amount: int = 200
    track_increases: bool = False


@dataclass
class PriceChange:
    deal_id: str
    type: Literal["drop", "increase"]
    old_price: int
    new_price: int
    diff_pln: int
    diff_percent: float
    is_lowest_ever: bool


@dataclass
class ScoredDeal:
    deal: Deal
    result: ScoreResult
    category: str


@dataclass
class FetchResult:
    deals: list[Deal]
    source_results: dict[str, bool]
    errors: list[str]
```

- [ ] **Step 2: Create `services/__init__.py`**

```python
# services/__init__.py
"""Business logic services for Deal Hunter."""
```

- [ ] **Step 3: Write tests for types**

```python
# tests/test_services.py
"""Tests for service layer."""

from services.types import FetchResult, PriceChange, PriceTrackingConfig, ScoredDeal


def test_price_tracking_config_defaults():
    config = PriceTrackingConfig()
    assert config.enabled is True
    assert config.min_drop_percent == 10
    assert config.min_drop_amount == 200
    assert config.track_increases is False


def test_price_change_dataclass():
    pc = PriceChange(
        deal_id="pepper:1",
        type="drop",
        old_price=5000,
        new_price=4000,
        diff_pln=1000,
        diff_percent=20.0,
        is_lowest_ever=True,
    )
    assert pc.diff_pln == 1000
    assert pc.type == "drop"
```

- [ ] **Step 4: Run tests**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_services.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/ tests/test_services.py
git commit -m "feat(services): add shared typed dataclasses for service layer"
```

---

### Task 2: ProfileManager

**Files:**
- Create: `services/profile_manager.py`
- Test: `tests/test_services.py` (append)

Extract from `deal_hunter.py` lines 224-250 (`load_profile`, `list_profiles`) and `dashboard/dependencies.py` lines 18-54 (`safe_profile_path`, `safe_load_profile`, `get_profiles`). Consolidate into one class that serves both CLI and dashboard needs.

- [ ] **Step 1: Write tests for ProfileManager**

```python
# Append to tests/test_services.py
import pytest
from pathlib import Path

class TestProfileManager:
    @pytest.fixture
    def profiles_dir(self, tmp_path):
        d = tmp_path / "profiles"
        d.mkdir()
        (d / "bikes.yaml").write_text("name: bikes\nemoji: '🚲'\nscore_threshold: 50\n")
        (d / "nas.yaml").write_text("name: nas\nemoji: '💾'\nenabled: false\n")
        return d

    @pytest.fixture
    def mgr(self, profiles_dir):
        from services.profile_manager import ProfileManager
        return ProfileManager(profiles_dir)

    def test_list_all(self, mgr):
        names = mgr.list_all()
        assert "bikes" in names
        assert "nas" in names

    def test_list_enabled_only(self, mgr):
        names = mgr.list_all(include_disabled=False)
        assert "bikes" in names
        assert "nas" not in names

    def test_load(self, mgr):
        data = mgr.load("bikes")
        assert data["name"] == "bikes"

    def test_load_missing_returns_none(self, mgr):
        assert mgr.load("nonexistent") is None

    def test_safe_path_valid(self, mgr):
        path = mgr.safe_path("bikes")
        assert path is not None
        assert path.name == "bikes.yaml"

    def test_safe_path_traversal_rejected(self, mgr):
        assert mgr.safe_path("../etc/passwd") is None
        assert mgr.safe_path("") is None
        assert mgr.safe_path("a" * 100) is None
```

- [ ] **Step 2: Implement ProfileManager**

```python
# services/profile_manager.py
"""Profile loading, listing, validation, and path safety."""

import re
from pathlib import Path

import yaml

_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


class ProfileManager:
    """Unified profile management for CLI and dashboard."""

    def __init__(self, profiles_dir: Path) -> None:
        self.profiles_dir = profiles_dir

    def list_all(self, include_disabled: bool = True) -> list[str]:
        """List available profile names."""
        if not self.profiles_dir.exists():
            return []
        names: list[str] = []
        for p in sorted(self.profiles_dir.glob("*.yaml")):
            if not include_disabled:
                data = self._read_yaml(p)
                if data and not data.get("enabled", True):
                    continue
            names.append(p.stem)
        return names

    def load(self, name: str) -> dict | None:
        """Load a profile by name. Returns None if not found or invalid."""
        path = self.safe_path(name)
        if path is None or not path.exists():
            return None
        return self._read_yaml(path)

    def safe_path(self, name: str) -> Path | None:
        """Validate name and return resolved path, or None if invalid."""
        if not _PROFILE_NAME_RE.match(name):
            return None
        path = (self.profiles_dir / f"{name}.yaml").resolve()
        if not path.is_relative_to(self.profiles_dir.resolve()):
            return None
        return path

    def validate(self, profile: dict) -> list[str]:
        """Validate a profile dict. Returns list of error messages."""
        from utils.validation import validate_profile
        return validate_profile(profile)

    def _read_yaml(self, path: Path) -> dict | None:
        """Read a YAML file safely."""
        try:
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return dict(data) if data else None
        except (yaml.YAMLError, OSError):
            return None
```

- [ ] **Step 3: Run tests**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_services.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add services/profile_manager.py tests/test_services.py
git commit -m "feat(services): add ProfileManager — unified profile loading for CLI + dashboard"
```

---

### Task 3: DealFetcher

**Files:**
- Create: `services/fetcher.py`
- Test: `tests/test_services.py` (append)

Extract from `deal_hunter.py` lines 143-148 (`_normalize_title`), 277-306 (`fetch_all_deals`), 309-370 (`deduplicate`).

- [ ] **Step 1: Write tests**

```python
# Append to tests/test_services.py
from sources.base import Deal

def _make_deal(**overrides):
    defaults = dict(
        id="test:1", title="Test Deal", price=1000, link="http://example.com",
        source="test", description="desc", temperature=0, image_url="", published_at="",
    )
    defaults.update(overrides)
    return Deal(**defaults)

class TestDealFetcher:
    def test_deduplicate_by_id(self):
        from services.fetcher import DealFetcher
        fetcher = DealFetcher({})
        deals = [_make_deal(id="a"), _make_deal(id="a"), _make_deal(id="b")]
        result = fetcher.deduplicate(deals)
        assert len(result) == 2

    def test_deduplicate_fuzzy_merge(self):
        from services.fetcher import DealFetcher
        fetcher = DealFetcher({})
        deals = [
            _make_deal(id="a:1", title="Giant Defy Advanced 2 2024", price=5000, source="pepper"),
            _make_deal(id="b:1", title="Giant Defy Advanced 2 2024", price=5100, source="ceneo"),
        ]
        result = fetcher.deduplicate(deals)
        assert len(result) == 1
        assert len(result[0].alt_links) == 1

    def test_normalize_title(self):
        from services.fetcher import DealFetcher
        assert DealFetcher._normalize_title("  Hello, World!  ") == "hello world"
```

- [ ] **Step 2: Implement DealFetcher**

```python
# services/fetcher.py
"""Deal fetching and deduplication."""

import logging
import re
from difflib import SequenceMatcher
from typing import Any

from sources.base import Deal

logger = logging.getLogger(__name__)


class DealFetcher:
    """Fetches deals from configured sources and deduplicates."""

    def __init__(self, source_registry: dict[str, Any]) -> None:
        self.source_registry = source_registry

    def fetch_all(self, profile: dict) -> tuple[list[Deal], dict[str, bool], list[str]]:
        """Fetch deals from all configured sources.

        Returns (deals, source_results, errors).
        """
        sources_config = profile.get("sources", {})
        all_deals: list[Deal] = []
        source_results: dict[str, bool] = {}
        errors: list[str] = []

        for source_name, source_config in sources_config.items():
            source_class = self.source_registry.get(source_name)
            if not source_class:
                logger.warning(f"Unknown source: {source_name}")
                continue

            try:
                source = source_class()
                deals = source.fetch_deals(source_config)
                all_deals.extend(deals)
                source_results[source_name] = True
                logger.info(f"Source {source_name}: {len(deals)} deals fetched")
            except Exception as e:
                logger.error(f"Source {source_name} failed: {e}", exc_info=True)
                source_results[source_name] = False
                errors.append(f"{source_name}: {e}")

        return all_deals, source_results, errors

    def deduplicate(self, deals: list[Deal], dedup_config: dict | None = None) -> list[Deal]:
        """Deduplicate by ID, then merge cross-source duplicates by fuzzy title + price."""
        config = dedup_config or {}
        enabled = config.get("enabled", True)
        price_tolerance = config.get("price_tolerance", 0.05)
        title_similarity = config.get("title_similarity", 0.85)

        seen_ids: set[str] = set()
        unique: list[Deal] = []
        seen_keys: list[tuple[str, int, int]] = []

        for d in deals:
            if d.id in seen_ids:
                continue
            seen_ids.add(d.id)

            norm_title = self._normalize_title(d.title)[:60]

            if not enabled:
                unique.append(d)
                continue

            merged = False
            for _i, (existing_title, existing_price, unique_idx) in enumerate(seen_keys):
                if d.price > 0 and (norm_title, d.price) == (existing_title, existing_price):
                    unique[unique_idx].alt_links.append(
                        {"source": d.source, "link": d.link, "price": d.price}
                    )
                    merged = True
                    break

                if d.price > 0 and existing_price > 0:
                    price_diff = abs(d.price - existing_price) / max(d.price, existing_price)
                    if price_diff <= price_tolerance:
                        ratio = SequenceMatcher(None, existing_title, norm_title).ratio()
                        if ratio >= title_similarity:
                            unique[unique_idx].alt_links.append(
                                {"source": d.source, "link": d.link, "price": d.price}
                            )
                            merged = True
                            break

            if not merged:
                seen_keys.append((norm_title, d.price, len(unique)))
                unique.append(d)

        return unique

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalize title for dedup: lowercase, strip, alphanumeric only."""
        text = title.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
```

- [ ] **Step 3: Run tests, commit**

---

### Task 4: ScoringService

**Files:**
- Create: `services/scorer.py`
- Test: `tests/test_services.py` (append)

Extract from `deal_hunter.py` lines 253-271 (`get_filter`, `_detect_category`).

- [ ] **Step 1: Write tests and implement ScoringService**

```python
# services/scorer.py
"""Scoring orchestration and category detection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from filters.base import BaseFilter

if TYPE_CHECKING:
    from sources.base import Deal

from services.types import ScoredDeal


class ScoringService:
    """Orchestrates deal scoring using filter registry."""

    def __init__(self, filter_registry: dict[str, Any]) -> None:
        self.filter_registry = filter_registry

    def get_filter(self, profile: dict) -> BaseFilter:
        """Get the appropriate filter for a profile."""
        custom_filter = profile.get("custom_filter")
        if custom_filter and custom_filter in self.filter_registry:
            return self.filter_registry[custom_filter](profile)
        return BaseFilter(profile)

    def score_deals(self, deals: list[Deal], profile: dict, profile_name: str = "") -> tuple[list[ScoredDeal], list[ScoredDeal]]:
        """Score all deals. Returns (scored, rejected) lists."""
        deal_filter = self.get_filter(profile)
        scored: list[ScoredDeal] = []
        rejected: list[ScoredDeal] = []

        for deal in deals:
            result = deal_filter.score_deal(deal)
            category = self.detect_category(deal, profile, profile_name)
            sd = ScoredDeal(deal=deal, result=result, category=category)
            if result.rejected:
                rejected.append(sd)
            else:
                scored.append(sd)

        scored.sort(key=lambda x: x.result.score, reverse=True)
        return scored, rejected

    @staticmethod
    def detect_category(deal: Deal, profile: dict, profile_name: str = "") -> str:
        """Detect product category from deal title+description."""
        categories = profile.get("categories", {})
        if not categories:
            return profile_name if profile_name else ""

        text = (deal.title + " " + deal.description).lower()
        for category, keywords in categories.items():
            if any(kw.lower() in text for kw in keywords):
                return str(category)
        return profile_name if profile_name else ""
```

Tests should verify `get_filter` returns BaseFilter by default, `detect_category` matches keywords, and `score_deals` separates scored from rejected.

- [ ] **Step 2: Run tests, commit**

```bash
git commit -m "feat(services): add ScoringService — scoring orchestration + category detection"
```

---

### Task 5: PriceTracker

**Files:**
- Create: `services/price_tracker.py`
- Test: `tests/test_services.py` (append)

Extract from `deal_hunter.py` lines 151-218 (`get_price_tracking_config`, `check_price_changes`). Return typed `PriceChange` instead of raw dict.

- [ ] **Step 1: Write tests and implement PriceTracker**

```python
# services/price_tracker.py
"""Price change detection service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from services.types import PriceChange, PriceTrackingConfig

if TYPE_CHECKING:
    from sources.base import Deal
    from storage.repositories import PriceRepository

logger = logging.getLogger(__name__)


class PriceTracker:
    """Detects significant price changes using SQLite price history."""

    def __init__(self, price_repo: PriceRepository) -> None:
        self.price_repo = price_repo

    @staticmethod
    def get_config(profile: dict) -> PriceTrackingConfig:
        """Extract price tracking config from profile with defaults."""
        pt = profile.get("price_tracking", {})
        return PriceTrackingConfig(
            enabled=pt.get("enabled", True),
            min_drop_percent=pt.get("min_drop_percent", 10),
            min_drop_amount=pt.get("min_drop_amount", 200),
            track_increases=pt.get("track_increases", False),
        )

    def check_price_change(self, deal: Deal, profile: dict | None = None) -> PriceChange | None:
        """Check if price changed significantly. Returns PriceChange or None."""
        if deal.price <= 0:
            return None

        config = self.get_config(profile) if profile else PriceTrackingConfig()
        if not config.enabled:
            return None

        prev_price = self.price_repo.get_previous_price(deal.id)
        if prev_price is None or deal.price == prev_price:
            return None

        if deal.price < prev_price:
            drop_abs = prev_price - deal.price
            drop_pct = (drop_abs / prev_price) * 100 if prev_price > 0 else 0

            if drop_pct >= config.min_drop_percent or drop_abs >= config.min_drop_amount:
                lowest = self.price_repo.get_lowest(deal.id)
                is_lowest = lowest is not None and deal.price <= lowest
                return PriceChange(
                    deal_id=deal.id,
                    type="drop",
                    old_price=prev_price,
                    new_price=deal.price,
                    diff_pln=drop_abs,
                    diff_percent=round(drop_pct, 1),
                    is_lowest_ever=is_lowest,
                )
        elif config.track_increases:
            increase_abs = deal.price - prev_price
            increase_pct = (increase_abs / prev_price) * 100 if prev_price > 0 else 0
            return PriceChange(
                deal_id=deal.id,
                type="increase",
                old_price=prev_price,
                new_price=deal.price,
                diff_pln=increase_abs,
                diff_percent=round(increase_pct, 1),
                is_lowest_ever=False,
            )
        return None
```

Tests should cover: no change returns None, small drop below thresholds returns None, significant drop returns PriceChange, increase only reported when configured.

- [ ] **Step 2: Run tests, commit**

```bash
git commit -m "feat(services): add PriceTracker — price change detection with typed results"
```

---

### Task 6: AlertService

**Files:**
- Create: `services/alerter.py`
- Test: `tests/test_services.py` (append)

Extract from `deal_hunter.py`:
- `is_quiet_hours()` (lines 58-90)
- Alert dispatch logic from `_run_normal()` (lines 461-691)
- `run_digest()` (lines 931-982)
- `_send_source_failure_alert()` (lines 1084-1102)

This is the largest service. It owns all Telegram interaction.

- [ ] **Step 1: Implement AlertService**

```python
# services/alerter.py
"""Notification dispatch, quiet hours, and alert queuing."""

from __future__ import annotations

import html
import json
import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from notifiers.telegram import TelegramNotifier
    from storage.repositories import AlertQueueRepository

from services.types import PriceChange

logger = logging.getLogger(__name__)


def is_quiet_hours(profile: dict) -> bool:
    """Check if current time is within quiet hours."""
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
        return start_minutes <= current_minutes < end_minutes
    return current_minutes >= start_minutes or current_minutes < end_minutes


class AlertService:
    """Sends deal alerts, price drops, and digests via Telegram."""

    def __init__(
        self,
        telegram: TelegramNotifier | None,
        alert_repo: AlertQueueRepository,
    ) -> None:
        self.telegram = telegram
        self.alert_repo = alert_repo

    def flush_queued(self, profile_name: str, profile: dict, topic_id: int | None, max_alerts: int) -> int:
        """Flush queued alerts from previous quiet hours. Returns count flushed."""
        if not self.telegram or is_quiet_hours(profile):
            return 0

        pending = self.alert_repo.get_pending(profile=profile_name)
        if not pending:
            return 0

        flush_count = min(len(pending), max_alerts)
        for alert_data in pending[:flush_count]:
            payload = json.loads(alert_data["payload"])
            if alert_data["alert_type"] == "deal":
                self.telegram.send_text(
                    f"\U0001f514 Zakolejkowany alert:\n"
                    f"<b>{html.escape(payload.get('title', ''))}</b>\n"
                    f"\U0001f4b0 {payload.get('price', 0):,} PLN\n"
                    f"Score: {payload.get('score', 0)}\n"
                    f'\U0001f517 <a href="{html.escape(payload.get("link", ""))}">Link</a>',
                    topic_id=topic_id,
                )
            elif alert_data["alert_type"] == "price_drop":
                self.telegram.send_text(
                    f"\U0001f514 Zakolejkowany spadek ceny:\n"
                    f"<b>{html.escape(payload.get('title', ''))}</b>\n"
                    f"{payload.get('old_price', 0):,}"
                    f" \u2192 {payload.get('new_price', 0):,} PLN",
                    topic_id=topic_id,
                )
        self.alert_repo.mark_sent([p["id"] for p in pending[:flush_count]])
        logger.info(f"Flushed {flush_count} queued alerts for {profile_name}")
        return flush_count

    def send_price_drop_alerts(
        self,
        drops: list[dict],
        profile: dict,
        profile_name: str,
        topic_id: int | None,
        max_alerts: int,
    ) -> int:
        """Send or queue price drop alerts. Returns count sent/queued."""
        if not drops or not self.telegram:
            return 0

        emoji = profile.get("emoji", "\U0001f50d")
        currency = profile.get("currency", "PLN")

        drops.sort(key=lambda x: x["price_change"]["diff_percent"], reverse=True)
        count = min(len(drops), max_alerts)

        if is_quiet_hours(profile):
            for pda in drops[:count]:
                payload = json.dumps({
                    "deal_id": pda["deal"].id, "title": pda["deal"].title,
                    "link": pda["deal"].link,
                    "old_price": pda["price_change"]["old_price"],
                    "new_price": pda["price_change"]["new_price"],
                    "diff_pln": pda["price_change"]["diff_pln"],
                    "diff_percent": pda["price_change"]["diff_percent"],
                })
                self.alert_repo.queue(profile_name, "price_drop", payload)
            logger.info(f"Queued {count} price drop alerts (quiet hours)")
        else:
            for pda in drops[:count]:
                self.telegram.send_price_drop_alert(
                    pda["deal"], pda["price_change"],
                    topic_id=topic_id, emoji=emoji, currency=currency,
                )
            logger.info(f"Sent {count} price drop alerts for {profile_name}")
        return count

    def send_deal_alerts(
        self,
        alerts: list[dict],
        profile: dict,
        profile_name: str,
        topic_id: int | None,
        max_alerts: int,
    ) -> int:
        """Send or queue deal alerts. Returns count sent/queued."""
        if not alerts or not self.telegram:
            return 0

        emoji = profile.get("emoji", "\U0001f50d")
        currency = profile.get("currency", "PLN")
        threshold_alert = profile.get("score_threshold_alert", 100)

        alerts.sort(key=lambda x: x["score"], reverse=True)

        if is_quiet_hours(profile):
            count = min(len(alerts), max_alerts)
            for a in alerts[:count]:
                payload = json.dumps({
                    "deal_id": a["deal"].id, "title": a["deal"].title,
                    "price": a["deal"].price, "link": a["deal"].link,
                    "score": a["score"], "plus": a["plus"][:6], "minus": a["minus"][:4],
                })
                self.alert_repo.queue(profile_name, "deal", payload)
            logger.info(f"Queued {count} deal alerts (quiet hours)")
            return count

        top_alerts = alerts[:max_alerts]
        remaining = alerts[max_alerts:]

        for a in top_alerts:
            tier = (
                "\U0001f525\U0001f525\U0001f525 GORĄCA PEREŁKA"
                if a["score"] >= threshold_alert
                else "\U0001f525 ZNALAZŁEM OKAZJĘ"
            )
            self.telegram.send_alert(
                a["deal"], a["score"], tier, a["plus"], a["minus"],
                topic_id=topic_id, emoji=emoji, currency=currency,
            )

        if remaining:
            self.telegram.send_summary(
                remaining, topic_id=topic_id, emoji=emoji, currency=currency,
            )

        return len(top_alerts)

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
        self.telegram.send_text(msg, topic_id=topic_id)
```

Tests: verify `is_quiet_hours` time logic (same tests as existing `test_quiet_hours.py`), verify flush/send methods handle None telegram gracefully.

- [ ] **Step 2: Run tests, commit**

```bash
git commit -m "feat(services): add AlertService — notification dispatch with quiet hours"
```

---

### Task 7: HealthTracker

**Files:**
- Create: `services/health_tracker.py`
- Test: `tests/test_services.py` (append)

Absorb all of `health.py` (228 lines) into a class.

- [ ] **Step 1: Implement HealthTracker**

Move all functions from `health.py` into `HealthTracker` class:
- `load_health()` → `self.load()`
- `save_health()` → `self.save()`
- `compute_overall_status()` → `self._compute_status()`
- `update_sources_health()` → `self.update_sources()`
- `build_health_data()` → `self.build_data()`
- `get_failing_sources()` → `self.get_failing_sources()`
- `print_health_status()` → `self.print_status()`
- `check_watchdog()` → `self.check_watchdog()`
- `_format_timedelta()` → `self._format_timedelta()` (static)

Keep `STALE_THRESHOLD` and `CONSECUTIVE_FAILURE_ALERT_THRESHOLD` as class constants.

Tests: Same coverage as existing `tests/test_health.py` — load, save, status computation, watchdog, source tracking, format_timedelta.

- [ ] **Step 2: Run tests, commit**

```bash
git commit -m "feat(services): add HealthTracker — absorbs health.py into service class"
```

---

### Task 8: CLI Verify Module

**Files:**
- Create: `cli/__init__.py`
- Create: `cli/verify.py`
- Test: `tests/test_cli_verify.py`

Extract from `deal_hunter.py` lines 694-925: `_format_breakdown_line`, `_print_verbose_plain`, `_print_verbose_rich`, `_print_verbose`, `_run_verify`. Accept `list[ScoredDeal]` instead of raw tuples.

- [ ] **Step 1: Implement cli/verify.py**

All 5 functions move here with updated signatures to accept `ScoredDeal` instead of `tuple[Deal, ScoreResult]`.

- [ ] **Step 2: Write test for format_breakdown_line**

```python
# tests/test_cli_verify.py
from cli.verify import format_breakdown_line

def test_format_keyword():
    line = format_breakdown_line({"points": 10, "rule": "carbon", "source": "title", "type": "keyword"})
    assert "+10" in line
    assert "carbon" in line

def test_format_budget():
    line = format_breakdown_line({"points": 5, "rule": "budget", "source": "", "match": "in range", "type": "budget"})
    assert "Budget" in line
```

- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "feat(cli): extract verify mode output to cli/verify.py"
```

---

### Task 9: Slim deal_hunter.py

**Files:**
- Modify: `deal_hunter.py` — rewrite to use services

This is the critical task. `deal_hunter.py` drops from ~1,224 to ~200 lines. It becomes:
1. Imports + version
2. `_setup_logging()` (stays — CLI concern)
3. `validate_environment()` (stays — CLI concern)
4. `_parse_topic_id()` (stays — CLI concern)
5. `_create_telegram()` → helper to build TelegramNotifier from env
6. `run_profile()` → orchestrates services (fetch → score → price check → alert)
7. `_run_with_health_tracking()` → wraps run_profile with health
8. `main()` → CLI entrypoint

All business logic delegates to services. Remove: `is_quiet_hours`, `_normalize_title`, `get_price_tracking_config`, `check_price_changes`, `load_profile`, `list_profiles`, `get_filter`, `_detect_category`, `fetch_all_deals`, `deduplicate`, `_format_breakdown_line`, `_print_verbose_plain`, `_print_verbose_rich`, `_print_verbose`, `_run_verify`, `_run_normal`, `run_digest`, `run_price_chart`, `run_trend_chart`, `_send_source_failure_alert`.

- [ ] **Step 1: Rewrite deal_hunter.py using services**

- [ ] **Step 2: Run full test suite**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/ -v --tb=short --ignore=tests/e2e`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor: slim deal_hunter.py to CLI entrypoint using service layer"
```

---

### Task 10: Update Dashboard Dependencies

**Files:**
- Modify: `dashboard/dependencies.py`
- Modify: `dashboard/routes/profiles.py` (if needed)

Replace `safe_profile_path()`, `safe_load_profile()`, `get_profiles()` in `dashboard/dependencies.py` with `ProfileManager`. Keep `get_db()` as-is.

- [ ] **Step 1: Update dependencies.py**

```python
# dashboard/dependencies.py
"""Shared dependencies for dashboard routes."""

import os
from collections.abc import Iterator
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.profile_manager import ProfileManager
from storage.database import get_session

BASE_DIR = Path(__file__).parent.parent
PROFILES_DIR = Path(os.environ.get("DEAL_HUNTER_PROFILES_DIR", str(BASE_DIR / "profiles")))

_profile_mgr = ProfileManager(PROFILES_DIR)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a SQLAlchemy session with auto commit/rollback."""
    with get_session() as session:
        yield session


def safe_profile_path(name: str) -> Path:
    """Validate profile name and return resolved path, or raise 400."""
    path = _profile_mgr.safe_path(name)
    if path is None:
        raise HTTPException(status_code=400, detail="Invalid profile name")
    return path


def safe_load_profile(name: str) -> dict | None:
    """Load profile YAML via ProfileManager."""
    return _profile_mgr.load(name)


def get_profiles() -> list[str]:
    """Get available profile names via ProfileManager."""
    return _profile_mgr.list_all()
```

- [ ] **Step 2: Run dashboard tests**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/test_dashboard.py -v --tb=short`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(dashboard): switch dependencies to ProfileManager"
```

---

### Task 11: Delete health.py + Final Verification

**Files:**
- Delete: `health.py`
- Modify: `tests/test_health.py` — update imports to use services.health_tracker

- [ ] **Step 1: Update test imports**

Change `from health import ...` to `from services.health_tracker import HealthTracker` in `tests/test_health.py`. Adapt test calls to use class methods.

- [ ] **Step 2: Delete health.py**

```bash
git rm health.py
```

- [ ] **Step 3: Verify no remaining health.py imports**

```bash
grep -r "from health import\|import health" --include="*.py" . | grep -v __pycache__ | grep -v test_health
```

Expected: No matches (deal_hunter.py should import from services.health_tracker now).

- [ ] **Step 4: Run full test suite**

Run: `/home/liske/Projects/deal-hunter/venv/bin/python -m pytest tests/ -v --tb=short --ignore=tests/e2e`
Expected: All tests PASS

- [ ] **Step 5: Run ruff + mypy**

```bash
ruff check . && ruff format --check . && mypy --ignore-missing-imports deal_hunter.py sources/ filters/ notifiers/ utils/ storage/ visualization/ services/ cli/
```

- [ ] **Step 6: Commit**

```bash
git commit -m "chore: delete health.py — absorbed into services/health_tracker.py"
```

---

### Task 12: Update CLAUDE.md + Final Cleanup

**Files:**
- Modify: `CLAUDE.md`

Update architecture section to reflect new `services/` and `cli/` packages. Update references to `health.py`.

- [ ] **Step 1: Update CLAUDE.md architecture section**

- [ ] **Step 2: Run full test suite one final time**

- [ ] **Step 3: Commit**

```bash
git commit -m "docs: update CLAUDE.md for Phase 3 service layer architecture"
```

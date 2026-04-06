# Wave 2: Cross-Source Dedup + Watchlist — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement two features: A.2 Cross-Source Deduplication (merge same product from multiple sources into 1 alert) and C.1 Watchlist with Price Alerts (per-deal target price monitoring).

**Architecture:** A.2 extends the existing `deduplicate()` function in `deal_hunter.py` to merge instead of drop, adds `alt_links` field to `Deal` dataclass, and renders merged sources in Telegram alerts. C.1 adds a `watchlist` SQLite table, dashboard page, deal detail integration, Telegram watchlist alerts, and a `/target` command in the feedback bot.

**Tech Stack:** Python 3.12+, SQLite, FastAPI, Jinja2/HTMX, pytest

---

## File Structure

### A.2 Cross-Source Dedup
- Modify: `sources/base.py` — add `alt_links` field to `Deal` dataclass
- Modify: `deal_hunter.py` — rewrite `deduplicate()` to merge, accept profile config
- Modify: `notifiers/telegram.py` — render `alt_links` in `send_alert()` and `send_price_drop_alert()`
- Modify: `dashboard/templates/deal_detail.html` — show alternative source links
- Modify: `utils/validation.py` — validate `dedup` config
- Modify: `tests/test_dedup.py` — extend with cross-source merge and config tests

### C.1 Watchlist with Price Alerts
- Modify: `storage/sqlite.py` — add `watchlist` table + 5 methods
- Modify: `deal_hunter.py` — check watchlist triggers after deal upsert
- Modify: `notifiers/telegram.py` — add `send_watchlist_alert()`
- Modify: `dashboard.py` — add watchlist routes and API endpoints
- Create: `dashboard/templates/watchlist.html` — watchlist page
- Modify: `dashboard/templates/base.html` — add Watchlist to sidebar nav
- Modify: `dashboard/templates/deal_detail.html` — add target price form
- Modify: `feedback_bot.py` — add `/target` command
- Create: `tests/test_watchlist.py` — all watchlist tests

---

## Task 1: A.2 — Add `alt_links` Field to Deal Dataclass

**Files:**
- Modify: `sources/base.py:24-45`
- Test: `tests/test_deal.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_deal.py`:

```python
def test_deal_alt_links_default_empty():
    """Deal.alt_links defaults to empty list."""
    deal = Deal(
        id="test:1",
        title="Test Deal",
        price=10000,
        link="https://example.com",
        source="pepper",
        description="",
        temperature=0,
        image_url="",
        published_at="",
    )
    assert deal.alt_links == []


def test_deal_alt_links_populated():
    """Deal.alt_links can be populated with source dicts."""
    deal = Deal(
        id="test:1",
        title="Test Deal",
        price=10000,
        link="https://example.com",
        source="pepper",
        description="",
        temperature=0,
        image_url="",
        published_at="",
        alt_links=[{"source": "ceneo", "link": "https://ceneo.pl/123", "price": 10200}],
    )
    assert len(deal.alt_links) == 1
    assert deal.alt_links[0]["source"] == "ceneo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_deal.py::test_deal_alt_links_default_empty tests/test_deal.py::test_deal_alt_links_populated -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'alt_links'`

- [ ] **Step 3: Add `alt_links` field to Deal**

In `sources/base.py`, add after `regular_price: int = 0`:

```python
    alt_links: list[dict] = field(default_factory=list)  # [{"source": "...", "link": "...", "price": N}]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/test_deal.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `./venv/bin/python -m pytest tests/ --tb=short -q`
Expected: ALL PASS (alt_links defaults to [] so existing code unaffected)

- [ ] **Step 6: Commit**

```bash
git add sources/base.py tests/test_deal.py
git commit -m "feat(dedup): add alt_links field to Deal dataclass"
```

---

## Task 2: A.2 — Rewrite `deduplicate()` to Merge Cross-Source

**Files:**
- Modify: `deal_hunter.py:406-439` — rewrite `deduplicate()` function
- Test: `tests/test_dedup.py`

The current `deduplicate()` drops duplicates. The new version merges them: the winner keeps its identity, losers' `(source, link, price)` are added to winner's `alt_links`.

**Config per profile (optional):**
```yaml
dedup:
  enabled: true           # default: true
  price_tolerance: 0.05   # default: 0.05 (5%)
  title_similarity: 0.85  # default: 0.85
```

- [ ] **Step 1: Write the failing tests**

Replace and extend `tests/test_dedup.py`:

```python
"""Tests for deal deduplication and title normalization."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from deal_hunter import _normalize_title, deduplicate
from sources.base import Deal


def _make_deal(**kwargs) -> Deal:
    defaults = {
        "id": "test:1",
        "title": "Test Deal",
        "price": 10000,
        "link": "https://example.com",
        "source": "pepper",
        "description": "",
        "temperature": 0,
        "image_url": "",
        "published_at": "",
    }
    defaults.update(kwargs)
    return Deal(**defaults)


# ── Existing behavior (must still pass) ──


def test_exact_dedup():
    """Same ID is deduplicated."""
    deals = [
        _make_deal(id="pepper:123", title="Deal A"),
        _make_deal(id="pepper:123", title="Deal A"),
    ]
    result = deduplicate(deals)
    assert len(result) == 1


def test_cross_source_dedup():
    """Same title+price from different sources is deduplicated (merged)."""
    deals = [
        _make_deal(id="pepper:1", title="Giant Defy Advanced 2", price=8500, source="pepper"),
        _make_deal(id="ceneo:2", title="Giant Defy Advanced 2", price=8500, source="ceneo"),
    ]
    result = deduplicate(deals)
    assert len(result) == 1


def test_fuzzy_dedup():
    """Similar titles with same price are deduplicated."""
    deals = [
        _make_deal(
            id="pepper:1",
            title="Giant Defy Advanced 2 2024 carbon rower szosowy",
            price=8500,
        ),
        _make_deal(
            id="ceneo:2",
            title="Giant Defy Advanced 2 2024 carbon szosowy rower",
            price=8500,
        ),
    ]
    result = deduplicate(deals)
    assert len(result) == 1


def test_different_price_not_deduped():
    """Same title but very different price is NOT deduplicated."""
    deals = [
        _make_deal(id="pepper:1", title="Giant Defy Advanced 2", price=8500),
        _make_deal(id="ceneo:2", title="Giant Defy Advanced 2", price=12000),
    ]
    result = deduplicate(deals)
    assert len(result) == 2


# ── Cross-source merge tests (NEW) ──


def test_merge_populates_alt_links():
    """Merged duplicate adds source info to winner's alt_links."""
    deals = [
        _make_deal(
            id="pepper:1",
            title="Canyon Endurace CF 7",
            price=9000,
            source="pepper",
            link="https://pepper.pl/1",
        ),
        _make_deal(
            id="ceneo:2",
            title="Canyon Endurace CF 7",
            price=9000,
            source="ceneo",
            link="https://ceneo.pl/2",
        ),
    ]
    result = deduplicate(deals)
    assert len(result) == 1
    assert len(result[0].alt_links) == 1
    assert result[0].alt_links[0]["source"] == "ceneo"
    assert result[0].alt_links[0]["link"] == "https://ceneo.pl/2"
    assert result[0].alt_links[0]["price"] == 9000


def test_merge_price_tolerance():
    """Deals within 5% price tolerance are merged."""
    deals = [
        _make_deal(
            id="pepper:1",
            title="Canyon Endurace CF 7",
            price=10000,
            source="pepper",
            link="https://pepper.pl/1",
        ),
        _make_deal(
            id="ceneo:2",
            title="Canyon Endurace CF 7",
            price=10300,
            source="ceneo",
            link="https://ceneo.pl/2",
        ),
    ]
    result = deduplicate(deals)
    assert len(result) == 1
    assert len(result[0].alt_links) == 1


def test_merge_price_outside_tolerance():
    """Deals with >5% price difference are NOT merged."""
    deals = [
        _make_deal(
            id="pepper:1",
            title="Canyon Endurace CF 7",
            price=10000,
            source="pepper",
        ),
        _make_deal(
            id="ceneo:2",
            title="Canyon Endurace CF 7",
            price=11000,
            source="ceneo",
        ),
    ]
    result = deduplicate(deals)
    assert len(result) == 2


def test_merge_three_sources():
    """3 sources for same product → 1 winner with 2 alt_links."""
    deals = [
        _make_deal(id="pepper:1", title="WD Red 4TB", price=500, source="pepper", link="https://pepper.pl/1"),
        _make_deal(id="ceneo:2", title="WD Red 4TB", price=510, source="ceneo", link="https://ceneo.pl/2"),
        _make_deal(id="morele:3", title="WD Red 4TB", price=490, source="morele", link="https://morele.net/3"),
    ]
    result = deduplicate(deals)
    assert len(result) == 1
    assert len(result[0].alt_links) == 2


def test_merge_keeps_first_as_winner():
    """First deal encountered is the winner (others become alt_links)."""
    deals = [
        _make_deal(id="pepper:1", title="Product X", price=1000, source="pepper", link="https://pepper.pl/1"),
        _make_deal(id="ceneo:2", title="Product X", price=1000, source="ceneo", link="https://ceneo.pl/2"),
    ]
    result = deduplicate(deals)
    assert result[0].source == "pepper"
    assert result[0].link == "https://pepper.pl/1"


def test_merge_zero_price_not_merged():
    """Deals with price=0 are not merged on price tolerance."""
    deals = [
        _make_deal(id="pepper:1", title="Product X", price=0, source="pepper"),
        _make_deal(id="ceneo:2", title="Product X", price=0, source="ceneo"),
    ]
    result = deduplicate(deals)
    # With zero price, should not merge (can't compare meaningfully)
    assert len(result) == 2


def test_dedup_with_custom_config():
    """Custom dedup config overrides defaults."""
    deals = [
        _make_deal(id="pepper:1", title="Canyon Endurace CF 7", price=10000, source="pepper"),
        _make_deal(id="ceneo:2", title="Canyon Endurace CF 7", price=10800, source="ceneo"),
    ]
    # Default 5% tolerance: 10800 is 8% off from 10000 → NOT merged
    result = deduplicate(deals)
    assert len(result) == 2

    # With 10% tolerance: 10800 is 8% off → MERGED
    config = {"price_tolerance": 0.10, "title_similarity": 0.85}
    result = deduplicate(deals, dedup_config=config)
    assert len(result) == 1


def test_dedup_disabled():
    """When dedup.enabled=false, only ID dedup occurs."""
    deals = [
        _make_deal(id="pepper:1", title="Same Product", price=1000, source="pepper"),
        _make_deal(id="ceneo:2", title="Same Product", price=1000, source="ceneo"),
    ]
    config = {"enabled": False}
    result = deduplicate(deals, dedup_config=config)
    assert len(result) == 2


# ── _normalize_title tests ──


def test_normalize_title_lowercase():
    assert _normalize_title("Sony WH-1000XM5") == "sony wh1000xm5"


def test_normalize_title_strips_punctuation():
    assert _normalize_title("Deal! (wow) - great.") == "deal wow great"


def test_normalize_title_collapses_whitespace():
    assert _normalize_title("  lots   of   spaces  ") == "lots of spaces"


def test_normalize_title_empty():
    assert _normalize_title("") == ""


def test_normalize_title_unicode():
    assert _normalize_title("Słuchawki ANC — super!") == "słuchawki anc super"
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `./venv/bin/python -m pytest tests/test_dedup.py -v`
Expected: New merge tests FAIL (deduplicate doesn't populate alt_links or accept dedup_config)

- [ ] **Step 3: Rewrite `deduplicate()` function**

Replace the `deduplicate()` function in `deal_hunter.py` (lines 406-439):

```python
def deduplicate(deals: list, dedup_config: dict | None = None) -> list:
    """Deduplicate deals by ID, then merge cross-source duplicates by fuzzy title + price tolerance.

    When duplicates are found, the first deal is kept as the winner and later
    duplicates' source info is added to the winner's alt_links.

    Args:
        deals: List of Deal objects.
        dedup_config: Optional config dict with keys:
            enabled (bool): If False, only ID dedup. Default True.
            price_tolerance (float): Max price diff ratio for merge. Default 0.05 (5%).
            title_similarity (float): Min SequenceMatcher ratio. Default 0.85.
    """
    config = dedup_config or {}
    enabled = config.get("enabled", True)
    price_tolerance = config.get("price_tolerance", 0.05)
    title_similarity = config.get("title_similarity", 0.85)

    seen_ids: set[str] = set()
    unique: list = []
    # Each entry: (normalized_title, price, index_in_unique)
    seen_keys: list[tuple[str, int, int]] = []

    for d in deals:
        if d.id in seen_ids:
            continue
        seen_ids.add(d.id)

        norm_title = _normalize_title(d.title)[:60]

        if not enabled:
            unique.append(d)
            continue

        # Find matching existing deal to merge with
        merged = False
        for i, (existing_title, existing_price, unique_idx) in enumerate(seen_keys):
            # Exact title+price match
            if (norm_title, d.price) == (existing_title, existing_price):
                # Merge: add to winner's alt_links
                unique[unique_idx].alt_links.append(
                    {"source": d.source, "link": d.link, "price": d.price}
                )
                merged = True
                break

            # Fuzzy match: similar title + price within tolerance
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
```

- [ ] **Step 4: Update `run_profile()` to pass dedup config**

In `deal_hunter.py`, find the `deduplicate(all_deals)` call in `run_profile()` (~line 484) and change to:

```python
    dedup_config = profile.get("dedup", {})
    unique_deals = deduplicate(all_deals, dedup_config=dedup_config)
```

- [ ] **Step 5: Run tests to verify all pass**

Run: `./venv/bin/python -m pytest tests/test_dedup.py -v`
Expected: ALL PASS

Run: `./venv/bin/python -m pytest tests/ --tb=short -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add deal_hunter.py tests/test_dedup.py
git commit -m "feat(dedup): rewrite deduplicate() to merge cross-source duplicates"
```

---

## Task 3: A.2 — Render `alt_links` in Telegram Alerts

**Files:**
- Modify: `notifiers/telegram.py:37-83` (send_alert) and `notifiers/telegram.py:118-147` (send_price_drop_alert)
- Test: `tests/test_dedup.py` (add rendering tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_dedup.py`:

```python
from unittest.mock import MagicMock, patch


def test_telegram_alert_with_alt_links():
    """send_alert includes alt_links in message when present."""
    from notifiers.telegram import TelegramNotifier

    notifier = TelegramNotifier("fake-token", "fake-chat")
    deal = _make_deal(
        id="pepper:1",
        title="Canyon Endurace CF 7",
        price=9000,
        source="pepper",
        link="https://pepper.pl/1",
        alt_links=[
            {"source": "ceneo", "link": "https://ceneo.pl/2", "price": 9200},
            {"source": "morele", "link": "https://morele.net/3", "price": 8900},
        ],
    )
    with patch.object(notifier, "_send_message") as mock_send:
        notifier.send_alert(deal, 85, "ZNALAZŁEM OKAZJĘ", ["keyword1"], [])
        msg = mock_send.call_args[0][0]
        assert "Też w:" in msg
        assert "ceneo" in msg
        assert "morele" in msg


def test_telegram_alert_without_alt_links():
    """send_alert omits 'Też w:' section when alt_links is empty."""
    from notifiers.telegram import TelegramNotifier

    notifier = TelegramNotifier("fake-token", "fake-chat")
    deal = _make_deal(
        id="pepper:1",
        title="Canyon Endurace CF 7",
        price=9000,
        source="pepper",
        link="https://pepper.pl/1",
    )
    with patch.object(notifier, "_send_message") as mock_send:
        notifier.send_alert(deal, 85, "ZNALAZŁEM OKAZJĘ", ["keyword1"], [])
        msg = mock_send.call_args[0][0]
        assert "Też w:" not in msg


def test_telegram_price_drop_with_alt_links():
    """send_price_drop_alert includes alt_links when present."""
    from notifiers.telegram import TelegramNotifier

    notifier = TelegramNotifier("fake-token", "fake-chat")
    deal = _make_deal(
        id="pepper:1",
        title="Canyon Endurace CF 7",
        price=8500,
        source="pepper",
        link="https://pepper.pl/1",
        alt_links=[{"source": "ceneo", "link": "https://ceneo.pl/2", "price": 8700}],
    )
    price_change = {
        "old_price": 9000,
        "new_price": 8500,
        "diff_pln": 500,
        "diff_percent": 5.6,
    }
    with patch.object(notifier, "_send_message") as mock_send:
        notifier.send_price_drop_alert(deal, price_change)
        msg = mock_send.call_args[0][0]
        assert "Też w:" in msg
        assert "ceneo" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_dedup.py::test_telegram_alert_with_alt_links tests/test_dedup.py::test_telegram_alert_without_alt_links tests/test_dedup.py::test_telegram_price_drop_with_alt_links -v`
Expected: FAIL (alt_links not rendered yet)

- [ ] **Step 3: Add alt_links rendering to `send_alert()`**

In `notifiers/telegram.py`, in `send_alert()`, before the final link line (`safe_link = html.escape(deal.link)`), add:

```python
        # Cross-source alt_links
        if hasattr(deal, "alt_links") and deal.alt_links:
            alt_parts = []
            for alt in deal.alt_links:
                alt_source = html.escape(alt["source"])
                alt_link = html.escape(alt["link"])
                alt_price_str = f'{alt["price"]:,} {currency}'.replace(",", " ") if alt.get("price") else ""
                if alt_price_str:
                    alt_parts.append(f'<a href="{alt_link}">{alt_source}</a> ({html.escape(alt_price_str)})')
                else:
                    alt_parts.append(f'<a href="{alt_link}">{alt_source}</a>')
            msg += f"\n🔗 Też w: {' | '.join(alt_parts)}\n"
```

- [ ] **Step 4: Add alt_links rendering to `send_price_drop_alert()`**

In `notifiers/telegram.py`, in `send_price_drop_alert()`, before the final link line (`msg += f'\n🔗 <a href=...`), add:

```python
        # Cross-source alt_links
        if hasattr(deal, "alt_links") and deal.alt_links:
            alt_parts = []
            for alt in deal.alt_links:
                alt_source = html.escape(alt["source"])
                alt_link = html.escape(alt["link"])
                alt_parts.append(f'<a href="{alt_link}">{alt_source}</a>')
            msg += f"\n🔗 Też w: {' | '.join(alt_parts)}\n"
```

- [ ] **Step 5: Run tests to verify all pass**

Run: `./venv/bin/python -m pytest tests/test_dedup.py -v`
Expected: ALL PASS

Run: `./venv/bin/python -m pytest tests/ --tb=short -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add notifiers/telegram.py tests/test_dedup.py
git commit -m "feat(dedup): render alt_links in Telegram alerts"
```

---

## Task 4: A.2 — Dashboard Alt Links + Validation

**Files:**
- Modify: `dashboard/templates/deal_detail.html` — show alternative source links
- Modify: `utils/validation.py` — validate `dedup` config
- Test: `tests/test_dedup.py` (dashboard test), `tests/test_validation.py` (dedup validation)

- [ ] **Step 1: Write validation test**

Add to `tests/test_validation.py`:

```python
def test_dedup_config_valid():
    """Valid dedup config passes validation."""
    profile = _valid_profile()
    profile["dedup"] = {"enabled": True, "price_tolerance": 0.05, "title_similarity": 0.85}
    errors = validate_profile(profile)
    assert not errors


def test_dedup_config_invalid_tolerance():
    """dedup.price_tolerance must be 0-1."""
    profile = _valid_profile()
    profile["dedup"] = {"price_tolerance": 1.5}
    errors = validate_profile(profile)
    assert any("price_tolerance" in e for e in errors)


def test_dedup_config_invalid_similarity():
    """dedup.title_similarity must be 0-1."""
    profile = _valid_profile()
    profile["dedup"] = {"title_similarity": -0.1}
    errors = validate_profile(profile)
    assert any("title_similarity" in e for e in errors)
```

- [ ] **Step 2: Add dedup validation to `utils/validation.py`**

Add before `return errors` in `validate_profile()`:

```python
    # dedup config
    dedup = profile.get("dedup")
    if dedup is not None:
        if not isinstance(dedup, dict):
            errors.append("dedup must be a dict")
        else:
            pt = dedup.get("price_tolerance")
            if pt is not None and (not isinstance(pt, (int, float)) or pt < 0 or pt > 1):
                errors.append("dedup.price_tolerance must be a number between 0 and 1")
            ts = dedup.get("title_similarity")
            if ts is not None and (not isinstance(ts, (int, float)) or ts < 0 or ts > 1):
                errors.append("dedup.title_similarity must be a number between 0 and 1")
```

- [ ] **Step 3: Add alt_links section to deal_detail.html**

In `dashboard/templates/deal_detail.html`, after the "Deal Details" card (after the closing `</div>` of the metadata card around line 191), add:

```html
        {% if deal.alt_links %}
        <div class="bg-surface-container-low rounded-card p-6">
            <h2 class="font-headline text-lg font-semibold text-on-surface mb-4">Also Available At</h2>
            <div class="space-y-3">
                {% for alt in deal.alt_links %}
                <a href="{{ alt.link }}" target="_blank" rel="noopener noreferrer"
                   class="flex items-center justify-between p-3 rounded-lg bg-surface-container hover:bg-surface-container-high transition-colors">
                    <div class="flex items-center gap-2">
                        <span class="material-symbols-outlined text-[18px] text-primary">store</span>
                        <span class="text-sm font-medium text-on-surface">{{ alt.source }}</span>
                    </div>
                    {% if alt.price %}
                    <span class="text-sm font-headline font-semibold text-on-surface">{{ alt.price | format_pln }}</span>
                    {% endif %}
                </a>
                {% endfor %}
            </div>
        </div>
        {% endif %}
```

Note: The deal detail route in `dashboard.py` returns `deal` as a dict from SQLite. The `alt_links` won't be in the DB dict directly — we need to pass it through. For now, the template renders if `deal.alt_links` exists. Since deals in SQLite don't store alt_links (it's a runtime merge), this section will only appear if the dashboard is enhanced later to re-compute dedup. This is acceptable — the primary rendering is in Telegram alerts.

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_validation.py tests/test_dedup.py -v`
Expected: ALL PASS

Run: `./venv/bin/python -m pytest tests/ --tb=short -q`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/templates/deal_detail.html utils/validation.py tests/test_validation.py
git commit -m "feat(dedup): add dashboard alt_links display and dedup validation"
```

---

## Task 5: C.1 — Watchlist SQLite Schema + Methods

**Files:**
- Modify: `storage/sqlite.py` — add `watchlist` table + 5 methods
- Create: `tests/test_watchlist.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_watchlist.py`:

```python
"""Tests for watchlist with price alerts."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.sqlite import SQLiteStorage


@pytest.fixture
def db(tmp_path):
    """Create a temporary SQLiteStorage instance."""
    db_path = tmp_path / "test.db"
    storage = SQLiteStorage(db_path)
    yield storage
    storage.close()


class TestWatchlistCRUD:
    """Tests for watchlist CRUD operations."""

    def _seed_deal(self, db, deal_id="pepper:123", price=10000):
        """Insert a deal for foreign key reference."""
        db.upsert_deal(
            type("Deal", (), {
                "id": deal_id, "title": "Test Deal", "price": price,
                "link": "https://example.com", "source": "pepper",
                "description": "", "image_url": "", "published_at": "",
                "regular_price": 0,
            })(),
            profile="bikes",
            score=80,
            category="test",
        )

    def test_add_to_watchlist(self, db):
        self._seed_deal(db)
        result = db.add_to_watchlist("pepper:123", 8000)
        assert result is True

    def test_add_duplicate_watchlist(self, db):
        """Adding same deal_id twice returns False."""
        self._seed_deal(db)
        db.add_to_watchlist("pepper:123", 8000)
        result = db.add_to_watchlist("pepper:123", 7000)
        assert result is False

    def test_get_watchlist(self, db):
        self._seed_deal(db, "pepper:1", 10000)
        self._seed_deal(db, "pepper:2", 20000)
        db.add_to_watchlist("pepper:1", 8000)
        db.add_to_watchlist("pepper:2", 15000)
        items = db.get_watchlist()
        assert len(items) == 2
        assert items[0]["deal_id"] in ("pepper:1", "pepper:2")
        assert "target_price" in items[0]
        assert "title" in items[0]

    def test_remove_from_watchlist(self, db):
        self._seed_deal(db)
        db.add_to_watchlist("pepper:123", 8000)
        result = db.remove_from_watchlist("pepper:123")
        assert result is True
        assert db.get_watchlist() == []

    def test_remove_nonexistent(self, db):
        result = db.remove_from_watchlist("pepper:999")
        assert result is False

    def test_check_watchlist_trigger_price_met(self, db):
        """Price at or below target triggers alert."""
        self._seed_deal(db)
        db.add_to_watchlist("pepper:123", 8000)
        trigger = db.check_watchlist_triggers("pepper:123", 7500)
        assert trigger is not None
        assert trigger["target_price"] == 8000

    def test_check_watchlist_trigger_price_not_met(self, db):
        """Price above target does not trigger."""
        self._seed_deal(db)
        db.add_to_watchlist("pepper:123", 8000)
        trigger = db.check_watchlist_triggers("pepper:123", 9000)
        assert trigger is None

    def test_check_watchlist_trigger_already_triggered(self, db):
        """Already triggered watchlist entry does not trigger again."""
        self._seed_deal(db)
        db.add_to_watchlist("pepper:123", 8000)
        db.check_watchlist_triggers("pepper:123", 7500)
        db.mark_watchlist_triggered("pepper:123")
        trigger = db.check_watchlist_triggers("pepper:123", 7000)
        assert trigger is None

    def test_mark_watchlist_triggered(self, db):
        self._seed_deal(db)
        db.add_to_watchlist("pepper:123", 8000)
        db.mark_watchlist_triggered("pepper:123")
        items = db.get_watchlist()
        assert items[0]["triggered_at"] is not None

    def test_get_watchlist_includes_current_price(self, db):
        """Watchlist items include current deal price."""
        self._seed_deal(db, "pepper:1", 10000)
        db.add_to_watchlist("pepper:1", 8000)
        items = db.get_watchlist()
        assert items[0]["current_price"] == 10000

    def test_watchlist_not_triggered_deal(self, db):
        """Deal not in watchlist returns None for trigger check."""
        trigger = db.check_watchlist_triggers("pepper:999", 5000)
        assert trigger is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_watchlist.py -v`
Expected: FAIL (no watchlist table or methods)

- [ ] **Step 3: Add watchlist table to SCHEMA_SQL**

In `storage/sqlite.py`, add to `SCHEMA_SQL` after the `alert_queue` table:

```sql
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id TEXT NOT NULL,
    target_price INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    triggered_at DATETIME,
    UNIQUE(deal_id)
);
```

- [ ] **Step 4: Add watchlist methods to SQLiteStorage**

Add these methods to the `SQLiteStorage` class:

```python
    def add_to_watchlist(self, deal_id: str, target_price: int) -> bool:
        """Add a deal to the watchlist. Returns False if already exists."""
        try:
            self.conn.execute(
                "INSERT INTO watchlist (deal_id, target_price, created_at) VALUES (?, ?, ?)",
                (deal_id, target_price, datetime.now().isoformat()),
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def remove_from_watchlist(self, deal_id: str) -> bool:
        """Remove a deal from the watchlist. Returns True if found and removed."""
        cursor = self.conn.execute(
            "DELETE FROM watchlist WHERE deal_id = ?", (deal_id,)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_watchlist(self) -> list[dict]:
        """Get all watchlist items with deal info."""
        cursor = self.conn.execute(
            """SELECT w.deal_id, w.target_price, w.created_at, w.triggered_at,
                      d.title, d.price as current_price, d.link, d.source
               FROM watchlist w
               LEFT JOIN deals d ON w.deal_id = d.id
               ORDER BY w.created_at DESC"""
        )
        return [dict(row) for row in cursor.fetchall()]

    def check_watchlist_triggers(self, deal_id: str, current_price: int) -> dict | None:
        """Check if a deal's current price meets the watchlist target.
        Returns the watchlist entry if triggered, None otherwise."""
        cursor = self.conn.execute(
            "SELECT deal_id, target_price FROM watchlist WHERE deal_id = ? AND triggered_at IS NULL",
            (deal_id,),
        )
        row = cursor.fetchone()
        if row and current_price <= row["target_price"]:
            return dict(row)
        return None

    def mark_watchlist_triggered(self, deal_id: str) -> None:
        """Mark a watchlist entry as triggered."""
        self.conn.execute(
            "UPDATE watchlist SET triggered_at = ? WHERE deal_id = ?",
            (datetime.now().isoformat(), deal_id),
        )
        self.conn.commit()
```

- [ ] **Step 5: Run tests to verify all pass**

Run: `./venv/bin/python -m pytest tests/test_watchlist.py -v`
Expected: ALL PASS

Run: `./venv/bin/python -m pytest tests/ --tb=short -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add storage/sqlite.py tests/test_watchlist.py
git commit -m "feat(watchlist): add SQLite schema and CRUD methods"
```

---

## Task 6: C.1 — Watchlist Telegram Alert + Run Integration

**Files:**
- Modify: `notifiers/telegram.py` — add `send_watchlist_alert()`
- Modify: `deal_hunter.py` — check watchlist triggers after upsert
- Test: `tests/test_watchlist.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_watchlist.py`:

```python
from unittest.mock import MagicMock, patch


class TestWatchlistTelegram:
    """Tests for watchlist Telegram alert."""

    def test_send_watchlist_alert_format(self):
        """send_watchlist_alert sends properly formatted Polish message."""
        from notifiers.telegram import TelegramNotifier

        notifier = TelegramNotifier("fake-token", "fake-chat")
        deal = type("Deal", (), {
            "id": "pepper:123",
            "title": "Canyon Endurace CF 7",
            "price": 8499,
            "link": "https://pepper.pl/123",
            "source": "pepper",
            "regular_price": 0,
            "alt_links": [],
        })()
        with patch.object(notifier, "_send_message") as mock_send:
            notifier.send_watchlist_alert(deal, target_price=9000, current_price=8499)
            msg = mock_send.call_args[0][0]
            assert "CEL CENOWY" in msg
            assert "9" in msg  # target price
            assert "8" in msg  # current price
            assert "Canyon" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_watchlist.py::TestWatchlistTelegram -v`
Expected: FAIL (no send_watchlist_alert method)

- [ ] **Step 3: Add `send_watchlist_alert()` to TelegramNotifier**

In `notifiers/telegram.py`, add after `send_price_drop_alert()`:

```python
    def send_watchlist_alert(
        self,
        deal,
        target_price: int,
        current_price: int,
        topic_id: int | None = None,
        currency: str = "PLN",
    ) -> None:
        """Send watchlist target price alert (messages in Polish for end users)."""
        target_str = f"{target_price:,} {currency}".replace(",", " ")
        current_str = f"{current_price:,} {currency}".replace(",", " ")

        safe_title = html.escape(deal.title)
        safe_link = html.escape(deal.link)

        msg = "🎯 <b>CEL CENOWY OSIĄGNIĘTY</b>\n"
        msg += f"<b>{safe_title}</b>\n\n"
        msg += f"Twój próg: {html.escape(target_str)}\n"
        msg += f"Obecna cena: <b>{html.escape(current_str)}</b>\n"
        msg += f'\n🔗 <a href="{safe_link}">Otwórz</a>'

        keyboard = build_deal_keyboard(deal.link, deal.id)
        self._send_message(msg, topic_id=topic_id, reply_markup=keyboard)
```

- [ ] **Step 4: Add watchlist trigger check to `_run_normal()`**

In `deal_hunter.py`, in `_run_normal()`, after the `db.upsert_deal()` call (~line 590), add:

```python
                # Check watchlist triggers
                if db:
                    trigger = db.check_watchlist_triggers(deal.id, deal.price)
                    if trigger and telegram:
                        telegram.send_watchlist_alert(
                            deal,
                            target_price=trigger["target_price"],
                            current_price=deal.price,
                            topic_id=tg_topic,
                            currency=currency,
                        )
                        db.mark_watchlist_triggered(deal.id)
                        logger.info(
                            f"Watchlist triggered: {deal.title[:40]} "
                            f"(target: {trigger['target_price']}, current: {deal.price})"
                        )
```

- [ ] **Step 5: Run tests to verify all pass**

Run: `./venv/bin/python -m pytest tests/test_watchlist.py -v`
Expected: ALL PASS

Run: `./venv/bin/python -m pytest tests/ --tb=short -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add notifiers/telegram.py deal_hunter.py tests/test_watchlist.py
git commit -m "feat(watchlist): add Telegram alert and run integration"
```

---

## Task 7: C.1 — Dashboard Watchlist Page + Routes

**Files:**
- Modify: `dashboard.py` — add watchlist routes
- Create: `dashboard/templates/watchlist.html`
- Modify: `dashboard/templates/base.html` — add to sidebar
- Modify: `dashboard/templates/deal_detail.html` — add target price form
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_dashboard.py`:

```python
class TestWatchlistPage:
    """Tests for the watchlist dashboard page."""

    def test_watchlist_page_loads(self, client):
        """GET /watchlist returns 200."""
        response = client.get("/watchlist")
        assert response.status_code == 200
        assert "Watchlist" in response.text

    def test_add_to_watchlist_api(self, client, seed_deals):
        """POST /api/watchlist adds a deal."""
        response = client.post(
            "/api/watchlist",
            data={"deal_id": "pepper:1", "target_price": "8000"},
        )
        assert response.status_code in (200, 303)

    def test_remove_from_watchlist_api(self, client, seed_deals):
        """DELETE /api/watchlist/{deal_id} removes a deal."""
        # First add
        client.post(
            "/api/watchlist",
            data={"deal_id": "pepper:1", "target_price": "8000"},
        )
        response = client.delete("/api/watchlist/pepper:1")
        assert response.status_code == 200

    def test_watchlist_in_sidebar(self, client):
        """Sidebar contains Watchlist link."""
        response = client.get("/deals")
        assert "/watchlist" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_dashboard.py::TestWatchlistPage -v`
Expected: FAIL (no /watchlist route)

- [ ] **Step 3: Add Watchlist to sidebar in base.html**

In `dashboard/templates/base.html`, in the `<nav>` section (after the "Price Trends" link, before the "System Health" link), add:

```html
                <a href="/watchlist" class="flex items-center gap-3 px-4 py-3 rounded-card text-sm font-medium transition-colors {% if active_page == 'watchlist' %}bg-surface-container-high text-primary{% else %}text-on-surface-variant hover:bg-surface-container{% endif %}">
                    <span class="material-symbols-outlined text-[20px]">bookmark</span>
                    Watchlist
                </a>
```

- [ ] **Step 4: Create watchlist.html template**

Create `dashboard/templates/watchlist.html`:

```html
{% extends "base.html" %}
{% set active_page = "watchlist" %}
{% block title %}Watchlist — DealMonitor{% endblock %}
{% block page_title %}Watchlist{% endblock %}
{% block content %}

{% if items %}
<div class="bg-surface-container-low rounded-card overflow-hidden">
    <div class="overflow-x-auto">
    <table class="w-full">
        <thead>
            <tr class="text-left text-xs font-label text-on-surface-variant uppercase tracking-wider">
                <th class="pb-3 pl-6 pt-4">Deal</th>
                <th class="pb-3 pt-4">Current Price</th>
                <th class="pb-3 pt-4">Target Price</th>
                <th class="pb-3 pt-4">Status</th>
                <th class="pb-3 pr-6 pt-4">Actions</th>
            </tr>
        </thead>
        <tbody class="divide-y divide-surface-variant/30">
            {% for item in items %}
            <tr id="watchlist-row-{{ loop.index }}">
                <td class="py-3 pl-6">
                    <a href="/deals/{{ item.deal_id | urlencode }}" class="text-sm font-medium text-primary hover:underline">
                        {{ item.title or item.deal_id }}
                    </a>
                    <div class="text-xs text-on-surface-variant mt-0.5">{{ item.source or '' }}</div>
                </td>
                <td class="py-3">
                    <span class="text-sm font-headline font-semibold text-on-surface">
                        {% if item.current_price %}{{ item.current_price | format_pln }}{% else %}&mdash;{% endif %}
                    </span>
                </td>
                <td class="py-3">
                    <span class="text-sm font-headline font-semibold text-tertiary">{{ item.target_price | format_pln }}</span>
                </td>
                <td class="py-3">
                    {% if item.triggered_at %}
                        <span class="text-xs font-label px-2.5 py-1 rounded-full bg-tertiary-container/30 text-tertiary font-medium">Triggered</span>
                    {% else %}
                        <span class="text-xs font-label px-2.5 py-1 rounded-full bg-primary-container text-primary font-medium">Active</span>
                    {% endif %}
                </td>
                <td class="py-3 pr-6">
                    <button hx-delete="/api/watchlist/{{ item.deal_id | urlencode }}"
                            hx-target="#watchlist-row-{{ loop.index }}"
                            hx-swap="outerHTML"
                            class="text-xs font-label px-3 py-1.5 rounded-card bg-surface-container-high text-on-surface-variant hover:bg-error-container/20 hover:text-error transition-colors">
                        Remove
                    </button>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    </div>
</div>
{% else %}
<div class="bg-surface-container-low rounded-card p-12 text-center">
    <span class="material-symbols-outlined text-[48px] text-outline-variant mb-4 block">bookmark_border</span>
    <h2 class="font-headline text-lg font-semibold text-on-surface mb-2">No watchlist items</h2>
    <p class="text-sm text-on-surface-variant">Set target prices on deal pages to start tracking.</p>
</div>
{% endif %}

{% endblock %}
```

- [ ] **Step 5: Add target price form to deal_detail.html**

In `dashboard/templates/deal_detail.html`, in the action buttons section (after the "Skip" button, before the closing `</div>` of `action-buttons`), add:

```html
            <form hx-post="/api/watchlist"
                  hx-swap="outerHTML"
                  class="flex items-center gap-1">
                <input type="hidden" name="deal_id" value="{{ deal.id }}">
                <input type="number" name="target_price" placeholder="Target PLN"
                       class="w-28 px-3 py-2.5 bg-surface-container-high text-on-surface rounded-card text-sm border-0 focus:ring-2 focus:ring-primary"
                       min="1">
                <button type="submit"
                        class="inline-flex items-center gap-1 px-3 py-2.5 bg-tertiary text-on-tertiary rounded-card text-sm font-medium hover:opacity-90 transition-opacity">
                    <span class="material-symbols-outlined text-[18px]">bookmark_add</span>
                    Target
                </button>
            </form>
```

- [ ] **Step 6: Add routes to dashboard.py**

Add these routes to `dashboard.py`:

```python
@app.get("/watchlist", response_class=HTMLResponse)
async def watchlist_page(request: Request, db: SQLiteStorage = Depends(get_db)):
    """Watchlist page — deals with target price alerts."""
    items = db.get_watchlist()
    return templates.TemplateResponse(
        "watchlist.html",
        {"request": request, "items": items},
    )


@app.post("/api/watchlist")
async def add_to_watchlist(
    request: Request,
    db: SQLiteStorage = Depends(get_db),
):
    """Add a deal to the watchlist."""
    form = await request.form()
    deal_id = form.get("deal_id", "")
    target_price = int(form.get("target_price", 0))
    if deal_id and target_price > 0:
        db.add_to_watchlist(deal_id, target_price)
    return HTMLResponse(
        '<span class="text-sm text-tertiary font-medium">✓ Target set</span>'
    )


@app.delete("/api/watchlist/{deal_id:path}")
async def remove_from_watchlist(
    deal_id: str,
    db: SQLiteStorage = Depends(get_db),
):
    """Remove a deal from the watchlist."""
    db.remove_from_watchlist(deal_id)
    return HTMLResponse("")  # HTMX removes the row
```

- [ ] **Step 7: Run tests to verify all pass**

Run: `./venv/bin/python -m pytest tests/test_dashboard.py -v`
Expected: ALL PASS

Run: `./venv/bin/python -m pytest tests/ --tb=short -q`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add dashboard.py dashboard/templates/base.html dashboard/templates/watchlist.html dashboard/templates/deal_detail.html tests/test_dashboard.py
git commit -m "feat(watchlist): add dashboard page, routes, and sidebar nav"
```

---

## Task 8: C.1 — Feedback Bot `/target` Command

**Files:**
- Modify: `feedback_bot.py` — add `/target` command
- Test: `tests/test_feedback_bot.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_feedback_bot.py`:

```python
@pytest.mark.asyncio
async def test_cmd_target_adds_to_watchlist(tmp_path):
    """The /target command adds a deal to the watchlist."""
    db_path = tmp_path / "test.db"
    db = SQLiteStorage(db_path)

    # Seed a deal
    db.upsert_deal(
        type("Deal", (), {
            "id": "pepper:123", "title": "Test Deal", "price": 10000,
            "link": "https://example.com", "source": "pepper",
            "description": "", "image_url": "", "published_at": "",
            "regular_price": 0,
        })(),
        profile="test",
        score=80,
        category="test",
    )

    from feedback_bot import cmd_target

    update = MagicMock()
    update.effective_chat.id = 12345
    update.message.reply_html = AsyncMock()

    context = MagicMock()
    context.args = ["pepper:123", "8000"]

    with patch("feedback_bot.get_storage") as mock_storage:
        mock_storage.return_value.__enter__ = MagicMock(return_value=db)
        mock_storage.return_value.__exit__ = MagicMock(return_value=False)
        await cmd_target(update, context)

    update.message.reply_html.assert_called_once()
    msg = update.message.reply_html.call_args[0][0]
    assert "8" in msg  # target price mentioned

    items = db.get_watchlist()
    assert len(items) == 1
    assert items[0]["target_price"] == 8000
    db.close()


@pytest.mark.asyncio
async def test_cmd_target_missing_args(tmp_path):
    """The /target command with wrong args shows usage."""
    from feedback_bot import cmd_target

    update = MagicMock()
    update.effective_chat.id = 12345
    update.message.reply_html = AsyncMock()

    context = MagicMock()
    context.args = []

    await cmd_target(update, context)

    update.message.reply_html.assert_called_once()
    msg = update.message.reply_html.call_args[0][0]
    assert "target" in msg.lower() or "użycie" in msg.lower() or "/target" in msg.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_feedback_bot.py::test_cmd_target_adds_to_watchlist tests/test_feedback_bot.py::test_cmd_target_missing_args -v`
Expected: FAIL (no cmd_target function)

- [ ] **Step 3: Add `/target` command to feedback_bot.py**

Add the command handler function:

```python
async def cmd_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set a target price for a deal. Usage: /target <deal_id> <price>"""
    if len(context.args) < 2:
        await update.message.reply_html(
            "Użycie: <code>/target &lt;deal_id&gt; &lt;cena&gt;</code>\n"
            "Przykład: <code>/target pepper:12345 8000</code>"
        )
        return

    deal_id = context.args[0]
    try:
        target_price = int(context.args[1])
    except ValueError:
        await update.message.reply_html("❌ Cena musi być liczbą całkowitą (w PLN).")
        return

    if target_price <= 0:
        await update.message.reply_html("❌ Cena musi być większa od 0.")
        return

    with get_storage() as db:
        result = db.add_to_watchlist(deal_id, target_price)

    if result:
        price_str = f"{target_price:,} PLN".replace(",", " ")
        await update.message.reply_html(
            f"🎯 Ustawiono cel cenowy: <b>{html.escape(price_str)}</b>\n"
            f"Deal: <code>{html.escape(deal_id)}</code>\n"
            f"Powiadomię Cię gdy cena spadnie do tego poziomu."
        )
    else:
        await update.message.reply_html(
            f"⚠️ Deal <code>{html.escape(deal_id)}</code> jest już na liście obserwowanych."
        )
```

Register it in the `main()` function alongside other command handlers:

```python
    app.add_handler(CommandHandler("target", cmd_target))
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `./venv/bin/python -m pytest tests/test_feedback_bot.py -v`
Expected: ALL PASS

Run: `./venv/bin/python -m pytest tests/ --tb=short -q`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add feedback_bot.py tests/test_feedback_bot.py
git commit -m "feat(watchlist): add /target command to feedback bot"
```

---

## Task 9: Final Integration — Lint, Docs, Push

**Files:**
- All modified files (lint/format)
- `CLAUDE.md` — update docs
- `docs/ROADMAP-v2.md` — mark A.2, C.1 as done

- [ ] **Step 1: Run full test suite**

Run: `./venv/bin/python -m pytest tests/ --tb=short -q`
Expected: ALL PASS

- [ ] **Step 2: Lint and format**

Run: `./venv/bin/ruff check .` and `./venv/bin/ruff format --check .`
Fix any issues with `./venv/bin/ruff check . --fix` and `./venv/bin/ruff format .`

- [ ] **Step 3: Update CLAUDE.md**

- Update Known Limitations: remove "Cross-source dedup is simple (title+price)" → replace with "Cross-source dedup uses fuzzy title matching + price tolerance; configurable per profile"
- Add to Tests section: `test_watchlist.py`
- Add to Feedback Bot commands: `/target <deal_id> <price>`
- Update SQLite description: add "watchlist" to the list of tables

- [ ] **Step 4: Update ROADMAP-v2.md**

Mark A.2 and C.1 as ✅ Done in the summary table.

- [ ] **Step 5: Commit and push**

```bash
git add -A
git commit -m "chore: lint fixes + docs update for Wave 2 (A.2, C.1)"
git push
```

# Deal Hunter Roadmap v2.0 — Design Spec

**Date:** 2026-04-06
**Status:** Draft
**Baseline:** v0.6.1 (439 tests, Roadmap v1 complete)

---

## Overview

Eight features across three phases, implemented in four dependency-driven waves for maximum parallelism. Total estimated effort: ~60h.

**Phases:**
- **A** — Alert Quality (Quiet Hours, Cross-Source Dedup, Scoring Tuner)
- **B** — New Sources (x-kom/Morele stores, Allegro RSS)
- **C** — Dashboard UX (Watchlist, Comparator, Profile Management)

---

## Parallelization Plan

```
Wave 1 (no dependencies — start simultaneously):
├── A.3 Quiet Hours              (~4h)
├── B.1 x-kom / Morele stores    (~3h)
└── B.2 Allegro RSS source       (~5h)

Wave 2 (after Wave 1):
├── A.2 Cross-Source Dedup       (~6h)
└── C.1 Watchlist + Price Alerts (~6h)

Wave 3 (after Wave 2):
└── C.4 Profile Management       (~20h)

Wave 4 (after C.4):
├── A.1 Scoring Tuner            (~10h)
└── C.2 Deal Comparator          (~6h)
```

**Dependency rationale:**
- Wave 2 needs Wave 1: A.2 modifies the `Deal` dataclass; C.1 reuses migration patterns from A.3.
- Wave 3 needs stable dashboard routes from Wave 2.
- Wave 4: A.1 reuses C.4's profile save mechanism; C.2 is independent but benefits from stable dashboard.

**Release strategy:** Each feature gets its own semver release upon completion.

---

## Wave 1

### A.3 Quiet Hours

**Goal:** Queue Telegram alerts during configurable quiet hours. Flush when quiet hours end.

#### Schema

```sql
CREATE TABLE IF NOT EXISTS alert_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT NOT NULL,
    alert_type TEXT NOT NULL,    -- 'deal' | 'price_drop'
    payload TEXT NOT NULL,       -- JSON-serialized alert data
    created_at DATETIME NOT NULL,
    sent_at DATETIME
);
```

#### Configuration

Two layers with override precedence:

1. **Global** (`.env`):
   ```
   QUIET_HOURS_START=22:00
   QUIET_HOURS_END=07:00
   ```
2. **Per-profile** (`profiles/*.yaml`, optional override):
   ```yaml
   quiet_hours:
     start: "23:00"
     end: "06:00"
   ```
3. **Default:** Disabled (no quiet hours unless configured).

#### Behavior

- **During quiet hours:** Alerts serialized to JSON, inserted into `alert_queue`.
- **At run start (outside quiet hours):** Flush pending alerts — send up to 5, rest rolled into next digest.
- **`--watchdog` and `--digest`:** Bypass quiet hours entirely.

#### Files to modify

| File | Change |
|------|--------|
| `storage/sqlite.py` | Add `alert_queue` table to `SCHEMA_SQL`. Methods: `queue_alert(profile, alert_type, payload_json)`, `get_pending_alerts(profile=None) -> list[dict]`, `mark_alerts_sent(ids: list[int])` |
| `deal_hunter.py` | Add `is_quiet_hours(profile) -> bool`. Modify alert-sending flow to queue when quiet. Add flush logic at run start. |
| `.env.example` | Add `QUIET_HOURS_START`, `QUIET_HOURS_END` |
| `utils/validation.py` | Validate `quiet_hours` format (HH:MM) |

#### Tests

New file: `tests/test_quiet_hours.py`
- `is_quiet_hours()` with various times, timezone edge cases, overnight ranges (22:00-07:00)
- Queue/flush SQLite methods (insert, retrieve, mark sent)
- Integration: mock time inside quiet hours → verify queue; mock time outside → verify flush
- Validation: invalid HH:MM format rejected

---

### B.1 x-kom / Morele Stores

**Goal:** Add x-kom.pl and morele.net as YAML store definitions. No Python code changes.

#### Approach

1. Inspect live search pages with curl to identify CSS selectors.
2. Write YAML store definitions following existing `stores/ceneo.yaml` pattern.
3. Auto-discovered by `sources/yaml_source.py` — no registration needed.

#### Files to create

| File | Description |
|------|-------------|
| `stores/xkom.yaml` | type: search, CSS selectors for x-kom.pl search results |
| `stores/morele.yaml` | type: search, CSS selectors for morele.net search results |
| `tests/fixtures/xkom_search.html` | HTML fixture for parser tests |
| `tests/fixtures/morele_search.html` | HTML fixture for parser tests |

#### Store YAML structure (template)

```yaml
name: xkom
type: search
base_url: "https://www.x-kom.pl"
search_url: "https://www.x-kom.pl/szukaj?q={query}"
strategies:
  - css
selectors:
  products: "<container selector>"
  title: "<title selector>"
  price: "<price selector>"
  link: "a@href"
  image: "img@src"
```

#### Tests

Extend existing YAML source test patterns:
- Parse HTML fixtures → verify Deal objects produced with correct fields
- Auto-discovery registers both sources in `SOURCE_REGISTRY`

#### Risk

Anti-scraping (Cloudflare) may block requests. Mitigation: test with real pages first; existing `_fetch_page()` User-Agent headers may need tuning.

---

### B.2 Allegro RSS Source

**Goal:** Generic RSS/Atom feed parser. Uses stdlib `xml.etree.ElementTree` (no new dependency).

#### RssSource class

```python
# sources/rss.py
class RssSource(Source):
    """RSS/Atom feed source for deal monitoring."""

    def fetch_deals(self, config: dict) -> list[Deal]:
        deals = []
        for feed_cfg in config.get("feeds", []):
            self._rate_limit()
            content = self._fetch_page(feed_cfg["url"])
            source_name = feed_cfg.get("source_name", "rss")
            deals.extend(self._parse_rss(content, source_name))
        return deals

    def _parse_rss(self, xml_content: str, source_name: str) -> list[Deal]:
        # Parse <channel><item> elements
        # Map: <title> -> title, <link> -> link, <pubDate> -> published_at
        # Extract price from title/description using extract_price()
        # Generate id as "{source_name}:{guid or link hash}"
        ...
```

#### Profile YAML usage

```yaml
sources:
  rss:
    feeds:
      - url: "https://allegro.pl/rss/listing?string=rower+endurance&price_from=8000"
        source_name: "allegro"
      - url: "https://example.com/deals.rss"
        source_name: "example"
```

#### Files to create/modify

| File | Change |
|------|--------|
| `sources/rss.py` | New `RssSource(Source)` class |
| `sources/__init__.py` | Register `SOURCE_REGISTRY["rss"] = RssSource` |
| `tests/test_rss_source.py` | New tests with XML fixtures |
| `tests/fixtures/allegro_rss.xml` | Sample RSS 2.0 feed |
| `tests/fixtures/rss_atom.xml` | Sample Atom feed |

#### Tests

- Parse valid RSS 2.0 feed → correct Deal objects
- Parse Atom feed → correct Deal objects
- Empty feed → empty list
- Missing price in title → price=0
- Malformed XML → graceful error (log warning, return empty)
- Multiple feeds in config → deals from all feeds combined

---

## Wave 2

### A.2 Cross-Source Dedup

**Goal:** Same product from multiple sources = 1 merged alert with all source links instead of separate alerts.

#### Deal dataclass change

```python
# sources/base.py - add to Deal dataclass
alt_links: list[dict] = field(default_factory=list)  # [{"source": "rowertour", "link": "https://...", "price": 10299}, ...]
```

Backward-compatible: default empty list, existing code unaffected. Using dicts (not tuples) for clean JSON serialization and future extensibility.

#### Dedup logic

Extend existing `deduplicate()` in `deal_hunter.py`:

- **Current:** `SequenceMatcher` ratio > 0.7 + exact price match → drop duplicate
- **New:** ratio threshold (default 0.85) + price within tolerance (default ±5%) → merge
  - Winner: highest score; if tied, lowest price
  - Losers' `(source, link)` pairs added to winner's `alt_links`
- **Per-profile config** (optional, backward-compatible):
  ```yaml
  dedup:
    enabled: true              # default: true
    price_tolerance: 0.05      # default: 0.05 (5%)
    title_similarity: 0.85     # default: 0.85
  ```

#### Telegram rendering

When `alt_links` is non-empty, append to alert message:

```
Też w: Rowertour (10 299 zł) | Sprint (10 499 zł)
```

#### Dashboard

Deal detail page: show "Also available at:" section with links to alternative sources.

#### Files to modify

| File | Change |
|------|--------|
| `sources/base.py` | Add `alt_links` field to `Deal` |
| `deal_hunter.py` | Rewrite `deduplicate()` to merge instead of drop |
| `notifiers/telegram.py` | Render `alt_links` in `send_alert()` and `send_price_drop_alert()` |
| `dashboard/templates/deal_detail.html` | Show alternative source links |
| `tests/test_dedup.py` | Extend with cross-source merge cases |

#### Tests

- Same product from 2 sources, 3% price diff → merged, alt_links populated
- Same product, 10% price diff → NOT merged (exceeds tolerance)
- 3 sources for same product → 1 winner with 2 alt_links
- Different products with similar titles but different prices → NOT merged
- Telegram message formatting with 0, 1, 3 alt_links
- Config: custom tolerance and similarity thresholds

---

### C.1 Watchlist with Price Alerts

**Goal:** Per-deal target price. Telegram alert when price drops to target.

#### Schema

```sql
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id TEXT NOT NULL REFERENCES deals(id),
    target_price INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    triggered_at DATETIME,
    UNIQUE(deal_id)
);
```

#### Dashboard routes

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/watchlist` | Watchlist page |
| POST | `/api/watchlist` | Add deal to watchlist (form: deal_id, target_price) |
| DELETE | `/api/watchlist/{deal_id}` | Remove from watchlist |

#### Dashboard UI

- **Sidebar:** New "Watchlist" item between "Price Trends" and "System Health"
- **`/watchlist` page:** Table with columns: Deal title (link to detail), Current price, Target price, Status (Active/Triggered), Added date, Remove button
- **Deal detail page:** "Set target price" input field + "Watch" button (HTMX POST)

#### Run integration

In `deal_hunter.py` `_run_normal()`, after `db.upsert_deal()`:
```python
trigger = db.check_watchlist_triggers(deal.id, deal.price)
if trigger:
    notifier.send_watchlist_alert(deal, trigger["target_price"], deal.price, topic_id)
    db.mark_watchlist_triggered(deal.id)
```

#### Telegram alert (Polish)

```
🎯 CEL CENOWY OSIĄGNIĘTY
Canyon Endurace CF 7
Twój próg: 9 000 zł | Obecna cena: 8 499 zł
[🔗 Otwórz]
```

#### Feedback bot

Add `/target <deal_id> <price>` command to `feedback_bot.py`.

#### Files to create/modify

| File | Change |
|------|--------|
| `storage/sqlite.py` | Add `watchlist` table + methods: `add_to_watchlist()`, `remove_from_watchlist()`, `get_watchlist()`, `check_watchlist_triggers()`, `mark_watchlist_triggered()` |
| `deal_hunter.py` | Check watchlist triggers after deal upsert |
| `notifiers/telegram.py` | Add `send_watchlist_alert()` |
| `dashboard.py` | Routes: GET /watchlist, POST/DELETE /api/watchlist |
| `dashboard/templates/watchlist.html` | New watchlist page template |
| `dashboard/templates/base.html` | Add Watchlist to sidebar nav |
| `dashboard/templates/deal_detail.html` | Add target price form |
| `feedback_bot.py` | Add `/target` command |

#### Tests

- SQLite CRUD: add, remove, get, check triggers
- Trigger logic: price at target → triggers; price above target → no trigger; already triggered → no re-trigger
- Dashboard: watchlist page renders, add/remove via API
- Telegram message formatting

---

## Wave 3

### C.4 Profile Management

**Goal:** Full CRUD for profiles via the dashboard. Zero SSH needed.

#### Sub-tasks

**1. Profile list + read (4h)**

Routes:
- `GET /profiles` — list all profiles with metadata
- `GET /profiles/{name}` — read-only profile detail view

Template `profiles.html`: card grid showing each profile with name, emoji, source count, budget range, last run status (from health.json), deal count.

Template `profile_detail.html`: rendered profile sections (Basic, Sources, Scoring, Telegram) + link to edit.

**2. Profile edit — form mode (6h)**

Route: `GET /profiles/{name}/edit` — tabbed form
Route: `PUT /api/profiles/{name}` — save profile

Tabs:
- **Basic:** name, emoji, budget min/max, currency
- **Sources:** checklist of available stores (from `SOURCE_REGISTRY`) + per-source config
- **Scoring:** editable table of score_rules (keyword → points), penalties, excluded_words, required_any
- **Thresholds:** score_threshold, score_threshold_alert
- **Telegram:** topic_id, max_alerts, quiet_hours

HTMX for dynamic add/remove of rules within the scoring tab.
Server-side validation via `validate_profile()` before save. Errors shown inline.

**3. Profile edit — raw YAML mode (3h)**

Route: `GET /profiles/{name}/edit/yaml` — CodeMirror editor (CDN)
Route: `PUT /api/profiles/{name}/yaml` — parse, validate, save raw YAML

CodeMirror loaded via CDN (`https://cdn.jsdelivr.net/npm/codemirror@5/...`). YAML mode for syntax highlighting. Validation errors displayed below editor.

**4. Profile create wizard (4h)**

Route: `GET /profiles/new` — 4-step HTMX wizard
Route: `POST /api/profiles` — create new profile

Steps:
1. Basic (name, emoji, budget) → validate name uniqueness
2. Sources (select stores, configure URLs)
3. Scoring (keyword rules, penalties, thresholds)
4. Review + optional "Import YAML" alternative

**5. Delete + manual trigger with SSE (3h)**

Routes:
- `DELETE /api/profiles/{name}` — delete profile YAML + clear state
- `POST /api/profiles/{name}/run` — start subprocess, return run ID
- `GET /api/profiles/{name}/run/stream` — SSE `StreamingResponse` with log lines

Delete: confirmation modal, refuses if run is in progress.
Manual trigger: `subprocess.Popen(["python", "deal_hunter.py", "--profile", name, "--verify"])`, capture stdout/stderr, stream via SSE.

#### Sidebar

Add "Profiles" nav item after "Watchlist".

#### API summary

```
GET    /profiles                    # list page
GET    /profiles/{name}             # detail page
GET    /profiles/{name}/edit        # form editor
GET    /profiles/{name}/edit/yaml   # YAML editor
GET    /profiles/new                # create wizard
GET    /api/profiles                # JSON list
POST   /api/profiles                # create
PUT    /api/profiles/{name}         # update (form)
PUT    /api/profiles/{name}/yaml    # update (raw YAML)
DELETE /api/profiles/{name}         # delete
POST   /api/profiles/{name}/run     # trigger run
GET    /api/profiles/{name}/run/stream  # SSE log stream
```

#### Files to create/modify

| File | Change |
|------|--------|
| `dashboard.py` | ~15 new routes. After this feature, consider splitting into `dashboard/routes/` package |
| `dashboard/templates/profiles.html` | Profile list page |
| `dashboard/templates/profile_detail.html` | Read-only profile view |
| `dashboard/templates/profile_edit.html` | Form editor (tabbed) |
| `dashboard/templates/profile_yaml.html` | Raw YAML editor with CodeMirror |
| `dashboard/templates/profile_create.html` | 4-step create wizard |
| `dashboard/templates/base.html` | Add Profiles to sidebar |

#### Risk

Highest-risk feature:
- **File system writes from web process:** Use proper error handling, validate before write, atomic rename pattern.
- **Raw YAML editing:** Malformed YAML must not crash. Parse + validate before save.
- **SSE complexity:** Use `asyncio.Queue` with FastAPI's async support. Timeout after 5 minutes.
- **Delete is destructive:** Require confirmation, refuse during active runs.

---

## Wave 4

### A.1 Scoring Tuner

**Goal:** Live rule editor with in-memory scoring simulation against existing SQLite deals.

#### Routes

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/tuner/{profile}` | Tuner page |
| POST | `/api/tuner/{profile}/simulate` | Run simulation, return JSON |
| POST | `/api/tuner/{profile}/save` | Save rules to profile YAML |

#### UI layout

HTMX-driven single page:
- **Left panel:** Editable rules
  - Score rules table: keyword input + points input + remove button + "Add rule" button
  - Penalties table: same pattern
  - Budget: min/max number inputs
  - Thresholds: score_threshold, score_threshold_alert
- **"Simulate" button** → POST modified rules as JSON
- **Right panel:** Results table
  - Columns: Deal title, Current score, Simulated score, Delta (green positive / red negative)
  - Sorted by absolute delta descending (biggest changes first)

#### Simulation backend

1. Load profile YAML from disk.
2. Override `score_rules`, `penalties`, `budget` with submitted JSON values.
3. Instantiate the profile's filter class (BaseFilter or custom e.g. BikeFilter) with modified profile dict.
4. Fetch recent deals: `db.get_recent_deals_for_simulation(profile, limit=50)`.
5. For each deal, convert dict back to `Deal` object, call `filter.score_deal(deal)`.
6. Return JSON array: `[{deal_id, title, old_score, new_score, delta, breakdown}]`.

#### Save

Reuses C.4's profile write mechanism (`PUT /api/profiles/{name}`). Updates only the scoring-related fields, preserving other profile config.

#### Files to create/modify

| File | Change |
|------|--------|
| `dashboard.py` | 3 new routes (tuner page, simulate, save) |
| `dashboard/templates/tuner.html` | Tuner page with HTMX forms + results table |
| `storage/sqlite.py` | `get_recent_deals_for_simulation(profile, limit=50)` |
| `dashboard/templates/base.html` | Add Tuner link (per-profile, accessible from profile detail) |

#### Tests

- Simulation returns correct scores with modified rules
- Modified rules with new keyword → deals that match get higher score
- Empty rules → all deals score 0
- Save persists changes, profile remains valid
- Custom filters (BikeFilter) work in simulation

---

### C.2 Deal Comparator

**Goal:** Multi-select deals and compare side-by-side.

#### Deals page changes

- Add checkbox column to deals table (both `deals.html` and `partials/deals_table.html`)
- JavaScript: track selected deal IDs in a Set
- Floating comparison bar (fixed bottom): "Compare (N)" button, visible when 2+ selected
- Click → navigate to `/compare?ids=id1,id2,id3`
- Max 5 deals in comparison

#### Compare page

Route: `GET /compare` — accepts `ids` query parameter (comma-separated)

Layout: responsive grid of cards (2-5 columns on desktop, stacked on mobile)

Each card contains:
- Deal title (link to detail page)
- Price (highlighted green if lowest among compared)
- Score (highlighted gold if highest among compared)
- Source + profile
- First seen / Last seen dates
- Mini Chart.js sparkline (price history, last 30 days)
- "Open link" button

#### Files to create/modify

| File | Change |
|------|--------|
| `dashboard.py` | `GET /compare` route |
| `dashboard/templates/compare.html` | New comparison template |
| `dashboard/templates/deals.html` | Add checkbox column + JS selection logic |
| `dashboard/templates/partials/deals_table.html` | Add checkbox column |
| `storage/sqlite.py` | `get_deals_by_ids(ids: list[str]) -> list[dict]` |

#### Tests

- Compare 2 deals → correct rendering with highlights
- Compare 5 deals → all shown
- Compare with non-existent ID → graceful handling (skip missing)
- Compare 1 deal → redirect to deal detail
- Price history sparklines render for each deal

---

## Cross-Cutting Concerns

### SQLite migrations

Use `CREATE TABLE IF NOT EXISTS` for all new tables (alert_queue, watchlist). No ALTER TABLE needed. If future features require column changes, add `PRAGMA user_version` based migration system at that point.

### Dashboard growth

After C.4, `dashboard.py` will contain ~40+ routes. Consider splitting into:
```
dashboard/
  __init__.py          # FastAPI app, middleware, template config
  routes/
    deals.py           # /deals, /deals/{id}
    profiles.py        # /profiles, /profiles/{name}/*
    tuner.py           # /tuner/{profile}
    watchlist.py       # /watchlist
    compare.py         # /compare
    health.py          # /health
    price_trends.py    # /price-trends
    api.py             # /api/* endpoints
  templates/           # (stays where it is)
```

This refactoring should happen as part of C.4 when the growth becomes real.

### Backward compatibility

All profile YAML additions are optional with sensible defaults:
- `quiet_hours` — default: disabled
- `dedup` — default: `{enabled: true, price_tolerance: 0.05, title_similarity: 0.85}`

Existing profiles work without changes.

### Testing targets

Each feature adds proportional tests. Target per feature:
- S features: 10-15 tests
- M features: 15-25 tests
- L features: 25-35 tests
- XL features: 35-50 tests

**Post-roadmap target:** 550+ tests (439 current + ~120 new).

---

## Verification Strategy

1. **Per-feature:** `python -m pytest tests/ -v` — all tests pass
2. **CI:** ruff lint + mypy + pytest on 3.12/3.13
3. **Dashboard:** Smoke test on desktop (1280px) + mobile (375px) — no overflow
4. **Notifications:** For A.3, A.2, C.1 — test alerts in staging Telegram group
5. **Schema:** Verify existing `deals.db` upgrades cleanly with new tables
6. **Integration:** `python deal_hunter.py --all --verify` — no regressions
7. **Stores (B.1):** Test against live sites with `--verify`
8. **RSS (B.2):** Test with real Allegro RSS feed URL

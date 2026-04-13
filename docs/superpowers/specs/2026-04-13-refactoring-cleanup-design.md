# Deal Hunter — Comprehensive Refactoring & Cleanup Design

**Date:** 2026-04-13
**Status:** Approved
**Approach:** Bottom-Up (Data Layer First)

## Context

Deal Hunter is a ~6,200-line Python application (plus ~3,278 lines of Jinja2 templates) that has grown organically. The codebase works well but has accumulated structural debt: a 1,356-line orchestrator mixing many concerns, dual state persistence (JSON + SQLite), N+1 query hotspots, significant template duplication, and incomplete type coverage.

This design covers a comprehensive refactoring across all layers — data, services, routes, templates, and tooling — executed bottom-up so each layer builds on a tested foundation.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database layer | Full SQLAlchemy ORM | Proper models, relationships, sessions, transactions |
| State persistence | Consolidate into SQLite | Single source of truth, eliminate JSON state files |
| Frontend build | Keep CDN-only, no build step | Personal tool, simplicity over optimization |
| `deal_hunter.py` | Full decomposition into services | 1,356 lines → ~150-line CLI entrypoint |
| Refactoring order | Bottom-up (data → services → routes → templates → types) | Each layer builds on tested foundation |

---

## Phase 1: Tooling, Formatting & Environment

**Goal:** Establish consistent code formatting and linting as the baseline before structural changes.

### 1a. Ruff Configuration Tightening

Update `pyproject.toml`:
- Remove `E501` from ignore list (enforce `line-length = 100`)
- Add rule sets: `"RET"` (return statements), `"SIM"` (simplification), `"PTH"` (pathlib)
- Add `"ANN"` (type annotations) — initially relaxed on routes via `per-file-ignores`
- Run `ruff check --fix` + `ruff format` across entire codebase

### 1b. Mypy Strictness Bump

- Enable `disallow_untyped_defs = true` for core modules (`storage/`, `filters/`, `sources/`, `health.py`)
- Keep routes relaxed initially (typed in Phase 6)

### 1c. Pre-commit Hook

New `.pre-commit-config.yaml`:
- Ruff lint + format on commit
- Mypy check on push
- Prevents formatting drift during multi-phase refactor

### 1d. Dependency Version Pinning

Update `pyproject.toml`:
- Pin minimum versions: FastAPI (`>=0.109`), Uvicorn (`>=0.25`), Jinja2 (`>=3.1`), python-multipart (`>=0.0.6`)
- Add `sqlalchemy>=2.0` (needed for Phase 2)
- Add `alembic>=1.13` for schema migrations

### 1e. Environment Variable Cleanup

- Move `DEALS_PER_PAGE` and `SCORE_THRESHOLD` from hardcoded constants to env vars with defaults
- Add `DATABASE_URL` env var (default: `sqlite:///state/deals.db`) for SQLAlchemy

### Scope

~15 files touched (formatting-only changes except `pyproject.toml` and new pre-commit config).

---

## Phase 2: SQLAlchemy ORM Migration & State Consolidation

**Goal:** Replace the raw SQL layer with SQLAlchemy ORM models, eliminate JSON state files, fix N+1 queries and transaction safety.

### 2a. ORM Models (`storage/models.py`, ~100 lines)

Five models mapping to existing tables, plus one new table:

```python
class Deal(Base):
    __tablename__ = "deals"
    id: Mapped[str]                  # PK: "source:native_id"
    title: Mapped[str]
    price: Mapped[int]
    link: Mapped[str]
    source: Mapped[str]
    description: Mapped[str]
    image_url: Mapped[str]
    profile: Mapped[str]
    score: Mapped[int]
    category: Mapped[str | None]
    status: Mapped[str]             # "active" / "watching" / "rejected" / "archived"
    first_seen: Mapped[datetime]
    last_seen: Mapped[datetime]

    prices: Mapped[list["PriceHistory"]] = relationship(back_populates="deal")
    feedback: Mapped[list["Feedback"]] = relationship(back_populates="deal")
    watchlist_entry: Mapped["WatchlistItem | None"] = relationship(back_populates="deal")

class PriceHistory(Base):
    __tablename__ = "price_history"
    deal_id: Mapped[str]            # FK -> deals.id
    price: Mapped[int]
    recorded_at: Mapped[datetime]   # composite PK with deal_id

class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int]                 # auto PK
    deal_id: Mapped[str]            # FK -> deals.id
    action: Mapped[str]
    created_at: Mapped[datetime]

class AlertQueue(Base):
    __tablename__ = "alert_queue"
    id: Mapped[int]
    deal_id: Mapped[str]
    profile: Mapped[str]
    message: Mapped[str]
    topic_id: Mapped[str | None]
    queued_at: Mapped[datetime]
    sent_at: Mapped[datetime | None]

class WatchlistItem(Base):
    __tablename__ = "watchlist"
    id: Mapped[int]
    deal_id: Mapped[str]            # FK -> deals.id, UNIQUE
    target_price: Mapped[int]
    added_at: Mapped[datetime]
    triggered_at: Mapped[datetime | None]

class SeenDeal(Base):
    """Replaces JSON state files for seen-deal tracking."""
    __tablename__ = "seen_deals"
    id: Mapped[int]
    deal_id: Mapped[str]
    profile: Mapped[str]
    dedup_key: Mapped[str]          # normalized title+price for cross-source dedup
    first_seen_at: Mapped[datetime]
    # TTL handled by query filter (WHERE first_seen_at > now - 14 days)
```

### 2b. Session & Engine Management (`storage/database.py`, ~30 lines)

```python
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

@contextmanager
def get_session() -> Iterator[Session]:
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

Replaces `check_same_thread=False` with proper SQLAlchemy connection pooling. Dashboard's `get_db()` dependency yields a session with automatic commit/rollback. Batch operations use a single transaction.

### 2c. Repository Layer (`storage/repositories.py`, ~300 lines)

Domain-organized query wrappers:

```python
class DealRepository:
    def __init__(self, session: Session): ...
    def upsert(self, deal: DealCreate) -> Deal: ...
    def get_by_id(self, deal_id: str) -> Deal | None: ...
    def get_filtered(self, *, profile, source, min_score, ...) -> list[Deal]: ...
    def get_stats(self, score_threshold: int) -> DealStats: ...
    def update_status(self, deal_id: str, status: str) -> bool: ...

class PriceRepository:
    def __init__(self, session: Session): ...
    def record(self, deal_id: str, price: int) -> None: ...
    def get_history(self, deal_id: str) -> list[PriceHistory]: ...
    def get_lowest(self, deal_id: str) -> int | None: ...
    def get_drops(self, days: int) -> list[PriceDrop]: ...
    def count_drops(self, days: int) -> int: ...
    def get_histories_batch(self, deal_ids: list[str]) -> dict[str, list]: ...

class WatchlistRepository:
    def __init__(self, session: Session): ...
    def add(self, deal_id: str, target_price: int) -> WatchlistItem: ...
    def remove(self, deal_id: str) -> bool: ...
    def get_all(self) -> list[WatchlistItem]: ...
    def check_triggers(self, deal_id: str, current_price: int) -> bool: ...
    def mark_triggered(self, deal_id: str) -> None: ...

class AlertQueueRepository:
    def __init__(self, session: Session): ...
    def queue(self, deal_id: str, profile: str, message: str, topic_id: str | None) -> None: ...
    def get_pending(self, profile: str | None) -> list[AlertQueue]: ...
    def mark_sent(self, alert_ids: list[int]) -> None: ...

class FeedbackRepository:
    def __init__(self, session: Session): ...
    def record(self, deal_id: str, action: str) -> None: ...
    def get_stats(self) -> dict[str, int]: ...

class SeenDealRepository:
    def mark_seen(self, deal_id, profile, dedup_key): ...
    def is_seen(self, deal_id, profile) -> bool: ...
    def cleanup_expired(self, ttl_days=14): ...
```

### 2d. N+1 Query Fixes

**`get_price_drops()`** — currently 2N+1 queries, becomes 1 using window functions:

```sql
WITH ranked AS (
    SELECT ph.deal_id, ph.price, ph.recorded_at,
           LAG(ph.price) OVER (PARTITION BY ph.deal_id ORDER BY ph.recorded_at) as prev_price,
           MIN(ph.price) OVER (PARTITION BY ph.deal_id) as lowest_price
    FROM price_history ph
    WHERE ph.recorded_at > :cutoff
)
SELECT d.*, ranked.price as new_price, ranked.prev_price, ranked.lowest_price
FROM ranked JOIN deals d ON d.id = ranked.deal_id
WHERE ranked.prev_price IS NOT NULL AND ranked.price < ranked.prev_price
```

**`generate_trend_chart()`** — currently D+1 queries, becomes 1:

```sql
SELECT ph.deal_id, ph.price, ph.recorded_at
FROM price_history ph
JOIN deals d ON d.id = ph.deal_id
WHERE d.profile = :profile AND ph.recorded_at > :cutoff
ORDER BY ph.recorded_at
```

### 2e. State Consolidation & Migration

- New Alembic migration directory (`storage/migrations/`)
- Migration script reads existing `state/*.json` files, inserts `seen_deals` rows
- `load_state()` / `save_state()` replaced with `SeenDealRepository` calls
- Price history from JSON state migrated to `price_history` table (dedup against existing)
- After migration: `state/*.json` files deleted (keep `health.json` — separate concern)

### 2f. Retire `storage/sqlite.py`

The 690-line monolith replaced by:
- `storage/models.py` (~100 lines)
- `storage/database.py` (~30 lines)
- `storage/repositories.py` (~300 lines)

Total: ~430 lines, with proper transactions and no N+1 patterns.

### Scope

Storage layer fully rewritten. `deal_hunter.py` state functions updated. Dashboard `get_db()` updated. `feedback_bot.py` updated to use repositories/sessions instead of `SQLiteStorage`. `visualization/charts.py` updated to use `PriceRepository` batch query (fixes N+1). All tests touching `SQLiteStorage` rewritten for session-based repos. This is the biggest phase.

---

## Phase 3: Service Layer Extraction & `deal_hunter.py` Decomposition

**Goal:** Break the 1,356-line orchestrator into focused service modules. `deal_hunter.py` becomes a thin CLI entrypoint (~150 lines).

### 3a. Service Directory Structure

```
services/
├── __init__.py
├── types.py              # Shared typed dataclasses (~80 lines, created first)
├── fetcher.py            # Deal fetching & deduplication (~120 lines)
├── scorer.py             # Scoring orchestration (~60 lines)
├── price_tracker.py      # Price change detection (~100 lines)
├── alerter.py            # Notification dispatch (~130 lines)
├── profile_manager.py    # Profile loading, validation, CRUD (~80 lines)
└── health_tracker.py     # Health state & watchdog (~80 lines)
```

### 3a-1. `services/types.py` (created first — other services depend on these)

Typed dataclasses replacing raw `dict` passing between services:

```python
@dataclass
class FetchResult:
    deals: list[Deal]
    source_results: dict[str, SourceResult]
    errors: list[str]

@dataclass
class ScoredDeal:
    deal: Deal
    result: ScoreResult
    category: str

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
class PriceTrackingConfig:
    enabled: bool
    min_drop_percent: int
    min_drop_amount: int
    track_increases: bool

@dataclass
class HealthStatus:
    overall: str              # "ok" / "partial" / "error"
    last_run: datetime | None
    profile_results: dict
    failing_sources: list[str]

@dataclass
class DealDetailData:
    deal: Deal
    price_history: list[PriceHistory]
    lowest_price: int | None
    previous_price: int | None
    score_data: ScoreResult | None

@dataclass
class DashboardStats:
    total_deals: int
    high_score_pct: float
    new_today: int
    drops_count: int
```

### 3b. `services/fetcher.py`

Extracted from `deal_hunter.py` lines 400-530:

```python
class DealFetcher:
    def __init__(self, source_registry: dict[str, type[Source]]): ...
    def fetch_all(self, profile: dict) -> FetchResult: ...
    def deduplicate(self, deals: list[Deal], config: dict) -> list[Deal]: ...
```

Owns: source instantiation, per-source error handling, rate limiting coordination, dedup logic.

### 3c. `services/scorer.py`

Extracted from `deal_hunter.py` lines 615-640 and filter registry lookup:

```python
class ScoringService:
    def __init__(self, filter_registry: dict[str, type[BaseFilter]]): ...
    def get_filter(self, profile: dict) -> BaseFilter: ...
    def score_deals(self, deals: list[Deal], profile: dict) -> list[ScoredDeal]: ...
    def detect_category(self, deal: Deal, profile: dict) -> str: ...
```

### 3d. `services/price_tracker.py`

Extracted from `deal_hunter.py` lines 206-325. Simplified because Phase 2 eliminated dual JSON/SQLite state:

```python
class PriceTracker:
    def __init__(self, price_repo: PriceRepository, seen_repo: SeenDealRepository): ...
    def check_price_change(self, deal: Deal, profile: dict) -> PriceChange | None: ...
    def get_tracking_config(self, profile: dict) -> PriceTrackingConfig: ...
```

### 3e. `services/alerter.py`

Extracted from `deal_hunter.py` alert dispatch, digest, and quiet hours:

```python
class AlertService:
    def __init__(self, notifier: TelegramNotifier, alert_repo: AlertQueueRepository): ...
    def send_deal_alerts(self, scored_deals: list[ScoredDeal], profile: dict) -> int: ...
    def send_price_drop_alerts(self, drops: list[PriceChange], profile: dict) -> int: ...
    def send_digest(self, profile: str, days: int = 7) -> None: ...
    def flush_queued(self, profile: str) -> int: ...
    def is_quiet_hours(self, profile: dict) -> bool: ...
```

### 3f. `services/profile_manager.py`

Consolidates profile loading from `deal_hunter.py` and `dashboard/dependencies.py`:

```python
class ProfileManager:
    def __init__(self, profiles_dir: Path): ...
    def load(self, name: str) -> dict: ...
    def list_all(self, include_disabled: bool = False) -> list[str]: ...
    def validate(self, profile: dict) -> list[str]: ...
    def save(self, name: str, data: dict) -> None: ...
    def safe_path(self, name: str) -> Path: ...
```

### 3g. `services/health_tracker.py`

Extracted from `health.py` (228 lines) + health code in `deal_hunter.py`:

```python
class HealthTracker:
    def __init__(self, health_path: Path): ...
    def record_run(self, profile_results: dict, source_results: dict) -> None: ...
    def get_status(self) -> HealthStatus: ...
    def check_watchdog(self) -> bool: ...
    def get_failing_sources(self) -> list[str]: ...
```

`health.json` stays as JSON file (not migrated to SQLite) — it's a status snapshot read by systemd watchdog.

### 3h. Slimmed `deal_hunter.py` (~150 lines)

Becomes a thin CLI entrypoint that wires dependencies and delegates:

```python
def main():
    args = parse_args()
    profile_mgr = ProfileManager(PROFILES_DIR)

    with get_session() as session:
        fetcher = DealFetcher(SOURCE_REGISTRY)
        scorer = ScoringService(FILTER_REGISTRY)
        price_tracker = PriceTracker(PriceRepository(session), SeenDealRepository(session))
        alerter = AlertService(TelegramNotifier(...), AlertQueueRepository(session))
        health = HealthTracker(HEALTH_PATH)

        if args.health: health.print_status()
        elif args.watchdog: health.check_and_alert(alerter)
        elif args.digest: alerter.send_digest(args.profile)
        elif args.validate: profile_mgr.validate_and_print(args.profile)
        else: run_profiles(args, profile_mgr, fetcher, scorer, price_tracker, alerter, health)
```

### 3i. `--verify` Mode

Verbose scoring output (`_print_verbose_plain`, `_print_verbose_rich`) moves to `cli/verify.py` (~100 lines).

### Scope

`deal_hunter.py` decomposed into 6 service modules + slim CLI. `health.py` absorbed. Dashboard services and dependencies updated to use `ProfileManager` and repositories. ~600 lines of new service code replacing ~1,350 lines of tangled orchestrator.

---

## Phase 4: Dashboard Route Cleanup & API Layer

**Goal:** Remove business logic from route handlers, fix remaining performance issues, establish clean HTTP-to-service separation.

### 4a. Dashboard Services Package

Expand the existing `dashboard/services.py` into a package:

```
dashboard/services/
├── __init__.py
├── deal_service.py       # Deal listing, detail, comparison, stats
├── profile_service.py    # Profile CRUD for dashboard
└── tuner_service.py      # Scoring preview/simulation
```

```python
class DashboardDealService:
    def __init__(self, session: Session, profile_mgr: ProfileManager): ...
    def get_deals_page(self, *, profile, source, min_score, ...) -> DealsPageData: ...
    def get_deal_detail(self, deal_id: str) -> DealDetailData: ...
    def get_stats(self, score_threshold: int) -> DashboardStats: ...
    def get_category_distribution(self) -> dict[str, int]: ...
    def get_price_drops_page(self, days: int) -> PriceDropsPageData: ...
```

### 4b. Route Handler Slimming

Each handler becomes ~10-15 lines: parse params, call service, return response.

Before (40 lines, 3+ queries, Python aggregation):
```python
def _price_drops_view(request, days, db):
    drops = db.get_price_drops(days=days)
    all_deals = db.get_deals()
    categories = {}
    for deal in all_deals: ...
```

After:
```python
def _price_drops_view(request, days, service):
    data = service.get_price_drops_page(days=days)
    return templates.TemplateResponse("price_trends.html", {"request": request, **data})
```

### 4c. Fix `api_stats()` Performance

Add `PriceRepository.count_drops(days: int) -> int` using `SELECT COUNT(*)` with window function CTE. Currently fetches all drop rows just to call `len()`.

### 4d. Dashboard Dependency Injection Update

```python
def get_deal_service(session: Session = Depends(get_session)) -> DashboardDealService:
    return DashboardDealService(session, ProfileManager(PROFILES_DIR))
```

Routes receive constructed services via `Depends()` — no raw database access in handlers.

### 4e. Response Type Annotations

Add return types to all 31 route handlers (`-> HTMLResponse`, `-> JSONResponse`, `-> RedirectResponse`).

### 4f. Consolidate Duplicate Routes

- Profile detail: standalone pages redirect to tab-based views
- Single pattern for profile viewing: `/profiles/{name}?tab=overview|edit|yaml|tuner`

### Scope

~5 route files refactored, new dashboard services package (~200 lines), route handlers shrink ~40%.

---

## Phase 5: Template DRY & Frontend Cleanup

**Goal:** Eliminate duplication across templates, extract inline JavaScript, establish reusable macro/partial library.

### 5a. New Macros (expand `macros.html` from 6 to ~15 macros)

```
score_rules_table(rules, penalties, editable=false)  — duplicated across 5 templates
budget_inputs(min_val, max_val, currency, editable)  — duplicated 5+ times
price_drops_table(drops)                              — duplicated in 2 templates
category_distribution(categories)                     — duplicated in 2 templates
category_trends(trends)                               — duplicated in 2 templates
profile_cards(profile)                                — duplicated in 2 templates
yaml_editor(profile_name, content)                    — duplicated in 2 templates
form_errors()                                         — repeated in 3 templates
table_header(*columns)                                — repeated styling in 5+ templates
```

### 5b. Consolidate Redundant Templates

| Delete | Replace With | Savings |
|--------|-------------|---------|
| `profile_detail.html` (124 lines) | Tab partial via `{% include %}` | ~120 lines |
| `profile_edit.html` (222 lines) | Redirect to `?tab=edit` | ~220 lines |
| `profile_yaml.html` (85 lines) | Redirect to `?tab=yaml` | ~85 lines |
| `price_trends.html` duplication | Shared macros with `price_drops_view.html` | ~170 lines |

Total: ~600 lines eliminated.

### 5c. Extract Inline JavaScript to Static Files

New static JS files:

```
dashboard/static/js/
├── price-chart.js      # from deal_detail.html (70 lines inline)
├── sparklines.js       # from 4 templates (createSparkline init loops)
├── yaml-editor.js      # from 2 templates (CodeMirror setup)
└── profile-actions.js  # from profile detail (delete, toggle, run)
```

Templates pass data via `data-*` attributes:
```html
<canvas id="price-chart" data-deal-id="{{ deal.id }}"></canvas>
<script src="/static/js/price-chart.js"></script>
```

### 5d. Replace Inline Event Handlers

20+ `onclick="..."` attributes replaced with `data-action` attributes and event delegation:

```html
<!-- Before -->
<button onclick="filterChart('1m')">1M</button>

<!-- After -->
<button data-action="filter-chart" data-period="1m">1M</button>
```

### 5e. Impact

| Template Group | Before | After | Reduction |
|---|---|---|---|
| Profile forms (5) | ~960 lines | ~300 lines | -69% |
| Price views (2) | ~348 lines | ~150 lines | -57% |
| Detail pages with inline JS | ~620 lines | ~350 lines | -44% |
| **Total** | **~3,278 lines** | **~1,900 lines** | **-42%** |

### Scope

`macros.html` grows from 84 to ~250 lines. 3 templates deleted, 4 new JS files created. No backend changes.

---

## Phase 6: Type Hints, Final Polish & Cleanup

**Goal:** Complete type coverage, remove dead code, strict linting across the codebase.

### 6a. Pydantic Models for API Validation (`dashboard/schemas.py`)

```python
class StatusUpdate(BaseModel):
    status: Literal["watching", "rejected", "active"]

class WatchlistAdd(BaseModel):
    target_price: int = Field(gt=0)

class ProfileCreate(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    content: dict
```

### 6b. Dead Code Removal

Files deleted after all phases:
- `storage/sqlite.py` (replaced by models + repos)
- `health.py` (absorbed into `services/health_tracker.py`)
- `profile_detail.html`, `profile_edit.html`, `profile_yaml.html` (replaced by tab partials)
- `state/*.json` files (consolidated into SQLite)
- `scripts/migrate_state_to_sqlite.py` (superseded by Alembic)

Functions removed from `deal_hunter.py`:
- `load_state()`, `save_state()`, `check_price_changes()`, `get_price_tracking_config()`, `deduplicate()`, `fetch_all_deals()`, `get_filter()`, `_detect_category()`, `_run_normal()`, `_run_verify()`, `_print_verbose_plain()`, `_print_verbose_rich()`, `_run_with_health_tracking()`, `_send_source_failure_alert()`

### 6c. Mypy Strict Mode

```toml
[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["sqlalchemy.ext.mypy.plugin", "pydantic.mypy"]
```

### 6d. Final Ruff Pass

`ruff check --fix` + `ruff format` with `ANN` rules enforced and `E501` no longer ignored.

### Scope

~50 type annotations added, ~150 lines of new typed dataclasses/schemas, dead code removal across ~10 files. No behavioral changes.

---

## Final Directory Structure

```
deal_hunter/
├── deal_hunter.py              # Thin CLI entrypoint (~150 lines)
├── feedback_bot.py             # Telegram bot (updated to use repositories)
│
├── services/                   # Business logic layer
│   ├── __init__.py
│   ├── types.py                # Shared dataclasses
│   ├── fetcher.py              # Deal fetching & deduplication
│   ├── scorer.py               # Scoring orchestration
│   ├── price_tracker.py        # Price change detection
│   ├── alerter.py              # Notification dispatch & quiet hours
│   ├── profile_manager.py      # Profile YAML loading, validation, CRUD
│   └── health_tracker.py       # Health state & watchdog
│
├── sources/                    # Source plugins (unchanged)
│   ├── base.py
│   ├── __init__.py
│   ├── yaml_source.py
│   ├── pepper.py
│   ├── web.py
│   └── rss.py
│
├── filters/                    # Scoring engines (unchanged)
│   ├── base.py
│   ├── __init__.py
│   └── bike_filter.py
│
├── storage/                    # Data layer (rewritten)
│   ├── __init__.py
│   ├── database.py             # Engine, SessionLocal, get_session()
│   ├── models.py               # SQLAlchemy ORM models
│   ├── repositories.py         # Domain-organized query wrappers
│   └── migrations/             # Alembic
│       ├── env.py
│       ├── alembic.ini
│       └── versions/
│
├── cli/                        # CLI presentation
│   ├── __init__.py
│   └── verify.py               # --verify verbose output
│
├── dashboard/                  # Web UI
│   ├── __init__.py
│   ├── dependencies.py
│   ├── schemas.py              # Pydantic request/response models
│   ├── services/
│   │   ├── deal_service.py
│   │   ├── profile_service.py
│   │   └── tuner_service.py
│   ├── routes/
│   │   ├── deals.py
│   │   ├── profiles.py
│   │   ├── tuner.py
│   │   ├── watchlist.py
│   │   └── health.py
│   ├── static/js/
│   │   ├── sidebar.js
│   │   ├── compare.js
│   │   ├── charts.js
│   │   ├── profile-form.js
│   │   ├── tuner.js
│   │   ├── price-chart.js
│   │   ├── sparklines.js
│   │   ├── yaml-editor.js
│   │   └── profile-actions.js
│   └── templates/
│       ├── base.html
│       ├── macros.html
│       ├── deals.html
│       ├── deal_detail.html
│       ├── compare.html
│       ├── watchlist.html
│       ├── profiles.html
│       ├── profile_unified.html
│       ├── profile_create.html
│       ├── health.html
│       ├── price_trends.html
│       ├── tuner.html
│       └── partials/
│
├── notifiers/                  # (unchanged)
├── visualization/              # (updated: batch query for trend chart)
├── utils/                      # (unchanged)
├── stores/                     # YAML store definitions (unchanged)
├── profiles/                   # User profiles (gitignored)
├── state/                      # Only health.json remains
├── tests/                      # Updated for new structure
└── docs/
```

## Line Count Projection

| Area | Before | After | Change |
|------|--------|-------|--------|
| `deal_hunter.py` | 1,356 | ~150 | -89% |
| `services/` (new) | 0 | ~570 | new |
| `storage/` | 695 | ~430 | -38% |
| `health.py` | 228 | 0 (merged) | -100% |
| Dashboard routes | 842 | ~500 | -41% |
| Dashboard services | 91 | ~200 | +120% |
| Templates | 3,278 | ~1,900 | -42% |
| **Total non-test** | **~6,490** | **~4,750** | **-27%** |

## Phase Execution Order

```
Phase 1 (Tooling)        ──> no structural changes, safe to ship
Phase 2 (SQLAlchemy)     ──> biggest risk, biggest payoff
Phase 3 (Services)       ──> depends on Phase 2 models/repos
Phase 4 (Dashboard)      ──> depends on Phase 3 services
Phase 5 (Templates)      ──> independent of Phase 3/4, but cleaner after
Phase 6 (Types/Polish)   ──> final pass, depends on all prior phases
```

Each phase is independently deployable and testable. Tests must pass at the end of every phase.

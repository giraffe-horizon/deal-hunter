# CHANGELOG


## v0.15.1 (2026-04-17)

### Bug Fixes

- **dashboard**: Split Watch bookmarks from Price Alerts + fix button swaps
  ([`aa5fbf4`](https://github.com/giraffe-horizon/deal-hunter/commit/aa5fbf41b84e2478ea988e71848974f83de851d5))

Previously the dashboard's "Watch" button set offers.status='watching' but the /watchlist page
  showed target-price alerts from an unrelated SQLite table, so clicking Watch and visiting
  Watchlist showed nothing related. On top of that, clicking Watch/Skip on a row wiped the action
  buttons, and clicking them on the detail page wiped the Target form.

- Repurpose /watchlist as a bookmark page listing offers with status='watching' (same semantics the
  Telegram bot already uses). - Move the price-alert page (formerly /watchlist) to /alerts with a
  "Price Alerts" label; backing table stays named watchlist (no DB migration needed). - Wrap the
  deals-table status badge + actions in a single #row-actions-{id} div that swaps via outerHTML, so
  Watch/Skip buttons stay visible after a click. - Split detail-page controls into
  #watch-skip-controls + sibling Target form; button responses re-render the same wrapper. - Log
  dashboard Watch/Skip clicks to the feedback table (parity with bot commands). - Update sidebar
  (Watchlist + Price Alerts) and refresh tests/e2e URLs.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>


## v0.15.0 (2026-04-14)

### Bug Fixes

- **types**: Add mypy annotations for new repos + ingest_one
  ([`f940397`](https://github.com/giraffe-horizon/deal-hunter/commit/f94039779b70fa4de4c5b0eb5d6b5bc2af397048))

- Type intermediate locals in Product/ProductAlias/FxRate repo getters so mypy doesn't see Any from
  session.get() / scalars().first(). - Annotate DealFetcher.ingest_one: session: Session, return
  type Offer (TYPE_CHECKING imports to keep runtime lazy).

Fixes CI lint failures on PR #12.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Chores

- Remove stale roadmap docs and one-time migration script
  ([`12424d3`](https://github.com/giraffe-horizon/deal-hunter/commit/12424d370cb772f786ae3973faadec14e2ddd804))

- Delete docs/ROADMAP.md and docs/ROADMAP-v2.md (superseded by phase plans in
  docs/superpowers/plans/ and CHANGELOG.md) - Delete scripts/migrate_json_state.py and its test
  (one-shot JSON->SQLite migration, already executed; SQLite is the sole state backend now) - Remove
  stale CLAUDE.md reference to the migration script

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Continuous Integration

- Fix pipeline for src-layout + package restructure
  ([`686970a`](https://github.com/giraffe-horizon/deal-hunter/commit/686970ac6cbc07eb6c1b510d936171fa5828560e))

CI was still targeting the pre-Phase-2 flat layout and the Phase-2 migration missed a couple of
  hard-coded paths. Fixes:

.github/workflows/ci.yml - mypy: replace `deal_hunter.py sources/ filters/ notifiers/ utils/` with
  `src/deal_hunter` (new package root) - lint job: install via `pip install -e ".[dev]"` so mypy
  sees full type context (types-*, pydantic plugin, etc.) - pytest --cov: drop `--cov=sources
  --cov=filters`; use single `--cov=deal_hunter` covering the whole package - smoke tests: switch
  from `python deal_hunter.py` to the console scripts (`deal-hunter --version` / `deal-hunter
  --list`)

src/deal_hunter/sources/yaml_source.py - STORES_DIR: the stores/ directory lives at the repo root,
  not inside the package. Phase-2 rename left the path computing parent.parent →
  src/deal_hunter/stores (which doesn't exist), silently yielding an empty SOURCE_REGISTRY. Now
  resolves parents[3] correctly → repo-root/stores.

tests/test_migration_003_rename.py, test_migration_004_products_schema.py - alembic config path:
  `storage/migrations/alembic.ini` → `src/deal_hunter/storage/migrations/alembic.ini`

pyproject.toml - New mypy override for `deal_hunter.bot.commands` + `deal_hunter.bot.callbacks`:
  disable union-attr/arg-type/index errors. python-telegram-bot stubs type `update.message` as
  `Message | None`, but library dispatch guarantees it's set inside
  CommandHandler/CallbackQueryHandler bodies. Previous CI didn't catch this because bot/ wasn't in
  the mypy target.

Test suite after fix: 696 passed / 0 failed / 0 errors (up from 663/31/4). ruff + mypy both clean on
  src/deal_hunter.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Documentation

- Fix stale price_history docstrings post-rename
  ([`a740229`](https://github.com/giraffe-horizon/deal-hunter/commit/a74022913b7806d267161dfdcf6ae96f1b03d2cc))

- **changelog**: Record phase A2 products schema + event emission
  ([`105ae85`](https://github.com/giraffe-horizon/deal-hunter/commit/105ae858f100a64f6b3c03f8cfa0e7df3eb1a825))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **plan**: Add phase A1 implementation plan — rename deals->offers
  ([`a7eb44a`](https://github.com/giraffe-horizon/deal-hunter/commit/a7eb44aff93417184c21d777ed971bb0c47ac705))

First implementation plan for the products-and-offers migration. Covers table rename (deals->offers,
  price_history->price_points), class rename (Deal->Offer, PriceHistory->PricePoint,
  DealRepository->OfferRepository), and Alembic revision 003 with round-trip test. Column renames
  and new schema are deferred to Phase A2.

- **plan**: Mark products-and-offers plan complete (A1+A2 shipped)
  ([`fc1bb3b`](https://github.com/giraffe-horizon/deal-hunter/commit/fc1bb3b3a304f41aa5526ea4f13a870c86f2698c))

All 12 tasks landed on phase-a1-rename worktree (head 105ae85, 698 tests passing). Plan doc now
  records each task's status and commit SHA, plus the deviations encountered during execution (Tasks
  7-10 commit batching, Task 5 FK bootstrapping, Task 11 split for score/category kwargs, Task 11
  mutable per-run profile_name caveat).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **plan**: Unified products-and-offers plan (A1 finish + A2)
  ([`5b1e063`](https://github.com/giraffe-horizon/deal-hunter/commit/5b1e063fe61a688af6f08a1b68601ece0e20181c))

Supersedes the phase-a1 plan file (left on disk as historical record). Picks up from the A1 worktree
  state (commits 2e1cf04, bf9df9c, cdd7aba already landed) and carries through 12 tasks: finish the
  OfferRepository rename, Alembic 004 (column renames + new tables), ORM updates with
  adapter-preserving _to_dict, and wiring OfferPayloadHistory + DealEvent emission into the fetcher.
  Phases B-G deferred to their own plans.

- **spec**: Decompose Phase A into A1 (rename) + A2 (schema)
  ([`8867338`](https://github.com/giraffe-horizon/deal-hunter/commit/88673386caf3ac1cd2c8fe8152528cf6b223eb68))

Reflects actual execution split: A1 landed a pure table/class rename with column names preserved
  (Alembic 003, in phase-a1-rename worktree); A2 handles column renames, new columns, and new
  product/event tables (Alembic 004, pending). Clarifies risks, test file naming, and the 9-step
  rollout order.

- **spec**: Re-align products-and-offers design to current repo
  ([`197f3cf`](https://github.com/giraffe-horizon/deal-hunter/commit/197f3cf40e2b917b938ec9a809f31b84b7eb93c1))

Update the 2026-04-13 design spec to match the post Phase 3-6 refactor (SQLAlchemy ORM, Alembic
  migrations, service layer, Pydantic dashboard schemas). Key changes:

- Adopt Option B naming refactor: rename Deal/deals -> Offer/offers and PriceHistory/price_history
  -> PricePoint/price_points; introduce new DealEvent append-only event log. Offer ids
  ("{source}:{native_id}") preserved verbatim so callback_data, CLI, watchlist FK keep working. -
  Schema migrations land as Alembic revisions 003_rename_deals_to_offers and 004_products_schema
  under storage/migrations/versions/. - Module paths aligned with current layout:
  services/matching/, services/fx/nbp.py, services/fetcher.py (existing DealFetcher.dedup coexists),
  cli/backfill_products.py, cli/eval_matching.py, dashboard/routes/products.py,
  dashboard/routes/review.py, dashboard/services/product_service.py, dashboard/schemas.py. - Tests
  updated to existing naming (test_models.py, test_repositories.py, test_services.py extended;
  test_matching_*.py added; tests/e2e/test_products.py for Playwright coverage). - FK types
  corrected: offer_id columns are TEXT, matching offers.id. - Added risk note covering in-memory vs
  persistent dedup overlap.

### Features

- **db**: Add alembic 004 — column renames, new product schema, backfill
  ([`ec92d8c`](https://github.com/giraffe-horizon/deal-hunter/commit/ec92d8c0ab5f61e7cb7e17aca2e40a8a1fcbfaa1))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **db**: Add alembic revision 003 renaming deals->offers
  ([`2e1cf04`](https://github.com/giraffe-horizon/deal-hunter/commit/2e1cf0415a4593295b4aec39a865b3484b7b9dbf))

Renames the `deals` table to `offers` and `price_history` to `price_points` at the database level.
  Includes a round-trip test (upgrade, downgrade, data preservation) in
  tests/test_migration_003_rename.py.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **events**: Dealevent model + repository
  ([`f2109fe`](https://github.com/giraffe-horizon/deal-hunter/commit/f2109fe37c230c435133acd2801445196f6889e8))

Model and repository were implemented as part of Task 7 model batch; this commit adds the test suite
  for emit, get_unnotified, and mark_notified operations.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **events**: Offerpayloadhistory model + FIFO N=10 repository
  ([`8593437`](https://github.com/giraffe-horizon/deal-hunter/commit/8593437331b9865eb23e745a3edfb85da7807b29))

Model and repository were implemented as part of Task 7 model batch; this commit adds the dedicated
  test suite verifying FIFO eviction and per-offer isolation.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **fetcher**: Emit DealEvent + append OfferPayloadHistory on ingest
  ([`7951515`](https://github.com/giraffe-horizon/deal-hunter/commit/7951515e759ededb0b7b9a793a6273d4355375d9))

- **ingest**: Wire DealFetcher.ingest_one into deal_hunter live ingest path
  ([`c6b249f`](https://github.com/giraffe-horizon/deal-hunter/commit/c6b249f410c8fe252d7222f5e41cc29761f0571f))

- **products**: Add Product + ProductAlias models + minimal repositories
  ([`ef14a2f`](https://github.com/giraffe-horizon/deal-hunter/commit/ef14a2fa36ee4f5a4d299060f93ef59486a19651))

- Add Product, ProductAlias, OfferPayloadHistory, DealEvent, MatchReview, MatchDecision, FxRate ORM
  models to storage/models.py - Restore deferred FK + relationship on Offer.product_id and
  PricePoint.product_id now that Product exists - Add Offer.product, Offer.payload_history,
  Offer.events relationships - Add ProductRepository, ProductAliasRepository to
  storage/repositories.py - Update test_models.py expected table set

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

### Refactoring

- Migrate callers to renamed offer/price_point columns, keep legacy dict keys
  ([`a3049ee`](https://github.com/giraffe-horizon/deal-hunter/commit/a3049ee6c1fd7cba8d66c48b1743cf0a6ebd62f7))

- OfferRepository.upsert: accepts both new names (raw_title, current_price_pln, url, first_seen_at,
  last_seen_at) and legacy kwarg aliases (title, price, link, first_seen, last_seen) for
  backward-compat callers - OfferRepository._to_dict: emits both legacy keys (title, price, link,
  first_seen, last_seen) and new keys (raw_title, current_price_pln, url, first_seen_at,
  last_seen_at, product_id, ...) — templates/Telegram/bot unchanged - OfferRepository._record_price
  + PriceRepository.record: raw SQL updated to use offer_id + price_pln column names - All other raw
  SQL in OfferRepository / PriceRepository / WatchlistRepository updated: aliases preserve legacy
  dict-key contract (raw_title AS title, etc.)

- ORM attr access in get_by_status: last_seen -> last_seen_at - PriceRepository: ORM attribute reads
  updated (offer_id, price_pln) - storage/models.py: add server_default for currency_original and
  is_active so raw SQL inserts that omit those columns don't fail NOT NULL constraints -
  scripts/migrate_json_state.py: raw SQL updated to new column names - tests updated: ORM
  constructors, filter_by(), attribute assertions, raw SQL

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **.gitignore**: Reorganize entries and remove example profile
  ([`0612367`](https://github.com/giraffe-horizon/deal-hunter/commit/061236754af0d45936fd36a0ed46480619d6bee3))

* Moved Python-related entries to the top for better organization. * Added missing entries for
  egg-info, dist, and build directories. * Removed the example profile file `headphones.yaml` as it
  is no longer needed. * Ensured that the .env entry is clearly separated for clarity.

- **api**: Create_app() factory + middleware/templating split (Phase 3B #10)
  ([`bb2f936`](https://github.com/giraffe-horizon/deal-hunter/commit/bb2f936f1a08a75ee0f9ee487592b7101d2cdf0a))

Splits the 75-line api/__init__.py into four focused modules:

api/templating.py Jinja2 templates + format_pln filter + APP_VERSION api/middleware.py csrf_check
  ASGI middleware api/app.py create_app() factory — builds FastAPI instance, mounts static,
  registers middleware, includes routers, wires "/" redirect api/__init__.py thin package entry:
  calls create_app() once to expose `app` (uvicorn target: deal_hunter.api:app) and re-exports
  templates / dependency helpers.

Why: the old __init__.py mixed four concerns — app construction, middleware, template env, and
  dependency re-export — with side-effectful imports (`app = FastAPI(...)` at module top) that make
  alt deployments (tests spinning up isolated apps, or multi-tenant setups) awkward.

With the factory: - tests can build a fresh app via create_app() without patching globals -
  middleware and template wiring are each testable in isolation - routes keep working unchanged
  (still `from deal_hunter.api import templates`)

Public surface preserved: `from deal_hunter.api import app, templates, format_pln, get_db, ...`
  still works. `_get_profiles` legacy alias kept for existing test imports.

Test suite: 663 passed / 31 failed — identical to pre-change baseline.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **bot**: Split bot/main.py into callbacks.py + commands.py (Phase 3C #12)
  ([`5f3b70b`](https://github.com/giraffe-horizon/deal-hunter/commit/5f3b70bb8af9e22c77063f01e322438c7c6f9254))

bot/main.py drops from 225 → 72 lines, now owning only: logging setup, token check, Application
  wiring, SIGTERM handling. All handler bodies move out:

bot/callbacks.py handle_callback — inline-keyboard watch/skip dispatcher (Offer.status + Feedback
  record) bot/commands.py cmd_watch, cmd_skip, cmd_status, cmd_target, cmd_watchlist — all
  slash-command handlers

Public surface preserved via __all__ re-export in bot/main.py so existing `from deal_hunter.bot.main
  import handle_callback / cmd_*` imports keep working (tests rely on this).

Test patches of `deal_hunter.bot.main.get_session` are updated to point at the actual import site
  (`bot.callbacks.get_session` or `bot.commands.get_session`) — since the handlers now live in those
  modules, that's where the `get_session` symbol they call actually is.

Extracts `_MAX_MSG_LEN = 3500` into a module constant in commands.py (previously a magic number in
  cmd_watchlist).

Test suite: 663 passed / 31 failed — identical to pre-change baseline.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **cli**: Extract hunt/digest/chart services from cli/main.py (Phase 3C #11)
  ([`98171cc`](https://github.com/giraffe-horizon/deal-hunter/commit/98171ccf068f126c0e3035938bdceef16b70a059))

cli/main.py drops from 605 → 160 lines; it's now purely argparse + dispatch. Business logic moves
  into four new service modules:

services/runtime.py Shared singletons — lru_cache'd factories for ProfileManager, DealFetcher,
  ScoringService, HealthTracker, plus get_telegram() and get_topic_id(). reset_runtime() for tests.

services/hunt_service.py run_profile() + run_profiles(profile_names, version=...) — the full fetch →
  score → persist → alert orchestration (previously cli.run_profile + _run_with_health_tracking).

services/digest_service.py run_digest() — weekly price-drop digest, previously cli.run_digest.

services/chart_service.py run_price_chart() + run_trend_chart(), sharing a _send_chart() helper.

Why: cli/main.py was acting as both CLI and orchestrator, which made the "run this hunt from code"
  use case (tests, dashboard, future API endpoints) hard. Now: - services/ owns every non-CLI
  surface - the CLI is a thin adapter over those services - singletons live in services/runtime.py
  rather than being constructed as module-level state in cli/main.py - every service can be invoked
  without argparse

Behavior preserved: same flags, same output, same Telegram/SQLite/ health.json effects. Test suite:
  663 passed / 31 failed — identical to pre-change baseline.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **core**: Centralize settings + logging (Phase 3A)
  ([`0d145d7`](https://github.com/giraffe-horizon/deal-hunter/commit/0d145d7f4b145fbc1e1a1902c5e9ee65072996d1))

Introduces two cross-cutting modules in deal_hunter.core:

* settings.py — a pydantic-settings `Settings` class owning all env vars (TELEGRAM_*, QUIET_HOURS_*,
  DEAL_HUNTER_STATE_DIR, DEAL_HUNTER_PROFILES_DIR, DATABASE_URL, DEALS_PER_PAGE, SCORE_THRESHOLD)
  plus derived paths (base_dir, state_dir, profiles_dir, default_database_url) and a
  `telegram_configured` predicate. `get_settings()` returns a cached instance; `Settings()` can be
  instantiated directly to re-read env.

* logging.py — `setup_app_logging()` (stream + file, used by CLI) and `setup_bot_logging()`
  (stream-only, used by feedback bot). Both idempotent.

Replaces scattered `os.environ.get(...)` reads and ad-hoc logging setup in: cli/main.py,
  bot/main.py, api/dependencies.py, api/routes/health.py, api/view_services/__init__.py,
  services/alerter.py, storage/database.py.

`is_quiet_hours()` and `view_services` read via `Settings()` (uncached) so env overrides (tests
  using monkeypatch / importlib.reload) still work.

Test suite: 663 passed / 31 failed — identical to pre-change baseline (failures are pre-existing
  schema/store issues unrelated to Phase 3A).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **layout**: Migrate to src/deal_hunter/ package (Phase 2)
  ([`23f8ebf`](https://github.com/giraffe-horizon/deal-hunter/commit/23f8ebfa6e350ff3a2a5fea4e5295ddb58ecc971))

Move flat package directories into a src-layout umbrella package: - services/, sources/, storage/,
  notifiers/, utils/, cli/, visualization/ -> src/deal_hunter/<pkg>/ - filters/ ->
  src/deal_hunter/domain/scoring/ - services/types.py -> src/deal_hunter/core/types.py - dashboard/
  -> src/deal_hunter/api/ - dashboard/services/ -> src/deal_hunter/api/view_services/ -
  deal_hunter.py (CLI script) -> src/deal_hunter/cli/main.py - feedback_bot.py ->
  src/deal_hunter/bot/main.py

Configuration updated: - pyproject.toml: packages.find where=["src"]; new console scripts
  deal-hunter and deal-hunter-bot; mypy/semantic-release paths updated - Dockerfile: single COPY
  src/ replaces per-package COPYs; HEALTHCHECK uses deal-hunter script - docker-compose.yml: bot
  uses deal-hunter-bot; web uses uvicorn deal_hunter.api:app - docker/entrypoint.sh and
  scripts/systemd/*.service: ExecStart uses new console scripts

Imports rewritten across 62 files; BASE_DIR path depths retargeted for the new layout. Two tests
  (test_dashboard, test_yaml_source) updated to use the new module references in reload/patch calls.

No file contents split yet (Phase 3).

Verified: ruff clean; python -m compileall clean; pytest --collect-only collects 768 tests
  (identical to pre-refactor baseline); deal-hunter --list works; deal_hunter.api:app loads.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **models**: Rename Deal->Offer, PriceHistory->PricePoint
  ([`cdd7aba`](https://github.com/giraffe-horizon/deal-hunter/commit/cdd7aba4e422f191f9d4766720e63a4d47c0d57c))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **models**: Rename Offer/PricePoint columns; add A2 columns
  ([`526962d`](https://github.com/giraffe-horizon/deal-hunter/commit/526962d711386a9328eef71d930932c0ee5cdfe3))

- Offer: title→raw_title, price→current_price_pln, link→url, first_seen→first_seen_at,
  last_seen→last_seen_at - PricePoint: deal_id→offer_id, price→price_pln - Offer: add product_id,
  source_native_id, current_price_original, currency_original, fx_rate_used, availability,
  attributes_hint, is_active - PricePoint: add product_id, price_original, currency_original,
  fx_rate_used, availability - product_id FK to products.id omitted from ORM (managed by Alembic
  004); Product model arrives in Tasks 7-10 - test_models.py updated to assert new column names and
  A2 columns

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **notifiers**: Split telegram.py into transport/formatters/keyboards (Phase 3B #9)
  ([`7c1d620`](https://github.com/giraffe-horizon/deal-hunter/commit/7c1d620fb323596d517655240f0ce6e1aed96fab))

Replaces the 350-line notifiers/telegram.py monolith with a package:

telegram/keyboards.py build_deal_keyboard (inline keyboard markup) telegram/formatters.py pure
  Polish-HTML formatters — format_deal_alert, format_summary, format_price_drop,
  format_watchlist_alert, format_digest telegram/transport.py TelegramNotifier — HTTP transport with
  retry + rate-limit; high-level send_* methods delegate to formatters + keyboards
  telegram/__init__.py re-exports TelegramNotifier, build_deal_keyboard, all formatters; also
  re-exports `requests` and `time` so existing
  patch("deal_hunter.notifiers.telegram.requests"/"time") test hooks keep working unchanged.

Why: the old file mixed three concerns — HTTP transport, Polish message composition, and keyboard
  markup — making it hard to reuse formatters outside the HTTP client (e.g. in tests or in the
  dashboard for preview). Formatters are now pure functions and unit-testable without mocks.

Consolidates retry-loop magic numbers into module constants (_RATE_LIMIT_SLEEP, _MAX_ATTEMPTS,
  _DEFAULT_RETRY_AFTER) and extracts the 429 retry_after parser into `_retry_after()` helper to DRY
  up the two retry loops.

Test suite: 663 passed / 31 failed — identical to pre-change baseline.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **repos**: Drop DealRepository alias; CHANGELOG for A1 rename
  ([`725cce9`](https://github.com/giraffe-horizon/deal-hunter/commit/725cce91e2f67eacf5b3f2ee19fc52037e7af69a))

- **repos**: Rename DealRepository->OfferRepository, update all callers & raw SQL
  ([`c3caf8f`](https://github.com/giraffe-horizon/deal-hunter/commit/c3caf8ffa2e8c3939e4b63f60ea57602c73b8c11))

Finish the A1 rename: DealRepository -> OfferRepository (with DealRepository alias for backward
  compat), PriceHistory -> PricePoint throughout, raw SQL tables deals/price_history ->
  offers/price_points. All 677 tests green.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **storage**: Split repositories.py by aggregate (Phase 3A #8)
  ([`b30b36f`](https://github.com/giraffe-horizon/deal-hunter/commit/b30b36f1673334a1596d74125b7e43430f37afa3))

Replaces the 978-line storage/repositories.py monolith with a storage/repositories/ package, one
  file per aggregate:

offer.py OfferRepository price.py PriceRepository watchlist.py WatchlistRepository alert_queue.py
  AlertQueueRepository feedback.py FeedbackRepository seen_deal.py SeenDealRepository product.py
  ProductRepository + ProductAliasRepository offer_payload_history.py OfferPayloadHistoryRepository
  + MAX const deal_event.py DealEventRepository match.py MatchReviewRepository +
  MatchDecisionRepository fx.py FxRateRepository __init__.py public re-exports (stable import
  surface)

Existing `from deal_hunter.storage.repositories import X` call sites are unchanged — the package
  __init__ re-exports the full prior public surface.

Each submodule imports only the SQLAlchemy symbols and models it needs, which keeps per-file
  dependencies minimal and makes the aggregate boundaries explicit.

Test suite: 663 passed / 31 failed — identical to pre-change baseline.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Testing

- **migration**: Tighten 003 round-trip test and fixture hygiene
  ([`bf9df9c`](https://github.com/giraffe-horizon/deal-hunter/commit/bf9df9c255fac45c067acba41b4c798050dd1ef1))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.14.1 (2026-04-13)

### Bug Fixes

- **docker**: Update Dockerfile for Phase 3 file changes
  ([`44633f0`](https://github.com/giraffe-horizon/deal-hunter/commit/44633f06869bec063a1462562bef99cefd4b652c))

Remove deleted health.py, add new cli/ and services/ packages.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.14.0 (2026-04-13)

### Bug Fixes

- **ci**: Add pydantic to lint job for mypy plugin
  ([`8275efb`](https://github.com/giraffe-horizon/deal-hunter/commit/8275efb13a8933832307a8a31fd186d9c3212bc2))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **ci**: Resolve mypy cross-environment type ignore conflict
  ([`42a615b`](https://github.com/giraffe-horizon/deal-hunter/commit/42a615b504a0084641888f80fc50c4d87882b33a))

Remove warn_unused_ignores (causes CI/local mismatch due to different SQLAlchemy stubs
  availability). Restore type: ignore on rowcount.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Chores

- Delete dead profile templates replaced by unified page
  ([`8cae9c3`](https://github.com/giraffe-horizon/deal-hunter/commit/8cae9c329a1bf379b9e8eaf652ff913eea91cc95))

- Delete health.py — absorbed into services/health_tracker.py
  ([`e710c9b`](https://github.com/giraffe-horizon/deal-hunter/commit/e710c9b65fcb2bff2e48e42514fddcf5571cc42b))

### Documentation

- Add Phase 3 service layer implementation plan
  ([`6c57066`](https://github.com/giraffe-horizon/deal-hunter/commit/6c570665a70ef364af410ce0be841e7a619ce75e))

- Add Phase 4 dashboard cleanup implementation plan
  ([`643293b`](https://github.com/giraffe-horizon/deal-hunter/commit/643293b0f28572d591c34e78d911dc95efdaf006))

- Add Phase 5 template DRY implementation plan
  ([`fa26086`](https://github.com/giraffe-horizon/deal-hunter/commit/fa2608627f82201acf2a8902be9ce8940e9611a7))

- Update CLAUDE.md for Phase 3 service layer architecture
  ([`4aedc4c`](https://github.com/giraffe-horizon/deal-hunter/commit/4aedc4cc641c747168d66a8c1fbd5e5ed1cb88b1))

- Update CLAUDE.md for Phase 4 dashboard services
  ([`7a30784`](https://github.com/giraffe-horizon/deal-hunter/commit/7a30784472fb216b993b0d910bd68b6091790c00))

- Update CLAUDE.md for Phase 5 template cleanup
  ([`3ce0e0d`](https://github.com/giraffe-horizon/deal-hunter/commit/3ce0e0dca4e02a561e240fd6e6b23aff490ea8fe))

- Update CLAUDE.md for Phase 6 type safety and Pydantic schemas
  ([`a68f79f`](https://github.com/giraffe-horizon/deal-hunter/commit/a68f79f02d1f930604cdf0d0dd1b9bb1092ed093))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Features

- **cli**: Extract verify mode output to cli/verify.py
  ([`4e6c518`](https://github.com/giraffe-horizon/deal-hunter/commit/4e6c5188d0afa241a30247854471abec1140b72d))

Move ~230 lines of --verify formatting/display logic out of deal_hunter.py into a dedicated
  cli/verify.py module. Public API: format_breakdown_line(), print_verbose(), run_verify().
  Backward-compat aliases preserved in deal_hunter.py for existing test imports.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **dashboard**: Add Pydantic schemas for API validation
  ([`13b2698`](https://github.com/giraffe-horizon/deal-hunter/commit/13b26987b8aa663722ad234a41e2b0cbc94acd17))

StatusUpdate, WatchlistAdd, WatchlistUpdate, ProfileCreate models used to validate input in
  dashboard API endpoints.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **services**: Add AlertService — notification dispatch with quiet hours
  ([`bcde46a`](https://github.com/giraffe-horizon/deal-hunter/commit/bcde46ab40e44ee538f5402096ad6f2b16c73dbd))

Extract alert sending, quiet-hours checking, and alert queuing into AlertService. Provides
  flush_queued(), send_deal_alerts(), send_price_drop_alerts(), and send_source_failure_alert()
  methods.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **services**: Add DealFetcher — deal fetching and deduplication
  ([`310c7ff`](https://github.com/giraffe-horizon/deal-hunter/commit/310c7ffbbf157500c7ca276c45a808189eab6a15))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **services**: Add HealthTracker — absorbs health.py into service class
  ([`221f061`](https://github.com/giraffe-horizon/deal-hunter/commit/221f061d3a6c50ea644a921369e262ee6f2ea811))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **services**: Add PriceTracker — price change detection with typed results
  ([`d4fed39`](https://github.com/giraffe-horizon/deal-hunter/commit/d4fed39048d56724cb3203c8f45900eea06834d9))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **services**: Add ProfileManager — unified profile loading for CLI + dashboard
  ([`1c0ca55`](https://github.com/giraffe-horizon/deal-hunter/commit/1c0ca551d171df33e67a84168a542c873f218940))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **services**: Add ScoringService — scoring orchestration + category detection
  ([`63a35fd`](https://github.com/giraffe-horizon/deal-hunter/commit/63a35fd46033020e537924b7084a3d3ede3c4651))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **services**: Add shared typed dataclasses for service layer
  ([`03aa30d`](https://github.com/giraffe-horizon/deal-hunter/commit/03aa30d867ae960832e2e0e3e947dc7e964a6bb5))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Refactoring

- Remove backward-compat wrappers from deal_hunter.py
  ([`2a44e3a`](https://github.com/giraffe-horizon/deal-hunter/commit/2a44e3a014f5a2092b9fde45cafbe05183260539))

Tests now import directly from service classes (PriceTracker, DealFetcher) instead of thin wrappers
  in deal_hunter.py.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Slim deal_hunter.py to CLI entrypoint using service layer
  ([`e396e6e`](https://github.com/giraffe-horizon/deal-hunter/commit/e396e6e4a61788ad0f01df7a4e0f2a0aa7d1d155))

Replace inline business logic with service delegation: - ProfileManager for load/list/validate -
  DealFetcher for fetch_all/deduplicate - ScoringService for get_filter/score_deals/detect_category
  - PriceTracker for check_price_change - AlertService for
  flush_queued/send_deal_alerts/send_price_drop_alerts - HealthTracker for health tracking and
  watchdog

Keep backward-compat wrappers (check_price_changes, get_price_tracking_config, deduplicate,
  _normalize_title) so existing consumers continue to work. Update test imports to point to
  canonical service locations where patch targets changed (quiet_hours -> services.alerter, verbose
  -> cli.verify).

deal_hunter.py: 1005 -> 689 lines (-31%). All 674 tests pass.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Tighten mypy config with pydantic plugin and stricter checks
  ([`d27ab40`](https://github.com/giraffe-horizon/deal-hunter/commit/d27ab4079446de956eb2ddfe4ef0f20bea7ee889))

Enable warn_redundant_casts, warn_unused_ignores, check_untyped_defs. Add pydantic.mypy plugin. Fix
  type errors in service layer. Make AlertService.alert_repo optional for source-failure-only usage.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **dashboard**: Add return type annotations to all route handlers
  ([`02bb2e6`](https://github.com/giraffe-horizon/deal-hunter/commit/02bb2e62e335e6d52cf2737b8f5fb705431befba))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **dashboard**: Convert services.py to services package
  ([`de9be64`](https://github.com/giraffe-horizon/deal-hunter/commit/de9be647a745d457e2fff5f4ee222f40807bbb75))

Split dashboard/services.py into a dashboard/services/ package with deal_service.py containing the
  DealService class. The __init__.py re-exports all public symbols so existing imports remain
  unchanged.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **dashboard**: Extract ProfileService from profile routes
  ([`92d9a94`](https://github.com/giraffe-horizon/deal-hunter/commit/92d9a94e3596a685c8c7d4274d5fcee89a3f2e9a))

Move YAML loading/validation/saving, profile summary building, toggle, and subprocess verify-run
  into a reusable ProfileService class, reducing duplication across 7 route handlers.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **dashboard**: Extract TunerService from tuner routes
  ([`dcc0b6a`](https://github.com/giraffe-horizon/deal-hunter/commit/dcc0b6a03aa3c49b70e627a153df56324f0366ce))

Move scoring simulation (merge overrides, fetch deals, re-score, format results) and rule
  persistence logic into TunerService. Route handlers now parse request data and delegate to the
  service, keeping them under 15 lines each.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **dashboard**: Move deals page logic to DealService
  ([`3c6b35e`](https://github.com/giraffe-horizon/deal-hunter/commit/3c6b35e6285f935fee0f487afc452c153c6d5587))

Extract filtering, pagination, stats computation, and price drops view logic from route handlers
  into DealService methods. Handlers now delegate to get_deals_page(), get_price_drops(), and
  get_stats(), keeping them under ~20 lines focused on request parsing and template rendering.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **dashboard**: Switch dependencies to ProfileManager
  ([`b0c8b70`](https://github.com/giraffe-horizon/deal-hunter/commit/b0c8b7047178feca9d88b9ec9263a7a07b88d298))

- **frontend**: Extract price chart JS to static file
  ([`08e8261`](https://github.com/giraffe-horizon/deal-hunter/commit/08e8261899281d70d9ee34d58f1ae425f826be2d))

Move the inline Chart.js price-history init script from deal_detail.html into
  dashboard/static/js/price-chart.js. The deal ID is passed via a data-deal-id attribute on the
  canvas element instead of Jinja interpolation.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **frontend**: Extract sparkline init to static JS file
  ([`92fdcdf`](https://github.com/giraffe-horizon/deal-hunter/commit/92fdcdf2585d69c072060bcb7e3a07679cc22261))

Deduplicate the identical .sparkline-canvas init loop that appeared in both deals_table.html and
  watchlist.html. Move it to sparklines.js, which also listens for htmx:afterSwap so HTMX-paginated
  deal rows get sparklines without needing an inline script in the partial. Load charts.js +
  sparklines.js from the parent full-page templates (deals.html, watchlist.html) instead.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **templates**: Add macros to reduce template duplication
  ([`15d193f`](https://github.com/giraffe-horizon/deal-hunter/commit/15d193f1bccd0bde92bd67f334bb4e8f11e38b71))

Add score_rules_list macro to macros.html and use it in profile_tab_overview.html to replace the
  identical score_rules and penalties display blocks (each was 8 lines of the same pattern). Macro
  is also available for future templates that display keyword→points rules in read-only view.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.13.0 (2026-04-13)

### Bug Fixes

- Add type annotations to satisfy mypy disallow_untyped_defs
  ([`cb99b58`](https://github.com/giraffe-horizon/deal-hunter/commit/cb99b58033f974ccf69032c7f9834cf6c3d87166))

Add missing type annotations for Deal parameters, BS4 elements, SQLAlchemy session/event args, and
  repository internals. All 23 mypy errors resolved.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Resolve all ruff lint violations (RET505, SIM105, SIM117, PTH123, PTH108/110/118/120, E501)
  ([`7ac3746`](https://github.com/giraffe-horizon/deal-hunter/commit/7ac3746922b4fa27b5412f0646b83ed099a95037))

- RET505: remove unnecessary else after return (auto-fixed) - SIM117: merge nested with statements
  into multi-context with - SIM105: replace try/except/pass with contextlib.suppress - PTH123:
  replace builtin open() with Path.open() - PTH108/110/118/120: replace os.path/os.unlink with
  pathlib in tests - E501: break long lines (strings, f-strings, SQL queries, docstrings)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Update pre-commit ruff hook to v0.15.9 to match local version
  ([`e13fecc`](https://github.com/giraffe-horizon/deal-hunter/commit/e13fecc3ee19d57296efd4d57ed77ad09a7d191f))

The previous v0.11.6 still enforced removed rule UP038, causing false positives on isinstance()
  calls in utils/validation.py.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **storage**: Address review — DESC index, batch mode, dir creation, template modernization
  ([`4cdb13f`](https://github.com/giraffe-horizon/deal-hunter/commit/4cdb13fd62ca93320a54fa781a17d68f5fe41c05))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **storage**: Move cutoff filter outside CTE in count_drops to match get_drops semantics
  ([`af3add9`](https://github.com/giraffe-horizon/deal-hunter/commit/af3add96c4ccd866e5d8ffaa6d5d217500aadbc0))

The cutoff inside the CTE caused LAG() to lose visibility of pre-window prices, undercounting drops
  where the previous price predates the window.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **storage**: Remove unused topic_id parameter from AlertQueueRepository.queue
  ([`d754d79`](https://github.com/giraffe-horizon/deal-hunter/commit/d754d790a3a13a3e1631ac67fa749c38e1cce393))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Chores

- Add sqlalchemy and alembic dependencies for Phase 2
  ([`0af2262`](https://github.com/giraffe-horizon/deal-hunter/commit/0af22620dee9ba24f057428a3bc75717d940588e))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Delete storage/sqlite.py — all consumers migrated to repositories
  ([`2c457f5`](https://github.com/giraffe-horizon/deal-hunter/commit/2c457f5a704d42406698ea339d81e7c4e9534437))

Removes the 690-line raw-SQL monolith and the one-time JSON-to-SQLite migration script now that
  every caller uses SQLAlchemy repositories. Also removes the backward-compat re-export from
  storage/__init__.py.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- Enable mypy disallow_untyped_defs for core modules
  ([`c8f8b56`](https://github.com/giraffe-horizon/deal-hunter/commit/c8f8b56266cd8c18521ee9da4b816e0e23b567cf))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- Tighten ruff lint rules — add RET, SIM, PTH; enforce line-length
  ([`a0bb9a7`](https://github.com/giraffe-horizon/deal-hunter/commit/a0bb9a747d9b81c2e15d2908487686bcd6147cf4))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Update stale references to deleted storage/sqlite.py
  ([`dc41aba`](https://github.com/giraffe-horizon/deal-hunter/commit/dc41abac6fd2db9a4a80c004516aa7877ebcb227))

Update CLAUDE.md architecture section, feedback bot docs, and test listing to reflect the new
  SQLAlchemy ORM layer. Fix stale docstring in charts.py.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Documentation

- Add comprehensive refactoring & cleanup design spec
  ([`f6d5c6b`](https://github.com/giraffe-horizon/deal-hunter/commit/f6d5c6bbffb112240c3550d14a27933b8361de77))

Six-phase bottom-up refactoring plan covering SQLAlchemy ORM migration, service layer extraction,
  dashboard cleanup, template DRY, and type safety.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Add Phase 1 implementation plan (tooling, formatting, env)
  ([`57e59b4`](https://github.com/giraffe-horizon/deal-hunter/commit/57e59b4f2b22d4ba203d5a3197b149cf52bd860f))

10 tasks covering: Ruff config tightening, lint violation fixes (42 errors), Mypy strictness,
  pre-commit hook, env var configuration, and Phase 2 deps.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Add Phase 2 implementation plan — SQLAlchemy ORM migration
  ([`6d399f3`](https://github.com/giraffe-horizon/deal-hunter/commit/6d399f3ae67beba9e3d5995eec15a1ec1dfe8845))

17 tasks covering: ORM models, session management, Alembic setup, 6 repository classes (Deal, Price,
  Watchlist, AlertQueue, Feedback, SeenDeal), N+1 query fixes via window functions, dashboard/route
  migration, deal_hunter.py state consolidation, feedback bot migration, test suite rewrite, and
  retirement of storage/sqlite.py.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Fix spec self-review issues (counts, ordering, scope gaps)
  ([`089d0a2`](https://github.com/giraffe-horizon/deal-hunter/commit/089d0a21e4f2a870f158c524a72d6f5096822ecf))

- Fix model count: 5 existing + 1 new, not 6 - Move services/types.py to Phase 3 (services depend on
  these types) - Remove duplicate return-type item from Phase 6 (already in Phase 4e) - Fix
  get_session() usage to use context manager - Expand stub repository signatures with key methods -
  Add feedback_bot.py and visualization/charts.py to Phase 2 scope - Renumber Phase 6 sections after
  removing duplicates

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Features

- Add JSON state migration script for seen_deals consolidation
  ([`a7a4589`](https://github.com/giraffe-horizon/deal-hunter/commit/a7a45896b21827a1f40b2f785d6ac885a668618f))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- Make DEALS_PER_PAGE and SCORE_THRESHOLD configurable via env vars
  ([`e55a32a`](https://github.com/giraffe-horizon/deal-hunter/commit/e55a32ae6148921ff72bdb84bfbeb813df3473db))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **storage**: Add Alembic migrations — baseline schema + seen_deals table
  ([`c68d57f`](https://github.com/giraffe-horizon/deal-hunter/commit/c68d57f28d8582497f60f0df7472b2570796fb51))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **storage**: Add AlertQueueRepository and FeedbackRepository
  ([`728f59d`](https://github.com/giraffe-horizon/deal-hunter/commit/728f59d4b1c582cb867ea8a1f0c5689ade0bd11f))

Implements queue/get_pending/mark_sent for alert_queue table and record/get_stats for feedback
  table, with 8 new tests (54 total passing).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **storage**: Add DealRepository with upsert, query, stats, and status
  ([`1f6c2cd`](https://github.com/giraffe-horizon/deal-hunter/commit/1f6c2cd3a3ca17ab1273b6294b6f739b33214a09))

Implements Task 4 of the SQLAlchemy ORM migration. DealRepository wraps all deal-related queries
  with upsert (preserves status on update), price history recording, filtered queries, pagination,
  stats, and status management. Covered by 21 tests following TDD.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **storage**: Add PriceRepository with N+1-free get_drops using window functions
  ([`e8a80d1`](https://github.com/giraffe-horizon/deal-hunter/commit/e8a80d1f3775a73257261e3d8ad37ed0aebdf9b2))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **storage**: Add SeenDealRepository — replaces JSON state file tracking
  ([`06f034f`](https://github.com/giraffe-horizon/deal-hunter/commit/06f034f2744229b6c3ac854c78b6a6e4fec806f0))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **storage**: Add SQLAlchemy ORM models for all 6 tables
  ([`9a33dee`](https://github.com/giraffe-horizon/deal-hunter/commit/9a33dee5f3fe8178d60bdaf656089774aa3646ee))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **storage**: Add SQLAlchemy session management with auto commit/rollback
  ([`8a74ce6`](https://github.com/giraffe-horizon/deal-hunter/commit/8a74ce660fa48f0b323cfe591d3dabba039e14dd))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **storage**: Add WatchlistRepository with CRUD and trigger checking
  ([`41351a1`](https://github.com/giraffe-horizon/deal-hunter/commit/41351a161a0d23b3c1abc4b9c8517c3067dfdd5c))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

### Performance Improvements

- Use count_drops() instead of materializing full get_drops()
  ([`30e27b2`](https://github.com/giraffe-horizon/deal-hunter/commit/30e27b296e66986707a1952b254d6f9a65383f48))

The deals page was calling get_drops(days=7) and taking len() just to get a count, materializing all
  drop rows with deal joins. count_drops() uses SELECT COUNT(*) with the same CTE — much cheaper.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Refactoring

- Migrate charts.py to session + repositories, fix N+1 in trend_chart
  ([`a8270da`](https://github.com/giraffe-horizon/deal-hunter/commit/a8270dab9debda3bb0fa90bcffe64eb9509b08fa))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- Migrate deal_hunter.py from SQLiteStorage + JSON state to repositories
  ([`1396a60`](https://github.com/giraffe-horizon/deal-hunter/commit/1396a602d0914039b1ea61ca254d52b3212eda7b))

Replace SQLiteStorage direct usage with repository pattern (DealRepository, PriceRepository,
  WatchlistRepository, AlertQueueRepository, SeenDealRepository). Delete
  load_state/save_state/STATE_TTL_DAYS — seen-deal tracking now uses SeenDealRepository backed by
  SQLite instead of per-profile JSON files.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Migrate feedback_bot.py from SQLiteStorage to repositories
  ([`977219b`](https://github.com/giraffe-horizon/deal-hunter/commit/977219bda881bc6fc5cab8924509844f99416126))

Replace SQLiteStorage with get_session() + DealRepository, FeedbackRepository, and
  WatchlistRepository. Remove DB_PATH and get_storage() helper.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **dashboard**: Migrate all routes from SQLiteStorage to repositories
  ([`4de4ed2`](https://github.com/giraffe-horizon/deal-hunter/commit/4de4ed22e75471f6d83c467739c3ee16950994d6))

Replace SQLiteStorage dependency injection in all dashboard routes with SQLAlchemy Session +
  DealRepository/PriceRepository/WatchlistRepository calls. DealService updated to accept Session
  directly.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **dashboard**: Switch get_db() from SQLiteStorage to SQLAlchemy session
  ([`007d904`](https://github.com/giraffe-horizon/deal-hunter/commit/007d904ee8846b1127ce75384b1b07d9b79fe668))

Wire up storage/__init__.py to re-export ORM models, repositories, and session helpers alongside the
  legacy SQLiteStorage. Update get_db() in dashboard/dependencies.py to yield a SQLAlchemy Session
  via get_session().

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

### Testing

- Expand ORM model tests — cover all 6 models, relationships, and indexes
  ([`b7772a6`](https://github.com/giraffe-horizon/deal-hunter/commit/b7772a600639e36b44ddc47378cc74310a3c99a0))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- Migrate all test fixtures from SQLiteStorage to SQLAlchemy sessions
  ([`b7c6b31`](https://github.com/giraffe-horizon/deal-hunter/commit/b7c6b314180260188adcc1349a7d27398150bb28))

Replace SQLiteStorage with SQLAlchemy engine/session/repository fixtures across all test files.
  Delete obsolete test_sqlite_storage.py, test_batch_queries.py, and test_state.py (replaced by
  test_repositories.py).

Also fixes two bugs found during migration: - storage/repositories.py: flush before raw SQL in
  _record_price() to satisfy FK constraints - dashboard/routes/profiles.py: tuner tab now uses
  injected session via Depends(get_db) instead of bypassing dependency injection

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.12.2 (2026-04-13)

### Bug Fixes

- **ci**: Grant write permissions for Claude code review workflows
  ([`29c87ef`](https://github.com/giraffe-horizon/deal-hunter/commit/29c87efe4ed5218a485f3fc9cf8fe51ba938558e))

The claude-review and claude workflows had pull-requests: read which prevented them from posting
  review comments. Changed to write.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Documentation

- **spec**: Add products-and-offers design for dashboard pivot
  ([`2599f31`](https://github.com/giraffe-horizon/deal-hunter/commit/2599f3149068f8af1393907575eadec74645eb1f))

Design doc for evolving deal-hunter from per-Deal feed to per-Product dashboard with cross-source
  price history and offer pinning. Covers domain model, data schema, conservative layered matching
  strategy (L1 hard IDs → L2 strong → L3 review → L4 new product), NBP FX conversion, migration plan
  (strangler with feature flag), implementation phases A-G, test/validation strategy, and decisions
  captured during brainstorming.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **spec**: Translate products-and-offers design to English
  ([`e64d2d1`](https://github.com/giraffe-horizon/deal-hunter/commit/e64d2d140f156e66e91c8709a8a27fee0b148328))

Same content, English wording — project convention is English for all code and docs (Telegram output
  stays Polish).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.12.1 (2026-04-07)

### Bug Fixes

- **storage**: Preserve deal status on upsert — stop resetting to active
  ([`71ff75e`](https://github.com/giraffe-horizon/deal-hunter/commit/71ff75e707c05365e6a593d769bc8618b05d3039))

upsert_deal() was always setting status='active' when updating existing deals, so every cron run
  would overwrite user-set watching/rejected statuses back to active.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.12.0 (2026-04-07)

### Features

- **dashboard**: Phase 1 — HTMX loading indicator, pagination, inline actions
  ([`8b1d30a`](https://github.com/giraffe-horizon/deal-hunter/commit/8b1d30aec908010c3ad22f9a8a08a0d94e70f739))

- Add global progress bar that appears during any HTMX request - Convert pagination links to HTMX
  (no full page reload, URL stays in sync) - Add inline Watch/Skip icon buttons in deals table rows
  - New partial: deal_row_status.html for compact inline status feedback

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **dashboard**: Phase 2 — score breakdown, sparklines, filter URL sync
  ([`2535d5f`](https://github.com/giraffe-horizon/deal-hunter/commit/2535d5f6a360ef5617ccdf60770075caa4b32bf1))

- Show score breakdown card on deal detail page (why this score?) - Add price sparklines in deals
  table via batch SQLite query - Sync filter state to browser URL (bookmarkable/shareable filtered
  views) - Convert Clear Filters to HTMX (no full page reload)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **dashboard**: Phase 3 — unified profile page with HTMX tabs
  ([`c8c28cb`](https://github.com/giraffe-horizon/deal-hunter/commit/c8c28cb2add09b9aae84da3d219fbfcd285008f8))

Consolidate 4 separate profile pages (detail, edit, YAML, tuner) into a single tabbed interface.
  Remove Scoring Tuner from sidebar nav. Old URLs redirect with 302 for backwards compatibility.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **dashboard**: Phase 4 — watchlist inline price edit + sparklines
  ([`8a1106b`](https://github.com/giraffe-horizon/deal-hunter/commit/8a1106b9edaa7f38c3cdc789fd0ee0ae8fab7068))

Add editable target price input (auto-saves on change via HTMX PATCH), sparkline trend column, and
  row partial for seamless updates.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **dashboard**: Phase 5 — merge Price Trends into Deals Explorer
  ([`cbbba39`](https://github.com/giraffe-horizon/deal-hunter/commit/cbbba397d9daa07ed46dd5f66fdd3f71bf97da93))

Add view toggle (All Deals / Price Drops) to deals page. Old /price-trends URL redirects to
  /deals?view=drops. Remove Price Trends from sidebar nav (now 3 primary links + health).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **dashboard**: Phase 5b — health status indicator in sidebar footer
  ([`d0a2017`](https://github.com/giraffe-horizon/deal-hunter/commit/d0a2017954d7f238070d9ff7566dbbfee97bf27b))

Replace System Health nav link with a compact status indicator in the sidebar footer. The /health
  page remains accessible via the indicator. Status is loaded via HTMX on page load.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.11.2 (2026-04-07)

### Bug Fixes

- **ci**: Exclude E2E tests from CI — they require playwright browser
  ([`4aa0e03`](https://github.com/giraffe-horizon/deal-hunter/commit/4aa0e037e524ba0ea424d032e102cb2767ce719d))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Testing

- Add 70 E2E browser tests covering all dashboard pages and features
  ([`5b682e6`](https://github.com/giraffe-horizon/deal-hunter/commit/5b682e6ae3a972cf63766933cd4b7282bffb73b5))

- Add pytest-playwright E2E infrastructure with live server fixture (uvicorn subprocess) - 12 test
  modules: page loads, deals, deal detail, compare, watchlist, health, price trends, profiles CRUD,
  tuner, sidebar, CSRF protection - Make dashboard dependencies (DB_PATH, PROFILES_DIR) overridable
  via env vars for test isolation — safe_load_profile/get_profiles now read YAML directly instead of
  delegating to deal_hunter.py - Make health.py state dir overridable via DEAL_HUNTER_STATE_DIR env
  var - Register e2e pytest marker and add pytest-playwright optional dependency - Update unit tests
  to match new dependencies.py implementation

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.11.1 (2026-04-07)

### Bug Fixes

- Remove stale COPY dashboard.py from Dockerfile (now dashboard/__init__.py)
  ([`f43f4f0`](https://github.com/giraffe-horizon/deal-hunter/commit/f43f4f0a5e03b33115ffdf2d751a0131669986be))


## v0.11.0 (2026-04-07)

### Bug Fixes

- Update TemplateResponse calls to Starlette 1.0 signature (request, name, context)
  ([`7a17a3e`](https://github.com/giraffe-horizon/deal-hunter/commit/7a17a3e256f783f5f42f7221074cf320967a9e08))

- **security**: Add CSRF protection middleware to dashboard
  ([`6527f63`](https://github.com/giraffe-horizon/deal-hunter/commit/6527f63dc0ab249ab27d6f70e4f7831d93d6bb94))

Require HX-Request or X-Requested-With header on all mutating requests (POST/PUT/DELETE/PATCH) to
  prevent cross-site request forgery. HTMX sends HX-Request automatically; vanilla fetch() calls in
  templates now include X-Requested-With. Test client auto-injects CSRF headers via a wrapper, with
  raw_client available for explicit CSRF tests.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **security**: Add path traversal protection to all profile endpoints
  ([`c54c314`](https://github.com/giraffe-horizon/deal-hunter/commit/c54c314ea64f226bf6c76b1ea6b3d3c2655e2d24))

Add centralized safe_profile_path() validator that rejects profile names not matching
  ^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$ and verifies resolved path stays within the profiles directory.
  Applied to all 11 profile endpoints.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **security**: Enable explicit Jinja2 autoescape
  ([`cb0131d`](https://github.com/giraffe-horizon/deal-hunter/commit/cb0131d3b2a355c003d71267094028cb0c2d0a1b))

### Chores

- Add .worktrees to gitignore for isolated workspaces
  ([`ed7e06f`](https://github.com/giraffe-horizon/deal-hunter/commit/ed7e06f5158e2c5e992bb8f2fa48242caff4800b))

- Add Docker HEALTHCHECK instruction
  ([`d067dbd`](https://github.com/giraffe-horizon/deal-hunter/commit/d067dbdcaac3b057fb750744793c9063886bd4d8))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Add pre-commit hooks for ruff format and lint
  ([`13afc80`](https://github.com/giraffe-horizon/deal-hunter/commit/13afc80e6170231d436be28a184300d7a531ac13))

- Dead code cleanup — remove unused import, fix re-export lint warnings
  ([`b4201c9`](https://github.com/giraffe-horizon/deal-hunter/commit/b4201c902cb11fee04dbf87c1df4c50d839ffeca))

Remove unused HTMLResponse import from dashboard/routes/health.py and convert implicit re-exports in
  dashboard/__init__.py to explicit form (PEP 484 compliant) to satisfy ruff F401 checks.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Tighten dependency pinning, expand ruff/mypy config, update gitignore
  ([`7765c4e`](https://github.com/giraffe-horizon/deal-hunter/commit/7765c4ee002b454f6cde5eb8cd3fe1b83486a9ec))

Pin minimum dependency versions, add security/complexity/bugbear ruff rules (S, C90, B, A),
  strengthen mypy with per-module overrides instead of global ignore_missing_imports, and add cache
  directories to gitignore.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Code Style

- Apply ruff format to modified files
  ([`aed43ae`](https://github.com/giraffe-horizon/deal-hunter/commit/aed43aeea6400177848a8bcbebae5e2eff1f2ea9))

### Documentation

- Add refactoring spec and implementation plan
  ([`a94fd93`](https://github.com/giraffe-horizon/deal-hunter/commit/a94fd93053e40db23df95006ddf4abba8b4b06bc))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Features

- Add batch price history and lowest price query methods to SQLiteStorage
  ([`b3d6429`](https://github.com/giraffe-horizon/deal-hunter/commit/b3d6429d11dad2ae0fd2a8e8acba990f84e88f0c))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Add environment variable validation on startup
  ([`7f48d61`](https://github.com/giraffe-horizon/deal-hunter/commit/7f48d61bd28cde8a248e57dfa687b69a8cc67651))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Performance Improvements

- Fix N+1 query in compare_deals using batch methods
  ([`639de6c`](https://github.com/giraffe-horizon/deal-hunter/commit/639de6cbec067469e7d66b923cf5e4d5808a7e7b))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Refactoring

- Extract dashboard business logic into DealService
  ([`42a6e1f`](https://github.com/giraffe-horizon/deal-hunter/commit/42a6e1fe0fef16b4e443071b5ae6269a443317f7))

Move comparison data fetching and deal scoring logic from dashboard.py route handlers into a
  dedicated DealService class in dashboard_services.py, separating business logic from HTTP routing
  concerns.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Fix async/sync inconsistency in dashboard routes
  ([`89783dc`](https://github.com/giraffe-horizon/deal-hunter/commit/89783dc32e17ce5f7800b82bdf31f97b2bb86b74))

Convert 14 route handlers from async def to def where they never use await. FastAPI correctly runs
  sync functions in a threadpool, which is appropriate for synchronous I/O like SQLite queries and
  file reads. Only handlers that actually await (request.form(), request.json(), request.body(),
  middleware call_next) remain async.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Replace try/finally DB pattern in feedback_bot with context manager
  ([`6a135ba`](https://github.com/giraffe-horizon/deal-hunter/commit/6a135bab49d8c413f4568a4605c4c1f2cd672eaf))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Split dashboard.py into route modules with APIRouter
  ([`b97c799`](https://github.com/giraffe-horizon/deal-hunter/commit/b97c79999bb18de806839a2596264615f3e00dba))

Convert monolithic dashboard.py into a proper Python package with route modules (deals, profiles,
  watchlist, tuner, health), shared dependencies, and the service layer moved into the package.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **frontend**: Create Jinja2 macro library, apply to all templates
  ([`d60771c`](https://github.com/giraffe-horizon/deal-hunter/commit/d60771cbb5555ffde14401e6998a31e078529562))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **frontend**: Create static dir, extract sidebar JS from base.html
  ([`0563402`](https://github.com/giraffe-horizon/deal-hunter/commit/0563402439c24be6f52c5c9be7548d840fc32f8a))

Move inline toggleSidebar() script to dashboard/static/js/sidebar.js and mount static files via
  Starlette StaticFiles in dashboard.py.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **frontend**: Extract Chart.js helpers to shared static file
  ([`98dc341`](https://github.com/giraffe-horizon/deal-hunter/commit/98dc3416975f8d7f280aab7b3deb38b5fdc94d38))

Move inline Chart.js configuration from three templates into dashboard/static/js/charts.js with
  reusable createPriceChart, createSparkline, and createTrendSparkline functions.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **frontend**: Extract compare bar JS to static file
  ([`e346b91`](https://github.com/giraffe-horizon/deal-hunter/commit/e346b910069f13d3a12e1c8833b0b8121279e223))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **frontend**: Extract tuner and profile form JS to static files
  ([`e209c94`](https://github.com/giraffe-horizon/deal-hunter/commit/e209c94f27ef10bea3c7791ee45bc7601bc75933))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **frontend**: Move inline HTML from api_update_deal_status to partial template
  ([`d17bff2`](https://github.com/giraffe-horizon/deal-hunter/commit/d17bff2a6aa2da01eacaf1d6b0ca39303a65ee63))

Extract the inline HTML string construction for deal action buttons into a Jinja2 partial template
  (partials/deal_action_buttons.html), replacing f-string HTML generation with TemplateResponse
  rendering.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Testing

- Add 21 missing tests for comparator and scoring tuner
  ([`44b50c0`](https://github.com/giraffe-horizon/deal-hunter/commit/44b50c0ff59742f8ca7d576c56effadfa8532651))

Unit tests: - _score_deals_with_profile: empty input, rule application, sort order, rejected deals,
  None price handling

E2E tests (comparator): - Compare with real deals (renders titles, prices) - Best price and highest
  score highlighting - Sparkline canvases present - Share link present - Max 5 deal limit enforced -
  Empty state and nonexistent IDs graceful

E2E tests (tuner): - Tuner loads with real profile - Simulate API returns score diffs for seeded
  deals - Simulate with different rules produces different scores - Save API writes rules to YAML
  and validates - Save API rejects invalid budget (min > max)

Workflow tests: - Browse deals then compare specific ones - Simulate then save (full tuner workflow)
  - Sidebar has tuner link on all pages

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.10.0 (2026-04-06)

### Chores

- Docs update for Wave 4 — mark A.1 + C.2 as Done, complete Roadmap v2
  ([`c3adc97`](https://github.com/giraffe-horizon/deal-hunter/commit/c3adc97be9a68f237c095f78bf87b76070b41448))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Features

- Add deal comparator with side-by-side view and sparklines
  ([`271c5e9`](https://github.com/giraffe-horizon/deal-hunter/commit/271c5e9ede1698dff476375ee9f8a89ca931df94))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- Add deal comparison checkboxes and floating compare bar
  ([`209b836`](https://github.com/giraffe-horizon/deal-hunter/commit/209b83674e3cdf8139775853a115d99b7eba676e))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- Add scoring tuner with live simulation and profile save
  ([`ebcec32`](https://github.com/giraffe-horizon/deal-hunter/commit/ebcec32de762e70c7dc44073da209d3938934d2f))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.9.0 (2026-04-06)

### Chores

- Lint fixes + docs update for Wave 3 (C.4 Profile Management)
  ([`08827bc`](https://github.com/giraffe-horizon/deal-hunter/commit/08827bc5664fadf6738d0444fefb46050f156a4d))

Fix ruff lint/format issues. Update CLAUDE.md with profile CRUD in dashboard description. Mark C.4
  as done in ROADMAP-v2.md.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Features

- **profiles**: Add delete, toggle, and manual run
  ([`ad82939`](https://github.com/giraffe-horizon/deal-hunter/commit/ad8293988bbcf5c5e00234e06eb1c238de1af4b2))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **profiles**: Add form-based profile editor with update API
  ([`1306529`](https://github.com/giraffe-horizon/deal-hunter/commit/1306529e7ec8d3c79d93498c844155dd9371f291))

Adds GET /profiles/{name}/edit page with form sections for Basic, Scoring (dynamic rules/penalties),
  Filters, and Telegram config. Adds PUT /api/profiles/{name} that validates and writes YAML,
  preserving sources and advanced fields not exposed in the form.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **profiles**: Add profile create page and API
  ([`3091455`](https://github.com/giraffe-horizon/deal-hunter/commit/30914556709cd76fa449cd9f5dd3f273179c9707))

- Add GET /profiles/new page (before /{name} to avoid route conflict) - Add POST /api/profiles
  endpoint with validation and YAML persistence - Add profile_create.html template with sources,
  scoring, and Telegram sections - Use safe DOM methods (no innerHTML) for error display - Add 2 new
  tests in TestProfilePages (create page + API)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **profiles**: Add profile list page and sidebar nav
  ([`12104fa`](https://github.com/giraffe-horizon/deal-hunter/commit/12104fad8b5a3bf443883100e87a504849c0ddfc))

Adds GET /profiles HTML page and GET /api/profiles JSON endpoint, inserts Profiles link into the
  sidebar between Watchlist and System Health, and covers both with three new TestProfilePages
  tests.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **profiles**: Add raw YAML editor with CodeMirror
  ([`e011a1c`](https://github.com/giraffe-horizon/deal-hunter/commit/e011a1c79bdcd416b81deccbfd472c91ccc47d03))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **profiles**: Add read-only profile detail page
  ([`3169cd9`](https://github.com/giraffe-horizon/deal-hunter/commit/3169cd9b26dc58b2d106f9f51507291d3042a8fb))

Adds GET /profiles/{name} route with a Jinja2 template showing Basic Info, Scoring rules/penalties,
  Sources, and Filters & Telegram sections. Returns 404 via HTTPException for unknown profiles.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.8.0 (2026-04-06)

### Chores

- Lint fixes + docs update for Wave 2 (A.2, C.1)
  ([`3fad777`](https://github.com/giraffe-horizon/deal-hunter/commit/3fad7779a4db7ed0b0c082c170f62c3578cd1b9e))

Fix ruff lint/format issues across Wave 2 files. Update CLAUDE.md with cross-source dedup,
  watchlist, /target command. Mark A.2, C.1 as done in ROADMAP-v2.md. Add Wave 2 implementation
  plan.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Features

- **dedup**: Add alt_links field to Deal dataclass
  ([`56e65f0`](https://github.com/giraffe-horizon/deal-hunter/commit/56e65f0c910c72ab9aef3b701b2444ed11cbfeb6))

Adds alt_links: list[dict] = field(default_factory=list) to the Deal dataclass to support
  cross-source deduplication (same product from multiple sources). Includes two new tests verifying
  default empty list and populated alt_links.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **dedup**: Add dashboard alt_links display and dedup validation
  ([`8409297`](https://github.com/giraffe-horizon/deal-hunter/commit/84092978476f69f9856eef0b30162c9507d542ed))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **dedup**: Render alt_links in Telegram alerts
  ([`bed0f48`](https://github.com/giraffe-horizon/deal-hunter/commit/bed0f48b40a862739b8863b503203f170678a807))

Add cross-source alt_links section to send_alert() and send_price_drop_alert() so users see
  alternate sources for the same product in Telegram messages.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **dedup**: Rewrite deduplicate() to merge cross-source duplicates
  ([`4ad5763`](https://github.com/giraffe-horizon/deal-hunter/commit/4ad5763941d3180b8d6f2aa1e2eac069f4d44506))

Instead of dropping duplicates, the winner keeps its position and gains alt_links entries from
  merged sources. Supports configurable price tolerance (default 5%) and title similarity (default
  0.85 via SequenceMatcher). Zero-price deals are never merged. Dedup can be disabled per-profile
  via `dedup: {enabled: false}` in YAML.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **watchlist**: Add /target command to feedback bot
  ([`849c39c`](https://github.com/giraffe-horizon/deal-hunter/commit/849c39c2ea2f3656036199975293c45d41e9d922))

Adds /target <deal_id> <price> command that sets a price target on a deal via add_to_watchlist().
  Includes two new tests covering the happy path and missing-args validation.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **watchlist**: Add dashboard page, routes, and sidebar nav
  ([`9b4e732`](https://github.com/giraffe-horizon/deal-hunter/commit/9b4e732f9bed77ab639cf41d96c66b1ad9751013))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **watchlist**: Add SQLite schema and CRUD methods
  ([`2f0b62e`](https://github.com/giraffe-horizon/deal-hunter/commit/2f0b62e75126327ace075d947d946512c6741152))

Add watchlist table to SCHEMA_SQL and implement add_to_watchlist, remove_from_watchlist,
  get_watchlist, check_watchlist_triggers, and mark_watchlist_triggered methods with full test
  coverage (11 tests).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **watchlist**: Add Telegram alert and run integration
  ([`8381a9d`](https://github.com/giraffe-horizon/deal-hunter/commit/8381a9d8d15454b63ab577e9458a2f9df116a752))

Add send_watchlist_alert() to TelegramNotifier with Polish-language CEL CENOWY message, and wire
  check_watchlist_triggers/mark_watchlist_triggered into the _run_normal() flow immediately after
  db.upsert_deal().

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.7.0 (2026-04-06)

### Chores

- Lint fixes + docs update for Wave 1 (A.3, B.1, B.2)
  ([`2e2590b`](https://github.com/giraffe-horizon/deal-hunter/commit/2e2590b08fdee3bc68b4bdc8354df321b7a280ad))

Fix ruff lint/format issues across Wave 1 files. Update CLAUDE.md with quiet hours, RSS source,
  x-kom/morele docs. Mark A.3, B.1, B.2 as done in ROADMAP-v2.md.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Documentation

- Add Roadmap v2.0 design spec
  ([`3aa5fd7`](https://github.com/giraffe-horizon/deal-hunter/commit/3aa5fd72a636835b0c9b142279d93aa65a6de379))

Complete design specification for 8 features across 4 waves: A.3 Quiet Hours, B.1 x-kom/Morele, B.2
  Allegro RSS, A.2 Dedup, C.1 Watchlist, C.4 Profile Management, A.1 Scoring Tuner, C.2 Comparator.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Add Wave 1 implementation plan (quiet hours + new sources)
  ([`38d0e4d`](https://github.com/giraffe-horizon/deal-hunter/commit/38d0e4d9947c1f3320ad5201faa6e31b8b130759))

Detailed task-by-task plan for A.3 Quiet Hours, B.1 x-kom/Morele stores, and B.2 Allegro RSS source.
  8 tasks with TDD steps.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Features

- Add morele.net YAML store definition
  ([`e08cced`](https://github.com/giraffe-horizon/deal-hunter/commit/e08cced8618a4d5a8f3ce93174135efc7de51441))

Selectors verified against live morele.net response (CSS-rendered HTML, no Cloudflare blocking).
  Includes HTML fixture with 3 products and 11 tests covering registration, parsing, prices, links,
  IDs, and images.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Add RSS/Atom feed source for Allegro and generic RSS
  ([`4602812`](https://github.com/giraffe-horizon/deal-hunter/commit/4602812d420df99a046f457d950a55d0b5d2f411))

Implements RssSource parsing RSS 2.0 and Atom feeds into Deal objects using stdlib
  xml.etree.ElementTree. Registered as 'rss' in SOURCE_REGISTRY. Includes a _find_price helper that
  locates price tokens with currency symbols before delegating to extract_price, avoiding false
  positives from model/year numbers embedded in titles and descriptions.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Add x-kom.pl YAML store definition
  ([`9ede776`](https://github.com/giraffe-horizon/deal-hunter/commit/9ede7767bf4771640dce77388b48dff9afb74d6a))

NOTE: x-kom.pl is behind Cloudflare + uses React CSR, so live HTTP scraping receives a challenge
  page. Store definition and selectors are based on x-kom.pl's known DOM structure and verified
  against a hand-crafted HTML fixture. Includes 11 tests covering registration, parsing, prices,
  links, IDs, images, and regular/old prices.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **quiet-hours**: Add alert_queue table and SQLite methods
  ([`37df95e`](https://github.com/giraffe-horizon/deal-hunter/commit/37df95ec35ce7951d468b170712bd4f183accc0e))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **quiet-hours**: Add is_quiet_hours() time logic
  ([`5c04ccf`](https://github.com/giraffe-horizon/deal-hunter/commit/5c04ccf47f464b1a7b6511c7b996e5cdf075892d))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **quiet-hours**: Add validation and .env.example
  ([`e7afcdf`](https://github.com/giraffe-horizon/deal-hunter/commit/e7afcdf01340b49934972a533ae83ff993567984))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **quiet-hours**: Integrate alert queuing into run flow
  ([`0d31b8e`](https://github.com/giraffe-horizon/deal-hunter/commit/0d31b8e6d61ccdc9e11ba8d96d702d974bd99827))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.6.1 (2026-04-06)

### Bug Fixes

- Resolve deal detail page horizontal overflow on mobile
  ([`5d881bd`](https://github.com/giraffe-horizon/deal-hunter/commit/5d881bd89ebd678aa45eb170aa6394ff3ccac58b))

Prevent long titles, chart containers, and period buttons from expanding beyond 375px viewport
  width.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Documentation

- Add roadmap v2.0 (A: quality, B: sources, C: dashboard UX)
  ([`1b408ee`](https://github.com/giraffe-horizon/deal-hunter/commit/1b408ee3700e28e16a65149b26124c8e22575418))


## v0.6.0 (2026-04-06)

### Code Style

- Apply ruff format to dashboard and storage tests
  ([`0975837`](https://github.com/giraffe-horizon/deal-hunter/commit/0975837c23d7102c5648940be7cd36768bd68332))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Features

- Make dashboard responsive and sync version with app
  ([`c858b2d`](https://github.com/giraffe-horizon/deal-hunter/commit/c858b2d52b74d26a4ed890382d44f67d45bb5454))

Add mobile-responsive layout: off-canvas sidebar with hamburger toggle, overlay backdrop, responsive
  padding, hidden table columns on small screens, full-width filter dropdowns, stacking action
  buttons, and responsive pagination. Dashboard version now reads from pyproject.toml via
  importlib.metadata instead of being hardcoded, displayed in sidebar.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.5.2 (2026-04-06)

### Bug Fixes

- Resolve ruff lint errors in dashboard and tests
  ([`d8b7007`](https://github.com/giraffe-horizon/deal-hunter/commit/d8b700714ddd8fd35536da4cb9a6d1aa57cc2922))

Sort imports per ruff I001, remove unused pytest import and dead helper function.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.5.1 (2026-04-06)

### Bug Fixes

- Dashboard bug fixes, comprehensive tests, and project cleanup
  ([`9425937`](https://github.com/giraffe-horizon/deal-hunter/commit/9425937973627f006bbbd79a29edbe2015df12b2))

Fix status update HTMX response losing action buttons after swap and pagination links not preserving
  active filters. Add COALESCE for NULL-safe SQL aggregates. Expand dashboard test suite from 51 to
  127 tests with unit, integration, and E2E workflow coverage. Remove remaining Notion references
  from wiki docs. Update ROADMAP to reflect v1.0 completion.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.5.0 (2026-04-06)

### Documentation

- Add Docker and examples entries to CLAUDE.md architecture
  ([`e02d38f`](https://github.com/giraffe-horizon/deal-hunter/commit/e02d38fc7524199f75a44a888f2fdf08135b69dc))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Add web dashboard design spec
  ([`563e0cd`](https://github.com/giraffe-horizon/deal-hunter/commit/563e0cda8fd5a18a7a5e16322ef5f9edc1bbc69e))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Features

- Add web dashboard scaffold with FastAPI + Stitch design system
  ([`00bf14b`](https://github.com/giraffe-horizon/deal-hunter/commit/00bf14be11c2e71fd104f10f96e8187cff2d0010))

Create FastAPI app with Jinja2 templates, sidebar navigation, and Stitch design tokens (Analytical
  Atelier). Includes CDN imports for Tailwind, Chart.js, HTMX, Google Fonts, and Material Symbols.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Add web dashboard with 4 screens and Docker service
  ([`8627d7f`](https://github.com/giraffe-horizon/deal-hunter/commit/8627d7fa9586e71b2e8a9b96f4e00c186889239d))

FastAPI dashboard at port 8080 with Deals Explorer (filterable, paginated), Deal Detail (Chart.js
  price history, watch/skip actions), System Health (source/profile status from health.json), and
  Price Trends (drops table, category sparklines). HTMX for partial table refresh, Tailwind CSS +
  Stitch design tokens via CDN.

Adds deal-hunter-web Docker Compose service, SQL aggregate methods for dashboard performance, and
  /api/stats endpoint.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.4.3 (2026-04-06)

### Bug Fixes

- Stop scanning examples/ directory as real profiles
  ([`b3e13fa`](https://github.com/giraffe-horizon/deal-hunter/commit/b3e13fa86fc7a7f8f4931d373115360519fd9da6))

- Remove EXAMPLES_DIR fallback from load_profile and list_profiles - Remove COPY examples/ from
  Dockerfile - examples/ is reference documentation only, not auto-discovered

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.4.2 (2026-04-06)

### Bug Fixes

- Resolve mypy no-any-return errors in health, storage, yaml_source
  ([`1138b21`](https://github.com/giraffe-horizon/deal-hunter/commit/1138b21532f5ff34fe0113e754c4840d9a38c7af))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.4.1 (2026-04-06)

### Bug Fixes

- Resolve all ruff lint and format errors
  ([`3718b7d`](https://github.com/giraffe-horizon/deal-hunter/commit/3718b7d69c40512977ea7ecf222aca6d05ca9e61))

- Remove unused imports (Path, Text, html, struct) - Remove f-string prefixes on strings without
  placeholders - Remove unused variable price_str - Fix import sorting in visualization/charts.py -
  Auto-format 13 files

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.4.0 (2026-04-06)

### Bug Fixes

- Add matplotlib, pytest-asyncio, python-telegram-bot to dev dependencies
  ([`3e87c9b`](https://github.com/giraffe-horizon/deal-hunter/commit/3e87c9b487afc9518b0f11958548790ebc8bbb0e))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- Add missing COPY targets to Dockerfile (feedback_bot, storage, visualization)
  ([`efdf6c0`](https://github.com/giraffe-horizon/deal-hunter/commit/efdf6c086e955ed4844a0728fcfb65441e27ff7c))

- Add missing health.py to Dockerfile, fix bot entrypoint override
  ([`01bdc08`](https://github.com/giraffe-horizon/deal-hunter/commit/01bdc086395816ff87fee813f5dcc8e38bdf79e0))

- health.py was missing from COPY targets, causing ModuleNotFoundError - bot service needs
  entrypoint override to bypass the cron entrypoint.sh

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Documentation

- Add Docker Compose full service design spec
  ([`7b8d58e`](https://github.com/giraffe-horizon/deal-hunter/commit/7b8d58e4e4b686b2b9a4cbfce26fb13b40debb5d))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Add Docker Compose implementation plan
  ([`94c20ff`](https://github.com/giraffe-horizon/deal-hunter/commit/94c20ff62ff84576bf434227a3c7bcffc202d34c))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Update Docker section with bot service and schedule config
  ([`41cb309`](https://github.com/giraffe-horizon/deal-hunter/commit/41cb30997eb5f167d1ee6f42c032b682db4dc889))

- Update implementation plan with CI fix task
  ([`e36964b`](https://github.com/giraffe-horizon/deal-hunter/commit/e36964b484c0c6613153c2bad70ee9898f406bfd))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Features

- Add feedback bot service to docker-compose
  ([`de68fc3`](https://github.com/giraffe-horizon/deal-hunter/commit/de68fc31fbca90651324e57493cace7c21836242))

- Extend entrypoint with watchdog and digest cron schedules
  ([`6f99b3e`](https://github.com/giraffe-horizon/deal-hunter/commit/6f99b3ecc23c3015f41afbd54761ef034f0c9e01))


## v0.3.0 (2026-04-06)

### Bug Fixes

- Sqlite transaction safety, encoding, systemd env, and defensive parsing
  ([`3d5982c`](https://github.com/giraffe-horizon/deal-hunter/commit/3d5982c13cea9a41983ae4e872f8ca8497e294bf))

- Remove mid-transaction commit from record_price() to make upsert_deal atomic - Add
  encoding="utf-8" to all state/health file open() calls (prevents Polish character corruption in
  non-UTF-8 locales like cron/Docker) - Add EnvironmentFile to bot systemd service for consistency -
  Log database close errors at debug level instead of silently swallowing - Guard against empty YAML
  profile (yaml.safe_load returns None) - Extract _parse_topic_id() helper for safe
  TELEGRAM_TOPIC_ID parsing (catches ValueError on non-numeric values)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

### Features

- Add Telegram feedback bot with inline keyboard support
  ([`625f47f`](https://github.com/giraffe-horizon/deal-hunter/commit/625f47f8ad8fb1c9c12442d4d14514ba6e5a1162))

Standalone polling bot (feedback_bot.py) with inline keyboard buttons on deal alerts (Watch/Skip),
  text commands (/status, /watchlist), SQLite storage methods, systemd service, and comprehensive
  tests.

Also includes scoring breakdown improvements in filters and project roadmap.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.2.0 (2026-04-06)

### Bug Fixes

- Address review findings (context manager, category detection, migration API)
  ([`937e64f`](https://github.com/giraffe-horizon/deal-hunter/commit/937e64f9c7327ab5edb74bf49d1b29c30155c607))

- Add __enter__/__exit__ to SQLiteStorage for context manager support - Replace manual db.close() in
  deal_hunter.py with try/finally - Add _detect_category() using new top-level 'categories' profile
  field - Add import_legacy_deal(), import_legacy_price(), commit() public methods to SQLiteStorage
  so migration script doesn't access _conn directly - Update migration script to use public API and
  context manager

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- False price drop alerts from cross-source price differences
  ([`ee51ec8`](https://github.com/giraffe-horizon/deal-hunter/commit/ee51ec85b640ff5ced0ff99aaba4f29af745521b))

- Use deal.id instead of normalized title for price history tracking, preventing cross-source false
  positives (e.g. same bike at different prices from sprint vs centrumrowerowe) - Add 24h cooldown
  between price drop alerts for the same deal - Increase default min_drop_amount from 100 to 200 PLN

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Health monitoring review fixes (public API, imports, topic_id)
  ([`307994c`](https://github.com/giraffe-horizon/deal-hunter/commit/307994cc39bc8767ccad9fccd81fd9c2a3985d8a))

- Add TelegramNotifier.send_text() public method, stop using _send_message() externally - Move
  'import time' to top-level imports - Don't mutate result dict in _run_with_health_tracking (use
  .get + dict comprehension) - Read TELEGRAM_TOPIC_ID from env for watchdog and source failure
  alerts

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Price drop review fixes (limits, digest timer, Polish chars)
  ([`3152cac`](https://github.com/giraffe-horizon/deal-hunter/commit/3152cac08d65588c5a03d6c27f15c117a035680f))

- Limit price drop alerts to max_alerts, sorted by diff_percent desc - Guard digest Telegram send
  when credentials are missing - Fix Polish diacritics: Najnizsza -> Najniższa - Add digest systemd
  timer (weekly Monday 08:00) + service

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Trigger Docker build from Release workflow_run instead of tag push
  ([`c45876b`](https://github.com/giraffe-horizon/deal-hunter/commit/c45876b0786201d9e168782e0866a843c6a09823))

GITHUB_TOKEN tags don't trigger other workflows. Use workflow_run event on Release completion +
  fetch latest release tag via API.

### Features

- Add health monitoring with watchdog and systemd timers
  ([`4c3b49a`](https://github.com/giraffe-horizon/deal-hunter/commit/4c3b49a3a666a5e7f7ba282de83993d118a73d5c))

- health.py: tracks run results, per-source consecutive failures, staleness - state/health.json
  written after every run with status/duration/version - --health flag: human-readable status (exit
  0=ok, 1=partial, 2=error, 3=stale) - --watchdog flag: checks freshness, sends Telegram alert if
  stale (>2h) - Source failure alerts: auto-notify via Telegram after 3+ consecutive failures -
  scripts/systemd/: user-level timer units (30min run, 1h watchdog) with OnFailure crash
  notifications - 30 new tests in test_health.py (all 192 tests pass)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Add SQLite persistence layer (replaces Notion)
  ([`ade211a`](https://github.com/giraffe-horizon/deal-hunter/commit/ade211ae3694fe694e91071e473b16d021cf5284))

Add storage/sqlite.py with SQLiteStorage class backed by stdlib sqlite3. Three tables: deals,
  price_history, feedback. Integrated into deal_hunter.py to persist scored deals after each run.
  Includes migration script for existing state/*.json files and comprehensive tests (27 cases).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Configurable price drop alerts with weekly digest
  ([`fba5147`](https://github.com/giraffe-horizon/deal-hunter/commit/fba5147f2b420526317042eacf2ae041d9d7d727))

Add price_tracking profile config (min_drop_percent, min_drop_amount, track_increases) with sensible
  defaults. Enhanced check_price_changes() returns structured dicts and checks SQLite for
  lowest-ever prices with graceful fallback to state JSON. Price drop alerts are sent as separate
  Telegram messages before regular alerts. New --digest flag sends weekly price drop summary from
  SQLite price_history. Added SQLite methods (get_price_drops, get_lowest_price,
  get_previous_price), Telegram formatting (send_price_drop_alert, send_digest), and profile
  validation.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Price history charts and visualization
  ([`0fae7d1`](https://github.com/giraffe-horizon/deal-hunter/commit/0fae7d1fcbeed5d4e620951c22824ad10976b512))

Add matplotlib-based chart generation (lazy-imported, Agg backend) with three chart types: price
  history line chart, weekly digest bar chart, and profile trend chart. Charts use Polish labels and
  are sent to Telegram via new send_photo() method (multipart/form-data upload).

New CLI flags: --price-chart DEAL_ID, --trend-chart PROFILE. The --digest command now also generates
  and sends a bar chart.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Remove Notion integration (replaced by SQLite in upcoming phase)
  ([`8a6de86`](https://github.com/giraffe-horizon/deal-hunter/commit/8a6de8687fd2d5d713d77323813336155381ece0))

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Verbose scoring breakdown (--verify --verbose)
  ([`f565c97`](https://github.com/giraffe-horizon/deal-hunter/commit/f565c97ea2957ea221ef8a2a29533391f0784ac5))

Add detailed scoring breakdown to ScoreResult with a new `breakdown` field that tracks every rule
  that fired (score_rules, penalties, budget, temperature, excluded, required_any) plus
  BikeFilter-specific entries (size, color, tire, race). New --verbose/-v flag shows per-deal
  breakdown with box-drawing output, with optional rich library support. New --top N flag limits
  output. 22 new tests in test_verbose_scoring.py.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>


## v0.1.0 (2026-04-03)

### Bug Fixes

- Address all review issues from yaml-stores
  ([`bcb98db`](https://github.com/giraffe-horizon/deal-hunter/commit/bcb98dbfcb538c310254d7596cacc10151e462b1))

Blocking: - Remove phantom price_format from stores/README.md - Extract regular_price from JSON-LD
  offers.highPrice - Fix native ID regex to use last digit segment (not first)

Non-blocking: - Fix README selector syntax consistency (no space before @) - Add YAML store schema
  validation (warn on missing selectors.products) - Add warning when YAML store shadows Python
  source - Fix _resolve_url for /-prefixed URLs with base_url containing path

Tests: 115 → 130 (15 new edge case tests, all passing)

- Address all review issues — Docker security, README accuracy, UX polish
  ([`cfdae2b`](https://github.com/giraffe-horizon/deal-hunter/commit/cfdae2b62c6a4d46ea0ef991c25cfadede7ff80e))

Blocking: - Fix README architecture tree (list actual files, not deleted ones) - Dockerfile: tini
  PID 1, supercronic (non-root cron), USER dealer - Dockerfile: proper pip install layer ordering

Non-blocking: - entrypoint.sh: umask 077 for secrets, supercronic integration - docker-compose:
  remove duplicate env vars, use env_file - .dockerignore: exclude profiles/ - init_profile: inline
  budget validation, robust topic_id parsing - Tests: mock SOURCE_REGISTRY for stability - README:
  Type column in sources table - Version bump to 1.1.0 - CONTRIBUTING: fix profile path

Tests: 135 passing

- Ceneo/proshop price parsing, telegram markdown escaping
  ([`5de939d`](https://github.com/giraffe-horizon/deal-hunter/commit/5de939debcce312863335a187532738fce1a5a66))

- Ceneo: add 'price-format', 'box-vert__price' selectors and broader container detection (CSS
  selectors, [data-pid]) - Proshop: add 'site-currency-attention', 'site-currency-sm' and broader
  product container selectors ([data-product-id]) - Telegram: switch from Markdown to HTML
  parse_mode to avoid breakage from regex patterns (slashes, backslashes) in score details;
  html.escape all user-facing text

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Extract shared price parser, stable web IDs, pin deps, Deal validation, tests
  ([`e5aeeaf`](https://github.com/giraffe-horizon/deal-hunter/commit/e5aeeafca1dd87dd61663c3ecafde38fe1471ef6))

- Extract _extract_price() to Source.extract_price() in base.py, remove from 7 source files + pepper
  module-level function. New parser correctly handles European dot-thousands format (e.g. '18.999
  ZŁ' -> 18999). - Fix web.py Deal ID: use content hash instead of index for stability. - Pin
  dependency versions in requirements.txt. - Add Deal.__post_init__ validation (empty title,
  negative price, temperature). - Fix Sprint pagination: use urllib.parse to preserve existing query
  params. - Fix bike_filter brand matching: use word boundary regex instead of substring 'in' check
  ('trek' no longer matches 'streker'). - Fix Telegram 429 retry: wrap resp.json() in try/except for
  non-JSON responses. - Add parametrized tests for extract_price covering European formats.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Update CONTRIBUTING.md install instructions to use pip install -e .[dev]
  ([`12c60f5`](https://github.com/giraffe-horizon/deal-hunter/commit/12c60f5d0140fc8fc7476225ec9c44c4c33b2075))

### Chores

- Add MIT license
  ([`876f480`](https://github.com/giraffe-horizon/deal-hunter/commit/876f480d2f486181130033c6efa01a0b772b56ae))

- Remove all example.yaml references, update docs
  ([`06c4434`](https://github.com/giraffe-horizon/deal-hunter/commit/06c44341351add1152a8d2a57f0bfaa865667dda))

example.yaml was deleted — update all references across README, CLAUDE.md, CONTRIBUTING.md,
  docs/creating-profiles.md, CI workflow, and .gitignore. Add inline minimal YAML template in the
  profile creation guide.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Remove example profile
  ([`80c9ae2`](https://github.com/giraffe-horizon/deal-hunter/commit/80c9ae20b1ccb491802988b54f3922807c5e82a2))

### Code Style

- Fix ruff formatting
  ([`c589828`](https://github.com/giraffe-horizon/deal-hunter/commit/c58982830ffe4a59c98183d9dd36951ab117e262))

### Documentation

- Add comprehensive wiki pages
  ([`a47a625`](https://github.com/giraffe-horizon/deal-hunter/commit/a47a62571af7cf6b4a0d0dededada0f11541629b))

- Home: overview, feature table, navigation - Getting Started: install, first scan, cron setup -
  Adding a Store: step-by-step YAML guide with examples - Creating Profiles: full reference for all
  fields - Scoring Engine: how scoring works, keyword/budget/temp - Docker Deployment: compose,
  config, one-off commands - Architecture: data flow, abstractions, directory structure - FAQ:
  common questions, troubleshooting

- Add profile docs, example profile, gitignore user profiles
  ([`7a88bd1`](https://github.com/giraffe-horizon/deal-hunter/commit/7a88bd1c813513c38dcec2d69be008fba5c061ec))

- Comprehensive README + CLAUDE.md for coding agents
  ([`611a9f8`](https://github.com/giraffe-horizon/deal-hunter/commit/611a9f881794eca06312644c888749e9cc178c3d))

### Features

- Add 5 new source plugins (Canyon, Rowertour, Veloshop, Centrumrowerowe, Sprint-Rowery), fix
  Ceneo/Proshop false positives, update nas_hdd profile
  ([`cf387ee`](https://github.com/giraffe-horizon/deal-hunter/commit/cf387eeafd2102860a91c7d70c74e43c2879fc09))

- Added CanyonSource, RowertourSource, VeloshopSource, CentrumroweroweSource, SprintSource - Fixed
  Ceneo/Proshop injecting search query into description (caused false scoring) - Fixed word boundary
  in nas_hdd penalties (2tb no longer matches 12tb) - Updated nas_hdd budget to 600-2000 PLN - Added
  excluded_words to nas_hdd (windows, microsoft, etc.) - Updated bikes.yaml with new sources and
  Pepper search queries - Removed bike-monitor (migrated to deal-hunter)

- Add CI/CD, tests, linting (ruff + mypy)
  ([`f08fd47`](https://github.com/giraffe-horizon/deal-hunter/commit/f08fd47442d9ae148ae3cb786bea995f6df276f6))

- GitHub Actions CI: lint (ruff + mypy), test (pytest), validate-profiles - GitHub Actions release
  workflow on tag push - 26 unit tests: scoring, bike filter, validation, dedup, price tracking -
  ruff config (py312, isort, pyupgrade) + mypy config in pyproject.toml - Fix double logging
  (configure root logger once, children propagate) - Fix --all skipping disabled profiles (enabled:
  false in example.yaml) - Auto-fix all ruff and mypy issues across codebase

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Add regular price parsing, discount calculation, and Notion dedup
  ([`640f698`](https://github.com/giraffe-horizon/deal-hunter/commit/640f6982527297d64f33fd32205c43af5451f569))

- Add regular_price field to Deal dataclass - Parse regular/original price from Pepper (Vue3 + HTML
  fallback) and Ceneo - Compute discount percentage from regular_price vs price - Send regular price
  and discount to Notion (Cena regularna, Rabat) - Deduplicate Notion entries by checking Link URL
  before saving - Show strikethrough regular price and discount in Telegram alerts

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Add semantic release and Docker CI/CD pipeline
  ([`dbcfdf9`](https://github.com/giraffe-horizon/deal-hunter/commit/dbcfdf971632efb735d38327251ea9063249d345))

- Add python-semantic-release config (conventional commits → semver) - Add
  .github/workflows/release.yml (auto version, changelog, tag, GH release) - Add
  .github/workflows/docker.yml (multi-arch build, ghcr.io push, semver tags) - Update Dockerfile for
  multi-arch (ARG TARGETARCH for supercronic) - Update docker-compose.yml with pre-built image
  option - Update README with release badge and ghcr.io pull instructions

Tests: 135 passing, no changes to application code

- Deal Hunter v1 — multi-source deal monitor
  ([`0456f10`](https://github.com/giraffe-horizon/deal-hunter/commit/0456f10055a31d6430c2c902d7e29794808181e9))

- Migrated full bike_monitor.py logic to modular architecture - Sources: Pepper.pl, Ceneo.pl,
  Proshop.pl (pluggable) - Filters: base scoring engine + BikeFilter (sizes, colors, tires, race
  keywords) - Notifiers: Telegram (rate-limited, retry) + Notion (optional per profile) - Profiles:
  bikes.yaml (full migration), nas_hdd.yaml (new) - CLI: --profile, --all, --verify, --list - State
  management with TTL cleanup and cross-source dedup - .env for secrets, YAML for config

- Deal-hunter init, Dockerfile, README polish
  ([`faa6ffe`](https://github.com/giraffe-horizon/deal-hunter/commit/faa6ffeac00b90f90f04c730ba4688b6366100c3))

- Add --init flag: interactive profile creator (source auto-discovery, queries/URLs, budget,
  keywords, notifications) - Add Dockerfile + docker-compose (CRON_SCHEDULE env var, volumes) - Add
  docker/entrypoint.sh - Rewrite README: Why section, leads with generic capability, Docker section,
  --init in quick-start - Update CHANGELOG v1.1.0

Tests: 130 → 135 (all passing)

- Make deal-hunter fully generic (regex, web source, price tracking, validation)
  ([`08bb7fd`](https://github.com/giraffe-horizon/deal-hunter/commit/08bb7fd72fdae36a30ea68a80f613ccf8ccff63f))

- Regex support in score_rules, penalties, excluded_words, required_any (r/pattern/ syntax) -
  Generic web scraper source (sources/web.py) with configurable CSS selectors - Price history
  tracking with price drop detection (>10% or >50 PLN) - Profile validation (utils/validation.py)
  with --validate CLI flag - Notion categories configurable per profile (instead of hardcoded) -
  Currency field in profiles (default PLN) - Better deduplication with normalized titles and fuzzy
  matching (SequenceMatcher) - Updated example.yaml, CLAUDE.md, README.md with new features

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- Open-source readiness overhaul
  ([`6d2f313`](https://github.com/giraffe-horizon/deal-hunter/commit/6d2f313a0ffedba66338dd8d69747ff5f8b65857))

- Add examples/headphones.yaml (working tutorial profile) - Add parser tests with HTML fixtures
  (Pepper Vue3/HTML, Ceneo) - Add tests for Deal validation, state management, dedup - Update
  README: Why section, all 9 sources, quick-start, pip install - Add CHANGELOG.md, SECURITY.md, PR
  template, Makefile - Replace MD5 with SHA256 in web.py - Use importlib.metadata for version
  (single source of truth) - Add env validation (warn if TELEGRAM_BOT_TOKEN empty) - CI: Python
  3.12+3.13 matrix, pip caching, pytest-cov - Fix pyproject.toml license format, ruff formatting

Tests: 39 → 69 (all passing)

- Replace Python source plugins with declarative YAML store definitions
  ([`1d2b1fd`](https://github.com/giraffe-horizon/deal-hunter/commit/1d2b1fd865687f4979a5fbbb6a8c32b659536778))

BREAKING: source plugins for ceneo, proshop, canyon, rowertour, centrumrowerowe, sprint, veloshop
  are now YAML files in stores/.

- Add sources/yaml_source.py — universal engine with strategies: CSS selectors, JSON-LD
  (schema.org), GTM dataLayer - Add 7 YAML store definitions (~15 lines each vs ~200 lines Python) -
  Auto-discovery: stores/*.yaml registered at import time - Backward compatible: existing profiles
  work without changes - Pepper stays as Python (too complex for YAML) - Add 46 tests for
  yaml_source (strategies, price parser, loading) - Add stores/README.md — 'How to add a store in 5
  minutes' - Delete 7 Python source files (-1432 lines)

Tests: 69 → 115 (all passing)

### Refactoring

- Professionalize codebase — English, docs, contributing guide
  ([`4b551c7`](https://github.com/giraffe-horizon/deal-hunter/commit/4b551c745b4feacd0ffde1e77c602714da0e36fc))

- All code comments, docstrings, log messages, CLI output -> English - Telegram alert messages stay
  in Polish (end-user facing) - Notion property names stay in Polish (match database schema) - Full
  README rewrite: badges, architecture, usage, scoring docs - CLAUDE.md rewritten in English -
  docs/creating-profiles.md rewritten in English - profiles/example.yaml comments translated to
  English - Added CONTRIBUTING.md with dev setup and plugin guides - Added pyproject.toml with
  project metadata and CLI entry point - Added .github/ISSUE_TEMPLATE/ (bug report + feature
  request) - Added __version__ to deal_hunter.py, --version CLI flag - Added __all__ to all
  __init__.py files - Added type hints throughout - Updated .env.example with English comments

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

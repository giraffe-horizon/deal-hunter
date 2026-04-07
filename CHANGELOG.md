# CHANGELOG


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

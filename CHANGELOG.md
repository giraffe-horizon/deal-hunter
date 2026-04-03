# CHANGELOG


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

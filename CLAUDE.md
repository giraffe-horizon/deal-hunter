# CLAUDE.md — Instructions for Claude Code

## Project

**Deal Hunter** — universal multi-source deal monitor. Scans various sources (Pepper.pl, Ceneo.pl, Proshop.pl, any website via generic web scraper), scores offers using a YAML-driven scoring engine (with regex support), tracks price changes, and sends alerts to Telegram.

## Tech Stack

- **Python 3.12+** (venv in `./venv/`)
- **requests** — HTTP client
- **beautifulsoup4** — HTML scraping
- **pyyaml** — YAML profile parsing
- **python-dotenv** — environment variables from `.env`
- No web framework — this is a CLI tool designed to run on cron

## Architecture

```
deal_hunter.py          Orchestrator: loads profile -> sources -> scoring -> notifications
sources/base.py         Base Source class + Deal dataclass (common format)
sources/yaml_source.py  Universal YAML-driven source engine (CSS, JSON-LD, GTM strategies)
sources/pepper.py       Pepper.pl scraper (Vue3 JSON + HTML fallback — too complex for YAML)
sources/web.py          Generic web scraper (configurable CSS selectors from profile YAML)
stores/*.yaml           Declarative store definitions (auto-discovered, no Python needed)
stores/README.md        Guide: "How to add a new store in 5 minutes"
filters/base.py         Base scoring engine (score_rules, penalties, budget, temperature, regex)
filters/bike_filter.py  Extended scorer for bikes (sizes, colors, tires, race keywords)
notifiers/telegram.py   Telegram Bot API with retry + rate limiting
storage/sqlite.py       SQLite persistence layer (deals, price history, feedback)
health.py               Health monitoring (state tracking, --health, --watchdog)
utils/validation.py     YAML profile validation (types, required fields, sanity checks)
profiles/*.yaml         Product profiles (gitignored, see docs/creating-profiles.md)
docs/creating-profiles.md  Profile creation guide
state/*.json            Persistent state per profile (what's been seen, 14-day TTL)
state/health.json       Health monitoring state (last run, per-source/profile results)
state/deals.db          SQLite database (deals, price_history, feedback tables)
scripts/migrate_state_to_sqlite.py  One-time migration from state/*.json to SQLite
scripts/systemd/        Systemd user timer units + install script
```

## Key Patterns

### Deal (dataclass)
Every source returns a list of `Deal` objects in a common format:
```python
@dataclass
class Deal:
    id: str           # "{source}:{native_id}" — unique cross-source
    title: str
    price: int        # PLN, 0 if unknown
    link: str
    source: str       # "pepper", "ceneo", "proshop", "web"
    description: str
    temperature: int   # Pepper only, rest 0
    image_url: str
    published_at: str  # ISO datetime or ""
```

### Source Plugin
```python
class Source(ABC):
    def fetch_deals(self, config: dict) -> list[Deal]:
        # config = the source's config section from the profile YAML
        pass
```
Sources have built-in rate limiting (`MIN_REQUEST_INTERVAL = 2s`), retry with backoff, and a `_fetch_page()` helper.

### Scoring
`BaseFilter.score_deal(deal) -> ScoreResult(score, plus, minus, rejected, reject_reason)`

Flow:
1. Excluded words -> hard reject
2. Required any -> reject if none match
3. Score rules -> `+points` per keyword match in title+desc
4. Penalties -> `-points` per keyword match
5. Budget -> in budget +5, too cheap -20, too expensive -30
6. Temperature (Pepper) -> hot >=100° +10, warm >=50° +5, cold <-10° -10

**Regex in score_rules/penalties/excluded_words/required_any:**
Keywords starting with `r/` and ending with `/` are treated as regex (re.IGNORECASE).
Example: `"r/\\b(xl|58|59)\\b/": 10` — matches whole words xl, 58, 59.

Custom filters (e.g., `BikeFilter`) inherit from `BaseFilter` and override `score_deal()` with additional logic.

### YAML Profile
Each profile (`profiles/*.yaml`) defines:
- `name`, `emoji` — identification
- `sources` — dict with per-source config
- `budget` — `{min, max}`
- `score_rules` — `keyword: points`
- `penalties` — `keyword: penalty`
- `required_any`, `excluded_words` — filters (optional)
- `custom_filter` — filter class name e.g. `"bike_filter.BikeFilter"` (optional)
- `custom_data` — arbitrary data for custom filter (e.g., sizes per brand)
- `score_threshold`, `score_threshold_alert` — thresholds
- `currency` — currency code (default "PLN")
- `telegram` — `{topic_id, max_alerts}`
- `price_tracking` — optional: `{enabled, min_drop_percent, min_drop_amount, track_increases}`

### Plugin Registration
- Sources: `sources/__init__.py` -> `SOURCE_REGISTRY` — Python sources (pepper, web) registered explicitly; YAML stores from `stores/*.yaml` auto-discovered at import time
- Filters: `filters/__init__.py` -> `FILTER_REGISTRY = {"bike_filter.BikeFilter": BikeFilter, ...}`

## How to Run

```bash
source venv/bin/activate
python deal_hunter.py --profile bikes --verify   # test without saving state
python deal_hunter.py --profile nas_hdd           # normal run
python deal_hunter.py --all                        # all profiles
python deal_hunter.py --list                       # list profiles
python deal_hunter.py --profile bikes --validate  # validate profile without running
python deal_hunter.py --health                     # show health status of last run
python deal_hunter.py --watchdog                   # check freshness, alert if stale
python deal_hunter.py --digest                     # weekly price drop digest from SQLite
```

## Environment Variables

File `.env` (not committed):
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Adding a New Source

**Preferred (no Python):** Create a YAML store definition in `stores/`. See `stores/README.md` for a 5-minute guide.

```yaml
# stores/myshop.yaml
name: myshop
type: catalog          # or "search" for query-based stores
base_url: "https://myshop.com"
strategies:
  - css                # also: json-ld, gtm
selectors:
  products: "div.product"
  title: "h2.name"
  price: "span.price"
  link: "a@href"
  image: "img@src"
```

The store is auto-discovered and registered — no code changes needed.

**For complex sources** (like Pepper with Vue3 JSON + temperature):
1. Create `sources/new_source.py`
2. Class inherits from `Source`, implements `fetch_deals(config) -> list[Deal]`
3. Use `self._fetch_page(url)` and `self._rate_limit()` from the base class
4. Register in `sources/__init__.py`: `SOURCE_REGISTRY["new_source"] = NewSource`

**Web scraper** (`sources/web.py`) — for one-off sites configured directly in profile YAML:
```yaml
sources:
  web:
    sites:
      - url: "https://example.com/deals"
        base_url: "https://example.com"
        selectors:
          container: "div.product"
          title: "h2.name"
          price: "span.price"
          link: "a@href"
          image: "img@src"
```

## Adding a New Profile

**IMPORTANT:** User profiles are NOT in the repo (gitignored).

1. Create `profiles/name.yaml` — see `docs/creating-profiles.md` for a template and guide
2. Detailed guide: `docs/creating-profiles.md`
3. If you need a custom filter -> create in `filters/`, register in `FILTER_REGISTRY`, set `custom_filter` in YAML

## Adding a Custom Filter

1. Create `filters/new_filter.py`
2. Class inherits from `BaseFilter`, overrides `score_deal(deal) -> ScoreResult`
3. **Always call** `result = super().score_deal(deal)` first — the base scorer handles universal rules
4. Access extra data via `self.profile.get("custom_data", {})`
5. Register in `filters/__init__.py`

## Code Conventions

- **Language:** English for all code, comments, docstrings, and log messages
- **Telegram messages:** Polish (they go to a Polish-speaking user)
- **Logging:** `logging` module, not `print()` (exception: `--verify` mode prints to stdout)
- **Error handling:** graceful degradation — one source fails -> rest continue, one notifier fails -> rest continue
- **Rate limiting:** each source has min 2s between requests, Telegram 1.5s + retry on 429
- **State:** per-profile JSON in `state/`, 14-day TTL, cross-source dedup by title+price
- **Secrets:** NEVER in code — `.env` + `python-dotenv`, `.gitignore` protects `.env`

## Price Tracking

Deal Hunter automatically tracks prices of known offers. State saved in `state/<profile>_state.json` under the `"prices"` key, with SQLite `price_history` as richer data source.

**Configurable via profile YAML:**
```yaml
price_tracking:
  enabled: true              # default: true
  min_drop_percent: 15       # alert if price drops >= 15% (default: 10)
  min_drop_amount: 200       # alert if price drops >= 200 PLN (default: 100, OR with percent)
  track_increases: false     # notify on price increases (default: false)
```

**Behavior:**
- Price drop meeting thresholds -> separate Telegram alert (sent before regular alerts)
- Checks SQLite price_history for all-time lowest price detection
- Falls back to state JSON if SQLite unavailable
- Price increase -> logged, optionally notified if `track_increases: true`

**Weekly digest:** `--digest` scans SQLite for all price drops in last 7 days and sends a Telegram summary.

## Health Monitoring

After every non-verify run, Deal Hunter writes `state/health.json` with:
- Overall status (`ok`/`partial`/`error`), duration, version
- Per-profile results (deals found, new alerts, errors)
- Per-source health (consecutive failures tracked across runs)

**CLI flags:**
- `--health` — human-readable status. Exit codes: 0=ok, 1=partial, 2=error, 3=stale/missing
- `--watchdog` — checks if last run was within 2 hours; sends Telegram alert if stale. Exit code: 0=fresh, 1=stale

**Source failure alerts:** If any source has >= 3 consecutive failures, a Telegram alert is sent automatically after the run.

**Systemd timers:** `scripts/systemd/install.sh` installs user-level timers (run every 30m, watchdog every 1h). The main service has `OnFailure=` to send Telegram crash alerts.

## Profile Validation

`utils/validation.py` -> `validate_profile(profile) -> list[str]`

Checks: required fields, data types, sanity (budget.min < budget.max, score_threshold < score_threshold_alert).

CLI: `python deal_hunter.py --profile bikes --validate`

## Tests

```bash
python -m pytest tests/ -v              # run all tests
python -m pytest tests/ -v --tb=short   # compact output
```

Test modules:
- `test_yaml_source.py` — YAML source engine: CSS/JSON-LD/GTM strategies, field extraction, pagination, store loading, auto-discovery
- `test_ceneo_parser.py` — Ceneo store parsing via YAML source (validates selectors against HTML fixtures)
- `test_pepper_parser.py` — Pepper parser (Vue3 + HTML)
- `test_scoring.py`, `test_bike_filter.py` — scoring engine
- `test_extract_price.py` — price parser
- `test_deal.py`, `test_dedup.py`, `test_state.py`, `test_validation.py` — core logic
- `test_sqlite_storage.py` — SQLite persistence layer (CRUD, upsert, price history, filtering)
- `test_health.py` — health monitoring (health.json, --health, --watchdog, source tracking)
- `test_price_drops.py` — price drop detection, thresholds, digest, Telegram formatting, validation

Manual testing:
```bash
python deal_hunter.py --profile bikes --verify
python deal_hunter.py --profile nas_hdd --verify
```

## Known Limitations

- Ceneo and Proshop scrape HTML — layout changes require parser updates
- No Allegro (requires API key + OAuth)
- No OLX, Morele, x-kom (to be added)
- Pepper may block after many requests — hence rate limiting
- Cross-source dedup is simple (title+price) — may miss variants of the same product

## Git Workflow

- Branch: `main` (single branch)
- Remote: `origin` -> `github.com/giraffe-horizon/deal-hunter`
- Commit with meaningful messages: `feat:`, `fix:`, `chore:`, `docs:`

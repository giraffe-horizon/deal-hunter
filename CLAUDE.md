# CLAUDE.md — Instructions for Claude Code

## Project

**Deal Hunter** — universal multi-source deal monitor. Scans various sources (Pepper.pl, Ceneo.pl, Proshop.pl, any website via generic web scraper), scores offers using a YAML-driven scoring engine (with regex support), tracks price changes, and sends alerts to Telegram + Notion.

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
sources/pepper.py       Pepper.pl scraper (Vue3 JSON + HTML fallback)
sources/ceneo.py        Ceneo.pl scraper (search results)
sources/proshop.py      Proshop.pl scraper (search results)
sources/web.py          Generic web scraper (configurable CSS selectors from YAML)
filters/base.py         Base scoring engine (score_rules, penalties, budget, temperature, regex)
filters/bike_filter.py  Extended scorer for bikes (sizes, colors, tires, race keywords)
notifiers/telegram.py   Telegram Bot API with retry + rate limiting
notifiers/notion.py     Notion API (categories from profile, optional per profile)
utils/validation.py     YAML profile validation (types, required fields, sanity checks)
profiles/*.yaml         Product profiles (gitignored except example.yaml)
profiles/example.yaml   Example profile documenting ALL available options
docs/creating-profiles.md  Profile creation guide
state/*.json            Persistent state per profile (what's been seen, 14-day TTL)
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
- `notion` — `{database_id, categories}` or `null` (categories map names to keyword lists)

### Plugin Registration
- Sources: `sources/__init__.py` -> `SOURCE_REGISTRY = {"pepper": PepperSource, ...}`
- Filters: `filters/__init__.py` -> `FILTER_REGISTRY = {"bike_filter.BikeFilter": BikeFilter, ...}`

## How to Run

```bash
source venv/bin/activate
python deal_hunter.py --profile bikes --verify   # test without saving state
python deal_hunter.py --profile nas_hdd           # normal run
python deal_hunter.py --all                        # all profiles
python deal_hunter.py --list                       # list profiles
python deal_hunter.py --profile bikes --validate  # validate profile without running
```

## Environment Variables

File `.env` (not committed):
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
NOTION_API_KEY_PATH=~/.config/notion/api_key
```

## Adding a New Source

1. Create `sources/new_source.py`
2. Class inherits from `Source`, implements `fetch_deals(config) -> list[Deal]`
3. Use `self._fetch_page(url)` and `self._rate_limit()` from the base class
4. Register in `sources/__init__.py`: `SOURCE_REGISTRY["new_source"] = NewSource`
5. Add source config to profile YAML

**Alternatively:** use the generic web scraper (`sources/web.py`) — no code needed, configure CSS selectors in YAML:
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
          link: "a@href"        # @attr syntax — extracts HTML attribute
          image: "img@src"
```

## Adding a New Profile

**IMPORTANT:** User profiles are NOT in the repo (gitignored). Only `profiles/example.yaml` is committed.

1. Create `profiles/name.yaml` — use `profiles/example.yaml` as a template
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
- **Notion property names:** Polish (they match the database schema)
- **Logging:** `logging` module, not `print()` (exception: `--verify` mode prints to stdout)
- **Error handling:** graceful degradation — one source fails -> rest continue, one notifier fails -> rest continue
- **Rate limiting:** each source has min 2s between requests, Telegram 1.5s + retry on 429
- **State:** per-profile JSON in `state/`, 14-day TTL, cross-source dedup by title+price
- **Secrets:** NEVER in code — `.env` + `python-dotenv`, `.gitignore` protects `.env`

## Price Tracking

Deal Hunter automatically tracks prices of known offers. State saved in `state/<profile>_state.json` under the `"prices"` key.
- If a deal reappears with a lower price (>10% drop or >50 PLN) -> extra plus in the alert
- Price increase -> logged, but no minus added
- No configuration needed — works out of the box

## Profile Validation

`utils/validation.py` -> `validate_profile(profile) -> list[str]`

Checks: required fields, data types, sanity (budget.min < budget.max, score_threshold < score_threshold_alert).

CLI: `python deal_hunter.py --profile bikes --validate`

## Tests

No unit tests yet (TODO). Manual testing:
```bash
# Verify scoring — shows all deals with scores
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

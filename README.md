# Deal Hunter

**Universal multi-source deal monitor.** Define what you're looking for in a YAML profile — Deal Hunter scans multiple sources, scores every offer with a configurable scoring engine (with regex support), tracks price changes, and sends alerts to Telegram + optionally Notion.

[![CI](https://github.com/giraffe-horizon/deal-hunter/actions/workflows/ci.yml/badge.svg)](https://github.com/giraffe-horizon/deal-hunter/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

---

## Why Deal Hunter?

You're looking for a specific product — the right bike, the right headphones, the right NAS drive — and it's scattered across dozens of websites, each with different layouts, search UIs, and pricing formats. Checking them manually every day is tedious and you inevitably miss the best deals. Deal Hunter watches all of them for you, scores every offer against your personal criteria, and only pings you when something is actually worth your attention.

**Works with ANY website** — point Deal Hunter at any page with product listings and configure CSS selectors in YAML. No code required. Polish deal sites (Pepper.pl, Ceneo.pl, Proshop.pl) and bike shops (Canyon, Rowertour, Veloshop, and more) come as included batteries with pre-built store definitions.

<!-- TODO: Add demo GIF — showing: `deal_hunter.py --profile headphones --verify` with colorful scored output, then a Telegram notification screenshot -->

---

## Features

- **Works with any website** — generic web scraper with configurable CSS selectors, or declarative YAML store definitions (no Python needed)
- **9 built-in sources** — Pepper.pl, Ceneo.pl, Proshop.pl, Canyon, Rowertour, Veloshop, Centrumrowerowe, Sprint-Rowery — included as batteries
- **Smart scoring engine** — keyword rules, penalties, budget checks, regex patterns, temperature bonuses
- **Custom filters** — extend the base scorer with domain-specific logic (e.g., bike sizes, tire widths)
- **Price tracking** — automatic price drop detection across runs
- **Telegram alerts** — tiered notifications with rate limiting and retry
- **Notion integration** — save deals to a Notion database with categories
- **YAML profiles** — one profile per product type, fully declarative
- **Interactive setup** — `--init` walks you through creating a new profile
- **Profile validation** — catch config errors before running
- **Docker support** — run on a schedule with docker-compose, zero system dependencies
- **Graceful degradation** — one source fails, the rest keep working
- **Cross-source dedup** — fuzzy title+price matching prevents duplicate alerts

## Quick Start

```bash
# Clone
git clone https://github.com/giraffe-horizon/deal-hunter.git
cd deal-hunter

# Setup environment
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"       # editable install with dev dependencies

# Try the example profile (no Telegram needed)
python deal_hunter.py --profile headphones --verify

# Configure for real use
cp .env.example .env
# Edit .env — add your Telegram bot token and chat ID

# Create your own profile interactively
python deal_hunter.py --init

# Run for real
python deal_hunter.py --profile my_product
```

> The included `examples/headphones.yaml` is a fully working profile that searches Pepper.pl and Ceneo.pl for wireless ANC headphones. Use `--verify` to see scored results without sending notifications.

## Architecture

```
deal-hunter/
├── deal_hunter.py              Main orchestrator (CLI entry point)
├── sources/                    Source plugins
│   ├── __init__.py             Source registry + YAML auto-discovery
│   ├── base.py                 Base Source class + Deal dataclass
│   ├── pepper.py               Pepper.pl — Vue3 JSON + HTML fallback (too complex for YAML)
│   ├── web.py                  Generic web scraper (CSS selectors from profile)
│   └── yaml_source.py          Universal YAML-driven source engine
├── stores/                     Declarative store definitions (auto-discovered)
│   ├── ceneo.yaml, proshop.yaml, canyon.yaml, etc.
│   └── README.md               How to add a store in 5 minutes
├── filters/                    Scoring engines
│   ├── base.py                 Base scorer (keywords, regex, budget, temperature)
│   └── bike_filter.py          Extended scorer: sizes, colors, tires
├── notifiers/                  Notification backends
│   ├── telegram.py             Telegram Bot API (retry + rate limiting)
│   └── notion.py               Notion API (categories from profile)
├── utils/                      Utilities
│   ├── validation.py           YAML profile validation
│   └── init_profile.py         Interactive profile creator (--init)
├── examples/                   Example profiles (committed to repo)
│   └── headphones.yaml         Working example — ANC headphones
├── profiles/                   User profiles (YAML, gitignored)
├── tests/                      Test suite
│   └── fixtures/               HTML fixtures for parser tests
├── docs/                       Documentation
│   └── creating-profiles.md    Profile creation guide
├── state/                      Persistent state per profile (JSON, 14-day TTL)
├── Makefile                    Dev commands: install, test, lint, typecheck
├── Dockerfile                  Docker image definition
├── docker-compose.yml          Docker Compose service config
├── docker/entrypoint.sh        Container entrypoint (cron setup)
├── .env                        Secrets (not committed)
├── .env.example                Environment variable template
├── pyproject.toml              Project metadata + tool config
├── CONTRIBUTING.md             Contribution guide
├── CHANGELOG.md                Release history
├── SECURITY.md                 Vulnerability reporting
└── LICENSE                     MIT
```

## Usage

```bash
# Create a new profile interactively
python deal_hunter.py --init

# Run a single profile
python deal_hunter.py --profile my_product

# Verify mode — shows ALL deals with scoring breakdown, no state changes
python deal_hunter.py --profile my_product --verify

# Validate profile config without running
python deal_hunter.py --profile my_product --validate

# Run all profiles
python deal_hunter.py --all

# List available profiles
python deal_hunter.py --list

# Show version
python deal_hunter.py --version
```

### Cron Setup

```bash
# Every 30 minutes
*/30 * * * * cd ~/Projects/deal-hunter && venv/bin/python deal_hunter.py --profile my_product >> deal_hunter.log 2>&1

# Or run all profiles at once
*/30 * * * * cd ~/Projects/deal-hunter && venv/bin/python deal_hunter.py --all >> deal_hunter.log 2>&1
```

### Running with Docker

Run Deal Hunter on a schedule with zero system dependencies:

```bash
# Configure
cp .env.example .env
# Edit .env with your Telegram bot token and chat ID
# Put your profiles in profiles/

# Start (runs --all every 30 minutes by default)
docker compose up -d

# Custom schedule (every 15 minutes)
CRON_SCHEDULE="*/15 * * * *" docker compose up -d

# One-off run inside the container
docker compose run --rm deal-hunter --profile my_product --verify

# View logs
docker compose logs -f
```

The container mounts `profiles/` and `state/` as volumes, so your data persists across restarts.

## Profiles

Each profile is a YAML file in `profiles/` that defines **what to search** and **how to score** results. One profile = one product type.

User profiles are gitignored. See [docs/creating-profiles.md](docs/creating-profiles.md) for how to create one.

### Minimal Profile

```yaml
name: headphones
emoji: "🎧"

sources:
  pepper:
    urls:
      - "https://www.pepper.pl/search?q=headphones+anc"
  ceneo:
    queries:
      - "wireless headphones ANC"

budget:
  min: 200
  max: 600

score_rules:
  "noise cancelling": 30
  sony: 40
  bose: 35

penalties:
  wired: -50
  gaming: -30

score_threshold: 40
score_threshold_alert: 70

telegram:
  topic_id: 31
  max_alerts: 5

notion: null
```

## Sources

| Source | Category | Type | Config |
|--------|----------|------|--------|
| **Pepper.pl** | Deal aggregator | Python | `urls` — list of URLs to scrape |
| **Ceneo.pl** | Price comparison | YAML store | `queries` — list of search queries |
| **Proshop.pl** | Online store | YAML store | `queries` — list of search queries |
| **Canyon.com** | Bike manufacturer | YAML store | `urls` — outlet/catalog pages |
| **Rowertour.com** | Bike shop | YAML store | `urls` — category/search pages |
| **Veloshop.pl** | Bike shop (OpenCart) | YAML store | `urls` — category/search pages |
| **Centrumrowerowe.pl** | Bike shop | YAML store | `urls` — category/search pages |
| **Sprint-Rowery.pl** | Bike shop | YAML store | `urls` — category pages, `max_pages` (default 5) |
| **Web** (generic) | Any website | Python | `sites` — list of sites with CSS selectors |

All sources have built-in rate limiting (min 2s between requests), retry with exponential backoff, and graceful degradation.

### Generic Web Scraper

Scrape any website without writing code — just define CSS selectors in your profile:

```yaml
sources:
  web:
    sites:
      - url: "https://example.com/deals"
        base_url: "https://example.com"
        selectors:
          container: "div.product-card"
          title: "h2.product-name"
          price: "span.price"
          link: "a.product-link@href"    # @attr syntax extracts HTML attribute
          image: "img.product-img@src"
```

## Scoring System

The scoring engine processes each deal in order:

| Step | Rule | Effect |
|------|------|--------|
| 1 | **Excluded words** | Hard reject if any match |
| 2 | **Required any** | Hard reject if none match |
| 3 | **Score rules** | `+points` per keyword match in title+description |
| 4 | **Penalties** | `-points` per keyword match |
| 5 | **Budget** | In range: +5 / Too cheap: -20 / Too expensive: -30 |
| 6 | **Temperature** | Hot (≥100°): +10 / Warm (≥50°): +5 / Cold (<-10°): -10 |

### Regex Support

Keywords can be regex patterns using `r/pattern/` syntax:

```yaml
score_rules:
  "r/\\b(xl|58|59|60)\\b/": 10    # matches whole words
  "r/\\d{2}\\s*mm/": 5             # matches e.g. "32 mm", "28mm"
```

Regex works in: `score_rules`, `penalties`, `excluded_words`, `required_any`.

### Alert Tiers

| Score | Tier | Emoji |
|-------|------|-------|
| ≥ `score_threshold_alert` | TOP DEAL | 🔥🔥🔥 |
| ≥ `score_threshold` | DEAL | 🔥 |
| ≥ 20 | MAYBE | 🤔 |
| < 20 | NO MATCH | ❌ |

### Price Tracking

Deal Hunter automatically tracks prices across runs. If a deal reappears with a lower price (>10% drop or >50 PLN), the alert includes the price drop info. No configuration needed.

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | Yes |
| `TELEGRAM_CHAT_ID` | Telegram chat/group ID | Yes |
| `NOTION_API_KEY_PATH` | Path to Notion API key file | No (only if using Notion) |

## Adding a New Source

1. Create `sources/my_source.py` — class inheriting from `Source`
2. Implement `fetch_deals(config) -> list[Deal]`
3. Use `self._fetch_page(url)` and `self._rate_limit()` from the base class
4. Register in `sources/__init__.py`: `SOURCE_REGISTRY["my_source"] = MySource`

**Or** use the generic web scraper — no code needed, just CSS selectors in YAML.

## Adding a Custom Filter

1. Create `filters/my_filter.py` — class inheriting from `BaseFilter`
2. Override `score_deal(deal) -> ScoreResult` — **always call `super().score_deal(deal)` first**
3. Access custom data via `self.profile.get("custom_data", {})`
4. Register in `filters/__init__.py`: `FILTER_REGISTRY["my_filter.MyFilter"] = MyFilter`
5. Set `custom_filter: "my_filter.MyFilter"` in your profile YAML

## Running Tests Locally

```bash
source venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests (with coverage)
make test

# Or with coverage report
python -m pytest tests/ -v --cov=sources --cov=filters --cov=deal_hunter --cov-report=term-missing

# Linting
make lint

# Type checking
make typecheck

# Verify example profile
make verify-example
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and how to add sources/filters.

## License

MIT — see [LICENSE](LICENSE).

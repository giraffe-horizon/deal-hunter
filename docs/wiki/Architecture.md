# Architecture

Technical overview for contributors.

## Directory Structure

```
deal-hunter/
├── deal_hunter.py              Orchestrator: profile → sources → scoring → notify
├── sources/
│   ├── base.py                 Base Source class + Deal dataclass
│   ├── __init__.py             Source registry + YAML auto-discovery
│   ├── pepper.py               Pepper.pl (Vue3 JSON + HTML fallback)
│   ├── web.py                  Generic web scraper (profile-configured CSS)
│   └── yaml_source.py          Universal YAML-driven source engine
├── stores/                     Declarative store definitions (auto-discovered)
│   ├── ceneo.yaml
│   ├── proshop.yaml
│   ├── canyon.yaml
│   ├── rowertour.yaml
│   ├── centrumrowerowe.yaml
│   ├── sprint.yaml
│   ├── veloshop.yaml
│   └── README.md
├── filters/
│   ├── base.py                 Scoring engine (keywords, budget, temperature)
│   └── bike_filter.py          Extended scorer for bikes
├── notifiers/
│   └── telegram.py             Telegram Bot API with retry
├── utils/
│   ├── validation.py           Profile YAML validation
│   └── init_profile.py         Interactive profile creator
├── profiles/*.yaml             User profiles (gitignored)
├── examples/headphones.yaml    Example profile (committed)
├── state/*.json                Persistent state per profile
├── tests/                      pytest test suite
└── docs/                       Documentation
```

## Data Flow

```
1. Load profile YAML
        ↓
2. For each source in profile:
   → Instantiate source (Python class or YAML-driven)
   → source.fetch_deals(config) → list[Deal]
        ↓
3. Deduplicate across sources (title normalization)
        ↓
4. Score each deal (BaseFilter or custom filter)
        ↓
5. Check price changes against state
        ↓
6. Filter by thresholds (hot/good/meh)
        ↓
7. Notify (Telegram)
        ↓
8. Save state (seen deals, prices, timestamps)
```

## Key Abstractions

### Deal (dataclass)
```python
@dataclass
class Deal:
    id: str             # "{source}:{native_id}"
    title: str
    price: int          # PLN, 0 if unknown
    regular_price: int  # Original price (0 if no discount)
    link: str
    source: str
    description: str
    temperature: int    # Pepper only
    image_url: str
    published_at: str   # ISO datetime
```

### Source (ABC)
```python
class Source(ABC):
    def fetch_deals(self, config: dict) -> list[Deal]: ...
```

All sources inherit from `Source` which provides:
- `_fetch_page(url)` — HTTP GET with rate limiting, retry, headers
- `_rate_limit()` — enforces `MIN_REQUEST_INTERVAL` (2s)
- `extract_price(text)` — European price format parser

### Source Registry

`sources/__init__.py` maintains `SOURCE_REGISTRY: dict[str, type[Source]]`:
- Python sources registered explicitly (pepper, web)
- YAML stores auto-discovered from `stores/*.yaml` at import time
- YAML takes priority over Python for same name

### YAML Source Engine

`yaml_source.py` is a factory that creates Source subclasses from YAML definitions. It supports three parsing strategies:
1. **CSS** — extract fields using CSS selectors
2. **JSON-LD** — parse `schema.org/Product` from `<script type="application/ld+json">`
3. **GTM** — parse Google Tag Manager `dataLayer` product impressions

Strategies are tried in order; first with results wins.

### ScoreResult
```python
@dataclass
class ScoreResult:
    score: int              # Final score
    plus: list[str]         # Positive factors
    minus: list[str]        # Negative factors
    rejected: bool          # Hard reject?
    reject_reason: str      # Why rejected
```

## State Management

Each profile has a JSON state file in `state/`:
- Tracks seen deal IDs (14-day TTL)
- Stores last known price per deal (for price change detection)
- Auto-migrates from older state formats

## Adding a Store

See [Adding a Store](Adding-a-Store.md) — create a YAML file, no Python needed.

## Adding a Python Source

For sources too complex for YAML (like Pepper's Vue3 parsing):

1. Create `sources/my_source.py` with a class extending `Source`
2. Implement `fetch_deals(config) -> list[Deal]`
3. Register in `sources/__init__.py`

See `sources/pepper.py` as a reference.

## Testing

```bash
# All tests
make test

# Specific test file
pytest tests/test_yaml_source.py -v

# With coverage
pytest --cov=. --cov-report=term-missing
```

Tests use HTML fixtures in `tests/fixtures/` for parser testing — no network calls needed.

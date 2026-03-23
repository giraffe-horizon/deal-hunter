# Creating Profiles — Guide

## Table of Contents

1. [Introduction](#introduction)
2. [Quick Start](#quick-start)
3. [YAML File Structure](#yaml-file-structure)
4. [Data Sources](#data-sources)
5. [Scoring System](#scoring-system)
6. [Custom Filters](#custom-filters)
7. [Notifications](#notifications)
8. [Examples](#examples)
9. [FAQ and Tips](#faq-and-tips)

---

## Introduction

A profile is a YAML file in the `profiles/` directory that defines **what you're searching for** and **how to evaluate offers**. One profile = one product type (e.g., bikes, hard drives, headphones).

How it works:
1. Deal Hunter loads the profile
2. Scans the configured sources (Pepper, Ceneo, Proshop, web)
3. Each found offer goes through the scoring engine
4. Offers above the threshold -> alert on Telegram (+ optionally Notion)
5. State is saved locally -> the same offers won't alert again

User profiles **are not committed to the repo** (`.gitignore`). Create your own from the minimal template below.

## Quick Start

Create `profiles/my_product.yaml` with the following minimal template:

```yaml
name: my_product
emoji: "🔍"

sources:
  pepper:
    urls:
      - "https://www.pepper.pl/search?q=your+search+query"

budget:
  min: 100
  max: 500

score_rules:
  "desired keyword": 30

penalties:
  "unwanted keyword": -30

score_threshold: 40
score_threshold_alert: 70

telegram:
  topic_id: 0
  max_alerts: 5

notion: null
```

Then test it:

```bash
# Test (--verify shows scoring without sending alerts)
python deal_hunter.py --profile my_product --verify

# Run normally
python deal_hunter.py --profile my_product
```

## YAML File Structure

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Profile name (used in `--profile name`) |
| `emoji` | string | Emoji shown in Telegram alerts |
| `sources` | dict | Source configuration (at least one) |
| `budget` | dict | Price range `{min, max}` in PLN |
| `score_rules` | dict | Keywords -> positive points |
| `penalties` | dict | Keywords -> negative points |
| `score_threshold` | int | Minimum score to trigger an alert |
| `score_threshold_alert` | int | Score for "top deal" tier 🔥🔥🔥 |
| `telegram` | dict | Telegram notification config |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `required_any` | list | `[]` | At least one word must match (hard reject) |
| `excluded_words` | list | `[]` | Any word matches -> hard reject |
| `custom_filter` | string | `null` | Custom filter class name |
| `custom_data` | dict | `{}` | Arbitrary data for custom filter |
| `currency` | string | `PLN` | Currency code for alerts |
| `notion` | dict/null | `null` | Notion config (`null` = disabled) |

### Budget

```yaml
budget:
  min: 400   # below -> -20 point penalty
  max: 900   # above -> -30 point penalty
             # in range -> +5 point bonus
```

Budget affects scoring:
- **In range**: +5 points
- **Too cheap** (below min): -20 points (likely a different/inferior product)
- **Too expensive** (above max): -30 points

---

## Data Sources

Four sources are available. You can use one, two, or all of them.

### Pepper.pl

Deal aggregator where users post deals and the community votes (temperature).

```yaml
sources:
  pepper:
    urls:
      - "https://www.pepper.pl/search?q=your+search+query"
      - "https://www.pepper.pl/grupa/category-name"
```

**Config:** List of URLs — can be search pages or category pages.

**Advantages:**
- Deal temperature (community-driven quality signal)
- Broad coverage — many stores in one place

**Tips:**
- Add multiple query variants (synonyms, model names)
- You can add pagination: `?page=2`, `?page=3`
- Don't overdo it — rate limiting protects against bans

### Ceneo.pl

Price comparison engine — aggregates prices from many stores.

```yaml
sources:
  ceneo:
    queries:
      - "product name"
      - "brand model"
```

**Config:** List of text search queries.

**Advantages:**
- Prices from many stores
- Great for specific products (known brand + model)

### Proshop.pl

Online electronics store.

```yaml
sources:
  proshop:
    queries:
      - "product name"
```

**Config:** List of text search queries.

### Generic Web Scraper

Scrape any website using CSS selectors — no code needed.

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
          link: "a.product-link@href"    # @attr extracts HTML attribute
          image: "img.product-img@src"
```

### Rate Limiting

All sources have built-in protections:
- Min 2 seconds between requests
- Retry with exponential backoff on errors
- Graceful degradation — one source fails -> the rest keep working

---

## Scoring System

### How It Works

The scoring engine processes each offer in this order:

1. **Excluded words** -> if found -> hard reject (offer discarded)
2. **Required any** -> if none match -> hard reject
3. **Score rules** -> keyword in title/description -> add points
4. **Penalties** -> keyword in title/description -> subtract points
5. **Budget** -> bonus/penalty based on price
6. **Temperature** (Pepper only) -> bonus/penalty based on community votes

### Score Rules

```yaml
score_rules:
  "exact phrase": 50     # high priority
  keyword: 25             # medium
  nice_bonus: 10          # low
```

Matching is **case-insensitive** and searches for substrings in the combined title + description.

**Tips for good scoring:**

- **50+ points** — the exact model/product you're looking for
- **25-40 points** — desired features (material, technology)
- **10-20 points** — nice-to-have extras
- **5-10 points** — minor bonuses (new condition, warranty)

### Penalties

```yaml
penalties:
  unwanted_model: -40
  different_category: -50
  used: -25
```

Values **must be negative**. The more unwanted the keyword, the larger the penalty.

### Required Any

```yaml
required_any:
  - "12tb"
  - "12 tb"
```

At least **one** word from the list must appear. Otherwise the offer is rejected. Useful when searching for a specific spec (capacity, size).

### Excluded Words

```yaml
excluded_words:
  - "spam"
  - "completely_different_product"
```

If **any** word from the list appears -> offer immediately rejected. Use to filter out obvious false positives.

### Regex Support

Keywords can be regular expressions using `r/pattern/` syntax:

```yaml
score_rules:
  "r/\\b(xl|xxl|58|60)\\b/": 10   # matches whole words
  "r/\\d{2}\\s*mm/": 5             # matches e.g. "32 mm", "28mm"
```

Regex works in: `score_rules`, `penalties`, `excluded_words`, `required_any`.

### Thresholds

```yaml
score_threshold: 50        # minimum score for an alert
score_threshold_alert: 80  # score for "top deal" tier
```

**Alert tiers:**

| Score | Tier | Emoji |
|-------|------|-------|
| >= `score_threshold_alert` | TOP DEAL | 🔥🔥🔥 |
| >= `score_threshold` | DEAL | 🔥 |
| >= 20 | MAYBE | 🤔 |
| < 20 | NO MATCH | ❌ |

### Temperature Bonus (Pepper)

Pepper deals have a temperature score (community votes):
- **>= 100°** -> +10 points (hot deal, many people confirm)
- **>= 50°** -> +5 points
- **< -10°** -> -10 points (cold, probably a weak offer)

### Scoring Tips

1. **Start with `--verify`** — see scoring for all offers
2. **Iterate** — adjust points based on verify results
3. **Avoid too low threshold** — you'll get too much noise
4. **Avoid too high threshold** — you'll miss good deals
5. **Penalties matter more than you think** — good penalties filter out junk more effectively than good score_rules

---

## Custom Filters

### When Needed

The base scoring engine is enough for most cases. You need a custom filter when:
- Logic is **too complex** for simple keyword -> points (e.g., sizes per bike brand)
- You need to **parse data** from the offer (e.g., extract size from text)
- You want **additional rules** that depend on context (e.g., color + size + type)

### How to Set Up

1. Create a file in `filters/`, e.g., `filters/my_filter.py`
2. Class inherits from `BaseFilter`:

```python
from filters.base import BaseFilter, ScoreResult

class MyFilter(BaseFilter):
    def score_deal(self, deal) -> ScoreResult:
        # Base scoring first (ALWAYS call super!)
        result = super().score_deal(deal)
        if result.rejected:
            return result

        # Your additional logic
        custom = self.profile.get("custom_data", {})
        # ...
        return result
```

3. Register in `filters/__init__.py`:
```python
FILTER_REGISTRY["my_filter.MyFilter"] = MyFilter
```

4. In profile YAML:
```yaml
custom_filter: "my_filter.MyFilter"
custom_data:
  key: value
```

### Custom Data

`custom_data` is an arbitrary dict passed to the filter. Structure depends on your filter.

```yaml
custom_data:
  preferred_sizes: ["L", "XL"]
  excluded_colors:
    - "white"
    - "yellow"
```

Access in filter: `self.profile.get("custom_data", {})`.

---

## Notifications

### Telegram

```yaml
telegram:
  topic_id: 31    # Thread ID in Telegram group (optional, 0 = no thread)
  max_alerts: 5   # Max alerts per run
```

**topic_id** — if your Telegram group has threads (topics) enabled, provide the thread ID. Find it in the URL: `t.me/c/GROUPID/TOPICID`. If the group doesn't have threads -> set `0` or omit.

**max_alerts** — protects against message floods when there are many results. Highest-scoring offers are sent first.

Required variables in `.env`:
```
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=chat_or_group_id
```

### Notion

```yaml
# Disabled:
notion: null

# Enabled:
notion:
  database_id: "your-notion-database-id"
```

Deals are saved to Notion as new pages. Requires:
- `NOTION_API_KEY_PATH` configured in `.env`
- A Notion database with matching properties

### Notion Categories

Categories can be configured per profile:

```yaml
notion:
  database_id: "your-db-id"
  categories:
    "electronics": ["laptop", "phone", "tablet"]
    "audio": ["headphones", "speaker", "soundbar"]
```

If no categories are defined, the profile name is used as the category.

---

## Examples

### Simple Profile — Wireless Headphones

```yaml
name: headphones
emoji: "🎧"

sources:
  pepper:
    urls:
      - "https://www.pepper.pl/search?q=headphones+wireless+anc"
  ceneo:
    queries:
      - "wireless headphones ANC"

budget:
  min: 200
  max: 600

score_rules:
  anc: 30
  "noise cancelling": 30
  sony: 40
  "wh-1000xm": 50
  bose: 35
  sennheiser: 30
  ldac: 20
  multipoint: 15

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

### Medium Profile — NAS HDD 12TB

```yaml
name: nas_hdd
emoji: "💾"

sources:
  pepper:
    urls:
      - "https://www.pepper.pl/search?q=hdd+12tb+nas"
      - "https://www.pepper.pl/search?q=ironwolf+12tb"
  ceneo:
    queries:
      - "HDD 12TB NAS"
      - "Seagate IronWolf 12TB"
      - "WD Red Plus 12TB"
  proshop:
    queries:
      - "HDD 12TB NAS"

budget:
  min: 400
  max: 900

score_rules:
  ironwolf: 45
  "ironwolf pro": 55
  exos: 50
  ultrastar: 50
  "red plus": 40
  "red pro": 45
  cmr: 30
  nas: 25
  7200rpm: 15
  helium: 20

penalties:
  smr: -50
  refurbished: -30
  used: -25
  ssd: -60
  external: -40

required_any:
  - "12tb"
  - "12 tb"

score_threshold: 50
score_threshold_alert: 80

telegram:
  topic_id: 31
  max_alerts: 5

notion: null
```

### Advanced Profile — Bikes with Custom Filter

```yaml
name: bikes
emoji: "🚲"

sources:
  pepper:
    urls:
      - "https://www.pepper.pl/grupa/rowery"
      - "https://www.pepper.pl/search?q=rower+endurance"

budget:
  min: 10000
  max: 15000

score_rules:
  carbon: 35
  di2: 40
  endurance: 50
  gravel: 25
  domane: 45
  roubaix: 45
  ultegra: 20
  disc: 15
  tubeless: 10

penalties:
  tcr: -50
  tarmac: -50
  aeroad: -60

score_threshold: 70
score_threshold_alert: 120

# Custom filter — extends base scoring with size and color logic
custom_filter: "bike_filter.BikeFilter"

# Data for the custom filter
custom_data:
  brand_sizes:
    trek: ["l", "60", "61"]
    canyon: ["xl", "2xl"]
    giant: ["xl", "ml"]
  generic_good_sizes: ["l", "xl", "xxl", "58", "59", "60", "61", "62"]
  excluded_colors:
    - "white"
    - "yellow"
    - "neon"
  race_keywords:
    - "aero"
    - "race"
    - "sprint"

telegram:
  topic_id: 31
  max_alerts: 5

notion:
  database_id: "your-notion-database-id"
```

---

## FAQ and Tips

### How do I find the `topic_id` on Telegram?

Open a thread in your Telegram group (in a browser or by clicking the link). The URL looks like:
`https://t.me/c/1234567890/31` — the last number (31) is the `topic_id`.

### How many sources should I use?

Depends on the product:
- **Deals/promotions** -> Pepper (community filters for you)
- **Price comparison** -> Ceneo (many stores)
- **Specific store** -> Proshop
- **Best coverage** -> all three

### Why does a good offer have a low score?

Check `--verify`:
```bash
python deal_hunter.py --profile my_product --verify
```

Common causes:
- Missing keyword in `score_rules` (add it)
- A penalty unintentionally matches (e.g., "blue" in a blue model name)
- Offer is outside budget
- `required_any` doesn't match (check spelling/variants)

### How to set good thresholds?

1. Run `--verify` and look at score distribution
2. Set `score_threshold` to cut off noise (bottom ~30% of offers)
3. Set `score_threshold_alert` to top ~10% — these will be your "top deals"
4. Better to start with lower thresholds and raise them than to miss a good deal

### Can I have a profile without penalties?

Yes — `penalties` can be empty (`penalties: {}`), but you lose an important tool for filtering junk. Recommended to add at least a few obvious exclusions.

### How to test a profile without sending alerts?

Use the `--verify` flag:
```bash
python deal_hunter.py --profile my_product --verify
```

Shows ALL found offers with full scoring breakdown, without saving state or sending notifications.

### Can I use multiple Pepper URLs?

Yes, more URLs = better coverage. But keep rate limiting in mind — 10-15 URLs is a reasonable maximum.

### How does deduplication work?

Deal Hunter saves state per profile in `state/`. Each offer is identified by `{source}:{native_id}`. State has a 14-day TTL — after that, an offer can alert again (likely already inactive).

Additionally, there's cross-source dedup by `title + price` with fuzzy matching — the same offer from Pepper and Ceneo won't alert twice.

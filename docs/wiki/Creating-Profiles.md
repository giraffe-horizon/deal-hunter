# Creating Profiles

Profiles define **what** to search for, **where** to search, and **how** to score results.

## Quick Way: Interactive Wizard

```bash
python deal_hunter.py --init
```

## Manual Way: YAML File

Create `profiles/your_name.yaml`:

```yaml
name: "Wireless Headphones 🎧"

sources:
  ceneo:
    queries:
      - "słuchawki bezprzewodowe"
      - "headphones bluetooth ANC"
  pepper:
    queries:
      - "słuchawki"

scoring:
  score_rules:
    "sony": 15
    "bose": 15
    "anc": 10
    "bluetooth 5": 5
    "r/\\bwh-?1000xm[45]\\b/": 20    # regex: WH-1000XM4 or XM5

  penalties:
    "chiński": -10
    "używane": -15
    "case only": -20

  excluded_words:
    - "etui"
    - "kabel"
    - "replacement"

  required_any:
    - "słuchawki"
    - "headphones"
    - "earbuds"

  budget_min: 200
  budget_max: 800

  thresholds:
    hot: 30
    good: 15
    meh: 0

notifications:
  telegram:
    enabled: true
    topic_id: null           # null = DM, number = group topic
```

## Profile Fields Reference

### `name` (required)
Display name. Supports emoji.

### `sources` (required)
Which stores to scan. Each source has its own config:

**Search-type sources** (ceneo, proshop):
```yaml
sources:
  ceneo:
    queries:
      - "search term 1"
      - "search term 2"
    category: "electronics"    # optional: Ceneo category slug
```

**Catalog-type sources** (canyon, veloshop, etc.):
```yaml
sources:
  canyon:
    urls:
      - "https://canyon.com/en-pl/outlet/road-bikes/"
```

**Pepper** (search + temperature):
```yaml
sources:
  pepper:
    queries:
      - "keyword"
    min_temperature: 50    # optional: skip cold deals
```

**Generic web scraper**:
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

### `scoring` (required)

#### `score_rules`
Keywords → points. Matched against title + description (case-insensitive):
```yaml
score_rules:
  "premium keyword": 15
  "good keyword": 10
  "r/\\bregex pattern\\b/": 20    # prefix with r/ for regex
```

#### `penalties`
Negative scoring:
```yaml
penalties:
  "bad keyword": -10
  "very bad": -20
```

#### `excluded_words`
Hard reject — deal is completely ignored:
```yaml
excluded_words:
  - "replacement part"
  - "case only"
```

#### `required_any`
At least ONE must match, or deal is rejected:
```yaml
required_any:
  - "headphones"
  - "słuchawki"
```

#### `budget_min` / `budget_max`
Price range in PLN:
- In budget: +5 points
- Below min: -20 points ("too cheap, probably junk")
- Above max: -30 points ("over budget")

#### `thresholds`
Score cutoffs for alert tiers:
```yaml
thresholds:
  hot: 30     # 🔥 immediate alert
  good: 15    # ✅ good deal
  meh: 0      # 💤 borderline, still reported
```

Deals scoring below `meh` are silently dropped.

### `notifications` (optional)

```yaml
notifications:
  telegram:
    enabled: true
    topic_id: 12345    # group topic ID, null for DM
```

If omitted, no notifications are sent (useful with `--verify`).

### `custom_filter` (optional)
For advanced scoring beyond keyword matching:
```yaml
custom_filter: "bike_filter.BikeFilter"
custom_data:
  preferred_sizes: ["XL", "58", "59"]
  preferred_tire_sizes: ["700x28", "700x32"]
```

## Testing Your Profile

```bash
# Check YAML syntax and required fields
python deal_hunter.py --profile my_product --validate

# Run full pipeline, print results, skip notifications
python deal_hunter.py --profile my_product --verify
```

## Tips

- Start with `--verify` and tune `score_rules` until hot deals are actually hot
- Use `required_any` to filter noise (e.g., searching "sony" returns speakers too — require "headphones")
- Regex is powerful for model numbers: `r/\bwh-?1000xm[45]\b/` catches "WH1000XM4", "WH-1000XM5"
- Set `budget_max` slightly above your real budget — deals just over budget might negotiate down

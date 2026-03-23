# Deal Hunter 🔍

Universal multi-source deal monitor. Define product profiles in YAML, and Deal Hunter will scrape multiple sources, score deals, and notify you via Telegram and Notion.

## Architecture

```
deal_hunter.py          — Main orchestrator (CLI)
sources/                — Source plugins (Pepper, Ceneo, Proshop)
filters/                — Scoring engines (base + custom per category)
notifiers/              — Notification backends (Telegram, Notion)
profiles/               — Product profiles (YAML)
state/                  — Persistent state per profile (JSON)
```

## Usage

```bash
# Run a specific profile
python deal_hunter.py --profile bikes
python deal_hunter.py --profile nas_hdd

# Verify mode (show all deals, no state tracking)
python deal_hunter.py --profile bikes --verify

# Run all profiles
python deal_hunter.py --all

# List available profiles
python deal_hunter.py --list
```

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your tokens
```

## Profiles

- **bikes** 🚲 — Endurance/gravel bikes from Pepper.pl (10-15k PLN)
- **nas_hdd** 💾 — 12TB NAS HDDs from Pepper, Ceneo, Proshop (400-900 PLN)

## Adding a new profile

Create `profiles/your_product.yaml` with:
- `name`, `emoji` — identification
- `sources` — dict of source configs
- `budget` — {min, max} price range
- `score_rules` — keyword → positive points
- `penalties` — keyword → negative points
- `score_threshold` / `score_threshold_alert` — alert thresholds
- `telegram` — {topic_id, max_alerts}
- `notion` — {database_id} or null

## Sources

| Source | Type | Config |
|--------|------|--------|
| Pepper.pl | Deal aggregator | `urls` list |
| Ceneo.pl | Price comparison | `queries`, `category` |
| Proshop.pl | Online store | `queries`, `category` |

## License

Private project.

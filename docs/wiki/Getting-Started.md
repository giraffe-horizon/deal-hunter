# Getting Started

## Requirements

- Python 3.12+
- Telegram bot token (optional, for alerts)

## Installation

```bash
# Clone
git clone https://github.com/giraffe-horizon/deal-hunter.git
cd deal-hunter

# Virtual environment
python3 -m venv venv
source venv/bin/activate

# Install
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with your tokens (or leave empty for --verify mode)
```

## Your First Scan

### Option A: Use the example profile

```bash
# See what the example profile finds (no Telegram needed)
python deal_hunter.py --profile headphones --verify
```

### Option B: Create your own profile interactively

```bash
python deal_hunter.py --init
```

This walks you through:
1. Naming your profile
2. Choosing sources (stores)
3. Setting search queries or URLs
4. Defining budget range
5. Adding scoring keywords
6. Configuring notifications

### Option C: Write YAML manually

See [Creating Profiles](Creating-Profiles.md) for the full guide.

## Verify Before Running

Always test with `--verify` first — it runs the full pipeline without sending notifications:

```bash
python deal_hunter.py --profile my_product --verify
```

You'll see scored deals in your terminal with a breakdown of why each deal got its score.

## Validate Your Profile

```bash
python deal_hunter.py --profile my_product --validate
```

Catches YAML errors, missing required fields, and logic issues (like budget min > max).

## Run for Real

```bash
# Single run with notifications
python deal_hunter.py --profile my_product

# Run all profiles
python deal_hunter.py --all
```

## Set Up Cron

```bash
# Every 30 minutes
crontab -e
*/30 * * * * cd /path/to/deal-hunter && venv/bin/python deal_hunter.py --all >> /var/log/deal-hunter.log 2>&1
```

Or use [Docker](Docker-Deployment.md) for a containerized setup.

## Next Steps

- [Adding a Store](Adding-a-Store.md) — Monitor a website not yet supported
- [Scoring Engine](Scoring-Engine.md) — Fine-tune your deal detection
- [Docker Deployment](Docker-Deployment.md) — Production-ready setup

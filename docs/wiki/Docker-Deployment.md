# Docker Deployment

Run Deal Hunter as an automated cron job in Docker.

## Quick Start

```bash
# Configure
cp .env.example .env
# Edit .env with your Telegram token

# Create a profile
mkdir -p profiles
# Copy and edit a profile, or use --init first:
python deal_hunter.py --init

# Build and run
docker-compose up -d
```

## docker-compose.yml

```yaml
services:
  deal-hunter:
    build: .
    env_file: .env
    environment:
      - CRON_SCHEDULE=*/30 * * * *    # Every 30 minutes
      - TZ=Europe/Warsaw
    volumes:
      - ./profiles:/app/profiles       # Your search profiles
      - ./state:/app/state             # Deal history (persistent)
      - ./.env:/app/.env:ro            # Secrets
    restart: unless-stopped
```

## Configuration

### CRON_SCHEDULE
Standard cron expression. Default: `*/30 * * * *` (every 30 minutes).

Examples:
- `*/15 * * * *` — every 15 minutes
- `0 */2 * * *` — every 2 hours
- `0 8,12,18 * * *` — at 8:00, 12:00, 18:00
- `0 * * * 1-5` — every hour, weekdays only

### TZ
Timezone for cron schedule. Default: `UTC`.

### Volumes

| Mount | Purpose | Required |
|-------|---------|----------|
| `./profiles:/app/profiles` | Your YAML profiles | Yes |
| `./state:/app/state` | Deal history & dedup state | Yes (for persistence) |
| `./.env:/app/.env:ro` | Secrets (Telegram token, etc.) | Yes |

## One-off Commands

Run a single scan without cron:

```bash
# Verify a profile
docker-compose run --rm deal-hunter --profile my_product --verify

# Validate a profile
docker-compose run --rm deal-hunter --profile my_product --validate

# List available profiles
docker-compose run --rm deal-hunter --list

# Run all profiles once
docker-compose run --rm deal-hunter --all
```

## Logs

```bash
# Follow cron output
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail 100
```

## Updating

```bash
docker-compose down
git pull
docker-compose build --no-cache
docker-compose up -d
```

## Security Notes

- The container runs as non-root user `dealer`
- Uses [supercronic](https://github.com/aptible/supercronic) instead of system cron (no root needed)
- Uses [tini](https://github.com/krallin/tini) as PID 1 for proper signal handling
- Secrets in `.env` are mounted read-only
- No ports are exposed (outbound-only: HTTP to stores, Telegram API)

## Troubleshooting

### Container exits immediately
Check logs: `docker-compose logs`. Usually a missing `.env` or invalid `CRON_SCHEDULE`.

### No notifications
1. Check `.env` has valid `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
2. Run `--verify` to confirm deals are found
3. Check state — already-seen deals aren't re-notified

### Profiles not found
Ensure `profiles/` directory contains your `.yaml` files and is mounted correctly.

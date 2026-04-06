# Docker Compose Full Service Setup — Design Spec

**Date:** 2026-04-06
**Roadmap item:** 1.3 Docker Compose

## Context

Deal Hunter currently has a working Dockerfile, docker-compose.yml, and entrypoint.sh, but they only run the main `--all` cron job. The systemd setup has 4 units (main cron, watchdog, digest, feedback bot) that aren't mirrored in Docker. This spec adds the missing services so Docker Compose provides a complete, self-contained deployment matching the systemd setup.

## Architecture

Two Docker services sharing a state volume:

```
deal-hunter (cron)              deal-hunter-bot
├── --all      (*/30 * * * *)   └── feedback_bot.py (long-running)
├── --watchdog (0 */1 * * *)
└── --digest   (0 8 * * 1)
         │                              │
         └──── ./state volume ──────────┘
               (deals.db, *.json)
```

Both services use the same Docker image. The bot overrides the command to run `feedback_bot.py` directly.

## Changes

### 1. Dockerfile — add missing COPY targets

Current Dockerfile is missing files needed for the bot and digest:
- Add `COPY feedback_bot.py .`
- Add `COPY storage/ storage/`
- Add `COPY visualization/ visualization/`

### 2. docker/entrypoint.sh — multi-schedule crontab

Replace the single cron line with 3 lines, each configurable via env vars:

| Env var | Default | Command |
|---------|---------|---------|
| `CRON_SCHEDULE` | `*/30 * * * *` | `deal_hunter.py --all` |
| `WATCHDOG_SCHEDULE` | `0 */1 * * *` | `deal_hunter.py --watchdog` |
| `DIGEST_SCHEDULE` | `0 8 * * 1` | `deal_hunter.py --digest` |

Also fix the env grep pattern: remove `NOTION_` (no longer exists), keep `TELEGRAM_` and `PATH`.

### 3. docker-compose.yml — add bot service

```yaml
services:
  deal-hunter:
    build: .
    container_name: deal-hunter
    restart: unless-stopped
    env_file: .env
    environment:
      - CRON_SCHEDULE=${CRON_SCHEDULE:-*/30 * * * *}
      - WATCHDOG_SCHEDULE=${WATCHDOG_SCHEDULE:-0 */1 * * *}
      - DIGEST_SCHEDULE=${DIGEST_SCHEDULE:-0 8 * * 1}
      - TZ=${TZ:-Europe/Warsaw}
    volumes:
      - ./profiles:/app/profiles
      - ./state:/app/state

  deal-hunter-bot:
    build: .
    container_name: deal-hunter-bot
    restart: unless-stopped
    env_file: .env
    environment:
      - TZ=${TZ:-Europe/Warsaw}
    command: ["python", "feedback_bot.py"]
    volumes:
      - ./profiles:/app/profiles
      - ./state:/app/state
    depends_on:
      - deal-hunter
```

### 4. Documentation

Update the Docker section in `README.md` to document:
- The two services and their roles
- Environment variables for schedule customization
- Example `docker compose up -d` usage
- How to run one-off commands: `docker compose exec deal-hunter python deal_hunter.py --list`

## SQLite Concurrency

Both services write to `state/deals.db`. SQLite WAL mode (already enabled in `storage/sqlite.py`) handles this safely — the workload is low-frequency writes (cron every 30m, bot callbacks are rare).

## Verification

1. `docker compose build` — image builds successfully
2. `docker compose up -d` — both services start
3. `docker compose logs deal-hunter` — shows "Deal Hunter cron started" with 3 schedule lines
4. `docker compose logs deal-hunter-bot` — shows bot polling started
5. `docker compose exec deal-hunter python deal_hunter.py --list` — one-off command works
6. `docker compose exec deal-hunter python deal_hunter.py --health` — health check works
7. Wait for cron trigger or run manually, verify `state/deals.db` is written

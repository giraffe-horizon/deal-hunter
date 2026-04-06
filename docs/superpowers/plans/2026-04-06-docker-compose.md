# Docker Compose Full Service Setup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Docker Compose to run all 4 systemd-equivalent services (main cron, watchdog, digest, feedback bot) as 2 containers sharing a state volume.

**Architecture:** One container runs supercronic with 3 cron lines (--all, --watchdog, --digest). A second container runs `feedback_bot.py` as a long-running process. Both share `./state` for SQLite access (WAL mode already enabled).

**Tech Stack:** Docker, docker-compose, supercronic, tini, Python 3.12

**Spec:** `docs/superpowers/specs/2026-04-06-docker-compose-design.md`

---

### Task 0: Fix CI pipeline — missing test dependencies

**Files:**
- Modify: `pyproject.toml:41-50`

CI runs `pip install -e ".[dev]"` but `[project.optional-dependencies] dev` is missing `matplotlib`, `pytest-asyncio`, and `python-telegram-bot`. This causes 16 test failures:
- 10 chart tests fail with `ImportError: matplotlib is required`
- 6 bot handler tests fail with `async def functions are not natively supported` (missing pytest-asyncio)

- [ ] **Step 1: Add missing dependencies to pyproject.toml dev extras**

In `pyproject.toml`, replace the `[project.optional-dependencies]` dev list:

```toml
[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "ruff",
    "mypy",
    "types-requests",
    "types-beautifulsoup4",
    "types-PyYAML",
    "matplotlib>=3.8",
    "python-telegram-bot>=21.0",
]
```

- [ ] **Step 2: Add pytest-asyncio mode to pyproject.toml**

The `[tool.pytest.ini_options]` section already exists at line 55. Add `asyncio_mode` to it:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"
asyncio_mode = "auto"
```

- [ ] **Step 3: Run tests locally to verify fixes**

```bash
pip install -e ".[dev]"
python -m pytest tests/test_charts.py tests/test_feedback_bot.py -v --tb=short
```
Expected: All 16 previously-failing tests pass.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "fix: add matplotlib, pytest-asyncio, python-telegram-bot to dev dependencies"
```

---

### Task 1: Fix Dockerfile — add missing COPY targets

**Files:**
- Modify: `Dockerfile:17-24`

The current Dockerfile is missing `feedback_bot.py`, `storage/`, and `visualization/` — needed for the bot service and `--digest` charts.

- [ ] **Step 1: Add missing COPY lines to Dockerfile**

After line 17 (`COPY deal_hunter.py .`), add `feedback_bot.py`. After `COPY stores/ stores/`, add `storage/` and `visualization/`:

```dockerfile
# Copy application code
COPY deal_hunter.py .
COPY feedback_bot.py .
COPY sources/ sources/
COPY filters/ filters/
COPY notifiers/ notifiers/
COPY utils/ utils/
COPY stores/ stores/
COPY storage/ storage/
COPY visualization/ visualization/
COPY examples/ examples/
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
```

- [ ] **Step 2: Verify Dockerfile builds**

Run: `docker build -t deal-hunter:test .`
Expected: Build completes successfully, no COPY errors.

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "fix: add missing COPY targets to Dockerfile (feedback_bot, storage, visualization)"
```

---

### Task 2: Extend entrypoint.sh — multi-schedule crontab

**Files:**
- Modify: `docker/entrypoint.sh`

Currently generates 1 cron line. Extend to 3 configurable schedules and fix the env grep pattern (remove dead `NOTION_` reference).

- [ ] **Step 1: Replace entrypoint.sh content**

```bash
#!/bin/bash
set -e

CRON_SCHEDULE="${CRON_SCHEDULE:-*/30 * * * *}"
WATCHDOG_SCHEDULE="${WATCHDOG_SCHEDULE:-0 */1 * * *}"
DIGEST_SCHEDULE="${DIGEST_SCHEDULE:-0 8 * * 1}"

# If called with arguments, run deal_hunter.py directly (for one-off commands)
if [ $# -gt 0 ]; then
    exec python /app/deal_hunter.py "$@"
fi

# Build environment file for cron jobs (secrets not world-readable)
umask 077
env | grep -E '^(TELEGRAM_|PATH=)' > /app/.cronenv
chmod 600 /app/.cronenv

# Build supercronic crontab with all schedules
ENV_PREFIX='export $(cat /app/.cronenv | xargs) &&'
cat > /app/crontab <<CRONTAB
$CRON_SCHEDULE cd /app && $ENV_PREFIX python deal_hunter.py --all >> /tmp/deal_hunter_cron.log 2>&1
$WATCHDOG_SCHEDULE cd /app && $ENV_PREFIX python deal_hunter.py --watchdog >> /tmp/deal_hunter_cron.log 2>&1
$DIGEST_SCHEDULE cd /app && $ENV_PREFIX python deal_hunter.py --digest >> /tmp/deal_hunter_cron.log 2>&1
CRONTAB

echo "Deal Hunter cron started:"
echo "  --all:      $CRON_SCHEDULE"
echo "  --watchdog: $WATCHDOG_SCHEDULE"
echo "  --digest:   $DIGEST_SCHEDULE"

# Run supercronic (handles signals, runs as non-root)
exec supercronic /app/crontab
```

- [ ] **Step 2: Verify entrypoint generates correct crontab**

Run: `docker build -t deal-hunter:test . && docker run --rm deal-hunter:test cat /dev/null`
This triggers the entrypoint with args, which runs `deal_hunter.py cat /dev/null` — that will fail, but it confirms the entrypoint script itself runs.

Better test — run with a quick override to just print the crontab:
```bash
docker run --rm --entrypoint bash deal-hunter:test -c '
  CRON_SCHEDULE="*/30 * * * *"
  WATCHDOG_SCHEDULE="0 */1 * * *"
  DIGEST_SCHEDULE="0 8 * * 1"
  ENV_PREFIX="export \$(cat /app/.cronenv | xargs) &&"
  echo "$CRON_SCHEDULE cd /app && $ENV_PREFIX python deal_hunter.py --all"
  echo "$WATCHDOG_SCHEDULE cd /app && $ENV_PREFIX python deal_hunter.py --watchdog"
  echo "$DIGEST_SCHEDULE cd /app && $ENV_PREFIX python deal_hunter.py --digest"
'
```
Expected: 3 cron lines printed with correct schedules and commands.

- [ ] **Step 3: Commit**

```bash
git add docker/entrypoint.sh
git commit -m "feat: extend entrypoint with watchdog and digest cron schedules"
```

---

### Task 3: Update docker-compose.yml — add bot service

**Files:**
- Modify: `docker-compose.yml`

Add the `deal-hunter-bot` service and new schedule environment variables.

- [ ] **Step 1: Replace docker-compose.yml content**

```yaml
services:
  deal-hunter:
    # image: ghcr.io/giraffe-horizon/deal-hunter:latest  # pre-built
    build: .  # or build locally
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
    # image: ghcr.io/giraffe-horizon/deal-hunter:latest  # pre-built
    build: .  # or build locally
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

- [ ] **Step 2: Verify compose config is valid**

Run: `docker compose config`
Expected: Parsed YAML output showing both services with correct settings. No errors.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add feedback bot service to docker-compose"
```

---

### Task 4: Update README.md — Docker section

**Files:**
- Modify: `README.md:144-173`

Update the "Running with Docker" section to document both services, schedule env vars, and bot commands.

- [ ] **Step 1: Replace the Docker section (lines 144-173)**

Replace from `### Running with Docker` through the line `The container mounts...` with:

```markdown
### Running with Docker

Run Deal Hunter on a schedule with zero system dependencies. Pre-built images for amd64 and arm64 (Raspberry Pi) are available on [GitHub Container Registry](https://github.com/giraffe-horizon/deal-hunter/pkgs/container/deal-hunter):

```bash
# Configure
cp .env.example .env
# Edit .env with your Telegram bot token and chat ID
# Put your profiles in profiles/

# Option 1: Use pre-built image
docker pull ghcr.io/giraffe-horizon/deal-hunter:latest

# Option 2: Build locally
# (docker-compose.yml builds by default — uncomment `image:` to use pre-built)

# Start both services (deal scanner + feedback bot)
docker compose up -d

# View logs
docker compose logs -f              # all services
docker compose logs -f deal-hunter   # cron service only
docker compose logs -f deal-hunter-bot  # bot only

# One-off commands
docker compose exec deal-hunter python deal_hunter.py --list
docker compose exec deal-hunter python deal_hunter.py --profile bikes --verify
docker compose exec deal-hunter python deal_hunter.py --health
```

**Services:**

| Service | Role | Default schedule |
|---------|------|-----------------|
| `deal-hunter` | Cron: scans deals, watchdog, digest | `--all` every 30m, `--watchdog` every 1h, `--digest` Mon 8am |
| `deal-hunter-bot` | Telegram feedback bot (long-running) | Always on |

**Schedule customization** via environment variables:

```bash
CRON_SCHEDULE="*/15 * * * *" WATCHDOG_SCHEDULE="0 */2 * * *" docker compose up -d
```

| Variable | Default | Description |
|----------|---------|-------------|
| `CRON_SCHEDULE` | `*/30 * * * *` | How often to scan all profiles |
| `WATCHDOG_SCHEDULE` | `0 */1 * * *` | How often to check run freshness |
| `DIGEST_SCHEDULE` | `0 8 * * 1` | When to send weekly price digest |
| `TZ` | `Europe/Warsaw` | Timezone for schedules |

Both containers mount `profiles/` and `state/` as volumes, so your data persists across restarts.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update Docker section with bot service and schedule config"
```

---

### Task 5: Integration test — full docker compose up

No code changes. Verify everything works end-to-end.

- [ ] **Step 1: Build and start**

```bash
docker compose build
docker compose up -d
```
Expected: Both containers start without errors.

- [ ] **Step 2: Check cron service logs**

```bash
docker compose logs deal-hunter
```
Expected output includes:
```
Deal Hunter cron started:
  --all:      */30 * * * *
  --watchdog: 0 */1 * * *
  --digest:   0 8 * * 1
```

- [ ] **Step 3: Check bot service logs**

```bash
docker compose logs deal-hunter-bot
```
Expected: Bot starts polling (may show Telegram connection errors if no valid token in .env — that's fine for this test).

- [ ] **Step 4: Test one-off command**

```bash
docker compose exec deal-hunter python deal_hunter.py --list
```
Expected: Lists available profiles (or empty list if no profiles mounted).

- [ ] **Step 5: Cleanup**

```bash
docker compose down
```

- [ ] **Step 6: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "fix: docker compose integration fixes"
```
Only if changes were needed. Skip if everything worked.

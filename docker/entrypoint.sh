#!/bin/bash
set -e

CRON_SCHEDULE="${CRON_SCHEDULE:-*/30 * * * *}"
WATCHDOG_SCHEDULE="${WATCHDOG_SCHEDULE:-0 */1 * * *}"
DIGEST_SCHEDULE="${DIGEST_SCHEDULE:-0 8 * * 1}"

# If called with arguments, run the CLI directly (for one-off commands)
if [ $# -gt 0 ]; then
    exec deal-hunter "$@"
fi

# Build environment file for cron jobs (secrets not world-readable)
umask 077
env | grep -E '^(TELEGRAM_|PATH=)' > /app/.cronenv
chmod 600 /app/.cronenv

# Build supercronic crontab with all schedules
ENV_PREFIX='export $(cat /app/.cronenv | xargs) &&'
cat > /app/crontab <<CRONTAB
$CRON_SCHEDULE cd /app && $ENV_PREFIX deal-hunter --all >> /tmp/deal_hunter_cron.log 2>&1
$WATCHDOG_SCHEDULE cd /app && $ENV_PREFIX deal-hunter --watchdog >> /tmp/deal_hunter_cron.log 2>&1
$DIGEST_SCHEDULE cd /app && $ENV_PREFIX deal-hunter --digest >> /tmp/deal_hunter_cron.log 2>&1
CRONTAB

echo "Deal Hunter cron started:"
echo "  --all:      $CRON_SCHEDULE"
echo "  --watchdog: $WATCHDOG_SCHEDULE"
echo "  --digest:   $DIGEST_SCHEDULE"

# Run supercronic (handles signals, runs as non-root)
exec supercronic /app/crontab

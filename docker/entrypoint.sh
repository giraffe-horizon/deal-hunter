#!/bin/bash
set -e

CRON_SCHEDULE="${CRON_SCHEDULE:-*/30 * * * *}"

# If called with arguments, run deal_hunter.py directly (for one-off commands)
if [ $# -gt 0 ]; then
    exec python /app/deal_hunter.py "$@"
fi

# Build environment file for cron jobs (secrets not world-readable)
umask 077
env | grep -E '^(TELEGRAM_|NOTION_|^PATH=)' > /app/.cronenv
chmod 600 /app/.cronenv

# Build supercronic crontab
echo "$CRON_SCHEDULE cd /app && export \$(cat /app/.cronenv | xargs) && python deal_hunter.py --all >> /tmp/deal_hunter_cron.log 2>&1" > /app/crontab

echo "Deal Hunter cron started: $CRON_SCHEDULE"

# Run supercronic (handles signals, runs as non-root)
exec supercronic /app/crontab

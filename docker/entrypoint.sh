#!/bin/bash
set -e

CRON_SCHEDULE="${CRON_SCHEDULE:-*/30 * * * *}"

# If called with arguments, run deal_hunter.py directly (for one-off commands)
if [ $# -gt 0 ]; then
    exec python /app/deal_hunter.py "$@"
fi

# Build cron job — run all profiles on schedule
# Pass environment variables to the cron job
env | grep -E '^(TELEGRAM_|NOTION_|PATH=)' > /app/.cronenv

CRON_CMD="$CRON_SCHEDULE cd /app && export \$(cat /app/.cronenv | xargs) && python deal_hunter.py --all >> /var/log/deal_hunter_cron.log 2>&1"

echo "$CRON_CMD" | crontab -

# Create log file
touch /var/log/deal_hunter_cron.log

echo "Deal Hunter cron started: $CRON_SCHEDULE"
echo "Logs: /var/log/deal_hunter_cron.log"

# Run cron in foreground, tailing the log
cron
exec tail -f /var/log/deal_hunter_cron.log

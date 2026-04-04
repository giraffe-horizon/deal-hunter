#!/bin/bash
# Install Deal Hunter systemd user timers.
# Usage: bash scripts/systemd/install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SYSTEMD_DIR="$HOME/.config/systemd/user"

mkdir -p "$SYSTEMD_DIR"

echo "Copying unit files to $SYSTEMD_DIR ..."
for unit in deal-hunter.service deal-hunter.timer \
            deal-hunter-watchdog.service deal-hunter-watchdog.timer \
            "deal-hunter-notify@.service"; do
    cp "$SCRIPT_DIR/$unit" "$SYSTEMD_DIR/$unit"
    echo "  -> $unit"
done

echo "Reloading systemd user daemon ..."
systemctl --user daemon-reload

echo "Enabling and starting timers ..."
systemctl --user enable --now deal-hunter.timer
systemctl --user enable --now deal-hunter-watchdog.timer

echo ""
echo "Done! Check status with:"
echo "  systemctl --user status deal-hunter.timer"
echo "  systemctl --user status deal-hunter-watchdog.timer"
echo "  systemctl --user list-timers"

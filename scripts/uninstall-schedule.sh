#!/usr/bin/env bash
#
# Remove the Sunday 08:00 weekly pipeline from launchd.
#
# Undoes scripts/install-schedule.sh: hands the job description back to
# launchd with `launchctl bootout`, then deletes the installed plist. See the
# comment block in install-schedule.sh for what launchctl is and why this is a
# launchd agent rather than a cron entry.
#
# This removes the SCHEDULE only. The repo, the commands, WheelOps, and every
# report and log already produced are left exactly where they are — you can
# still run the pipeline by hand afterwards.
#
set -euo pipefail

LABEL="com.adventurelabs.wheel-engine"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "$DOMAIN/$LABEL" || {
    echo "uninstall-schedule: launchctl bootout failed for $DOMAIN/$LABEL" >&2
    exit 1
  }
  echo "unloaded $LABEL from $DOMAIN"
else
  echo "$LABEL was not loaded"
fi

if [[ -f "$TARGET" ]]; then
  rm "$TARGET"
  echo "removed $TARGET"
else
  echo "no plist at $TARGET"
fi

echo
echo "The schedule is gone. Reports, logs and WheelOps are untouched."
echo "Run the pipeline by hand any time:"
echo "  commands/wheel-screen && commands/wheel-enrich && commands/wheel-render && commands/wheel-deliver"

#!/usr/bin/env bash
#
# Install the Sunday 08:00 weekly pipeline as a launchd user agent.
#
# MANUAL STEP. Nothing in the build runs this. Run it when you are ready for
# the pipeline to go live, and read scripts/com.adventurelabs.wheel-engine.plist
# first — it is the thing being installed.
#
# ---------------------------------------------------------------------------
# What launchctl is, and why not cron
# ---------------------------------------------------------------------------
# launchd is the macOS service manager: it starts, stops and supervises every
# background job on the system, and `launchctl` is the command that talks to it.
# A job is described by a plist and, for a per-user job like this one, lives in
# ~/Library/LaunchAgents/. `launchctl bootstrap` hands launchd that description
# and asks it to take ownership; `launchctl bootout` hands it back.
#
# cron still exists on macOS but is the wrong tool here:
#
#   * A cron job that comes due while the Mac is asleep is simply missed.
#     launchd runs a missed StartCalendarInterval job at the next opportunity,
#     which matters for a schedule that fires once a week — a sleeping laptop
#     at 08:00 on Sunday would silently cost the whole run.
#   * cron predates the macOS privacy model. A job that drives Mail through
#     AppleScript needs an Automation grant, and those are attributed to the
#     launching process. A launchd agent is a first-class prompt-and-grant
#     citizen; a cron job is a confusing one.
#   * launchd keeps per-job state that `launchctl print` will show you. cron
#     tells you nothing about whether last Sunday's job ran.
#
set -euo pipefail

LABEL="com.adventurelabs.wheel-engine"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$REPO/scripts/$LABEL.plist"
AGENTS_DIR="$HOME/Library/LaunchAgents"
TARGET="$AGENTS_DIR/$LABEL.plist"
DOMAIN="gui/$(id -u)"

fail() { echo "install-schedule: $*" >&2; exit 1; }

# --- The plist is machine-specific. Refuse to install one that points elsewhere.
[[ -f "$SOURCE" ]] || fail "plist not found at $SOURCE"
plutil -lint "$SOURCE" >/dev/null || fail "plist is malformed: $SOURCE"

PLIST_REPO="$(plutil -extract WorkingDirectory raw -o - "$SOURCE")"
if [[ "$PLIST_REPO" != "$REPO" ]]; then
  fail "plist WorkingDirectory is $PLIST_REPO but this repo is at $REPO.
       Edit scripts/$LABEL.plist so its absolute paths match, then re-run."
fi

# --- Everything the job invokes must exist before launchd owns the schedule.
[[ -x "$REPO/.venv/bin/python" ]] || fail "no virtualenv at $REPO/.venv"
for step in wheel-screen wheel-enrich wheel-render wheel-deliver wheel-backup; do
  [[ -x "$REPO/commands/$step" ]] || fail "missing or non-executable: commands/$step"
done
[[ -f "$REPO/config.yaml" ]] || fail "no config.yaml — copy config/example.yaml and edit it"

LOG_DIR="$(plutil -extract StandardOutPath raw -o - "$SOURCE")"
LOG_DIR="$(dirname "$LOG_DIR")"
mkdir -p "$LOG_DIR" || fail "cannot create log directory $LOG_DIR"

# --- Install and hand it to launchd.
mkdir -p "$AGENTS_DIR"
cp "$SOURCE" "$TARGET"
echo "installed $TARGET"

# bootout first so a re-install replaces the running definition rather than
# colliding with it. It fails when nothing is loaded, which is fine.
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$TARGET" || fail "launchctl bootstrap failed"

echo "loaded $LABEL into $DOMAIN"
echo
launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E "state|runs|last exit" || true
echo
cat <<EOF
Scheduled: Sundays at 08:00 local time.
Pipeline:  screen -> enrich -> render -> deliver -> backup
Logs:      $LOG_DIR/launchd-YYYY-MM-DD.log

The first run will ask for permission to control Mail. Approve it, or the
email step fails and only the file copy lands — which is by design, but you
will want the email.

It may also ask to write to ~/Downloads. Approve that one too: the file copy
is the artifact, and it is the ONE delivery failure that is fatal.

Failure notifications post as "Script Editor" in Notification Center. If you
have never let it notify you, check System Settings > Notifications before
relying on the alert. The log below records every failure either way.

Run it once by hand to check the whole chain before Sunday:
  launchctl kickstart -p $DOMAIN/$LABEL

Remove it with:
  scripts/uninstall-schedule.sh
EOF

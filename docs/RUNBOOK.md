# Runbook — Wheel Engine

Operator procedures for the weekly screen. Written for the version of you who
has not touched this in two months and does not remember any of it.

Everything here assumes:

```bash
cd ~/Developer/wheel-engine
```

**One thing worth knowing before anything else:** the file copy in
`~/Downloads/wheel/` is the artifact. The email is a convenience. A run that
copies the file and fails to send the email **succeeded**.

---

## The shape of a normal week

Sunday 08:00, launchd runs, unattended:

```
wheel-screen → wheel-enrich → wheel-render → wheel-deliver → wheel-backup
```

Cold cache: ~5 hours. Warm cache (a run in the same ISO week): minutes. You
should find `~/Downloads/wheel/YYYY-MM-DD.html` and an email by early
afternoon.

---

## Install the schedule

```bash
scripts/install-schedule.sh
```

Manual, always — nothing in the build does this for you. The script refuses to
install if the plist's paths disagree with where the repo actually is, if the
venv is missing, if any command is not executable, or if `config.yaml` is
absent. **A refusal is the guardrail working. Fix the thing it names; don't
route around it.**

### Then test it before trusting it

```bash
launchctl kickstart -p gui/$(id -u)/com.adventurelabs.wheel-engine
```

Do this **at the Mac, with time to spare** — it runs the real pipeline, which
means ~5 hours on a cold cache. macOS will prompt for permissions during the
first run and those prompts need a human:

- **Automation → Mail.** Without it the email step fails. Non-fatal.
- **Files → Downloads.** Without it the file copy fails, and that one **is**
  fatal.

Watch it go:

```bash
tail -f ~/Developer/WheelOps/logs/launchd-$(date +%Y-%m-%d).log
```

---

## Did last Sunday actually run?

Fastest answer first:

```bash
ls -lt ~/Downloads/wheel/ | head
```

A file dated last Sunday means yes. If you want detail:

```bash
# what launchd thinks
launchctl print gui/$(id -u)/com.adventurelabs.wheel-engine | grep -E "state|runs|last exit"

# the run's own log
ls -lt ~/Developer/WheelOps/logs/
tail -40 ~/Developer/WheelOps/logs/launchd-$(date -v-sun +%Y-%m-%d).log
```

**Reading `last exit code`:** `0` is a clean run. Anything else is the exit
status of the step that failed, and the log will have a `FAILED <step>` line
naming it.

A missing log file for that date means the job never started — the Mac was
powered off, or the schedule is not loaded. Check:

```bash
launchctl print gui/$(id -u)/com.adventurelabs.wheel-engine >/dev/null 2>&1 \
  && echo "loaded" || echo "NOT loaded"
```

---

## Turn it off for a while

Unload it but keep it installed:

```bash
launchctl bootout gui/$(id -u)/com.adventurelabs.wheel-engine
```

Put it back:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.adventurelabs.wheel-engine.plist
```

Remove it entirely — unloads **and** deletes the installed plist:

```bash
scripts/uninstall-schedule.sh
```

That removes the schedule only. The repo, commands, WheelOps, and every report
and log already produced stay exactly where they are.

**Stop a run that is currently going:**

```bash
launchctl kill SIGTERM gui/$(id -u)/com.adventurelabs.wheel-engine
```

---

## The email didn't arrive Sunday

Work down this list. Most causes are in the first two steps.

**1. Did the file land?** If yes, the run succeeded and only the send failed.

```bash
ls -lt ~/Downloads/wheel/ | head -3
```

**2. What does the log say?** Search for the delivery lines:

```bash
grep -E "COPIED|EMAILED|EMAIL skipped|WARN email|FAILED" \
  ~/Developer/WheelOps/logs/launchd-*.log | tail -20
```

| What you see | What it means | Fix |
|---|---|---|
| `EMAILED <address>` | It sent. Check spam, and check the address is yours | — |
| `EMAIL skipped — delivery.email_enabled is false` | Email is switched off | Set `email_enabled: true` in `config.yaml` |
| `WARN email skipped — delivery.email_to is not set` | No recipient | Set `email_to:` in `config.yaml` |
| `WARN email delivery failed: osascript exited 1` | Mail refused the script | Usually the Automation grant — see below |
| `FAILED commands/wheel-deliver` | The **copy** failed, not the email | Downloads permission, or a full disk |
| No delivery lines at all | An earlier step failed | Find the `FAILED` line above them |

**3. Check the Automation grant.** System Settings → Privacy & Security →
Automation. The entry that needs to control Mail will be **Script Editor** or
**bash**, depending on how the run was launched. If it is unchecked, check it.
If it is not listed at all, macOS never asked — run a kickstart at the Mac so
the prompt appears.

**4. Send it again by hand.** The report still exists; delivery is a separate
step and safe to repeat.

```bash
commands/wheel-deliver              # newest report
commands/wheel-deliver 2026-09-20   # a specific week
```

---

## Re-run things by hand

The pipeline steps are ordinary commands. Nothing about running them yourself
differs from what launchd does.

```bash
commands/wheel-screen               # full run — fetch + score, hours
commands/wheel-screen --score-only  # re-score existing snapshots, seconds
commands/wheel-enrich
commands/wheel-render
commands/wheel-deliver
commands/wheel-backup
```

`--score-only` is the one to reach for after a scoring change: it skips the
fetch entirely and re-scores what is already on disk.

---

## Where everything lives

| What | Where |
|---|---|
| Delivered reports | `~/Downloads/wheel/YYYY-MM-DD.html` |
| Run logs | `~/Developer/WheelOps/logs/launchd-YYYY-MM-DD.log` |
| Startup failures (before logging begins) | `~/Developer/WheelOps/logs/launchd-bootstrap.log` |
| Weekly output | `~/Developer/WheelOps/weeks/` |
| Snapshots | `~/Developer/WheelOps/snapshots/` |
| Your thesis notes | `~/Developer/WheelOps/notes/<TICKER>.md` |
| Config | `config.yaml` (gitignored) |
| Secrets | `.env` (gitignored, never in config) |
| The installed schedule | `~/Library/LaunchAgents/com.adventurelabs.wheel-engine.plist` |

---

## Tests

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
```

**Note the `tests/`.** A bare `pytest` also collects `legacy/`, which is
quarantined code that no longer imports cleanly, and you will get a wall of
collection errors that have nothing to do with anything you changed.

If you changed a scorer, regenerate the golden baseline **in the same commit**
(AGENTS.md §4.3):

```bash
PYTHONPATH=src .venv/bin/python tests/test_golden_baseline.py --regenerate
```

The diff of `tests/golden/live/expected_scores.json` is the thing to review.

---

## Things that are normal and not bugs

- **22 NumPy deprecation warnings** from `scoring.py:165`. Known; will need
  fixing before a future NumPy makes it an error.
- **Names that "could not be evaluated."** With FMP disabled, a null hard-gate
  field fails closed rather than being filled. ~39 names on the 2026-08-16 run.
- **A ~5 hour run.** Normal on a cold Stage 1 cache. The cache is keyed by ISO
  week, so the first run after a gap pays full price.
- **`caffeinate` does not survive a closed lid.** If the Mac is a laptop and
  you shut it, the run stops. Leave it open.

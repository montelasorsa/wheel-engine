"""Tell the operator that a scheduled step failed.

The weekly run is unattended. Without this, a failure is silent in the worst
way: no report arrives, and the only record is a log file nobody thinks to open
on a Sunday. The operator finds out by noticing an absence, which is the slowest
signal there is.

**The log line is the durable record; the notification is what sends someone to
read it.** Notification Center drops messages -- Do Not Disturb, a locked
screen, a missing Automation grant -- so nothing here is load-bearing. The
launchd log always carries the same line.

Same split as `deliver`: the script is a pure function of its arguments, and the
one impure call is a subprocess launch injected as `runner`, so tests never post
to a real screen.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any, Callable

from .applescript import quote

TITLE = "Wheel Engine"

# A notification that hangs holds the failing pipeline open behind it. The
# message is worth a few seconds and not one more; `deliver` can afford 120s
# for a send, this cannot.
OSASCRIPT_TIMEOUT_SECONDS = 15


def build_notification_applescript(*, title: str, subtitle: str, message: str) -> str:
    """The script that posts one notification. Pure."""

    return (
        f"display notification {quote(message)} "
        f"with title {quote(title)} "
        f"subtitle {quote(subtitle)}"
    )


def run_osascript(script: str) -> subprocess.CompletedProcess:
    """The one impure call. Injected everywhere else so tests stay quiet."""

    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=OSASCRIPT_TIMEOUT_SECONDS,
    )


def notify_failure(
    step_name: str,
    error_summary: str,
    *,
    runner: Callable[[str], Any] | None = None,
) -> None:
    """Post one failure notification. Never raises.

    A notifier that takes down the run it is reporting on is worse than no
    notifier -- the operator would lose the step's exit status as well as the
    reason for it. Every failure here is swallowed onto stderr, which the
    launchd log is already capturing.

    `runner` defaults to None rather than to `run_osascript` directly: a default
    argument binds at definition time, which would make the real subprocess
    unreachable to substitution and post a notification from a test run.
    """

    script = build_notification_applescript(
        title=TITLE, subtitle=step_name, message=error_summary
    )
    try:
        completed = (runner or run_osascript)(script)
    except Exception as error:  # timeout, missing binary, anything
        _warn(f"{type(error).__name__}: {error}")
        return
    code = getattr(completed, "returncode", 0)
    if code:
        detail = (getattr(completed, "stderr", "") or "").strip()
        _warn(f"osascript exited {code}: {detail or 'no output'}")


def _warn(reason: str) -> None:
    print(f"WARN could not post notification: {reason}", file=sys.stderr)


def main(
    argv: list[str] | None = None,
    *,
    runner: Callable[[str], Any] | None = None,
) -> int:
    """`python -m wheel.notify <step> <summary>` -- the launchd job's entry point."""

    arguments = argv if argv is not None else sys.argv[1:]
    step_name = arguments[0] if arguments else "unknown step"
    error_summary = arguments[1] if len(arguments) > 1 else "failed"
    notify_failure(step_name, error_summary, runner=runner)
    # Always zero. The caller is a failing pipeline step on its way out, and it
    # is carrying the exit status that matters. This must not overwrite it.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

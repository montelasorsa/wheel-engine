"""Deliver the rendered week: a file copy, then an email through Apple Mail.

The output edge of the pipeline. It reads a finished artifact and moves it; it
computes nothing, scores nothing, and imports no provider. Same split as the
rest of the codebase -- the pure parts (path resolution, AppleScript
construction) are functions of their arguments, and the one impure call is a
subprocess launch injected as `runner` so tests never touch Mail.

**The file is the artifact; the email is a convenience.** A copy that lands and
an email that does not is a successful delivery, reported loudly on stderr and
exiting zero. Mail being closed on a Sunday evening must not take down an
otherwise complete weekly run.

Mail is driven through `osascript` rather than SMTP on purpose: the operator's
account is already configured in Mail, and reimplementing that means holding a
password somewhere this repo has spent real effort keeping secrets out of.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable, Mapping

from .applescript import quote as _applescript_string
from .config_io import load_config, wheelops_dir

SUBJECT_PREFIX = "Wheel Engine — Weekly Screen"
BODY = "Weekly wheel screen attached. Opens in any browser."
DEFAULT_DESTINATION = "~/Downloads/wheel/"

# Mail can sit on a modal dialog or a stalled send forever. A bounded wait
# turns that into a reported failure instead of a wedged pipeline.
OSASCRIPT_TIMEOUT_SECONDS = 120


class DeliveryError(RuntimeError):
    """The file copy failed -- the one delivery failure that is fatal."""


@dataclass(frozen=True)
class DeliveryConfig:
    file_destination: Path
    email_to: str | None
    email_enabled: bool


def delivery_config_from_config(config: Mapping[str, Any]) -> DeliveryConfig:
    settings = config.get("delivery") or {}
    destination = str(settings.get("file_destination") or DEFAULT_DESTINATION)
    recipient = settings.get("email_to")
    return DeliveryConfig(
        file_destination=Path(destination).expanduser(),
        email_to=str(recipient).strip() if recipient else None,
        email_enabled=bool(settings.get("email_enabled", True)),
    )


# ---------------------------------------------------------------------------
# The artifact
# ---------------------------------------------------------------------------


def latest_report(weeks_dir: str | Path, run_date: str | None = None) -> Path:
    """The newest rendered report, or the one for an explicit date."""

    directory = Path(weeks_dir)
    if run_date is not None:
        path = directory / f"{run_date}.html"
        if not path.is_file():
            raise FileNotFoundError(f"No rendered report for {run_date} in {directory}.")
        return path
    candidates = sorted(directory.glob("*.html"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No rendered report found in {directory}.")
    return candidates[0]


def copy_report(report: str | Path, destination: str | Path) -> Path:
    """Copy the report into the destination folder, creating it if needed.

    The filename is preserved: the date in the name is how the operator finds
    last week's file next to this week's.
    """

    source = Path(report)
    directory = Path(destination).expanduser()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / source.name
        shutil.copy2(source, target)
    except OSError as error:
        raise DeliveryError(f"Could not copy {source} to {directory}: {error}") from error
    return target


# ---------------------------------------------------------------------------
# Apple Mail
# ---------------------------------------------------------------------------


def subject_for(run_date: str) -> str:
    return f"{SUBJECT_PREFIX} — {run_date}"


def build_applescript(
    *,
    subject: str,
    body: str,
    attachment: str | Path,
    recipient: str,
) -> str:
    """The script that composes and sends one message. Pure.

    `visible:false` keeps a scheduled Sunday-evening run from opening a compose
    window on the operator's screen. The attachment is added inside `tell
    content` after the last paragraph, which is the placement Mail requires --
    an attachment set as a message property is silently dropped.
    """

    posix_path = str(Path(attachment))
    return "\n".join(
        (
            f"set attachmentFile to POSIX file {_applescript_string(posix_path)}",
            'tell application "Mail"',
            "    set newMessage to make new outgoing message with properties "
            f"{{subject:{_applescript_string(subject)}, "
            f"content:{_applescript_string(body + chr(10))}, visible:false}}",
            "    tell newMessage",
            "        make new to recipient at end of to recipients with properties "
            f"{{address:{_applescript_string(recipient)}}}",
            "        tell content",
            "            make new attachment with properties "
            "{file name:attachmentFile} at after the last paragraph",
            "        end tell",
            "    end tell",
            "    send newMessage",
            "end tell",
        )
    )


def run_osascript(script: str) -> subprocess.CompletedProcess:
    """The one impure call. Injected everywhere else so tests stay offline."""

    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=OSASCRIPT_TIMEOUT_SECONDS,
    )


def send_via_mail(
    *,
    subject: str,
    body: str,
    attachment: str | Path,
    recipient: str,
    runner: Callable[[str], Any] | None = None,
) -> str | None:
    """Send one message. Returns None on success, or the reason it failed.

    `runner` defaults to None rather than to `run_osascript` directly: a
    default argument binds at definition time, which would make the real
    subprocess unreachable to substitution and launch Mail from a test run.
    """

    script = build_applescript(
        subject=subject, body=body, attachment=attachment, recipient=recipient
    )
    try:
        completed = (runner or run_osascript)(script)
    except Exception as error:  # timeout, missing binary, anything
        return f"{type(error).__name__}: {error}"
    code = getattr(completed, "returncode", 0)
    if code:
        detail = (getattr(completed, "stderr", "") or "").strip()
        return f"osascript exited {code}: {detail or 'no output'}"
    return None


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def deliver(
    config: Mapping[str, Any],
    run_date: str | None = None,
    *,
    runner: Callable[[str], Any] | None = None,
    say: Callable[[str], None] = print,
    warn: Callable[[str], None] = lambda message: print(message, file=sys.stderr),
) -> dict[str, Any]:
    """Copy the week's report out, then email it. Never raises on the email."""

    settings = delivery_config_from_config(config)
    report = latest_report(wheelops_dir(config) / "weeks", run_date)
    copied = copy_report(report, settings.file_destination)
    say(f"COPIED {copied}")

    result: dict[str, Any] = {
        "report": report,
        "copied": copied,
        "emailed": False,
        "email_error": None,
        "email_skipped": None,
    }

    if not settings.email_enabled:
        result["email_skipped"] = "delivery.email_enabled is false"
        say("EMAIL skipped — delivery.email_enabled is false")
        return result
    if not settings.email_to:
        result["email_skipped"] = "delivery.email_to is not set"
        warn("WARN email skipped — delivery.email_to is not set in config.yaml")
        return result

    stamp = report.stem
    error = send_via_mail(
        subject=subject_for(stamp),
        body=BODY,
        # Mail attaches the copy in the destination folder, not the one in
        # WheelOps. Same bytes either way, and it keeps the operational folder
        # out of reach of anything Mail does with an attachment.
        attachment=copied,
        recipient=settings.email_to,
        runner=runner,
    )
    if error is None:
        result["emailed"] = True
        say(f"EMAILED {settings.email_to}")
        return result

    result["email_error"] = error
    warn(
        f"WARN email delivery failed: {error} — the file copy at {copied} "
        "is the artifact and it succeeded"
    )
    return result


def main(
    argv: list[str] | None = None,
    *,
    runner: Callable[[str], Any] | None = None,
) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    run_date = arguments[0] if arguments else None
    result = deliver(load_config("config.yaml"), run_date, runner=runner)
    print(
        f"DELIVERED {result['copied']} emailed={result['emailed']}",
        flush=True,
    )
    # Exit zero whenever the copy landed. A delivery failure must never block
    # the pipeline, and the copy is what the operator actually needs.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

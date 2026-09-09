"""Delivery: the copy is the artifact, the email is a convenience.

Nothing here touches Mail. The osascript call is injected as `runner`, so the
tests assert what would have been run rather than running it, and the failure
paths are exercised by a runner that fails on purpose.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from wheel.deliver import (
    BODY,
    DEFAULT_DESTINATION,
    OSASCRIPT_TIMEOUT_SECONDS,
    DeliveryConfig,
    DeliveryError,
    build_applescript,
    copy_report,
    deliver,
    delivery_config_from_config,
    latest_report,
    main,
    send_via_mail,
    subject_for,
)

RUN_DATE = "2026-09-06"
REPORT_HTML = "<!doctype html><title>Wheel Engine weekly screen</title><p>x</p>"


class Recorder:
    """Stands in for `osascript`, recording the script it was handed."""

    def __init__(self, *, returncode: int = 0, stderr: str = "", raises: Exception | None = None) -> None:
        self.scripts: list[str] = []
        self.returncode = returncode
        self.stderr = stderr
        self.raises = raises

    def __call__(self, script: str):
        self.scripts.append(script)
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(
            args=["osascript", "-e", script],
            returncode=self.returncode,
            stdout="",
            stderr=self.stderr,
        )

    @property
    def script(self) -> str:
        return self.scripts[-1]


class Log:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, message: str) -> None:
        self.lines.append(message)

    def joined(self) -> str:
        return "\n".join(self.lines)


def make_wheelops(root: str, *dates: str) -> Path:
    wheelops = Path(root) / "WheelOps"
    weeks = wheelops / "weeks"
    weeks.mkdir(parents=True)
    for stamp in dates or (RUN_DATE,):
        (weeks / f"{stamp}.html").write_text(REPORT_HTML, encoding="utf-8")
        (weeks / f"{stamp}.md").write_text("# markdown", encoding="utf-8")
    return wheelops


def config_for(wheelops: Path, destination: Path, **delivery) -> dict:
    settings = {
        "file_destination": str(destination),
        "email_to": "monte@example.test",
        "email_enabled": True,
    }
    settings.update(delivery)
    return {"paths": {"wheelops": str(wheelops)}, "delivery": settings}


class ConfigTests(unittest.TestCase):
    def test_defaults_when_the_section_is_absent(self) -> None:
        settings = delivery_config_from_config({})
        self.assertEqual(settings.file_destination, Path(DEFAULT_DESTINATION).expanduser())
        self.assertIsNone(settings.email_to)
        self.assertTrue(settings.email_enabled)

    def test_the_tilde_is_expanded(self) -> None:
        settings = delivery_config_from_config(
            {"delivery": {"file_destination": "~/Downloads/wheel/"}}
        )
        self.assertTrue(settings.file_destination.is_absolute())
        self.assertNotIn("~", str(settings.file_destination))

    def test_values_are_read(self) -> None:
        settings = delivery_config_from_config(
            {
                "delivery": {
                    "file_destination": "/tmp/out",
                    "email_to": "  a@b.test  ",
                    "email_enabled": False,
                }
            }
        )
        self.assertEqual(
            settings,
            DeliveryConfig(
                file_destination=Path("/tmp/out"),
                email_to="a@b.test",
                email_enabled=False,
            ),
        )

    def test_the_example_config_carries_the_section(self) -> None:
        import yaml

        example = yaml.safe_load(
            (Path(__file__).parent.parent / "config" / "example.yaml").read_text()
        )
        settings = delivery_config_from_config(example)
        self.assertEqual(
            settings.file_destination, Path("~/Downloads/wheel/").expanduser()
        )
        self.assertTrue(settings.email_enabled)
        self.assertIn("@", settings.email_to)


class ReportDiscoveryTests(unittest.TestCase):
    def test_the_newest_report_wins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = make_wheelops(temporary, "2026-08-30", "2026-09-06")
            self.assertEqual(
                latest_report(wheelops / "weeks").name, "2026-09-06.html"
            )

    def test_an_explicit_date_is_honoured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = make_wheelops(temporary, "2026-08-30", "2026-09-06")
            self.assertEqual(
                latest_report(wheelops / "weeks", "2026-08-30").name, "2026-08-30.html"
            )

    def test_a_missing_report_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            weeks = Path(temporary) / "weeks"
            weeks.mkdir()
            with self.assertRaises(FileNotFoundError):
                latest_report(weeks)
            with self.assertRaises(FileNotFoundError):
                latest_report(weeks, RUN_DATE)


class FileCopyTests(unittest.TestCase):
    def test_the_file_lands_with_its_name_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = make_wheelops(temporary)
            destination = Path(temporary) / "Downloads" / "wheel"
            landed = copy_report(wheelops / "weeks" / f"{RUN_DATE}.html", destination)
            self.assertEqual(landed, destination / f"{RUN_DATE}.html")
            self.assertEqual(landed.read_text(encoding="utf-8"), REPORT_HTML)

    def test_a_missing_destination_directory_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = make_wheelops(temporary)
            destination = Path(temporary) / "a" / "b" / "c"
            self.assertFalse(destination.exists())
            copy_report(wheelops / "weeks" / f"{RUN_DATE}.html", destination)
            self.assertTrue(destination.is_dir())

    def test_an_existing_file_is_overwritten_not_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = make_wheelops(temporary)
            destination = Path(temporary) / "out"
            source = wheelops / "weeks" / f"{RUN_DATE}.html"
            copy_report(source, destination)
            source.write_text("<p>rerendered</p>", encoding="utf-8")
            landed = copy_report(source, destination)
            self.assertEqual(list(destination.iterdir()), [landed])
            self.assertEqual(landed.read_text(encoding="utf-8"), "<p>rerendered</p>")

    def test_an_unwritable_destination_is_a_fatal_delivery_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = make_wheelops(temporary)
            blocker = Path(temporary) / "blocked"
            blocker.write_text("I am a file, not a directory", encoding="utf-8")
            with self.assertRaises(DeliveryError):
                copy_report(wheelops / "weeks" / f"{RUN_DATE}.html", blocker)


class AppleScriptTests(unittest.TestCase):
    def script(self) -> str:
        return build_applescript(
            subject=subject_for(RUN_DATE),
            body=BODY,
            attachment="/Users/x/Downloads/wheel/2026-09-06.html",
            recipient="monte@example.test",
        )

    def test_it_composes_sets_and_sends(self) -> None:
        script = self.script()
        self.assertIn('tell application "Mail"', script)
        self.assertIn("make new outgoing message with properties", script)
        self.assertIn("send newMessage", script)

    def test_the_subject_body_recipient_and_attachment_are_all_present(self) -> None:
        script = self.script()
        self.assertIn('subject:"Wheel Engine — Weekly Screen — 2026-09-06"', script)
        self.assertIn('Weekly wheel screen attached. Opens in any browser.', script)
        self.assertIn('address:"monte@example.test"', script)
        self.assertIn('POSIX file "/Users/x/Downloads/wheel/2026-09-06.html"', script)

    def test_the_body_is_a_single_line(self) -> None:
        self.assertEqual(BODY, "Weekly wheel screen attached. Opens in any browser.")
        self.assertNotIn("\n", BODY)

    def test_the_attachment_goes_inside_the_content_block(self) -> None:
        """Set as a message property it is silently dropped; this is the fix."""

        script = self.script()
        self.assertIn("tell content", script)
        self.assertIn(
            "make new attachment with properties {file name:attachmentFile} "
            "at after the last paragraph",
            script,
        )

    def test_it_does_not_open_a_compose_window(self) -> None:
        self.assertIn("visible:false", self.script())

    def test_quotes_and_backslashes_in_a_path_are_escaped(self) -> None:
        script = build_applescript(
            subject='He said "hi"',
            body="body",
            attachment='/tmp/we"ird\\name.html',
            recipient="a@b.test",
        )
        self.assertIn(r'subject:"He said \"hi\""', script)
        self.assertIn(r'POSIX file "/tmp/we\"ird\\name.html"', script)


class SendTests(unittest.TestCase):
    def test_a_clean_run_reports_no_error(self) -> None:
        runner = Recorder()
        self.assertIsNone(
            send_via_mail(
                subject="s",
                body="b",
                attachment="/tmp/x.html",
                recipient="a@b.test",
                runner=runner,
            )
        )
        self.assertEqual(len(runner.scripts), 1)

    def test_a_nonzero_exit_is_reported_not_raised(self) -> None:
        runner = Recorder(returncode=1, stderr="Mail got an error: Can't get application")
        error = send_via_mail(
            subject="s", body="b", attachment="/tmp/x.html", recipient="a@b.test", runner=runner
        )
        self.assertIn("osascript exited 1", error)
        self.assertIn("Can't get application", error)

    def test_a_timeout_is_reported_not_raised(self) -> None:
        runner = Recorder(
            raises=subprocess.TimeoutExpired(cmd="osascript", timeout=OSASCRIPT_TIMEOUT_SECONDS)
        )
        error = send_via_mail(
            subject="s", body="b", attachment="/tmp/x.html", recipient="a@b.test", runner=runner
        )
        self.assertIn("TimeoutExpired", error)

    def test_a_missing_osascript_is_reported_not_raised(self) -> None:
        runner = Recorder(raises=FileNotFoundError("osascript"))
        error = send_via_mail(
            subject="s", body="b", attachment="/tmp/x.html", recipient="a@b.test", runner=runner
        )
        self.assertIn("FileNotFoundError", error)


class DeliverTests(unittest.TestCase):
    def test_the_file_lands_and_the_script_carries_the_right_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = make_wheelops(temporary, "2026-08-30", RUN_DATE)
            destination = Path(temporary) / "Downloads" / "wheel"
            runner = Recorder()
            say, warn = Log(), Log()

            result = deliver(
                config_for(wheelops, destination),
                runner=runner,
                say=say,
                warn=warn,
            )

            landed = destination / f"{RUN_DATE}.html"
            self.assertTrue(landed.is_file())
            self.assertEqual(result["copied"], landed)
            self.assertTrue(result["emailed"])
            self.assertIsNone(result["email_error"])

            script = runner.script
            self.assertIn(f'subject:"Wheel Engine — Weekly Screen — {RUN_DATE}"', script)
            self.assertIn(f'address:"monte@example.test"', script)
            # The attachment is the copy in the destination, not the WheelOps file.
            self.assertIn(f'POSIX file "{landed}"', script)
            self.assertNotIn("WheelOps", script)
            self.assertEqual(warn.lines, [])

    def test_an_explicit_date_delivers_that_week(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = make_wheelops(temporary, "2026-08-30", RUN_DATE)
            destination = Path(temporary) / "out"
            runner = Recorder()
            result = deliver(
                config_for(wheelops, destination),
                "2026-08-30",
                runner=runner,
                say=Log(),
                warn=Log(),
            )
            self.assertEqual(result["copied"].name, "2026-08-30.html")
            self.assertIn("2026-08-30", runner.script)

    def test_email_disabled_copies_only_and_never_calls_osascript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = make_wheelops(temporary)
            destination = Path(temporary) / "out"
            runner = Recorder()
            say = Log()
            result = deliver(
                config_for(wheelops, destination, email_enabled=False),
                runner=runner,
                say=say,
                warn=Log(),
            )
            self.assertTrue((destination / f"{RUN_DATE}.html").is_file())
            self.assertEqual(runner.scripts, [])
            self.assertFalse(result["emailed"])
            self.assertIn("email_enabled is false", result["email_skipped"])
            self.assertIn("EMAIL skipped", say.joined())

    def test_a_missing_recipient_warns_and_skips_rather_than_sending(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = make_wheelops(temporary)
            destination = Path(temporary) / "out"
            runner = Recorder()
            warn = Log()
            result = deliver(
                config_for(wheelops, destination, email_to=None),
                runner=runner,
                say=Log(),
                warn=warn,
            )
            self.assertTrue((destination / f"{RUN_DATE}.html").is_file())
            self.assertEqual(runner.scripts, [])
            self.assertIn("email_to", result["email_skipped"])
            self.assertIn("WARN", warn.joined())

    def test_a_failed_send_warns_but_the_copy_still_stands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = make_wheelops(temporary)
            destination = Path(temporary) / "out"
            warn = Log()
            result = deliver(
                config_for(wheelops, destination),
                runner=Recorder(returncode=1, stderr="Mail is not running"),
                say=Log(),
                warn=warn,
            )
            self.assertTrue((destination / f"{RUN_DATE}.html").is_file())
            self.assertFalse(result["emailed"])
            self.assertIn("Mail is not running", result["email_error"])
            self.assertIn("the file copy", warn.joined())

    def test_a_failed_copy_is_the_one_fatal_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = make_wheelops(temporary)
            blocker = Path(temporary) / "blocked"
            blocker.write_text("not a directory", encoding="utf-8")
            with self.assertRaises(DeliveryError):
                deliver(
                    config_for(wheelops, blocker),
                    runner=Recorder(),
                    say=Log(),
                    warn=Log(),
                )


class ExitCodeTests(unittest.TestCase):
    """A delivery failure must never take the pipeline down."""

    def _main_with(self, config: dict, runner: Recorder) -> int:
        """Run main() with the config swapped and the runner passed straight in.

        The runner is a parameter rather than a patched module global on
        purpose: an earlier version of this file patched the global while
        `deliver` still carried `run_osascript` as a default argument, which
        binds at definition time -- so the substitution missed and the test
        launched Mail for real. Passing it through leaves no path to the
        subprocess at all.
        """

        import wheel.deliver as module

        original = module.load_config
        module.load_config = lambda _path="config.yaml": config
        try:
            return main([], runner=runner)
        finally:
            module.load_config = original

    def test_exit_zero_on_a_clean_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = make_wheelops(temporary)
            config = config_for(wheelops, Path(temporary) / "out")
            runner = Recorder()
            self.assertEqual(self._main_with(config, runner), 0)
            self.assertEqual(len(runner.scripts), 1)

    def test_exit_zero_when_only_the_email_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = make_wheelops(temporary)
            destination = Path(temporary) / "out"
            config = config_for(wheelops, destination)
            code = self._main_with(config, Recorder(returncode=1, stderr="Mail closed"))
            self.assertEqual(code, 0)
            self.assertTrue((destination / f"{RUN_DATE}.html").is_file())


class NoLiveSubprocessTests(unittest.TestCase):
    """The regression guard for the bug that launched Mail from a test run."""

    def test_an_injected_runner_is_the_one_that_runs(self) -> None:
        import wheel.deliver as module

        def explode(_script):  # pragma: no cover - must never be reached
            raise AssertionError("the real osascript runner was called")

        original = module.run_osascript
        module.run_osascript = explode
        try:
            with tempfile.TemporaryDirectory() as temporary:
                wheelops = make_wheelops(temporary)
                runner = Recorder()
                deliver(
                    config_for(wheelops, Path(temporary) / "out"),
                    runner=runner,
                    say=Log(),
                    warn=Log(),
                )
                self.assertEqual(len(runner.scripts), 1)
        finally:
            module.run_osascript = original


if __name__ == "__main__":
    unittest.main()

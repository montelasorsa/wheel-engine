"""Failure notification: what would have been posted, never a real notification.

The osascript call is injected as `runner`, so these tests assert the script
that would have run. The failure paths are exercised by a runner that fails on
purpose, because the whole point of this module is that it stays quiet when it
cannot do its job -- a notifier that raises would take down the run it exists to
report on.
"""

from __future__ import annotations

import inspect
import io
import subprocess
import unittest
import unittest.mock
from contextlib import redirect_stderr

from wheel import notify
from wheel.notify import (
    OSASCRIPT_TIMEOUT_SECONDS,
    TITLE,
    build_notification_applescript,
    main,
    notify_failure,
)


class Recorder:
    """Stands in for `osascript`, recording the script it was handed."""

    def __init__(
        self,
        *,
        returncode: int = 0,
        stderr: str = "",
        raises: Exception | None = None,
    ) -> None:
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


class ScriptTests(unittest.TestCase):
    def test_it_carries_the_message_title_and_subtitle(self) -> None:
        script = build_notification_applescript(
            title="Wheel Engine", subtitle="wheel-screen", message="exit 1"
        )
        self.assertTrue(script.startswith("display notification "))
        self.assertIn('"exit 1"', script)
        self.assertIn('with title "Wheel Engine"', script)
        self.assertIn('subtitle "wheel-screen"', script)

    def test_quotes_and_backslashes_are_escaped(self) -> None:
        """A step name or error text reaches AppleScript as data, not as code."""

        script = build_notification_applescript(
            title="t", subtitle='say "hi"', message="back\\slash"
        )
        self.assertIn('subtitle "say \\"hi\\""', script)
        self.assertIn('"back\\\\slash"', script)

    def test_a_quote_cannot_end_the_literal_early(self) -> None:
        script = build_notification_applescript(
            title="t", subtitle="s", message='" & (do shell script "x") & "'
        )
        # Every quote inside the payload is escaped, so the only unescaped
        # quotes left are the literal delimiters the builder itself wrote.
        unescaped = script.replace('\\"', "")
        self.assertEqual(unescaped.count('"'), 6)


class NotifyFailureTests(unittest.TestCase):
    def test_it_posts_one_notification_with_the_step_as_subtitle(self) -> None:
        runner = Recorder()
        notify_failure("wheel-enrich", "exit 2", runner=runner)
        self.assertEqual(len(runner.scripts), 1)
        self.assertIn(f'with title "{TITLE}"', runner.script)
        self.assertIn('subtitle "wheel-enrich"', runner.script)
        self.assertIn('"exit 2"', runner.script)

    def test_a_nonzero_exit_is_reported_not_raised(self) -> None:
        runner = Recorder(returncode=1, stderr="Not authorized to send Apple events")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            notify_failure("wheel-render", "exit 3", runner=runner)
        self.assertIn("could not post notification", stderr.getvalue())
        self.assertIn("osascript exited 1", stderr.getvalue())

    def test_a_timeout_is_reported_not_raised(self) -> None:
        runner = Recorder(
            raises=subprocess.TimeoutExpired(cmd="osascript", timeout=OSASCRIPT_TIMEOUT_SECONDS)
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            notify_failure("wheel-deliver", "exit 4", runner=runner)
        self.assertIn("TimeoutExpired", stderr.getvalue())

    def test_a_missing_binary_is_reported_not_raised(self) -> None:
        runner = Recorder(raises=FileNotFoundError("osascript"))
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            notify_failure("wheel-screen", "exit 5", runner=runner)
        self.assertIn("FileNotFoundError", stderr.getvalue())

    def test_the_timeout_is_short_enough_not_to_hold_the_pipeline(self) -> None:
        self.assertLessEqual(OSASCRIPT_TIMEOUT_SECONDS, 30)


class CommandTests(unittest.TestCase):
    """`python -m wheel.notify <step> <summary>` — what the launchd job calls."""

    def test_it_passes_both_arguments_through(self) -> None:
        runner = Recorder()
        self.assertEqual(main(["wheel-screen", "exit 1"], runner=runner), 0)
        self.assertIn('subtitle "wheel-screen"', runner.script)
        self.assertIn('"exit 1"', runner.script)

    def test_it_exits_zero_even_when_the_notification_fails(self) -> None:
        """The caller is a failing step carrying the exit status that matters."""

        runner = Recorder(returncode=1)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["wheel-screen", "exit 1"], runner=runner), 0)

    def test_missing_arguments_still_produce_a_notification(self) -> None:
        runner = Recorder()
        self.assertEqual(main([], runner=runner), 0)
        self.assertIn("unknown step", runner.script)


class NothingPostsForRealTests(unittest.TestCase):
    """The injected runner must actually displace the subprocess, not shadow it."""

    def test_an_injected_runner_never_reaches_the_real_osascript(self) -> None:
        def explode(script: str):
            raise AssertionError("the real osascript was called")

        with unittest.mock.patch.object(notify, "run_osascript", explode):
            notify_failure("wheel-screen", "exit 1", runner=Recorder())
            main(["wheel-screen", "exit 1"], runner=Recorder())

    def test_the_default_runner_is_bound_at_call_time(self) -> None:
        """A default of `run_osascript` would make the real call unsubstitutable."""

        signature = inspect.signature(notify_failure)
        self.assertIsNone(signature.parameters["runner"].default)


if __name__ == "__main__":
    unittest.main()

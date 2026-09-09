"""The launchd artifacts: the plist parses, the scripts run, the paths agree.

A schedule cannot be unit tested — proving it fires on Sunday means waiting
until Sunday. What can be tested is everything that makes a hand-install fail
silently: malformed XML, a shell fragment that will not parse, a plist that
points at a repo which has moved, an install and an uninstall that disagree
about which job they are managing.

The one thing this file must never do is install anything.
"""

from __future__ import annotations

from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest

REPO = Path(__file__).parent.parent
SCRIPTS = REPO / "scripts"
LABEL = "com.adventurelabs.wheel-engine"
PLIST = SCRIPTS / f"{LABEL}.plist"
INSTALL = SCRIPTS / "install-schedule.sh"
UNINSTALL = SCRIPTS / "uninstall-schedule.sh"
PIPELINE = ("wheel-screen", "wheel-enrich", "wheel-render", "wheel-deliver")


def plist() -> dict:
    return plistlib.loads(PLIST.read_bytes())


def job_script() -> str:
    return plist()["ProgramArguments"][2]


class PlistTests(unittest.TestCase):
    def test_it_is_well_formed(self) -> None:
        completed = subprocess.run(
            ["plutil", "-lint", str(PLIST)], capture_output=True, text=True
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_the_label_matches_the_filename(self) -> None:
        self.assertEqual(plist()["Label"], LABEL)
        self.assertEqual(PLIST.stem, LABEL)

    def test_it_runs_sunday_at_six(self) -> None:
        self.assertEqual(
            plist()["StartCalendarInterval"], {"Weekday": 0, "Hour": 18, "Minute": 0}
        )

    def test_it_does_not_run_at_load(self) -> None:
        """Loading the agent must not kick off a full universe scan."""

        self.assertIs(plist()["RunAtLoad"], False)

    def test_the_working_directory_is_this_repo(self) -> None:
        self.assertEqual(Path(plist()["WorkingDirectory"]), REPO.resolve())

    def test_the_bootstrap_log_sits_under_wheelops(self) -> None:
        for key in ("StandardOutPath", "StandardErrorPath"):
            with self.subTest(key=key):
                path = Path(plist()[key])
                self.assertEqual(path.parent.name, "logs")
                self.assertEqual(path.parent.parent.name, "WheelOps")

    def test_wheelops_is_the_repo_sibling(self) -> None:
        """AGENTS.md §3: operational data lives beside the repo, never inside."""

        logs = Path(plist()["StandardOutPath"]).parent
        self.assertEqual(logs.parent.parent, REPO.resolve().parent)
        self.assertNotIn(REPO.name, logs.parts)


class JobScriptTests(unittest.TestCase):
    def test_it_is_valid_shell(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".sh") as handle:
            handle.write(job_script())
            handle.flush()
            completed = subprocess.run(
                ["bash", "-n", handle.name], capture_output=True, text=True
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_it_runs_the_four_steps_in_order(self) -> None:
        script = job_script()
        positions = [script.index(f"commands/{step}") for step in PIPELINE]
        self.assertEqual(positions, sorted(positions))

    def test_the_steps_are_chained_so_a_failure_stops_the_rest(self) -> None:
        script = job_script()
        self.assertEqual(script.count("&&"), len(PIPELINE) - 1)
        self.assertNotIn(";", script.split("commands/wheel-screen")[1].split("status=")[0])

    def test_it_activates_the_virtualenv(self) -> None:
        self.assertIn("source .venv/bin/activate", job_script())

    def test_the_log_filename_carries_the_run_date(self) -> None:
        script = job_script()
        self.assertIn("launchd-$(date +%Y-%m-%d).log", script)
        self.assertIn("2>&1", script)

    def test_it_appends_rather_than_truncating(self) -> None:
        self.assertIn('exec >> "$LOG_DIR/', job_script())

    def test_the_exit_status_survives_the_logging(self) -> None:
        script = job_script()
        self.assertIn("status=$?", script)
        self.assertIn("exit $status", script)


class ScriptTests(unittest.TestCase):
    def test_both_scripts_parse(self) -> None:
        for script in (INSTALL, UNINSTALL):
            with self.subTest(script=script.name):
                completed = subprocess.run(
                    ["bash", "-n", str(script)], capture_output=True, text=True
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_both_scripts_are_executable(self) -> None:
        for script in (INSTALL, UNINSTALL, PLIST.parent / "install-schedule.sh"):
            with self.subTest(script=script.name):
                self.assertTrue(script.stat().st_mode & 0o111, f"{script} is not executable")

    def test_they_manage_the_same_job(self) -> None:
        for script in (INSTALL, UNINSTALL):
            with self.subTest(script=script.name):
                text = script.read_text()
                self.assertIn(f'LABEL="{LABEL}"', text)
                self.assertIn("$HOME/Library/LaunchAgents", text)

    def test_install_bootstraps_and_uninstall_boots_out(self) -> None:
        self.assertIn("launchctl bootstrap", INSTALL.read_text())
        self.assertIn("launchctl bootout", UNINSTALL.read_text())

    def test_install_validates_before_it_copies(self) -> None:
        text = INSTALL.read_text()
        self.assertLess(text.index("plutil -lint"), text.index('cp "$SOURCE"'))
        self.assertLess(text.index("WorkingDirectory"), text.index('cp "$SOURCE"'))

    def test_install_checks_every_step_it_will_schedule(self) -> None:
        text = INSTALL.read_text()
        for step in PIPELINE:
            with self.subTest(step=step):
                self.assertIn(step, text)

    def test_uninstall_removes_the_installed_plist(self) -> None:
        self.assertIn('rm "$TARGET"', UNINSTALL.read_text())

    def test_both_explain_launchctl_and_why_not_cron(self) -> None:
        """The comment the task asks for, kept honest by a test."""

        install = INSTALL.read_text().lower()
        self.assertIn("launchctl", install)
        self.assertIn("cron", install)
        self.assertIn("asleep", install)
        self.assertIn("install-schedule.sh", UNINSTALL.read_text())


class NothingInstallsItselfTests(unittest.TestCase):
    """Installing the schedule is a manual step and must stay one."""

    def test_no_command_or_module_invokes_the_installer(self) -> None:
        watched = list((REPO / "commands").iterdir())
        watched += list((REPO / "src").rglob("*.py"))
        watched += [p for p in (REPO / "tests").rglob("*.py") if p.name != "test_schedule.py"]
        offenders = [
            str(path.relative_to(REPO))
            for path in watched
            if path.is_file() and "install-schedule" in path.read_text(errors="ignore")
        ]
        self.assertEqual(offenders, [])

    def test_this_test_file_never_shells_out_to_launchctl(self) -> None:
        source = Path(__file__).read_text()
        for line in source.splitlines():
            if "subprocess.run" in line:
                self.assertNotIn("launchctl", line)


if __name__ == "__main__":
    unittest.main()

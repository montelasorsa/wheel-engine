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
# The fail-stop chain. Backup is deliberately not in here: it runs after the
# report is already delivered, so it is not allowed to fail the run, and the
# tests below would mean the opposite of what they say if it were included.
PIPELINE = ("wheel-screen", "wheel-enrich", "wheel-render", "wheel-deliver")
BACKUP = "wheel-backup"


def plist() -> dict:
    return plistlib.loads(PLIST.read_bytes())


def job_script() -> str:
    return plist()["ProgramArguments"][2]


def run_step_body() -> str:
    """The body of the wrapper every fail-stop step is invoked through."""

    return job_script().split("run_step() {")[1].split("}")[0]


class PlistTests(unittest.TestCase):
    def test_it_is_well_formed(self) -> None:
        completed = subprocess.run(
            ["plutil", "-lint", str(PLIST)], capture_output=True, text=True
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_the_label_matches_the_filename(self) -> None:
        self.assertEqual(plist()["Label"], LABEL)
        self.assertEqual(PLIST.stem, LABEL)

    def test_it_runs_sunday_morning(self) -> None:
        """Morning, so a ~5h cold run has the whole day rather than the night."""

        self.assertEqual(
            plist()["StartCalendarInterval"], {"Weekday": 0, "Hour": 8, "Minute": 0}
        )

    def test_it_does_not_run_at_load(self) -> None:
        """Loading the agent must not kick off a full universe scan."""

        self.assertIs(plist()["RunAtLoad"], False)

    def test_the_working_directory_is_the_repo_the_script_enters(self) -> None:
        """Whether that path is THIS checkout is machine state, not code.

        Asserting it here failed every clone at any other path. The guard
        lives where it matters: install-schedule.sh refuses to install a plist
        whose WorkingDirectory disagrees with where the repo actually is, and
        test_install_validates_before_it_copies holds it to that.
        """

        self.assertIn(f'REPO="{plist()["WorkingDirectory"]}"', job_script())

    def test_the_bootstrap_log_sits_under_wheelops(self) -> None:
        for key in ("StandardOutPath", "StandardErrorPath"):
            with self.subTest(key=key):
                path = Path(plist()[key])
                self.assertEqual(path.parent.name, "logs")
                self.assertEqual(path.parent.parent.name, "WheelOps")

    def test_wheelops_is_the_repo_sibling(self) -> None:
        """AGENTS.md §3: operational data lives beside the repo, never inside."""

        repo = Path(plist()["WorkingDirectory"])
        logs = Path(plist()["StandardOutPath"]).parent
        self.assertEqual(logs.parent.parent, repo.parent)
        self.assertNotIn(repo.name, logs.parts)
        self.assertIn(f'LOG_DIR="{logs}"', job_script())


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

    def test_every_step_runs_through_the_failure_wrapper(self) -> None:
        """A failing step must stop the ones after it, not log and carry on."""

        script = job_script()
        for step in PIPELINE:
            with self.subTest(step=step):
                self.assertIn(f"run_step commands/{step}", script)

    def test_the_wrapper_stops_the_run_carrying_the_step_s_status(self) -> None:
        body = run_step_body()
        self.assertIn("code=$?", body)
        self.assertIn('exit "$code"', body)

    def test_a_failed_step_notifies_before_it_gives_up(self) -> None:
        body = run_step_body()
        self.assertIn("wheel.notify", body)
        self.assertLess(body.index("wheel.notify"), body.index('exit "$code"'))

    def test_the_notification_can_find_the_package(self) -> None:
        """commands/* set PYTHONPATH themselves; a bare python call must too."""

        self.assertIn("PYTHONPATH=src", run_step_body())

    def test_the_notification_cannot_take_down_the_run_it_reports_on(self) -> None:
        line = next(l for l in run_step_body().splitlines() if "wheel.notify" in l)
        self.assertIn("|| true", line)

    def test_it_holds_idle_sleep_off_for_the_whole_run(self) -> None:
        """A ~5h run that sleeps mid-fetch resumes only when someone walks past."""

        script = job_script()
        self.assertIn("/usr/bin/caffeinate", script)
        self.assertIn("-i", script.split("/usr/bin/caffeinate")[1].split("\n")[0])

    def test_the_keep_awake_is_absolute_because_launchd_has_no_login_path(self) -> None:
        line = next(l for l in job_script().splitlines() if "caffeinate" in l and not l.strip().startswith("#"))
        self.assertTrue(line.strip().startswith("/usr/bin/caffeinate"), line)

    def test_it_does_not_keep_the_display_on(self) -> None:
        line = next(l for l in job_script().splitlines() if "caffeinate" in l and not l.strip().startswith("#"))
        self.assertNotIn("-d", line)

    def test_the_keep_awake_releases_when_the_run_ends(self) -> None:
        """`-w $$` ties the assertion to this script's lifetime, however it ends."""

        line = next(l for l in job_script().splitlines() if "caffeinate" in l and not l.strip().startswith("#"))
        self.assertIn("-w $$", line)
        self.assertTrue(line.rstrip().endswith("&"), line)

    def test_it_activates_the_virtualenv(self) -> None:
        self.assertIn("source .venv/bin/activate", job_script())

    def test_the_log_filename_carries_the_run_date(self) -> None:
        script = job_script()
        self.assertIn("launchd-$(date +%Y-%m-%d).log", script)
        self.assertIn("2>&1", script)

    def test_it_appends_rather_than_truncating(self) -> None:
        self.assertIn('exec >> "$LOG_DIR/', job_script())

    def test_a_completed_run_exits_zero(self) -> None:
        self.assertTrue(job_script().rstrip().endswith("exit 0"), job_script()[-200:])

    def test_backup_runs_after_the_report_is_delivered(self) -> None:
        script = job_script()
        self.assertLess(
            script.index(f"commands/{PIPELINE[-1]}"), script.index(f"commands/{BACKUP}")
        )

    def test_backup_cannot_fail_the_run(self) -> None:
        """The report is already in the operator's hands by then."""

        script = job_script()
        self.assertNotIn(f"run_step commands/{BACKUP}", script)
        line = next(l for l in script.splitlines() if f"commands/{BACKUP}" in l)
        self.assertIn("||", line)
        self.assertNotIn("exit", line)


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
        for step in PIPELINE + (BACKUP,):
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

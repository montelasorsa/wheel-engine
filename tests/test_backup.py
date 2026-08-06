"""Tests for commands/wheel-backup: one-way copy, destination creation.

Runs the actual shell script via subprocess with --source/--dest overrides,
so nothing touches the real WheelOps or the real iCloud destination.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "commands" / "wheel-backup"


def run_backup(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(SCRIPT), *arguments], capture_output=True, text=True
    )


class WheelBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        root = Path(self._directory.name)
        self.source = root / "WheelOps"
        self.dest = root / "backup destination"  # space: the real one has one
        (self.source / "decisions").mkdir(parents=True)
        (self.source / "decisions" / "decisions.jsonl").write_text(
            '{"id":"DEC-20260815-001"}\n'
        )
        (self.source / "weeks").mkdir()
        (self.source / "weeks" / "2026-08-15.md").write_text("# report\n")
        self.addCleanup(self._directory.cleanup)

    def test_creates_the_destination_and_copies_files(self) -> None:
        completed = run_backup(
            "--source", str(self.source), "--dest", str(self.dest)
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(self.dest.is_dir())
        copied = self.dest / "decisions" / "decisions.jsonl"
        self.assertEqual(
            copied.read_text(),
            (self.source / "decisions" / "decisions.jsonl").read_text(),
        )
        self.assertTrue((self.dest / "weeks" / "2026-08-15.md").is_file())

    def test_subdir_mode_copies_only_that_folder(self) -> None:
        completed = run_backup(
            "decisions", "--source", str(self.source), "--dest", str(self.dest)
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(
            (self.dest / "decisions" / "decisions.jsonl").is_file()
        )
        self.assertFalse((self.dest / "weeks").exists())

    def test_one_way_copy_never_deletes_from_the_destination(self) -> None:
        run_backup("--source", str(self.source), "--dest", str(self.dest))
        stale = self.dest / "only-in-backup.txt"
        stale.write_text("must survive")
        (self.source / "weeks" / "2026-08-15.md").unlink()
        completed = run_backup(
            "--source", str(self.source), "--dest", str(self.dest)
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(stale.is_file())
        # The file deleted at the source also survives in the backup.
        self.assertTrue((self.dest / "weeks" / "2026-08-15.md").is_file())

    def test_missing_source_fails_loudly(self) -> None:
        completed = run_backup(
            "--source", str(self.source / "nope"), "--dest", str(self.dest)
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("does not exist", completed.stderr)


if __name__ == "__main__":
    unittest.main()

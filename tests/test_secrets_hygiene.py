"""Secrets stay in .env, and .env stays out of git -- enforced, not remembered.

Three concerns, three locations (AGENTS.md §3): `.env` holds secrets and is
gitignored, `config.yaml` holds behavior and is gitignored behind a tracked
template, `governance/` holds rules and is tracked. The failure this guards
against already happened once in this repo: an API key committed inside `.env`
and recoverable from history long after the file was deleted from the tree.

A convention cannot prevent that recurring. A test can.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent

# Env-file `NAME=value` where the value is neither empty nor a placeholder.
# Matching the assignment rather than a key shape keeps this provider-agnostic:
# a future SCHWAB_CLIENT_SECRET is caught without editing the test.
#
# No whitespace is permitted around `=`, and the value may not open with a
# quote or bracket. That is what separates an env assignment from Python --
# `SECRET_ANCHORS = (...)` is a constant, not a credential, and a test that
# cries wolf on ordinary code gets muted.
SECRET_ASSIGNMENT = re.compile(
    r"^\s*(?!#)([A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*)"
    r"=([^\s\"'(\[{#]+)",
    re.MULTILINE,
)
PLACEHOLDERS = frozenset(
    {"your_key_here", "changeme", "xxx", "<key>", "none", "null", ""}
)


def git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


class SecretsHygieneTests(unittest.TestCase):
    def test_env_is_not_tracked(self) -> None:
        self.assertNotIn(".env\n", git("ls-files", "--", ".env"))

    def test_env_is_ignored_so_it_cannot_be_added_by_accident(self) -> None:
        # check-ignore exits 1 when the path is NOT ignored, so ask git directly
        # rather than trusting that .gitignore merely mentions it.
        result = subprocess.run(
            ["git", "check-ignore", "-q", ".env"], cwd=REPO
        )
        self.assertEqual(result.returncode, 0, ".env is not gitignored")

    def test_env_example_is_tracked_as_the_template(self) -> None:
        self.assertIn(".env.example", git("ls-files", "--", ".env.example"))

    def test_no_tracked_file_carries_a_real_secret(self) -> None:
        offenders: list[str] = []
        for name in git("ls-files").splitlines():
            path = REPO / name
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue  # binary or unreadable: nothing to read a key out of
            for key, value in SECRET_ASSIGNMENT.findall(text):
                if value.strip().strip("\"'").lower() not in PLACEHOLDERS:
                    offenders.append(f"{name}: {key}")
        self.assertEqual(offenders, [])

    def test_the_scan_would_actually_catch_one(self) -> None:
        # Guards the test itself: a rotted regex must fail here first.
        self.assertEqual(
            SECRET_ASSIGNMENT.findall("FMP_API_KEY=abc123def\n"),
            [("FMP_API_KEY", "abc123def")],
        )
        self.assertEqual(SECRET_ASSIGNMENT.findall("FMP_API_KEY=\n"), [])
        self.assertEqual(SECRET_ASSIGNMENT.findall("# FMP_API_KEY=real\n"), [])
        # Python constants that merely contain a trigger word are not secrets.
        self.assertEqual(SECRET_ASSIGNMENT.findall("SECRET_ANCHORS = (1, 2)\n"), [])
        self.assertEqual(SECRET_ASSIGNMENT.findall('TOKEN_NAME = "x"\n'), [])


if __name__ == "__main__":
    unittest.main()

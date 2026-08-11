"""AGENTS.md §4.2: provider isolation is enforced by test, not convention.

No provider import may appear anywhere in src/ outside src/wheel_mcp/. If a
future change needs provider data elsewhere, the data goes through a snapshot,
not through an import.

`dotenv` is on the list for the same reason a provider is: secrets are loaded at
the Layer 0 edge, and a Layer 1 module that can read an API key is a Layer 1
module that can make a call. Layer 1 sees snapshots, never credentials.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SRC = Path(__file__).parent.parent / "src"
PROVIDER_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+(yfinance|schwab|curl_cffi|requests|fmpsdk|dotenv)\b",
    re.MULTILINE,
)


class ProviderIsolationTests(unittest.TestCase):
    def test_no_provider_import_outside_wheel_mcp(self) -> None:
        violations = []
        for path in SRC.rglob("*.py"):
            if "wheel_mcp" in path.parts:
                continue
            for match in PROVIDER_IMPORT.finditer(path.read_text()):
                violations.append(f"{path.relative_to(SRC)}: {match.group(0).strip()}")
        self.assertEqual(violations, [])

    def test_the_scan_actually_sees_the_provider_where_it_is_allowed(self) -> None:
        # Guards the test itself: if the regex rotted, this would fail first.
        yahoo = (SRC / "wheel_mcp" / "yahoo.py").read_text()
        self.assertTrue(PROVIDER_IMPORT.search(yahoo))


if __name__ == "__main__":
    unittest.main()

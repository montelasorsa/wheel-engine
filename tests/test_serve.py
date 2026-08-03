"""Offline tests for the Step 7 serve module: discovery plus loopback HTTP.

The handler tests bind 127.0.0.1 only -- no external network is touched,
consistent with the offline-test discipline.
"""

from __future__ import annotations

import http.client
import os
import socket
import tempfile
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from wheel_screener.serve import (
    ReportRequestHandler,
    latest_report_file,
)

OLDER_REPORT = "report_2026-07-01-090000.html"
NEWER_REPORT = "report_2026-07-20-090000.html"


class QuietHandler(ReportRequestHandler):
    """Same behavior, no per-request stderr lines polluting test output."""

    def log_message(self, *args: object) -> None:
        pass


def populate_fixture_dir(directory: Path) -> None:
    (directory / OLDER_REPORT).write_text("<html>older</html>")
    (directory / NEWER_REPORT).write_text("<html>newer</html>")
    # Decoys the report glob must ignore.
    (directory / "run_state_2026-07-25-090000.json").write_text("{}")
    (directory / "candidates_2026-07-20-090000.csv").write_text("ticker\nDVN\n")


class LatestReportFileTests(unittest.TestCase):
    def test_picks_newest_by_filename_timestamp_not_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            populate_fixture_dir(path)
            # Give the OLDER-stamped report the NEWEST mtime; the filename
            # must still win (copies and iCloud syncs rewrite mtimes).
            newest_mtime = (path / NEWER_REPORT).stat().st_mtime + 1000
            os.utime(path / OLDER_REPORT, (newest_mtime, newest_mtime))

            result = latest_report_file(path)

            self.assertIsNotNone(result)
            self.assertEqual(result.name, NEWER_REPORT)

    def test_ignores_state_and_csv_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "run_state_2026-07-25-090000.json").write_text("{}")
            (path / "candidates_2026-07-25-090000.csv").write_text("ticker\n")

            self.assertIsNone(latest_report_file(path))

    def test_empty_directory_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(latest_report_file(directory))


class HandlerLoopbackTests(unittest.TestCase):
    """Requests over 127.0.0.1 against a fixture directory."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tempdir = tempfile.TemporaryDirectory()
        cls.fixture_dir = Path(cls._tempdir.name)
        populate_fixture_dir(cls.fixture_dir)
        handler = partial(QuietHandler, directory=str(cls.fixture_dir))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        cls._thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True
        )
        cls._thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls._thread.join(timeout=5)
        cls._tempdir.cleanup()

    def request(self, path: str) -> http.client.HTTPResponse:
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        self.addCleanup(connection.close)
        connection.request("GET", path)
        return connection.getresponse()

    def test_root_redirects_to_latest_report(self) -> None:
        response = self.request("/")
        self.assertEqual(response.status, 302)
        self.assertEqual(response.getheader("Location"), f"/{NEWER_REPORT}")

    def test_head_on_root_redirects_like_get(self) -> None:
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        self.addCleanup(connection.close)
        connection.request("HEAD", "/")
        response = connection.getresponse()
        self.assertEqual(response.status, 302)
        self.assertEqual(response.getheader("Location"), f"/{NEWER_REPORT}")

    def test_directory_listing_is_disabled(self) -> None:
        # /./ resolves to the served directory while bypassing the "/" check
        # ("//" does not: the stdlib collapses leading slashes since
        # CVE-2021-28861). Raw socket, because http.client normalizes paths.
        # It must 404, not render a raw file browser of the output folder.
        with socket.create_connection(("127.0.0.1", self.port)) as raw:
            raw.sendall(b"GET /./ HTTP/1.0\r\n\r\n")
            status_line = raw.recv(200).decode().split("\r\n")[0]
        self.assertIn("404", status_line)

    def test_report_served_byte_identical(self) -> None:
        response = self.request(f"/{NEWER_REPORT}")
        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.read(),
            (self.fixture_dir / NEWER_REPORT).read_bytes(),
        )

    def test_csv_downloads_as_attachment(self) -> None:
        response = self.request("/candidates_2026-07-20-090000.csv")
        self.assertEqual(response.status, 200)
        self.assertIn("text/csv", response.getheader("Content-Type", ""))
        self.assertEqual(
            response.getheader("Content-Disposition"),
            'attachment; filename="candidates_2026-07-20-090000.csv"',
        )

    def test_state_json_served_with_json_mime(self) -> None:
        response = self.request("/run_state_2026-07-25-090000.json")
        self.assertEqual(response.status, 200)
        self.assertIn("application/json", response.getheader("Content-Type", ""))

    def test_history_lists_all_reports_newest_first(self) -> None:
        response = self.request("/history/")
        self.assertEqual(response.status, 200)
        body = response.read().decode("utf-8")
        self.assertIn(NEWER_REPORT, body)
        self.assertIn(OLDER_REPORT, body)
        self.assertLess(body.index(NEWER_REPORT), body.index(OLDER_REPORT))
        self.assertIn("2026-07-20 09:00:00", body)


class EmptyDirectoryLoopbackTests(unittest.TestCase):
    def test_root_returns_404_with_guidance_when_no_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            handler = partial(QuietHandler, directory=directory)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_address[1]
                )
                connection.request("GET", "/")
                response = connection.getresponse()
                body = response.read().decode("utf-8", errors="replace")
                connection.close()
                self.assertEqual(response.status, 404)
                self.assertIn("wheel_screener.run", body)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()

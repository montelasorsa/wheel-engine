"""Local-network static server for the WheelOps report folder.

Stdlib only, on purpose: presentation gets no new dependencies, and
`http.server` covers everything a phone on the home wifi needs. This serves
exactly one directory -- the configured output folder -- and nothing else;
`SimpleHTTPRequestHandler.translate_path` confines every request to it.
"""

from __future__ import annotations

import os
import socket
from functools import partial
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPORT_GLOB = "report_*.html"


def latest_report_file(output_dir: str | Path) -> Path | None:
    """Return the newest report by filename timestamp.

    Mirrors `latest_state_file` in screening/diff.py: the zero-padded
    %Y-%m-%d-%H%M%S stamp makes lexicographic order chronological. The
    filename, not mtime, is the source of truth -- copies and iCloud syncs
    rewrite mtimes.
    """

    candidates = sorted(Path(output_dir).glob(REPORT_GLOB))
    return candidates[-1] if candidates else None


def _report_timestamp_label(name: str) -> str:
    """Turn report_2026-07-26-085321.html into '2026-07-26 08:53:21'."""

    stamp = name[len("report_") : -len(".html")]
    date_part, _, time_part = stamp.rpartition("-")
    if len(time_part) == 6 and time_part.isdigit():
        clock = f"{time_part[0:2]}:{time_part[2:4]}:{time_part[4:6]}"
        return f"{date_part} {clock}"
    return stamp


class ReportRequestHandler(SimpleHTTPRequestHandler):
    """Serve the output folder, with a latest-report redirect at the root."""

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler naming
        if not self._handle_special(include_body=True):
            super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler naming
        # HEAD must intercept the same paths as GET, or curl -I / a browser
        # preflight falls through to the stdlib default for the root.
        if not self._handle_special(include_body=False):
            super().do_HEAD()

    def _handle_special(self, *, include_body: bool) -> bool:
        if self.path in ("/", ""):
            self._redirect_to_latest()
            return True
        if self.path.rstrip("/") == "/history":
            self._send_history(include_body=include_body)
            return True
        return False

    def list_directory(self, path: str | os.PathLike[str]) -> None:
        # Directory listings stay off: /history/ is the only sanctioned index.
        # Without this, GET // or HEAD / would render a raw file browser.
        self.send_error(404, "Not found")
        return None

    def _redirect_to_latest(self) -> None:
        # Discovered per request, never cached: a run that finishes while the
        # server is up shows on the next page load without a restart.
        latest = latest_report_file(self.directory)
        if latest is None:
            self.send_error(
                404,
                "No reports yet",
                "Run 'python -m wheel_screener.run' first, then reload.",
            )
            return
        self.send_response(302)
        self.send_header("Location", f"/{latest.name}")
        self.end_headers()

    def _send_history(self, *, include_body: bool = True) -> None:
        reports = sorted(Path(self.directory).glob(REPORT_GLOB), reverse=True)
        items = "\n".join(
            f'<li><a href="/{escape(path.name)}">'
            f"{escape(_report_timestamp_label(path.name))}</a></li>"
            for path in reports
        )
        body = (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>Wheel Screener — run history</title></head><body>"
            f"<h1>Run history ({len(reports)})</h1>"
            f"<ul>{items or '<li>No reports yet.</li>'}</ul>"
            "</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def end_headers(self) -> None:
        # MIME type alone does not make Safari download a CSV; an attachment
        # disposition does, on desktop and phone alike.
        if self.path.endswith(".csv"):
            filename = Path(self.path).name
            self.send_header(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
        super().end_headers()


def detect_lan_ip() -> str | None:
    """Find the outbound-facing local IP without sending any packets.

    Connecting a UDP socket only resolves the routing table -- nothing is
    transmitted, so this works without internet reachability. It just answers
    'which of my addresses would traffic leave from'.
    """

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            return probe.getsockname()[0]
    except OSError:
        return None


def run_server(
    output_dir: str | Path,
    port: int = 8000,
    bind: str = "0.0.0.0",
) -> None:
    """Serve the output folder until interrupted.

    bind stays "0.0.0.0": binding every interface is what makes the phone on
    the same wifi able to reach this. "Tidying" it to 127.0.0.1 silently
    breaks LAN access while everything still works on the Mac.
    """

    directory = Path(output_dir)
    if not directory.is_dir():
        raise SystemExit(f"Output directory does not exist: {directory}")

    handler = partial(ReportRequestHandler, directory=str(directory))
    try:
        server = ThreadingHTTPServer((bind, port), handler)
    except OSError as error:
        raise SystemExit(
            f"Could not bind port {port} ({error.strerror}) — "
            f"try --port {port + 1}."
        ) from error

    lan_ip = detect_lan_ip()
    network_line = (
        f"  Network: http://{lan_ip}:{port}/"
        if lan_ip is not None
        else "  Network: unavailable — check your wifi connection."
    )
    print("Wheel Screener report server")
    print(f"  Local:   http://127.0.0.1:{port}/")
    print(network_line)
    print("Bookmark the Network URL on your phone (same wifi required).")
    print("Ctrl+C to stop.", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


def _default_output_dir() -> Path:
    """Resolve the configured output folder; fall back to ../WheelOps."""

    config_path = Path("config.yaml")
    if config_path.exists():
        from wheel_screener.run import load_config

        return (config_path.parent / load_config(config_path)["paths"]["output"]).resolve()
    return Path("../WheelOps").resolve()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Serve WheelOps reports over the local network."
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Folder to serve (default: paths.output from config.yaml).",
    )
    arguments = parser.parse_args()
    run_server(
        arguments.output_dir
        if arguments.output_dir is not None
        else _default_output_dir(),
        port=arguments.port,
    )

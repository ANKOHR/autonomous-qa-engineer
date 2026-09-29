"""Synthetic fixture applications served with Python's standard library."""

from __future__ import annotations

import html
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


FIXTURE_CATALOGUE = {
    "buggy": {
        "label": "Synthetic Buggy App",
        "planted_bugs": [
            "broken link returns 404",
            "required form fields are accepted when empty or overlong",
            "empty lookup input returns HTTP 500",
            "slow page exceeds the response-time threshold",
            "one page is missing its required h1 element",
        ],
    },
    "clean": {"label": "Synthetic Clean App", "planted_bugs": []},
}


def _page(title: str, body: str, *, include_heading: bool = True) -> bytes:
    heading = f"<h1>{html.escape(title)}</h1>" if include_heading else ""
    document = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"aqe-required\" content=\"h1\"><title>"
        + html.escape(title)
        + "</title></head><body>"
        + heading
        + body
        + "</body></html>"
    )
    return document.encode("utf-8")


def _home(app: str) -> bytes:
    if app == "buggy":
        links = (
            '<a href="/contact">Contact</a> '
            '<a href="/missing-page">Missing page</a> '
            '<a href="/api/lookup?q=">Empty lookup</a> '
            '<a href="/slow">Slow page</a> '
            '<a href="/missing-heading">Page without heading</a>'
        )
    else:
        links = (
            '<a href="/contact">Contact</a> '
            '<a href="/about">About</a> '
            '<a href="/api/lookup?q=hello">Lookup</a> '
            '<a href="/slow">Status page</a>'
        )
    return _page(FIXTURE_CATALOGUE[app]["label"], links)


def _contact(app: str) -> bytes:
    form = (
        '<form action="/submit" method="post">'
        '<label>Name <input name="name" type="text" required maxlength="40"></label>'
        '<label>Email <input name="email" type="email" required maxlength="120"></label>'
        '<button type="submit">Send</button></form>'
        '<a href="/">Home</a>'
    )
    return _page(f"{FIXTURE_CATALOGUE[app]['label']} contact", form)


class FixtureHandler(BaseHTTPRequestHandler):
    server_version = "AQESyntheticFixture/1.0"
    sys_version = ""

    @property
    def app_name(self) -> str:
        return self.server.app_name  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/":
            self._send(200, _home(self.app_name))
        elif path == "/contact":
            self._send(200, _contact(self.app_name))
        elif self.app_name == "buggy" and path == "/missing-heading":
            self._send(200, _page("Page without heading", "<p>The required heading is missing.</p>", include_heading=False))
        elif self.app_name == "buggy" and path == "/missing-page":
            self._send(404, b"Synthetic fixture: page not found", "text/plain; charset=utf-8")
        elif path == "/api/lookup":
            query = parse_qs(parsed.query, keep_blank_values=True)
            value = query.get("q", [""])[0]
            if self.app_name == "buggy" and not value:
                self._send(500, b"Synthetic fixture error: lookup input is empty", "text/plain; charset=utf-8")
            elif self.app_name == "buggy":
                self._send(200, ("Synthetic lookup result: " + html.escape(value)).encode("utf-8"), "text/plain; charset=utf-8")
            else:
                self._send(200, ("Synthetic lookup result: " + html.escape(value or "default")).encode("utf-8"), "text/plain; charset=utf-8")
        elif path == "/slow":
            if self.app_name == "buggy":
                time.sleep(0.35)
            self._send(200, _page(f"{FIXTURE_CATALOGUE[self.app_name]['label']} status", "<p>Fixture status page.</p>"))
        elif self.app_name == "clean" and path == "/about":
            self._send(200, _page("Synthetic Clean App about", "<p>This synthetic fixture is clean.</p>"))
        else:
            self._send(404, b"Synthetic fixture: page not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/submit":
            self._send(404, b"Synthetic fixture: endpoint not found", "text/plain; charset=utf-8")
            return
        size = int(self.headers.get("Content-Length", "0"))
        values = parse_qs(self.rfile.read(size).decode("utf-8", errors="replace"), keep_blank_values=True)
        name = values.get("name", [""])[0]
        email = values.get("email", [""])[0]
        if self.app_name == "clean":
            if not name.strip() or not email.strip():
                self._send(400, b"Validation error: name and email are required")
                return
            if len(name) > 40 or len(email) > 120:
                self._send(400, b"Validation error: input exceeds maximum length")
                return
        body = _page("Synthetic form accepted", f"<p>Accepted for {html.escape(name)}.</p>")
        self._send(200, body)


class FixtureHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], app_name: str):
        if app_name not in FIXTURE_CATALOGUE:
            raise ValueError(f"Unknown fixture app: {app_name}")
        self.app_name = app_name
        super().__init__(address, FixtureHandler)


def start_fixture_server(app_name: str, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Create a fixture server; the caller owns its serve_forever lifecycle."""
    return FixtureHTTPServer((host, port), app_name)

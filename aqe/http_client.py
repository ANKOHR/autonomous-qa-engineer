"""Small deterministic HTTP client shared by exploration and test execution."""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class HTTPResult:
    status_code: int | None
    headers: dict[str, str]
    body: bytes
    duration_ms: float
    error: str | None = None


def request(
    url: str,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 3.0,
) -> HTTPResult:
    request_headers = {
        "User-Agent": "AQE-HTTP-Client/0.1",
        "Accept-Encoding": "identity",
    }
    if headers:
        request_headers.update(headers)
    req = Request(url, data=body, headers=request_headers, method=method.upper())
    start = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout) as response:
            payload = response.read()
            status = response.status
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            error = None
    except HTTPError as exc:
        payload = exc.read()
        status = exc.code
        response_headers = {key.lower(): value for key, value in exc.headers.items()}
        error = None
    except (URLError, TimeoutError, OSError) as exc:
        payload = b""
        status = None
        response_headers = {}
        error = f"{type(exc).__name__}: {exc}"
    duration_ms = round((time.perf_counter() - start) * 1000, 3)
    return HTTPResult(status, response_headers, payload, duration_ms, error)


def decode_body(result: HTTPResult) -> str:
    content_type = result.headers.get("content-type", "")
    charset = "utf-8"
    for part in content_type.split(";")[1:]:
        name, separator, value = part.strip().partition("=")
        if separator and name.lower() == "charset":
            charset = value.strip('"') or "utf-8"
            break
    try:
        return result.body.decode(charset, errors="replace")
    except LookupError:
        return result.body.decode("utf-8", errors="replace")


def excerpt(text: str, limit: int = 320) -> str:
    return " ".join(text.replace("\x00", "").split())[:limit]

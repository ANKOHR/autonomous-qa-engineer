"""Execute generated cases over HTTP and retain replayable request evidence."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from .http_client import decode_body, excerpt, request
from .reporting import build_bug_list


class ElementFinder(HTMLParser):
    def __init__(self, required: str):
        super().__init__(convert_charrefs=True)
        self.required = required.lower()
        self.found = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == self.required:
            self.found = True


def _make_request(test: dict[str, object]) -> tuple[str, str, dict[str, str], bytes | None]:
    method = str(test.get("method", "GET")).upper()
    url = str(test["url"])
    headers: dict[str, str] = {}
    body: bytes | None = None
    values = test.get("form_values")
    if values is not None:
        encoded = urlencode([(str(name), str(value)) for name, value in values])
        if method == "GET":
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{encoded}" if encoded else url
        else:
            body = encoded.encode("ascii")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
    return method, url, headers, body


def _assert(test: dict[str, object], status: int | None, text: str, duration_ms: float) -> tuple[bool, str]:
    assertion = str(test["assertion"])
    if assertion == "http_success_status":
        passed = status is not None and 200 <= status < 400
        return passed, "expected an HTTP status from 200 to 399"
    if assertion in {"required_fields_rejected", "maxlength_rejected"}:
        rejected = status is not None and 400 <= status < 500
        validation_message = any(word in text.lower() for word in ("validation error", "invalid input", "required field", "must be"))
        passed = status is not None and status < 500 and (rejected or validation_message)
        expected = "invalid form input must be rejected by the server"
        return passed, expected
    if assertion == "no_server_error":
        return status is not None and status < 500, "special characters must not cause an HTTP 500 or transport error"
    if assertion == "required_element_present":
        finder = ElementFinder(str(test["element"]))
        finder.feed(text)
        return finder.found, f"response must contain <{test['element']}>"
    if assertion == "http_success_within_threshold":
        threshold = float(test["threshold_ms"])
        passed = status is not None and 200 <= status < 400 and duration_ms <= threshold
        return passed, f"expected HTTP success within {threshold:g} ms"
    return False, f"unknown assertion: {assertion}"


def run_catalogue(
    catalogue: dict[str, object],
    output_dir: str | Path,
    *,
    timeout: float = 3.0,
) -> dict[str, object]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    outcomes: list[dict[str, object]] = []
    for test in catalogue.get("tests", []):
        method, url, headers, body = _make_request(test)
        result = request(url, method=method, body=body, headers=headers, timeout=timeout)
        response_text = decode_body(result)
        passed, expectation = _assert(test, result.status_code, response_text, result.duration_ms)
        recorded_headers = {
            "Accept-Encoding": "identity",
            "Host": urlsplit(url).netloc,
            "User-Agent": "AQE-HTTP-Client/0.1",
        }
        recorded_headers.update(headers)
        if body is not None:
            recorded_headers["Content-Length"] = str(len(body))
        request_record = {
            "method": method,
            "url": url,
            "headers": recorded_headers,
            "body": body.decode("ascii") if body is not None else None,
        }
        outcome: dict[str, object] = {
            "test_id": test["id"],
            "test_name": test["name"],
            "test_type": test["type"],
            "edge_kind": test.get("edge_kind"),
            "assertion": test["assertion"],
            "expectation": expectation,
            "passed": passed,
            "failed_assertion": None if passed else test["assertion"],
            "request": request_record,
            "response": {
                "status_code": result.status_code,
                "excerpt": excerpt(response_text),
                "duration_ms": result.duration_ms,
                "error": result.error,
            },
        }
        if "form_id" in test:
            outcome["form_id"] = test["form_id"]
        if "element" in test:
            outcome["element"] = test["element"]
        if "threshold_ms" in test:
            outcome["threshold_ms"] = test["threshold_ms"]
        outcomes.append(outcome)

    results: dict[str, object] = {
        "schema_version": 1,
        "base_url": catalogue.get("base_url", ""),
        "summary": {
            "total": len(outcomes),
            "passed": sum(1 for item in outcomes if item["passed"]),
            "failed": sum(1 for item in outcomes if not item["passed"]),
        },
        "outcomes": outcomes,
    }
    (output / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="")
    bugs = build_bug_list(results)
    (output / "bugs.json").write_text(json.dumps(bugs, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="")
    return results


def run_from_file(
    catalogue_path: str | Path,
    output_dir: str | Path,
    *,
    timeout: float = 3.0,
) -> dict[str, object]:
    catalogue = json.loads(Path(catalogue_path).read_text(encoding="utf-8"))
    return run_catalogue(catalogue, output_dir, timeout=timeout)

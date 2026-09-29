"""Stable bug list construction and reproducible Markdown/HTML reports."""

from __future__ import annotations

import html
import json
from pathlib import Path


HONESTY_BANNER = (
    "The bundled apps are synthetic fixtures. AQE is an HTTP-only client. It does not execute JavaScript, "
    "render pages, or take real screenshots. Page snapshots are saved HTML."
)


def _bug_identity(outcome: dict[str, object]) -> tuple[str, str, str, str]:
    response = outcome.get("response", {})
    request = outcome.get("request", {})
    status = response.get("status_code")
    url = str(request.get("url", ""))
    test_type = str(outcome.get("test_type", ""))
    assertion = str(outcome.get("assertion", ""))
    if isinstance(status, int) and status >= 500:
        return f"server_error:{url}", "HTTP server error", "high", f"An endpoint returned HTTP {status}."
    if test_type == "link_status":
        return f"broken_link:{url}", "Broken link", "medium", f"The linked URL returned HTTP {status}."
    if test_type == "form_edge" and assertion in {"required_fields_rejected", "maxlength_rejected"}:
        form_id = str(outcome.get("form_id", "unknown-form"))
        return f"form_validation:{form_id}", "Form accepts invalid input", "medium", "The server accepted input that should have been rejected."
    if assertion == "required_element_present":
        element = str(outcome.get("element", "required element"))
        return f"missing_element:{url}:{element}", "Required page element is missing", "medium", f"The response does not contain the required <{element}> element."
    if assertion == "http_success_within_threshold":
        return f"slow_response:{url}", "Slow response", "low", "The page exceeded its configured response-time threshold."
    return f"failed_test:{outcome.get('test_id', 'unknown')}", "Test assertion failed", "medium", str(outcome.get("expectation", "The test assertion failed."))


def build_bug_list(results: dict[str, object], *, include_timings: bool = False) -> dict[str, object]:
    grouped: dict[str, dict[str, object]] = {}
    for outcome in results.get("outcomes", []):
        if outcome.get("passed"):
            continue
        key, title, severity, description = _bug_identity(outcome)
        group = grouped.setdefault(key, {
            "key": key,
            "title": title,
            "severity": severity,
            "description": description,
            "evidence": [],
        })
        response = outcome.get("response", {})
        item: dict[str, object] = {
            "test_id": outcome.get("test_id"),
            "test_name": outcome.get("test_name"),
            "assertion": outcome.get("failed_assertion"),
            "request": outcome.get("request"),
            "status_code": response.get("status_code"),
            "excerpt": response.get("excerpt", ""),
            "error": response.get("error"),
        }
        if include_timings:
            item["duration_ms"] = response.get("duration_ms")
        group["evidence"].append(item)

    bugs = []
    for number, key in enumerate(sorted(grouped), start=1):
        bug = grouped[key]
        bug["id"] = f"AQE-{number:03d}"
        bugs.append(bug)
    return {"schema_version": 1, "bug_count": len(bugs), "bugs": bugs}


def _request_block(evidence: dict[str, object]) -> str:
    request = evidence.get("request", {})
    lines = [f"{request.get('method', 'GET')} {request.get('url', '')} HTTP/1.1"]
    for name, value in sorted((request.get("headers") or {}).items()):
        lines.append(f"{name}: {value}")
    if request.get("body") is not None:
        lines.extend(["", str(request["body"])])
    return "\n".join(lines)


def render_markdown(results: dict[str, object]) -> str:
    bug_list = build_bug_list(results, include_timings=True)
    summary = results.get("summary", {})
    lines = [
        "# Autonomous QA Engineer bug report",
        "",
        f"> **Honesty boundary:** {HONESTY_BANNER}",
        "",
        f"Tests: {summary.get('total', 0)} total, {summary.get('passed', 0)} passed, {summary.get('failed', 0)} failed.",
        f"Bugs: {bug_list['bug_count']}.",
        "",
        "Severity rubric: HTTP 500 and other server errors are high, broken links are medium, form validation and missing required elements are medium, and slow responses are low.",
    ]
    for bug in bug_list["bugs"]:
        lines.extend(["", f"## {bug['id']}: {bug['title']}", "", f"Severity: **{bug['severity']}**", "", str(bug["description"]), ""])
        for evidence in bug["evidence"]:
            lines.extend([
                f"### Reproduction request: {evidence['test_id']}",
                "",
                "Replay this HTTP request exactly:",
                "",
                "```http",
                _request_block(evidence),
                "```",
                "",
                f"Evidence: status {evidence['status_code']}; {evidence.get('duration_ms', 0):.3f} ms.",
                "",
                f"Response excerpt: `{str(evidence.get('excerpt', '')).replace('`', '\\`')}`",
            ])
    if bug_list["bug_count"] == 0:
        lines.extend(["", "No failed assertions were recorded."])
    return "\n".join(lines).rstrip() + "\n"


def render_html(results: dict[str, object]) -> str:
    bug_list = build_bug_list(results, include_timings=True)
    summary = results.get("summary", {})
    pieces = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>Autonomous QA Engineer bug report</title>",
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#18212b}header{border:2px solid #a35b00;background:#fff4df;padding:1rem;margin-bottom:1.5rem}section{border-top:1px solid #ccd3da;padding:1rem 0}pre{background:#f2f4f7;padding:1rem;overflow:auto;white-space:pre-wrap}.high{color:#a31313}.medium{color:#825100}.low{color:#315f8c}code{overflow-wrap:anywhere}</style></head><body>",
        "<header><strong>Honesty boundary:</strong> " + html.escape(HONESTY_BANNER) + "</header>",
        "<h1>Autonomous QA Engineer bug report</h1>",
        f"<p>Tests: {summary.get('total', 0)} total, {summary.get('passed', 0)} passed, {summary.get('failed', 0)} failed. Bugs: {bug_list['bug_count']}.</p>",
        "<p>Severity rubric: HTTP 500 and other server errors are high, broken links are medium, form validation and missing required elements are medium, and slow responses are low.</p>",
    ]
    for bug in bug_list["bugs"]:
        pieces.extend([
            f"<section><h2>{html.escape(str(bug['id']))}: {html.escape(str(bug['title']))}</h2>",
            f"<p class=\"{html.escape(str(bug['severity']))}\"><strong>Severity: {html.escape(str(bug['severity']))}</strong></p>",
            f"<p>{html.escape(str(bug['description']))}</p>",
        ])
        for evidence in bug["evidence"]:
            pieces.extend([
                f"<h3>Reproduction request: {html.escape(str(evidence['test_id']))}</h3>",
                "<p>Replay this HTTP request exactly:</p>",
                f"<pre>{html.escape(_request_block(evidence))}</pre>",
                f"<p>Evidence: status {html.escape(str(evidence['status_code']))}; {float(evidence.get('duration_ms') or 0):.3f} ms.</p>",
                f"<p>Response excerpt: <code>{html.escape(str(evidence.get('excerpt', '')))}</code></p>",
            ])
        pieces.append("</section>")
    if bug_list["bug_count"] == 0:
        pieces.append("<p>No failed assertions were recorded.</p>")
    pieces.append("</body></html>")
    return "\n".join(pieces) + "\n"


def render_report(results: dict[str, object], format_name: str) -> str:
    if format_name == "md":
        return render_markdown(results)
    if format_name == "html":
        return render_html(results)
    raise ValueError("format must be md or html")


def report_from_file(
    results_path: str | Path,
    format_name: str,
    output_path: str | Path | None = None,
) -> str:
    source = Path(results_path)
    if source.is_dir():
        source = source / "results.json"
    results = json.loads(source.read_text(encoding="utf-8"))
    rendered = render_report(results, format_name)
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="")
    return rendered

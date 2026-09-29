from __future__ import annotations

import json
from urllib.request import Request, urlopen

from aqe.executor import run_catalogue
from aqe.explorer import explore
from aqe.generator import generate_tests
from aqe.http_client import request
from aqe.reporting import build_bug_list, render_html, render_markdown


def _run_app(fixture_server, tmp_path, app_name: str, folder: str):
    base = fixture_server(app_name)
    sitemap = explore(base, tmp_path / f"{folder}-sitemap.json", max_depth=2)
    catalogue = generate_tests(sitemap)
    results = run_catalogue(catalogue, tmp_path / folder)
    return base, sitemap, catalogue, results


def test_buggy_app_finds_exactly_the_five_planted_bugs(fixture_server, tmp_path):
    _base, _sitemap, _catalogue, results = _run_app(fixture_server, tmp_path, "buggy", "buggy-run")
    bugs = build_bug_list(results)
    titles = {bug["title"] for bug in bugs["bugs"]}
    assert bugs["bug_count"] == 5
    assert titles == {
        "Broken link",
        "Form accepts invalid input",
        "HTTP server error",
        "Required page element is missing",
        "Slow response",
    }
    severity = {bug["title"]: bug["severity"] for bug in bugs["bugs"]}
    assert severity["HTTP server error"] == "high"
    assert severity["Broken link"] == "medium"
    assert severity["Slow response"] == "low"


def test_clean_app_has_no_findings(fixture_server, tmp_path):
    _base, _sitemap, _catalogue, results = _run_app(fixture_server, tmp_path, "clean", "clean-run")
    assert results["summary"]["failed"] == 0
    assert build_bug_list(results)["bugs"] == []


def test_every_bug_has_http_requests_that_reproduce_its_failure(fixture_server, tmp_path):
    _base, _sitemap, _catalogue, results = _run_app(fixture_server, tmp_path, "buggy", "replay-run")
    bugs = build_bug_list(results, include_timings=True)
    assert bugs["bug_count"] == 5
    for bug in bugs["bugs"]:
        assert bug["evidence"]
        for evidence in bug["evidence"]:
            replay = evidence["request"]
            body = replay["body"].encode("ascii") if replay["body"] is not None else None
            result = request(replay["url"], replay["method"], body=body, headers=replay["headers"])
            assert result.status_code == evidence["status_code"]
            assert evidence["duration_ms"] >= 0
            if bug["title"] == "Slow response":
                assert result.duration_ms > 180
            if bug["title"] == "Broken link":
                assert result.status_code == 404
            if bug["title"] == "HTTP server error":
                assert result.status_code == 500
            if bug["title"] == "Form accepts invalid input":
                assert result.status_code == 200
            if bug["title"] == "Required page element is missing":
                assert b"<h1" not in result.body.lower()


def test_reports_include_http_only_banner_and_reproduction_requests(fixture_server, tmp_path):
    _base, _sitemap, _catalogue, results = _run_app(fixture_server, tmp_path, "buggy", "report-run")
    markdown = render_markdown(results)
    page = render_html(results)
    assert "bundled apps are synthetic fixtures" in markdown
    assert "JavaScript" in markdown and "real screenshots" in markdown
    assert "POST http://" in markdown
    assert "duration" not in markdown.lower() or "ms" in markdown
    assert "bundled apps are synthetic fixtures" in page
    assert "HTTP-only client" in page
    assert "Reproduction request" in page


def test_bug_list_json_is_byte_identical_across_repeated_runs(fixture_server, tmp_path):
    base = fixture_server("buggy")
    first_map = tmp_path / "first-map.json"
    second_map = tmp_path / "second-map.json"
    first_sitemap = explore(base, first_map, max_depth=2)
    second_sitemap = explore(base, second_map, max_depth=2)
    assert first_map.read_bytes() == second_map.read_bytes()
    first_catalogue = generate_tests(first_sitemap)
    second_catalogue = generate_tests(second_sitemap)
    assert json.dumps(first_catalogue, sort_keys=True) == json.dumps(second_catalogue, sort_keys=True)
    run_catalogue(first_catalogue, tmp_path / "first-run")
    run_catalogue(second_catalogue, tmp_path / "second-run")
    assert (tmp_path / "first-run" / "bugs.json").read_bytes() == (tmp_path / "second-run" / "bugs.json").read_bytes()

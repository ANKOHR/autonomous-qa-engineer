from __future__ import annotations

import json

from aqe.explorer import explore
from aqe.generator import generate_from_file, generate_tests


def test_generator_derives_edge_input_and_required_element_cases(fixture_server, tmp_path):
    sitemap_path = tmp_path / "sitemap.json"
    sitemap = explore(fixture_server("buggy"), sitemap_path, max_depth=2)
    catalogue = generate_tests(sitemap)
    assert {test.get("edge_kind") for test in catalogue["tests"] if test["type"] == "form_edge"} == {
        "empty_required", "overlong", "special_characters"
    }
    assert any(test["type"] == "required_element" and test["url"].endswith("/missing-heading") for test in catalogue["tests"])
    assert any(test["type"] == "response_time" and test["url"].endswith("/slow") for test in catalogue["tests"])
    saved = tmp_path / "tests.json"
    generate_from_file(sitemap_path, saved)
    assert json.loads(saved.read_text(encoding="utf-8")) == generate_tests(sitemap)


def test_generator_is_deterministic_for_same_site_map(fixture_server, tmp_path):
    sitemap = explore(fixture_server("clean"), tmp_path / "unused-sitemap.json", max_depth=2)
    first = json.dumps(generate_tests(sitemap), sort_keys=True)
    second = json.dumps(generate_tests(sitemap), sort_keys=True)
    assert first == second

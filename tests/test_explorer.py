from __future__ import annotations

import json

from aqe.explorer import explore


def test_explorer_records_buggy_pages_forms_and_broken_link(fixture_server, tmp_path):
    sitemap = explore(fixture_server("buggy"), tmp_path / "sitemap.json", max_depth=2)
    assert "/contact" in " ".join(sitemap["visited_urls"])
    assert "/missing-page" in " ".join(sitemap["visited_urls"])
    assert any(form["action_url"].endswith("/submit") for form in sitemap["forms"])
    assert any(field["name"] == "email" and field["required"] for form in sitemap["forms"] for field in form["fields"])
    assert any(link["target_url"].endswith("/missing-page") for link in sitemap["link_graph"])
    assert sitemap["pages"][sitemap["base_url"]]["is_html"]
    snapshot = tmp_path / sitemap["pages"][sitemap["base_url"]]["snapshot_path"]
    assert snapshot.exists()
    assert json.loads((tmp_path / "sitemap.json").read_text(encoding="utf-8"))["schema_version"] == 1


def test_explorer_depth_limit_prevents_following_child_links(fixture_server, tmp_path):
    sitemap = explore(fixture_server("buggy"), tmp_path / "shallow.json", max_depth=0)
    assert sitemap["visited_urls"] == [sitemap["base_url"]]
    assert sitemap["link_graph"]


def test_explorer_rejects_invalid_base_url(tmp_path):
    try:
        explore("file:///etc/passwd", tmp_path / "bad.json")
    except ValueError as exc:
        assert "absolute http" in str(exc)
    else:
        raise AssertionError("invalid URL was accepted")

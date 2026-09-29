from __future__ import annotations

from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from aqe.fixtures import start_fixture_server


def test_fixture_server_starts_and_buggy_app_serves_planted_behaviour(fixture_server):
    base = fixture_server("buggy")
    assert b"Synthetic Buggy App" in urlopen(base).read()
    assert b"name=\"name\"" in urlopen(base + "contact").read()
    with pytest.raises(HTTPError) as broken:
        urlopen(base + "missing-page")
    assert broken.value.code == 404
    with pytest.raises(HTTPError) as failed:
        urlopen(base + "api/lookup?q=")
    assert failed.value.code == 500
    assert b"required heading is missing" in urlopen(base + "missing-heading").read()


def test_clean_fixture_serves_healthy_pages_and_lookup(fixture_server):
    base = fixture_server("clean")
    assert b"Synthetic Clean App" in urlopen(base).read()
    assert b"<h1>" in urlopen(base + "about").read()
    assert b"Synthetic lookup result" in urlopen(base + "api/lookup?q=").read()


def test_fixture_server_rejects_unknown_app():
    with pytest.raises(ValueError, match="Unknown fixture app"):
        start_fixture_server("unknown")

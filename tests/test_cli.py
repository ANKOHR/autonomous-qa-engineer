from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _aqe(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "aqe", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_cli_smoke_for_each_subcommand(fixture_server, tmp_path):
    listing = _aqe("fixtures", cwd=tmp_path)
    assert listing.returncode == 0
    assert "buggy" in listing.stdout and "clean" in listing.stdout
    assert "synthetic" in listing.stdout.lower()

    base = fixture_server("buggy")
    sitemap_path = tmp_path / "site.json"
    catalogue_path = tmp_path / "tests.json"
    run_dir = tmp_path / "run"
    report_path = tmp_path / "run" / "report.html"

    explored = _aqe("explore", base, "--out", str(sitemap_path), cwd=tmp_path)
    assert explored.returncode == 0, explored.stderr
    generated = _aqe("generate", "--sitemap", str(sitemap_path), "--out", str(catalogue_path), cwd=tmp_path)
    assert generated.returncode == 0, generated.stderr
    executed = _aqe("run", "--tests", str(catalogue_path), "--out", str(run_dir), cwd=tmp_path)
    assert executed.returncode == 0, executed.stderr
    reported = _aqe("report", "--results", str(run_dir), "--format", "html", "--out", str(report_path), cwd=tmp_path)
    assert reported.returncode == 0, reported.stderr
    assert sitemap_path.exists() and catalogue_path.exists()
    assert (run_dir / "results.json").exists() and (run_dir / "bugs.json").exists()
    report = report_path.read_text(encoding="utf-8")
    assert "bundled apps are synthetic fixtures" in report
    assert "HTTP-only client" in report
    import json
    assert json.loads((run_dir / "bugs.json").read_text(encoding="utf-8"))["bug_count"] == 5


def test_cli_fixtures_serve_starts_real_http_server(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    process = subprocess.Popen(
        [sys.executable, "-m", "aqe", "fixtures", "--serve", "--app", "clean", "--port", "0"],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        ready = process.stdout.readline().strip()
        assert "Serving synthetic fixture 'clean' at http://" in ready
        url = ready.rsplit(" ", 1)[-1]
        from urllib.request import urlopen
        assert b"Synthetic Clean App" in urlopen(url, timeout=2).read()
    finally:
        process.terminate()
        process.wait(timeout=5)

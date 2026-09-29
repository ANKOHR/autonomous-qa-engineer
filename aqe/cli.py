"""Command line interface for the Autonomous QA Engineer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .executor import run_from_file
from .explorer import explore
from .fixtures import FIXTURE_CATALOGUE, start_fixture_server
from .generator import generate_from_file
from .reporting import HONESTY_BANNER, report_from_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aqe",
        description="Crawl an app over HTTP, generate tests, execute requests, and report reproducible failures.",
        epilog="HTTP-only client: JavaScript is not executed, pages are not rendered, and real screenshots are not taken.",
    )
    parser.add_argument("--version", action="version", version=f"aqe {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    fixtures = commands.add_parser("fixtures", help="list or serve synthetic fixture apps")
    fixtures.add_argument("--serve", action="store_true", help="serve the selected synthetic fixture")
    fixtures.add_argument("--app", choices=sorted(FIXTURE_CATALOGUE), help="fixture name")
    fixtures.add_argument("--host", default="127.0.0.1", help="bind address")
    fixtures.add_argument("--port", type=int, default=8000, help="port to bind, or 0 for an available port")

    exploration = commands.add_parser("explore", help="crawl pages, links, and forms into a site map")
    exploration.add_argument("base_url", help="absolute HTTP or HTTPS URL to crawl")
    exploration.add_argument("--out", default="sitemap.json", help="site map JSON output path")
    exploration.add_argument("--snapshot-dir", help="directory for saved HTML page snapshots")
    exploration.add_argument("--max-depth", type=int, default=2, help="maximum link depth from the starting URL")
    exploration.add_argument("--timeout", type=float, default=3.0, help="per-request timeout in seconds")

    generation = commands.add_parser("generate", help="derive an HTTP test catalogue from a site map")
    generation.add_argument("--sitemap", required=True, help="site map JSON created by explore")
    generation.add_argument("--out", default="aqe-tests.json", help="test catalogue JSON output path")
    generation.add_argument("--slow-threshold-ms", type=float, default=180.0, help="response-time limit in milliseconds")

    execution = commands.add_parser("run", help="execute a generated catalogue over HTTP")
    execution.add_argument("--tests", required=True, help="test catalogue JSON created by generate")
    execution.add_argument("--out", default="aq-run", help="directory for results.json and bugs.json")
    execution.add_argument("--timeout", type=float, default=3.0, help="per-request timeout in seconds")

    reporting = commands.add_parser("report", help="write a reproducible Markdown or HTML bug report")
    reporting.add_argument("--results", default="aq-run", help="results.json path or run output directory")
    reporting.add_argument("--format", choices=("md", "html"), default="md", help="report format")
    reporting.add_argument("--out", help="report output path; defaults beside results.json")
    return parser


def _print_honesty() -> None:
    print(HONESTY_BANNER)


def _run_fixtures(args: argparse.Namespace) -> int:
    if not args.serve:
        for name in sorted(FIXTURE_CATALOGUE):
            item = FIXTURE_CATALOGUE[name]
            bugs = "; ".join(item["planted_bugs"]) if item["planted_bugs"] else "no planted bugs"
            print(f"{name}: {item['label']} (synthetic); {bugs}")
        _print_honesty()
        return 0
    if not args.app:
        raise ValueError("--app is required with --serve")
    server = start_fixture_server(args.app, args.host, args.port)
    host, port = server.server_address[:2]
    display_host = f"[{host}]" if ":" in host else host
    print(f"Serving synthetic fixture '{args.app}' at http://{display_host}:{port}/", flush=True)
    _print_honesty()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Fixture server stopped.")
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "fixtures":
            return _run_fixtures(args)
        if args.command == "explore":
            sitemap = explore(
                args.base_url,
                args.out,
                max_depth=args.max_depth,
                timeout=args.timeout,
                snapshot_dir=args.snapshot_dir,
            )
            print(f"Explored {len(sitemap['visited_urls'])} URLs, found {len(sitemap['forms'])} forms, and saved the site map to {args.out}.")
            _print_honesty()
            return 0
        if args.command == "generate":
            catalogue = generate_from_file(args.sitemap, args.out, slow_threshold_ms=args.slow_threshold_ms)
            print(f"Generated {len(catalogue['tests'])} HTTP test cases at {args.out}.")
            _print_honesty()
            return 0
        if args.command == "run":
            results = run_from_file(args.tests, args.out, timeout=args.timeout)
            summary = results["summary"]
            print(f"Executed {summary['total']} tests: {summary['passed']} passed, {summary['failed']} failed.")
            print(f"Results and deterministic bug list saved to {args.out}.")
            _print_honesty()
            return 0
        if args.command == "report":
            source = Path(args.results)
            results_file = source / "results.json" if source.is_dir() else source
            output = Path(args.out) if args.out else results_file.parent / f"report.{args.format}"
            report_from_file(args.results, args.format, output)
            print(f"Wrote {args.format.upper()} bug report to {output}.")
            _print_honesty()
            return 0
        parser.error("unknown command")
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print(f"aqe: {exc}", file=sys.stderr)
        return 2
    return 0

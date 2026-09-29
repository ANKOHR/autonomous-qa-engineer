# Autonomous QA Engineer

Autonomous QA Engineer (AQE) crawls a web app over HTTP, builds a site map, derives a test catalogue, executes the requests, and writes reproducible bug reports. Its portfolio proof is: "It crawls your app, writes its own test cases, runs them, and hands you a bug list where every bug comes with the exact requests that reproduce it."

AQE uses Python's standard library at runtime. The bundled apps are synthetic fixtures with controlled behaviour. No training, GPU libraries, browser driver, or external service is used.

## Quickstart

Install Python 3.10 or newer, then install AQE and its test extra:

```sh
python -m pip install -e ".[test]"
```

Start the buggy synthetic fixture in one terminal:

```sh
aqe fixtures --serve --app buggy --port 8000
```

In another terminal, explore, generate tests, execute them, and write a report:

```sh
aqe explore http://127.0.0.1:8000/ --out sitemap.json
aqe generate --sitemap sitemap.json --out tests.json
aqe run --tests tests.json --out aq-run
aqe report --results aq-run --format md --out aq-run/report.md
aqe report --results aq-run --format html --out aq-run/report.html
```

The fixture server prints that its app is synthetic. AQE also prints its HTTP-only boundary. `aqe fixtures` lists the available fixture apps. Use `--port 0` to have the operating system choose a free port.

The `run` command writes `results.json`, which includes each observed status, response excerpt, measured duration, assertion, and replayable request. It also writes `bugs.json`, whose stable output omits variable request durations so identical findings compare byte for byte. Markdown and HTML reports include the observed request durations.

Run the complete test suite with:

```sh
python -m pytest
```

## Architecture

```text
synthetic fixture app or target HTTP URL
                 |
                 v
       explore (HTTP GET crawler)
          |              |
          v              v
      site map       saved HTML snapshots
          |
          v
  generate (map-derived test catalogue)
          |
          v
     run (real HTTP requests)
          |              |
          v              v
    results.json     deterministic bugs.json
          |
          v
   report (Markdown or HTML with replay requests)
```

The explorer follows same-origin links up to a depth limit and records links, forms, form fields, required elements declared by the page, response status, and the saved HTML path. The generator uses only that site map to create link checks, form cases, required-element checks, and response-time checks. The executor submits those cases with `urllib`, measures each request, and stores the exact method, URL, headers, and body. The report groups related failed assertions into bugs and preserves the requests needed to reproduce them.

No random values are generated, so there is no random seed. Ordering is normalized at each serialization boundary. The response-time threshold defaults to 180 milliseconds and can be changed with `aqe generate --slow-threshold-ms`.

## HONESTY BOUNDARY

The fixture apps are SYNTHETIC with planted bugs. The "browser" is an HTTP client: it does NOT execute JavaScript, render pages, or take real screenshots; page snapshots are saved HTML. The CLI output, reports, and README state this plainly. AQE does not claim real browser automation, JavaScript testing, or visual regression. It can send HTTP requests to a real staging URL, but this build only validates HTTP responses and the HTML bytes returned by the server.

## Bug severity rubric

- **High:** an endpoint returns HTTP 500 or another server error.
- **Medium:** a link returns an error status, invalid form input is accepted, or a required page element is missing.
- **Low:** a page exceeds the configured response-time threshold.

The report records the assertion and evidence for each finding. Every reproduction block includes the method, URL, request headers, and request body exactly as recorded by the executor. Status, response excerpt, and elapsed request time accompany the reproduction request.

## Fixture app catalogue

All apps below are synthetic and served by Python's standard library HTTP server.

### `buggy`

- `/missing-page` is linked from the home page and returns HTTP 404.
- The `/contact` form accepts empty required fields and a name longer than its declared maximum.
- `/api/lookup?q=` returns HTTP 500 for empty lookup input.
- `/slow` waits 350 milliseconds before responding, above the default 180 millisecond threshold.
- `/missing-heading` declares that `h1` is required but omits that element.

### `clean`

The clean fixture has working internal links, a form that validates required and maximum-length fields, a lookup endpoint that accepts empty input safely, responsive pages, and the required heading on each HTML page. It has no planted bugs.

## Commands

- `aqe fixtures [--serve --app buggy|clean]`: list or serve a synthetic fixture.
- `aqe explore <base-url> --out sitemap.json`: crawl pages and write a site map plus HTML snapshots.
- `aqe generate --sitemap sitemap.json --out tests.json`: derive the test catalogue.
- `aqe run --tests tests.json --out aq-run`: execute requests and write results and a deterministic bug list.
- `aqe report --results aq-run --format md|html`: write a report with reproduction evidence.

All commands are HTTP-only. The client does not execute page scripts or render returned pages.

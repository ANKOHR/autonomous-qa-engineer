"""Depth-limited HTTP crawler that records a stable site map and HTML snapshots."""

from __future__ import annotations

import hashlib
import json
import os
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit

from .http_client import decode_body, excerpt, request


def canonical_url(url: str) -> str:
    no_fragment, _fragment = urldefrag(url)
    parts = urlsplit(no_fragment)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


class PageParser(HTMLParser):
    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.links: list[dict[str, str]] = []
        self.forms: list[dict[str, object]] = []
        self.required_elements: set[str] = set()
        self._form: dict[str, object] | None = None
        self._anchor: dict[str, str] | None = None
        self._textarea: dict[str, object] | None = None
        self._select: dict[str, object] | None = None

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key.lower(): (value or "") for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = self._attrs(attrs)
        tag = tag.lower()
        if tag == "meta" and values.get("name", "").lower() == "aqe-required":
            self.required_elements.update(item.strip().lower() for item in values.get("content", "").split(",") if item.strip())
        elif tag == "a" and values.get("href"):
            self._anchor = {"url": canonical_url(urljoin(self.page_url, values["href"])), "text": ""}
        elif tag == "form":
            method = values.get("method", "get").upper()
            if method not in {"GET", "POST"}:
                method = "GET"
            self._form = {
                "action_url": canonical_url(urljoin(self.page_url, values.get("action") or self.page_url)),
                "method": method,
                "fields": [],
            }
            self.forms.append(self._form)
        elif self._form is not None and tag == "input":
            field_type = values.get("type", "text").lower()
            if field_type not in {"submit", "button", "reset", "image"} and values.get("name"):
                self._add_field(values, field_type)
        elif self._form is not None and tag == "textarea" and values.get("name"):
            self._textarea = {"field": self._field_from_attrs(values, "textarea"), "parts": []}
        elif self._form is not None and tag == "select" and values.get("name"):
            self._select = {"field": self._field_from_attrs(values, "select"), "options": [], "selected": None}
        elif self._select is not None and tag == "option":
            option_value = values.get("value", "")
            if "selected" in values:
                self._select["selected"] = option_value
            self._select["options"].append(option_value)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "a" and self._anchor is not None:
            self.links.append(self._anchor)
            self._anchor = None
        elif tag == "form":
            self._form = None
            self._textarea = None
            self._select = None
        elif tag == "textarea" and self._textarea is not None:
            field = self._textarea["field"]
            field["value"] = "".join(self._textarea["parts"])
            self._form["fields"].append(field)  # type: ignore[index]
            self._textarea = None
        elif tag == "select" and self._select is not None:
            field = self._select["field"]
            selected = self._select["selected"] or (self._select["options"][0] if self._select["options"] else "")
            field["value"] = selected
            self._form["fields"].append(field)  # type: ignore[index]
            self._select = None

    def handle_data(self, data: str) -> None:
        if self._anchor is not None:
            self._anchor["text"] += data
        if self._textarea is not None:
            self._textarea["parts"].append(data)

    @staticmethod
    def _field_from_attrs(values: dict[str, str], field_type: str) -> dict[str, object]:
        field: dict[str, object] = {
            "name": values["name"],
            "type": field_type,
            "required": "required" in values,
            "value": values.get("value", ""),
        }
        if values.get("maxlength", "").isdigit():
            field["maxlength"] = int(values["maxlength"])
        if values.get("minlength", "").isdigit():
            field["minlength"] = int(values["minlength"])
        return field

    def _add_field(self, values: dict[str, str], field_type: str) -> None:
        self._form["fields"].append(self._field_from_attrs(values, field_type))  # type: ignore[index]


def _is_same_origin(candidate: str, base: str) -> bool:
    left, right = urlsplit(candidate), urlsplit(base)
    return (left.scheme.lower(), left.netloc.lower()) == (right.scheme.lower(), right.netloc.lower())


def explore(
    base_url: str,
    sitemap_path: str | Path,
    *,
    max_depth: int = 2,
    timeout: float = 3.0,
    snapshot_dir: str | Path | None = None,
) -> dict[str, object]:
    if max_depth < 0:
        raise ValueError("max_depth must be zero or greater")
    base = canonical_url(base_url)
    if urlsplit(base).scheme not in {"http", "https"} or not urlsplit(base).netloc:
        raise ValueError("base_url must be an absolute http or https URL")
    target = Path(sitemap_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    snapshots = Path(snapshot_dir) if snapshot_dir else target.parent / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    queue: deque[tuple[str, int]] = deque([(base, 0)])
    scheduled = {base}
    page_data: dict[str, dict[str, object]] = {}
    form_data: list[dict[str, object]] = []
    graph: list[dict[str, object]] = []

    while queue:
        current, depth = queue.popleft()
        result = request(current, timeout=timeout)
        content = decode_body(result)
        content_type = result.headers.get("content-type", "")
        is_html = "html" in content_type.lower() or content.lstrip().lower().startswith(("<!doctype html", "<html"))
        parsed = PageParser(current)
        if is_html:
            parsed.feed(content)
            parsed.close()
        digest = hashlib.sha256(current.encode("utf-8")).hexdigest()[:16]
        snapshot_name = f"{digest}.html"
        (snapshots / snapshot_name).write_text(content, encoding="utf-8", newline="")
        snapshot_path = (snapshots / snapshot_name).resolve()
        try:
            relative_snapshot = snapshot_path.relative_to(target.parent.resolve())
        except ValueError:
            relative_snapshot = Path(os.path.relpath(snapshot_path, target.parent.resolve()))
        page_data[current] = {
            "url": current,
            "depth": depth,
            "status_code": result.status_code,
            "content_type": content_type,
            "is_html": is_html,
            "required_elements": sorted(parsed.required_elements),
            "snapshot_path": relative_snapshot.as_posix(),
            "response_excerpt": excerpt(content),
            "fetch_error": result.error,
        }
        for index, form in enumerate(parsed.forms, start=1):
            form_data.append({
                "id": f"form-{digest}-{index}",
                "page_url": current,
                "action_url": form["action_url"],
                "method": form["method"],
                "fields": form["fields"],
            })
        for link in parsed.links:
            same_origin = _is_same_origin(link["url"], base)
            graph.append({
                "source_url": current,
                "target_url": link["url"],
                "anchor_text": " ".join(link["text"].split()),
                "same_origin": same_origin,
            })
            if same_origin and link["url"] not in scheduled and depth < max_depth:
                scheduled.add(link["url"])
                queue.append((link["url"], depth + 1))

    page_data = dict(sorted(page_data.items()))
    form_data.sort(key=lambda item: (str(item["page_url"]), str(item["id"])))
    graph.sort(key=lambda item: (str(item["source_url"]), str(item["target_url"]), str(item["anchor_text"])))
    sitemap: dict[str, object] = {
        "schema_version": 1,
        "base_url": base,
        "max_depth": max_depth,
        "visited_urls": sorted(page_data),
        "pages": page_data,
        "forms": form_data,
        "link_graph": graph,
    }
    target.write_text(json.dumps(sitemap, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="")
    return sitemap

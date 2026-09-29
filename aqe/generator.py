"""Generate reproducible HTTP test cases from an AQE site map."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode


SPECIAL_VALUE = "<script>alert(1)</script>&\"'\u2603"


def _valid_value(field: dict[str, object]) -> str:
    field_type = str(field.get("type", "text")).lower()
    name = str(field.get("name", "")).lower()
    if field_type == "email" or "email" in name:
        return "aqe@example.test"
    if field_type == "url":
        return "https://example.test/"
    if field_type in {"number", "range"}:
        return "42"
    if field_type in {"checkbox", "radio"}:
        return str(field.get("value") or "on")
    return str(field.get("value") or "AQE Test")


def _form_values(fields: list[dict[str, object]]) -> list[list[str]]:
    return [[str(field["name"]), _valid_value(field)] for field in fields if field.get("name")]


def generate_tests(
    sitemap: dict[str, object],
    *,
    slow_threshold_ms: float = 180.0,
) -> dict[str, object]:
    if slow_threshold_ms <= 0:
        raise ValueError("slow_threshold_ms must be greater than zero")
    tests: list[dict[str, object]] = []
    pages = sitemap.get("pages", {})
    links = sitemap.get("link_graph", [])
    forms = sitemap.get("forms", [])
    base_url = str(sitemap.get("base_url", ""))

    unique_links: dict[tuple[str, str], dict[str, object]] = {}
    for link in links:
        if link.get("same_origin"):
            key = (str(link["source_url"]), str(link["target_url"]))
            unique_links.setdefault(key, link)
    for (source, target), link in sorted(unique_links.items()):
        tests.append({
            "type": "link_status",
            "name": f"Link from {source} to {target} returns successfully",
            "method": "GET",
            "url": target,
            "source_url": source,
            "anchor_text": link.get("anchor_text", ""),
            "assertion": "http_success_status",
        })

    for form in sorted(forms, key=lambda item: (str(item.get("page_url", "")), str(item.get("id", "")))):
        fields = [field for field in form.get("fields", []) if field.get("name")]
        valid_values = _form_values(fields)
        method = str(form.get("method", "GET")).upper()
        action = str(form.get("action_url", base_url))
        common = {"form_id": form.get("id"), "form_url": form.get("page_url"), "method": method, "url": action}
        tests.append({
            **common,
            "type": "form_valid",
            "name": f"Form {form.get('id')} accepts valid input",
            "assertion": "http_success_status",
            "form_values": valid_values,
        })
        required = [str(field["name"]) for field in fields if field.get("required")]
        if required:
            empty_values = [[name, ""] if name in required else [name, value] for name, value in valid_values]
            tests.append({
                **common,
                "type": "form_edge",
                "edge_kind": "empty_required",
                "name": f"Form {form.get('id')} rejects empty required fields",
                "assertion": "required_fields_rejected",
                "assertion_args": {"fields": required},
                "form_values": empty_values,
            })
        length_fields = [field for field in fields if isinstance(field.get("maxlength"), int)]
        if length_fields:
            chosen = sorted(length_fields, key=lambda field: (int(field["maxlength"]), str(field["name"])))[0]
            max_length = int(chosen["maxlength"])
            overlong_values = [
                [name, "X" * (max_length + 1) if name == chosen["name"] else value]
                for name, value in valid_values
            ]
            tests.append({
                **common,
                "type": "form_edge",
                "edge_kind": "overlong",
                "name": f"Form {form.get('id')} rejects overlong {chosen['name']}",
                "assertion": "maxlength_rejected",
                "assertion_args": {"field": chosen["name"], "maxlength": max_length},
                "form_values": overlong_values,
            })
        text_fields = [field for field in fields if str(field.get("type", "text")).lower() not in {"checkbox", "radio", "file", "submit", "button"}]
        if text_fields:
            chosen = sorted(text_fields, key=lambda field: str(field["name"]))[0]
            special_values = [[name, SPECIAL_VALUE if name == chosen["name"] else value] for name, value in valid_values]
            tests.append({
                **common,
                "type": "form_edge",
                "edge_kind": "special_characters",
                "name": f"Form {form.get('id')} handles special characters safely",
                "assertion": "no_server_error",
                "assertion_args": {"field": chosen["name"]},
                "form_values": special_values,
            })

    for page_url, page in sorted(pages.items()):
        if page.get("is_html") and page.get("status_code") is not None and int(page["status_code"]) < 400:
            for element in sorted(page.get("required_elements", [])):
                tests.append({
                    "type": "required_element",
                    "name": f"Page {page_url} contains required element {element}",
                    "method": "GET",
                    "url": page_url,
                    "element": element,
                    "assertion": "required_element_present",
                })
            tests.append({
                "type": "response_time",
                "name": f"Page {page_url} responds within {slow_threshold_ms:g} ms",
                "method": "GET",
                "url": page_url,
                "threshold_ms": slow_threshold_ms,
                "assertion": "http_success_within_threshold",
            })

    ordering = lambda test: (str(test.get("url", "")), str(test.get("type", "")), str(test.get("edge_kind", "")), str(test.get("name", "")))
    tests.sort(key=ordering)
    for number, test in enumerate(tests, start=1):
        test["id"] = f"T{number:04d}"
    catalogue = {
        "schema_version": 1,
        "base_url": base_url,
        "slow_threshold_ms": slow_threshold_ms,
        "tests": tests,
    }
    return catalogue


def generate_from_file(
    sitemap_path: str | Path,
    output_path: str | Path,
    *,
    slow_threshold_ms: float = 180.0,
) -> dict[str, object]:
    sitemap = json.loads(Path(sitemap_path).read_text(encoding="utf-8"))
    catalogue = generate_tests(sitemap, slow_threshold_ms=slow_threshold_ms)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalogue, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="")
    return catalogue

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

HASH_TEMPLATE_PATTERN = re.compile(r"\{\{\s*#([a-zA-Z0-9_]+(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)\s*#\s*\}\}")
SIMPLE_TEMPLATE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def normalize_template_parameter_name(variable: str) -> str:
    return variable.replace(".", "_")


def extract_template_parameter_names(template: str) -> list[str]:
    if not template:
        return []

    seen = OrderedDict[str, None]()

    for match in HASH_TEMPLATE_PATTERN.finditer(template):
        seen[normalize_template_parameter_name(match.group(1))] = None

    for match in SIMPLE_TEMPLATE_PATTERN.finditer(template):
        seen[normalize_template_parameter_name(match.group(1))] = None

    return list(seen.keys())


def render_template_with_parameters(template: str, parameters: dict[str, Any]) -> str:
    if not template:
        return ""

    def replace_hash(match: re.Match[str]) -> str:
        key = normalize_template_parameter_name(match.group(1))
        return str(parameters.get(key, ""))

    def replace_simple(match: re.Match[str]) -> str:
        key = normalize_template_parameter_name(match.group(1))
        return str(parameters.get(key, ""))

    rendered = HASH_TEMPLATE_PATTERN.sub(replace_hash, template)
    rendered = SIMPLE_TEMPLATE_PATTERN.sub(replace_simple, rendered)
    return rendered


def extract_http_template_parameter_names(node_config: dict[str, Any]) -> list[str]:
    templates: list[str] = []

    url = node_config.get("url")
    if isinstance(url, str):
        templates.append(url)

    body = node_config.get("body")
    if isinstance(body, dict):
        body_data = body.get("data")
        if isinstance(body_data, list):
            for item in body_data:
                if not isinstance(item, dict):
                    continue
                key = item.get("key")
                value = item.get("value")
                if isinstance(key, str):
                    templates.append(key)
                if isinstance(value, str):
                    templates.append(value)

    seen = OrderedDict[str, None]()
    for template in templates:
        for name in extract_template_parameter_names(template):
            seen[name] = None

    return list(seen.keys())

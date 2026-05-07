from __future__ import annotations

import base64
import json
from collections.abc import Generator
from typing import TYPE_CHECKING, Any

from core.helper.ssrf_proxy import graphon_ssrf_proxy
from core.tools.entities.tool_entities import ToolInvokeMessage
from core.tools.workflow_node_tool.template_utils import render_template_with_parameters
from graphon.nodes.http_request.entities import HttpRequestNodeData

if TYPE_CHECKING:
    from ..tool import WorkflowNodeTool


def invoke_http_request(
    *,
    tool: WorkflowNodeTool,
    tool_parameters: dict[str, Any],
) -> Generator[ToolInvokeMessage, None, None]:
    try:
        node_data = HttpRequestNodeData.model_validate(tool.node_config)
        url = render_template_with_parameters(node_data.url, tool_parameters)
        if not url:
            yield tool.create_text_message(text="HTTP request URL is empty.")
            return

        headers = _parse_headers(node_data.headers, tool_parameters)
        headers.update(_build_auth_headers(node_data.authorization.model_dump(mode="python"), tool_parameters))
        params = _parse_key_value_lines(node_data.params, tool_parameters)
        body_config = node_data.body.model_dump(mode="python") if node_data.body else None
        timeout_config = node_data.timeout.model_dump(mode="python") if node_data.timeout else None
        request_kwargs = _build_request_kwargs(body_config, tool_parameters)
        request_kwargs["headers"] = headers
        request_kwargs["params"] = params or None
        request_kwargs["timeout"] = _build_timeout_tuple(timeout_config)
        request_kwargs["ssl_verify"] = bool(node_data.ssl_verify) if node_data.ssl_verify is not None else True
        request_kwargs["follow_redirects"] = True

        method = node_data.method.lower()
        method_map = {
            "get": graphon_ssrf_proxy.get,
            "head": graphon_ssrf_proxy.head,
            "post": graphon_ssrf_proxy.post,
            "put": graphon_ssrf_proxy.put,
            "delete": graphon_ssrf_proxy.delete,
            "patch": graphon_ssrf_proxy.patch,
        }
        request = method_map.get(method)
        if request is None:
            yield tool.create_text_message(text=f"Unsupported HTTP method: {node_data.method}")
            return

        response = request(url=url, max_retries=0, **request_kwargs)
        body_text = response.text

        yield tool.create_json_message(
            object={
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": body_text,
            }
        )
        yield tool.create_text_message(text=body_text or f"HTTP {response.status_code}")
    except Exception as e:
        yield tool.create_text_message(text=f"HTTP request tool failed: {e}")


def _parse_headers(raw_headers: str, parameters: dict[str, Any]) -> dict[str, str]:
    rendered = render_template_with_parameters(raw_headers or "", parameters)
    headers: dict[str, str] = {}
    for line in rendered.splitlines():
        if not line.strip():
            continue
        key, *value = line.split(":", 1)
        key = key.strip()
        if not key:
            continue
        headers[key] = value[0].strip() if value else ""
    return headers


def _parse_key_value_lines(raw_value: str, parameters: dict[str, Any]) -> list[tuple[str, str]]:
    rendered = render_template_with_parameters(raw_value or "", parameters)
    pairs: list[tuple[str, str]] = []
    for line in rendered.splitlines():
        if not line.strip():
            continue
        key, *value = line.split(":", 1)
        normalized_key = key.strip()
        if not normalized_key:
            continue
        normalized_value = value[0].strip() if value else ""
        pairs.append((normalized_key, normalized_value))
    return pairs


def _build_auth_headers(authorization: dict[str, Any], parameters: dict[str, Any]) -> dict[str, str]:
    if authorization.get("type") != "api-key":
        return {}

    config = authorization.get("config") or {}
    header = str(config.get("header") or "Authorization")
    api_key = render_template_with_parameters(str(config.get("api_key") or ""), parameters)
    auth_type = str(config.get("type") or "bearer")

    if not api_key:
        return {}
    if auth_type == "bearer":
        return {header: f"Bearer {api_key}"}
    if auth_type == "basic":
        encoded = api_key
        if ":" in api_key:
            encoded = base64.b64encode(api_key.encode("utf-8")).decode("utf-8")
        return {header: f"Basic {encoded}"}
    return {header: api_key}


def _build_request_kwargs(body: dict[str, Any] | None, parameters: dict[str, Any]) -> dict[str, Any]:
    if not body:
        return {}

    body_type = body.get("type")
    data_items = body.get("data") or []

    if body_type in ("none", None):
        return {"content": ""}

    if body_type == "raw-text":
        value = _first_body_value(data_items)
        return {"content": render_template_with_parameters(value, parameters)}

    if body_type == "json":
        value = _first_body_value(data_items)
        rendered = render_template_with_parameters(value, parameters)
        if not rendered:
            return {"json": {}}
        return {"json": json.loads(rendered)}

    if body_type in ("x-www-form-urlencoded", "form-data"):
        payload: dict[str, str] = {}
        for item in data_items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if body_type == "form-data" and item_type == "file":
                continue
            key = render_template_with_parameters(str(item.get("key") or ""), parameters)
            value = render_template_with_parameters(str(item.get("value") or ""), parameters)
            if key:
                payload[key] = value
        return {"data": payload}

    raise ValueError(f"Unsupported HTTP body type: {body_type}")


def _first_body_value(data_items: Any) -> str:
    if not isinstance(data_items, list) or not data_items:
        return ""
    first_item = data_items[0]
    if not isinstance(first_item, dict):
        return ""
    return str(first_item.get("value") or "")


def _build_timeout_tuple(timeout_config: dict[str, Any] | None) -> tuple[int | None, int | None, int | None]:
    if not timeout_config:
        return (None, None, None)
    connect = timeout_config.get("connect")
    read = timeout_config.get("read")
    write = timeout_config.get("write")
    return (connect, read, write)

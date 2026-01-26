"""
Utilities for parsing tool calls from text-based model outputs.
"""

from __future__ import annotations

import json
from typing import Any

TOOL_CALLS_BEGIN = "TERNION_TOOL_CALLS_BEGIN"
TOOL_CALLS_END = "TERNION_TOOL_CALLS_END"
STREAM_TOOL_CALLS_PREFIX = "TERNION_STREAM_TOOL_CALLS_JSON:"
_MAX_SCHEMA_CHARS = 1200


def encode_stream_tool_calls(tool_calls: list[dict[str, Any]]) -> str:
    """
    Encode tool calls into an internal streaming marker string.

    This is a server-internal protocol used to transport tool-calls metadata through
    provider streaming generators without changing the public provider interface.
    The marker must NEVER be forwarded to users.
    """
    try:
        payload = json.dumps(tool_calls or [], ensure_ascii=False)
    except Exception:
        payload = "[]"
    return f"{STREAM_TOOL_CALLS_PREFIX}{payload}"


def decode_stream_tool_calls(text: str | None) -> list[dict[str, Any]] | None:
    """
    Decode tool calls from an internal streaming marker string.

    Returns None if the text is not a tool-calls marker.
    """
    if not text or not isinstance(text, str):
        return None
    if not text.startswith(STREAM_TOOL_CALLS_PREFIX):
        return None
    payload = text[len(STREAM_TOOL_CALLS_PREFIX):].strip()
    try:
        data = json.loads(payload)
    except Exception:
        return None
    if not isinstance(data, list):
        return None
    out: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            out.append(item)
    return out or None


def build_text_tool_calls_instruction(cursor_tools: list[dict[str, Any]]) -> str:
    """
    Build a tool-calls protocol instruction for providers without native tool calls.
    """
    tool_lines = _format_tool_list(cursor_tools)
    protocol = [
        "[NON-OPENAI TOOL CALLS PROTOCOL]",
        "If you need tools, respond with ONLY the following block (no extra text):",
        TOOL_CALLS_BEGIN,
        "{",
        '  "tool_calls": [',
        '    {"name": "read_file", "arguments": {"target_file": "...", "offset": 0, "limit": 200}}',
        "  ]",
        "}",
        TOOL_CALLS_END,
        "",
        "Rules:",
        "- Use ONLY tools from the list below.",
        "- arguments must be valid JSON objects.",
        "- Do not include code fences or additional prose.",
        "",
        "Available tools:",
        *tool_lines,
    ]
    return "\n".join(protocol).strip()


def extract_tool_calls_from_text(text: str | None) -> list[dict[str, Any]] | None:
    """
    Extract tool calls from a text response using the Ternion tool-call protocol.
    """
    if not text or not isinstance(text, str):
        return None

    payload = _extract_payload(text)
    if payload is None:
        return None

    data = _parse_json(payload)
    if not isinstance(data, dict):
        return None

    raw_calls = data.get("tool_calls")
    if not isinstance(raw_calls, list):
        return None

    normalized: list[dict[str, Any]] = []
    for item in raw_calls:
        call = _normalize_tool_call(item)
        if call:
            normalized.append(call)

    return normalized or None


def _extract_payload(text: str) -> str | None:
    if TOOL_CALLS_BEGIN in text and TOOL_CALLS_END in text:
        start = text.find(TOOL_CALLS_BEGIN) + len(TOOL_CALLS_BEGIN)
        end = text.find(TOOL_CALLS_END, start)
        if end > start:
            return text[start:end].strip()
        return None

    return text.strip()


def _parse_json(payload: str) -> Any:
    try:
        return json.loads(payload)
    except Exception:
        return None


def _normalize_tool_call(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    if "function" in item and isinstance(item["function"], dict):
        name = item["function"].get("name")
        arguments = item["function"].get("arguments")
    else:
        name = item.get("name")
        arguments = item.get("arguments")

    if not isinstance(name, str) or not name.strip():
        return None

    arguments_str = _normalize_arguments(arguments)
    return {
        "type": "function",
        "function": {
            "name": name,
            "arguments": arguments_str,
        },
    }


def _normalize_arguments(arguments: Any) -> str:
    if arguments is None:
        return "{}"
    if isinstance(arguments, str):
        return arguments
    try:
        return json.dumps(arguments, ensure_ascii=False)
    except Exception:
        return "{}"


def _format_tool_list(cursor_tools: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for tool in cursor_tools or []:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        params = function.get("parameters")
        params_preview = _stringify_params(params)
        if params_preview:
            lines.append(f"- {name}: parameters={params_preview}")
        else:
            lines.append(f"- {name}")
    return lines or ["- (no tools provided)"]


def _stringify_params(params: Any) -> str:
    if params is None:
        return ""
    try:
        encoded = json.dumps(params, ensure_ascii=False)
    except Exception:
        return ""
    if len(encoded) <= _MAX_SCHEMA_CHARS:
        return encoded
    return encoded[:_MAX_SCHEMA_CHARS] + "..."

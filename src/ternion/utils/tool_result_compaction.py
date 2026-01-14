"""
Deterministic compaction for Cursor tool results.

This module reduces oversized tool outputs before passing them to the Writer.
It does not call any LLM. The raw tool outputs can be persisted separately in
the execution session for debugging and reproducibility.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResultCompactionConfig:
    """Configuration for deterministic tool result compaction."""

    max_chars: int = 12_000

    read_file_head_chars: int = 5_500
    read_file_tail_chars: int = 2_500
    read_file_index_chars: int = 2_500
    read_file_max_index_items: int = 40
    read_file_max_line_len: int = 360

    generic_head_chars: int = 8_000
    generic_tail_chars: int = 2_500


_NUMBERED_LINE_RE = re.compile(r"^\s*(\d+)\|(.*)$")
_DEF_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\s*def\s+([A-Za-z_]\w*)\s*\("), "def"),
    (re.compile(r"^\s*class\s+([A-Za-z_]\w*)\b"), "class"),
    (re.compile(r"^\s*(export\s+)?(default\s+)?function\s+([A-Za-z_]\w*)\b"), "function"),
    (re.compile(r"^\s*(export\s+)?class\s+([A-Za-z_]\w*)\b"), "class"),
    (re.compile(r"^\s*interface\s+([A-Za-z_]\w*)\b"), "interface"),
    (re.compile(r"^\s*type\s+([A-Za-z_]\w*)\b"), "type"),
    (re.compile(r"^\s*enum\s+([A-Za-z_]\w*)\b"), "enum"),
    (re.compile(r"^\s*(export\s+)?const\s+([A-Za-z_]\w*)\s*="), "const"),
]


def compact_tool_result(
    *,
    tool_name: str | None,
    content: str | None,
    tool_arguments: str | None = None,
    config: ToolResultCompactionConfig | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Compact a tool result deterministically.

    Returns:
        (compacted_content, meta)
    """
    cfg = config or ToolResultCompactionConfig()
    raw = content or ""

    meta: dict[str, Any] = {
        "tool_name": tool_name or "",
        "original_chars": len(raw),
        "compacted": False,
        "strategy": "none",
    }

    if len(raw) <= cfg.max_chars:
        return raw, meta

    if (tool_name or "") == "read_file":
        compacted, details = _compact_read_file(
            raw=raw,
            tool_arguments=tool_arguments,
            cfg=cfg,
        )
        meta.update(details)
        return compacted, meta

    compacted = _compact_generic(
        raw=raw,
        tool_name=tool_name or "",
        tool_arguments=tool_arguments,
        cfg=cfg,
    )
    meta["compacted"] = True
    meta["strategy"] = "generic_head_tail"
    meta["compacted_chars"] = len(compacted)
    return compacted, meta


def _compact_read_file(
    *,
    raw: str,
    tool_arguments: str | None,
    cfg: ToolResultCompactionConfig,
) -> tuple[str, dict[str, Any]]:
    args = _parse_json_object(tool_arguments)
    target_file = str(args.get("target_file") or "")
    offset = args.get("offset")
    limit = args.get("limit")

    lines = raw.splitlines()
    numbered = [_NUMBERED_LINE_RE.match(line) for line in lines]
    looks_numbered = sum(1 for m in numbered if m) >= max(3, len(lines) // 3)

    header_lines = [
        "[TERNION COMPACTED TOOL RESULT]",
        f"tool=read_file",
        f"target_file={target_file}" if target_file else "target_file=(unknown)",
        f"offset={offset}" if isinstance(offset, int) else "offset=(unspecified)",
        f"limit={limit}" if isinstance(limit, int) else "limit=(unspecified)",
        f"original_chars={len(raw)}",
        "",
        "Note: The tool output was compacted for context budget. Do not assume omitted content.",
        "Fetch additional context via read_file with offset/limit, ideally after locating the region with grep/codebase_search.",
    ]
    header = "\n".join(header_lines).strip()

    if not looks_numbered:
        compacted = _compact_generic(
            raw=raw,
            tool_name="read_file",
            tool_arguments=tool_arguments,
            cfg=cfg,
        )
        return compacted, {
            "compacted": True,
            "strategy": "read_file_generic_fallback",
            "compacted_chars": len(compacted),
        }

    parsed_lines: list[tuple[int, str, str]] = []
    for line in lines:
        match = _NUMBERED_LINE_RE.match(line)
        if not match:
            continue
        num = int(match.group(1))
        text = match.group(2)
        parsed_lines.append((num, text, line))

    index_items = _extract_definition_index(
        parsed_lines=parsed_lines,
        max_items=cfg.read_file_max_index_items,
    )
    index_block = _join_with_budget(
        lines=[f"- {item}" for item in index_items],
        budget=cfg.read_file_index_chars,
    )
    if not index_block.strip():
        index_block = "- (no obvious definitions found)"

    head_block = _excerpt_from_start(
        parsed_lines=parsed_lines,
        budget=cfg.read_file_head_chars,
        max_line_len=cfg.read_file_max_line_len,
    )
    tail_block = _excerpt_from_end(
        parsed_lines=parsed_lines,
        budget=cfg.read_file_tail_chars,
        max_line_len=cfg.read_file_max_line_len,
    )

    compacted_parts = [
        header,
        "",
        "[INDEX]",
        index_block,
        "",
        "[EXCERPT: START]",
        head_block or "(empty)",
        "",
        "[EXCERPT: END]",
        tail_block or "(empty)",
        "",
        "[NEXT STEPS]",
        "- Use grep/codebase_search to locate a symbol/phrase.",
        "- Then call read_file with offset/limit around that region.",
        "- Keep reads small (e.g., limit=200..400) and iterate.",
    ]

    compacted = "\n".join(compacted_parts).strip()
    if len(compacted) > cfg.max_chars:
        compacted = compacted[: cfg.max_chars].rstrip() + "\n\n[TRUNCATED]"

    return compacted, {
        "compacted": True,
        "strategy": "read_file_structured",
        "compacted_chars": len(compacted),
    }


def _compact_generic(
    *,
    raw: str,
    tool_name: str,
    tool_arguments: str | None,
    cfg: ToolResultCompactionConfig,
) -> str:
    head = raw[: cfg.generic_head_chars]
    tail = raw[-cfg.generic_tail_chars :] if len(raw) > cfg.generic_tail_chars else ""

    args_preview = ""
    if tool_arguments and isinstance(tool_arguments, str):
        preview = tool_arguments.strip()
        args_preview = preview[:600] + ("…" if len(preview) > 600 else "")

    parts = [
        "[TERNION COMPACTED TOOL RESULT]",
        f"tool={tool_name}" if tool_name else "tool=(unknown)",
        f"original_chars={len(raw)}",
    ]
    if args_preview:
        parts.append("tool_arguments_preview=" + args_preview.replace("\n", "\\n"))
    parts.extend([
        "",
        "[HEAD]",
        head.rstrip(),
        "",
        "[TAIL]",
        tail.lstrip(),
        "",
        "Note: The tool output was compacted for context budget. Do not assume omitted content.",
    ])
    return "\n".join(parts).strip()


def _parse_json_object(text: str | None) -> dict[str, Any]:
    if not text or not isinstance(text, str):
        return {}
    try:
        value = json.loads(text)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _extract_definition_index(
    *,
    parsed_lines: list[tuple[int, str, str]],
    max_items: int,
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for num, text, _raw_line in parsed_lines:
        stripped = text.strip()
        if not stripped:
            continue

        for pattern, kind in _DEF_PATTERNS:
            match = pattern.match(stripped)
            if not match:
                continue
            name = match.group(match.lastindex or 1) if match.lastindex else match.group(1)
            key = f"{kind}:{name}"
            if key in seen:
                continue
            seen.add(key)
            out.append(f"{num}|{kind} {name}")
            break

        if len(out) >= max_items:
            break
    return out


def _excerpt_from_start(
    *,
    parsed_lines: list[tuple[int, str, str]],
    budget: int,
    max_line_len: int,
) -> str:
    out_lines: list[str] = []
    used = 0
    for _num, _text, raw_line in parsed_lines:
        line = _truncate_line(raw_line, max_line_len=max_line_len)
        if used + len(line) + 1 > budget and out_lines:
            break
        out_lines.append(line)
        used += len(line) + 1
    return "\n".join(out_lines).strip()


def _excerpt_from_end(
    *,
    parsed_lines: list[tuple[int, str, str]],
    budget: int,
    max_line_len: int,
) -> str:
    out_lines: list[str] = []
    used = 0
    for _num, _text, raw_line in reversed(parsed_lines):
        line = _truncate_line(raw_line, max_line_len=max_line_len)
        if used + len(line) + 1 > budget and out_lines:
            break
        out_lines.append(line)
        used += len(line) + 1
    out_lines.reverse()
    return "\n".join(out_lines).strip()


def _truncate_line(line: str, *, max_line_len: int) -> str:
    if len(line) <= max_line_len:
        return line
    return line[: max_line_len - 1] + "…"


def _join_with_budget(*, lines: list[str], budget: int) -> str:
    out_lines: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > budget and out_lines:
            break
        out_lines.append(line)
        used += len(line) + 1
    return "\n".join(out_lines).strip()


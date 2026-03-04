"""
Execution history compaction utilities.

This module applies deterministic, non-LLM compaction strategies to keep the
Writer context within practical budget limits during multi-round tool loops.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionHistoryCompactionConfig:
    """Configuration for execution history compaction."""

    # Prefer retaining more recent raw history to reduce repeated reads in long tool loops.
    max_history_chars: int = 160_000  # ~40K tokens at ~4 chars/token
    max_tail_messages: int = 80
    max_digest_chars: int = 500_000  # ~125K tokens at ~4 chars/token
    max_args_chars: int = 600
    # Keep more tool-result detail in the digest so the Writer can avoid repeating reads
    # after history truncation.
    max_result_chars: int = 1200


def compact_execution_history_for_writer(
    history: list[dict[str, Any]],
    *,
    config: ExecutionHistoryCompactionConfig | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """
    Compact execution history for the Writer.

    Returns:
        (trimmed_history, tool_context_digest)
    """
    cfg = config or ExecutionHistoryCompactionConfig()
    total_chars = _estimate_history_chars(history)
    if total_chars <= cfg.max_history_chars:
        return _sanitize_openai_tool_message_order(history), ""

    digest = _build_tool_context_digest(history, cfg=cfg)

    tail = _tail_messages_with_budget(
        history,
        max_messages=cfg.max_tail_messages,
        max_chars=cfg.max_history_chars,
    )
    tail = _sanitize_openai_tool_message_order(tail)
    return tail, digest


def _estimate_history_chars(history: list[dict[str, Any]]) -> int:
    total = 0
    for msg in history or []:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            total += len(content)
        tool_calls = msg.get("tool_calls")
        if tool_calls is not None:
            try:
                total += len(json.dumps(tool_calls, ensure_ascii=False))
            except Exception:
                total += len(str(tool_calls))
        tool_call_id = msg.get("tool_call_id")
        if isinstance(tool_call_id, str):
            total += len(tool_call_id)
        role = msg.get("role")
        if isinstance(role, str):
            total += len(role)
    return total


def _build_tool_context_digest(
    history: list[dict[str, Any]],
    *,
    cfg: ExecutionHistoryCompactionConfig,
) -> str:
    """
    Build a deterministic digest that helps the Writer navigate tool evidence.

    This digest is intentionally lossy. The Writer should re-fetch exact ranges
    with read_file(offset/limit) when needed.
    """
    call_meta_by_id: dict[str, dict[str, Any]] = {}
    tool_results: list[tuple[str, str, dict[str, Any], str]] = []

    for msg in history or []:
        if not isinstance(msg, dict):
            continue

        role = msg.get("role")
        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    tc_id = tc.get("id")
                    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                    name = fn.get("name") if isinstance(fn.get("name"), str) else ""
                    args = fn.get("arguments") if isinstance(fn.get("arguments"), str) else ""
                    if isinstance(tc_id, str) and tc_id:
                        call_meta_by_id[tc_id] = {
                            "name": name,
                            "arguments": args,
                        }

        if role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if not isinstance(tool_call_id, str) or not tool_call_id:
                continue
            meta = call_meta_by_id.get(tool_call_id, {})
            name = str(meta.get("name") or "")
            args = meta.get("arguments") if isinstance(meta.get("arguments"), str) else ""
            content_text = _coerce_tool_content_text(msg.get("content"))
            result_summary = _summarize_tool_content(content_text, max_len=cfg.max_result_chars)
            tool_results.append((tool_call_id, name, _parse_args(args), result_summary))

    lines: list[str] = [
        "[TERNION TOOL CONTEXT DIGEST]",
        "Note: This digest is lossy. Re-fetch exact evidence with tools when needed.",
        "",
    ]

    if not tool_results:
        lines.append("- (no tool results recorded yet)")
        return _truncate_text("\n".join(lines).strip(), cfg.max_digest_chars)

    # Group by tool for readability.
    by_tool: dict[str, list[tuple[str, dict[str, Any], str]]] = {}
    for tool_call_id, name, parsed_args, result_summary in tool_results:
        by_tool.setdefault(name or "(unknown)", []).append(
            (tool_call_id, parsed_args, result_summary)
        )

    # Keep substantially more than the last 10 calls/tool to reduce repeated reads.
    max_calls_per_tool = 200

    for tool_name, items in sorted(by_tool.items(), key=lambda kv: kv[0]):
        lines.append(f"- tool={tool_name} calls={len(items)}")
        shown = items[-max_calls_per_tool:] if len(items) > max_calls_per_tool else items
        for tool_call_id, parsed_args, result_summary in shown:
            args_preview = _format_args_preview(parsed_args, max_len=cfg.max_args_chars)
            if result_summary:
                lines.append(
                    f"  - {tool_call_id}: args={args_preview} | result={result_summary}".rstrip()
                )
            else:
                lines.append(f"  - {tool_call_id}: args={args_preview}".rstrip())
        if len(items) > max_calls_per_tool:
            lines.append("  - … (more calls omitted)")
        lines.append("")

    return _truncate_text("\n".join(lines).strip(), cfg.max_digest_chars)


def _tail_messages_with_budget(
    history: list[dict[str, Any]],
    *,
    max_messages: int,
    max_chars: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    used = 0

    for msg in reversed(history or []):
        if not isinstance(msg, dict):
            continue
        msg_chars = _estimate_history_chars([msg])
        if out and used + msg_chars > max_chars:
            break
        out.append(msg)
        used += msg_chars
        if len(out) >= max_messages:
            break

    out.reverse()
    return out


def _sanitize_openai_tool_message_order(
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Ensure OpenAI tool-message protocol correctness.

    OpenAI requires tool-role messages to be responses to an immediately
    preceding assistant message containing tool_calls. When history is trimmed,
    it is possible to end up with orphan tool messages, which would trigger a
    400 invalid_request_error.
    """
    out: list[dict[str, Any]] = []
    pending_tool_call_ids: set[str] = set()

    for msg in history or []:
        if not isinstance(msg, dict):
            continue

        role = msg.get("role")

        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                ids: set[str] = set()
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    tc_id = tc.get("id")
                    if isinstance(tc_id, str) and tc_id:
                        ids.add(tc_id)
                pending_tool_call_ids = ids
            else:
                pending_tool_call_ids = set()
            out.append(msg)
            continue

        if role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if (
                isinstance(tool_call_id, str)
                and tool_call_id
                and tool_call_id in pending_tool_call_ids
            ):
                out.append(msg)
                continue
            # Drop orphan tool messages.
            continue

        # Any other role breaks the tool-call adjacency requirement.
        pending_tool_call_ids = set()
        out.append(msg)

    return out


def _parse_args(arguments: str) -> dict[str, Any]:
    if not arguments:
        return {}
    try:
        value = json.loads(arguments)
    except Exception:
        return {"_raw": arguments}
    return value if isinstance(value, dict) else {"_raw": arguments}


def _format_args_preview(args: dict[str, Any], *, max_len: int) -> str:
    try:
        text = json.dumps(args, ensure_ascii=False)
    except Exception:
        text = str(args)
    return _truncate_text(text, max_len)


def _truncate_text(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _coerce_tool_content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False)
    except Exception:
        return str(content)


def _summarize_tool_content(text: str, *, max_len: int) -> str:
    """
    Produce a compact, one-line-ish summary of a tool result.

    This is intentionally lossy: it's meant to help the Writer avoid repeating
    the same discovery work after history truncation.
    """
    raw = (text or "").strip()
    if not raw:
        return ""

    # If we have a structured compaction header, prefer only the header lines.
    if raw.startswith("[TERNION COMPACTED TOOL RESULT]"):
        header_lines: list[str] = []
        for line in raw.splitlines():
            s = line.strip()
            if not s:
                break
            header_lines.append(s)
            if len(header_lines) >= 12:
                break
        summary = " | ".join(header_lines)
        summary = re.sub(r"\s+", " ", summary).strip()
        return _truncate_text(summary, max_len)

    # Otherwise, keep a few high-signal lines (first non-empty lines).
    lines: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        lines.append(s)
        if len(lines) >= 12:
            break

    summary = " | ".join(lines)
    summary = re.sub(r"\s+", " ", summary).strip()
    return _truncate_text(summary, max_len)

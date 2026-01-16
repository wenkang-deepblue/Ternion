"""
API routes for Ternion gateway.

Implements OpenAI-compatible endpoints for chat completions and models listing.
"""

from collections.abc import Iterable
import json
import re
from pathlib import Path

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ternion.core.budget import budget_manager
from ternion.core.config_store import config_store
from ternion.core.intent_classifier import (
    Intent,
    classify_intent_with_fallback,
    get_latest_user_message,
    parse_report_hash_marker,
    parse_session_marker,
)
from ternion.core.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    MessageRole,
    ModelInfo,
    ModelsListResponse,
)
from ternion.core.session_store import (
    ExecutionMode,
    Session,
    SessionStage,
    session_store,
)
from ternion.providers.manager import provider_manager
from ternion.router.message_router import MessageRouter
from ternion.utils.cursor_safety import sanitize_for_cursor_display
from ternion.utils.cursor_request_capture import schedule_cursor_request_capture
from ternion.utils.i18n import MessageKey, get_web_base_url, t
from ternion.utils.log_manager import log_manager
from ternion.utils.report_parser import parse_structured_report
from ternion.utils.streaming import (
    create_sse_stream,
    create_sse_stream_from_queue,
    create_sse_tool_calls_stream,
)
from ternion.workflow.streaming_events import StreamEventQueue

logger = structlog.get_logger(__name__)
router = APIRouter()

_PATCHLIKE_TRIGGERS = (
    "*** Begin Patch",
    "*** End Patch",
    "*** Update File:",
    "*** Add File:",
    "diff --git",
)

_TERNION_TOOL_CALL_ID_SESSION_RE = re.compile(r"\bternion_([a-f0-9]{12})_", re.IGNORECASE)

_READ_FILE_DEFAULT_LIMIT = 300
_READ_FILE_MAX_LIMIT = 400
_TOOL_LOOP_MAX_ROUNDS = 100


_CURSOR_NON_AGENT_MODE_HINTS = (
    # Ask mode
    "Ask mode is active",
    "The user is in ask mode",
    # Plan mode
    "Plan mode is active",
    # Debug mode
    "Debug mode is active",
    "You are now in **DEBUG MODE**",
    "debug_mode_logging",
)


def _iter_message_content_text(content: object) -> Iterable[str]:
    """
    Yield all plain text segments from an OpenAI-compatible message content.

    Cursor may send message content as either:
    - a plain string
    - a multimodal list of content parts (text + image_url)

    This helper extracts only text parts for lightweight, in-memory mode detection.
    """
    if isinstance(content, str):
        text = content.strip()
        if text:
            yield text
        return

    if isinstance(content, list):
        for part in content:
            part_type = getattr(part, "type", None)
            if part_type != "text":
                continue
            text = getattr(part, "text", None)
            if isinstance(text, str):
                text = text.strip()
                if text:
                    yield text


def _request_contains_case_insensitive(request: ChatCompletionRequest, needle: str) -> bool:
    """
    Check whether any request message contains the given substring (case-insensitive).

    This avoids persisting or logging Cursor's system prompt while still allowing
    best-effort detection of Ask/Plan/Debug vs Agent modes.
    """
    if not needle:
        return False
    needle_lower = needle.lower()
    for msg in request.messages:
        for text in _iter_message_content_text(msg.content):
            if needle_lower in text.lower():
                return True
    return False


def _build_session_markers(session: Session, *, stage: SessionStage | None = None) -> str:
    stage_value = stage.value if stage is not None else session.stage.value
    return (
        f"TERNION_SESSION_ID={session.session_id}\n"
        f"TERNION_SESSION_STAGE={stage_value}\n"
        f"TERNION_EXECUTION_MODE={session.execution_mode.value}\n"
        f"TERNION_REPORT_HASH={session.report_hash}"
    )


def _build_guardrail_response(
    *,
    session: Session,
    content: str,
    stage: SessionStage = SessionStage.AWAITING_CONFIRMATION,
) -> str:
    markers = _build_session_markers(session, stage=stage)
    return f"{content}\n{markers}"


def _budget_confirmation_message(session: Session) -> str:
    usage_summary = budget_manager.get_usage_summary()
    usage_pct = str(usage_summary.get("usage_pct", 0))
    content = t(MessageKey.BUDGET_CONFIRM_REQUIRED, usage_pct=usage_pct)
    return _build_guardrail_response(session=session, content=content)


def _budget_exceeded_message(session: Session) -> str:
    content = budget_manager.format_budget_warning("BUDGET_EXCEEDED")
    return _build_guardrail_response(session=session, content=content)


def _tool_loop_failsafe_message(session: Session) -> str:
    content = t(MessageKey.TOOL_LOOP_FAILSAFE_REACHED, max_rounds=_TOOL_LOOP_MAX_ROUNDS)
    return _build_guardrail_response(session=session, content=content)


def _respond_with_text(request: ChatCompletionRequest, content: str) -> Response:
    if request.stream:
        return StreamingResponse(
            create_sse_stream(model=request.model, content=content),
            media_type="text/event-stream",
        )
    return JSONResponse(
        content=ChatCompletionResponse(
            model=request.model,
            choices=[
                Choice(
                    message=ChatMessage(
                        role=MessageRole.ASSISTANT,
                        content=content,
                    )
                )
            ],
        ).model_dump()
    )


def _is_high_confidence_non_agent_mode(request: ChatCompletionRequest) -> bool:
    """
    Detect non-agent Cursor modes (Ask/Plan/Debug) from in-band system reminders.

    Cursor may include a <system_reminder> block in user messages that explicitly
    states a non-agent mode (e.g., "Ask mode is active") and instructs switching
    to Agent mode for code changes. When present, we treat the request as non-agent
    regardless of tools/tool_choice fields.
    """
    return any(
        _request_contains_case_insensitive(request, hint) for hint in _CURSOR_NON_AGENT_MODE_HINTS
    )


def _is_cursor_agent_request(request: ChatCompletionRequest) -> bool:
    """
    Best-effort detection for Cursor Agent mode requests.

    This detection is intentionally conservative:
    - Return False for non-agent modes (Ask/Plan/Debug).
    - Return True when no non-agent mode marker is present.
    """
    return not _is_high_confidence_non_agent_mode(request)


def _phase_start_indicator_text(phase: str) -> str | None:
    """
    Build a localized, Cursor-visible phase start indicator.

    This must use i18n (t/MessageKey) and must not hardcode user-facing text.
    """
    phase_lower = (phase or "").strip().lower()
    if phase_lower == "divergence":
        return t(MessageKey.DIVERGENCE_START)
    if phase_lower == "convergence":
        return t(MessageKey.CONVERGENCE_START)
    if phase_lower == "execution":
        return t(MessageKey.EXECUTION_START)
    if phase_lower == "optimizer":
        return t(MessageKey.OPTIMIZER_START)
    return None


def _is_patch_or_diff_output(text: str) -> bool:
    """
    Detect whether an output likely contains a diff/patch that should remain "patch-only".

    This is used to avoid prefixing the final output with thinking logs, which can
    reduce Cursor's auto-apply stability in strict patch-only scenarios.
    """
    if not text:
        return False
    return any(trigger in text for trigger in _PATCHLIKE_TRIGGERS)


def _parse_execution_session_id(messages: list[dict]) -> str | None:
    """
    Parse execution session_id from tool call identifiers in conversation history.

    Execution follow-ups for tool loops may not include any plain-text session markers.
    In those cases, we rely on `tool_call_id` (tool messages) or `tool_calls[].id`
    (assistant messages) to recover the session identifier.
    """
    for msg in reversed(messages or []):
        role = str(msg.get("role", "") or "")

        if role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if isinstance(tool_call_id, str):
                match = _TERNION_TOOL_CALL_ID_SESSION_RE.search(tool_call_id)
                if match:
                    return match.group(1).lower()

        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    tc_id = tc.get("id")
                    if isinstance(tc_id, str):
                        match = _TERNION_TOOL_CALL_ID_SESSION_RE.search(tc_id)
                        if match:
                            return match.group(1).lower()

    return None


def _rewrite_tool_call_ids(
    tool_calls: list[dict],
    *,
    session_id: str,
    round_index: int,
) -> list[dict]:
    """
    Rewrite tool_call ids to embed session_id for stable follow-up routing.

    Cursor will echo these ids back as `tool_call_id` in tool-role messages.
    """
    rewritten: list[dict] = []
    for idx, tc in enumerate(tool_calls or []):
        if not isinstance(tc, dict):
            continue

        function = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = function.get("name")
        arguments = function.get("arguments")
        if not isinstance(name, str) or not name.strip():
            continue

        if arguments is None:
            arguments_str = "{}"
        elif isinstance(arguments, str):
            arguments_str = arguments
        else:
            import json

            arguments_str = json.dumps(arguments, ensure_ascii=False)

        if name == "read_file":
            arguments_str = _enforce_read_file_pagination(arguments_str)

        new_id = f"ternion_{session_id}_r{round_index:04d}_c{idx:02d}"
        rewritten.append({
            "id": new_id,
            "type": "function",
            "function": {
                "name": name,
                "arguments": arguments_str,
            },
        })

    return rewritten


def _enforce_read_file_pagination(arguments_json: str) -> str:
    """
    Enforce read_file pagination (offset/limit) to avoid oversized contexts.

    This guardrail is deterministic and only applies to read_file tool calls.
    """
    import json

    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except Exception:
        return arguments_json

    if not isinstance(args, dict):
        return arguments_json

    offset = args.get("offset")
    limit = args.get("limit")

    if not isinstance(offset, int) or offset < 1:
        args["offset"] = 1

    if not isinstance(limit, int) or limit < 1:
        args["limit"] = _READ_FILE_DEFAULT_LIMIT
    elif limit > _READ_FILE_MAX_LIMIT:
        args["limit"] = _READ_FILE_MAX_LIMIT

    return json.dumps(args, ensure_ascii=False)


_MUTATING_TOOL_NAMES = {
    "write",
    "search_replace",
    "delete_file",
    "edit_notebook",
}


def _coerce_json_object(text: str) -> dict:
    try:
        value = json.loads(text or "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _extract_tool_name_and_arguments(tc: dict) -> tuple[str | None, str]:
    function = tc.get("function") if isinstance(tc.get("function"), dict) else {}
    name = function.get("name")
    if not isinstance(name, str) or not name.strip():
        return None, "{}"

    arguments = function.get("arguments")
    if arguments is None:
        return name.strip(), "{}"
    if isinstance(arguments, str):
        return name.strip(), arguments

    return name.strip(), json.dumps(arguments, ensure_ascii=False)


def _normalize_file_path(path_str: str) -> str | None:
    if not isinstance(path_str, str) or not path_str.strip():
        return None
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p)
    try:
        return str(p.resolve())
    except Exception:
        return str(p)


def _read_text_file_best_effort(path_str: str) -> str | None:
    try:
        p = Path(path_str)
        if not p.exists() or not p.is_file():
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _extract_mutation_target_path(tool_name: str, arguments_json: str) -> str | None:
    args = _coerce_json_object(arguments_json)
    if tool_name in {"write", "search_replace"}:
        value = args.get("file_path")
        return value if isinstance(value, str) else None
    if tool_name == "delete_file":
        value = args.get("target_file")
        return value if isinstance(value, str) else None
    if tool_name == "edit_notebook":
        value = args.get("target_notebook")
        return value if isinstance(value, str) else None
    return None


def _ensure_baseline_snapshots_for_tool_calls(
    session: Session,
    tool_calls: list[dict],
) -> tuple[dict[str, str], list[str]]:
    baseline = dict(getattr(session, "baseline_file_snapshots", {}) or {})
    modified_files = list(getattr(session, "modified_files", []) or [])
    modified_set = set(modified_files)

    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        name, args_str = _extract_tool_name_and_arguments(tc)
        if not name or name not in _MUTATING_TOOL_NAMES:
            continue
        target = _extract_mutation_target_path(name, args_str)
        normalized = _normalize_file_path(target or "")
        if not normalized:
            continue

        if normalized not in baseline:
            content = _read_text_file_best_effort(normalized)
            if content is not None:
                baseline[normalized] = content

        if normalized not in modified_set:
            modified_files.append(normalized)
            modified_set.add(normalized)

    return baseline, modified_files


def _filter_optimizer_todo_write(
    session: Session,
    tool_calls: list[dict],
) -> tuple[list[dict], bool]:
    """
    Enforce "todo_write at most once" during Optimizer phase.

    Returns:
        (filtered_tool_calls, todo_written_now)
    """
    if not tool_calls:
        return [], False

    already_written = bool(getattr(session, "optimizer_todo_written", False))
    filtered: list[dict] = []
    todo_written_now = False
    todo_seen = False

    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        name, _args = _extract_tool_name_and_arguments(tc)
        if name != "todo_write":
            filtered.append(tc)
            continue
        if already_written:
            continue
        if todo_seen:
            continue
        todo_seen = True
        todo_written_now = True
        filtered.append(tc)

    return filtered, todo_written_now


def _emit_thinking_logs_to_observability(
    thinking_logs: list[str],
    *,
    session_id: str | None,
    context: str,
    suppressed_from_chat: bool,
) -> None:
    """
    Emit thinking logs into the Observability stream.

    This preserves debuggability even when we intentionally suppress thinking logs
    from chat output for patch/diff responses.
    """
    if not thinking_logs:
        return

    prefix = f"session_id={session_id} | " if session_id else ""
    status = "suppressed_from_chat" if suppressed_from_chat else "included_in_chat"
    log_manager.emit(
        level="INFO",
        category="THINKING",
        message=f"{prefix}{context} | {status} | count={len(thinking_logs)}",
    )
    for line in thinking_logs:
        msg = (line or "").strip()
        if not msg:
            continue
        log_manager.emit(
            level="INFO",
            category="THINKING",
            message=f"{prefix}{context} | {msg}",
        )


def get_control_panel_url() -> str:
    """
    Get the Control Panel URL dynamically from user config.

    Uses the configured web port from ports.web, defaulting to 9120.
    This avoids hardcoding URLs throughout the codebase.
    """
    return get_web_base_url()


def _as_blockquote(text: str) -> str:
    """Format text as a Markdown blockquote (safe for multi-line input)."""
    if not text:
        return "> "
    return "\n".join(f"> {line}" for line in text.splitlines())


def _extract_relevant_report_excerpt(
    report: str,
    question: str,
    *,
    max_chars: int = 1200,
    max_sections: int = 3,
) -> str:
    """
    Extract a small relevant excerpt from a long report to answer clarification questions.

    This intentionally avoids echoing the full report to reduce token usage and noise.
    The returned text is sanitized for Cursor display.
    """
    if not report:
        return ""

    normalized_question = (question or "").strip()

    parsed = parse_structured_report(report)
    if parsed.is_structured:
        return _extract_structured_excerpt(
            parsed,
            question=normalized_question,
            max_chars=max_chars,
        )

    # Split report into coarse "sections" (paragraph blocks)
    sections = [s.strip() for s in re.split(r"\n\s*\n", report) if s.strip()]
    if not sections:
        excerpt = report[:max_chars]
        if len(report) > max_chars:
            excerpt += "\n\n…"
        return sanitize_for_cursor_display(excerpt)

    # Extract simple multilingual keywords (ASCII tokens + CJK sequences)
    ascii_keywords = set(re.findall(r"[a-z0-9_]{4,}", normalized_question.lower()))
    cjk_keywords = set(re.findall(r"[\u4e00-\u9fff]{2,}", normalized_question))
    keywords: list[tuple[str, bool]] = [(k, True) for k in ascii_keywords] + [(k, False) for k in cjk_keywords]

    scored: list[tuple[int, str]] = []
    for s in sections:
        score = 0
        s_lower = s.lower()
        for k, is_ascii in keywords:
            score += s_lower.count(k) if is_ascii else s.count(k)
        if score > 0:
            scored.append((score, s))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [s for _, s in scored[:max_sections]]
    else:
        # Fallback: show the first section rather than the full report
        selected = [sections[0]]

    out_parts: list[str] = []
    used = 0
    for s in selected:
        remaining = max_chars - used
        if remaining <= 0:
            break
        chunk = s if len(s) <= remaining else s[:remaining]
        out_parts.append(chunk)
        used += len(chunk)
        if used < max_chars:
            out_parts.append("\n\n")

    excerpt = "".join(out_parts).rstrip()
    if len(excerpt) >= max_chars:
        excerpt += "\n\n…"

    return sanitize_for_cursor_display(excerpt)


def _extract_structured_excerpt(
    parsed: object,
    *,
    question: str,
    max_chars: int,
) -> str:
    """
    Extract a targeted excerpt from a structured report based on the user's question.

    This is a deterministic section-level selection (no LLM semantics).
    """
    q = (question or "").strip().lower()

    # Map question intent to section preference (multi-lingual keyword routing).
    prefer: list[str] = []
    if any(k in q for k in ["scope", "non-goal", "non goal", "范围", "不要改", "不改", "不需要改", "out of scope"]):
        prefer = ["scope"]
    elif any(k in q for k in ["verify", "verification", "test", "acceptance", "criteria", "验收", "验收标准", "验证", "测试", "怎么确认", "如何确认"]):
        prefer = ["verification"]
    elif any(k in q for k in ["rollback", "risk", "risks", "回滚", "风险"]):
        prefer = ["risks"]
    elif any(
        k in q
        for k in [
            "requirement",
            "requirements",
            "constraint",
            "constraints",
            "assumption",
            "assumptions",
            "需求",
            "约束",
            "前提",
            "限制",
            "成功标准",
        ]
    ):
        # For Design/Feature tasks, \"Evidence / Logs\" often contains requirements/constraints.
        prefer = ["evidence", "scope"]
    elif any(
        k in q
        for k in [
            "trade-off",
            "tradeoff",
            "trade-offs",
            "pros and cons",
            "rationale",
            "why choose",
            "why this",
            "优缺点",
            "利弊",
            "取舍",
            "权衡",
            "为什么选",
            "为何选",
        ]
    ):
        # For Design/Feature tasks, \"Root Cause\" is the architecture thesis / decision rationale.
        prefer = ["root_cause", "risks"]
    elif any(
        k in q
        for k in [
            "architecture",
            "design",
            "system design",
            "ui",
            "ux",
            "interaction",
            "frontend",
            "front-end",
            "roadmap",
            "milestone",
            "module",
            "modules",
            "interface",
            "interfaces",
            "api",
            "data flow",
            "state machine",
            "架构",
            "设计",
            "系统设计",
            "界面",
            "交互",
            "前端",
            "动效",
            "动画",
            "样式",
            "布局",
            "组件",
            "实现路径",
            "路线图",
            "里程碑",
            "模块",
            "接口",
            "数据流",
            "状态机",
        ]
    ):
        # Prefer the actionable roadmap for design/feature questions to reduce excerpt noise.
        prefer = ["fix_plan"]
    elif any(k in q for k in ["plan", "fix", "recommendation", "steps", "怎么修", "如何修", "修复", "方案", "计划"]):
        prefer = ["fix_plan"]
    elif any(k in q for k in ["evidence", "log", "logs", "trace", "stack", "日志", "证据", "报错", "堆栈"]):
        prefer = ["evidence"]
    elif any(k in q for k in ["not effective", "doesn't work", "fallback", "alternative", "无效", "不生效", "替代", "下一步"]):
        prefer = ["if_not_effective"]
    else:
        # Default: most users ask about the core conclusion.
        prefer = ["root_cause", "fix_plan", "verification"]

    chunks: list[str] = []
    for key in prefer:
        value = getattr(parsed, key, "")
        if value:
            title = key.replace("_", " ").title()
            chunks.append(f"## {title}\n{value}".strip())

    if not chunks:
        # If parsed but empty (unexpected), fall back to an empty excerpt.
        return ""

    combined = "\n\n".join(chunks).strip()
    excerpt = combined if len(combined) <= max_chars else combined[:max_chars].rstrip() + "\n\n…"
    return sanitize_for_cursor_display(excerpt)


# Available Ternion models
TERNION_MODELS = [
    ModelInfo(id="ternion-team", owned_by="ternion"),
    # ModelInfo(id="ternion-quick", owned_by="ternion"),  # Coming Soon
]

# Message router instance
message_router = MessageRouter()


async def _run_discussion_streaming(
    context: "TernionContext",
    model: str,
    budget_warning: str | None,
    show_thinking_logs: bool,
) -> StreamingResponse:
    """
    Run the Ternion discussion workflow with real-time streaming output.

    This function creates a StreamEventQueue, passes it to the workflow,
    and returns an SSE response that forwards LLM tokens in real-time.

    Args:
        context: The extracted context from the Cursor request
        model: Model name for SSE response
        budget_warning: Optional budget warning to prepend
        show_thinking_logs: Whether to include thinking logs in output

    Returns:
        StreamingResponse with real-time SSE events
    """
    import asyncio
    from collections.abc import AsyncGenerator

    from ternion.workflow.graph import run_discussion
    from ternion.workflow.streaming_events import StreamEventQueue, StreamEventType

    # Create event queue for streaming
    stream_queue = StreamEventQueue()

    # Inject queue into context so workflow can access it
    context._stream_queue = stream_queue  # type: ignore[attr-defined]

    async def generate_sse() -> AsyncGenerator[str, None]:
        """SSE generator that consumes events from the queue."""
        import time
        import uuid

        from ternion.core.models import ChatCompletionChunk, ChoiceDelta, StreamChoice

        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
        final_state: dict = {}

        # Start workflow in background task
        async def run_workflow() -> None:
            nonlocal final_state
            try:
                final_state = await run_discussion(context)
            except Exception as e:
                logger.exception("streaming_workflow_error", error=str(e))
                await stream_queue.put_error(str(e))
            finally:
                stream_queue.close()

        # Launch workflow task
        workflow_task = asyncio.create_task(run_workflow())

        # Send budget warning first if present
        if budget_warning:
            from ternion.core.budget import budget_manager
            warning_text = budget_manager.format_budget_warning(budget_warning)
            chunk = ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=model,
                choices=[StreamChoice(delta=ChoiceDelta(content=warning_text))],
            )
            yield f"data: {chunk.model_dump_json()}\n\n"

        # Variables for final output assembly
        streamed_content = ""
        current_phase = ""

        try:
            # Consume events from queue
            async for event in stream_queue:
                if event.event_type == StreamEventType.TOKEN_DELTA:
                    # Forward token delta as SSE chunk
                    if event.delta:
                        streamed_content += event.delta
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=event.delta))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

                elif event.event_type == StreamEventType.PHASE_START:
                    current_phase = event.phase
                    # Optionally emit phase start indicator
                    if show_thinking_logs and event.phase:
                        indicator = _phase_start_indicator_text(event.phase)
                        if indicator:
                            chunk = ChatCompletionChunk(
                                id=chunk_id,
                                created=created,
                                model=model,
                                choices=[StreamChoice(delta=ChoiceDelta(content="\n" + indicator))],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"

                elif event.event_type == StreamEventType.ERROR:
                    # Forward error
                    error_text = f"\n\n[Ternion Error] {event.content}\n"
                    chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[StreamChoice(delta=ChoiceDelta(content=error_text))],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"

            # Wait for workflow to complete
            await workflow_task

            pending_tool_calls = final_state.get("pending_tool_calls") or []
            if pending_tool_calls:
                cursor_prompt = context.cursor_system_prompt.content if (
                    context.cursor_system_prompt and isinstance(context.cursor_system_prompt.content, str)
                ) else ""
                workflow_phase = str(final_state.get("current_phase") or "execution")
                session = session_store.create_session(
                    ternion_report=final_state.get("ternion_report", "") or "",
                    execution_mode=ExecutionMode.TERNION_FULL,
                    stage=SessionStage.AWAITING_TOOL_RESULTS,
                    cursor_system_prompt=cursor_prompt,
                    cursor_tools=list(getattr(context, "cursor_tools", []) or []),
                    cursor_tool_choice=getattr(context, "cursor_tool_choice", None),
                    execution_messages=list(final_state.get("conversation_history", []) or []),
                    workflow_phase=workflow_phase,
                )
                filtered_tool_calls = list(pending_tool_calls or [])
                todo_written_now = False
                if workflow_phase == "optimizer":
                    filtered_tool_calls, todo_written_now = _filter_optimizer_todo_write(
                        session,
                        filtered_tool_calls,
                    )
                baseline, modified_files = _ensure_baseline_snapshots_for_tool_calls(
                    session,
                    filtered_tool_calls,
                )
                rewritten_tool_calls = _rewrite_tool_call_ids(
                    filtered_tool_calls,
                    session_id=session.session_id,
                    round_index=1,
                )
                execution_messages = list(session.execution_messages or [])
                execution_messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": rewritten_tool_calls,
                })
                session_store.update_session(
                    session.session_id,
                    execution_messages=execution_messages,
                    pending_tool_calls=rewritten_tool_calls,
                    round_index=1,
                    workflow_phase=workflow_phase,
                    modified_files=modified_files,
                    baseline_file_snapshots=baseline,
                    optimizer_todo_written=(
                        True if todo_written_now else getattr(session, "optimizer_todo_written", False)
                    ),
                    optimizer_phase_announced=True if workflow_phase == "optimizer" else False,
                )

                tool_chunk = ChatCompletionChunk(
                    id=chunk_id,
                    created=created,
                    model=model,
                    choices=[
                        StreamChoice(
                            delta=ChoiceDelta(
                                role="assistant",
                                content=None,
                                tool_calls=rewritten_tool_calls,
                            ),
                        )
                    ],
                )
                yield f"data: {tool_chunk.model_dump_json()}\n\n"

                final_chunk = ChatCompletionChunk(
                    id=chunk_id,
                    created=created,
                    model=model,
                    choices=[StreamChoice(delta=ChoiceDelta(), finish_reason="tool_calls")],
                )
                yield f"data: {final_chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
                return

            # If workflow produced final_output but we didn't stream it
            # (e.g., non-streamable phases), send it now
            workflow_final = final_state.get("final_output", "") or final_state.get("generated_code", "")
            if workflow_final and not streamed_content:
                # Workflow produced output but streaming wasn't used
                # (e.g., divergence phase doesn't stream)
                # Send the complete output
                for i in range(0, len(workflow_final), 128):
                    text = workflow_final[i:i + 128]
                    chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"

            # Emit thinking logs to observability
            thinking_logs = final_state.get("thinking_logs", [])
            if thinking_logs:
                _emit_thinking_logs_to_observability(
                    thinking_logs,
                    session_id=final_state.get("session_id") or None,
                    context="streaming_discussion_output",
                    suppressed_from_chat=True,  # Already streamed
                )

            # Send final chunk
            final_chunk = ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=model,
                choices=[StreamChoice(delta=ChoiceDelta(), finish_reason="stop")],
            )
            yield f"data: {final_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception("sse_generation_error", error=str(e))
            error_chunk = ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=model,
                choices=[StreamChoice(delta=ChoiceDelta(content=f"\n[Stream Error] {str(e)}"))],
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
    )


async def _run_implementation_streaming(
    initial_state: dict,
    model: str,
    session_id: str,
    budget_prefix: str,
    show_thinking_logs: bool,
) -> StreamingResponse:
    """
    Run the implementation stage (Writer + Reviewer) with real-time streaming.

    This function creates a StreamEventQueue, passes it to the implementation stage,
    and returns an SSE response that forwards LLM tokens in real-time.

    Args:
        initial_state: Initial state dict with ternion_report, conversation_history, etc.
        model: Model name for SSE response
        session_id: Session ID for tracking
        budget_prefix: Optional budget warning to prepend
        show_thinking_logs: Whether to include thinking logs

    Returns:
        StreamingResponse with real-time SSE events
    """
    import asyncio
    from collections.abc import AsyncGenerator

    from ternion.workflow.implementation_stage import run_implementation_stage
    from ternion.workflow.streaming_events import StreamEventQueue, StreamEventType

    # Create event queue for streaming
    stream_queue = StreamEventQueue()

    # Inject queue into state so nodes can access it
    initial_state["_stream_queue"] = stream_queue

    async def generate_sse() -> AsyncGenerator[str, None]:
        """SSE generator that consumes events from the queue."""
        import time
        import uuid

        from ternion.core.models import ChatCompletionChunk, ChoiceDelta, StreamChoice

        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
        final_state: dict = {}

        # Start implementation stage in background task
        async def run_impl() -> None:
            nonlocal final_state
            try:
                final_state = await run_implementation_stage(initial_state)
            except Exception as e:
                logger.exception("streaming_implementation_error", error=str(e))
                await stream_queue.put_error(str(e))
            finally:
                stream_queue.close()

        # Launch implementation task
        impl_task = asyncio.create_task(run_impl())

        # Send budget prefix first if present
        if budget_prefix:
            chunk = ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=model,
                choices=[StreamChoice(delta=ChoiceDelta(content=budget_prefix))],
            )
            yield f"data: {chunk.model_dump_json()}\n\n"

        streamed_content = ""

        try:
            # Consume events from queue
            async for event in stream_queue:
                if event.event_type == StreamEventType.TOKEN_DELTA:
                    if event.delta:
                        streamed_content += event.delta
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=event.delta))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

                elif event.event_type == StreamEventType.PHASE_START:
                    if show_thinking_logs and event.phase:
                        indicator = _phase_start_indicator_text(event.phase)
                        if indicator:
                            chunk = ChatCompletionChunk(
                                id=chunk_id,
                                created=created,
                                model=model,
                                choices=[StreamChoice(delta=ChoiceDelta(content="\n" + indicator))],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"

                elif event.event_type == StreamEventType.ERROR:
                    error_text = f"\n\n[Ternion Error] {event.content}\n"
                    chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[StreamChoice(delta=ChoiceDelta(content=error_text))],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"

            # Wait for implementation to complete
            await impl_task

            # If no content was streamed but workflow produced output, send it
            workflow_final = final_state.get("final_output", "") or final_state.get("generated_code", "")
            if workflow_final and not streamed_content:
                for i in range(0, len(workflow_final), 128):
                    text = workflow_final[i:i + 128]
                    chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"

            # Update session status
            session_store.update_session(session_id, stage=SessionStage.EXECUTED)

            # Log completion
            thinking_logs = final_state.get("thinking_logs", [])
            if thinking_logs:
                _emit_thinking_logs_to_observability(
                    thinking_logs,
                    session_id=session_id,
                    context="streaming_implementation_output",
                    suppressed_from_chat=True,
                )

            # Send final chunk
            final_chunk = ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=model,
                choices=[StreamChoice(delta=ChoiceDelta(), finish_reason="stop")],
            )
            yield f"data: {final_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception("sse_impl_generation_error", error=str(e))
            error_chunk = ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=model,
                choices=[StreamChoice(delta=ChoiceDelta(content=f"\n[Stream Error] {str(e)}"))],
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
    )


# Import for type hints
from ternion.router.context import TernionContext


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@router.get("/", include_in_schema=False)
async def root_probe(request: Request) -> dict[str, str]:
    """
    Base URL probe endpoint (no /v1 prefix).

    Some clients validate connectivity by probing the base origin before calling
    API paths. Returning 200 helps distinguish "no request sent" vs "wrong path".
    """
    logger.info(
        "api_probe",
        path=str(request.url.path),
        method=request.method,
        user_agent=request.headers.get("user-agent", ""),
    )
    return {"status": "ok"}


@router.head("/", include_in_schema=False)
async def root_probe_head(request: Request) -> Response:
    """HEAD variant of `/` for strict clients."""
    logger.info(
        "api_probe",
        path=str(request.url.path),
        method=request.method,
        user_agent=request.headers.get("user-agent", ""),
    )
    return Response(status_code=200)


@router.get("/v1", include_in_schema=False)
async def v1_root(request: Request) -> dict[str, str]:
    """
    OpenAI-compatible base URL probe endpoint.

    Cursor (certain versions) may issue a GET/HEAD to the configured base URL
    (often ending with `/v1`) before calling `/v1/models` or `/v1/chat/completions`.
    """
    logger.info(
        "api_probe",
        path=str(request.url.path),
        method=request.method,
        user_agent=request.headers.get("user-agent", ""),
    )
    return {"status": "ok"}


@router.head("/v1", include_in_schema=False)
async def v1_root_head(request: Request) -> Response:
    """HEAD variant of `/v1` for strict clients."""
    logger.info(
        "api_probe",
        path=str(request.url.path),
        method=request.method,
        user_agent=request.headers.get("user-agent", ""),
    )
    return Response(status_code=200)


@router.get("/v1/", include_in_schema=False)
async def v1_root_slash(request: Request) -> dict[str, str]:
    """Same as `/v1` but avoids redirect_slashes for strict clients."""
    logger.info(
        "api_probe",
        path=str(request.url.path),
        method=request.method,
        user_agent=request.headers.get("user-agent", ""),
    )
    return {"status": "ok"}


@router.head("/v1/", include_in_schema=False)
async def v1_root_slash_head(request: Request) -> Response:
    """HEAD variant of `/v1/` for strict clients."""
    logger.info(
        "api_probe",
        path=str(request.url.path),
        method=request.method,
        user_agent=request.headers.get("user-agent", ""),
    )
    return Response(status_code=200)


@router.get("/models")
@router.get("/v1/models")
async def list_models(request: Request) -> ModelsListResponse:
    """List available models (OpenAI-compatible)."""
    logger.info(
        "models_list_request",
        path=str(request.url.path),
        method=request.method,
        user_agent=request.headers.get("user-agent", ""),
    )
    # Intentionally expose only Ternion models.
    #
    # Rationale: When users enable "Override OpenAI Base URL" in Cursor to point at Ternion,
    # exposing passthrough provider models (gpt/claude/gemini) can cause accidental BYOK
    # usage and unexpected extra costs.
    return ModelsListResponse(data=list(TERNION_MODELS))


@router.head("/models", include_in_schema=False)
@router.head("/v1/models", include_in_schema=False)
async def list_models_head(request: Request) -> Response:
    """HEAD variant of `/v1/models` for strict clients."""
    logger.info(
        "models_list_request",
        path=str(request.url.path),
        method=request.method,
        user_agent=request.headers.get("user-agent", ""),
    )
    return Response(status_code=200)


@router.post("/responses", response_model=None)
@router.post("/v1/responses", response_model=None)
@router.post("/chat/completions", response_model=None)
@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
) -> Response:
    """
    Handle chat completion requests (OpenAI-compatible).

    Routes requests based on the model name:
    - ternion-team: Full 4-step discussion flow
    - (All other models are rejected to avoid accidental passthrough/BYOK costs)
    """
    logger.info(
        "chat_completion_request",
        model=request.model,
        message_count=len(request.messages),
        stream=request.stream,
    )

    # Development-only: capture incoming Cursor requests (including system prompt) for debugging.
    # This is disabled by default and runs in the background when enabled.
    schedule_cursor_request_capture(request)

    model = request.model.lower()

    # Default mode: this gateway only serves the Ternion model.
    # Any other model name is rejected with an explicit Cursor guidance message.
    if model != "ternion-team":
        message = t(MessageKey.UNSUPPORTED_MODEL, model=request.model)
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": message,
                    "type": "model_not_supported",
                }
            },
        )

    # Convert messages to dict format for parsing and routing.
    #
    # Note: Tool-loop execution follow-ups may only be identifiable via tool_call_id/tool_calls,
    # so we must preserve those fields here.
    messages_as_dicts = []
    for msg in request.messages:
        role = msg.role.value if hasattr(msg.role, "value") else msg.role
        messages_as_dicts.append({
            "role": role,
            "content": msg.content,
            "name": msg.name,
            "tool_calls": msg.tool_calls,
            "tool_call_id": msg.tool_call_id,
        })

    # Check for execution follow-up session first (tool loop).
    execution_session_id = _parse_execution_session_id(messages_as_dicts)
    if execution_session_id:
        session = session_store.load_session(execution_session_id)
        if session and session.stage in (
            SessionStage.EXECUTION_IN_PROGRESS,
            SessionStage.AWAITING_TOOL_RESULTS,
            SessionStage.REVIEW_IN_PROGRESS,
            SessionStage.OPTIMIZER_IN_PROGRESS,
        ):
            return await handle_execution_followup(session, request)

    # Check for existing session in conversation history (Human-in-the-Loop)
    session_id = parse_session_marker(messages_as_dicts)

    if session_id:
        session = session_store.load_session(session_id)
        if session:
            latest_message = get_latest_user_message(messages_as_dicts)

            if session.stage == SessionStage.AWAITING_CONFIRMATION:
                # Verify report hash consistency (optional security check)
                marker_hash = parse_report_hash_marker(messages_as_dicts)
                if marker_hash and session.report_hash and marker_hash != session.report_hash:
                    logger.warning(
                        "report_hash_mismatch",
                        session_id=session_id,
                        marker_hash=marker_hash,
                        stored_hash=session.report_hash,
                    )
                    log_manager.emit(
                        level="WARN",
                        category="SECURITY",
                        message=f"Report hash mismatch | session_id={session_id} | marker_hash={marker_hash[:8]}... | stored_hash={session.report_hash[:8]}...",
                    )
                    # Continue anyway but log the mismatch for monitoring

                # Classify user intent from latest message (heuristic + LLM fallback)
                intent = await classify_intent_with_fallback(latest_message)

                # Compute and persist hash verification result for offline analysis
                hash_verified = marker_hash == session.report_hash if marker_hash else None
                if hash_verified is not None:
                    session_store.update_session(session_id, hash_verified=hash_verified)

                logger.info(
                    "session_followup",
                    session_id=session_id,
                    stage=session.stage.value,
                    intent=intent.value,
                    message_preview=latest_message[:50],
                    hash_verified=hash_verified,
                )
                hash_status = f"hash_verified={hash_verified}" if hash_verified is not None else "hash_not_checked"
                log_manager.emit(
                    level="INFO",
                    category="SESSION",
                    message=f"Session follow-up | session_id={session_id} | stage={session.stage.value} | intent={intent.value} | {hash_status}",
                )

                return await handle_session_followup(session, intent, latest_message, request)

            elif session.stage in (SessionStage.CONFIRMED, SessionStage.EXECUTED):
                # Session already confirmed/executed - handle post-execution follow-up
                logger.info(
                    "session_post_execution",
                    session_id=session_id,
                    stage=session.stage.value,
                    execution_mode=session.execution_mode.value,
                )
                log_manager.emit(
                    level="INFO",
                    category="SESSION",
                    message=f"Post-execution follow-up | session_id={session_id} | stage={session.stage.value} | mode={session.execution_mode.value}",
                )

                return await handle_post_execution_followup(session, latest_message, request)

            elif session.stage == SessionStage.REJECTED:
                # Session was rejected - provide clear guidance
                logger.info(
                    "session_rejected_followup",
                    session_id=session_id,
                    has_feedback=bool(session.last_user_feedback),
                )
                log_manager.emit(
                    level="INFO",
                    category="SESSION",
                    message=f"Rejected session follow-up | session_id={session_id} | has_feedback={bool(session.last_user_feedback)}",
                )

                return await handle_rejected_session_followup(session, latest_message, request)

        else:
            # Session marker found but session not loadable (e.g. corrupted/deleted)
            logger.warning(
                "session_unavailable",
                session_id=session_id,
                reason="not_found_or_corrupted",
            )
            log_manager.emit(
                level="WARN",
                category="SESSION",
                message=f"Session unavailable (not found or corrupted) | session_id={session_id} | Starting new analysis",
            )
            # Fall through to create a new RCA session
            # The warning in the Logs panel provides observability

    # Extract context using MessageRouter
    context = message_router.extract_context(request.messages)
    context.cursor_tools = list(request.tools or [])
    context.cursor_tool_choice = request.tool_choice

    # Set session management flags from user config
    user_config = config_store.load()
    is_agent_request = _is_cursor_agent_request(request)

    context.execution_mode = user_config.execution_mode
    # Default: require confirmation unless this is an Agent request in ternion_full.
    context.await_confirmation = user_config.execution_mode != "ternion_full"
    if not is_agent_request:
        # Non-agent modes (Ask/Plan/Debug): always stop after generating the report.
        context.await_confirmation = True

    # Cursor Agent compatibility: When users configured CURSOR_HANDOFF but run Cursor in Agent mode,
    # Cursor cannot automatically switch away from `ternion-team` to a native model for implementation.
    #
    # To avoid "report-only stall" in Agent mode, automatically promote the execution mode to
    # TERNION_FULL and skip the confirmation gate for this request. Also persist the mode switch
    # so the Web UI reflects the new mode.
    if is_agent_request and user_config.execution_mode == "cursor_handoff":
        log_manager.emit(
            level="INFO",
            category="USER_ACTION",
            message=(
                "Cursor Agent mode detected | auto-switch execution_mode: cursor_handoff -> ternion_full "
                "(confirmation gate disabled for this request)"
            ),
        )
        user_config.execution_mode = "ternion_full"
        config_store.save(user_config)
        context.execution_mode = "ternion_full"
        context.await_confirmation = False

    # Require execution mode to be explicitly configured and saved
    if user_config.execution_mode not in ("cursor_handoff", "ternion_full"):
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "message": t(MessageKey.EXECUTION_MODE_MISSING),
                    "type": "configuration_error",
                }
            },
        )

    logger.debug(
        "context_extracted",
        has_system_prompt=context.cursor_system_prompt is not None,
        history_length=len(context.conversation_history),
        execution_mode=context.execution_mode,
    )

    # Check if providers are available
    if not provider_manager.has_providers:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "message": t(MessageKey.NO_PROVIDERS_CONFIGURED),
                    "type": "configuration_error",
                }
            },
        )

    # Check role configuration completeness (depends on execution mode)
    missing_roles = []
    required_roles = ["ternion_a", "ternion_b", "ternion_c", "arbiter"]
    requires_implementation_roles = is_agent_request and context.execution_mode == "ternion_full"
    if requires_implementation_roles:
        required_roles += ["writer", "reviewer"]
    role_names = {
        "ternion_a": "Ternion A",
        "ternion_b": "Ternion B",
        "ternion_c": "Ternion C",
        "arbiter": "Arbiter",
        "writer": "Writer",
        "reviewer": "Reviewer",
    }

    for role in required_roles:
        display_name = role_names.get(role, role)
        role_config = user_config.roles.get(role)
        if not role_config:
            missing_roles.append(display_name)
            continue
        # Check if provider and model are explicitly configured (must be non-empty)
        if not role_config.provider or not role_config.model:
            missing_roles.append(f"{display_name} (provider/model not selected)")
            continue
        # Check if the provider for this role is enabled
        provider_config = user_config.providers.get(role_config.provider)
        if not provider_config or not provider_config.api_keys or not provider_config.selected_key_id:
            missing_roles.append(f"{display_name} ({role_config.provider} not configured)")

    if missing_roles:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "message": t(MessageKey.ROLE_CONFIG_INCOMPLETE, missing_roles=', '.join(missing_roles)),
                    "type": "configuration_error",
                }
            },
        )

    # Check budget before proceeding
    budget_ok, budget_warning = budget_manager.check_budget()
    if not budget_ok:
        log_manager.emit(
            level="WARN",
            category="BUDGET",
            message=t(MessageKey.LOG_BUDGET_EXCEEDED),
        )
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "message": t(MessageKey.BUDGET_EXCEEDED_ERROR),
                    "type": "budget_exceeded",
                }
            },
        )

    if budget_warning == "BUDGET_WARNING":
        usage_summary = budget_manager.get_usage_summary()
        log_manager.emit(
            level="WARN",
            category="BUDGET",
            message=t(MessageKey.LOG_BUDGET_WARNING, usage_pct=str(usage_summary.get('usage_pct', 0))),
        )

    # Run the Ternion discussion workflow
    try:
        from ternion.workflow.graph import run_discussion

        if request.stream:
            return await _run_discussion_streaming(
                context=context,
                model=request.model,
                budget_warning=budget_warning,
                show_thinking_logs=user_config.show_thinking_logs,
            )

        # Non-streaming: run workflow and return complete response
        final_state = await run_discussion(context)
        pending_tool_calls = final_state.get("pending_tool_calls") or []
        if pending_tool_calls:
            cursor_prompt = context.cursor_system_prompt.content if (
                context.cursor_system_prompt and isinstance(context.cursor_system_prompt.content, str)
            ) else ""
            workflow_phase = str(final_state.get("current_phase") or "execution")
            session = session_store.create_session(
                ternion_report=final_state.get("ternion_report", "") or "",
                execution_mode=ExecutionMode.TERNION_FULL,
                stage=SessionStage.AWAITING_TOOL_RESULTS,
                cursor_system_prompt=cursor_prompt,
                cursor_tools=list(request.tools or []),
                cursor_tool_choice=request.tool_choice,
                execution_messages=list(final_state.get("conversation_history", []) or []),
                workflow_phase=workflow_phase,
            )
            filtered_tool_calls = list(pending_tool_calls or [])
            todo_written_now = False
            announce_text: str | None = None
            if workflow_phase == "optimizer":
                filtered_tool_calls, todo_written_now = _filter_optimizer_todo_write(
                    session,
                    filtered_tool_calls,
                )
                announce_text = "\n" + t(MessageKey.OPTIMIZER_START)
            baseline, modified_files = _ensure_baseline_snapshots_for_tool_calls(
                session,
                filtered_tool_calls,
            )
            rewritten_tool_calls = _rewrite_tool_call_ids(
                filtered_tool_calls,
                session_id=session.session_id,
                round_index=1,
            )
            execution_messages = list(session.execution_messages or [])
            execution_messages.append({
                "role": "assistant",
                "content": announce_text,
                "tool_calls": rewritten_tool_calls,
            })
            session_store.update_session(
                session.session_id,
                execution_messages=execution_messages,
                pending_tool_calls=rewritten_tool_calls,
                round_index=1,
                workflow_phase=workflow_phase,
                modified_files=modified_files,
                baseline_file_snapshots=baseline,
                optimizer_todo_written=bool(getattr(session, "optimizer_todo_written", False)) or todo_written_now,
                optimizer_phase_announced=True if workflow_phase == "optimizer" else False,
            )
            return JSONResponse(
                content=ChatCompletionResponse(
                    model=request.model,
                    choices=[
                        Choice(
                            finish_reason="tool_calls",
                            message=ChatMessage(
                                role=MessageRole.ASSISTANT,
                                content=announce_text,
                                tool_calls=rewritten_tool_calls,
                            ),
                        )
                    ],
                ).model_dump()
            )

        # Build output with thinking logs + final code
        thinking_logs = final_state.get("thinking_logs", [])
        errors = final_state.get("errors", []) or []
        final_code = final_state.get("final_output", "") or final_state.get("generated_code", "")
        is_patch_output = _is_patch_or_diff_output(final_code)
        _emit_thinking_logs_to_observability(
            thinking_logs,
            session_id=final_state.get("session_id") or None,
            context="discussion_output",
            suppressed_from_chat=is_patch_output,
        )

        # Combine thinking stream with final output
        output_parts = []

        if budget_warning:
            output_parts.append(budget_manager.format_budget_warning(budget_warning))

        # Add thinking logs for report/gate stage only (avoid prefixing patch/diff output)
        if thinking_logs and user_config.show_thinking_logs and not is_patch_output:
            output_parts.append("".join(thinking_logs))
            output_parts.append("\n---\n\n")  # Separator

        # Add final output
        if final_code:
            output_parts.append(final_code)
        else:
            output_parts.append("[Ternion] Discussion completed but no output was generated.")
            if errors:
                output_parts.append("\n\n[Ternion] Errors:\n")
                for err in errors:
                    msg = sanitize_for_cursor_display(str(err))
                    if msg:
                        output_parts.append(f"- {msg}\n")

        output = "".join(output_parts)

        return JSONResponse(
                content=ChatCompletionResponse(
                    model=request.model,
                    choices=[
                        Choice(
                            message=ChatMessage(
                                role=MessageRole.ASSISTANT,
                                content=output,
                            )
                        )
                    ],
                ).model_dump()
            )
    except Exception as e:
        logger.exception("discussion_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": f"Discussion workflow error: {str(e)}",
                    "type": "workflow_error",
                }
            },
        )


async def handle_execution_followup(
    session: Session,
    request: ChatCompletionRequest,
    *,
    skip_budget_confirm: bool = False,
) -> Response:
    """
    Handle execution-stage follow-ups for Cursor Agent tool loops.

    This branch is identified via tool_call_id, not via plain-text session markers.
    """
    from ternion.workflow.implementation_stage import run_implementation_stage
    from ternion.utils.tool_result_compaction import compact_tool_result

    # Refresh tool definitions on every request if present.
    cursor_tools = list(request.tools or []) or list(session.cursor_tools or [])
    cursor_tool_choice = request.tool_choice if request.tool_choice is not None else session.cursor_tool_choice

    context = message_router.extract_context(request.messages)
    cursor_system_prompt = session.cursor_system_prompt
    if context.cursor_system_prompt and isinstance(context.cursor_system_prompt.content, str):
        cursor_system_prompt = context.cursor_system_prompt.content

    # Append new tool results from this request into the persisted execution history.
    pending_by_id = {
        tc.get("id"): tc
        for tc in (session.pending_tool_calls or [])
        if isinstance(tc, dict) and isinstance(tc.get("id"), str)
    }
    existing_tool_ids = {
        m.get("tool_call_id")
        for m in (session.execution_messages or [])
        if isinstance(m, dict) and m.get("role") == "tool" and isinstance(m.get("tool_call_id"), str)
    }
    updated_execution_messages = list(session.execution_messages or [])
    tool_results_raw = dict(getattr(session, "tool_results_raw", {}) or {})
    tool_results_meta = dict(getattr(session, "tool_results_meta", {}) or {})
    for msg in request.messages:
        if msg.role != MessageRole.TOOL:
            continue
        if not isinstance(msg.tool_call_id, str):
            continue
        if msg.tool_call_id in existing_tool_ids:
            continue
        match = _TERNION_TOOL_CALL_ID_SESSION_RE.search(msg.tool_call_id)
        if not match or match.group(1).lower() != session.session_id.lower():
            continue
        raw_content = msg.content if isinstance(msg.content, str) else str(msg.content)
        tool_call = pending_by_id.get(msg.tool_call_id) or {}
        fn = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
        tool_name = fn.get("name") if isinstance(fn.get("name"), str) else None
        tool_args = fn.get("arguments") if isinstance(fn.get("arguments"), str) else None

        compacted_content, meta = compact_tool_result(
            tool_name=tool_name,
            content=raw_content,
            tool_arguments=tool_args,
        )
        meta["source_ref"] = msg.tool_call_id
        tool_results_meta[msg.tool_call_id] = meta
        if meta.get("compacted") is True:
            tool_results_raw[msg.tool_call_id] = raw_content
        updated_execution_messages.append({
            "role": "tool",
            "content": compacted_content,
            "tool_call_id": msg.tool_call_id,
        })
        existing_tool_ids.add(msg.tool_call_id)

    resume_phase = str(getattr(session, "workflow_phase", "") or "execution")
    resume_stage = (
        SessionStage.OPTIMIZER_IN_PROGRESS
        if resume_phase == "optimizer"
        else SessionStage.EXECUTION_IN_PROGRESS
    )
    session_store.update_session(
        session.session_id,
        stage=resume_stage,
        cursor_system_prompt=cursor_system_prompt,
        cursor_tools=list(cursor_tools or []),
        cursor_tool_choice=cursor_tool_choice,
        execution_messages=updated_execution_messages,
        pending_tool_calls=[],
        tool_results_raw=tool_results_raw,
        tool_results_meta=tool_results_meta,
    )

    if not skip_budget_confirm:
        budget_ok, budget_warning = budget_manager.check_budget()
        if not budget_ok:
            log_manager.emit(
                level="WARN",
                category="BUDGET",
                message=t(MessageKey.LOG_BUDGET_EXCEEDED),
            )
            session_store.update_session(
                session.session_id,
                stage=SessionStage.AWAITING_CONFIRMATION,
                confirmation_reason="budget_exceeded",
            )
            return _respond_with_text(request, _budget_exceeded_message(session))
        if budget_warning == "BUDGET_WARNING":
            usage_summary = budget_manager.get_usage_summary()
            log_manager.emit(
                level="WARN",
                category="BUDGET",
                message=t(
                    MessageKey.LOG_BUDGET_CONFIRM_REQUIRED,
                    usage_pct=str(usage_summary.get("usage_pct", 0)),
                ),
            )
            session_store.update_session(
                session.session_id,
                stage=SessionStage.AWAITING_CONFIRMATION,
                confirmation_reason="budget",
            )
            return _respond_with_text(request, _budget_confirmation_message(session))

    initial_state = {
        "cursor_system_prompt": cursor_system_prompt or None,
        "conversation_history": updated_execution_messages,
        "ternion_report": session.ternion_report_raw,
        "session_id": session.session_id,
        "execution_mode": session.execution_mode.value,
        "current_phase": getattr(session, "workflow_phase", "execution") or "execution",
        "thinking_logs": [],
        "errors": [],
        "generated_code": session.generated_code,
        "review_feedback": session.review_feedback,
        "revision_count": session.revision_count,
        "baseline_file_snapshots": dict(getattr(session, "baseline_file_snapshots", {}) or {}),
        "modified_files": list(getattr(session, "modified_files", []) or []),
        "writer_output_files": dict(getattr(session, "writer_output_files", {}) or {}),
        "optimizer_review_report": str(getattr(session, "optimizer_review_report", "") or ""),
        "cursor_tools": cursor_tools,
        "cursor_tool_choice": cursor_tool_choice,
    }

    final_state = await run_implementation_stage(initial_state)
    pending_tool_calls = final_state.get("pending_tool_calls") or []

    if pending_tool_calls:
        next_round = (session.round_index or 0) + 1
        if next_round > _TOOL_LOOP_MAX_ROUNDS:
            session_store.update_session(
                session.session_id,
                stage=SessionStage.AWAITING_CONFIRMATION,
                confirmation_reason="failsafe",
                pending_tool_calls=[],
            )
            log_manager.emit(
                level="WARN",
                category="GUARDRAIL",
                message=t(
                    MessageKey.LOG_TOOL_LOOP_FAILSAFE_REACHED,
                    max_rounds=str(_TOOL_LOOP_MAX_ROUNDS),
                    session_id=session.session_id,
                ),
            )
            return _respond_with_text(request, _tool_loop_failsafe_message(session))
        workflow_phase = str(final_state.get("current_phase") or getattr(session, "workflow_phase", "execution") or "execution")
        filtered_tool_calls = list(pending_tool_calls or [])
        todo_written_now = False
        announce_now = False
        announce_text: str | None = None
        if workflow_phase == "optimizer":
            filtered_tool_calls, todo_written_now = _filter_optimizer_todo_write(
                session,
                filtered_tool_calls,
            )
            announce_now = not bool(getattr(session, "optimizer_phase_announced", False))
            if announce_now:
                announce_text = "\n" + t(MessageKey.OPTIMIZER_START)

        baseline, modified_files = _ensure_baseline_snapshots_for_tool_calls(
            session,
            filtered_tool_calls,
        )
        rewritten_tool_calls = _rewrite_tool_call_ids(
            filtered_tool_calls,
            session_id=session.session_id,
            round_index=next_round,
        )
        updated_execution_messages.append({
            "role": "assistant",
            "content": announce_text,
            "tool_calls": rewritten_tool_calls,
        })
        session_store.update_session(
            session.session_id,
            stage=SessionStage.AWAITING_TOOL_RESULTS,
            execution_messages=updated_execution_messages,
            pending_tool_calls=rewritten_tool_calls,
            round_index=next_round,
            generated_code=final_state.get("generated_code") or session.generated_code,
            review_feedback=final_state.get("review_feedback") or session.review_feedback,
            revision_count=final_state.get("revision_count", session.revision_count),
            workflow_phase=workflow_phase,
            modified_files=modified_files,
            baseline_file_snapshots=baseline,
            writer_output_files=dict(final_state.get("writer_output_files") or getattr(session, "writer_output_files", {}) or {}),
            optimizer_review_report=str(final_state.get("optimizer_review_report") or getattr(session, "optimizer_review_report", "") or ""),
            optimizer_todo_written=bool(getattr(session, "optimizer_todo_written", False)) or todo_written_now,
            optimizer_phase_announced=bool(getattr(session, "optimizer_phase_announced", False)) or announce_now,
        )

        if request.stream:
            return StreamingResponse(
                create_sse_tool_calls_stream(
                    model=request.model,
                    tool_calls=rewritten_tool_calls,
                    content=announce_text,
                ),
                media_type="text/event-stream",
            )
        return JSONResponse(
            content=ChatCompletionResponse(
                model=request.model,
                choices=[
                    Choice(
                        finish_reason="tool_calls",
                        message=ChatMessage(
                            role=MessageRole.ASSISTANT,
                            content=announce_text,
                            tool_calls=rewritten_tool_calls,
                        ),
                    )
                ],
            ).model_dump()
        )

    final_output = final_state.get("final_output", "") or final_state.get("generated_code", "")
    errors = final_state.get("errors", []) or []
    optimizer_ran = bool(final_state.get("optimizer_review_report") or getattr(session, "workflow_phase", "") == "optimizer")
    announce_now = optimizer_ran and not bool(getattr(session, "optimizer_phase_announced", False))
    if announce_now and final_output:
        final_output = "\n" + t(MessageKey.OPTIMIZER_START) + final_output
    new_stage = SessionStage.EXECUTED if not errors else SessionStage.EXECUTION_IN_PROGRESS
    session_store.update_session(
        session.session_id,
        stage=new_stage,
        pending_tool_calls=[],
        generated_code=final_state.get("generated_code") or session.generated_code,
        review_feedback=final_state.get("review_feedback") or session.review_feedback,
        revision_count=final_state.get("revision_count", session.revision_count),
        workflow_phase=str(final_state.get("current_phase") or getattr(session, "workflow_phase", "execution") or "execution"),
        modified_files=list(final_state.get("modified_files") or getattr(session, "modified_files", []) or []),
        baseline_file_snapshots=dict(final_state.get("baseline_file_snapshots") or getattr(session, "baseline_file_snapshots", {}) or {}),
        writer_output_files=dict(final_state.get("writer_output_files") or getattr(session, "writer_output_files", {}) or {}),
        optimizer_review_report=str(final_state.get("optimizer_review_report") or getattr(session, "optimizer_review_report", "") or ""),
        optimizer_phase_announced=bool(getattr(session, "optimizer_phase_announced", False)) or announce_now,
    )

    if request.stream:
        return StreamingResponse(
            create_sse_stream(model=request.model, content=final_output),
            media_type="text/event-stream",
        )
    return JSONResponse(
        content=ChatCompletionResponse(
            model=request.model,
            choices=[
                Choice(
                    message=ChatMessage(
                        role=MessageRole.ASSISTANT,
                        content=final_output,
                    )
                )
            ],
        ).model_dump()
    )


async def handle_session_followup(
    session: Session,
    intent: Intent,
    user_message: str,
    request: ChatCompletionRequest,
) -> Response:
    """
    Handle follow-up to an existing session based on user intent.

    Routes to appropriate handler based on classified intent:
    - CONFIRM: Proceed with execution or handoff
    - REJECT: Re-run analysis with rejection context
    - CLARIFY: Treat as rejection with clarification request
    - UNKNOWN: Ask user to clarify their intent

    Args:
        session: The existing session
        intent: Classified user intent
        user_message: The user's response message
        request: Original chat completion request

    Returns:
        Response appropriate for the intent
    """
    if session.confirmation_reason:
        return await handle_guardrail_confirmation(session, intent, request)
    if intent == Intent.CONFIRM:
        return await handle_confirmed_session(session, request)
    elif intent == Intent.REJECT:
        return await handle_rejected_session(session, user_message, request)
    elif intent == Intent.CLARIFY:
        # Answer question using existing report without re-running RCA
        return await handle_clarify_request(session, user_message, request)
    else:  # UNKNOWN
        return await handle_unknown_intent(session, request)


async def handle_guardrail_confirmation(
    session: Session,
    intent: Intent,
    request: ChatCompletionRequest,
) -> Response:
    """
    Handle guardrail confirmations for tool-loop budget and failsafe checks.
    """
    reason = session.confirmation_reason or ""
    if reason == "budget":
        if intent == Intent.CONFIRM:
            resume_stage = (
                SessionStage.OPTIMIZER_IN_PROGRESS
                if session.workflow_phase == "optimizer"
                else SessionStage.EXECUTION_IN_PROGRESS
            )
            session_store.update_session(
                session.session_id,
                stage=resume_stage,
                confirmation_reason=None,
            )
            session.confirmation_reason = None
            return await handle_execution_followup(
                session,
                request,
                skip_budget_confirm=True,
            )
        return _respond_with_text(request, _budget_confirmation_message(session))
    if reason == "budget_exceeded":
        return _respond_with_text(request, _budget_exceeded_message(session))
    if reason == "failsafe":
        return _respond_with_text(request, _tool_loop_failsafe_message(session))
    return _respond_with_text(request, _budget_confirmation_message(session))


async def handle_confirmed_session(
    session: Session,
    request: ChatCompletionRequest,
) -> Response:
    """
    Handle user confirmation of the analysis report.

    Updates session state and either:
    - TERNION_FULL: Continues workflow to Writer + Reviewer
    - CURSOR_HANDOFF: Returns a handoff package

    Args:
        session: The confirmed session
        request: Original chat completion request

    Returns:
        Generated code or handoff package
    """
    is_agent_request = _is_cursor_agent_request(request)
    if session.execution_mode == ExecutionMode.TERNION_FULL and not is_agent_request:
        message = t(MessageKey.EXECUTION_REQUIRES_AGENT_MODE)
        log_manager.emit(
            level="INFO",
            category="USER_ACTION",
            message=(
                "Execution requires Cursor Agent mode | "
                f"session_id={session.session_id} | mode={session.execution_mode.value}"
            ),
        )
        if request.stream:
            return StreamingResponse(
                create_sse_stream(model=request.model, content=message),
                media_type="text/event-stream",
            )
        return JSONResponse(
            content=ChatCompletionResponse(
                model=request.model,
                choices=[
                    Choice(
                        message=ChatMessage(
                            role=MessageRole.ASSISTANT,
                            content=message,
                        )
                    )
                ],
            ).model_dump()
        )

    session_store.update_session(session.session_id, stage=SessionStage.CONFIRMED)

    if session.execution_mode == ExecutionMode.CURSOR_HANDOFF:
        # Log session confirmation for handoff mode
        logger.info(
            "session_confirmed",
            session_id=session.session_id,
            execution_mode="cursor_handoff",
            action="generating_handoff_package",
        )
        log_manager.emit(
            level="INFO",
            category="USER_ACTION",
            message=f"Session confirmed | session_id={session.session_id} | mode=cursor_handoff | action=generating_handoff_package",
        )

        # Return handoff package (no code generation)
        # Use ternion_report_safe for user-visible output
        handoff_output = generate_handoff_package(session.ternion_report_safe)
        session_store.update_session(session.session_id, stage=SessionStage.EXECUTED)

        if request.stream:
            return StreamingResponse(
                create_sse_stream(model=request.model, content=handoff_output),
                media_type="text/event-stream",
            )
        else:
            return JSONResponse(
                content=ChatCompletionResponse(
                    model=request.model,
                    choices=[
                        Choice(
                            message=ChatMessage(
                                role=MessageRole.ASSISTANT,
                                content=handoff_output,
                            )
                        )
                    ],
                ).model_dump()
            )
    else:
        # TERNION_FULL: Run only Execution + Final Check with the confirmed report
        # This avoids re-running RCA (divergence + convergence) and reuses the validated report
        from ternion.workflow.implementation_stage import run_implementation_stage

        # Load config once at the start of this branch (reuse for all config checks)
        config = config_store.load()

        # Log session confirmation for full execution mode
        logger.info(
            "session_confirmed",
            session_id=session.session_id,
            execution_mode="ternion_full",
            action="starting_implementation_stage",
            show_thinking_logs=config.show_thinking_logs,
        )
        log_manager.emit(
            level="INFO",
            category="USER_ACTION",
            message=f"Session confirmed | session_id={session.session_id} | mode=ternion_full | action=starting_implementation_stage",
        )

        budget_ok, budget_warning = budget_manager.check_budget()
        impl_budget_prefix = ""
        if not budget_ok:
            log_manager.emit(
                level="WARN",
                category="BUDGET",
                message=t(MessageKey.LOG_BUDGET_IMPL_BLOCKED, session_id=session.session_id),
            )
            error_msg = budget_manager.format_budget_warning("BUDGET_EXCEEDED")
            if request.stream:
                return StreamingResponse(
                    create_sse_stream(model=request.model, content=error_msg),
                    media_type="text/event-stream",
                )
            else:
                return JSONResponse(
                    content=ChatCompletionResponse(
                        model=request.model,
                        choices=[Choice(message=ChatMessage(role=MessageRole.ASSISTANT, content=error_msg))],
                    ).model_dump()
                )
        if budget_warning == "BUDGET_WARNING":
            usage_summary = budget_manager.get_usage_summary()
            log_manager.emit(
                level="WARN",
                category="BUDGET",
                message=t(MessageKey.LOG_BUDGET_WARNING, usage_pct=str(usage_summary.get('usage_pct', 0))),
            )
            impl_budget_prefix = budget_manager.format_budget_warning(budget_warning)

        # Build initial state for implementation stage using session's confirmed report
        context = message_router.extract_context(request.messages)

        # Restore original context from session if available (for better Writer context)
        original_ctx = session.original_context or {}
        conversation_history = original_ctx.get(
            "conversation_history",
            context.conversation_history
        )
        cursor_system_prompt = original_ctx.get(
            "cursor_system_prompt",
            context.cursor_system_prompt
        )

        initial_state = {
            "cursor_system_prompt": cursor_system_prompt,
            "conversation_history": conversation_history,
            "ternion_report": session.ternion_report_raw,  # Use raw for Writer (internal use)
            "session_id": session.session_id,
            "execution_mode": session.execution_mode.value,
            "thinking_logs": [],
            "errors": [],
            "revision_count": 0,
        }

        # For streaming requests, use real-time event forwarding
        if request.stream:
            return await _run_implementation_streaming(
                initial_state=initial_state,
                model=request.model,
                session_id=session.session_id,
                budget_prefix=impl_budget_prefix,
                show_thinking_logs=config.show_thinking_logs,
            )

        # Non-streaming execution
        final_state = await run_implementation_stage(initial_state)

        # Extract results
        thinking_logs = final_state.get("thinking_logs", [])
        final_code = final_state.get("final_output", "") or final_state.get("generated_code", "")
        final_revision_count = final_state.get("revision_count", 0)

        # Log completion with revision count for Observability tracking
        logger.info(
            "implementation_stage_completed",
            session_id=session.session_id,
            execution_mode="ternion_full",
            revision_count=final_revision_count,
            has_output=bool(final_code),
            errors=final_state.get("errors", []),
        )
        error_count = len(final_state.get("errors", []))
        log_manager.emit(
            level="INFO",
            category="SESSION",
            message=f"Implementation stage completed | session_id={session.session_id} | revisions={final_revision_count} | has_output={bool(final_code)} | errors={error_count}",
        )

        # Build output using the already-loaded config
        output_parts = []
        if impl_budget_prefix:
            output_parts.append(impl_budget_prefix)
        is_patch_output = _is_patch_or_diff_output(final_code)
        _emit_thinking_logs_to_observability(
            thinking_logs,
            session_id=session.session_id,
            context="implementation_stage_output",
            suppressed_from_chat=is_patch_output,
        )
        if thinking_logs and config.show_thinking_logs and not is_patch_output:
            output_parts.append("".join(thinking_logs))
            output_parts.append("\n---\n\n")
        if final_code:
            output_parts.append(final_code)
        else:
            output_parts.append("[Ternion] Execution completed but no output was generated.")

        output = "".join(output_parts)
        session_store.update_session(session.session_id, stage=SessionStage.EXECUTED)

        return JSONResponse(
                content=ChatCompletionResponse(
                    model=request.model,
                    choices=[
                        Choice(
                            message=ChatMessage(
                                role=MessageRole.ASSISTANT,
                                content=output,
                            )
                        )
                    ],
                ).model_dump()
            )


async def handle_rejected_session(
    session: Session,
    feedback: str,
    request: ChatCompletionRequest,
) -> Response:
    """
    Handle user rejection of the analysis report.

    Updates session state and re-runs the analysis with rejection context.

    Args:
        session: The rejected session
        feedback: User's rejection feedback
        request: Original chat completion request

    Returns:
        New analysis report
    """
    session_store.update_session(
        session.session_id,
        stage=SessionStage.REJECTED,
        last_user_feedback=feedback,
    )

    # Re-run analysis with rejection context
    from ternion.workflow.graph import run_discussion

    context = message_router.extract_context(request.messages)
    # In ternion_full, we do not stop at the report stage; proceed to execution automatically.
    context.await_confirmation = session.execution_mode != ExecutionMode.TERNION_FULL
    context.rejection_context = feedback
    context.execution_mode = session.execution_mode.value

    # Add rejection context to thinking
    logger.info(
        "session_rejected_reanalyze",
        session_id=session.session_id,
        feedback_preview=feedback[:100],
    )
    log_manager.emit(
        level="INFO",
        category="USER_ACTION",
        message=f"Session rejected - re-analyzing | session_id={session.session_id} | feedback_preview={feedback[:50]}...",
    )

    final_state = await run_discussion(context)

    # Build output (this will be a new report with new session)
    thinking_logs = final_state.get("thinking_logs", [])
    final_output = final_state.get("final_output", "")
    _emit_thinking_logs_to_observability(
        thinking_logs,
        session_id=session.session_id,
        context="rejected_session_reanalyze_report",
        suppressed_from_chat=False,
    )

    output_parts = []
    # Check config for thinking logs display
    config = config_store.load()
    if thinking_logs and config.show_thinking_logs:
        output_parts.append("".join(thinking_logs))
        if final_output and not final_output.startswith("\n"):
            output_parts.append("\n")
    if final_output:
        output_parts.append(final_output)

    output = "".join(output_parts) if output_parts else "[Ternion] Re-analysis completed."

    if request.stream:
        return StreamingResponse(
            create_sse_stream(model=request.model, content=output),
            media_type="text/event-stream",
        )
    else:
        return JSONResponse(
            content=ChatCompletionResponse(
                model=request.model,
                choices=[
                    Choice(
                        message=ChatMessage(
                            role=MessageRole.ASSISTANT,
                            content=output,
                        )
                    )
                ],
            ).model_dump()
        )


async def handle_clarify_request(
    session: Session,
    question: str,
    request: ChatCompletionRequest,
) -> Response:
    """
    Handle user clarification questions about the analysis report.

    Answers questions using the existing report without re-running RCA.
    The session remains in AWAITING_CONFIRMATION state.

    Args:
        session: The current session with the analysis report
        question: User's clarification question
        request: Original chat completion request

    Returns:
        Answer with confirm/reject prompt and session markers
    """
    safe_question = sanitize_for_cursor_display((question or "").strip())
    report_for_search = session.ternion_report_raw or session.ternion_report_safe
    excerpt = _extract_relevant_report_excerpt(report_for_search, question)

    mode_desc = (
        "code implementation by Ternion"
        if session.execution_mode == ExecutionMode.TERNION_FULL
        else "implementation handoff to Cursor"
    )

    answer_text = (
        "Below is the most relevant excerpt from the existing analysis report."
        if excerpt
        else (
            "I couldn't locate a specific passage in the existing report that directly answers your question. "
            "Please tell me which part you want to clarify (root cause / impact / plan / verification / rollback), "
            "or rephrase your question."
        )
    )
    excerpt_block = f"""\n\n### Relevant excerpt from the report\n\n{excerpt}""" if excerpt else ""

    # Build a response that addresses the question without re-running RCA
    clarification_response = f"""## Clarification

Based on the analysis report above, I'll address your question:

### Your question
{_as_blockquote(safe_question)}

---

### Answer (based on the existing report)
{answer_text}{excerpt_block}

### Next Steps

Please review the analysis and let me know how you'd like to proceed:
- **Confirm**: Reply with "yes", "proceed", or similar to continue with {mode_desc}
- **Reject**: Reply with "no", "wrong", or describe what's incorrect for me to re-analyze
- **Clarify**: Ask more questions (I won't generate code changes until you confirm)

TERNION_SESSION_ID={session.session_id}
TERNION_SESSION_STAGE=AWAITING_CONFIRMATION
TERNION_EXECUTION_MODE={session.execution_mode.value}
TERNION_REPORT_HASH={session.report_hash}"""

    logger.info(
        "clarify_request_handled",
        session_id=session.session_id,
        question_preview=question[:50],
    )
    log_manager.emit(
        level="INFO",
        category="SESSION",
        message=f"Clarification request handled | session_id={session.session_id} | question_preview={question[:50]}...",
    )

    if request.stream:
        return StreamingResponse(
            create_sse_stream(model=request.model, content=clarification_response),
            media_type="text/event-stream",
        )
    else:
        return JSONResponse(
            content=ChatCompletionResponse(
                model=request.model,
                choices=[
                    Choice(
                        message=ChatMessage(
                            role=MessageRole.ASSISTANT,
                            content=clarification_response,
                        )
                    )
                ],
            ).model_dump()
        )


async def handle_post_execution_followup(
    session: Session,
    _user_message: str,
    request: ChatCompletionRequest,
) -> Response:
    """
    Handle follow-up messages for sessions that have already been confirmed/executed.

    Routes based on execution mode:
    - CURSOR_HANDOFF: Remind user to switch to a non-Ternion model for code generation
    - TERNION_FULL: Inform user the session is complete and suggest starting a new request

    Args:
        session: The confirmed/executed session
        _user_message: User's latest message
        request: Original chat completion request

    Returns:
        Reminder or guidance response
    """
    # Session markers (read-only) for context reference
    session_markers = f"""
---

**Session Reference** _(read-only)_:
TERNION_SESSION_ID={session.session_id}
TERNION_SESSION_STAGE={session.stage.value}
TERNION_EXECUTION_MODE={session.execution_mode.value}"""

    if session.execution_mode == ExecutionMode.CURSOR_HANDOFF:
        # Remind user to switch to a non-Ternion model and re-provide handoff
        # Use ternion_report_safe for user-visible output
        handoff_output = generate_handoff_package(session.ternion_report_safe)

        reminder = f"""## 📋 Reminder: Please Switch to a Non-Ternion Model

This session has already been confirmed. To proceed with code implementation, please:

1. **Switch your model** from `ternion-team` to a direct model (e.g., `claude-3-5-sonnet-latest`, `gpt-4o`, or `gemini-2.0-flash`)
2. Then send your implementation request

The Ternion council provides analysis only - code generation should be done by a dedicated coding model.

---

{handoff_output}
{session_markers}"""

        if request.stream:
            return StreamingResponse(
                create_sse_stream(model=request.model, content=reminder),
                media_type="text/event-stream",
            )
        else:
            return JSONResponse(
                content=ChatCompletionResponse(
                    model=request.model,
                    choices=[
                        Choice(
                            message=ChatMessage(
                                role=MessageRole.ASSISTANT,
                                content=reminder,
                            )
                        )
                    ],
                ).model_dump()
            )
    else:
        # TERNION_FULL: Session is complete
        completion_notice = f"""## ✅ Session Complete

This Ternion session has already been executed. The code has been generated and reviewed.

If you need to make additional changes or start a new analysis, please send a new request describing what you need.

---

**Previous Session Summary**:
- Session ID: `{session.session_id}`
- Status: {session.stage.value.replace('_', ' ').title()}
- Mode: Ternion Full (code generated by Ternion)
{session_markers}"""

        if request.stream:
            return StreamingResponse(
                create_sse_stream(model=request.model, content=completion_notice),
                media_type="text/event-stream",
            )
        else:
            return JSONResponse(
                content=ChatCompletionResponse(
                    model=request.model,
                    choices=[
                        Choice(
                            message=ChatMessage(
                                role=MessageRole.ASSISTANT,
                                content=completion_notice,
                            )
                        )
                    ],
                ).model_dump()
            )


async def handle_rejected_session_followup(
    session: Session,
    _user_message: str,
    request: ChatCompletionRequest,
) -> Response:
    """
    Handle follow-up messages for rejected sessions.

    Provides clear guidance when users continue referencing a rejected session,
    explaining the session was rejected and suggesting next steps.

    Args:
        session: The rejected session
        _user_message: User's latest message
        request: Original chat completion request

    Returns:
        Guidance response explaining the rejection status and next steps
    """
    # Session markers (read-only) for context reference
    session_markers = f"""
---

**Session Reference** _(read-only)_:
TERNION_SESSION_ID={session.session_id}
TERNION_SESSION_STAGE={session.stage.value}
TERNION_EXECUTION_MODE={session.execution_mode.value}"""

    # Include last user feedback if available
    feedback_section = ""
    if session.last_user_feedback:
        feedback_section = f"""
**Your Previous Feedback**:
> {session.last_user_feedback[:200]}{'...' if len(session.last_user_feedback) > 200 else ''}
"""

    guidance = f"""## ⚠️ Session Previously Rejected

This Ternion session was rejected based on your previous feedback. The analysis is no longer active.
{feedback_section}
### What Would You Like to Do?

**Option 1: Start Fresh Analysis**
Send a new request describing your problem, and Ternion will perform a fresh root cause analysis.

**Option 2: Clarify Your Concerns**
If you'd like to explain what was wrong with the previous analysis, please describe the specific issues and I'll initiate a new analysis with that context.

---

**Previous Session Info**:
- Session ID: `{session.session_id}`
- Original Mode: {session.execution_mode.value.replace('_', ' ').title()}
- Status: Rejected
{session_markers}"""

    if request.stream:
        return StreamingResponse(
            create_sse_stream(model=request.model, content=guidance),
            media_type="text/event-stream",
        )
    else:
        return JSONResponse(
            content=ChatCompletionResponse(
                model=request.model,
                choices=[
                    Choice(
                        message=ChatMessage(
                            role=MessageRole.ASSISTANT,
                            content=guidance,
                        )
                    )
                ],
            ).model_dump()
        )


async def handle_unknown_intent(
    session: Session,
    request: ChatCompletionRequest,
) -> Response:
    """
    Handle unknown user intent by asking for clarification.

    Args:
        session: The current session
        request: Original chat completion request

    Returns:
        Clarification prompt
    """
    mode_desc = (
        "code implementation by Ternion"
        if session.execution_mode == ExecutionMode.TERNION_FULL
        else "implementation handoff to Cursor"
    )

    clarification = f"""I couldn't determine your intent from your response.

Please let me know how you'd like to proceed:
- **Confirm**: Reply with "yes", "proceed", or similar to continue with {mode_desc}
- **Reject**: Reply with "no", "wrong", or describe what's incorrect for me to re-analyze
- **Clarify**: Ask any questions about the analysis

TERNION_SESSION_ID={session.session_id}
TERNION_SESSION_STAGE=AWAITING_CONFIRMATION
TERNION_EXECUTION_MODE={session.execution_mode.value}
TERNION_REPORT_HASH={session.report_hash}"""

    if request.stream:
        return StreamingResponse(
            create_sse_stream(model=request.model, content=clarification),
            media_type="text/event-stream",
        )
    else:
        return JSONResponse(
            content=ChatCompletionResponse(
                model=request.model,
                choices=[
                    Choice(
                        message=ChatMessage(
                            role=MessageRole.ASSISTANT,
                            content=clarification,
                        )
                    )
                ],
            ).model_dump()
        )


def generate_handoff_package(ternion_report_safe: str) -> str:
    """
    Generate a structured handoff package for Cursor agent execution.

    The package contains the confirmed analysis formatted according to Spec 7.2,
    with clear sections for the receiving model/agent to implement.

    Args:
        ternion_report_safe: The sanitized Ternion analysis report (pre-processed
                             for Cursor safety - no code fences or patch triggers)

    Returns:
        Formatted handoff package string with structured sections
    """
    # Note: Caller is expected to pass session.ternion_report_safe
    # No additional sanitization needed

    parsed = parse_structured_report(ternion_report_safe)
    if parsed.is_structured:
        structured_body = f"""### Root Cause

{parsed.root_cause or "- (Missing) Root cause section not found in report."}

---

### Evidence / Logs

{parsed.evidence or "- (Missing) Evidence section not found in report."}

---

### Scope & Non-Goals

{parsed.scope or "- (Missing) Scope section not found in report."}

---

### Fix Plan / Recommendation

{parsed.fix_plan or "- (Missing) Fix plan section not found in report."}

---

### Verification

{parsed.verification or "- (Missing) Verification section not found in report."}

---

### Risks & Rollback

{parsed.risks or "- (Missing) Risks section not found in report."}

---

### If not effective, then what?

{parsed.if_not_effective or "- (Missing) Fallback section not found in report."}"""
    else:
        structured_body = f"""### Confirmed Analysis Report (Unstructured)

{ternion_report_safe}"""

    return f"""## Ternion Analysis Confirmed — Cursor Handoff Package

The Ternion council has completed the root cause analysis and the user has confirmed the findings. Please implement the solution based on the following structured analysis.

---

{structured_body}

---

### Next Action

> **IMPORTANT**: Switch your model from `ternion-team` to a dedicated coding model
> (e.g., `claude-3-5-sonnet-latest`, `gpt-4o`, or `gemini-2.0-flash`)
> and then implement the plan above.

The Ternion council provides analysis only. Code generation should be done by a dedicated implementation model."""

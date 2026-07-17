"""
API routes for Ternion gateway.

Implements:
- OpenAI-compatible endpoints (chat completions, models listing, health/probe)
- Session lifecycle management (create → confirm/reject → execute → complete)
- Tool-loop orchestration for Cursor Agent execution follow-ups
- Guardrail enforcement (tool policy, deliverable policy, budget, shell safety)
- Phase-specific follow-up handlers (evidence, report_evidence, execution, optimizer)
"""

import asyncio
import contextlib
import json
import ntpath
import posixpath
import re
import subprocess
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable
from dataclasses import dataclass
from dataclasses import field as dc_field
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ternion.core.budget import budget_manager
from ternion.core.config_store import config_store
from ternion.core.deliverable_policy import DeliverableType, resolve_deliverable_policy
from ternion.core.exceptions import RuntimeModelUnavailableError
from ternion.core.intent_classifier import (
    Intent,
    classify_intent_with_fallback,
    get_latest_user_message,
    parse_report_hash_marker,
    parse_session_marker,
)
from ternion.core.models import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    ChoiceDelta,
    MessageRole,
    ModelInfo,
    ModelsListResponse,
    StreamChoice,
)
from ternion.core.session_store import (
    ExecutionMode,
    Session,
    SessionStage,
    get_session_lock,
    session_store,
)
from ternion.providers.manager import provider_manager
from ternion.router.context import TernionContext
from ternion.router.message_router import MessageRouter
from ternion.utils.cursor_safety import sanitize_for_cursor_display, sanitize_for_preview
from ternion.utils.i18n import MessageKey, get_web_base_url, t
from ternion.utils.language_resources import (
    get_cursor_non_agent_mode_hints,
    get_report_section_keywords,
)
from ternion.utils.log_manager import log_manager
from ternion.utils.report_parser import parse_structured_report
from ternion.utils.secrets import redact_secrets
from ternion.utils.shell_policy import evaluate_shell_command
from ternion.utils.streaming import (
    create_sse_stream,
    create_sse_tool_calls_stream,
)
from ternion.utils.tool_policy import (
    EXECUTION_ALLOWED_TOOL_CANONICAL as _EXECUTION_ALLOWED_TOOL_CANONICAL,
)
from ternion.utils.tool_policy import (
    SHELL_TOOL_CANONICAL as _SHELL_TOOL_CANONICAL,
)
from ternion.utils.workspace_paths import (
    detect_path_style,
    normalize_declared_workspace_path,
    normalize_local_file_path,
    normalize_workspace_target_path,
    resolve_local_workspace_root,
    workspace_relative_path,
)
from ternion.workflow.streaming_events import StreamEventQueue, StreamEventType

logger = structlog.get_logger(__name__)
router = APIRouter()

# Strings that indicate the output is a Cursor auto-apply patch.
# When detected, thinking logs are suppressed from chat output to avoid
# breaking Cursor's patch parser.
_PATCHLIKE_TRIGGERS = (
    "*** Begin Patch",
    "*** End Patch",
    "*** Update File:",
    "*** Add File:",
    "diff --git",
)

_TERNION_TOOL_CALL_ID_SESSION_RE = re.compile(r"\bternion_([a-f0-9]{12})_", re.IGNORECASE)
_WORKSPACE_PATH_LINE_RE = re.compile(
    r"(?im)^\s*(?:Workspace Path|workspace_path)\s*[:=]\s*(?P<path>.+?)\s*$"
)
_OPEN_FILES_SECTION_RE = re.compile(
    r"<open_and_recently_viewed_files>\s*(?P<body>.*?)\s*</open_and_recently_viewed_files>",
    flags=re.IGNORECASE | re.DOTALL,
)
_DOCUMENT_FILE_SUFFIXES = {
    ".adoc",
    ".md",
    ".mdx",
    ".org",
    ".rst",
    ".txt",
}
_CODE_LIKE_TOP_LEVEL_DIRS = {
    "migrations",
    "scripts",
    "src",
    "test",
    "tests",
    "web",
}
_CODE_LIKE_SUFFIXES = {
    ".c",
    ".cc",
    ".cfg",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".py",
    ".pyi",
    ".rs",
    ".scss",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".vue",
    ".yaml",
    ".yml",
}

# Default/max line limits for read_file pagination. Keeps context window
# usage bounded. Evidence phase allows a higher limit because evidence
# collection benefits from wider file reads.
_READ_FILE_DEFAULT_LIMIT = 300
_READ_FILE_MAX_LIMIT = 400
_READ_FILE_EVIDENCE_MAX_LIMIT = 2000
_TOOL_LOOP_MAX_ROUNDS = 100

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

# Number of raw characters to buffer at chunk boundary to prevent
# cross-chunk formation of patch triggers during streaming sanitization.
_STREAM_SANITIZE_TAIL_KEEP = 32

# Maps workflow phase names to the SessionStage used when a follow-up
# completes without producing final output. Allows the tool loop to
# continue rather than prematurely closing the session.
_RESUMABLE_PHASE_STAGE_MAP = {
    "report_evidence": SessionStage.EXECUTION_IN_PROGRESS,
    "execution": SessionStage.EXECUTION_IN_PROGRESS,
    "optimizer": SessionStage.OPTIMIZER_IN_PROGRESS,
}


def _extract_runtime_model_unavailable_payload(
    payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a normalized runtime stale-model payload if present."""
    if not isinstance(payload, dict):
        return None
    code = str(payload.get("code") or payload.get("detail") or "").strip()
    provider = str(payload.get("provider") or "").strip()
    model = str(payload.get("model") or "").strip()
    if code != "MODEL_UNAVAILABLE" or not provider or not model:
        return None
    return {
        "code": "MODEL_UNAVAILABLE",
        "provider": provider,
        "model": model,
        "refresh_suggested": bool(payload.get("refresh_suggested", True)),
        "provider_message": str(payload.get("provider_message") or "").strip(),
    }


def _build_runtime_model_unavailable_text(provider: str, model: str) -> str:
    """Build a localized runtime stale-model message for HTTP and SSE responses."""
    return t(
        MessageKey.RUNTIME_MODEL_UNAVAILABLE,
        provider=provider,
        model=model,
    )


def _build_runtime_model_unavailable_response(payload: dict[str, Any]) -> JSONResponse:
    """Build an OpenAI-compatible error response for runtime stale-model failures."""
    normalized = _extract_runtime_model_unavailable_payload(payload)
    if normalized is None:
        logger.error(
            "runtime_model_unavailable_payload_invalid",
            payload_keys=sorted(payload.keys()) if isinstance(payload, dict) else [],
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": t(MessageKey.STREAM_ERROR_GENERIC).strip(),
                    "type": "internal_error",
                    "code": "INTERNAL_ERROR",
                }
            },
        )
    provider = str(normalized.get("provider") or "")
    model = str(normalized.get("model") or "")
    refresh_suggested = bool(normalized.get("refresh_suggested", True))
    provider_message = str(normalized.get("provider_message") or "")
    error_content: dict[str, Any] = {
        "message": _build_runtime_model_unavailable_text(provider, model),
        "type": "model_unavailable",
        "code": "MODEL_UNAVAILABLE",
        "provider": provider,
        "model": model,
        "refresh_suggested": refresh_suggested,
    }
    if provider_message:
        error_content["provider_message"] = provider_message
    return JSONResponse(
        status_code=400,
        content={"error": error_content},
    )


def _get_runtime_model_unavailable_response_from_state(
    state: dict[str, Any] | None,
) -> JSONResponse | None:
    """Convert workflow runtime stale-model payloads into HTTP responses."""
    if not isinstance(state, dict):
        return None
    payload = _extract_runtime_model_unavailable_payload(state.get("runtime_error_payload"))
    if payload is None:
        return None
    return _build_runtime_model_unavailable_response(payload)


async def _put_stream_exception(
    stream_queue: StreamEventQueue,
    exc: Exception,
    *,
    phase: str = "",
) -> None:
    """Emit a stream error, enriching recognized error types with metadata."""
    if isinstance(exc, RuntimeModelUnavailableError):
        await stream_queue.put_error(
            str(exc),
            phase=phase,
            **exc.to_payload(),
        )
        return
    await stream_queue.put_error(str(exc), phase=phase)


def _get_stream_error_text(metadata: dict[str, Any]) -> str:
    """Build stream-facing error text, specializing runtime stale-model failures."""
    payload = _extract_runtime_model_unavailable_payload(metadata)
    if payload is not None:
        return _build_runtime_model_unavailable_text(
            str(payload.get("provider") or ""),
            str(payload.get("model") or ""),
        )
    return t(MessageKey.STREAM_ERROR_GENERIC)


def _build_stream_error_backfill(errors: list[Any]) -> str:
    """Build a fallback text block when streaming ends without user-visible output."""
    if not errors:
        return ""
    output_parts = [
        t(MessageKey.DISCUSSION_NO_OUTPUT),
        "\n\n",
        t(MessageKey.DISCUSSION_ERRORS_HEADER),
    ]
    for err in errors:
        err_msg = sanitize_for_cursor_display(str(err))
        if err_msg:
            output_parts.append(f"- {err_msg}\n")
    return "".join(output_parts)


_REPORT_SECTION_TITLE_KEYS = {
    "root_cause": MessageKey.REPORT_SECTION_ROOT_CAUSE_TITLE,
    "evidence": MessageKey.REPORT_SECTION_EVIDENCE_TITLE,
    "scope": MessageKey.REPORT_SECTION_SCOPE_TITLE,
    "fix_plan": MessageKey.REPORT_SECTION_FIX_PLAN_TITLE,
    "verification": MessageKey.REPORT_SECTION_VERIFICATION_TITLE,
    "risks": MessageKey.REPORT_SECTION_RISKS_TITLE,
    "if_not_effective": MessageKey.REPORT_SECTION_IF_NOT_EFFECTIVE_TITLE,
}


def _get_report_section_title(key: str) -> str:
    """Return the localized display title for a structured report section.

    Args:
        key: Internal section key (e.g. "root_cause", "evidence").

    Returns:
        Translated title string, or the raw key if no mapping exists.
    """
    message_key = _REPORT_SECTION_TITLE_KEYS.get(key)
    if message_key is None:
        return key
    return t(message_key)


async def _sse_heartbeat_event(chunk_id: str, created: int, model: str) -> str:
    """Build a keep-alive SSE heartbeat chunk string.

    Heartbeats prevent proxy/client idle timeouts during long non-streaming
    workflow phases (e.g. evidence collection, divergence).

    Args:
        chunk_id: The SSE stream chunk identifier.
        created: Unix timestamp for the chunk.
        model: Model name to embed in the chunk.

    Returns:
        Formatted SSE data line string ready to yield.
    """
    heartbeat = ChatCompletionChunk(
        id=chunk_id,
        created=created,
        model=model,
        choices=[StreamChoice(delta=ChoiceDelta(role=MessageRole.ASSISTANT))],
    )
    return f"data: {heartbeat.model_dump_json()}\n\n"


async def _consume_sse_events(
    *,
    stream_queue: StreamEventQueue,
    heartbeat_interval_seconds: int,
    on_timeout: Callable[[], Awaitable[str]],
    on_event: Callable[[Any], AsyncGenerator[str, None]],
) -> AsyncGenerator[str, None]:
    """Consume StreamEventQueue events with keep-alive heartbeats.

    This helper centralizes the common SSE event-consumption loop:
    - wait on the stream queue with a timeout
    - emit a heartbeat on idle timeout
    - stop when the queue yields None
    - delegate event-specific handling to the provided callback

    Args:
        stream_queue: The StreamEventQueue providing streaming events.
        heartbeat_interval_seconds: Heartbeat interval (seconds) for idle keep-alive.
        on_timeout: Async callable returning a single SSE chunk string for heartbeat.
        on_event: Async generator callback that yields SSE chunk strings for a given event.

    Yields:
        SSE-formatted chunk strings to forward to clients.
    """
    while True:
        try:
            event = await asyncio.wait_for(
                stream_queue.get(),
                timeout=heartbeat_interval_seconds,
            )
        except TimeoutError:
            yield await on_timeout()
            continue

        if event is None:
            break

        async for sse_chunk in on_event(event):
            yield sse_chunk


def _append_stream_safe_cursor_text(
    pending_raw: str,
    chunk: str,
    *,
    tail_keep: int = _STREAM_SANITIZE_TAIL_KEEP,
) -> tuple[str, str]:
    """
    Incrementally sanitize text for Cursor display without cross-chunk trigger formation.

    This keeps a small raw tail buffer so patch/code-fence triggers cannot be formed
    across streamed chunk boundaries.
    """
    if not chunk:
        return "", pending_raw

    pending = (pending_raw or "") + chunk
    keep = max(0, int(tail_keep))
    if keep and len(pending) <= keep:
        return "", pending
    if keep:
        safe_raw = pending[:-keep]
        pending = pending[-keep:]
    else:
        safe_raw = pending
        pending = ""
    return sanitize_for_cursor_display(safe_raw), pending


_CURSOR_NON_AGENT_MODE_HINTS = tuple(get_cursor_non_agent_mode_hints())


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
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str):
                part_text = part_text.strip()
                if part_text:
                    yield part_text


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
        if msg.role != MessageRole.USER:
            continue
        for text in _iter_message_content_text(msg.content):
            if needle_lower in text.lower():
                return True
    return False


def _build_session_markers(session: Session, *, stage: SessionStage | None = None) -> str:
    """Build session-marker block appended to chat responses.

    These markers (TERNION_SESSION_ID, TERNION_SESSION_STAGE, etc.) are
    echoed back by the client in subsequent turns and parsed by
    ``parse_session_marker()`` to re-attach follow-up messages to the
    correct session. Changing the format here requires a coordinated
    update in ``core/intent_classifier.py``.
    """
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
    """Wrap guardrail/gate content with session markers for HITL routing."""
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
            headers=_SSE_HEADERS,
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


def _phase_start_indicator_text(phase: str, *, session_id: str | None = None) -> str | None:
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
        session_id_str = str(session_id or "").strip()
        if session_id_str:
            session = session_store.load_session(session_id_str)
            if session is not None:
                announced = bool(getattr(session, "execution_phase_announced", False))
                previous_phase = str(getattr(session, "workflow_phase", "") or "").strip().lower()
                resume_phase = (
                    str(getattr(session, "report_evidence_resume_phase", "") or "").strip().lower()
                )
                if previous_phase == "report_evidence" and resume_phase == "execution":
                    if not announced:
                        session_store.update_session(session_id_str, execution_phase_announced=True)
                    return t(MessageKey.EXECUTION_CONTINUE_AFTER_EVIDENCE)
                if not announced:
                    session_store.update_session(session_id_str, execution_phase_announced=True)
                    return t(MessageKey.EXECUTION_START)
                return None
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
    workflow_phase: str | None = None,
) -> list[dict]:
    """
    Rewrite tool_call ids to embed session_id for stable follow-up routing.

    Cursor will echo these ids back as `tool_call_id` in tool-role messages.
    """
    phase = (workflow_phase or "").strip().lower()
    read_file_max_limit = (
        _READ_FILE_EVIDENCE_MAX_LIMIT if "evidence" in phase else _READ_FILE_MAX_LIMIT
    )

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

        # Cursor tool naming differs across client versions ("read_file" vs "Read").
        # Enforce pagination for both to avoid oversized contexts.
        canonical_name = re.sub(r"[^a-z0-9]+", "", name.strip().lower())
        if canonical_name in {"readfile", "read"}:
            arguments_str = _enforce_read_file_pagination(
                arguments_str,
                max_limit=read_file_max_limit,
            )
            arguments_str = _rewrite_tool_call_repo_paths(name, arguments_str)
        elif canonical_name in {"ls", "glob", "grep", "semanticsearch", "readlints"}:
            arguments_str = _rewrite_tool_call_repo_paths(name, arguments_str)

        new_id = f"ternion_{session_id}_r{round_index:04d}_c{idx:02d}"
        rewritten_call = {
            "id": new_id,
            "type": "function",
            "function": {
                "name": name,
                "arguments": arguments_str,
            },
        }

        responses_item_id = tc.get("responses_api_item_id")
        responses_call_id = tc.get("responses_api_call_id")
        responses_response_id = tc.get("responses_api_response_id")
        raw_id = tc.get("id")
        if (
            (not isinstance(responses_item_id, str) or not responses_item_id.strip())
            and isinstance(raw_id, str)
            and raw_id.startswith("fc_")
        ):
            responses_item_id = raw_id
        if (
            (not isinstance(responses_call_id, str) or not responses_call_id.strip())
            and isinstance(raw_id, str)
            and raw_id.startswith("call_")
        ):
            responses_call_id = raw_id

        if isinstance(responses_item_id, str) and responses_item_id.strip():
            rewritten_call["responses_api_item_id"] = responses_item_id.strip()
        if isinstance(responses_call_id, str) and responses_call_id.strip():
            rewritten_call["responses_api_call_id"] = responses_call_id.strip()
        if isinstance(responses_response_id, str) and responses_response_id.strip():
            rewritten_call["responses_api_response_id"] = responses_response_id.strip()

        rewritten.append(rewritten_call)

    return rewritten


def _strip_internal_tool_call_fields(tool_calls: list[dict] | None) -> list[dict]:
    """Return tool calls without internal metadata used for provider round-tripping."""
    public_tool_calls: list[dict] = []
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        public_tc = dict(tc)
        public_tc.pop("responses_api_item_id", None)
        public_tc.pop("responses_api_call_id", None)
        public_tc.pop("responses_api_response_id", None)
        public_tool_calls.append(public_tc)
    return public_tool_calls


def _append_assistant_tool_call_message(
    execution_messages: list[dict] | None,
    tool_calls: list[dict] | None,
) -> list[dict]:
    """Append one assistant tool-call message to execution history."""
    messages = list(execution_messages or [])
    messages.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": list(tool_calls or []),
        }
    )
    return messages


def _resolve_followup_completion_stage(
    *,
    final_phase: str,
    final_code: str,
    errors: list[Any],
    session_id: str,
) -> SessionStage:
    """Resolve session stage for follow-up workflow completion."""
    if isinstance(final_code, str) and final_code.strip() and not errors:
        return SessionStage.EXECUTED
    if errors:
        return SessionStage.EXECUTION_IN_PROGRESS

    phase = str(final_phase or "").strip().lower()
    resumable_stage = _RESUMABLE_PHASE_STAGE_MAP.get(phase)
    if resumable_stage is not None:
        log_manager.emit(
            level="WARN",
            category="WORKFLOW",
            message=(
                "followup_non_terminal_without_output | "
                f"session_id={session_id} | "
                f"phase={phase} | "
                f"resolved_stage={resumable_stage.value}"
            ),
        )
        logger.warning(
            "followup_non_terminal_without_output",
            session_id=session_id,
            workflow_phase=phase,
            resolved_stage=resumable_stage.value,
        )
        return resumable_stage

    return SessionStage.RCA_COMPLETE


def _is_safe_repo_relative_path(path_str: str) -> bool:
    """
    Validate a repo-relative path (no parent traversal; no absolute roots).
    """
    if not isinstance(path_str, str) or not path_str.strip():
        return False
    s = path_str.strip()
    if s.startswith(("/", "\\", "~")):
        return False
    if "$" in s:
        return False
    normalized = s.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p]
    for part in parts:
        if part == ".":
            continue
        if part == "..":
            return False
    return True


def _rewrite_repo_internal_path_value(raw_path: str) -> str:
    """
    Rewrite common repo-relative path mistakes into an absolute repo-internal path.

    Examples:
    - "/docs/x.md" -> "<repo_root>/docs/x.md"
    - "./web/src/App.tsx" -> "<repo_root>/web/src/App.tsx"
    """
    if not isinstance(raw_path, str) or not raw_path.strip():
        return raw_path

    repo_root = _resolve_project_root()
    cleaned = raw_path.strip().strip('"').strip("'").strip("`")

    p = Path(cleaned).expanduser()
    if p.is_absolute():
        try:
            resolved = p.resolve(strict=False)
        except Exception:
            resolved = p
        try:
            resolved.relative_to(repo_root)
            return str(resolved)
        except Exception:
            pass

        if resolved.exists():
            return str(resolved)

        if cleaned.startswith("/"):
            candidate_rel = cleaned.lstrip("/")
        else:
            return raw_path
    else:
        candidate_rel = cleaned[2:] if cleaned.startswith("./") else cleaned

    if not _is_safe_repo_relative_path(candidate_rel):
        return raw_path

    first = candidate_rel.replace("\\", "/").split("/", 1)[0]
    if first and (repo_root / first).exists():
        try:
            return str((repo_root / candidate_rel).resolve(strict=False))
        except Exception:
            return str(repo_root / candidate_rel)
    return raw_path


def _rewrite_tool_call_repo_paths(tool_name: str, arguments_json: str) -> str:
    """
    Normalize repo-relative paths for read/search tool calls.

    This improves robustness when models emit absolute-looking paths like "/docs/x.md".
    """
    import json

    canonical = re.sub(r"[^a-z0-9]+", "", (tool_name or "").strip().lower())
    try:
        args = json.loads(arguments_json or "{}")
    except Exception:
        return arguments_json
    if not isinstance(args, dict):
        return arguments_json

    changed = False

    def rewrite_key(key: str) -> None:
        nonlocal changed
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            rewritten = _rewrite_repo_internal_path_value(value)
            if rewritten != value:
                args[key] = rewritten
                changed = True

    def rewrite_list_key(key: str) -> None:
        nonlocal changed
        value = args.get(key)
        if not isinstance(value, list):
            return
        rewritten_list: list[str] = []
        list_changed = False
        for item in value:
            if not isinstance(item, str):
                continue
            rewritten = _rewrite_repo_internal_path_value(item)
            if rewritten != item:
                list_changed = True
            rewritten_list.append(rewritten)
        if list_changed:
            args[key] = rewritten_list
            changed = True

    if canonical in {"read", "readfile"}:
        rewrite_key("path")
        rewrite_key("target_file")
        rewrite_key("target_notebook")
    elif canonical == "ls" or canonical == "glob":
        rewrite_key("target_directory")
    elif canonical == "grep":
        rewrite_key("path")
    elif canonical == "semanticsearch":
        rewrite_list_key("target_directories")
    elif canonical == "readlints":
        rewrite_list_key("paths")

    if not changed:
        return arguments_json
    return json.dumps(args, ensure_ascii=False)


def _enforce_read_file_pagination(arguments_json: str, *, max_limit: int) -> str:
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

    if not isinstance(max_limit, int) or max_limit < 1:
        max_limit = _READ_FILE_MAX_LIMIT

    offset = args.get("offset")
    limit = args.get("limit")

    if not isinstance(offset, int) or offset < 1:
        args["offset"] = 1

    if not isinstance(limit, int) or limit < 1:
        args["limit"] = _READ_FILE_DEFAULT_LIMIT
    elif limit > max_limit:
        args["limit"] = max_limit

    return json.dumps(args, ensure_ascii=False)


# Post-canonicalization names (all lowercase, alphanumeric only).
# Older Cursor clients use snake_case; newer versions use TitleCase.
# Both map to the same canonical form here.
_MUTATING_TOOL_NAMES = {
    "write",
    "writefile",
    "strreplace",
    "searchreplace",
    "deletefile",
    "editnotebook",
    "applypatch",
    "delete",
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


_EXTERNAL_OUTPUT_WRITTEN_RE = re.compile(r"(?im)^\s*output\s+written\s+to:\s*(?P<path>.+?)\s*$")
_FILE_TAG_RE = re.compile(r"(?i)\[file\](?P<path>.+?)\[/file\]")


def _extract_external_output_paths(text: str) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    candidates: list[str] = []
    for match in _EXTERNAL_OUTPUT_WRITTEN_RE.finditer(text):
        path = match.group("path").strip().strip('"').strip("'").strip("`")
        if path:
            candidates.append(path)
    for match in _FILE_TAG_RE.finditer(text):
        path = match.group("path").strip().strip('"').strip("'").strip("`")
        if path:
            candidates.append(path)

    seen: set[str] = set()
    unique: list[str] = []
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _build_redacted_preview(text: str, *, max_chars: int = 200) -> str:
    raw = (text or "").strip().replace("\n", " ")
    redacted = redact_secrets(raw)
    if len(redacted) > max_chars:
        redacted = redacted[:max_chars] + "..."
    return sanitize_for_cursor_display(redacted)


def _diff_tool_call_name_rewrites(before: list[dict], after: list[dict]) -> list[dict[str, str]]:
    before_by_id: dict[str, str] = {}
    for tc in before or []:
        if not isinstance(tc, dict):
            continue
        tc_id = tc.get("id")
        if not isinstance(tc_id, str) or not tc_id:
            continue
        name, _args = _extract_tool_name_and_arguments(tc)
        if isinstance(name, str) and name:
            before_by_id[tc_id] = name

    rewrites: list[dict[str, str]] = []
    for tc in after or []:
        if not isinstance(tc, dict):
            continue
        tc_id = tc.get("id")
        if not isinstance(tc_id, str) or not tc_id:
            continue
        name, _args = _extract_tool_name_and_arguments(tc)
        before_name = before_by_id.get(tc_id)
        if before_name and isinstance(name, str) and name and name != before_name:
            rewrites.append({"id": tc_id, "from": before_name, "to": name})

    return rewrites


def _collect_execution_tool_policy_block_details(
    tool_calls: list[dict],
) -> tuple[list[str], list[dict[str, str]]]:
    blocked_tools: list[str] = []
    blocked_shell: list[dict[str, str]] = []
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        name, args_str = _extract_tool_name_and_arguments(tc)
        canonical = re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())
        if not canonical or canonical not in _EXECUTION_ALLOWED_TOOL_CANONICAL:
            blocked_tools.append(name or t(MessageKey.TOOL_POLICY_UNKNOWN_TOOL))
            continue

        if canonical in _SHELL_TOOL_CANONICAL:
            command = _extract_shell_command(args_str) or ""
            decision = evaluate_shell_command(command)
            if decision.allowed:
                continue
            blocked_shell.append(
                {
                    "tool": name or t(MessageKey.TOOL_POLICY_SHELL),
                    "command_preview": _build_redacted_preview(command, max_chars=200),
                    "reason": decision.reason,
                }
            )
    return blocked_tools, blocked_shell


def _extract_text_fragments(content: Any) -> list[str]:
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        fragments: list[str] = []
        for item in content:
            if isinstance(item, str):
                fragments.append(item)
                continue
            if isinstance(item, dict):
                for key in ("text", "content"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        fragments.append(value)
                        break
                continue
            for attr in ("text", "content"):
                value = getattr(item, attr, None)
                if isinstance(value, str) and value.strip():
                    fragments.append(value)
                    break
        return fragments
    if content is None:
        return []
    return [str(content)]


def _iter_request_message_texts(messages: list[ChatMessage]) -> Iterable[str]:
    for message in messages or []:
        yield from _extract_text_fragments(getattr(message, "content", None))


def _path_module_for_style(style: str) -> Any:
    return ntpath if style == "windows" else posixpath


def _coerce_workspace_candidate_root(path_str: str) -> tuple[str, str]:
    normalized, style = normalize_declared_workspace_path(path_str)
    if not normalized or not style:
        return "", ""
    path_mod = _path_module_for_style(style)
    basename = path_mod.basename(normalized)
    suffix = path_mod.splitext(basename)[1] if basename else ""
    if suffix:
        parent = path_mod.dirname(normalized)
        if parent:
            normalized = parent
    return normalized, style


def _extract_candidate_paths_from_text(text: str) -> list[str]:
    candidates: list[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- ") or line.startswith("* "):
            line = line[2:].strip()
        if " (" in line:
            line = line.split(" (", 1)[0].strip()
        line = line.strip("`'\"")
        if detect_path_style(line):
            candidates.append(line)
    return candidates


def _longest_declared_common_ancestor(paths: list[str]) -> tuple[str, str]:
    grouped: dict[str, list[str]] = {"posix": [], "windows": []}
    for raw_path in paths or []:
        candidate, style = _coerce_workspace_candidate_root(raw_path)
        if candidate and style in grouped:
            grouped[style].append(candidate)
    for style in sorted(grouped, key=lambda item: len(grouped[item]), reverse=True):
        normalized = grouped[style]
        if not normalized:
            continue
        path_mod = _path_module_for_style(style)
        try:
            common = path_mod.commonpath(normalized)
        except Exception:
            continue
        if common:
            return path_mod.normpath(common), style
    return "", ""


def _extract_workspace_boundary_from_request_messages(
    messages: list[ChatMessage],
) -> tuple[str, str, str, str]:
    texts = list(_iter_request_message_texts(messages))
    for text in texts:
        match = _WORKSPACE_PATH_LINE_RE.search(text)
        if not match:
            continue
        workspace_root, style = normalize_declared_workspace_path(match.group("path"))
        if workspace_root and style:
            return (
                workspace_root,
                resolve_local_workspace_root(workspace_root),
                style,
                "explicit_workspace_path",
            )

    open_file_candidates: list[str] = []
    for text in texts:
        for match in _OPEN_FILES_SECTION_RE.finditer(text):
            open_file_candidates.extend(_extract_candidate_paths_from_text(match.group("body")))
    inferred_open_files, open_files_style = _longest_declared_common_ancestor(open_file_candidates)
    if inferred_open_files and open_files_style:
        return (
            inferred_open_files,
            resolve_local_workspace_root(inferred_open_files),
            open_files_style,
            "open_files_common_ancestor",
        )

    candidates: list[str] = []
    for text in texts:
        candidates.extend(_extract_candidate_paths_from_text(text))
    inferred, inferred_style = _longest_declared_common_ancestor(candidates)
    if inferred and inferred_style:
        return (
            inferred,
            resolve_local_workspace_root(inferred),
            inferred_style,
            "message_paths_common_ancestor",
        )

    fallback = _resolve_project_root()
    logger.warning("workspace_root_fallback_used", fallback=str(fallback))
    return str(fallback), str(fallback), "posix", "fallback_project_root"


def _extract_workspace_root_from_request_messages(messages: list[ChatMessage]) -> str:
    workspace_root, _local_workspace_root, _style, _source = (
        _extract_workspace_boundary_from_request_messages(messages)
    )
    return workspace_root


def _apply_workspace_boundary_to_context(
    context: TernionContext,
    messages: list[ChatMessage],
    *,
    session: Session | None = None,
) -> None:
    extracted_root, extracted_local_root, extracted_style, extracted_source = (
        _extract_workspace_boundary_from_request_messages(messages)
    )
    persisted_root = str(getattr(session, "workspace_root", "") or "")
    persisted_local_root = str(getattr(session, "local_workspace_root", "") or "")
    persisted_style = str(getattr(session, "workspace_path_style", "") or "")
    persisted_source = str(getattr(session, "workspace_root_source", "") or "")
    if persisted_root and not persisted_style:
        _normalized_root, persisted_style = normalize_declared_workspace_path(persisted_root)
    if persisted_root and extracted_root and persisted_root != extracted_root:
        logger.warning(
            "workspace_root_session_request_mismatch",
            session_id=str(getattr(session, "session_id", "") or ""),
            persisted_workspace_root=persisted_root,
            extracted_workspace_root=extracted_root,
            persisted_workspace_root_source=persisted_source,
            extracted_workspace_root_source=extracted_source,
        )
    workspace_root = persisted_root or extracted_root
    context.workspace_root = workspace_root
    context.local_workspace_root = persisted_local_root
    if not context.local_workspace_root and extracted_root == workspace_root:
        context.local_workspace_root = extracted_local_root
    if not context.local_workspace_root:
        context.local_workspace_root = resolve_local_workspace_root(workspace_root)
    context.workspace_path_style = persisted_style
    if not context.workspace_path_style and extracted_root == workspace_root:
        context.workspace_path_style = extracted_style
    if not context.workspace_path_style:
        _normalized_root, context.workspace_path_style = normalize_declared_workspace_path(
            workspace_root
        )
    context.workspace_root_source = persisted_source
    if not context.workspace_root_source and extracted_root == workspace_root:
        context.workspace_root_source = extracted_source


def _normalize_file_path(
    path_str: str,
    workspace_root: str | None = None,
    workspace_path_style: str | None = None,
) -> str | None:
    """Normalize a file path against the declared workspace boundary.

    Args:
        path_str: The path to normalize.
        workspace_root: Optional client-declared workspace root.
        workspace_path_style: Optional workspace path style.

    Returns:
        The normalized client-visible path, or None if invalid.
    """
    return normalize_workspace_target_path(
        path_str,
        workspace_root=str(workspace_root or ""),
        workspace_path_style=str(workspace_path_style or ""),
    )


def _normalize_local_file_path(
    path_str: str,
    *,
    workspace_root: str | None = None,
    workspace_path_style: str | None = None,
    local_workspace_root: str | None = None,
) -> str | None:
    """Map a client-visible path onto a locally accessible server path."""
    provided_local_root = str(local_workspace_root or "").strip()
    resolved_local_root = provided_local_root
    if not resolved_local_root:
        resolved_local_root = resolve_local_workspace_root(str(workspace_root or ""))
        if resolved_local_root:
            logger.debug(
                "workspace_local_root_fallback_used",
                workspace_root=str(workspace_root or ""),
                resolved_local_workspace_root=resolved_local_root,
            )
    return normalize_local_file_path(
        path_str,
        workspace_root=str(workspace_root or ""),
        workspace_path_style=str(workspace_path_style or ""),
        local_workspace_root=resolved_local_root,
    )


def _resolve_workspace_fields(
    *,
    state: dict[str, Any] | None = None,
    context: TernionContext | None = None,
    session: Session | None = None,
    original_context: dict[str, Any] | None = None,
) -> tuple[str, str, str, str]:
    """Resolve workspace boundary fields from the highest-priority available source."""

    def _get_from_dict(source: dict[str, Any] | None, key: str) -> str:
        if not isinstance(source, dict):
            return ""
        value = source.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else ""

    def _get_from_object(source: object | None, key: str) -> str:
        value = getattr(source, key, "")
        return value.strip() if isinstance(value, str) and value.strip() else ""

    workspace_root = (
        _get_from_dict(state, "workspace_root")
        or _get_from_dict(original_context, "workspace_root")
        or _get_from_object(context, "workspace_root")
        or _get_from_object(session, "workspace_root")
    )
    local_workspace_root = (
        _get_from_dict(state, "local_workspace_root")
        or _get_from_dict(original_context, "local_workspace_root")
        or _get_from_object(context, "local_workspace_root")
        or _get_from_object(session, "local_workspace_root")
    )
    workspace_path_style = (
        _get_from_dict(state, "workspace_path_style")
        or _get_from_dict(original_context, "workspace_path_style")
        or _get_from_object(context, "workspace_path_style")
        or _get_from_object(session, "workspace_path_style")
    )
    workspace_root_source = (
        _get_from_dict(state, "workspace_root_source")
        or _get_from_dict(original_context, "workspace_root_source")
        or _get_from_object(context, "workspace_root_source")
        or _get_from_object(session, "workspace_root_source")
    )
    return (
        workspace_root,
        local_workspace_root,
        workspace_path_style,
        workspace_root_source,
    )


def _read_text_file_best_effort(path_str: str) -> str | None:
    try:
        p = Path(path_str)
        if not p.exists() or not p.is_file():
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _extract_mutation_target_path(tool_name: str, arguments_json: str) -> str | None:
    canonical = re.sub(r"[^a-z0-9]+", "", (tool_name or "").strip().lower())
    args = _coerce_json_object(arguments_json)

    # Legacy write/search_replace tools (and newer StrReplace)
    if canonical in {"write", "writefile", "searchreplace", "strreplace"}:
        for key in ("file_path", "path", "target_file", "target_path"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    # Legacy delete_file and newer Delete
    if canonical in {"deletefile", "delete"}:
        value = args.get("target_file")
        if isinstance(value, str):
            return value
        value = args.get("path")
        return value if isinstance(value, str) else None

    # Legacy edit_notebook and newer EditNotebook
    if canonical == "editnotebook":
        value = args.get("target_notebook")
        return value if isinstance(value, str) else None

    # Newer ApplyPatch (freeform patch string)
    if canonical == "applypatch":
        return _extract_apply_patch_target_path(arguments_json)

    return None


def _extract_apply_patch_target_path(patch_text: str) -> str | None:
    """
    Extract the target file path from a Cursor ApplyPatch payload.

    ApplyPatch supports a single-file envelope with one of:
    - "*** Update File: <path>"
    - "*** Add File: <path>"
    """
    if not isinstance(patch_text, str) or not patch_text.strip():
        return None
    for line in patch_text.splitlines():
        s = line.strip()
        if s.startswith("*** Update File:"):
            return s[len("*** Update File:") :].strip() or None
        if s.startswith("*** Add File:"):
            return s[len("*** Add File:") :].strip() or None
    return None


def _extract_shell_command(arguments_json: str) -> str | None:
    args = _coerce_json_object(arguments_json)
    for key in ("command", "cmd", "commands"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, list):
            parts = [v for v in value if isinstance(v, str) and v.strip()]
            if parts:
                return " && ".join(parts)
    return None


_SHELL_EXIT_CODE_RE = re.compile(
    r"(?:\bexit[_\s-]*code\b|\blast[_\s-]*exit[_\s-]*code\b)\s*[:=]\s*(\d+)",
    flags=re.IGNORECASE | re.UNICODE,
)
_SHELL_ELAPSED_MS_RE = re.compile(
    r"(?:\belapsed[_\s-]*ms\b|\bduration[_\s-]*ms\b)\s*[:=]\s*(\d+)",
    flags=re.IGNORECASE | re.UNICODE,
)
_SHELL_COMPLETED_MS_RE = re.compile(
    r"\bcompleted\s+in\s+(\d+)\s*ms\b",
    flags=re.IGNORECASE | re.UNICODE,
)


def _extract_shell_purpose(arguments_json: str) -> str | None:
    args = _coerce_json_object(arguments_json)
    for key in ("description", "purpose"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_shell_working_directory(arguments_json: str) -> str | None:
    args = _coerce_json_object(arguments_json)
    for key in ("working_directory", "cwd"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_shell_command_for_dedup(command: str) -> str:
    s = (command or "").strip()
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def _extract_shell_result_metrics(raw_content: str) -> tuple[int | None, int | None]:
    """
    Best-effort extraction of exit_code / elapsed_ms from a Shell tool result.

    Cursor/clients may embed these values in the tool output text. If not present,
    this returns (None, None).
    """
    text = raw_content or ""
    exit_code: int | None = None
    elapsed_ms: int | None = None

    m = _SHELL_EXIT_CODE_RE.search(text)
    if m:
        try:
            exit_code = int(m.group(1))
        except Exception:
            exit_code = None

    m = _SHELL_ELAPSED_MS_RE.search(text) or _SHELL_COMPLETED_MS_RE.search(text)
    if m:
        try:
            elapsed_ms = int(m.group(1))
        except Exception:
            elapsed_ms = None

    return exit_code, elapsed_ms


_PYTEST_NODEID_RE = re.compile(
    r"^(?:FAILED|ERROR)\s+([^\s]+::[^\s]+)(?:\s+-\s+.*)?$",
    flags=re.IGNORECASE | re.UNICODE,
)
_PYTEST_ERROR_TYPE_RE = re.compile(r"^E\s+([A-Za-z_]\w+)(?::|\s|$)")
_PYTEST_SUMMARY_RE = re.compile(
    r"(?P<failed>\d+)\s+failed\b.*",
    flags=re.IGNORECASE | re.UNICODE,
)
# Client-derived workspace sources considered trustworthy for mutation scoping.
_TRUSTED_WORKSPACE_ROOT_SOURCES = {
    "explicit_workspace_path",
    "open_files_common_ancestor",
    "message_paths_common_ancestor",
}


def _is_pytest_command(command: str) -> bool:
    s = (command or "").strip().lower()
    return bool(s) and "pytest" in s


def _extract_pytest_failure_details(raw_content: str) -> dict[str, object]:
    """
    Best-effort extraction of pytest failure details from a Shell tool result.

    This is used to build deterministic failure handoff context for the Optimizer.
    """
    text = raw_content or ""
    marker = "Command output:"
    if marker in text:
        _, text = text.split(marker, 1)
    lines = [line.rstrip("\n") for line in (text or "").splitlines()]

    failed_tests: list[str] = []
    for line in lines:
        m = _PYTEST_NODEID_RE.match((line or "").strip())
        if not m:
            continue
        nodeid = (m.group(1) or "").strip()
        if nodeid and nodeid not in failed_tests:
            failed_tests.append(nodeid)

    error_type = ""
    for line in reversed(lines):
        m = _PYTEST_ERROR_TYPE_RE.match((line or "").strip())
        if not m:
            continue
        token = (m.group(1) or "").strip()
        if token:
            error_type = token
            break

    summary_line = ""
    for line in reversed(lines[-80:]):
        s = (line or "").strip()
        if not s:
            continue
        if _PYTEST_SUMMARY_RE.search(s):
            summary_line = s
            break

    # Include the tail to preserve the most actionable stack context.
    non_empty = [ln for ln in lines if (ln or "").strip()]
    tail_lines = non_empty[-30:] if non_empty else []
    trace_tail = "\n".join(tail_lines).strip()
    if len(trace_tail) > 1600:
        trace_tail = trace_tail[-1600:]

    return {
        "pytest_failed_tests": failed_tests[:12],
        "pytest_error_type": error_type,
        "pytest_summary_line": summary_line,
        "pytest_trace_tail": trace_tail,
    }


def _find_duplicate_shell_call(
    tool_results_meta: dict[str, dict],
    *,
    dedup_key: str,
) -> str | None:
    if not dedup_key:
        return None
    for tool_call_id, meta in (tool_results_meta or {}).items():
        if not isinstance(meta, dict):
            continue
        key = meta.get("shell_dedup_key")
        if isinstance(key, str) and key == dedup_key:
            return tool_call_id
        cmd = meta.get("shell_command")
        if isinstance(cmd, str) and _normalize_shell_command_for_dedup(cmd) == dedup_key:
            return tool_call_id
    return None


def _extract_cursor_tool_names(cursor_tools: list[dict[str, Any]] | None) -> list[str]:
    names: list[str] = []
    for tool in cursor_tools or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _canonical_tool_name(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())


def _prefer_tool_name(available: list[str], *, preferred: list[str]) -> str:
    available_set = {n for n in available if isinstance(n, str)}
    for name in preferred:
        if name in available_set:
            return name
    return available[0]


def _normalize_and_validate_tool_calls_against_cursor_tools(
    *,
    workflow_phase: str,
    tool_calls: list[dict],
    cursor_tools: list[dict[str, Any]] | None,
) -> tuple[list[dict], str | None]:
    """
    Normalize tool call names to match Cursor-provided tools (case-sensitive).

    This is a defensive guardrail to prevent legacy alias drift (e.g., "run_terminal_cmd")
    from producing non-executable tool calls in Cursor.
    """
    phase = str(workflow_phase or "").strip().lower()
    if phase not in {"execution", "optimizer"}:
        return list(tool_calls or []), None

    available = _extract_cursor_tool_names(cursor_tools)
    if not available:
        return list(tool_calls or []), None

    available_set = set(available)
    canonical_to_available: dict[str, list[str]] = {}
    for tool_name in available:
        canonical_to_available.setdefault(_canonical_tool_name(tool_name), []).append(tool_name)

    shell_available = [
        name for name in available if _canonical_tool_name(name) in _SHELL_TOOL_CANONICAL
    ]
    write_available = [
        name for name in available if _canonical_tool_name(name) in {"write", "writefile"}
    ]
    delete_available = [
        name for name in available if _canonical_tool_name(name) in {"delete", "deletefile"}
    ]

    rewritten: list[dict] = []
    rewrites: list[tuple[str, str]] = []
    unknown: list[str] = []
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        name, args_str = _extract_tool_name_and_arguments(tc)
        if not isinstance(name, str) or not name.strip():
            unknown.append(t(MessageKey.TOOL_POLICY_UNKNOWN_TOOL))
            continue

        if name in available_set:
            rewritten.append(tc)
            continue

        canonical = _canonical_tool_name(name)
        mapped: str | None = None

        exact_candidates = canonical_to_available.get(canonical) or []
        unique_exact = list(dict.fromkeys(exact_candidates))
        if len(unique_exact) == 1:
            mapped = unique_exact[0]

        if mapped is None and canonical in _SHELL_TOOL_CANONICAL and shell_available:
            mapped = _prefer_tool_name(
                shell_available,
                preferred=["Shell", "RunTerminalCmd", "bash", "Bash"],
            )

        if mapped is None and canonical in {"write", "writefile"} and write_available:
            mapped = _prefer_tool_name(
                write_available,
                preferred=["Write", "write_file", "write", "WriteFile"],
            )

        if mapped is None and canonical in {"delete", "deletefile"} and delete_available:
            mapped = _prefer_tool_name(
                delete_available,
                preferred=["Delete", "delete_file", "delete", "DeleteFile"],
            )

        if mapped is None or mapped not in available_set:
            unknown.append(name)
            continue

        if mapped != name:
            rewrites.append((name, mapped))
        rewritten.append(
            {
                **tc,
                "function": {
                    **(tc.get("function") if isinstance(tc.get("function"), dict) else {}),
                    "name": mapped,
                    "arguments": args_str,
                },
            }
        )

    if rewrites:
        rendered = ", ".join(f"{src}->{dst}" for src, dst in rewrites[:8])
        log_manager.emit(
            level="INFO",
            category="GUARDRAIL",
            message=(
                "tool_call_name_rewrite | "
                f"phase={phase} | "
                f"rewrites={rendered}" + (" | truncated=true" if len(rewrites) > 8 else "")
            ),
        )

    if not unknown:
        return rewritten, None

    blocked_tools_text = "\n".join(f"- {item}" for item in sorted(set(unknown)))
    none_placeholder = t(MessageKey.TOOL_POLICY_NONE)
    return [], t(
        MessageKey.EXECUTION_TOOL_POLICY_BLOCKED,
        blocked_tools=blocked_tools_text,
        blocked_shell=f"- {none_placeholder}",
    )


def _enforce_execution_tool_policy(
    *,
    workflow_phase: str,
    tool_calls: list[dict],
) -> tuple[list[dict], str | None]:
    if workflow_phase not in {"execution", "optimizer"}:
        return list(tool_calls or []), None

    blocked_tools: list[str] = []
    blocked_shell: list[str] = []
    none_placeholder = t(MessageKey.TOOL_POLICY_NONE)
    unknown_tool = t(MessageKey.TOOL_POLICY_UNKNOWN_TOOL)
    shell_label = t(MessageKey.TOOL_POLICY_SHELL)
    empty_command = t(MessageKey.TOOL_POLICY_EMPTY_COMMAND)

    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        name, args_str = _extract_tool_name_and_arguments(tc)
        canonical = re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())
        if not canonical or canonical not in _EXECUTION_ALLOWED_TOOL_CANONICAL:
            blocked_tools.append(name or unknown_tool)
            continue

        if canonical in _SHELL_TOOL_CANONICAL:
            command = _extract_shell_command(args_str)
            decision = evaluate_shell_command(command or "")
            if not decision.allowed:
                preview = (command or "").strip().replace("\n", " ")
                if len(preview) > 200:
                    preview = preview[:200] + "..."
                blocked_shell.append(f"{name or shell_label} -> {preview or empty_command}")

    if not blocked_tools and not blocked_shell:
        return list(tool_calls or []), None

    log_manager.emit(
        level="INFO",
        category="GUARDRAIL",
        message=(
            "execution_tool_policy_blocked | "
            f"blocked_tools={'; '.join(blocked_tools) or none_placeholder} | "
            f"blocked_shell={'; '.join(blocked_shell) or none_placeholder}"
        ),
    )
    blocked_tools_text = (
        "\n".join(f"- {item}" for item in blocked_tools)
        if blocked_tools
        else f"- {none_placeholder}"
    )
    blocked_shell_text = (
        "\n".join(f"- {item}" for item in blocked_shell)
        if blocked_shell
        else f"- {none_placeholder}"
    )
    return [], t(
        MessageKey.EXECUTION_TOOL_POLICY_BLOCKED,
        blocked_tools=blocked_tools_text,
        blocked_shell=blocked_shell_text,
    )


def _ensure_baseline_snapshots_for_tool_calls(
    session: Session,
    tool_calls: list[dict],
) -> tuple[dict[str, str], list[str]]:
    baseline = dict(getattr(session, "baseline_file_snapshots", {}) or {})
    modified_files = list(getattr(session, "modified_files", []) or [])
    modified_set = set(modified_files)
    local_workspace_root = str(getattr(session, "local_workspace_root", "") or "").strip()
    if not local_workspace_root:
        logger.debug("baseline_snapshot_skipped_no_local_workspace")

    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        name, args_str = _extract_tool_name_and_arguments(tc)
        canonical = re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())
        if not canonical or canonical not in _MUTATING_TOOL_NAMES:
            continue
        target = _extract_mutation_target_path(name, args_str)
        normalized = _normalize_file_path(
            target or "",
            getattr(session, "workspace_root", ""),
            getattr(session, "workspace_path_style", ""),
        )
        if not normalized:
            continue

        if normalized not in baseline and local_workspace_root:
            local_target = _normalize_local_file_path(
                target or "",
                workspace_root=getattr(session, "workspace_root", ""),
                workspace_path_style=getattr(session, "workspace_path_style", ""),
                local_workspace_root=local_workspace_root,
            )
            content = _read_text_file_best_effort(local_target) if local_target else None
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
    (Temporarily disabled) Do not rewrite/filter TodoWrite in execution flow.

    We intentionally let the agent decide whether/when to call TodoWrite.

    Returns:
        (tool_calls_unchanged, todo_written_now=False)
    """
    _ = session  # keep signature stable; used by future guardrails
    return list(tool_calls or []), False


def _resolve_deliverable_policy_from_context(
    conversation_history: list[dict],
    ternion_report: str,
) -> tuple[DeliverableType, str]:
    user_message = get_latest_user_message(conversation_history or [])
    report_for_policy = _extract_report_scope_for_policy(ternion_report)
    policy = resolve_deliverable_policy(user_message, report_for_policy)
    return policy.deliverable_type, policy.allowed_write_scope


def _extract_report_scope_for_policy(report: str) -> str:
    parsed = parse_structured_report(report or "")
    if parsed.is_structured and parsed.scope.strip():
        return parsed.scope
    return report or ""


def _workspace_relative_path(
    path_str: str,
    workspace_root: str | None = None,
    workspace_path_style: str | None = None,
) -> str | None:
    return workspace_relative_path(
        path_str,
        workspace_root=str(workspace_root or ""),
        workspace_path_style=str(workspace_path_style or ""),
    )


@lru_cache(maxsize=1)
def _resolve_project_root() -> Path:
    """
    Resolve project root for path scoping.
    """
    origin = Path(__file__).resolve().parent
    for base in [origin] + list(origin.parents):
        if (base / "pyproject.toml").is_file():
            return base
        if (base / ".git").exists():
            return base
    try:
        return Path.cwd().resolve()
    except Exception:
        return Path.cwd()


# Timeout for local git subprocess calls (status, show).
# Kept short to avoid blocking request handling on slow filesystems.
_GIT_CMD_TIMEOUT_SECONDS = 2.0


def _parse_git_status_porcelain(
    output: str,
    *,
    repo_root: Path,
    workspace_root: str,
    workspace_path_style: str,
) -> tuple[set[str], set[str]]:
    """
    Parse `git status --porcelain=v1` output into absolute path sets.

    Returns:
        (modified_paths, untracked_paths)
    """
    modified: set[str] = set()
    untracked: set[str] = set()
    for raw in (output or "").splitlines():
        line = raw.rstrip("\n")
        if len(line) < 3:
            continue
        status = line[:2]
        if status == "!!":
            continue
        path_part = line[3:].strip()
        if not path_part:
            continue
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1].strip()
        normalized = _normalize_file_path(
            str(repo_root / path_part),
            workspace_root=workspace_root,
            workspace_path_style=workspace_path_style,
        )
        if not normalized:
            continue
        if status == "??":
            untracked.add(normalized)
        else:
            modified.add(normalized)
    return modified, untracked


def _try_get_git_status_snapshot(
    *,
    workspace_root: str | None = None,
    workspace_path_style: str | None = None,
    local_workspace_root: str | None = None,
) -> dict:
    """
    Best-effort workspace status snapshot for Shell side-effect tracking.
    """
    repo_root = str(local_workspace_root or "").strip()
    if not repo_root:
        logger.debug(
            "git_status_snapshot_skipped_no_local_workspace",
            workspace_root=str(workspace_root or ""),
        )
        return {}
    repo_root_path = Path(repo_root)
    if not (repo_root_path / ".git").exists():
        return {}
    try:
        result = subprocess.run(  # nosec - controlled local command
            ["git", "-C", str(repo_root_path), "status", "--porcelain=v1"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_CMD_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception:
        return {}
    if result.returncode != 0:
        return {}
    modified, untracked = _parse_git_status_porcelain(
        result.stdout,
        repo_root=repo_root_path,
        workspace_root=str(workspace_root or ""),
        workspace_path_style=str(workspace_path_style or ""),
    )
    return {
        "repo_root": str(repo_root_path),
        "modified": sorted(modified),
        "untracked": sorted(untracked),
    }


def _try_read_git_head_file(
    relative_path: str,
    *,
    local_workspace_root: str | None = None,
) -> str | None:
    """
    Best-effort read of a file at HEAD for baseline reconstruction.
    """
    if not isinstance(relative_path, str) or not relative_path.strip():
        return None
    repo_root = str(local_workspace_root or "").strip()
    if not repo_root:
        return None
    repo_root_path = Path(repo_root)
    if not (repo_root_path / ".git").exists():
        return None
    ref = f"HEAD:{relative_path.strip()}"
    try:
        result = subprocess.run(  # nosec - controlled local command
            ["git", "-C", str(repo_root_path), "show", ref],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_CMD_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _has_shell_tool_call(tool_calls: list[dict]) -> bool:
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        name, _args = _extract_tool_name_and_arguments(tc)
        canonical = re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())
        if canonical in _SHELL_TOOL_CANONICAL:
            return True
    return False


def _split_tool_calls_for_transparent_batching(
    tool_calls: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Split a mixed tool_calls list into (mutation_batch, shell_batch).

    Step 2 policy (transparent batching):
    - If the plan includes both mutation tools and shell commands, execute mutation first.
    - Defer shell commands to the next tool round without re-calling the LLM.
    """
    shell_calls: list[dict] = []
    mutation_calls: list[dict] = []
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        name, _args = _extract_tool_name_and_arguments(tc)
        canonical = re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())
        if canonical in _SHELL_TOOL_CANONICAL:
            shell_calls.append(tc)
        else:
            mutation_calls.append(tc)

    if shell_calls and mutation_calls:
        return mutation_calls, shell_calls
    return list(tool_calls or []), []


def _capture_tool_loop_pre_git_status(
    tool_calls: list[dict],
    *,
    round_index: int,
    workflow_phase: str,
    workspace_root: str | None = None,
    workspace_path_style: str | None = None,
    local_workspace_root: str | None = None,
) -> dict:
    if not _has_shell_tool_call(tool_calls):
        return {}
    snapshot = _try_get_git_status_snapshot(
        workspace_root=workspace_root,
        workspace_path_style=workspace_path_style,
        local_workspace_root=local_workspace_root,
    )
    if not snapshot:
        return {}
    snapshot["round_index"] = int(round_index or 0)
    snapshot["workflow_phase"] = str(workflow_phase or "")
    return snapshot


def _shell_command_may_write(command: str) -> bool:
    """
    Best-effort classification for Shell commands that may write to the workspace.

    This is used for observability only; it must not be relied on for policy.
    """
    s = (command or "").strip().lower()
    if not s:
        return False

    # Formatters may write by default unless explicitly in check/diff mode.
    if " -m black" in s or re.search(r"(?:^|\s)black(?:\s|$)", s):
        return "--check" not in s and "--diff" not in s

    if " -m ruff" in s or re.search(r"(?:^|\s)ruff(?:\s|$)", s):
        if "--fix" in s or "--fix-only" in s or "--unsafe-fixes" in s:
            return True
        if re.search(r"(?:^|\s)ruff\s+format(?:\s|$)", s):
            return "--check" not in s and "--diff" not in s
        return False

    # Script targets are project-defined; treat obvious "fix/format" scripts as potentially mutating.
    if re.search(r"(?:^|\s)(npm|pnpm|yarn)(?:\s|$)", s):
        if any(key in s for key in (":fix", "-fix", "_fix", ".fix")):
            return True
        if "format" in s:
            return True

    if re.search(r"(?:^|\s)make(?:\s|$)", s):
        return "format" in s or "fix" in s

    return False


def _is_document_like_target(relative_path: str) -> bool:
    if not relative_path:
        return False
    return PurePosixPath(relative_path).suffix.lower() in _DOCUMENT_FILE_SUFFIXES


def _is_code_like_target(relative_path: str) -> bool:
    if not relative_path:
        return False
    path = PurePosixPath(relative_path)
    first = path.parts[0] if path.parts else ""
    if first in _CODE_LIKE_TOP_LEVEL_DIRS:
        return True
    return path.suffix.lower() in _CODE_LIKE_SUFFIXES


def _is_doc_only_mutation_allowed(relative_path: str) -> bool:
    if not relative_path:
        return False
    if _is_code_like_target(relative_path):
        return False
    return bool(_is_document_like_target(relative_path))


def _has_mutating_tool_calls(tool_calls: list[dict]) -> bool:
    """Return whether the tool call batch contains any mutation tool."""
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        name, _args = _extract_tool_name_and_arguments(tc)
        canonical = re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())
        if canonical in _MUTATING_TOOL_NAMES:
            return True
    return False


def _is_workspace_root_trusted(
    workspace_root: str | None,
    workspace_root_source: str | None,
) -> bool:
    """Return whether the current workspace boundary is client-derived and trustworthy."""
    root = str(workspace_root or "").strip()
    source = str(workspace_root_source or "").strip()
    return bool(root) and source in _TRUSTED_WORKSPACE_ROOT_SOURCES


def _collect_mutation_target_displays(tool_calls: list[dict]) -> list[str]:
    """Collect mutation target display strings for guardrail feedback."""
    violations: list[str] = []
    unknown_target = t(MessageKey.TOOL_POLICY_UNKNOWN_TARGET)
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        name, args_str = _extract_tool_name_and_arguments(tc)
        canonical = re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())
        if not canonical or canonical not in _MUTATING_TOOL_NAMES:
            continue
        target = _extract_mutation_target_path(name or "", args_str)
        target_display = target or unknown_target
        violations.append(f"{name} -> {target_display}")
    return violations


def _workspace_root_unresolved_message(blocked_targets: list[str]) -> str:
    """Build the fail-closed message for mutation attempts without a trusted workspace."""
    none_placeholder = t(MessageKey.TOOL_POLICY_NONE)
    blocked = (
        "\n".join(f"- {item}" for item in blocked_targets)
        if blocked_targets
        else f"- {none_placeholder}"
    )
    return t(MessageKey.WORKSPACE_ROOT_UNRESOLVED, blocked_targets=blocked)


def _collect_deliverable_policy_violations(
    tool_calls: list[dict],
    deliverable_type: DeliverableType,
    workspace_root: str | None = None,
    workspace_path_style: str | None = None,
    workspace_root_source: str | None = None,
) -> list[str]:
    # Keep the trust guard here as well because this helper is also invoked
    # independently by guardrail event builders outside the main enforcement path.
    if _has_mutating_tool_calls(tool_calls) and not _is_workspace_root_trusted(
        workspace_root,
        workspace_root_source,
    ):
        return _collect_mutation_target_displays(tool_calls)
    violations: list[str] = []
    unknown_target = t(MessageKey.TOOL_POLICY_UNKNOWN_TARGET)
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        name, args_str = _extract_tool_name_and_arguments(tc)
        canonical = re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())
        if not canonical or canonical not in _MUTATING_TOOL_NAMES:
            continue
        target = _extract_mutation_target_path(name or "", args_str)
        target_display = target or unknown_target
        relative = _workspace_relative_path(target or "", workspace_root, workspace_path_style)
        if not relative:
            violations.append(f"{name} -> {target_display}")
            continue

        if deliverable_type == DeliverableType.ANALYSIS_ONLY:
            violations.append(f"{name} -> {target_display}")
            continue

        if deliverable_type == DeliverableType.DOC_ONLY and not _is_doc_only_mutation_allowed(
            relative
        ):
            violations.append(f"{name} -> {target_display}")

    return violations


def _deliverable_policy_violation_message(
    deliverable_type: DeliverableType,
    allowed_scope: str,
    violations: list[str],
) -> str:
    none_placeholder = t(MessageKey.TOOL_POLICY_NONE)
    blocked_targets = (
        "\n".join(f"- {item}" for item in violations) if violations else f"- {none_placeholder}"
    )
    return t(
        MessageKey.DELIVERABLE_POLICY_BLOCKED,
        deliverable_type=deliverable_type.value,
        allowed_scope=allowed_scope,
        blocked_targets=blocked_targets,
    )


def _enforce_deliverable_policy(
    *,
    workflow_phase: str,
    tool_calls: list[dict],
    conversation_history: list[dict],
    ternion_report: str,
    workspace_root: str | None = None,
    workspace_path_style: str | None = None,
    workspace_root_source: str | None = None,
) -> tuple[list[dict], str | None, DeliverableType | None, str]:
    if workflow_phase not in {"execution", "optimizer"}:
        return list(tool_calls or []), None, None, ""

    deliverable_type, allowed_scope = _resolve_deliverable_policy_from_context(
        conversation_history,
        ternion_report,
    )
    if _has_mutating_tool_calls(tool_calls) and not _is_workspace_root_trusted(
        workspace_root,
        workspace_root_source,
    ):
        blocked_targets = _collect_mutation_target_displays(tool_calls)
        log_manager.emit(
            level="INFO",
            category="GUARDRAIL",
            message=(
                "workspace_root_unresolved | "
                f"type={deliverable_type.value} | "
                f"allowed_scope={allowed_scope} | "
                f"workspace_root={str(workspace_root or '')} | "
                f"workspace_root_source={str(workspace_root_source or '')} | "
                f"blocked_targets={'; '.join(blocked_targets)}"
            ),
        )
        return (
            [],
            _workspace_root_unresolved_message(blocked_targets),
            deliverable_type,
            allowed_scope,
        )
    violations = _collect_deliverable_policy_violations(
        tool_calls,
        deliverable_type,
        workspace_root,
        workspace_path_style,
        workspace_root_source,
    )
    if not violations:
        return list(tool_calls or []), None, deliverable_type, allowed_scope

    log_manager.emit(
        level="INFO",
        category="GUARDRAIL",
        message=(
            "deliverable_policy_blocked | "
            f"type={deliverable_type.value} | "
            f"allowed_scope={allowed_scope} | "
            f"workspace_root={str(workspace_root or '')} | "
            f"workspace_path_style={str(workspace_path_style or '')} | "
            f"violations={'; '.join(violations)}"
        ),
    )
    message = _deliverable_policy_violation_message(
        deliverable_type,
        allowed_scope,
        violations,
    )
    return [], message, deliverable_type, allowed_scope


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
    """Return the effective Control Panel URL for the current runtime mode."""
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
    keywords: list[tuple[str, bool]] = [(k, True) for k in ascii_keywords] + [
        (k, False) for k in cjk_keywords
    ]

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

    keywords = get_report_section_keywords()

    # Map question intent to section preference (multi-lingual keyword routing).
    prefer: list[str] = []
    if any(k in q for k in keywords.scope):
        prefer = ["scope"]
    elif any(k in q for k in keywords.verification):
        prefer = ["verification"]
    elif any(k in q for k in keywords.risks):
        prefer = ["risks"]
    elif any(k in q for k in keywords.requirements):
        # For Design/Feature tasks, "Evidence / Logs" often contains requirements/constraints.
        prefer = ["evidence", "scope"]
    elif any(k in q for k in keywords.tradeoffs):
        # For Design/Feature tasks, "Root Cause" is the architecture thesis / decision rationale.
        prefer = ["root_cause", "risks"]
    elif any(k in q for k in keywords.design):
        # Prefer the actionable roadmap for design/feature questions to reduce excerpt noise.
        prefer = ["fix_plan"]
    elif any(k in q for k in keywords.fix_plan):
        prefer = ["fix_plan"]
    elif any(k in q for k in keywords.evidence):
        prefer = ["evidence"]
    elif any(k in q for k in keywords.if_not_effective):
        prefer = ["if_not_effective"]
    else:
        # Default: most users ask about the core conclusion.
        prefer = ["root_cause", "fix_plan", "verification"]

    chunks: list[str] = []
    for key in prefer:
        value = getattr(parsed, key, "")
        if value:
            title = _get_report_section_title(key)
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
    show_phase_indicators: bool,
) -> StreamingResponse:
    """
    Run the Ternion discussion workflow with real-time streaming output.

    This function creates a StreamEventQueue, passes it to the workflow,
    and returns an SSE response that forwards LLM tokens in real-time.

    Args:
        context: The extracted context from the Cursor request
        model: Model name for SSE response
        budget_warning: Optional budget warning to prepend
        show_phase_indicators: Whether to emit phase indicators into the stream

    Returns:
        StreamingResponse with real-time SSE events
    """
    from ternion.workflow.graph import run_discussion

    stream_queue = StreamEventQueue()

    context._stream_queue = stream_queue  # type: ignore[attr-defined]

    async def generate_sse() -> AsyncGenerator[str, None]:
        """SSE generator that consumes events from the queue."""
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
        final_state: dict = {}

        async def run_workflow() -> None:
            nonlocal final_state
            try:
                final_state = await run_discussion(context)
            except Exception as e:
                logger.exception("streaming_workflow_error", error=str(e))
                await _put_stream_exception(stream_queue, e)
            finally:
                stream_queue.close()

        workflow_task = asyncio.create_task(run_workflow())

        if budget_warning:
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
        pending_phase_indicator: str | None = None
        convergence_pending_raw = ""
        streamed_any_convergence = False

        try:
            # Consume events from queue with periodic keep-alive heartbeats.
            #
            # Some clients/proxies impose an idle timeout on streaming HTTP responses.
            # Heartbeats keep the SSE connection alive even when the workflow has
            # long non-streaming steps (e.g., evidence/divergence).
            heartbeat_interval_seconds = 10

            async def on_timeout() -> str:
                return await _sse_heartbeat_event(chunk_id, created, model)

            async def on_event(event: Any) -> AsyncGenerator[str, None]:
                nonlocal convergence_pending_raw
                nonlocal pending_phase_indicator
                nonlocal streamed_any_convergence
                nonlocal streamed_content
                if event.event_type == StreamEventType.TOKEN_DELTA:
                    # Forward token delta as SSE chunk
                    if event.delta:
                        phase_lower = str(event.phase or "").strip().lower()
                        if phase_lower == "convergence":
                            safe_text, convergence_pending_raw = _append_stream_safe_cursor_text(
                                convergence_pending_raw,
                                event.delta,
                            )
                            if safe_text:
                                if pending_phase_indicator:
                                    chunk = ChatCompletionChunk(
                                        id=chunk_id,
                                        created=created,
                                        model=model,
                                        choices=[
                                            StreamChoice(
                                                delta=ChoiceDelta(
                                                    content="\n" + pending_phase_indicator
                                                )
                                            )
                                        ],
                                    )
                                    yield f"data: {chunk.model_dump_json()}\n\n"
                                    pending_phase_indicator = None
                                streamed_any_convergence = True
                                streamed_content += safe_text
                                chunk = ChatCompletionChunk(
                                    id=chunk_id,
                                    created=created,
                                    model=model,
                                    choices=[StreamChoice(delta=ChoiceDelta(content=safe_text))],
                                )
                                yield f"data: {chunk.model_dump_json()}\n\n"
                            return

                        if pending_phase_indicator:
                            chunk = ChatCompletionChunk(
                                id=chunk_id,
                                created=created,
                                model=model,
                                choices=[
                                    StreamChoice(
                                        delta=ChoiceDelta(content="\n" + pending_phase_indicator)
                                    )
                                ],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"
                            pending_phase_indicator = None
                        streamed_content += event.delta
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=event.delta))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
                    return

                if event.event_type == StreamEventType.PHASE_START:
                    if show_phase_indicators and event.phase:
                        phase_lower = str(event.phase or "").strip().lower()
                        if convergence_pending_raw and phase_lower != "convergence":
                            flushed = sanitize_for_cursor_display(convergence_pending_raw)
                            convergence_pending_raw = ""
                            if flushed:
                                streamed_any_convergence = True
                                streamed_content += flushed
                                chunk = ChatCompletionChunk(
                                    id=chunk_id,
                                    created=created,
                                    model=model,
                                    choices=[StreamChoice(delta=ChoiceDelta(content=flushed))],
                                )
                                yield f"data: {chunk.model_dump_json()}\n\n"
                        indicator = _phase_start_indicator_text(
                            event.phase, session_id=getattr(context, "session_id", None)
                        )
                        if indicator:
                            if phase_lower == "convergence":
                                delta = ChoiceDelta(
                                    role=MessageRole.ASSISTANT,
                                    content=indicator,
                                )
                            else:
                                delta = ChoiceDelta(content="\n" + indicator)
                            chunk = ChatCompletionChunk(
                                id=chunk_id,
                                created=created,
                                model=model,
                                choices=[StreamChoice(delta=delta)],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"
                            pending_phase_indicator = None
                    return

                if event.event_type == StreamEventType.ERROR:
                    # Forward error
                    error_text = _get_stream_error_text(event.metadata)
                    chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[StreamChoice(delta=ChoiceDelta(content=error_text))],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"
                    return

            async for sse_chunk in _consume_sse_events(
                stream_queue=stream_queue,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                on_timeout=on_timeout,
                on_event=on_event,
            ):
                yield sse_chunk

            # Wait for workflow to complete
            await workflow_task

            if convergence_pending_raw:
                flushed = sanitize_for_cursor_display(convergence_pending_raw)
                convergence_pending_raw = ""
                if flushed:
                    streamed_any_convergence = True
                    streamed_content += flushed
                    chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[StreamChoice(delta=ChoiceDelta(content=flushed))],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"

            pending_tool_calls = final_state.get("pending_tool_calls") or []
            if pending_tool_calls:
                turn_outcome = _create_initial_tool_loop_session(
                    final_state=final_state,
                    context=context,
                    pending_tool_calls=pending_tool_calls,
                    cursor_tools=list(getattr(context, "cursor_tools", []) or []),
                    cursor_tool_choice=getattr(context, "cursor_tool_choice", None),
                )
                if turn_outcome.blocked:
                    for sse_chunk in _sse_text_stop_chunks(
                        chunk_id, created, model, turn_outcome.blocked_message
                    ):
                        yield sse_chunk
                    return
                for sse_chunk in _sse_tool_calls_chunks(
                    chunk_id, created, model, turn_outcome.cursor_tool_calls
                ):
                    yield sse_chunk
                return

            if streamed_any_convergence:
                suffix = str(final_state.get("final_output_suffix") or "")
                suffix = sanitize_for_cursor_display(suffix)
                if suffix:
                    for i in range(0, len(suffix), 128):
                        text = suffix[i : i + 128]
                        if not text:
                            continue
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

            # If workflow produced final_output but we didn't stream it
            # (e.g., non-streamable phases), send it now
            workflow_final = final_state.get("final_output", "") or final_state.get(
                "generated_code", ""
            )
            errors = final_state.get("errors", []) or []
            if workflow_final and not streamed_content:
                if pending_phase_indicator:
                    chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[
                            StreamChoice(delta=ChoiceDelta(content="\n" + pending_phase_indicator))
                        ],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"
                    pending_phase_indicator = None
                # Workflow produced output but streaming wasn't used
                # (e.g., divergence phase doesn't stream)
                # Send the complete output
                for i in range(0, len(workflow_final), 128):
                    text = workflow_final[i : i + 128]
                    chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"

            if errors and not workflow_final and not streamed_content:
                error_output = _build_stream_error_backfill(list(errors))
                for i in range(0, len(error_output), 128):
                    text = error_output[i : i + 128]
                    if not text:
                        continue
                    chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"
                streamed_content += error_output

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

        except asyncio.CancelledError:
            stream_queue.close()
            workflow_task.cancel()
            with contextlib.suppress(BaseException):
                await workflow_task
            raise
        except Exception as e:
            logger.exception("sse_generation_error", error=str(e))
            error_chunk = ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=model,
                choices=[
                    StreamChoice(delta=ChoiceDelta(content=t(MessageKey.STREAM_ERROR_INTERRUPTED)))
                ],
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


async def _run_implementation_streaming(
    initial_state: dict,
    model: str,
    session_id: str,
    budget_prefix: str,
    show_phase_indicators: bool,
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
        show_phase_indicators: Whether to emit phase indicators into the stream

    Returns:
        StreamingResponse with real-time SSE events
    """
    from ternion.workflow.implementation_stage import run_implementation_stage

    stream_queue = StreamEventQueue()

    initial_state["_stream_queue"] = stream_queue

    async def generate_sse() -> AsyncGenerator[str, None]:
        """SSE generator that consumes events from the queue."""
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
        final_state: dict = {}

        async def run_impl() -> None:
            nonlocal final_state
            try:
                final_state = await run_implementation_stage(initial_state)
            except Exception as e:
                logger.exception("streaming_implementation_error", error=str(e))
                await _put_stream_exception(stream_queue, e)
            finally:
                stream_queue.close()

        impl_task = asyncio.create_task(run_impl())

        if budget_prefix:
            chunk = ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=model,
                choices=[StreamChoice(delta=ChoiceDelta(content=budget_prefix))],
            )
            yield f"data: {chunk.model_dump_json()}\n\n"

        streamed_content = ""
        pending_phase_indicator: str | None = None

        try:
            # Consume events from queue with periodic keep-alive heartbeats.
            heartbeat_interval_seconds = 10

            async def on_timeout() -> str:
                return await _sse_heartbeat_event(chunk_id, created, model)

            async def on_event(event: Any) -> AsyncGenerator[str, None]:
                nonlocal pending_phase_indicator
                nonlocal streamed_content
                if event.event_type == StreamEventType.TOKEN_DELTA:
                    if event.delta:
                        if pending_phase_indicator:
                            chunk = ChatCompletionChunk(
                                id=chunk_id,
                                created=created,
                                model=model,
                                choices=[
                                    StreamChoice(
                                        delta=ChoiceDelta(content="\n" + pending_phase_indicator)
                                    )
                                ],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"
                            pending_phase_indicator = None
                        streamed_content += event.delta
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=event.delta))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
                    return

                if event.event_type == StreamEventType.PHASE_START:
                    if show_phase_indicators and event.phase:
                        indicator = _phase_start_indicator_text(event.phase, session_id=session_id)
                        if indicator:
                            chunk = ChatCompletionChunk(
                                id=chunk_id,
                                created=created,
                                model=model,
                                choices=[
                                    StreamChoice(
                                        delta=ChoiceDelta(content="\n" + indicator),
                                    )
                                ],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"
                            pending_phase_indicator = None
                    return

                if event.event_type == StreamEventType.ERROR:
                    error_text = _get_stream_error_text(event.metadata)
                    chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[StreamChoice(delta=ChoiceDelta(content=error_text))],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"
                    return

            async for sse_chunk in _consume_sse_events(
                stream_queue=stream_queue,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                on_timeout=on_timeout,
                on_event=on_event,
            ):
                yield sse_chunk

            # Wait for implementation to complete
            await impl_task

            pending_tool_calls = final_state.get("pending_tool_calls") or []
            if pending_tool_calls:
                session = session_store.load_session(session_id)
                next_round = (getattr(session, "round_index", 0) or 0) + 1
                if next_round > _TOOL_LOOP_MAX_ROUNDS:
                    session_store.update_session(
                        session_id,
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
                            session_id=session_id,
                        ),
                    )
                    message = _tool_loop_failsafe_message(session) if session is not None else ""
                    if message:
                        for i in range(0, len(message), 128):
                            text = message[i : i + 128]
                            if not text:
                                continue
                            chunk = ChatCompletionChunk(
                                id=chunk_id,
                                created=created,
                                model=model,
                                choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"

                    final_chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[StreamChoice(delta=ChoiceDelta(), finish_reason="stop")],
                    )
                    yield f"data: {final_chunk.model_dump_json()}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                workflow_phase = str(
                    final_state.get("current_phase")
                    or getattr(session, "workflow_phase", "execution")
                    or "execution"
                )
                (
                    current_workspace_root,
                    current_local_workspace_root,
                    current_workspace_path_style,
                    current_workspace_root_source,
                ) = _resolve_workspace_fields(session=session)
                filtered_tool_calls = list(pending_tool_calls or [])
                todo_written_now = False
                if workflow_phase in {"execution", "optimizer"} and session is not None:
                    filtered_tool_calls, todo_written_now = _filter_optimizer_todo_write(
                        session,
                        filtered_tool_calls,
                    )
                guardrail_events_to_append: list[dict[str, Any]] = []
                before_cursor_validate = list(filtered_tool_calls)
                filtered_tool_calls, cursor_tools_error = (
                    _normalize_and_validate_tool_calls_against_cursor_tools(
                        workflow_phase=workflow_phase,
                        tool_calls=filtered_tool_calls,
                        cursor_tools=list(getattr(session, "cursor_tools", []) or []),
                    )
                )
                rewrites = _diff_tool_call_name_rewrites(
                    before_cursor_validate, filtered_tool_calls
                )
                if rewrites:
                    guardrail_events_to_append.append(
                        {
                            "type": "tool_call_name_rewrite",
                            "role": "optimizer" if workflow_phase == "optimizer" else "writer",
                            "rewrites": rewrites,
                        }
                    )

                tool_policy_error = cursor_tools_error
                role_label = "optimizer" if workflow_phase == "optimizer" else "writer"
                if tool_policy_error:
                    available = _extract_cursor_tool_names(
                        getattr(session, "cursor_tools", []) or []
                    )
                    available_set = set(available)
                    unknown: list[str] = []
                    for tc in before_cursor_validate:
                        name, _args = _extract_tool_name_and_arguments(tc)
                        if isinstance(name, str) and name and name not in available_set:
                            unknown.append(name)
                    guardrail_events_to_append.append(
                        {
                            "type": "tool_calls_not_in_cursor_tools",
                            "role": role_label,
                            "blocked_tools": sorted(set(unknown)),
                            "error_preview": sanitize_for_preview(
                                redact_secrets(tool_policy_error),
                                max_length=240,
                            ),
                        }
                    )
                else:
                    before_exec_policy = list(filtered_tool_calls)
                    filtered_tool_calls, tool_policy_error = _enforce_execution_tool_policy(
                        workflow_phase=workflow_phase,
                        tool_calls=filtered_tool_calls,
                    )
                    if tool_policy_error:
                        blocked_tools, blocked_shell = _collect_execution_tool_policy_block_details(
                            before_exec_policy
                        )
                        guardrail_events_to_append.append(
                            {
                                "type": "execution_tool_policy_blocked",
                                "role": role_label,
                                "blocked_tools": blocked_tools,
                                "blocked_shell": blocked_shell,
                                "error_preview": sanitize_for_preview(
                                    redact_secrets(tool_policy_error),
                                    max_length=240,
                                ),
                            }
                        )
                if tool_policy_error:
                    if session is not None:
                        session_store.update_session(
                            session_id,
                            stage=SessionStage.AWAITING_CONFIRMATION,
                            confirmation_reason="tool_policy",
                            pending_tool_calls=[],
                            append_guardrail_events=guardrail_events_to_append,
                        )
                    for i in range(0, len(tool_policy_error), 128):
                        text = tool_policy_error[i : i + 128]
                        if not text:
                            continue
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

                    final_chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[StreamChoice(delta=ChoiceDelta(), finish_reason="stop")],
                    )
                    yield f"data: {final_chunk.model_dump_json()}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                before_deliverable_policy = list(filtered_tool_calls)
                filtered_tool_calls, policy_error, deliverable_type, allowed_scope = (
                    _enforce_deliverable_policy(
                        workflow_phase=workflow_phase,
                        tool_calls=filtered_tool_calls,
                        conversation_history=list(
                            final_state.get("conversation_history", [])
                            or getattr(session, "execution_messages", [])
                            or []
                        ),
                        ternion_report=str(
                            final_state.get("ternion_report", "")
                            or getattr(session, "ternion_report_raw", "")
                            or ""
                        ),
                        workspace_root=current_workspace_root,
                        workspace_path_style=current_workspace_path_style,
                        workspace_root_source=current_workspace_root_source,
                    )
                )
                if policy_error:
                    if session is not None:
                        violations = (
                            _collect_deliverable_policy_violations(
                                before_deliverable_policy,
                                deliverable_type,
                                current_workspace_root,
                                current_workspace_path_style,
                                current_workspace_root_source,
                            )
                            if deliverable_type is not None
                            else []
                        )
                        guardrail_events_to_append.append(
                            {
                                "type": "deliverable_policy_blocked",
                                "role": role_label,
                                "deliverable_type": deliverable_type.value
                                if deliverable_type is not None
                                else "",
                                "allowed_scope": allowed_scope or "",
                                "violations": violations,
                                "error_preview": sanitize_for_preview(
                                    redact_secrets(policy_error),
                                    max_length=240,
                                ),
                            }
                        )
                        session_store.update_session(
                            session_id,
                            stage=SessionStage.AWAITING_CONFIRMATION,
                            confirmation_reason="deliverable_policy",
                            pending_tool_calls=[],
                            append_guardrail_events=guardrail_events_to_append,
                        )
                    for i in range(0, len(policy_error), 128):
                        text = policy_error[i : i + 128]
                        if not text:
                            continue
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

                    final_chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[StreamChoice(delta=ChoiceDelta(), finish_reason="stop")],
                    )
                    yield f"data: {final_chunk.model_dump_json()}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                baseline, modified_files = (
                    _ensure_baseline_snapshots_for_tool_calls(
                        session,
                        filtered_tool_calls,
                    )
                    if session is not None
                    else ({}, [])
                )
                rewritten_tool_calls = _rewrite_tool_call_ids(
                    filtered_tool_calls,
                    session_id=session_id,
                    round_index=next_round,
                    workflow_phase=workflow_phase,
                )
                cursor_tool_calls = _strip_internal_tool_call_fields(rewritten_tool_calls)
                execution_messages = (
                    list(getattr(session, "execution_messages", []) or [])
                    if (session is not None)
                    else []
                )
                if not execution_messages:
                    execution_messages = list(
                        final_state.get("conversation_history", [])
                        or initial_state.get("conversation_history", [])
                        or []
                    )
                execution_messages = _append_assistant_tool_call_message(
                    execution_messages,
                    rewritten_tool_calls,
                )
                session_store.update_session(
                    session_id,
                    stage=SessionStage.AWAITING_TOOL_RESULTS,
                    execution_messages=execution_messages,
                    pending_tool_calls=rewritten_tool_calls,
                    round_index=next_round,
                    generated_code=final_state.get("generated_code")
                    or getattr(session, "generated_code", ""),
                    review_feedback=final_state.get("review_feedback")
                    or getattr(session, "review_feedback", ""),
                    revision_count=final_state.get(
                        "revision_count", getattr(session, "revision_count", 0)
                    ),
                    workflow_phase=workflow_phase,
                    tool_loop_pre_git_status=_capture_tool_loop_pre_git_status(
                        rewritten_tool_calls,
                        round_index=next_round,
                        workflow_phase=workflow_phase,
                        workspace_root=current_workspace_root,
                        workspace_path_style=current_workspace_path_style,
                        local_workspace_root=current_local_workspace_root,
                    ),
                    modified_files=modified_files,
                    baseline_file_snapshots=baseline,
                    writer_output_files=dict(
                        final_state.get("writer_output_files")
                        or getattr(session, "writer_output_files", {})
                        or {}
                    ),
                    stabilized_document_paths=list(
                        final_state.get("stabilized_document_paths")
                        or getattr(session, "stabilized_document_paths", [])
                        or []
                    ),
                    optimizer_review_report=str(
                        final_state.get("optimizer_review_report")
                        or getattr(session, "optimizer_review_report", "")
                        or ""
                    ),
                    todo_written=bool(getattr(session, "todo_written", False)) or todo_written_now,
                    optimizer_todo_written=(
                        bool(getattr(session, "optimizer_todo_written", False)) or todo_written_now
                        if workflow_phase == "optimizer"
                        else bool(getattr(session, "optimizer_todo_written", False))
                    ),
                    append_guardrail_events=guardrail_events_to_append,
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
                                tool_calls=cursor_tool_calls,
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

            # If no content was streamed but workflow produced output, send it
            workflow_final = final_state.get("final_output", "") or final_state.get(
                "generated_code", ""
            )
            errors = final_state.get("errors", []) or []
            if workflow_final and not streamed_content:
                if pending_phase_indicator:
                    chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[
                            StreamChoice(delta=ChoiceDelta(content="\n" + pending_phase_indicator))
                        ],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"
                    pending_phase_indicator = None
                for i in range(0, len(workflow_final), 128):
                    text = workflow_final[i : i + 128]
                    chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"

            if errors and not workflow_final and not streamed_content:
                error_backfill = _build_stream_error_backfill(list(errors))
                if pending_phase_indicator:
                    chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[
                            StreamChoice(delta=ChoiceDelta(content="\n" + pending_phase_indicator))
                        ],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"
                    pending_phase_indicator = None
                for i in range(0, len(error_backfill), 128):
                    text = error_backfill[i : i + 128]
                    if not text:
                        continue
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

        except asyncio.CancelledError:
            stream_queue.close()
            impl_task.cancel()
            with contextlib.suppress(BaseException):
                await impl_task
            raise
        except Exception as e:
            logger.exception("sse_impl_generation_error", error=str(e))
            error_chunk = ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=model,
                choices=[
                    StreamChoice(delta=ChoiceDelta(content=t(MessageKey.STREAM_ERROR_INTERRUPTED)))
                ],
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        A simple status dictionary indicating the server is healthy.
    """
    return {"status": "healthy"}


@router.get("/", include_in_schema=False)
async def root_probe(request: Request) -> dict[str, str]:
    """
    Base URL probe endpoint (no /v1 prefix).

    Some clients validate connectivity by probing the base origin before calling
    API paths. Returning 200 helps distinguish "no request sent" vs "wrong path".

    Args:
        request: The incoming FastAPI request.

    Returns:
        A basic status dictionary.
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
    """HEAD variant of `/` for strict clients.

    Args:
        request: The incoming FastAPI request.

    Returns:
        An empty 200 OK Response.
    """
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

    Args:
        request: The incoming FastAPI request.

    Returns:
        A basic status dictionary.
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
    """HEAD variant of `/v1` for strict clients.

    Args:
        request: The incoming FastAPI request.

    Returns:
        An empty 200 OK Response.
    """
    logger.info(
        "api_probe",
        path=str(request.url.path),
        method=request.method,
        user_agent=request.headers.get("user-agent", ""),
    )
    return Response(status_code=200)


@router.get("/v1/", include_in_schema=False)
async def v1_root_slash(request: Request) -> dict[str, str]:
    """Same as `/v1` but avoids redirect_slashes for strict clients.

    Args:
        request: The incoming FastAPI request.

    Returns:
        A basic status dictionary.
    """
    logger.info(
        "api_probe",
        path=str(request.url.path),
        method=request.method,
        user_agent=request.headers.get("user-agent", ""),
    )
    return {"status": "ok"}


@router.head("/v1/", include_in_schema=False)
async def v1_root_slash_head(request: Request) -> Response:
    """HEAD variant of `/v1/` for strict clients.

    Args:
        request: The incoming FastAPI request.

    Returns:
        An empty 200 OK Response.
    """
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
    """List available models (OpenAI-compatible).

    Args:
        request: The incoming FastAPI request.

    Returns:
        A list of models supported by this proxy.
    """
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
    """HEAD variant of `/v1/models` for strict clients.

    Args:
        request: The incoming FastAPI request.

    Returns:
        An empty 200 OK Response.
    """
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
    - ternion-team: Full Ternion multi-phase workflow (evidence → divergence → convergence → execution → review → optimizer)
    - (All other models are rejected to avoid accidental passthrough/BYOK costs)

    Args:
        request: The incoming ChatCompletionRequest.

    Returns:
        A standard Response, or a StreamingResponse if streaming is requested.
    """
    logger.info(
        "chat_completion_request",
        model=request.model,
        message_count=len(request.messages),
        stream=request.stream,
    )

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
        messages_as_dicts.append(
            {
                "role": role,
                "content": msg.content,
                "name": msg.name,
                "tool_calls": msg.tool_calls,
                "tool_call_id": msg.tool_call_id,
            }
        )

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
            workflow_phase = str(getattr(session, "workflow_phase", "") or "").lower()
            if workflow_phase == "report_evidence":
                resume_phase = (
                    str(getattr(session, "report_evidence_resume_phase", "") or "").strip().lower()
                )
                if resume_phase in {"execution", "optimizer"}:
                    return await handle_execution_followup(session, request)
                return await handle_report_evidence_followup(session, request)
            if workflow_phase == "evidence":
                return await handle_evidence_followup(session, request)
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
                hash_status = (
                    f"hash_verified={hash_verified}"
                    if hash_verified is not None
                    else "hash_not_checked"
                )
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
    _apply_workspace_boundary_to_context(context, request.messages)
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
        if (
            not provider_config
            or not provider_config.api_keys
            or not provider_config.selected_key_id
        ):
            missing_roles.append(f"{display_name} ({role_config.provider} not configured)")

    if missing_roles:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "message": t(
                        MessageKey.ROLE_CONFIG_INCOMPLETE, missing_roles=", ".join(missing_roles)
                    ),
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
            message=t(
                MessageKey.LOG_BUDGET_WARNING, usage_pct=str(usage_summary.get("usage_pct", 0))
            ),
        )

    # Run the Ternion discussion workflow
    try:
        from ternion.workflow.graph import run_discussion

        if request.stream:
            return await _run_discussion_streaming(
                context=context,
                model=request.model,
                budget_warning=budget_warning,
                show_phase_indicators=bool(getattr(user_config, "show_phase_indicators", True)),
            )

        # Non-streaming: run workflow and return complete response
        final_state = await run_discussion(context)
        runtime_model_response = _get_runtime_model_unavailable_response_from_state(final_state)
        if runtime_model_response is not None:
            return runtime_model_response
        pending_tool_calls = final_state.get("pending_tool_calls") or []
        if pending_tool_calls:
            turn_outcome = _create_initial_tool_loop_session(
                final_state=final_state,
                context=context,
                pending_tool_calls=pending_tool_calls,
                cursor_tools=list(request.tools or []),
                cursor_tool_choice=request.tool_choice,
            )
            if turn_outcome.blocked:
                return JSONResponse(
                    content=ChatCompletionResponse(
                        model=request.model,
                        choices=[
                            Choice(
                                message=ChatMessage(
                                    role=MessageRole.ASSISTANT,
                                    content=turn_outcome.blocked_message,
                                )
                            )
                        ],
                    ).model_dump()
                )
            return _tool_calls_json_response(request.model, turn_outcome.cursor_tool_calls)

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
            output_parts.append(t(MessageKey.DISCUSSION_NO_OUTPUT))
            if errors:
                output_parts.append("\n\n")
                output_parts.append(t(MessageKey.DISCUSSION_ERRORS_HEADER))
                for err in errors:
                    err_msg = sanitize_for_cursor_display(str(err))
                    if err_msg:
                        output_parts.append(f"- {err_msg}\n")

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
    except RuntimeModelUnavailableError as e:
        return _build_runtime_model_unavailable_response(e.to_payload())
    except Exception as e:
        logger.exception("discussion_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": t(MessageKey.DISCUSSION_WORKFLOW_ERROR, error=str(e)),
                    "type": "workflow_error",
                }
            },
        )


class _SessionTurnLock:
    """
    Per-session turn lock spanning a handler body and its streaming generator.

    Serializes concurrent follow-ups for the same session across the whole
    load -> merge -> workflow -> save turn. For streaming responses the lock
    ownership is handed off to the SSE generator, which releases it in a
    finally block once the stream completes (or the client disconnects).

    Acquisition is bounded: on timeout the turn proceeds without the lock
    (legacy unserialized behavior) instead of deadlocking the session.
    """

    # A legitimate turn can chain multiple provider calls (e.g. a Writer call
    # capped at writer_timeout_seconds=300s plus one soft retry), so the
    # acquire timeout must exceed a single provider timeout to avoid degrading
    # to unlocked mode while a long-but-healthy turn still holds the lock.
    _ACQUIRE_TIMEOUT_SECONDS = 600.0

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._lock = get_session_lock(session_id)
        self._held = False
        self.handed_off = False

    async def acquire(self) -> None:
        """Acquire the session lock, degrading with a warning on timeout."""
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=self._ACQUIRE_TIMEOUT_SECONDS)
            self._held = True
        except TimeoutError:
            logger.warning(
                "session_turn_lock_timeout",
                session_id=self._session_id,
                timeout_seconds=self._ACQUIRE_TIMEOUT_SECONDS,
            )

    def hand_off(self) -> None:
        """Transfer release responsibility to the streaming generator.

        Known edge: if the ASGI server never starts iterating the generator
        after hand-off, the release in its finally block never runs and the
        lock stays held for the process lifetime. No concrete trigger is
        known; the bounded acquire timeout keeps this a delay (subsequent
        turns degrade to unlocked mode) rather than a deadlock.
        """
        self.handed_off = True

    def release(self) -> None:
        """Release the session lock if held (idempotent)."""
        if self._held:
            self._held = False
            self._lock.release()


@dataclass
class _FollowupTurnSetup:
    """Shared per-turn preparation state for tool-loop follow-up handlers."""

    cursor_tools: list[dict[str, Any]]
    cursor_tool_choice: Any
    context: TernionContext
    workspace_root: str
    local_workspace_root: str
    workspace_path_style: str
    workspace_root_source: str
    cursor_system_prompt: str


def _prepare_followup_turn(
    session: Session,
    request: ChatCompletionRequest,
) -> _FollowupTurnSetup:
    """
    Resolve the shared request-scoped state for a follow-up turn.

    Refreshes tool definitions from the request when present, applies the
    client workspace boundary, and prefers the freshest Cursor system prompt.

    Args:
        session: The tool-loop session being resumed.
        request: The incoming follow-up request.

    Returns:
        The prepared turn setup consumed by all follow-up handlers.
    """
    cursor_tools = list(request.tools or []) or list(session.cursor_tools or [])
    cursor_tool_choice = (
        request.tool_choice if request.tool_choice is not None else session.cursor_tool_choice
    )

    context = message_router.extract_context(request.messages)
    _apply_workspace_boundary_to_context(context, request.messages, session=session)
    (
        workspace_root,
        local_workspace_root,
        workspace_path_style,
        workspace_root_source,
    ) = _resolve_workspace_fields(context=context, session=session)
    cursor_system_prompt = session.cursor_system_prompt
    if context.cursor_system_prompt and isinstance(context.cursor_system_prompt.content, str):
        cursor_system_prompt = context.cursor_system_prompt.content

    return _FollowupTurnSetup(
        cursor_tools=cursor_tools,
        cursor_tool_choice=cursor_tool_choice,
        context=context,
        workspace_root=workspace_root,
        local_workspace_root=local_workspace_root,
        workspace_path_style=workspace_path_style,
        workspace_root_source=workspace_root_source,
        cursor_system_prompt=cursor_system_prompt,
    )


def _merge_incoming_tool_results(
    session: Session,
    request_messages: list[ChatMessage],
    *,
    process_result: Callable[[ChatMessage, str], str] | None = None,
) -> list[dict[str, Any]]:
    """
    Merge new tool-result messages from a follow-up request into history.

    Skips non-tool messages, already-merged results, and results whose
    tool_call_id belongs to a different session. Each accepted result is
    appended as a {"role": "tool", ...} message.

    Args:
        session: The session whose execution history is extended.
        request_messages: Incoming request messages to scan.
        process_result: Optional hook receiving (message, raw_content) and
            returning the content to persist; defaults to the raw content.
            Used by the execution handler for compaction and side-effect
            tracking without duplicating the merge skeleton.

    Returns:
        The extended execution message list (a copy; session is untouched).
    """
    updated_execution_messages = list(session.execution_messages or [])
    existing_tool_ids = {
        m.get("tool_call_id")
        for m in (session.execution_messages or [])
        if isinstance(m, dict)
        and m.get("role") == "tool"
        and isinstance(m.get("tool_call_id"), str)
    }
    for tool_result_msg in request_messages:
        if tool_result_msg.role != MessageRole.TOOL:
            continue
        if not isinstance(tool_result_msg.tool_call_id, str):
            continue
        if tool_result_msg.tool_call_id in existing_tool_ids:
            continue
        match = _TERNION_TOOL_CALL_ID_SESSION_RE.search(tool_result_msg.tool_call_id)
        if not match or match.group(1).lower() != session.session_id.lower():
            continue
        raw_content = (
            tool_result_msg.content
            if isinstance(tool_result_msg.content, str)
            else str(tool_result_msg.content)
        )
        content = (
            process_result(tool_result_msg, raw_content)
            if process_result is not None
            else raw_content
        )
        updated_execution_messages.append(
            {
                "role": "tool",
                "content": content,
                "tool_call_id": tool_result_msg.tool_call_id,
            }
        )
        existing_tool_ids.add(tool_result_msg.tool_call_id)
    return updated_execution_messages


def _check_followup_budget(
    session: Session,
    request: ChatCompletionRequest,
) -> Response | None:
    """
    Apply the budget gate for a follow-up turn.

    Callers that must bypass the whole gate (e.g. the execution follow-up
    resuming right after a user confirmed the budget warning) skip calling
    this function entirely instead of passing a flag: both the hard-exceeded
    block and the warning-level confirmation are suppressed in that case.

    Args:
        session: The session paused when the budget gate triggers.
        request: The incoming request (used for response formatting).

    Returns:
        A gate response to return immediately, or None to continue.
    """
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
    return None


def _resolve_followup_execution_mode(request: ChatCompletionRequest) -> tuple[Any, bool]:
    """
    Resolve the effective execution mode and confirmation gate for a follow-up.

    Applies the Cursor Agent auto-switch (cursor_handoff -> ternion_full) and
    persists the promoted mode, matching the initial-request behavior.

    Args:
        request: The incoming follow-up request.

    Returns:
        Tuple of (user_config, await_confirmation).
    """
    user_config = config_store.load()
    is_agent_request = _is_cursor_agent_request(request)
    await_confirmation = user_config.execution_mode != "ternion_full"
    if not is_agent_request:
        await_confirmation = True
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
        await_confirmation = False
    return user_config, await_confirmation


def _build_followup_conversation_history(
    execution_messages: list[dict[str, Any]],
) -> list[ChatMessage]:
    """
    Rebuild ChatMessage history from persisted execution messages.

    Args:
        execution_messages: Persisted OpenAI-style message dicts.

    Returns:
        ChatMessage list preserving tool_calls / tool_call_id replay fields.
    """
    conversation_history: list[ChatMessage] = []
    for execution_msg in execution_messages:
        role_value = execution_msg.get("role")
        if not isinstance(role_value, str):
            continue
        try:
            role = MessageRole(role_value)
        except ValueError:
            continue
        conversation_history.append(
            ChatMessage(
                role=role,
                content=execution_msg.get("content"),
                name=execution_msg.get("name"),
                tool_calls=execution_msg.get("tool_calls"),
                tool_call_id=execution_msg.get("tool_call_id"),
            )
        )
    return conversation_history


def _log_followup_history_diagnostics(
    session_id: str,
    execution_messages: list[dict[str, Any]],
    *,
    label: str,
) -> None:
    """
    Emit tool_call_id mismatch diagnostics for a follow-up history.

    Args:
        session_id: The session identifier for log correlation.
        execution_messages: The merged execution message history.
        label: Handler label prefix (e.g. "evidence_followup").
    """
    assistant_with_tools_count = sum(
        1
        for m in execution_messages
        if m.get("role") == "assistant"
        and isinstance(m.get("tool_calls"), list)
        and m.get("tool_calls")
    )
    tool_msg_count = sum(1 for m in execution_messages if m.get("role") == "tool")
    if tool_msg_count <= 0:
        return
    log_manager.emit(
        level="DEBUG" if assistant_with_tools_count > 0 else "WARN",
        category="WORKFLOW",
        message=(
            f"{label}_history | "
            f"session_id={session_id} | "
            f"execution_msgs_len={len(execution_messages)} | "
            f"assistant_with_tools={assistant_with_tools_count} | "
            f"tool_msgs={tool_msg_count}"
        ),
    )
    if assistant_with_tools_count == 0:
        logger.warning(
            f"{label}_missing_assistant_tool_calls",
            session_id=session_id,
            execution_msgs_len=len(execution_messages),
            tool_msg_count=tool_msg_count,
            msg_roles=[m.get("role") for m in execution_messages],
            assistant_tool_calls=[
                bool(m.get("tool_calls"))
                for m in execution_messages
                if m.get("role") == "assistant"
            ],
        )


@dataclass
class _PendingToolCallsTurn:
    """Outcome of preparing a pending-tool-calls turn for the client."""

    blocked: bool = False
    blocked_message: str = ""
    cursor_tool_calls: list[dict[str, Any]] = dc_field(default_factory=list)


def _prepare_evidence_pending_tool_calls_turn(
    *,
    session: Session,
    final_state: dict[str, Any],
    pending_tool_calls: list[dict[str, Any]],
    workflow_phase: str,
    updated_execution_messages: list[dict[str, Any]],
    cursor_system_prompt: str,
    cursor_tools: list[dict[str, Any]],
    cursor_tool_choice: Any,
    include_topup_state: bool,
) -> _PendingToolCallsTurn:
    """
    Run guardrails, persist the turn, and prepare tool calls for the client.

    Shared by the evidence and report-evidence follow-up handlers (streaming
    and non-streaming): failsafe round limit, tool/deliverable policy checks,
    baseline capture, tool_call_id rewrite, and session persistence happen in
    one place so all four call sites stay behaviorally identical.

    Args:
        session: The session driving this tool loop.
        final_state: Final workflow state carrying pending tool calls.
        pending_tool_calls: Tool calls produced by the workflow segment.
        workflow_phase: The phase to persist and encode in tool_call ids.
        updated_execution_messages: History including newly merged results.
        cursor_system_prompt: Latest Cursor system prompt to persist.
        cursor_tools: Latest Cursor tools schema to persist.
        cursor_tool_choice: Latest Cursor tool_choice payload to persist.
        include_topup_state: When True, evidence top-up round and resume
            phase are resolved from final_state/session and persisted
            (report-evidence semantics); when False they are left untouched.

    Returns:
        The turn outcome: either a blocked guardrail message or the
        client-facing tool calls after successful persistence.
    """
    current_session = session_store.load_session(session.session_id)
    next_round = (getattr(current_session, "round_index", 0) or 0) + 1
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
        message = (
            _tool_loop_failsafe_message(current_session) if current_session is not None else ""
        )
        return _PendingToolCallsTurn(blocked=True, blocked_message=message)

    filtered_tool_calls = list(pending_tool_calls or [])
    todo_written_now = False
    if workflow_phase in {"execution", "optimizer"} and current_session is not None:
        filtered_tool_calls, todo_written_now = _filter_optimizer_todo_write(
            current_session,
            filtered_tool_calls,
        )
    filtered_tool_calls, tool_policy_error = (
        _normalize_and_validate_tool_calls_against_cursor_tools(
            workflow_phase=workflow_phase,
            tool_calls=filtered_tool_calls,
            cursor_tools=list(getattr(current_session, "cursor_tools", []) or []),
        )
    )
    if not tool_policy_error:
        filtered_tool_calls, tool_policy_error = _enforce_execution_tool_policy(
            workflow_phase=workflow_phase,
            tool_calls=filtered_tool_calls,
        )
    if tool_policy_error:
        if current_session is not None:
            session_store.update_session(
                session.session_id,
                stage=SessionStage.AWAITING_CONFIRMATION,
                confirmation_reason="tool_policy",
                pending_tool_calls=[],
            )
        return _PendingToolCallsTurn(blocked=True, blocked_message=tool_policy_error)

    (
        current_workspace_root,
        current_local_workspace_root,
        current_workspace_path_style,
        current_workspace_root_source,
    ) = _resolve_workspace_fields(session=current_session or session)
    filtered_tool_calls, policy_error, _, _ = _enforce_deliverable_policy(
        workflow_phase=workflow_phase,
        tool_calls=filtered_tool_calls,
        conversation_history=list(final_state.get("conversation_history", []) or []),
        ternion_report=str(
            final_state.get("ternion_report", "")
            or getattr(session, "ternion_report_raw", "")
            or ""
        ),
        workspace_root=current_workspace_root,
        workspace_path_style=current_workspace_path_style,
        workspace_root_source=current_workspace_root_source,
    )
    if policy_error:
        if current_session is not None:
            session_store.update_session(
                session.session_id,
                stage=SessionStage.AWAITING_CONFIRMATION,
                confirmation_reason="deliverable_policy",
                pending_tool_calls=[],
            )
        return _PendingToolCallsTurn(blocked=True, blocked_message=policy_error)

    baseline: dict[str, str] = {}
    modified_files: list[str] = []
    if current_session is not None:
        baseline, modified_files = _ensure_baseline_snapshots_for_tool_calls(
            current_session,
            filtered_tool_calls,
        )

    rewritten_tool_calls = _rewrite_tool_call_ids(
        filtered_tool_calls,
        session_id=session.session_id,
        round_index=next_round,
        workflow_phase=workflow_phase,
    )
    cursor_tool_calls = _strip_internal_tool_call_fields(rewritten_tool_calls)
    execution_messages = _append_assistant_tool_call_message(
        updated_execution_messages,
        rewritten_tool_calls,
    )
    optimizer_todo_written = todo_written_now
    if current_session is not None:
        optimizer_todo_written = (
            bool(getattr(current_session, "optimizer_todo_written", False)) or todo_written_now
            if workflow_phase == "optimizer"
            else bool(getattr(current_session, "optimizer_todo_written", False))
        )

    topup_kwargs: dict[str, Any] = {}
    if include_topup_state:
        resume_meta_source = current_session if current_session is not None else session
        topup_round_value = final_state.get("evidence_topup_round")
        try:
            evidence_topup_round = int(topup_round_value) if topup_round_value is not None else 0
        except Exception:
            evidence_topup_round = 0
        if evidence_topup_round <= 0:
            evidence_topup_round = int(getattr(resume_meta_source, "evidence_topup_round", 0) or 0)

        resume_phase = str(final_state.get("report_evidence_resume_phase") or "").strip()
        if not resume_phase:
            resume_phase = str(
                getattr(resume_meta_source, "report_evidence_resume_phase", "") or ""
            ).strip()
        topup_kwargs["evidence_topup_round"] = int(evidence_topup_round or 0)
        topup_kwargs["report_evidence_resume_phase"] = str(resume_phase or "")

    session_store.update_session(
        session.session_id,
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        cursor_system_prompt=cursor_system_prompt,
        cursor_tools=list(cursor_tools or []),
        cursor_tool_choice=cursor_tool_choice,
        execution_messages=execution_messages,
        pending_tool_calls=rewritten_tool_calls,
        round_index=next_round,
        workflow_phase=workflow_phase,
        tool_loop_pre_git_status=_capture_tool_loop_pre_git_status(
            rewritten_tool_calls,
            round_index=next_round,
            workflow_phase=workflow_phase,
            workspace_root=current_workspace_root,
            workspace_path_style=current_workspace_path_style,
            local_workspace_root=current_local_workspace_root,
        ),
        modified_files=modified_files,
        baseline_file_snapshots=baseline,
        todo_written=bool(getattr(current_session, "todo_written", False)) or todo_written_now,
        optimizer_todo_written=optimizer_todo_written,
        evidence_bundle=str(
            final_state.get("evidence_bundle") or getattr(session, "evidence_bundle", "") or ""
        ),
        evidence_gaps=str(
            final_state.get("evidence_gaps") or getattr(session, "evidence_gaps", "") or ""
        ),
        evidence_requests=str(
            final_state.get("evidence_requests") or getattr(session, "evidence_requests", "") or ""
        ),
        evidence_chain_index=list(
            final_state.get("evidence_chain_index")
            or getattr(session, "evidence_chain_index", [])
            or []
        ),
        ternion_analyses=list(
            final_state.get("ternion_analyses") or getattr(session, "ternion_analyses", []) or []
        ),
        **topup_kwargs,
    )
    return _PendingToolCallsTurn(cursor_tool_calls=cursor_tool_calls)


def _sse_text_stop_chunks(
    chunk_id: str,
    created: int,
    model: str,
    text: str,
) -> Iterable[str]:
    """
    Yield SSE chunks for a plain-text message followed by a stop finish.

    Args:
        chunk_id: The chat completion chunk identifier.
        created: The chunk creation timestamp.
        model: The model name echoed in each chunk.
        text: Text to stream in 128-character slices (may be empty).

    Yields:
        Serialized SSE data lines including the final [DONE] marker.
    """
    for i in range(0, len(text), 128):
        piece = text[i : i + 128]
        if not piece:
            continue
        chunk = ChatCompletionChunk(
            id=chunk_id,
            created=created,
            model=model,
            choices=[StreamChoice(delta=ChoiceDelta(content=piece))],
        )
        yield f"data: {chunk.model_dump_json()}\n\n"
    final_chunk = ChatCompletionChunk(
        id=chunk_id,
        created=created,
        model=model,
        choices=[StreamChoice(delta=ChoiceDelta(), finish_reason="stop")],
    )
    yield f"data: {final_chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"


def _sse_tool_calls_chunks(
    chunk_id: str,
    created: int,
    model: str,
    cursor_tool_calls: list[dict[str, Any]],
) -> Iterable[str]:
    """
    Yield the one-shot SSE chunks carrying tool calls for the client.

    Args:
        chunk_id: The chat completion chunk identifier.
        created: The chunk creation timestamp.
        model: The model name echoed in each chunk.
        cursor_tool_calls: Client-facing tool call payloads.

    Yields:
        Serialized SSE data lines including the final [DONE] marker.
    """
    tool_chunk = ChatCompletionChunk(
        id=chunk_id,
        created=created,
        model=model,
        choices=[
            StreamChoice(
                delta=ChoiceDelta(
                    role="assistant",
                    content=None,
                    tool_calls=cursor_tool_calls,
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


def _tool_calls_json_response(
    model: str,
    cursor_tool_calls: list[dict[str, Any]],
) -> JSONResponse:
    """
    Build the non-streaming JSON response carrying tool calls.

    Args:
        model: The model name echoed in the response.
        cursor_tool_calls: Client-facing tool call payloads.

    Returns:
        An OpenAI-compatible chat completion response with tool calls.
    """
    return JSONResponse(
        content=ChatCompletionResponse(
            model=model,
            choices=[
                Choice(
                    finish_reason="tool_calls",
                    message=ChatMessage(
                        role=MessageRole.ASSISTANT,
                        content=None,
                        tool_calls=cursor_tool_calls,
                    ),
                )
            ],
        ).model_dump()
    )


@dataclass
class _ExecutionGuardrailOutcome:
    """Result of the shared execution-stage guardrail chain."""

    filtered_tool_calls: list[dict[str, Any]]
    guardrail_events: list[dict[str, Any]]
    blocked_message: str | None = None
    confirmation_reason: str = ""


def _run_execution_guardrail_chain(
    *,
    workflow_phase: str,
    tool_calls: list[dict[str, Any]],
    cursor_tools: list[dict[str, Any]],
    conversation_history: list[Any],
    ternion_report: str,
    workspace_root: str,
    workspace_path_style: str,
    workspace_root_source: str,
) -> _ExecutionGuardrailOutcome:
    """
    Run the execution-stage tool-call guardrail chain with audit events.

    Applies (in order) cursor-tools name validation, execution tool policy,
    and deliverable policy, accumulating a guardrail audit event on each
    block. Shared by the execution follow-up and the initial-request tool-loop
    helpers so their guardrail behavior and audit trail stay identical; the two
    call sites differ only in the inputs they pass (cursor tools source and the
    deliverable-policy conversation/report fallbacks), which are parameters
    here. Persistence of the block is left to the caller.

    Args:
        workflow_phase: The phase (used for role labeling and policy scope).
        tool_calls: Tool calls after any todo filtering.
        cursor_tools: Cursor tools schema to validate against.
        conversation_history: History passed to the deliverable policy.
        ternion_report: Report text passed to the deliverable policy.
        workspace_root: Client-declared workspace root.
        workspace_path_style: Path style of the client workspace.
        workspace_root_source: Provenance of the workspace root.

    Returns:
        The guardrail outcome: filtered tool calls plus the audit events, and
        (when blocked) a client-facing message with its confirmation reason.
    """
    guardrail_events: list[dict[str, Any]] = []
    role_label = "optimizer" if workflow_phase == "optimizer" else "writer"

    before_cursor_validate = list(tool_calls)
    filtered_tool_calls, cursor_tools_error = (
        _normalize_and_validate_tool_calls_against_cursor_tools(
            workflow_phase=workflow_phase,
            tool_calls=list(tool_calls),
            cursor_tools=list(cursor_tools or []),
        )
    )
    rewrites = _diff_tool_call_name_rewrites(before_cursor_validate, filtered_tool_calls)
    if rewrites:
        guardrail_events.append(
            {
                "type": "tool_call_name_rewrite",
                "role": role_label,
                "rewrites": rewrites,
            }
        )

    tool_policy_error = cursor_tools_error
    if tool_policy_error:
        available_set = set(_extract_cursor_tool_names(cursor_tools))
        unknown_tool_names: list[str] = []
        for tc in before_cursor_validate:
            name, _args = _extract_tool_name_and_arguments(tc)
            if isinstance(name, str) and name and name not in available_set:
                unknown_tool_names.append(name)
        guardrail_events.append(
            {
                "type": "tool_calls_not_in_cursor_tools",
                "role": role_label,
                "blocked_tools": sorted(set(unknown_tool_names)),
                "error_preview": sanitize_for_preview(
                    redact_secrets(tool_policy_error),
                    max_length=240,
                ),
            }
        )
    else:
        before_exec_policy = list(filtered_tool_calls)
        filtered_tool_calls, tool_policy_error = _enforce_execution_tool_policy(
            workflow_phase=workflow_phase,
            tool_calls=filtered_tool_calls,
        )
        if tool_policy_error:
            blocked_tools, blocked_shell = _collect_execution_tool_policy_block_details(
                before_exec_policy
            )
            guardrail_events.append(
                {
                    "type": "execution_tool_policy_blocked",
                    "role": role_label,
                    "blocked_tools": blocked_tools,
                    "blocked_shell": blocked_shell,
                    "error_preview": sanitize_for_preview(
                        redact_secrets(tool_policy_error),
                        max_length=240,
                    ),
                }
            )
    if tool_policy_error:
        return _ExecutionGuardrailOutcome(
            filtered_tool_calls=filtered_tool_calls,
            guardrail_events=guardrail_events,
            blocked_message=tool_policy_error,
            confirmation_reason="tool_policy",
        )

    before_deliverable_policy = list(filtered_tool_calls)
    filtered_tool_calls, policy_error, deliverable_type, allowed_scope = (
        _enforce_deliverable_policy(
            workflow_phase=workflow_phase,
            tool_calls=filtered_tool_calls,
            conversation_history=conversation_history,
            ternion_report=ternion_report,
            workspace_root=workspace_root,
            workspace_path_style=workspace_path_style,
            workspace_root_source=workspace_root_source,
        )
    )
    if policy_error:
        violations = (
            _collect_deliverable_policy_violations(
                before_deliverable_policy,
                deliverable_type,
                workspace_root,
                workspace_path_style,
                workspace_root_source,
            )
            if deliverable_type is not None
            else []
        )
        guardrail_events.append(
            {
                "type": "deliverable_policy_blocked",
                "role": role_label,
                "deliverable_type": deliverable_type.value if deliverable_type is not None else "",
                "allowed_scope": allowed_scope or "",
                "violations": violations,
                "error_preview": sanitize_for_preview(
                    redact_secrets(policy_error),
                    max_length=240,
                ),
            }
        )
        return _ExecutionGuardrailOutcome(
            filtered_tool_calls=filtered_tool_calls,
            guardrail_events=guardrail_events,
            blocked_message=policy_error,
            confirmation_reason="deliverable_policy",
        )

    return _ExecutionGuardrailOutcome(
        filtered_tool_calls=filtered_tool_calls,
        guardrail_events=guardrail_events,
    )


def _prepare_execution_pending_tool_calls_turn(
    *,
    session: Session,
    final_state: dict[str, Any],
    pending_tool_calls: list[dict[str, Any]],
    updated_execution_messages: list[dict[str, Any]],
    cursor_tools: list[dict[str, Any]],
    workspace_root: str,
    workspace_path_style: str,
    workspace_root_source: str,
    local_workspace_root: str,
) -> _PendingToolCallsTurn:
    """
    Run execution-stage guardrails, persist the turn, and prepare tool calls.

    Shared by the streaming and non-streaming paths of the execution
    follow-up handler. Compared to the evidence variant this records
    guardrail audit events, applies transparent batching, and persists the
    execution-specific session fields (writer outputs, stabilized documents,
    evidence top-up state).

    Args:
        session: The session driving this tool loop (already merged).
        final_state: Final workflow state carrying pending tool calls.
        pending_tool_calls: Tool calls produced by the workflow segment.
        updated_execution_messages: History including newly merged results.
        cursor_tools: Latest Cursor tools schema for validation.
        workspace_root: Client-declared workspace root.
        workspace_path_style: Path style of the client workspace.
        workspace_root_source: Provenance of the workspace root.
        local_workspace_root: Server-local workspace root when accessible.

    Returns:
        The turn outcome: either a blocked guardrail message or the
        client-facing tool calls after successful persistence.
    """
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
        return _PendingToolCallsTurn(
            blocked=True,
            blocked_message=_tool_loop_failsafe_message(session),
        )

    workflow_phase = str(
        final_state.get("current_phase")
        or getattr(session, "workflow_phase", "execution")
        or "execution"
    )
    filtered_tool_calls = list(pending_tool_calls or [])
    todo_written_now = False
    if workflow_phase in {"execution", "optimizer"}:
        filtered_tool_calls, todo_written_now = _filter_optimizer_todo_write(
            session,
            filtered_tool_calls,
        )
    guardrail = _run_execution_guardrail_chain(
        workflow_phase=workflow_phase,
        tool_calls=filtered_tool_calls,
        cursor_tools=list(cursor_tools or []),
        conversation_history=list(
            final_state.get("conversation_history", [])
            or getattr(session, "execution_messages", [])
            or []
        ),
        ternion_report=str(
            final_state.get("ternion_report", "")
            or getattr(session, "ternion_report_raw", "")
            or ""
        ),
        workspace_root=workspace_root,
        workspace_path_style=workspace_path_style,
        workspace_root_source=workspace_root_source,
    )
    filtered_tool_calls = guardrail.filtered_tool_calls
    guardrail_events_to_append = guardrail.guardrail_events
    if guardrail.blocked_message is not None:
        session_store.update_session(
            session.session_id,
            stage=SessionStage.AWAITING_CONFIRMATION,
            confirmation_reason=guardrail.confirmation_reason,
            pending_tool_calls=[],
            append_guardrail_events=guardrail_events_to_append,
        )
        return _PendingToolCallsTurn(blocked=True, blocked_message=guardrail.blocked_message)

    deferred_tool_calls: list[dict] = []
    if workflow_phase in {"execution", "optimizer"}:
        filtered_tool_calls, deferred_tool_calls = _split_tool_calls_for_transparent_batching(
            filtered_tool_calls
        )
    baseline, modified_files = _ensure_baseline_snapshots_for_tool_calls(
        session,
        filtered_tool_calls,
    )
    rewritten_tool_calls = _rewrite_tool_call_ids(
        filtered_tool_calls,
        session_id=session.session_id,
        round_index=next_round,
        workflow_phase=workflow_phase,
    )
    cursor_tool_calls = _strip_internal_tool_call_fields(rewritten_tool_calls)
    execution_messages = _append_assistant_tool_call_message(
        updated_execution_messages,
        rewritten_tool_calls,
    )
    session_store.update_session(
        session.session_id,
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_messages=execution_messages,
        pending_tool_calls=rewritten_tool_calls,
        deferred_tool_calls=deferred_tool_calls,
        round_index=next_round,
        generated_code=final_state.get("generated_code") or session.generated_code,
        review_feedback=final_state.get("review_feedback") or session.review_feedback,
        revision_count=final_state.get("revision_count", session.revision_count),
        workflow_phase=workflow_phase,
        tool_loop_pre_git_status=_capture_tool_loop_pre_git_status(
            rewritten_tool_calls,
            round_index=next_round,
            workflow_phase=workflow_phase,
            workspace_root=workspace_root,
            workspace_path_style=workspace_path_style,
            local_workspace_root=local_workspace_root,
        ),
        modified_files=modified_files,
        baseline_file_snapshots=baseline,
        writer_output_files=dict(
            final_state.get("writer_output_files")
            or getattr(session, "writer_output_files", {})
            or {}
        ),
        stabilized_document_paths=list(
            final_state.get("stabilized_document_paths")
            or getattr(session, "stabilized_document_paths", [])
            or []
        ),
        optimizer_review_report=str(
            final_state.get("optimizer_review_report")
            or getattr(session, "optimizer_review_report", "")
            or ""
        ),
        evidence_bundle=str(
            final_state.get("evidence_bundle") or getattr(session, "evidence_bundle", "") or ""
        ),
        evidence_gaps=str(
            final_state.get("evidence_gaps") or getattr(session, "evidence_gaps", "") or ""
        ),
        evidence_requests=str(
            final_state.get("evidence_requests") or getattr(session, "evidence_requests", "") or ""
        ),
        evidence_chain_index=list(
            final_state.get("evidence_chain_index")
            or getattr(session, "evidence_chain_index", [])
            or []
        ),
        evidence_topup_round=int(
            final_state.get("evidence_topup_round", getattr(session, "evidence_topup_round", 0))
            or 0
        ),
        report_evidence_resume_phase=str(
            final_state.get("report_evidence_resume_phase")
            or getattr(session, "report_evidence_resume_phase", "")
            or ""
        ),
        todo_written=bool(getattr(session, "todo_written", False)) or todo_written_now,
        optimizer_todo_written=(
            bool(getattr(session, "optimizer_todo_written", False)) or todo_written_now
            if workflow_phase == "optimizer"
            else bool(getattr(session, "optimizer_todo_written", False))
        ),
        append_guardrail_events=guardrail_events_to_append,
    )
    return _PendingToolCallsTurn(cursor_tool_calls=cursor_tool_calls)


def _create_initial_tool_loop_session(
    *,
    final_state: dict[str, Any],
    context: TernionContext,
    pending_tool_calls: list[dict[str, Any]],
    cursor_tools: list[dict[str, Any]],
    cursor_tool_choice: Any,
) -> _PendingToolCallsTurn:
    """
    Create the execution session for an initial request entering a tool loop.

    Shared by the streaming and non-streaming initial-request paths: session
    creation, guardrail checks with audit events, transparent batching,
    baseline capture, tool_call_id rewrite (round 1), and persistence happen
    in one place so both call sites stay behaviorally identical.

    Args:
        final_state: Final workflow state carrying pending tool calls.
        context: The request context (workspace fields, system prompt).
        pending_tool_calls: Tool calls produced by the workflow.
        cursor_tools: Cursor tools schema to persist on the new session.
        cursor_tool_choice: Cursor tool_choice payload to persist.

    Returns:
        The turn outcome: either a blocked guardrail message or the
        client-facing tool calls after successful persistence.
    """
    cursor_prompt = (
        context.cursor_system_prompt.content
        if (context.cursor_system_prompt and isinstance(context.cursor_system_prompt.content, str))
        else ""
    )
    workflow_phase = str(final_state.get("current_phase") or "execution")
    (
        workspace_root,
        local_workspace_root,
        workspace_path_style,
        workspace_root_source,
    ) = _resolve_workspace_fields(state=final_state, context=context)
    session = session_store.create_session(
        ternion_report=final_state.get("ternion_report", "") or "",
        execution_mode=ExecutionMode.TERNION_FULL,
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        cursor_system_prompt=cursor_prompt,
        cursor_tools=list(cursor_tools or []),
        cursor_tool_choice=cursor_tool_choice,
        workspace_root=workspace_root,
        local_workspace_root=local_workspace_root,
        workspace_path_style=workspace_path_style,
        workspace_root_source=workspace_root_source,
        execution_messages=list(final_state.get("conversation_history", []) or []),
        workflow_phase=workflow_phase,
        execution_phase_announced=False,
        # Phase 1.5 evidence state (required for report_evidence follow-ups)
        evidence_bundle=str(final_state.get("evidence_bundle", "") or ""),
        evidence_gaps=str(final_state.get("evidence_gaps", "") or ""),
        evidence_requests=str(final_state.get("evidence_requests", "") or ""),
        evidence_chain_index=list(final_state.get("evidence_chain_index", []) or []),
        writer_output_files=dict(final_state.get("writer_output_files", {}) or {}),
        stabilized_document_paths=list(final_state.get("stabilized_document_paths", []) or []),
        evidence_topup_round=int(final_state.get("evidence_topup_round", 0) or 0),
        report_evidence_resume_phase=str(final_state.get("report_evidence_resume_phase", "") or ""),
        ternion_analyses=list(final_state.get("ternion_analyses", []) or []),
    )
    filtered_tool_calls = list(pending_tool_calls or [])
    todo_written_now = False
    if workflow_phase in {"execution", "optimizer"}:
        filtered_tool_calls, todo_written_now = _filter_optimizer_todo_write(
            session,
            filtered_tool_calls,
        )
    guardrail = _run_execution_guardrail_chain(
        workflow_phase=workflow_phase,
        tool_calls=filtered_tool_calls,
        cursor_tools=list(getattr(session, "cursor_tools", []) or []),
        conversation_history=list(final_state.get("conversation_history", []) or []),
        ternion_report=str(final_state.get("ternion_report", "") or ""),
        workspace_root=workspace_root,
        workspace_path_style=workspace_path_style,
        workspace_root_source=workspace_root_source,
    )
    filtered_tool_calls = guardrail.filtered_tool_calls
    guardrail_events_to_append = guardrail.guardrail_events
    if guardrail.blocked_message is not None:
        session_store.update_session(
            session.session_id,
            stage=SessionStage.AWAITING_CONFIRMATION,
            confirmation_reason=guardrail.confirmation_reason,
            pending_tool_calls=[],
            append_guardrail_events=guardrail_events_to_append,
        )
        return _PendingToolCallsTurn(blocked=True, blocked_message=guardrail.blocked_message)

    deferred_tool_calls: list[dict] = []
    if workflow_phase in {"execution", "optimizer"}:
        filtered_tool_calls, deferred_tool_calls = _split_tool_calls_for_transparent_batching(
            filtered_tool_calls
        )
    baseline, modified_files = _ensure_baseline_snapshots_for_tool_calls(
        session,
        filtered_tool_calls,
    )
    rewritten_tool_calls = _rewrite_tool_call_ids(
        filtered_tool_calls,
        session_id=session.session_id,
        round_index=1,
        workflow_phase=workflow_phase,
    )
    cursor_tool_calls = _strip_internal_tool_call_fields(rewritten_tool_calls)
    execution_messages = _append_assistant_tool_call_message(
        session.execution_messages,
        rewritten_tool_calls,
    )
    session_store.update_session(
        session.session_id,
        execution_messages=execution_messages,
        pending_tool_calls=rewritten_tool_calls,
        deferred_tool_calls=deferred_tool_calls,
        round_index=1,
        workflow_phase=workflow_phase,
        tool_loop_pre_git_status=_capture_tool_loop_pre_git_status(
            rewritten_tool_calls,
            round_index=1,
            workflow_phase=workflow_phase,
            workspace_root=workspace_root,
            workspace_path_style=workspace_path_style,
            local_workspace_root=local_workspace_root,
        ),
        modified_files=modified_files,
        baseline_file_snapshots=baseline,
        todo_written=bool(getattr(session, "todo_written", False)) or todo_written_now,
        optimizer_todo_written=(
            bool(getattr(session, "optimizer_todo_written", False)) or todo_written_now
            if workflow_phase == "optimizer"
            else bool(getattr(session, "optimizer_todo_written", False))
        ),
        append_guardrail_events=guardrail_events_to_append,
    )
    return _PendingToolCallsTurn(cursor_tool_calls=cursor_tool_calls)


async def handle_report_evidence_followup(
    session: Session,
    request: ChatCompletionRequest,
) -> Response:
    """
    Handle Phase 1.5 (Report Evidence) follow-ups for Cursor Agent tool loops.

    This branch is identified via tool_call_id and workflow_phase == "report_evidence".
    It uses resume_report_evidence to preserve Phase 0/1 evidence state.

    The whole turn runs under the per-session lock; for streaming responses
    the lock is handed off to the SSE generator.
    """
    turn_lock = _SessionTurnLock(session.session_id)
    await turn_lock.acquire()
    try:
        return await _report_evidence_followup_turn(session, request, turn_lock)
    finally:
        if not turn_lock.handed_off:
            turn_lock.release()


async def _report_evidence_followup_turn(
    session: Session,
    request: ChatCompletionRequest,
    turn_lock: _SessionTurnLock,
) -> Response:
    """Locked turn body for handle_report_evidence_followup."""
    from ternion.workflow.graph import resume_report_evidence

    turn = _prepare_followup_turn(session, request)
    cursor_tools = turn.cursor_tools
    cursor_tool_choice = turn.cursor_tool_choice
    context = turn.context
    cursor_system_prompt = turn.cursor_system_prompt

    updated_execution_messages = _merge_incoming_tool_results(session, request.messages)

    # Update session for Phase 1.5
    session_store.update_session(
        session.session_id,
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        cursor_system_prompt=cursor_system_prompt,
        cursor_tools=list(cursor_tools or []),
        cursor_tool_choice=cursor_tool_choice,
        workspace_root=context.workspace_root,
        local_workspace_root=context.local_workspace_root,
        workspace_path_style=context.workspace_path_style,
        workspace_root_source=context.workspace_root_source,
        execution_messages=updated_execution_messages,
        pending_tool_calls=[],
        workflow_phase="report_evidence",  # Explicitly Phase 1.5
        # Persist existing evidence state
        evidence_bundle=session.evidence_bundle,
        evidence_gaps=session.evidence_gaps,
        evidence_requests=session.evidence_requests,
        evidence_chain_index=list(getattr(session, "evidence_chain_index", []) or []),
        ternion_analyses=session.ternion_analyses,
    )

    budget_response = _check_followup_budget(session, request)
    if budget_response is not None:
        return budget_response

    user_config, await_confirmation = _resolve_followup_execution_mode(request)

    system_message = (
        ChatMessage(role=MessageRole.SYSTEM, content=cursor_system_prompt)
        if cursor_system_prompt
        else None
    )
    conversation_history = _build_followup_conversation_history(updated_execution_messages)
    _log_followup_history_diagnostics(
        session.session_id,
        updated_execution_messages,
        label="report_evidence_followup",
    )

    evidence_context = TernionContext(
        cursor_system_prompt=system_message,
        conversation_history=conversation_history,
        has_images=False,
        cursor_tools=list(cursor_tools or []),
        cursor_tool_choice=cursor_tool_choice,
        session_id=session.session_id,
        await_confirmation=await_confirmation,
        execution_mode=user_config.execution_mode,
        workspace_root=context.workspace_root,
        local_workspace_root=context.local_workspace_root,
        workspace_path_style=context.workspace_path_style,
        workspace_root_source=context.workspace_root_source,
    )

    if request.stream:
        show_phase_indicators = bool(getattr(user_config, "show_phase_indicators", True))
        stream_queue = StreamEventQueue()
        evidence_context._stream_queue = stream_queue  # type: ignore[attr-defined]

        async def generate_sse() -> AsyncGenerator[str, None]:
            """SSE generator for Phase 1.5 resume with real-time output."""
            chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
            created = int(time.time())
            final_state: dict = {}
            streamed_content = ""
            pending_phase_indicator: str | None = None
            convergence_pending_raw = ""
            streamed_any_convergence = False

            async def run_workflow() -> None:
                nonlocal final_state
                try:
                    final_state = await resume_report_evidence(
                        evidence_context,
                        evidence_bundle=str(getattr(session, "evidence_bundle", "") or ""),
                        evidence_gaps=str(getattr(session, "evidence_gaps", "") or ""),
                        evidence_requests=str(getattr(session, "evidence_requests", "") or ""),
                        ternion_analyses=list(getattr(session, "ternion_analyses", []) or []),
                        evidence_items=list(getattr(session, "evidence_items", []) or []),
                        evidence_chain_index=list(
                            getattr(session, "evidence_chain_index", []) or []
                        ),
                        evidence_topup_round=int(getattr(session, "evidence_topup_round", 0) or 0),
                        report_evidence_resume_phase=str(
                            getattr(session, "report_evidence_resume_phase", "") or ""
                        ),
                    )
                except Exception as e:
                    logger.exception(
                        "streaming_report_evidence_followup_error",
                        session_id=session.session_id,
                        error=str(e),
                    )
                    await _put_stream_exception(stream_queue, e, phase="report_evidence")
                finally:
                    stream_queue.close()

            workflow_task = asyncio.create_task(run_workflow())

            try:
                heartbeat_interval_seconds = 10

                async def on_timeout() -> str:
                    return await _sse_heartbeat_event(chunk_id, created, request.model)

                async def on_event(event: Any) -> AsyncGenerator[str, None]:
                    nonlocal convergence_pending_raw
                    nonlocal pending_phase_indicator
                    nonlocal streamed_any_convergence
                    nonlocal streamed_content
                    if event.event_type == StreamEventType.TOKEN_DELTA:
                        if event.delta:
                            phase_lower = str(event.phase or "").strip().lower()
                            if phase_lower == "convergence":
                                safe_text, convergence_pending_raw = (
                                    _append_stream_safe_cursor_text(
                                        convergence_pending_raw,
                                        event.delta,
                                    )
                                )
                                if safe_text:
                                    if pending_phase_indicator:
                                        chunk = ChatCompletionChunk(
                                            id=chunk_id,
                                            created=created,
                                            model=request.model,
                                            choices=[
                                                StreamChoice(
                                                    delta=ChoiceDelta(
                                                        content="\n" + pending_phase_indicator
                                                    )
                                                )
                                            ],
                                        )
                                        yield f"data: {chunk.model_dump_json()}\n\n"
                                        pending_phase_indicator = None
                                    streamed_any_convergence = True
                                    streamed_content += safe_text
                                    chunk = ChatCompletionChunk(
                                        id=chunk_id,
                                        created=created,
                                        model=request.model,
                                        choices=[
                                            StreamChoice(delta=ChoiceDelta(content=safe_text))
                                        ],
                                    )
                                    yield f"data: {chunk.model_dump_json()}\n\n"
                                return

                            if pending_phase_indicator:
                                chunk = ChatCompletionChunk(
                                    id=chunk_id,
                                    created=created,
                                    model=request.model,
                                    choices=[
                                        StreamChoice(
                                            delta=ChoiceDelta(
                                                content="\n" + pending_phase_indicator
                                            )
                                        )
                                    ],
                                )
                                yield f"data: {chunk.model_dump_json()}\n\n"
                                pending_phase_indicator = None
                            streamed_content += event.delta
                            chunk = ChatCompletionChunk(
                                id=chunk_id,
                                created=created,
                                model=request.model,
                                choices=[StreamChoice(delta=ChoiceDelta(content=event.delta))],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"
                        return

                    if event.event_type == StreamEventType.PHASE_START:
                        if show_phase_indicators and event.phase:
                            phase_lower = str(event.phase or "").strip().lower()
                            if convergence_pending_raw and phase_lower != "convergence":
                                flushed = sanitize_for_cursor_display(convergence_pending_raw)
                                convergence_pending_raw = ""
                                if flushed:
                                    streamed_any_convergence = True
                                    streamed_content += flushed
                                    chunk = ChatCompletionChunk(
                                        id=chunk_id,
                                        created=created,
                                        model=request.model,
                                        choices=[StreamChoice(delta=ChoiceDelta(content=flushed))],
                                    )
                                    yield f"data: {chunk.model_dump_json()}\n\n"
                            indicator = _phase_start_indicator_text(
                                event.phase, session_id=session.session_id
                            )
                            if indicator:
                                if phase_lower == "convergence":
                                    delta = ChoiceDelta(
                                        role=MessageRole.ASSISTANT,
                                        content=indicator,
                                    )
                                else:
                                    delta = ChoiceDelta(content="\n" + indicator)
                                chunk = ChatCompletionChunk(
                                    id=chunk_id,
                                    created=created,
                                    model=request.model,
                                    choices=[StreamChoice(delta=delta)],
                                )
                                yield f"data: {chunk.model_dump_json()}\n\n"
                                pending_phase_indicator = None
                        return

                    if event.event_type == StreamEventType.ERROR:
                        error_text = _get_stream_error_text(event.metadata)
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=error_text))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
                        return

                async for sse_chunk in _consume_sse_events(
                    stream_queue=stream_queue,
                    heartbeat_interval_seconds=heartbeat_interval_seconds,
                    on_timeout=on_timeout,
                    on_event=on_event,
                ):
                    yield sse_chunk

                await workflow_task

                if convergence_pending_raw:
                    flushed = sanitize_for_cursor_display(convergence_pending_raw)
                    convergence_pending_raw = ""
                    if flushed:
                        streamed_any_convergence = True
                        streamed_content += flushed
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=flushed))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

                pending_tool_calls = final_state.get("pending_tool_calls") or []
                workflow_phase = str(final_state.get("current_phase") or "report_evidence")

                if pending_tool_calls:
                    turn_outcome = _prepare_evidence_pending_tool_calls_turn(
                        session=session,
                        final_state=final_state,
                        pending_tool_calls=pending_tool_calls,
                        workflow_phase=workflow_phase,
                        updated_execution_messages=updated_execution_messages,
                        cursor_system_prompt=cursor_system_prompt,
                        cursor_tools=cursor_tools,
                        cursor_tool_choice=cursor_tool_choice,
                        include_topup_state=True,
                    )
                    if turn_outcome.blocked:
                        for sse_chunk in _sse_text_stop_chunks(
                            chunk_id, created, request.model, turn_outcome.blocked_message
                        ):
                            yield sse_chunk
                        return
                    for sse_chunk in _sse_tool_calls_chunks(
                        chunk_id, created, request.model, turn_outcome.cursor_tool_calls
                    ):
                        yield sse_chunk
                    return

                if streamed_any_convergence:
                    suffix = str(final_state.get("final_output_suffix") or "")
                    suffix = sanitize_for_cursor_display(suffix)
                    if suffix:
                        for i in range(0, len(suffix), 128):
                            text = suffix[i : i + 128]
                            if not text:
                                continue
                            chunk = ChatCompletionChunk(
                                id=chunk_id,
                                created=created,
                                model=request.model,
                                choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"

                workflow_final = final_state.get("final_output", "") or final_state.get(
                    "generated_code", ""
                )
                errors = final_state.get("errors", []) or []
                if workflow_final and not streamed_content:
                    if pending_phase_indicator:
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[
                                StreamChoice(
                                    delta=ChoiceDelta(content="\n" + pending_phase_indicator)
                                )
                            ],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
                        pending_phase_indicator = None
                    for i in range(0, len(workflow_final), 128):
                        text = workflow_final[i : i + 128]
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

                if errors and not workflow_final and not streamed_content:
                    error_backfill = _build_stream_error_backfill(list(errors))
                    if pending_phase_indicator:
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[
                                StreamChoice(
                                    delta=ChoiceDelta(content="\n" + pending_phase_indicator)
                                )
                            ],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
                        pending_phase_indicator = None
                    for i in range(0, len(error_backfill), 128):
                        text = error_backfill[i : i + 128]
                        if not text:
                            continue
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

                thinking_logs = final_state.get("thinking_logs", [])
                if thinking_logs:
                    _emit_thinking_logs_to_observability(
                        thinking_logs,
                        session_id=final_state.get("session_id") or None,
                        context="streaming_report_evidence_followup_output",
                        suppressed_from_chat=True,
                    )

                try:
                    errors = final_state.get("errors", []) or []
                    final_code = final_state.get("final_output", "") or final_state.get(
                        "generated_code", ""
                    )
                    final_phase = str(final_state.get("current_phase") or "report_evidence")
                    new_stage = _resolve_followup_completion_stage(
                        final_phase=final_phase,
                        final_code=str(final_code or ""),
                        errors=list(errors),
                        session_id=session.session_id,
                    )

                    session_store.update_session(
                        session.session_id,
                        stage=new_stage,
                        workflow_phase=final_phase,
                        pending_tool_calls=[],
                        ternion_report_raw=str(
                            final_state.get("ternion_report")
                            or getattr(session, "ternion_report_raw", "")
                            or ""
                        ),
                        generated_code=str(
                            final_state.get("generated_code")
                            or getattr(session, "generated_code", "")
                            or ""
                        ),
                        review_feedback=str(
                            final_state.get("review_feedback")
                            or getattr(session, "review_feedback", "")
                            or ""
                        ),
                        revision_count=int(
                            final_state.get(
                                "revision_count",
                                getattr(session, "revision_count", 0),
                            )
                            or 0
                        ),
                        writer_output_files=dict(
                            final_state.get("writer_output_files")
                            or getattr(session, "writer_output_files", {})
                            or {}
                        ),
                        stabilized_document_paths=list(
                            final_state.get("stabilized_document_paths")
                            or getattr(session, "stabilized_document_paths", [])
                            or []
                        ),
                        optimizer_review_report=str(
                            final_state.get("optimizer_review_report")
                            or getattr(session, "optimizer_review_report", "")
                            or ""
                        ),
                        evidence_bundle=str(
                            final_state.get("evidence_bundle")
                            or getattr(session, "evidence_bundle", "")
                            or ""
                        ),
                        evidence_gaps=str(
                            final_state.get("evidence_gaps")
                            or getattr(session, "evidence_gaps", "")
                            or ""
                        ),
                        evidence_requests=str(
                            final_state.get("evidence_requests")
                            or getattr(session, "evidence_requests", "")
                            or ""
                        ),
                        evidence_chain_index=list(
                            final_state.get("evidence_chain_index")
                            or getattr(session, "evidence_chain_index", [])
                            or []
                        ),
                        evidence_topup_round=int(
                            final_state.get(
                                "evidence_topup_round",
                                getattr(session, "evidence_topup_round", 0),
                            )
                            or 0
                        ),
                        report_evidence_resume_phase=str(
                            final_state.get("report_evidence_resume_phase")
                            or getattr(session, "report_evidence_resume_phase", "")
                            or ""
                        ),
                        ternion_analyses=list(
                            final_state.get("ternion_analyses")
                            or getattr(session, "ternion_analyses", [])
                            or []
                        ),
                    )
                except Exception:
                    pass

                final_chunk = ChatCompletionChunk(
                    id=chunk_id,
                    created=created,
                    model=request.model,
                    choices=[StreamChoice(delta=ChoiceDelta(), finish_reason="stop")],
                )
                yield f"data: {final_chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"

            except asyncio.CancelledError:
                stream_queue.close()
                workflow_task.cancel()
                with contextlib.suppress(BaseException):
                    await workflow_task
                raise
            except Exception as e:
                logger.exception("sse_report_evidence_followup_generation_error", error=str(e))
                error_chunk = ChatCompletionChunk(
                    id=chunk_id,
                    created=created,
                    model=request.model,
                    choices=[
                        StreamChoice(
                            delta=ChoiceDelta(content=t(MessageKey.STREAM_ERROR_INTERRUPTED))
                        )
                    ],
                )
                yield f"data: {error_chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                turn_lock.release()

        turn_lock.hand_off()
        return StreamingResponse(
            generate_sse(),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    # Resume from report_evidence with preserved Phase 0/1 state
    final_state = await resume_report_evidence(
        evidence_context,
        evidence_bundle=str(getattr(session, "evidence_bundle", "") or ""),
        evidence_gaps=str(getattr(session, "evidence_gaps", "") or ""),
        evidence_requests=str(getattr(session, "evidence_requests", "") or ""),
        ternion_analyses=list(getattr(session, "ternion_analyses", []) or []),
        evidence_items=list(getattr(session, "evidence_items", []) or []),
        evidence_chain_index=list(getattr(session, "evidence_chain_index", []) or []),
        evidence_topup_round=int(getattr(session, "evidence_topup_round", 0) or 0),
        report_evidence_resume_phase=str(
            getattr(session, "report_evidence_resume_phase", "") or ""
        ),
    )
    runtime_model_response = _get_runtime_model_unavailable_response_from_state(final_state)
    if runtime_model_response is not None:
        return runtime_model_response

    pending_tool_calls = final_state.get("pending_tool_calls") or []
    workflow_phase = str(final_state.get("current_phase") or "report_evidence")

    if pending_tool_calls:
        turn_outcome = _prepare_evidence_pending_tool_calls_turn(
            session=session,
            final_state=final_state,
            pending_tool_calls=pending_tool_calls,
            workflow_phase=workflow_phase,
            updated_execution_messages=updated_execution_messages,
            cursor_system_prompt=cursor_system_prompt,
            cursor_tools=cursor_tools,
            cursor_tool_choice=cursor_tool_choice,
            include_topup_state=True,
        )
        if turn_outcome.blocked:
            return _respond_with_text(request, turn_outcome.blocked_message)
        return _tool_calls_json_response(request.model, turn_outcome.cursor_tool_calls)

    thinking_logs = final_state.get("thinking_logs", [])
    errors = final_state.get("errors", []) or []
    final_code = final_state.get("final_output", "") or final_state.get("generated_code", "")
    try:
        final_phase = str(final_state.get("current_phase") or "report_evidence")
        new_stage = _resolve_followup_completion_stage(
            final_phase=final_phase,
            final_code=str(final_code or ""),
            errors=list(errors),
            session_id=session.session_id,
        )

        session_store.update_session(
            session.session_id,
            stage=new_stage,
            workflow_phase=final_phase,
            pending_tool_calls=[],
            ternion_report_raw=str(
                final_state.get("ternion_report") or session.ternion_report_raw or ""
            ),
            generated_code=str(final_state.get("generated_code") or session.generated_code or ""),
            review_feedback=str(
                final_state.get("review_feedback") or session.review_feedback or ""
            ),
            revision_count=int(final_state.get("revision_count", session.revision_count) or 0),
            writer_output_files=dict(
                final_state.get("writer_output_files") or session.writer_output_files or {}
            ),
            stabilized_document_paths=list(
                final_state.get("stabilized_document_paths")
                or getattr(session, "stabilized_document_paths", [])
                or []
            ),
            optimizer_review_report=str(
                final_state.get("optimizer_review_report") or session.optimizer_review_report or ""
            ),
            evidence_bundle=str(
                final_state.get("evidence_bundle") or getattr(session, "evidence_bundle", "") or ""
            ),
            evidence_gaps=str(
                final_state.get("evidence_gaps") or getattr(session, "evidence_gaps", "") or ""
            ),
            evidence_requests=str(
                final_state.get("evidence_requests")
                or getattr(session, "evidence_requests", "")
                or ""
            ),
            evidence_chain_index=list(
                final_state.get("evidence_chain_index")
                or getattr(session, "evidence_chain_index", [])
                or []
            ),
            evidence_topup_round=int(
                final_state.get("evidence_topup_round", getattr(session, "evidence_topup_round", 0))
                or 0
            ),
            report_evidence_resume_phase=str(
                final_state.get("report_evidence_resume_phase")
                or getattr(session, "report_evidence_resume_phase", "")
                or ""
            ),
            ternion_analyses=list(
                final_state.get("ternion_analyses")
                or getattr(session, "ternion_analyses", [])
                or []
            ),
        )
    except Exception:
        logger.warning(
            "session_update_failed",
            session_id=session.session_id,
            exc_info=True,
        )
    is_patch_output = _is_patch_or_diff_output(final_code)
    _emit_thinking_logs_to_observability(
        thinking_logs,
        session_id=final_state.get("session_id") or None,
        context="discussion_output",
        suppressed_from_chat=is_patch_output,
    )

    output_parts = []
    if thinking_logs and user_config.show_thinking_logs and not is_patch_output:
        output_parts.append("".join(thinking_logs))
        output_parts.append("\n---\n\n")
    if final_code:
        output_parts.append(final_code)
    else:
        output_parts.append(t(MessageKey.DISCUSSION_NO_OUTPUT))
        if errors:
            output_parts.append("\n\n")
            output_parts.append(t(MessageKey.DISCUSSION_ERRORS_HEADER))
            for err in errors:
                err_msg = sanitize_for_cursor_display(str(err))
                if err_msg:
                    output_parts.append(f"- {err_msg}\n")

    return _respond_with_text(request, "".join(output_parts))


async def handle_evidence_followup(
    session: Session,
    request: ChatCompletionRequest,
) -> Response:
    """
    Handle Phase 0 (Evidence) follow-ups for Cursor Agent tool loops.

    This branch is identified via tool_call_id and workflow_phase == "evidence".
    Runs full workflow from evidence node.

    The whole turn runs under the per-session lock; for streaming responses
    the lock is handed off to the SSE generator.
    """
    turn_lock = _SessionTurnLock(session.session_id)
    await turn_lock.acquire()
    try:
        return await _evidence_followup_turn(session, request, turn_lock)
    finally:
        if not turn_lock.handed_off:
            turn_lock.release()


async def _evidence_followup_turn(
    session: Session,
    request: ChatCompletionRequest,
    turn_lock: _SessionTurnLock,
) -> Response:
    """Locked turn body for handle_evidence_followup."""
    from ternion.workflow.graph import run_discussion

    turn = _prepare_followup_turn(session, request)
    cursor_tools = turn.cursor_tools
    cursor_tool_choice = turn.cursor_tool_choice
    context = turn.context
    cursor_system_prompt = turn.cursor_system_prompt

    updated_execution_messages = _merge_incoming_tool_results(session, request.messages)

    # Preserve the original workflow_phase (critical for P0-1 fix)
    original_workflow_phase = str(getattr(session, "workflow_phase", "") or "evidence")
    session_store.update_session(
        session.session_id,
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        cursor_system_prompt=cursor_system_prompt,
        cursor_tools=list(cursor_tools or []),
        cursor_tool_choice=cursor_tool_choice,
        execution_messages=updated_execution_messages,
        pending_tool_calls=[],
        workflow_phase=original_workflow_phase,  # Preserve, not hardcode "evidence"
    )

    budget_response = _check_followup_budget(session, request)
    if budget_response is not None:
        return budget_response

    user_config, await_confirmation = _resolve_followup_execution_mode(request)

    system_message = (
        ChatMessage(role=MessageRole.SYSTEM, content=cursor_system_prompt)
        if cursor_system_prompt
        else None
    )
    conversation_history = _build_followup_conversation_history(updated_execution_messages)
    _log_followup_history_diagnostics(
        session.session_id,
        updated_execution_messages,
        label="evidence_followup",
    )

    evidence_context = TernionContext(
        cursor_system_prompt=system_message,
        conversation_history=conversation_history,
        has_images=False,
        cursor_tools=list(cursor_tools or []),
        cursor_tool_choice=cursor_tool_choice,
        session_id=session.session_id,
        await_confirmation=await_confirmation,
        execution_mode=user_config.execution_mode,
        workspace_root=context.workspace_root,
        local_workspace_root=context.local_workspace_root,
        workspace_path_style=context.workspace_path_style,
        workspace_root_source=context.workspace_root_source,
    )

    if request.stream:
        show_phase_indicators = bool(getattr(user_config, "show_phase_indicators", True))
        stream_queue = StreamEventQueue()
        evidence_context._stream_queue = stream_queue  # type: ignore[attr-defined]

        async def generate_sse() -> AsyncGenerator[str, None]:
            """SSE generator for Phase 0 follow-up with real-time output."""
            chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
            created = int(time.time())
            final_state: dict = {}
            streamed_content = ""
            pending_phase_indicator: str | None = None
            convergence_pending_raw = ""
            streamed_any_convergence = False

            async def run_workflow() -> None:
                nonlocal final_state
                try:
                    final_state = await run_discussion(evidence_context)
                except Exception as e:
                    logger.exception(
                        "streaming_evidence_followup_error",
                        session_id=session.session_id,
                        error=str(e),
                    )
                    await _put_stream_exception(stream_queue, e, phase="evidence")
                finally:
                    stream_queue.close()

            workflow_task = asyncio.create_task(run_workflow())

            try:
                heartbeat_interval_seconds = 10

                async def on_timeout() -> str:
                    return await _sse_heartbeat_event(chunk_id, created, request.model)

                async def on_event(event: Any) -> AsyncGenerator[str, None]:
                    nonlocal convergence_pending_raw
                    nonlocal pending_phase_indicator
                    nonlocal streamed_any_convergence
                    nonlocal streamed_content
                    if event.event_type == StreamEventType.TOKEN_DELTA:
                        if event.delta:
                            phase_lower = str(event.phase or "").strip().lower()
                            if phase_lower == "convergence":
                                safe_text, convergence_pending_raw = (
                                    _append_stream_safe_cursor_text(
                                        convergence_pending_raw,
                                        event.delta,
                                    )
                                )
                                if safe_text:
                                    if pending_phase_indicator:
                                        chunk = ChatCompletionChunk(
                                            id=chunk_id,
                                            created=created,
                                            model=request.model,
                                            choices=[
                                                StreamChoice(
                                                    delta=ChoiceDelta(
                                                        content="\n" + pending_phase_indicator
                                                    )
                                                )
                                            ],
                                        )
                                        yield f"data: {chunk.model_dump_json()}\n\n"
                                        pending_phase_indicator = None
                                    streamed_any_convergence = True
                                    streamed_content += safe_text
                                    chunk = ChatCompletionChunk(
                                        id=chunk_id,
                                        created=created,
                                        model=request.model,
                                        choices=[
                                            StreamChoice(delta=ChoiceDelta(content=safe_text))
                                        ],
                                    )
                                    yield f"data: {chunk.model_dump_json()}\n\n"
                                return

                            if pending_phase_indicator:
                                chunk = ChatCompletionChunk(
                                    id=chunk_id,
                                    created=created,
                                    model=request.model,
                                    choices=[
                                        StreamChoice(
                                            delta=ChoiceDelta(
                                                content="\n" + pending_phase_indicator
                                            )
                                        )
                                    ],
                                )
                                yield f"data: {chunk.model_dump_json()}\n\n"
                                pending_phase_indicator = None
                            streamed_content += event.delta
                            chunk = ChatCompletionChunk(
                                id=chunk_id,
                                created=created,
                                model=request.model,
                                choices=[StreamChoice(delta=ChoiceDelta(content=event.delta))],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"
                        return

                    if event.event_type == StreamEventType.PHASE_START:
                        if show_phase_indicators and event.phase:
                            phase_lower = str(event.phase or "").strip().lower()
                            if convergence_pending_raw and phase_lower != "convergence":
                                flushed = sanitize_for_cursor_display(convergence_pending_raw)
                                convergence_pending_raw = ""
                                if flushed:
                                    streamed_any_convergence = True
                                    streamed_content += flushed
                                    chunk = ChatCompletionChunk(
                                        id=chunk_id,
                                        created=created,
                                        model=request.model,
                                        choices=[StreamChoice(delta=ChoiceDelta(content=flushed))],
                                    )
                                    yield f"data: {chunk.model_dump_json()}\n\n"
                            indicator = _phase_start_indicator_text(
                                event.phase, session_id=session.session_id
                            )
                            if indicator:
                                if phase_lower == "convergence":
                                    delta = ChoiceDelta(
                                        role=MessageRole.ASSISTANT,
                                        content=indicator,
                                    )
                                else:
                                    delta = ChoiceDelta(content="\n" + indicator)
                                chunk = ChatCompletionChunk(
                                    id=chunk_id,
                                    created=created,
                                    model=request.model,
                                    choices=[StreamChoice(delta=delta)],
                                )
                                yield f"data: {chunk.model_dump_json()}\n\n"
                                pending_phase_indicator = None
                        return

                    if event.event_type == StreamEventType.ERROR:
                        error_text = _get_stream_error_text(event.metadata)
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=error_text))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
                        return

                async for sse_chunk in _consume_sse_events(
                    stream_queue=stream_queue,
                    heartbeat_interval_seconds=heartbeat_interval_seconds,
                    on_timeout=on_timeout,
                    on_event=on_event,
                ):
                    yield sse_chunk

                await workflow_task

                if convergence_pending_raw:
                    flushed = sanitize_for_cursor_display(convergence_pending_raw)
                    convergence_pending_raw = ""
                    if flushed:
                        streamed_any_convergence = True
                        streamed_content += flushed
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=flushed))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

                pending_tool_calls = final_state.get("pending_tool_calls") or []
                workflow_phase = str(final_state.get("current_phase") or "evidence")
                if pending_tool_calls:
                    turn_outcome = _prepare_evidence_pending_tool_calls_turn(
                        session=session,
                        final_state=final_state,
                        pending_tool_calls=pending_tool_calls,
                        workflow_phase=workflow_phase,
                        updated_execution_messages=updated_execution_messages,
                        cursor_system_prompt=cursor_system_prompt,
                        cursor_tools=cursor_tools,
                        cursor_tool_choice=cursor_tool_choice,
                        include_topup_state=False,
                    )
                    if turn_outcome.blocked:
                        for sse_chunk in _sse_text_stop_chunks(
                            chunk_id, created, request.model, turn_outcome.blocked_message
                        ):
                            yield sse_chunk
                        return
                    for sse_chunk in _sse_tool_calls_chunks(
                        chunk_id, created, request.model, turn_outcome.cursor_tool_calls
                    ):
                        yield sse_chunk
                    return

                if streamed_any_convergence:
                    suffix = str(final_state.get("final_output_suffix") or "")
                    suffix = sanitize_for_cursor_display(suffix)
                    if suffix:
                        for i in range(0, len(suffix), 128):
                            text = suffix[i : i + 128]
                            if not text:
                                continue
                            chunk = ChatCompletionChunk(
                                id=chunk_id,
                                created=created,
                                model=request.model,
                                choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"

                workflow_final = final_state.get("final_output", "") or final_state.get(
                    "generated_code", ""
                )
                errors = final_state.get("errors", []) or []
                if workflow_final and not streamed_content:
                    if pending_phase_indicator:
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[
                                StreamChoice(
                                    delta=ChoiceDelta(content="\n" + pending_phase_indicator)
                                )
                            ],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
                        pending_phase_indicator = None
                    for i in range(0, len(workflow_final), 128):
                        text = workflow_final[i : i + 128]
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

                if errors and not workflow_final and not streamed_content:
                    error_backfill = _build_stream_error_backfill(list(errors))
                    if pending_phase_indicator:
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[
                                StreamChoice(
                                    delta=ChoiceDelta(content="\n" + pending_phase_indicator)
                                )
                            ],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
                        pending_phase_indicator = None
                    for i in range(0, len(error_backfill), 128):
                        text = error_backfill[i : i + 128]
                        if not text:
                            continue
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

                thinking_logs = final_state.get("thinking_logs", [])
                if thinking_logs:
                    _emit_thinking_logs_to_observability(
                        thinking_logs,
                        session_id=final_state.get("session_id") or None,
                        context="streaming_evidence_followup_output",
                        suppressed_from_chat=True,
                    )

                final_chunk = ChatCompletionChunk(
                    id=chunk_id,
                    created=created,
                    model=request.model,
                    choices=[StreamChoice(delta=ChoiceDelta(), finish_reason="stop")],
                )
                yield f"data: {final_chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"

            except asyncio.CancelledError:
                stream_queue.close()
                workflow_task.cancel()
                with contextlib.suppress(BaseException):
                    await workflow_task
                raise
            except Exception as e:
                logger.exception("sse_evidence_followup_generation_error", error=str(e))
                error_chunk = ChatCompletionChunk(
                    id=chunk_id,
                    created=created,
                    model=request.model,
                    choices=[
                        StreamChoice(
                            delta=ChoiceDelta(content=t(MessageKey.STREAM_ERROR_INTERRUPTED))
                        )
                    ],
                )
                yield f"data: {error_chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                turn_lock.release()

        turn_lock.hand_off()
        return StreamingResponse(
            generate_sse(),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    # Run full workflow from evidence node (Phase 0)
    final_state = await run_discussion(evidence_context)
    runtime_model_response = _get_runtime_model_unavailable_response_from_state(final_state)
    if runtime_model_response is not None:
        return runtime_model_response

    pending_tool_calls = final_state.get("pending_tool_calls") or []
    workflow_phase = str(final_state.get("current_phase") or "evidence")
    if pending_tool_calls:
        turn_outcome = _prepare_evidence_pending_tool_calls_turn(
            session=session,
            final_state=final_state,
            pending_tool_calls=pending_tool_calls,
            workflow_phase=workflow_phase,
            updated_execution_messages=updated_execution_messages,
            cursor_system_prompt=cursor_system_prompt,
            cursor_tools=cursor_tools,
            cursor_tool_choice=cursor_tool_choice,
            include_topup_state=False,
        )
        if turn_outcome.blocked:
            return _respond_with_text(request, turn_outcome.blocked_message)
        return _tool_calls_json_response(request.model, turn_outcome.cursor_tool_calls)

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

    output_parts = []
    if thinking_logs and user_config.show_thinking_logs and not is_patch_output:
        output_parts.append("".join(thinking_logs))
        output_parts.append("\n---\n\n")
    if final_code:
        output_parts.append(final_code)
    else:
        output_parts.append(t(MessageKey.DISCUSSION_NO_OUTPUT))
        if errors:
            output_parts.append("\n\n")
            output_parts.append(t(MessageKey.DISCUSSION_ERRORS_HEADER))
            for err in errors:
                err_msg = sanitize_for_cursor_display(str(err))
                if err_msg:
                    output_parts.append(f"- {err_msg}\n")

    return _respond_with_text(request, "".join(output_parts))


async def handle_execution_followup(
    session: Session,
    request: ChatCompletionRequest,
    *,
    skip_budget_confirm: bool = False,
) -> Response:
    """
    Handle execution-stage follow-ups for Cursor Agent tool loops.

    This branch is identified via tool_call_id, not via plain-text session markers.

    The whole turn runs under the per-session lock; for streaming responses
    the lock is handed off to the SSE generator.
    """
    turn_lock = _SessionTurnLock(session.session_id)
    await turn_lock.acquire()
    try:
        return await _execution_followup_turn(
            session,
            request,
            turn_lock,
            skip_budget_confirm=skip_budget_confirm,
        )
    finally:
        if not turn_lock.handed_off:
            turn_lock.release()


async def _execution_followup_turn(
    session: Session,
    request: ChatCompletionRequest,
    turn_lock: _SessionTurnLock,
    *,
    skip_budget_confirm: bool = False,
) -> Response:
    """Locked turn body for handle_execution_followup."""
    from ternion.utils.tool_result_compaction import compact_tool_result
    from ternion.workflow.implementation_stage import run_implementation_stage

    turn = _prepare_followup_turn(session, request)
    cursor_tools = turn.cursor_tools
    cursor_tool_choice = turn.cursor_tool_choice
    workspace_root = turn.workspace_root
    local_workspace_root = turn.local_workspace_root
    workspace_path_style = turn.workspace_path_style
    workspace_root_source = turn.workspace_root_source
    cursor_system_prompt = turn.cursor_system_prompt

    # Append new tool results from this request into the persisted execution history.
    pending_by_id = {
        tc.get("id"): tc
        for tc in (session.pending_tool_calls or [])
        if isinstance(tc, dict) and isinstance(tc.get("id"), str)
    }
    tool_results_raw = dict(getattr(session, "tool_results_raw", {}) or {})
    tool_results_meta = dict(getattr(session, "tool_results_meta", {}) or {})
    tool_call_index = dict(getattr(session, "tool_call_index", {}) or {})
    guardrail_events_to_append: list[dict[str, Any]] = []
    external_outputs_to_append: list[dict[str, Any]] = []

    baseline = dict(getattr(session, "baseline_file_snapshots", {}) or {})
    modified_files = list(getattr(session, "modified_files", []) or [])
    modified_set = set(modified_files)
    writer_output_files = dict(getattr(session, "writer_output_files", {}) or {})
    stabilized_document_paths = list(getattr(session, "stabilized_document_paths", []) or [])
    stabilized_document_set = {
        path for path in stabilized_document_paths if isinstance(path, str) and path.strip()
    }
    newly_stabilized_document_paths: list[str] = []

    git_cursor = dict(getattr(session, "tool_loop_pre_git_status", {}) or {})
    git_cursor_modified = {
        p for p in (git_cursor.get("modified") or []) if isinstance(p, str) and p.strip()
    }
    git_cursor_untracked = {
        p for p in (git_cursor.get("untracked") or []) if isinstance(p, str) and p.strip()
    }

    history_tool_calls_by_id: dict[str, dict] = {}
    for history_msg in session.execution_messages or []:
        if not isinstance(history_msg, dict) or history_msg.get("role") != "assistant":
            continue
        tool_calls = history_msg.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            tc_id = tc.get("id")
            if isinstance(tc_id, str) and tc_id:
                history_tool_calls_by_id[tc_id] = tc

    def _process_execution_tool_result(tool_result_msg: ChatMessage, raw_content: str) -> str:
        """Compact one incoming tool result and track execution-stage side effects."""
        nonlocal git_cursor_modified, git_cursor_untracked
        tool_call = (
            pending_by_id.get(tool_result_msg.tool_call_id)
            or history_tool_calls_by_id.get(tool_result_msg.tool_call_id)
            or {}
        )
        fn = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
        tool_name = fn.get("name") if isinstance(fn.get("name"), str) else None
        tool_args = fn.get("arguments") if isinstance(fn.get("arguments"), str) else None
        if not tool_name:
            indexed = tool_call_index.get(tool_result_msg.tool_call_id)
            if isinstance(indexed, dict):
                indexed_name = indexed.get("tool_name")
                if isinstance(indexed_name, str) and indexed_name.strip():
                    tool_name = indexed_name.strip()
                indexed_args = indexed.get("tool_arguments")
                if tool_args is None and isinstance(indexed_args, str) and indexed_args.strip():
                    tool_args = indexed_args

        compacted_content, meta = compact_tool_result(
            tool_name=tool_name,
            content=raw_content,
            tool_arguments=tool_args,
        )
        meta["source_ref"] = tool_result_msg.tool_call_id
        canonical_tool = re.sub(r"[^a-z0-9]+", "", (tool_name or "").strip().lower())
        if canonical_tool in _MUTATING_TOOL_NAMES:
            target = _extract_mutation_target_path(tool_name or "", tool_args or "{}")
            normalized = _normalize_file_path(
                target or "",
                workspace_root,
                workspace_path_style,
            )
            if normalized:
                git_cursor_modified.add(normalized)
        if canonical_tool in {"write", "writefile"}:
            target = _extract_mutation_target_path(tool_name or "", tool_args or "{}")
            normalized = _normalize_file_path(
                target or "",
                workspace_root,
                workspace_path_style,
            )
            relative = _workspace_relative_path(
                normalized or "",
                workspace_root,
                workspace_path_style,
            )
            if normalized and relative and _is_document_like_target(relative):
                local_target = _normalize_local_file_path(
                    target or "",
                    workspace_root=workspace_root,
                    workspace_path_style=workspace_path_style,
                    local_workspace_root=local_workspace_root,
                )
                document_snapshot = (
                    _read_text_file_best_effort(local_target) if local_target else None
                )
                if document_snapshot is not None:
                    writer_output_files[normalized] = document_snapshot
                    meta["document_output_stabilized"] = True
                    meta["document_output_path"] = normalized
                    meta["document_output_snapshot_chars"] = len(document_snapshot)
                    if normalized not in stabilized_document_set:
                        stabilized_document_paths.append(normalized)
                        stabilized_document_set.add(normalized)
                        newly_stabilized_document_paths.append(normalized)
        if canonical_tool in {"shell"}:
            shell_command = _extract_shell_command(tool_args or "{}") or ""
            shell_purpose = _extract_shell_purpose(tool_args or "{}")
            shell_workdir = _extract_shell_working_directory(tool_args or "{}")
            dedup_key = _normalize_shell_command_for_dedup(shell_command)
            duplicate_of = _find_duplicate_shell_call(tool_results_meta, dedup_key=dedup_key)
            exit_code, elapsed_ms = _extract_shell_result_metrics(raw_content)
            indexed = (
                tool_call_index.get(tool_result_msg.tool_call_id)
                if isinstance(tool_call_index, dict)
                else None
            )
            phase = (
                str(indexed.get("workflow_phase"))
                if isinstance(indexed, dict) and isinstance(indexed.get("workflow_phase"), str)
                else str(getattr(session, "workflow_phase", "") or "")
            )
            role = "optimizer" if phase == "optimizer" else "writer"
            shell_may_write = _shell_command_may_write(shell_command)

            dirty_before_count = 0
            dirty_after_count = 0
            delta_added_count = 0
            delta_removed_count = 0
            delta_added_paths: list[str] = []
            delta_removed_paths: list[str] = []
            delta_truncated = False

            if isinstance(git_cursor, dict) and "repo_root" in git_cursor:
                git_status_snapshot = _try_get_git_status_snapshot(
                    workspace_root=workspace_root,
                    workspace_path_style=workspace_path_style,
                    local_workspace_root=local_workspace_root,
                )
                if git_status_snapshot:
                    post_modified = {
                        p
                        for p in (git_status_snapshot.get("modified") or [])
                        if isinstance(p, str) and p.strip()
                    }
                    post_untracked = {
                        p
                        for p in (git_status_snapshot.get("untracked") or [])
                        if isinstance(p, str) and p.strip()
                    }
                    pre_all = set(git_cursor_modified) | set(git_cursor_untracked)
                    post_all = post_modified | post_untracked
                    dirty_before_count = len(pre_all)
                    dirty_after_count = len(post_all)

                    added = sorted(post_all - pre_all)
                    removed = sorted(pre_all - post_all)
                    delta_added_count = len(added)
                    delta_removed_count = len(removed)

                    max_paths = 50
                    delta_truncated = len(added) > max_paths or len(removed) > max_paths
                    for abs_path in added[:max_paths]:
                        rel = _workspace_relative_path(
                            abs_path,
                            workspace_root,
                            workspace_path_style,
                        )
                        if rel:
                            delta_added_paths.append(rel)
                    for abs_path in removed[:max_paths]:
                        rel = _workspace_relative_path(
                            abs_path,
                            workspace_root,
                            workspace_path_style,
                        )
                        if rel:
                            delta_removed_paths.append(rel)

                    for abs_path in added:
                        if abs_path not in modified_set:
                            modified_files.append(abs_path)
                            modified_set.add(abs_path)
                        if abs_path in baseline:
                            continue
                        rel = _workspace_relative_path(
                            abs_path,
                            workspace_root,
                            workspace_path_style,
                        )
                        if not rel:
                            continue
                        if abs_path in post_untracked:
                            baseline[abs_path] = ""
                            continue
                        base_content = _try_read_git_head_file(
                            rel,
                            local_workspace_root=local_workspace_root,
                        )
                        if base_content is not None:
                            baseline[abs_path] = base_content

                    git_cursor_modified = post_modified
                    git_cursor_untracked = post_untracked
                    git_cursor["repo_root"] = git_status_snapshot.get(
                        "repo_root",
                        git_cursor.get("repo_root", ""),
                    )
                    git_cursor["modified"] = sorted(post_modified)
                    git_cursor["untracked"] = sorted(post_untracked)

            meta.update(
                {
                    "shell_command": shell_command,
                    "shell_purpose": shell_purpose or "",
                    "shell_working_directory": shell_workdir or "",
                    "shell_exit_code": exit_code,
                    "shell_elapsed_ms": elapsed_ms,
                    "shell_dedup_key": dedup_key,
                    "shell_is_duplicate": bool(duplicate_of),
                    "shell_duplicate_of": duplicate_of or "",
                    "shell_phase": phase,
                    "shell_role": role,
                    "shell_may_write": bool(shell_may_write),
                    "shell_dirty_before_count": int(dirty_before_count),
                    "shell_dirty_after_count": int(dirty_after_count),
                    "shell_dirty_added_count": int(delta_added_count),
                    "shell_dirty_removed_count": int(delta_removed_count),
                    "shell_dirty_added_paths": delta_added_paths,
                    "shell_dirty_removed_paths": delta_removed_paths,
                    "shell_dirty_paths_truncated": bool(delta_truncated),
                }
            )
            if _is_pytest_command(shell_command) and (exit_code is None or exit_code != 0):
                meta.update(_extract_pytest_failure_details(raw_content))

            external_paths = _extract_external_output_paths(raw_content)
            if external_paths:
                meta["shell_output_external_path"] = external_paths[0]
                meta["shell_output_external_paths"] = list(external_paths)
                tail_lines = "\n".join((raw_content or "").splitlines()[-20:])
                preview_tail = sanitize_for_cursor_display(redact_secrets(tail_lines))
                if len(preview_tail) > 1200:
                    preview_tail = preview_tail[-1200:]
                meta["shell_output_preview_tail"] = preview_tail

                cmd_preview = _build_redacted_preview(shell_command, max_chars=200)
                for path in external_paths:
                    external_outputs_to_append.append(
                        {
                            "kind": "shell_output",
                            "tool_call_id": tool_result_msg.tool_call_id,
                            "tool_name": tool_name or "Shell",
                            "path": path,
                            "command_preview": cmd_preview,
                            "exit_code": exit_code,
                            "elapsed_ms": elapsed_ms,
                        }
                    )
            preview = shell_command.strip().replace("\n", " ")
            if len(preview) > 200:
                preview = preview[:200] + "..."
            log_manager.emit(
                level="INFO",
                category="OBSERVABILITY",
                message=(
                    "shell_tool_result | "
                    f"session_id={session.session_id} | "
                    f"tool_call_id={tool_result_msg.tool_call_id} | "
                    f"phase={phase or '(unknown)'} | "
                    f"role={role} | "
                    f"exit_code={exit_code if exit_code is not None else '(unknown)'} | "
                    f"elapsed_ms={elapsed_ms if elapsed_ms is not None else '(unknown)'} | "
                    f"duplicate={bool(duplicate_of)} | "
                    f"may_write={bool(shell_may_write)} | "
                    f"delta_added={delta_added_count} | "
                    f"delta_removed={delta_removed_count} | "
                    f"purpose={sanitize_for_cursor_display(shell_purpose or '')[:120]} | "
                    f"command={preview}"
                ),
            )
        tool_results_meta[tool_result_msg.tool_call_id] = meta
        if meta.get("compacted") is True:
            tool_results_raw[tool_result_msg.tool_call_id] = raw_content
        return compacted_content

    updated_execution_messages = _merge_incoming_tool_results(
        session,
        request.messages,
        process_result=_process_execution_tool_result,
    )

    if isinstance(git_cursor, dict) and "repo_root" in git_cursor:
        git_cursor["modified"] = sorted(git_cursor_modified)
        git_cursor["untracked"] = sorted(git_cursor_untracked)

    resume_phase = str(getattr(session, "workflow_phase", "") or "execution").strip().lower()
    deliverable_type, _allowed_scope = _resolve_deliverable_policy_from_context(
        updated_execution_messages,
        str(getattr(session, "ternion_report_raw", "") or ""),
    )
    auto_promote_doc_only = (
        resume_phase == "execution"
        and deliverable_type == DeliverableType.DOC_ONLY
        and bool(newly_stabilized_document_paths)
    )
    if auto_promote_doc_only:
        resume_phase = "optimizer"
        guardrail_events_to_append.append(
            {
                "type": "doc_only_document_stabilized",
                "role": "writer",
                "deliverable_type": deliverable_type.value,
                "paths": list(newly_stabilized_document_paths),
            }
        )

    deferred_plan = list(getattr(session, "deferred_tool_calls", []) or [])
    if deferred_plan and not auto_promote_doc_only:
        workflow_phase = resume_phase
        next_round = (session.round_index or 0) + 1

        filtered_tool_calls = list(deferred_plan)
        before_cursor_validate = list(filtered_tool_calls)
        filtered_tool_calls, cursor_tools_error = (
            _normalize_and_validate_tool_calls_against_cursor_tools(
                workflow_phase=workflow_phase,
                tool_calls=filtered_tool_calls,
                cursor_tools=list(cursor_tools or []),
            )
        )
        rewrites = _diff_tool_call_name_rewrites(before_cursor_validate, filtered_tool_calls)
        if rewrites:
            guardrail_events_to_append.append(
                {
                    "type": "tool_call_name_rewrite",
                    "role": "optimizer" if workflow_phase == "optimizer" else "writer",
                    "rewrites": rewrites,
                }
            )
        tool_policy_error = cursor_tools_error
        role_label = "optimizer" if workflow_phase == "optimizer" else "writer"
        if tool_policy_error:
            available = _extract_cursor_tool_names(cursor_tools)
            available_set = set(available)
            unknown: list[str] = []
            for tc in before_cursor_validate:
                name, _args = _extract_tool_name_and_arguments(tc)
                if isinstance(name, str) and name and name not in available_set:
                    unknown.append(name)
            guardrail_events_to_append.append(
                {
                    "type": "tool_calls_not_in_cursor_tools",
                    "role": role_label,
                    "blocked_tools": sorted(set(unknown)),
                    "error_preview": sanitize_for_preview(
                        redact_secrets(tool_policy_error),
                        max_length=240,
                    ),
                }
            )
        else:
            before_exec_policy = list(filtered_tool_calls)
            filtered_tool_calls, tool_policy_error = _enforce_execution_tool_policy(
                workflow_phase=workflow_phase,
                tool_calls=filtered_tool_calls,
            )
            if tool_policy_error:
                blocked_tools, blocked_shell = _collect_execution_tool_policy_block_details(
                    before_exec_policy
                )
                guardrail_events_to_append.append(
                    {
                        "type": "execution_tool_policy_blocked",
                        "role": role_label,
                        "blocked_tools": blocked_tools,
                        "blocked_shell": blocked_shell,
                        "error_preview": sanitize_for_preview(
                            redact_secrets(tool_policy_error),
                            max_length=240,
                        ),
                    }
                )

        if tool_policy_error:
            session_store.update_session(
                session.session_id,
                stage=SessionStage.AWAITING_CONFIRMATION,
                confirmation_reason="tool_policy",
                pending_tool_calls=[],
                deferred_tool_calls=[],
                execution_messages=updated_execution_messages,
                tool_results_raw=tool_results_raw,
                tool_results_meta=tool_results_meta,
                tool_loop_pre_git_status=git_cursor,
                modified_files=modified_files,
                baseline_file_snapshots=baseline,
                writer_output_files=writer_output_files,
                stabilized_document_paths=stabilized_document_paths,
                evidence_bundle=str(getattr(session, "evidence_bundle", "") or ""),
                evidence_gaps=str(getattr(session, "evidence_gaps", "") or ""),
                evidence_requests=str(getattr(session, "evidence_requests", "") or ""),
                evidence_chain_index=list(getattr(session, "evidence_chain_index", []) or []),
                evidence_topup_round=int(getattr(session, "evidence_topup_round", 0) or 0),
                report_evidence_resume_phase=str(
                    getattr(session, "report_evidence_resume_phase", "") or ""
                ),
                append_guardrail_events=guardrail_events_to_append,
                append_external_outputs_index=external_outputs_to_append,
            )
            return _respond_with_text(request, tool_policy_error)

        before_deliverable_policy = list(filtered_tool_calls)
        filtered_tool_calls, policy_error, deferred_deliverable_type, allowed_scope = (
            _enforce_deliverable_policy(
                workflow_phase=workflow_phase,
                tool_calls=filtered_tool_calls,
                conversation_history=updated_execution_messages,
                ternion_report=str(getattr(session, "ternion_report_raw", "") or ""),
                workspace_root=workspace_root,
                workspace_path_style=workspace_path_style,
                workspace_root_source=workspace_root_source,
            )
        )
        if policy_error:
            violations = (
                _collect_deliverable_policy_violations(
                    before_deliverable_policy,
                    deferred_deliverable_type,
                    workspace_root,
                    workspace_path_style,
                    workspace_root_source,
                )
                if deferred_deliverable_type is not None
                else []
            )
            guardrail_events_to_append.append(
                {
                    "type": "deliverable_policy_blocked",
                    "role": "optimizer" if workflow_phase == "optimizer" else "writer",
                    "deliverable_type": deferred_deliverable_type.value
                    if deferred_deliverable_type is not None
                    else "",
                    "allowed_scope": allowed_scope or "",
                    "violations": violations,
                    "error_preview": sanitize_for_preview(
                        redact_secrets(policy_error),
                        max_length=240,
                    ),
                }
            )
            session_store.update_session(
                session.session_id,
                stage=SessionStage.AWAITING_CONFIRMATION,
                confirmation_reason="deliverable_policy",
                pending_tool_calls=[],
                deferred_tool_calls=[],
                execution_messages=updated_execution_messages,
                tool_results_raw=tool_results_raw,
                tool_results_meta=tool_results_meta,
                tool_loop_pre_git_status=git_cursor,
                modified_files=modified_files,
                baseline_file_snapshots=baseline,
                writer_output_files=writer_output_files,
                stabilized_document_paths=stabilized_document_paths,
                evidence_bundle=str(getattr(session, "evidence_bundle", "") or ""),
                evidence_gaps=str(getattr(session, "evidence_gaps", "") or ""),
                evidence_requests=str(getattr(session, "evidence_requests", "") or ""),
                evidence_chain_index=list(getattr(session, "evidence_chain_index", []) or []),
                evidence_topup_round=int(getattr(session, "evidence_topup_round", 0) or 0),
                report_evidence_resume_phase=str(
                    getattr(session, "report_evidence_resume_phase", "") or ""
                ),
                append_guardrail_events=guardrail_events_to_append,
                append_external_outputs_index=external_outputs_to_append,
            )
            return _respond_with_text(request, policy_error)

        rewritten_tool_calls = _rewrite_tool_call_ids(
            filtered_tool_calls,
            session_id=session.session_id,
            round_index=next_round,
            workflow_phase=workflow_phase,
        )
        cursor_tool_calls = _strip_internal_tool_call_fields(rewritten_tool_calls)
        execution_messages = _append_assistant_tool_call_message(
            updated_execution_messages,
            rewritten_tool_calls,
        )
        session_store.update_session(
            session.session_id,
            stage=SessionStage.AWAITING_TOOL_RESULTS,
            cursor_system_prompt=cursor_system_prompt,
            cursor_tools=list(cursor_tools or []),
            cursor_tool_choice=cursor_tool_choice,
            execution_messages=execution_messages,
            pending_tool_calls=rewritten_tool_calls,
            deferred_tool_calls=[],
            tool_results_raw=tool_results_raw,
            tool_results_meta=tool_results_meta,
            tool_loop_pre_git_status=_capture_tool_loop_pre_git_status(
                rewritten_tool_calls,
                round_index=next_round,
                workflow_phase=workflow_phase,
                workspace_root=workspace_root,
                workspace_path_style=workspace_path_style,
                local_workspace_root=local_workspace_root,
            ),
            round_index=next_round,
            workflow_phase=workflow_phase,
            modified_files=modified_files,
            baseline_file_snapshots=baseline,
            writer_output_files=writer_output_files,
            stabilized_document_paths=stabilized_document_paths,
            evidence_bundle=str(getattr(session, "evidence_bundle", "") or ""),
            evidence_gaps=str(getattr(session, "evidence_gaps", "") or ""),
            evidence_requests=str(getattr(session, "evidence_requests", "") or ""),
            evidence_chain_index=list(getattr(session, "evidence_chain_index", []) or []),
            evidence_topup_round=int(getattr(session, "evidence_topup_round", 0) or 0),
            report_evidence_resume_phase=str(
                getattr(session, "report_evidence_resume_phase", "") or ""
            ),
            append_guardrail_events=guardrail_events_to_append,
            append_external_outputs_index=external_outputs_to_append,
        )

        if request.stream:
            return StreamingResponse(
                create_sse_tool_calls_stream(
                    model=request.model,
                    tool_calls=cursor_tool_calls,
                    content=None,
                ),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
            )
        return JSONResponse(
            content=ChatCompletionResponse(
                model=request.model,
                choices=[
                    Choice(
                        finish_reason="tool_calls",
                        message=ChatMessage(
                            role=MessageRole.ASSISTANT,
                            content=None,
                            tool_calls=cursor_tool_calls,
                        ),
                    )
                ],
            ).model_dump()
        )

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
        deferred_tool_calls=[],
        workflow_phase=resume_phase,
        tool_results_raw=tool_results_raw,
        tool_results_meta=tool_results_meta,
        tool_loop_pre_git_status=git_cursor,
        modified_files=modified_files,
        baseline_file_snapshots=baseline,
        writer_output_files=writer_output_files,
        stabilized_document_paths=stabilized_document_paths,
        evidence_bundle=str(getattr(session, "evidence_bundle", "") or ""),
        evidence_gaps=str(getattr(session, "evidence_gaps", "") or ""),
        evidence_requests=str(getattr(session, "evidence_requests", "") or ""),
        evidence_chain_index=list(getattr(session, "evidence_chain_index", []) or []),
        evidence_topup_round=int(getattr(session, "evidence_topup_round", 0) or 0),
        report_evidence_resume_phase=str(
            getattr(session, "report_evidence_resume_phase", "") or ""
        ),
        append_guardrail_events=guardrail_events_to_append,
        append_external_outputs_index=external_outputs_to_append,
    )

    if not skip_budget_confirm:
        budget_response = _check_followup_budget(session, request)
        if budget_response is not None:
            return budget_response

    (
        workspace_root,
        local_workspace_root,
        workspace_path_style,
        workspace_root_source,
    ) = _resolve_workspace_fields(session=session)
    initial_state = {
        "cursor_system_prompt": cursor_system_prompt or None,
        "conversation_history": updated_execution_messages,
        "ternion_report": session.ternion_report_raw,
        "session_id": session.session_id,
        "execution_mode": session.execution_mode.value,
        "workspace_root": workspace_root,
        "local_workspace_root": local_workspace_root,
        "workspace_path_style": workspace_path_style,
        "workspace_root_source": workspace_root_source,
        "current_phase": resume_phase or "execution",
        "thinking_logs": [],
        "errors": [],
        "generated_code": session.generated_code,
        "review_feedback": session.review_feedback,
        "revision_count": session.revision_count,
        # Step E: Evidence chain state is required for execution-time Phase 1.5 top-ups.
        "evidence_bundle": str(getattr(session, "evidence_bundle", "") or ""),
        "evidence_gaps": str(getattr(session, "evidence_gaps", "") or ""),
        "evidence_requests": str(getattr(session, "evidence_requests", "") or ""),
        "evidence_items": list(getattr(session, "evidence_items", []) or []),
        "evidence_chain_index": list(getattr(session, "evidence_chain_index", []) or []),
        "evidence_topup_round": int(getattr(session, "evidence_topup_round", 0) or 0),
        "report_evidence_resume_phase": str(
            getattr(session, "report_evidence_resume_phase", "") or ""
        ),
        "baseline_file_snapshots": baseline,
        "modified_files": modified_files,
        "writer_output_files": writer_output_files,
        "optimizer_review_report": str(getattr(session, "optimizer_review_report", "") or ""),
        "stabilized_document_paths": stabilized_document_paths,
        "cursor_tools": cursor_tools,
        "cursor_tool_choice": cursor_tool_choice,
        "tool_results_meta": tool_results_meta,
    }

    if request.stream:
        cfg = config_store.load()
        show_phase_indicators = bool(getattr(cfg, "show_phase_indicators", True))

        stream_queue = StreamEventQueue()
        initial_state["_stream_queue"] = stream_queue

        async def generate_sse() -> AsyncGenerator[str, None]:
            """SSE generator that consumes events from the queue (execution follow-up)."""
            chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
            created = int(time.time())
            final_state: dict = {}
            streamed_content = ""
            pending_phase_indicator: str | None = None
            last_phase_start_emitted: str | None = None
            first_stream_delta_logged = False

            async def run_impl() -> None:
                nonlocal final_state
                try:
                    final_state = await run_implementation_stage(initial_state)
                except Exception as e:
                    logger.exception(
                        "streaming_execution_followup_error",
                        session_id=session.session_id,
                        error=str(e),
                    )
                    await _put_stream_exception(stream_queue, e, phase="execution_followup")
                finally:
                    stream_queue.close()

            impl_task = asyncio.create_task(run_impl())

            try:
                heartbeat_interval_seconds = 10

                async def on_timeout() -> str:
                    return await _sse_heartbeat_event(chunk_id, created, request.model)

                async def on_event(event: Any) -> AsyncGenerator[str, None]:
                    nonlocal first_stream_delta_logged
                    nonlocal last_phase_start_emitted
                    nonlocal pending_phase_indicator
                    nonlocal streamed_content
                    if event.event_type == StreamEventType.TOKEN_DELTA:
                        if event.delta:
                            if not first_stream_delta_logged:
                                log_manager.emit(
                                    level="INFO",
                                    category="WORKFLOW",
                                    message=(
                                        "execution_followup_stream_first_delta | "
                                        f"session_id={session.session_id} | "
                                        f"phase={str(event.phase or '')} | "
                                        f"delta_chars={len(event.delta)} | "
                                        f"streamed_chars_before={len(streamed_content)}"
                                    ),
                                )
                                first_stream_delta_logged = True
                            if pending_phase_indicator:
                                chunk = ChatCompletionChunk(
                                    id=chunk_id,
                                    created=created,
                                    model=request.model,
                                    choices=[
                                        StreamChoice(
                                            delta=ChoiceDelta(
                                                content="\n" + pending_phase_indicator
                                            )
                                        )
                                    ],
                                )
                                yield f"data: {chunk.model_dump_json()}\n\n"
                                pending_phase_indicator = None
                            streamed_content += event.delta
                            chunk = ChatCompletionChunk(
                                id=chunk_id,
                                created=created,
                                model=request.model,
                                choices=[StreamChoice(delta=ChoiceDelta(content=event.delta))],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"
                        return

                    if event.event_type == StreamEventType.PHASE_START:
                        if show_phase_indicators and event.phase:
                            phase_lower = str(event.phase or "").strip().lower()
                            should_emit_phase = phase_lower != last_phase_start_emitted
                            indicator = _phase_start_indicator_text(
                                event.phase, session_id=session.session_id
                            )
                            if indicator:
                                if should_emit_phase:
                                    chunk = ChatCompletionChunk(
                                        id=chunk_id,
                                        created=created,
                                        model=request.model,
                                        choices=[
                                            StreamChoice(
                                                delta=ChoiceDelta(content="\n" + indicator),
                                            )
                                        ],
                                    )
                                    yield f"data: {chunk.model_dump_json()}\n\n"
                                pending_phase_indicator = None
                            if phase_lower:
                                last_phase_start_emitted = phase_lower
                        return

                    if event.event_type == StreamEventType.ERROR:
                        error_text = _get_stream_error_text(event.metadata)
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=error_text))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
                        return

                async for sse_chunk in _consume_sse_events(
                    stream_queue=stream_queue,
                    heartbeat_interval_seconds=heartbeat_interval_seconds,
                    on_timeout=on_timeout,
                    on_event=on_event,
                ):
                    yield sse_chunk

                await impl_task

                pending_tool_calls = final_state.get("pending_tool_calls") or []
                if pending_tool_calls:
                    turn_outcome = _prepare_execution_pending_tool_calls_turn(
                        session=session,
                        final_state=final_state,
                        pending_tool_calls=pending_tool_calls,
                        updated_execution_messages=updated_execution_messages,
                        cursor_tools=cursor_tools,
                        workspace_root=workspace_root,
                        workspace_path_style=workspace_path_style,
                        workspace_root_source=workspace_root_source,
                        local_workspace_root=local_workspace_root,
                    )
                    if turn_outcome.blocked:
                        for sse_chunk in _sse_text_stop_chunks(
                            chunk_id, created, request.model, turn_outcome.blocked_message
                        ):
                            yield sse_chunk
                        return
                    for sse_chunk in _sse_tool_calls_chunks(
                        chunk_id, created, request.model, turn_outcome.cursor_tool_calls
                    ):
                        yield sse_chunk
                    return

                final_output = final_state.get("final_output", "") or final_state.get(
                    "generated_code", ""
                )
                errors = final_state.get("errors", []) or []
                error_backfill = ""
                if not final_output and not streamed_content and errors:
                    error_backfill = _build_stream_error_backfill(list(errors))
                new_stage = (
                    SessionStage.EXECUTED if not errors else SessionStage.EXECUTION_IN_PROGRESS
                )
                session_store.update_session(
                    session.session_id,
                    stage=new_stage,
                    pending_tool_calls=[],
                    generated_code=final_state.get("generated_code") or session.generated_code,
                    review_feedback=final_state.get("review_feedback") or session.review_feedback,
                    revision_count=final_state.get("revision_count", session.revision_count),
                    workflow_phase=str(
                        final_state.get("current_phase")
                        or getattr(session, "workflow_phase", "execution")
                        or "execution"
                    ),
                    modified_files=list(
                        final_state.get("modified_files")
                        or getattr(session, "modified_files", [])
                        or []
                    ),
                    baseline_file_snapshots=dict(
                        final_state.get("baseline_file_snapshots")
                        or getattr(session, "baseline_file_snapshots", {})
                        or {}
                    ),
                    writer_output_files=dict(
                        final_state.get("writer_output_files")
                        or getattr(session, "writer_output_files", {})
                        or {}
                    ),
                    stabilized_document_paths=list(
                        final_state.get("stabilized_document_paths")
                        or getattr(session, "stabilized_document_paths", [])
                        or []
                    ),
                    optimizer_review_report=str(
                        final_state.get("optimizer_review_report")
                        or getattr(session, "optimizer_review_report", "")
                        or ""
                    ),
                    evidence_bundle=str(
                        final_state.get("evidence_bundle")
                        or getattr(session, "evidence_bundle", "")
                        or ""
                    ),
                    evidence_gaps=str(
                        final_state.get("evidence_gaps")
                        or getattr(session, "evidence_gaps", "")
                        or ""
                    ),
                    evidence_requests=str(
                        final_state.get("evidence_requests")
                        or getattr(session, "evidence_requests", "")
                        or ""
                    ),
                    evidence_chain_index=list(
                        final_state.get("evidence_chain_index")
                        or getattr(session, "evidence_chain_index", [])
                        or []
                    ),
                    evidence_topup_round=int(
                        final_state.get(
                            "evidence_topup_round",
                            getattr(session, "evidence_topup_round", 0),
                        )
                        or 0
                    ),
                    report_evidence_resume_phase=str(
                        final_state.get("report_evidence_resume_phase")
                        or getattr(session, "report_evidence_resume_phase", "")
                        or ""
                    ),
                )

                log_manager.emit(
                    level="INFO",
                    category="WORKFLOW",
                    message=(
                        "execution_followup_stream_backfill_decision | "
                        f"session_id={session.session_id} | "
                        f"final_output_chars={len(final_output or '')} | "
                        f"streamed_chars={len(streamed_content)} | "
                        f"first_delta_logged={first_stream_delta_logged} | "
                        f"will_backfill={bool(final_output and not streamed_content)} | "
                        f"will_error_backfill={bool(error_backfill)}"
                    ),
                )

                if final_output and not streamed_content:
                    if pending_phase_indicator:
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[
                                StreamChoice(
                                    delta=ChoiceDelta(content="\n" + pending_phase_indicator)
                                )
                            ],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
                        pending_phase_indicator = None
                    for i in range(0, len(final_output), 128):
                        text = final_output[i : i + 128]
                        if not text:
                            continue
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
                elif error_backfill:
                    if pending_phase_indicator:
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[
                                StreamChoice(
                                    delta=ChoiceDelta(content="\n" + pending_phase_indicator)
                                )
                            ],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
                        pending_phase_indicator = None
                    for i in range(0, len(error_backfill), 128):
                        text = error_backfill[i : i + 128]
                        if not text:
                            continue
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[StreamChoice(delta=ChoiceDelta(content=text))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

                final_chunk = ChatCompletionChunk(
                    id=chunk_id,
                    created=created,
                    model=request.model,
                    choices=[StreamChoice(delta=ChoiceDelta(), finish_reason="stop")],
                )
                yield f"data: {final_chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            except asyncio.CancelledError:
                stream_queue.close()
                impl_task.cancel()
                with contextlib.suppress(BaseException):
                    await impl_task
                raise
            except Exception as e:
                logger.exception("sse_execution_followup_generation_error", error=str(e))
                error_chunk = ChatCompletionChunk(
                    id=chunk_id,
                    created=created,
                    model=request.model,
                    choices=[
                        StreamChoice(
                            delta=ChoiceDelta(content=t(MessageKey.STREAM_ERROR_INTERRUPTED))
                        )
                    ],
                )
                yield f"data: {error_chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                turn_lock.release()

        turn_lock.hand_off()
        return StreamingResponse(
            generate_sse(),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    final_state = await run_implementation_stage(initial_state)
    runtime_model_response = _get_runtime_model_unavailable_response_from_state(final_state)
    if runtime_model_response is not None:
        return runtime_model_response
    pending_tool_calls = final_state.get("pending_tool_calls") or []

    if pending_tool_calls:
        turn_outcome = _prepare_execution_pending_tool_calls_turn(
            session=session,
            final_state=final_state,
            pending_tool_calls=pending_tool_calls,
            updated_execution_messages=updated_execution_messages,
            cursor_tools=cursor_tools,
            workspace_root=workspace_root,
            workspace_path_style=workspace_path_style,
            workspace_root_source=workspace_root_source,
            local_workspace_root=local_workspace_root,
        )
        if turn_outcome.blocked:
            return _respond_with_text(request, turn_outcome.blocked_message)
        if request.stream:
            return StreamingResponse(
                create_sse_tool_calls_stream(
                    model=request.model,
                    tool_calls=turn_outcome.cursor_tool_calls,
                    content=None,
                ),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
            )
        return _tool_calls_json_response(request.model, turn_outcome.cursor_tool_calls)

    final_output = final_state.get("final_output", "") or final_state.get("generated_code", "")
    errors = final_state.get("errors", []) or []
    new_stage = SessionStage.EXECUTED if not errors else SessionStage.EXECUTION_IN_PROGRESS
    session_store.update_session(
        session.session_id,
        stage=new_stage,
        pending_tool_calls=[],
        generated_code=final_state.get("generated_code") or session.generated_code,
        review_feedback=final_state.get("review_feedback") or session.review_feedback,
        revision_count=final_state.get("revision_count", session.revision_count),
        workflow_phase=str(
            final_state.get("current_phase")
            or getattr(session, "workflow_phase", "execution")
            or "execution"
        ),
        modified_files=list(
            final_state.get("modified_files") or getattr(session, "modified_files", []) or []
        ),
        baseline_file_snapshots=dict(
            final_state.get("baseline_file_snapshots")
            or getattr(session, "baseline_file_snapshots", {})
            or {}
        ),
        writer_output_files=dict(
            final_state.get("writer_output_files")
            or getattr(session, "writer_output_files", {})
            or {}
        ),
        stabilized_document_paths=list(
            final_state.get("stabilized_document_paths")
            or getattr(session, "stabilized_document_paths", [])
            or []
        ),
        optimizer_review_report=str(
            final_state.get("optimizer_review_report")
            or getattr(session, "optimizer_review_report", "")
            or ""
        ),
        evidence_bundle=str(
            final_state.get("evidence_bundle") or getattr(session, "evidence_bundle", "") or ""
        ),
        evidence_gaps=str(
            final_state.get("evidence_gaps") or getattr(session, "evidence_gaps", "") or ""
        ),
        evidence_requests=str(
            final_state.get("evidence_requests") or getattr(session, "evidence_requests", "") or ""
        ),
        evidence_chain_index=list(
            final_state.get("evidence_chain_index")
            or getattr(session, "evidence_chain_index", [])
            or []
        ),
        evidence_topup_round=int(
            final_state.get("evidence_topup_round", getattr(session, "evidence_topup_round", 0))
            or 0
        ),
        report_evidence_resume_phase=str(
            final_state.get("report_evidence_resume_phase")
            or getattr(session, "report_evidence_resume_phase", "")
            or ""
        ),
    )

    if request.stream:
        return StreamingResponse(
            create_sse_stream(model=request.model, content=final_output),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
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
                headers=_SSE_HEADERS,
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
                headers=_SSE_HEADERS,
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
                    headers=_SSE_HEADERS,
                )
            else:
                return JSONResponse(
                    content=ChatCompletionResponse(
                        model=request.model,
                        choices=[
                            Choice(
                                message=ChatMessage(role=MessageRole.ASSISTANT, content=error_msg)
                            )
                        ],
                    ).model_dump()
                )
        if budget_warning == "BUDGET_WARNING":
            usage_summary = budget_manager.get_usage_summary()
            log_manager.emit(
                level="WARN",
                category="BUDGET",
                message=t(
                    MessageKey.LOG_BUDGET_WARNING, usage_pct=str(usage_summary.get("usage_pct", 0))
                ),
            )
            impl_budget_prefix = budget_manager.format_budget_warning(budget_warning)

        # Build initial state for implementation stage using session's confirmed report
        context = message_router.extract_context(request.messages)
        _apply_workspace_boundary_to_context(context, request.messages, session=session)

        # Restore original context from session if available (for better Writer context)
        original_ctx = session.original_context or {}
        conversation_history = original_ctx.get(
            "conversation_history", context.conversation_history
        )
        cursor_system_prompt = original_ctx.get(
            "cursor_system_prompt", context.cursor_system_prompt
        )

        (
            workspace_root,
            local_workspace_root,
            workspace_path_style,
            workspace_root_source,
        ) = _resolve_workspace_fields(original_context=original_ctx, session=session)
        initial_state = {
            "cursor_system_prompt": cursor_system_prompt,
            "conversation_history": conversation_history,
            "ternion_report": session.ternion_report_raw,  # Use raw for Writer (internal use)
            "session_id": session.session_id,
            "execution_mode": session.execution_mode.value,
            "workspace_root": workspace_root,
            "local_workspace_root": local_workspace_root,
            "workspace_path_style": workspace_path_style,
            "workspace_root_source": workspace_root_source,
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
                show_phase_indicators=bool(getattr(config, "show_phase_indicators", True)),
            )

        # Non-streaming execution
        final_state = await run_implementation_stage(initial_state)
        runtime_model_response = _get_runtime_model_unavailable_response_from_state(final_state)
        if runtime_model_response is not None:
            return runtime_model_response

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
            output_parts.append(t(MessageKey.EXECUTION_NO_OUTPUT))

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
    _apply_workspace_boundary_to_context(context, request.messages, session=session)
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
    runtime_model_response = _get_runtime_model_unavailable_response_from_state(final_state)
    if runtime_model_response is not None:
        return runtime_model_response

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

    output = "".join(output_parts) if output_parts else t(MessageKey.REANALYSIS_COMPLETED)

    if request.stream:
        return StreamingResponse(
            create_sse_stream(model=request.model, content=output),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
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

    mode_desc = t(
        MessageKey.EXECUTION_MODE_DESC_TERNION_FULL
        if session.execution_mode == ExecutionMode.TERNION_FULL
        else MessageKey.EXECUTION_MODE_DESC_CURSOR_HANDOFF
    )

    answer_text = (
        t(MessageKey.CLARIFY_ANSWER_WITH_EXCERPT)
        if excerpt
        else t(MessageKey.CLARIFY_ANSWER_NO_EXCERPT)
    )
    excerpt_block = f"\n\n### Relevant excerpt from the report\n\n{excerpt}" if excerpt else ""

    # Build a response that addresses the question without re-running RCA
    clarification_response = t(
        MessageKey.CLARIFY_RESPONSE_TEMPLATE,
        blockquote=_as_blockquote(safe_question),
        answer_text=answer_text,
        excerpt_block=excerpt_block,
        mode_desc=mode_desc,
        session_id=session.session_id,
        execution_mode=session.execution_mode.value,
        report_hash=session.report_hash or "",
    )

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
            headers=_SSE_HEADERS,
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

        # User-visible reminder message (CURSOR_HANDOFF).
        reminder = t(
            MessageKey.POST_EXEC_CURSOR_HANDOFF_REMINDER,
            handoff_output=handoff_output,
            session_markers=session_markers,
        )

        if request.stream:
            return StreamingResponse(
                create_sse_stream(model=request.model, content=reminder),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
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
        completion_notice = t(
            MessageKey.POST_EXEC_TERNION_FULL_COMPLETE,
            session_id=session.session_id,
            stage_display=session.stage.value.replace("_", " ").title(),
            session_markers=session_markers,
        )

        if request.stream:
            return StreamingResponse(
                create_sse_stream(model=request.model, content=completion_notice),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
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
        truncated = session.last_user_feedback[:200]
        ellipsis = "..." if len(session.last_user_feedback) > 200 else ""
        feedback_section = f"\n**Your Previous Feedback**:\n> {truncated}{ellipsis}\n"

    guidance = t(
        MessageKey.REJECTED_SESSION_GUIDANCE,
        feedback_section=feedback_section,
        session_id=session.session_id,
        mode_display=session.execution_mode.value.replace("_", " ").title(),
        session_markers=session_markers,
    )

    if request.stream:
        return StreamingResponse(
            create_sse_stream(model=request.model, content=guidance),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
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
    mode_desc = t(
        MessageKey.EXECUTION_MODE_DESC_TERNION_FULL
        if session.execution_mode == ExecutionMode.TERNION_FULL
        else MessageKey.EXECUTION_MODE_DESC_CURSOR_HANDOFF
    )

    clarification = t(
        MessageKey.UNKNOWN_INTENT_RESPONSE,
        mode_desc=mode_desc,
        session_id=session.session_id,
        execution_mode=session.execution_mode.value,
        report_hash=session.report_hash or "",
    )

    if request.stream:
        return StreamingResponse(
            create_sse_stream(model=request.model, content=clarification),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
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

    missing = t(MessageKey.REPORT_SECTION_MISSING_PLACEHOLDER)
    parsed = parse_structured_report(ternion_report_safe)
    if parsed.is_structured:
        structured_body = (
            f"### {_get_report_section_title('root_cause')}\n\n"
            f"{parsed.root_cause or f'- ({missing}) Root cause section not found in report.'}\n\n"
            f"---\n\n"
            f"### {_get_report_section_title('evidence')}\n\n"
            f"{parsed.evidence or f'- ({missing}) Evidence section not found in report.'}\n\n"
            f"---\n\n"
            f"### {_get_report_section_title('scope')}\n\n"
            f"{parsed.scope or f'- ({missing}) Scope section not found in report.'}\n\n"
            f"---\n\n"
            f"### {_get_report_section_title('fix_plan')}\n\n"
            f"{parsed.fix_plan or f'- ({missing}) Fix plan section not found in report.'}\n\n"
            f"---\n\n"
            f"### {_get_report_section_title('verification')}\n\n"
            f"{parsed.verification or f'- ({missing}) Verification section not found in report.'}\n\n"
            f"---\n\n"
            f"### {_get_report_section_title('risks')}\n\n"
            f"{parsed.risks or f'- ({missing}) Risks section not found in report.'}\n\n"
            f"---\n\n"
            f"### {_get_report_section_title('if_not_effective')}\n\n"
            f"{parsed.if_not_effective or f'- ({missing}) Fallback section not found in report.'}"
        )
    else:
        structured_body = f"### Confirmed Analysis Report (Unstructured)\n\n{ternion_report_safe}"

    header = t(MessageKey.HANDOFF_PACKAGE_HEADER)
    next_action = t(MessageKey.HANDOFF_PACKAGE_NEXT_ACTION)
    return f"{header}\n\n---\n\n{structured_body}\n\n---\n\n{next_action}"

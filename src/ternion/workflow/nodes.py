"""
Node implementations for the Ternion LangGraph workflow.

Each node represents a step in the 4-step discussion flow.
"""

import asyncio
import json
import re
from typing import Any

import structlog

from ternion.core.budget import budget_manager
from ternion.core.config import settings
from ternion.core.deliverable_policy import (
    format_deliverable_policy_for_prompt,
    resolve_deliverable_policy,
)
from ternion.core.config_store import config_store
from ternion.core.exceptions import TimeoutError as TernionTimeout
from ternion.core.intent_classifier import get_latest_user_message
from ternion.core.models import ChatMessage, MessageRole
from ternion.core.session_store import (
    ExecutionMode,
    session_store,
)
from ternion.providers.base import ProviderResponse
from ternion.providers.manager import provider_manager
from ternion.router.prompts import (
    ARBITER_EVIDENCE_PROMPT,
    ARBITER_REPORT_EVIDENCE_PROMPT,
    CONVERGENCE_PROMPT,
    DIVERGENCE_PROMPT,
    EXECUTION_PROMPT,
    FINAL_CHECK_PROMPT,
    GLOBAL_SECURITY_RULES,
    OPTIMIZER_PROMPT,
)
from ternion.utils.cursor_safety import sanitize_for_cursor_display, sanitize_for_preview
from ternion.utils.evidence_chain import (
    merge_missing_purpose_gaps,
    parse_evidence_requests,
    reconcile_evidence_chain,
)
from ternion.utils.evidence_requests_protocol import (
    EVIDENCE_REQUESTS_BEGIN,
    extract_evidence_requests_block,
)
from ternion.utils.i18n import MessageKey, t
from ternion.utils.language_resources import (
    get_language_name,
    get_optimizer_language_instruction_template,
    get_report_language_instruction_template,
)
from ternion.utils.log_manager import log_manager
from ternion.utils.report_parser import format_report_for_display, parse_structured_report
from ternion.utils.tool_policy import EXECUTION_ALLOWED_TOOL_CANONICAL
from ternion.utils.tool_calls_parser import (
    TOOL_CALLS_BEGIN,
    build_text_tool_calls_instruction,
    decode_stream_tool_calls,
    extract_tool_calls_from_text,
)
from ternion.utils.workflow_prompt_capture import (
    build_workflow_prompt_payload,
    schedule_workflow_prompt_capture,
)
from ternion.workflow.state import ReviewResult, TernionState, WorkflowPhase
from ternion.workflow.streaming_events import StreamEventQueue

logger = structlog.get_logger(__name__)

# Optimizer output wrapper markers (development override).
_OPTIMIZER_INTERNAL_BEGIN = "TERNION_OPTIMIZER_INTERNAL_REPORT_BEGIN"
_OPTIMIZER_INTERNAL_END = "TERNION_OPTIMIZER_INTERNAL_REPORT_END"
_OPTIMIZER_USER_BEGIN = "TERNION_OPTIMIZER_USER_SUMMARY_BEGIN"
_OPTIMIZER_USER_END = "TERNION_OPTIMIZER_USER_SUMMARY_END"

_ROLE_DISPLAY_NAMES = {
    "ternion_a": "Ternion A",
    "ternion_b": "Ternion B",
    "ternion_c": "Ternion C",
    "arbiter": "Arbiter",
    "writer": "Writer",
    "reviewer": "Reviewer",
    "optimizer": "Optimizer",
}


def _extract_report_scope_for_policy(report: str) -> str:
    """
    Extract Scope/Non-Goals content for deliverable classification.
    """
    parsed = parse_structured_report(report or "")
    if parsed.is_structured and parsed.scope.strip():
        return parsed.scope
    return report or ""

# Default timeout for provider calls (CR-030)
DEFAULT_TIMEOUT_SECONDS = settings.discussion.timeout_seconds
WRITER_TIMEOUT_SECONDS = max(DEFAULT_TIMEOUT_SECONDS, settings.discussion.writer_timeout_seconds)

_MAX_EVIDENCE_TOPUP_ROUNDS = 2


def _validate_evidence_topup_request(*, used_round: int, final_request: bool) -> str | None:
    """
    Validate execution-time evidence top-up guardrails.

    Guardrails (Step E):
    - Max 2 top-up rounds across Writer + Optimizer.
    - The 2nd request must be explicitly marked as the final request.
    """
    used = int(used_round or 0)
    if used >= _MAX_EVIDENCE_TOPUP_ROUNDS:
        return t(
            MessageKey.EVIDENCE_TOPUP_LIMIT_REACHED,
            max_rounds=str(_MAX_EVIDENCE_TOPUP_ROUNDS),
        )

    if used == _MAX_EVIDENCE_TOPUP_ROUNDS - 1 and not final_request:
        return t(MessageKey.EVIDENCE_TOPUP_FINAL_REQUIRED)

    return None


def _validate_evidence_requests_payload(requests_text: str) -> str | None:
    """
    Validate evidence_requests payload format for execution-time top-ups.

    Requirements (Step E):
    - Must contain at least one actionable request.
    - Each request must include a PURPOSE line (stored as metadata, not excerpt).
    """
    entries = parse_evidence_requests(requests_text or "")
    if not entries:
        return t(MessageKey.EVIDENCE_TOPUP_REQUESTS_EMPTY)

    missing_purpose = [e.request for e in entries if not (e.purpose or "").strip()]
    if not missing_purpose:
        return None

    display = "\n".join(f"- {item}" for item in missing_purpose[:8])
    if len(missing_purpose) > 8:
        display += f"\n- ... (+{len(missing_purpose) - 8})"
    return t(MessageKey.EVIDENCE_TOPUP_PURPOSE_REQUIRED, missing_items=display)


async def _call_with_timeout(
    provider: Any,
    messages: list[ChatMessage],
    model: str,
    temperature: float,
    timeout_seconds: int | None = None,
    **kwargs: Any,
) -> Any:
    """
    Call provider.chat_completion with timeout protection (CR-030).

    Args:
        provider: Provider instance with chat_completion method
        messages: Chat messages
        model: Model to use
        temperature: Sampling temperature
        timeout_seconds: Optional timeout override

    Returns:
        ProviderResponse from the provider

    Raises:
        TernionTimeout: If request times out (status_code=504)
    """
    timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS
    try:
        return await asyncio.wait_for(
            provider.chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                **kwargs,
            ),
            timeout=timeout,
        )
    except TimeoutError:
        log_manager.emit(
            "ERROR",
            "LLM",
            f"Provider timeout: {provider.name} did not respond within {timeout}s",
        )
        raise TernionTimeout(
            operation=f"chat_completion ({provider.name})",
            timeout_seconds=timeout,
        ) from None


async def _call_with_stream(
    provider: Any,
    messages: list[ChatMessage],
    model: str,
    temperature: float,
    stream_queue: StreamEventQueue | None = None,
    phase: str = "",
    message_id: str = "",
    timeout_seconds: int | None = None,
    detect_tool_calls: bool = False,
    tool_calls_guard_chars: int = 256,
    tool_calls_auto_retry_max: int = 1,
    **kwargs: Any,
) -> ProviderResponse:
    """
    Call provider.chat_completion_stream with real-time token forwarding.

    This function streams LLM output tokens to the provided queue while
    accumulating the full response. If no queue is provided, falls back
    to non-streaming call.

    Args:
        provider: Provider instance with chat_completion_stream method
        messages: Chat messages
        model: Model to use
        temperature: Sampling temperature
        stream_queue: Optional queue to receive incremental tokens
        phase: Current workflow phase (for event metadata)
        message_id: Message identifier (for event metadata)
        timeout_seconds: Optional timeout override

    Returns:
        ProviderResponse with the complete generated content

    Raises:
        TernionTimeout: If request times out
    """
    # If no queue provided, fall back to non-streaming call
    if stream_queue is None:
        return await _call_with_timeout(
            provider=provider,
            messages=messages,
            model=model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            **kwargs,
        )

    timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS
    full_content = ""

    try:
        # Signal phase start
        await stream_queue.put_phase_start(phase, provider=provider.name, model=model)

        # Create stream generator
        stream_gen = provider.chat_completion_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            **kwargs,
        )

        # Consume stream with an idle timeout between chunks.
        async def consume_stream() -> ProviderResponse:
            nonlocal full_content

            retry_remaining = max(0, int(tool_calls_auto_retry_max or 0))
            buffered = ""
            buffered_flushed = False
            emitted_any_token = False
            tool_calls: list[dict[str, Any]] | None = None
            tool_calls_detected = False
            full_parts: list[str] = []
            marker_tail = ""
            marker_len = len(TOOL_CALLS_BEGIN)

            try:
                guard_chars = max(0, int(tool_calls_guard_chars))
            except Exception:
                guard_chars = 256
            if not detect_tool_calls:
                guard_chars = 0

            # Step E (P2-1): Short-window buffering to avoid streaming an invalid
            # evidence top-up protocol block before guardrails validate it.
            topup_marker = EVIDENCE_REQUESTS_BEGIN
            topup_probe_enabled = str(phase or "").strip().lower() in (
                WorkflowPhase.EXECUTION.value,
                WorkflowPhase.OPTIMIZER.value,
            )
            topup_decision: bool | None = None
            suppress_stream_tokens = False

            def _maybe_is_evidence_topup_start(text: str) -> bool | None:
                probe = (text or "").lstrip()
                if not probe:
                    return None
                if probe.startswith(topup_marker):
                    return True
                # Keep buffering while the current probe is a prefix of the marker.
                if topup_marker.startswith(probe) and len(probe) < len(topup_marker):
                    return None
                return False

            async def _retry_tool_calls_only() -> list[dict[str, Any]] | None:
                nonlocal retry_remaining
                if retry_remaining <= 0:
                    return None
                retry_remaining -= 1
                retry_instruction = (
                    "[TOOL_CALLS_ONLY_RETRY]\n\n"
                    "You MUST return tool calls ONLY. The assistant content MUST be empty.\n"
                    "Do NOT output any prose, analysis, or code fences.\n"
                    "If native tool calling is available, return tool_calls.\n"
                    "If you are using a text-based tool-calls protocol, output ONLY the tool-calls block.\n"
                )
                retry_messages = list(messages)
                retry_messages.append(
                    ChatMessage(
                        role=MessageRole.USER,
                        content=retry_instruction,
                    )
                )
                try:
                    retry_response = await _call_with_timeout(
                        provider=provider,
                        messages=retry_messages,
                        model=model,
                        temperature=min(float(temperature or 0.2), 0.2),
                        timeout_seconds=timeout_seconds,
                        **kwargs,
                    )
                except Exception as e:
                    logger.warning(
                        "tool_calls_only_retry_failed",
                        phase=phase,
                        provider=provider.name,
                        error=str(e),
                    )
                    return None

                if retry_response.tool_calls:
                    return retry_response.tool_calls

                parsed = extract_tool_calls_from_text(retry_response.content)
                if parsed:
                    return parsed

                return None

            while True:
                try:
                    chunk = await asyncio.wait_for(stream_gen.__anext__(), timeout=timeout)
                except StopAsyncIteration:
                    break
                if not chunk:
                    continue

                if detect_tool_calls:
                    decoded = decode_stream_tool_calls(chunk)
                    if decoded is not None:
                        tool_calls_detected = True
                        tool_calls = decoded
                        buffered = ""
                        continue

                full_parts.append(chunk)

                if detect_tool_calls and not tool_calls_detected:
                    scan = marker_tail + chunk
                    if TOOL_CALLS_BEGIN in scan:
                        tool_calls_detected = True
                        buffered = ""
                        marker_tail = ""
                        continue
                    if marker_len > 1:
                        marker_tail = scan[-(marker_len - 1):]

                if tool_calls_detected:
                    continue

                if suppress_stream_tokens:
                    continue

                if topup_probe_enabled and topup_decision is None and not emitted_any_token:
                    # Buffer until we can deterministically decide whether the output is a
                    # top-up protocol block (which must be the first non-empty line).
                    buffered += chunk
                    topup_decision = _maybe_is_evidence_topup_start(buffered)
                    if topup_decision is None:
                        continue
                    if topup_decision is True:
                        # Suppress streaming for this response to avoid UI noise; the caller
                        # will parse/validate the full content and may soft-retry if needed.
                        suppress_stream_tokens = True
                        buffered = ""
                        buffered_flushed = True
                        continue

                    # Not a top-up block. Flush (or continue buffering) per the guard_chars policy.
                    if guard_chars > 0 and not buffered_flushed:
                        if len(buffered) >= guard_chars:
                            await stream_queue.put_token(
                                delta=buffered,
                                phase=phase,
                                message_id=message_id,
                            )
                            emitted_any_token = True
                            buffered = ""
                            buffered_flushed = True
                        continue

                    await stream_queue.put_token(
                        delta=buffered,
                        phase=phase,
                        message_id=message_id,
                    )
                    emitted_any_token = True
                    buffered = ""
                    buffered_flushed = True
                    continue

                if guard_chars > 0 and not buffered_flushed:
                    buffered += chunk
                    if len(buffered) >= guard_chars:
                        await stream_queue.put_token(
                            delta=buffered,
                            phase=phase,
                            message_id=message_id,
                        )
                        emitted_any_token = True
                        buffered = ""
                        buffered_flushed = True
                    continue

                await stream_queue.put_token(
                    delta=chunk,
                    phase=phase,
                    message_id=message_id,
                )
                emitted_any_token = True

            full_content = "".join(full_parts)
            if tool_calls_detected:
                if tool_calls is None:
                    tool_calls = extract_tool_calls_from_text(full_content)

                mixed_stream = bool(detect_tool_calls and emitted_any_token)
                if mixed_stream or not tool_calls:
                    retry_tool_calls = await _retry_tool_calls_only()
                    if retry_tool_calls:
                        tool_calls = retry_tool_calls
                    elif mixed_stream:
                        logger.warning(
                            "tool_calls_only_retry_mixed_stream_fallback",
                            phase=phase,
                            provider=provider.name,
                        )

                if tool_calls:
                    return ProviderResponse(
                        content="",
                        finish_reason="tool_calls",
                        tool_calls=tool_calls,
                        usage={},
                    )
                raise ValueError("stream_detected_tool_calls_but_parse_failed")

            if buffered and not buffered_flushed:
                await stream_queue.put_token(
                    delta=buffered,
                    phase=phase,
                    message_id=message_id,
                )

            return ProviderResponse(
                content=full_content,
                finish_reason="stop",
                usage={},
            )

        response = await consume_stream()
        full_content = response.content or ""

        # Signal completion with final content
        await stream_queue.put_final(
            content=full_content,
            phase=phase,
            message_id=message_id,
        )

        # Note: Token usage is tracked inside provider.chat_completion_stream.
        return response

    except TimeoutError:
        log_manager.emit(
            "ERROR",
            "LLM",
            f"Provider stream timeout: {provider.name} did not complete within {timeout}s",
        )
        await stream_queue.put_error(
            f"Stream timeout after {timeout}s",
            phase=phase,
        )
        raise TernionTimeout(
            operation=f"chat_completion_stream ({provider.name})",
            timeout_seconds=timeout,
        ) from None
    except Exception as e:
        logger.exception("stream_error", provider=provider.name, error=str(e))
        await stream_queue.put_error(str(e), phase=phase)
        raise


async def _call_optimizer_with_stream(
    provider: Any,
    messages: list[ChatMessage],
    model: str,
    temperature: float,
    stream_queue: StreamEventQueue | None,
    *,
    phase: str,
    message_id: str,
    timeout_seconds: int | None = None,
    detect_tool_calls: bool = False,
    tool_calls_auto_retry_max: int = 1,
    **kwargs: Any,
) -> tuple[ProviderResponse, bool]:
    """
    Optimizer-specific streaming wrapper.

    This streams ONLY the user-visible summary section (between the Optimizer wrapper
    markers) to avoid leaking the internal optimizer report in Cursor chat output.
    """
    if stream_queue is None:
        response = await _call_with_timeout(
            provider=provider,
            messages=messages,
            model=model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            **kwargs,
        )
        return response, False

    timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS
    full_parts: list[str] = []
    emitted_any = False
    retry_remaining = max(0, int(tool_calls_auto_retry_max or 0))

    try:
        await stream_queue.put_phase_start(phase, provider=provider.name, model=model)

        stream_gen = provider.chat_completion_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            **kwargs,
        )

        tool_calls: list[dict[str, Any]] | None = None
        tool_calls_detected = False
        marker_tail = ""
        marker_len = len(TOOL_CALLS_BEGIN)

        user_started = False
        user_done = False
        begin_tail = ""
        end_tail = ""
        begin_len = len(_OPTIMIZER_USER_BEGIN)
        begin_keep = begin_len - 1 if begin_len > 1 else 0
        end_len = len(_OPTIMIZER_USER_END)
        end_keep = end_len - 1 if end_len > 1 else 0

        # Stream-safe sanitization: keep a small tail to prevent cross-chunk trigger formation.
        tail_len = 32
        user_emit_buffer_raw = ""

        async def _retry_tool_calls_only() -> list[dict[str, Any]] | None:
            nonlocal retry_remaining
            if retry_remaining <= 0:
                return None
            retry_remaining -= 1
            retry_instruction = (
                "[TOOL_CALLS_ONLY_RETRY]\n\n"
                "You MUST return tool calls ONLY. The assistant content MUST be empty.\n"
                "Do NOT output any wrapper markers or prose.\n"
            )
            retry_messages = list(messages)
            retry_messages.append(
                ChatMessage(
                    role=MessageRole.USER,
                    content=retry_instruction,
                )
            )
            try:
                retry_response = await _call_with_timeout(
                    provider=provider,
                    messages=retry_messages,
                    model=model,
                    temperature=min(float(temperature or 0.2), 0.2),
                    timeout_seconds=timeout_seconds,
                    **kwargs,
                )
            except Exception as e:
                logger.warning(
                    "optimizer_tool_calls_only_retry_failed",
                    phase=phase,
                    provider=provider.name,
                    error=str(e),
                )
                return None

            if retry_response.tool_calls:
                return retry_response.tool_calls

            parsed = extract_tool_calls_from_text(retry_response.content)
            if parsed:
                return parsed

            return None

        while True:
            try:
                chunk = await asyncio.wait_for(stream_gen.__anext__(), timeout=timeout)
            except StopAsyncIteration:
                break
            if not chunk:
                continue

            if detect_tool_calls and not tool_calls_detected:
                decoded = decode_stream_tool_calls(chunk)
                if decoded is not None:
                    tool_calls_detected = True
                    tool_calls = decoded
                    continue

            full_parts.append(chunk)

            if detect_tool_calls and not tool_calls_detected:
                scan = marker_tail + chunk
                if TOOL_CALLS_BEGIN in scan:
                    tool_calls_detected = True
                    marker_tail = ""
                    continue
                if marker_len > 1:
                    marker_tail = scan[-(marker_len - 1):]

            if tool_calls_detected:
                continue

            if user_done:
                continue

            visible_chunk = ""
            if not user_started:
                scan = begin_tail + chunk
                idx = scan.find(_OPTIMIZER_USER_BEGIN)
                if idx < 0:
                    if begin_keep > 0:
                        begin_tail = scan[-begin_keep:]
                    continue

                user_started = True
                begin_tail = ""
                visible_chunk = scan[idx + len(_OPTIMIZER_USER_BEGIN):].lstrip("\n\r")
            else:
                visible_chunk = chunk

            if not user_started:
                continue

            if not visible_chunk:
                continue

            scan = end_tail + visible_chunk
            end_idx = scan.find(_OPTIMIZER_USER_END)
            if end_idx < 0:
                if end_keep > 0:
                    if len(scan) <= end_keep:
                        end_tail = scan
                        continue
                    visible = scan[:-end_keep]
                    end_tail = scan[-end_keep:]
                else:
                    visible = scan
                    end_tail = ""
            else:
                visible = scan[:end_idx]
                end_tail = ""
                user_done = True

            if not visible:
                continue

            user_emit_buffer_raw += visible
            if user_done or len(user_emit_buffer_raw) > tail_len:
                if user_done:
                    flush_raw = user_emit_buffer_raw
                    user_emit_buffer_raw = ""
                else:
                    flush_raw = user_emit_buffer_raw[:-tail_len]
                    user_emit_buffer_raw = user_emit_buffer_raw[-tail_len:]

                safe = sanitize_for_cursor_display(flush_raw)
                if safe:
                    await stream_queue.put_token(
                        delta=safe,
                        phase=phase,
                        message_id=message_id,
                    )
                    emitted_any = True

        full_content = "".join(full_parts)
        if tool_calls_detected:
            if tool_calls is None:
                tool_calls = extract_tool_calls_from_text(full_content)
            mixed_stream = bool(detect_tool_calls and emitted_any)
            if mixed_stream or not tool_calls:
                retry_tool_calls = await _retry_tool_calls_only()
                if retry_tool_calls:
                    tool_calls = retry_tool_calls
                elif mixed_stream:
                    logger.warning(
                        "optimizer_tool_calls_only_retry_mixed_stream_fallback",
                        phase=phase,
                        provider=provider.name,
                    )
            if tool_calls:
                return (
                    ProviderResponse(
                        content="",
                        finish_reason="tool_calls",
                        tool_calls=tool_calls,
                        usage={},
                    ),
                    False,
                )
            raise ValueError("optimizer_stream_detected_tool_calls_but_parse_failed")

        if user_started and not user_done:
            if end_tail:
                user_emit_buffer_raw += end_tail
                end_tail = ""
            safe_tail = sanitize_for_cursor_display(user_emit_buffer_raw) if user_emit_buffer_raw else ""
            if safe_tail:
                await stream_queue.put_token(
                    delta=safe_tail,
                    phase=phase,
                    message_id=message_id,
                )
                emitted_any = True

        await stream_queue.put_final(
            content="",
            phase=phase,
            message_id=message_id,
        )

        return (
            ProviderResponse(
                content=full_content,
                finish_reason="stop",
                usage={},
            ),
            emitted_any,
        )
    except TimeoutError:
        log_manager.emit(
            "ERROR",
            "LLM",
            f"Provider stream timeout: {provider.name} did not complete within {timeout}s",
        )
        await stream_queue.put_error(
            f"Stream timeout after {timeout}s",
            phase=phase,
        )
        raise TernionTimeout(
            operation=f"chat_completion_stream ({provider.name})",
            timeout_seconds=timeout,
        ) from None
    except Exception as e:
        logger.exception("optimizer_stream_error", provider=provider.name, error=str(e))
        await stream_queue.put_error(str(e), phase=phase)
        raise


def _prepend_global_security_rules(prompt: str) -> str:
    """
    Prepend global security rules to a phase-specific system prompt.

    This keeps provider compatibility by emitting a single system prompt string.
    """
    rules = GLOBAL_SECURITY_RULES.strip()
    if not rules:
        return prompt
    return f"{rules}\n\n{prompt}"


def _append_global_security_rules(prompt: str) -> str:
    """
    Append global security rules to an external system prompt.

    This is used for preserving the client's system prompt semantics while
    ensuring global security constraints remain present.
    """
    rules = GLOBAL_SECURITY_RULES.strip()
    if not rules:
        return prompt
    prompt = prompt.strip()
    if not prompt:
        return rules
    return f"{prompt}\n\n{rules}"


def _parse_review_status(review_content: str) -> ReviewResult:
    """
    Parse the review status from the reviewer output.

    The primary protocol is a strict first-line status marker:
    - TERNION_REVIEW_STATUS=APPROVED
    - TERNION_REVIEW_STATUS=REVISION_NEEDED

    Falls back to legacy markers for backward compatibility.
    """
    text = (review_content or "").strip()
    first_line = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            first_line = stripped
            break

    if first_line == "TERNION_REVIEW_STATUS=APPROVED":
        return ReviewResult.APPROVED
    if first_line == "TERNION_REVIEW_STATUS=REVISION_NEEDED":
        return ReviewResult.REVISION_NEEDED

    lowered = text.lower()
    if "status: approved" in lowered or "lgtm" in lowered:
        return ReviewResult.APPROVED
    if "status: revision needed" in lowered:
        return ReviewResult.REVISION_NEEDED

    return ReviewResult.REVISION_NEEDED


def _format_role_names(role_ids: list[str]) -> str:
    names = [_ROLE_DISPLAY_NAMES.get(role_id, role_id) for role_id in role_ids]
    return ", ".join([name for name in names if name])


def _format_evidence_section(
    lines: list[str],
    *,
    header: str,
    default_line: str,
) -> str:
    if not any(line.strip() for line in lines):
        return f"{header}\n{default_line}"
    return "\n".join([header, *lines]).rstrip()


def _build_execution_policy_context(
    *,
    ternion_report: str,
    latest_user_message: str,
    evidence_bundle: str,
    evidence_gaps: str,
    evidence_chain_index: list[dict[str, object]],
    evidence_topup_round: int,
) -> tuple[str, list[str], list[str]]:
    report_for_policy = _extract_report_scope_for_policy(ternion_report)
    deliverable_policy = resolve_deliverable_policy(latest_user_message, report_for_policy)
    deliverable_policy_text = format_deliverable_policy_for_prompt(deliverable_policy)
    try:
        evidence_index_json = json.dumps(evidence_chain_index, ensure_ascii=False, indent=2)
    except Exception:
        evidence_index_json = "[]"
    evidence_chain_lines = [
        "\n\n[REPORT_EVIDENCE_CHAIN - VERBATIM]\n\n",
        evidence_bundle,
        "\n\n",
        evidence_gaps,
        "\n\nEVIDENCE_CHAIN_INDEX_JSON:\n",
        evidence_index_json,
    ]
    topup_rounds_remaining = max(0, _MAX_EVIDENCE_TOPUP_ROUNDS - evidence_topup_round)
    topup_status_lines = [
        "\n\n[EVIDENCE_TOPUP_STATUS]\n\n",
        f"TOPUP_ROUND_USED: {evidence_topup_round}\n",
        f"TOPUP_MAX_ROUNDS: {_MAX_EVIDENCE_TOPUP_ROUNDS}\n",
        f"TOPUP_ROUNDS_REMAINING: {topup_rounds_remaining}\n",
        "RULES:\n",
        "- If evidence is insufficient and TOPUP_ROUNDS_REMAINING > 0, use the Phase 1.5 protocol block.\n",
        "- Before requesting evidence top-up, you MUST consult EVIDENCE_CHAIN_INDEX_JSON and must NOT request items already satisfied.\n",
        "- If TOPUP_ROUNDS_REMAINING == 0, you MUST proceed with the requested deliverable using existing evidence.\n",
        "- If EVIDENCE_GAPS contains [MISSING_PURPOSE], it indicates missing PURPOSE metadata (not missing code). Do NOT request additional code just to satisfy it; if PURPOSE is needed for traceability, request the SAME ref range and include a PURPOSE line.\n",
    ]
    if topup_rounds_remaining == 1:
        topup_status_lines.append(
            "- This is the LAST allowed top-up. Any top-up request MUST set FINAL_REQUEST: true.\n"
        )
    return deliverable_policy_text, evidence_chain_lines, topup_status_lines


def _parse_evidence_output(content: str) -> tuple[str, str]:
    text = (content or "").strip()
    bundle_header = "EVIDENCE_BUNDLE:"
    gaps_header = "EVIDENCE_GAPS:"
    bundle_lines: list[str] = []
    gaps_lines: list[str] = []
    section: str | None = None
    found_bundle = False
    found_gaps = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped == bundle_header:
            section = "bundle"
            found_bundle = True
            continue
        if stripped == gaps_header:
            section = "gaps"
            found_gaps = True
            continue
        if section == "bundle":
            bundle_lines.append(line)
        elif section == "gaps":
            gaps_lines.append(line)

    if not found_bundle and not found_gaps:
        fallback = text if text else "- None"
        return (
            f"{bundle_header}\n{fallback}".rstrip(),
            f"{gaps_header}\n- None",
        )

    bundle = _format_evidence_section(
        bundle_lines,
        header=bundle_header,
        default_line="- None",
    )
    gaps = _format_evidence_section(
        gaps_lines,
        header=gaps_header,
        default_line="- None",
    )
    return bundle, gaps


def _extract_evidence_requests(analyses: list[dict[str, Any]]) -> str:
    def is_none_marker(line: str) -> bool:
        normalized = line.strip()
        if not normalized:
            return False
        normalized = normalized.lower()
        return normalized in ("- [p0] none", "[p0] none")

    requests: list[str] = []
    for analysis in analyses:
        text = (analysis.get("analysis") or "").splitlines()
        capture = False
        for line in text:
            stripped = line.strip()
            if stripped.lower().startswith("### 5. evidence_requests"):
                capture = True
                continue
            if capture and stripped.startswith("###"):
                break
            if capture and stripped:
                requests.append(stripped)
    if not requests:
        return "- [P0] None"

    # Canonicalize the empty marker to avoid downstream heuristic ambiguity.
    non_empty = [line for line in requests if line.strip()]
    if non_empty and all(is_none_marker(line) for line in non_empty):
        return "- [P0] None"
    return "\n".join(requests)


def _filter_conversation_history_for_analysis(
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Filter conversation history for analysis/report phases.

    This removes tool-result messages and tool-call artifacts so that:
    - Council/Arbiter only see user/assistant dialogue context
    - Evidence is provided exclusively via evidence_bundle/evidence_gaps
    - Token usage stays predictable (avoid carrying raw tool outputs)

    Args:
        history: Conversation history list (OpenAI-compatible message dicts).

    Returns:
        Filtered history containing only user/assistant messages with content.
    """
    filtered: list[dict[str, Any]] = []
    for msg in history:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue

        content = msg.get("content")
        if content is None:
            continue
        if isinstance(content, str) and not content.strip():
            continue

        filtered.append(
            {
                "role": role,
                "content": content,
                "name": msg.get("name"),
                # Intentionally omit tool_calls/tool_call_id to keep downstream context clean.
            }
        )
    return filtered


def _collect_tool_call_ids(tool_calls: list[dict[str, Any]] | None) -> set[str]:
    ids: set[str] = set()
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        tc_id = tc.get("id")
        if isinstance(tc_id, str) and tc_id:
            ids.add(tc_id)
    return ids


_READ_ONLY_CURSOR_TOOL_CANONICAL = {
    "read",
    "readfile",
    "grep",
    "glob",
    "ls",
    "readlints",
    "semanticsearch",
    "codebasesearch",
}


def _filter_read_only_cursor_tools(cursor_tools: list[Any]) -> list[Any]:
    """
    Evidence collection must be read-only.

    Cursor-provided tool schemas include both read-only and mutating tools (Write/ApplyPatch/Shell/etc).
    We must not allow Arbiter evidence phases to mutate the workspace.
    """
    filtered: list[Any] = []
    for tool in cursor_tools or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        canonical = re.sub(r"[^a-z0-9]+", "", name.strip().lower())
        if canonical in _READ_ONLY_CURSOR_TOOL_CANONICAL:
            filtered.append(tool)
    return filtered


def _filter_execution_cursor_tools(cursor_tools: list[Any]) -> list[Any]:
    """
    Execution/Optimizer tools must exclude read/search tools.
    """
    filtered: list[Any] = []
    for tool in cursor_tools or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        canonical = re.sub(r"[^a-z0-9]+", "", name.strip().lower())
        if canonical in EXECUTION_ALLOWED_TOOL_CANONICAL:
            filtered.append(tool)
    return filtered


async def evidence_node(state: TernionState) -> TernionState:
    """
    Phase 0: Evidence Gathering - Arbiter collects minimal code evidence.

    Uses tool calls only. Outputs evidence_bundle and evidence_gaps.
    """
    logger.info("workflow_evidence_start")
    log_manager.emit(
        level="INFO",
        category="WORKFLOW",
        message="Evidence phase started | Arbiter collecting evidence",
    )

    thinking_logs = list(state.get("thinking_logs", []))

    history = state.get("conversation_history", [])
    session_id = str(state.get("session_id") or "").strip()
    history_for_prompt = history
    if not session_id:
        # For a new evidence run, strip any prior tool artifacts from the inbound history.
        # Evidence should be re-collected via tools and represented in the evidence bundle.
        history_for_prompt = _filter_conversation_history_for_analysis(history)

    system_prompt = _prepend_global_security_rules(ARBITER_EVIDENCE_PROMPT)
    messages: list[ChatMessage] = [
        ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
    ]
    for msg in history_for_prompt:
        messages.append(
            ChatMessage(
                role=MessageRole(msg["role"]),
                content=msg.get("content"),
                name=msg.get("name"),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id"),
            )
        )

    cursor_tools = _filter_read_only_cursor_tools(state.get("cursor_tools") or [])
    cursor_tool_choice = state.get("cursor_tool_choice")
    role_cfg = config_store.get_role_config("arbiter")

    try:
        provider = provider_manager.get_provider_for_role("arbiter")
        model = role_cfg.model if role_cfg and role_cfg.model else None
        if not model:
            logger.error("arbiter_model_not_configured")
            error_msg = t(
                MessageKey.ROLE_CONFIG_INCOMPLETE,
                missing_roles=_format_role_names(["arbiter"]),
            )
            return {
                **state,
                "errors": state.get("errors", []) + [error_msg],
                "thinking_logs": thinking_logs + [t(MessageKey.CONVERGENCE_ERROR, error=error_msg)],
            }

        supports_native_tools = getattr(provider, "supports_native_tool_calls", False) is True
        supports_text_tools = bool(cursor_tools) and not supports_native_tools
        should_use_tool_calls = bool(cursor_tools) and (supports_native_tools or supports_text_tools)

        if supports_text_tools:
            messages.append(
                ChatMessage(
                    role=MessageRole.USER,
                    content=(
                        "[NON-OPENAI TOOL CALLS]\n\n"
                        f"{build_text_tool_calls_instruction(cursor_tools)}"
                    ),
                )
            )

        schedule_workflow_prompt_capture(
            build_workflow_prompt_payload(
                phase="evidence",
                role="arbiter_evidence",
                provider=provider.name,
                model=model,
                messages=messages,
                temperature=0.2,
                session_id=session_id,
            )
        )
        extra_kwargs: dict[str, Any] = {}
        if should_use_tool_calls and supports_native_tools:
            extra_kwargs["tools"] = cursor_tools
            if cursor_tool_choice is not None:
                extra_kwargs["tool_choice"] = cursor_tool_choice

        response = await _call_with_timeout(
            provider=provider,
            messages=messages,
            model=model,
            temperature=0.2,
            **extra_kwargs,
        )
        tool_calls = response.tool_calls if isinstance(response.tool_calls, list) else None
        if supports_text_tools and not tool_calls:
            parsed_tool_calls = extract_tool_calls_from_text(response.content)
            if parsed_tool_calls:
                response.tool_calls = parsed_tool_calls
                response.content = ""
                tool_calls = parsed_tool_calls

        usage = response.usage or {}
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        completion_tokens = (
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or 0
        )
        thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
        output_for_cost = (
            completion_tokens if provider.name != "google" else completion_tokens + thoughts_tokens
        )
        budget_manager.record_usage(
            provider=provider.name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_for_cost,
            thoughts_tokens=thoughts_tokens,
            context_length=usage.get("total_tokens", 0),
        )
        if input_tokens or output_for_cost or thoughts_tokens:
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    f"evidence_usage | provider={provider.name} | "
                    f"model={model} | "
                    f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens} | "
                    f"total={usage.get('total_tokens', input_tokens + output_for_cost)}"
                ),
            )

        if tool_calls:
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    "evidence_tool_calls_ready | "
                    f"session_id={state.get('session_id', '')} | "
                    f"count={len(tool_calls)}"
                ),
            )
            return {
                **state,
                "current_phase": WorkflowPhase.EVIDENCE.value,
                "pending_tool_calls": tool_calls,
                "thinking_logs": thinking_logs,
            }

        evidence_bundle, evidence_gaps = _parse_evidence_output(response.content)
        evidence_gaps = merge_missing_purpose_gaps(
            evidence_bundle=evidence_bundle,
            evidence_gaps=evidence_gaps,
        )
        cleaned_history = _filter_conversation_history_for_analysis(history)
        return {
            **state,
            "current_phase": WorkflowPhase.DIVERGENCE.value,
            "conversation_history": cleaned_history,
            "evidence_bundle": evidence_bundle,
            "evidence_gaps": evidence_gaps,
            "thinking_logs": thinking_logs,
        }
    except Exception as e:
        logger.warning("evidence_collection_failed", error=str(e))
        log_manager.emit(
            level="WARN",
            category="WORKFLOW",
            message=f"Evidence collection failed: {str(e)[:120]}",
        )
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + [
                t(MessageKey.EVIDENCE_COLLECTION_FAILED, error=str(e))
            ],
            "thinking_logs": thinking_logs,
        }


def _split_optimizer_output(text: str) -> tuple[str, str]:
    """
    Split Optimizer output into internal and user-visible sections.

    The Optimizer prompt requires a strict wrapper with begin/end markers.
    This helper extracts those blocks and falls back to treating the full
    content as user summary when markers are missing.
    """
    raw = (text or "").strip()
    if not raw:
        return "", ""

    def extract_block(begin: str, end: str) -> str:
        start = raw.find(begin)
        if start < 0:
            return ""
        start += len(begin)
        stop = raw.find(end, start)
        if stop < 0:
            return ""
        return raw[start:stop].strip()

    internal = extract_block(_OPTIMIZER_INTERNAL_BEGIN, _OPTIMIZER_INTERNAL_END)
    user = extract_block(_OPTIMIZER_USER_BEGIN, _OPTIMIZER_USER_END)
    if user:
        return internal, user

    # Safety fallback: never leak the raw optimizer output to the user if the wrapper is missing.
    return internal or raw, ""


# Note: sanitize_for_preview and sanitize_for_cursor_display are imported from
# ternion.utils.cursor_safety. Use sanitize_for_preview for short previews in
# thinking logs, and sanitize_for_cursor_display for full report/handoff output.


async def divergence_node(state: TernionState) -> TernionState:
    """
    Step 1: The Divergence - Parallel Root Cause Analysis.

    Three user-configured ternion members analyze the problem concurrently,
    focusing on root cause analysis without writing code.

    Args:
        state: Current workflow state

    Returns:
        Updated state with ternion analyses
    """
    logger.info("workflow_divergence_start")
    log_manager.emit(
        level="INFO",
        category="WORKFLOW",
        message="Divergence phase started | Parallel ternion analysis beginning",
    )

    thinking_logs = list(state.get("thinking_logs", []))
    thinking_logs.append(t(MessageKey.DIVERGENCE_START))

    # Build messages for ternion - use Ternion RCA prompt, not Cursor's
    history = state.get("conversation_history", [])
    history_for_prompt = _filter_conversation_history_for_analysis(history)
    evidence_bundle = state.get("evidence_bundle") or "EVIDENCE_BUNDLE:\n- None"
    evidence_gaps = state.get("evidence_gaps") or "EVIDENCE_GAPS:\n- None"
    evidence_block = f"[EVIDENCE]\n\n{evidence_bundle}\n\n{evidence_gaps}"
    system_prompt = _prepend_global_security_rules(f"{DIVERGENCE_PROMPT}\n\n{evidence_block}")
    ternion_messages = [
        ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
    ]
    for msg in history_for_prompt:
        ternion_messages.append(
            ChatMessage(
                role=MessageRole(msg["role"]),
                content=msg.get("content"),
                name=msg.get("name"),
            )
        )

    # Read ternion configurations from config_store
    ternion_ids = ["ternion_a", "ternion_b", "ternion_c"]
    ternion_configs = []
    unconfigured = []

    for ternion_id in ternion_ids:
        cfg = config_store.get_role_config(ternion_id)
        if cfg and cfg.provider and cfg.model:
            ternion_configs.append({
                "ternion_id": ternion_id,
                "provider": cfg.provider,
                "model": cfg.model,
            })
        else:
            unconfigured.append(ternion_id)

    # Check if any ternions are not configured
    if unconfigured:
        error_msg = t(
            MessageKey.ROLE_CONFIG_INCOMPLETE,
            missing_roles=_format_role_names(unconfigured),
        )
        logger.warning("ternion_not_configured", unconfigured=unconfigured)
        thinking_logs.append(f"⚠️ {error_msg}")
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + [error_msg],
            "ternion_analyses": [],
            "thinking_logs": thinking_logs,
        }

    async def analyze(ternion_cfg: dict) -> dict[str, Any]:
        ternion_id = ternion_cfg["ternion_id"]
        provider_name = ternion_cfg["provider"]
        model = ternion_cfg["model"]
        try:
            provider = provider_manager.get_provider(provider_name)
            if not provider:
                role_name = _ROLE_DISPLAY_NAMES.get(ternion_id, ternion_id)
                return {
                    "ternion_id": ternion_id,
                    "provider": provider_name,
                    "analysis": "",
                    "error": t(
                        MessageKey.PROVIDER_UNAVAILABLE,
                        role=role_name,
                        provider=provider_name,
                    ),
                }

            schedule_workflow_prompt_capture(
                build_workflow_prompt_payload(
                    phase="divergence",
                    role=ternion_id,
                    provider=provider_name,
                    model=model,
                    messages=ternion_messages,
                    temperature=0.7,
                    session_id=state.get("session_id", ""),
                )
            )
            response = None
            max_attempts = 3 if provider.name == "google" else 1
            for attempt in range(1, max_attempts + 1):
                try:
                    response = await _call_with_timeout(
                        provider=provider,
                        messages=ternion_messages,
                        model=model,
                        temperature=0.7,
                    )
                    break
                except Exception as e:
                    is_last = attempt >= max_attempts
                    error_text = str(e)
                    retryable = (
                        provider.name == "google"
                        and ("503" in error_text or "UNAVAILABLE" in error_text or "overloaded" in error_text.lower())
                    )
                    if is_last or not retryable:
                        raise
                    wait_seconds = 1.5 * attempt
                    logger.warning(
                        "ternion_analysis_retry",
                        ternion_id=ternion_id,
                        provider=provider_name,
                        model=model,
                        attempt=attempt,
                        wait_seconds=wait_seconds,
                        error=error_text[:200],
                    )
                    await asyncio.sleep(wait_seconds)

            if response is None:
                raise RuntimeError("divergence_provider_response_missing")
            usage = response.usage or {}
            input_tokens = (
                usage.get("prompt_tokens")
                or usage.get("input_tokens")
                or 0
            )
            completion_tokens = (
                usage.get("completion_tokens")
                or usage.get("output_tokens")
                or 0
            )
            thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
            output_for_cost = (
                completion_tokens if provider.name != "google" else completion_tokens + thoughts_tokens
            )
            budget_manager.record_usage(
                provider=provider.name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_for_cost,
                thoughts_tokens=thoughts_tokens,
                context_length=usage.get("total_tokens", 0),
            )
            if input_tokens or output_for_cost or thoughts_tokens:
                log_manager.emit(
                    level="INFO",
                    category="WORKFLOW",
                    message=(
                        f"divergence_usage | provider={provider.name} | "
                        f"model={model} | "
                        f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens} | "
                        f"total={usage.get('total_tokens', input_tokens + output_for_cost)}"
                    ),
                )
            return {
                "ternion_id": ternion_id,
                "provider": provider_name,
                "analysis": response.content,
                "error": None,
            }
        except Exception as e:
            logger.warning(
                "ternion_analysis_failed",
                ternion_id=ternion_id,
                provider=provider_name,
                error=str(e),
            )
            return {
                "ternion_id": ternion_id,
                "provider": provider_name,
                "analysis": "",
                "error": str(e),
            }

    # Execute concurrently using user-configured ternions
    tasks = [analyze(cfg) for cfg in ternion_configs]
    analyses = await asyncio.gather(*tasks)

    # Filter successful analyses
    successful = [a for a in analyses if not a.get("error")]
    logger.info(
        "workflow_divergence_complete",
        successful_count=len(successful),
        total_count=len(analyses),
    )

    # Add thinking logs for each analysis
    for a in successful:
        preview = sanitize_for_preview(a["analysis"], max_length=100)
        thinking_logs.append(t(MessageKey.DIVERGENCE_ANALYSIS, ternion_id=a['ternion_id'], preview=preview))

    failed = [a for a in analyses if a.get("error")]
    for a in failed:
        err_preview = sanitize_for_preview(str(a.get("error") or ""), max_length=100)
        thinking_logs.append(
            t(
                MessageKey.DIVERGENCE_ANALYSIS_FAILED,
                ternion_id=str(a.get("ternion_id") or ""),
                provider=str(a.get("provider") or ""),
                error=err_preview,
            )
        )

    # Extract evidence requests from all analyses for Phase 1.5
    evidence_requests = _extract_evidence_requests(successful)

    return {
        **state,
        "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
        "ternion_analyses": list(analyses),
        "evidence_requests": evidence_requests,
        "thinking_logs": thinking_logs,
    }


def _has_real_evidence_requests(requests: str) -> bool:
    """
    Check if evidence_requests contains real requests (not just '- [P0] None').

    Args:
        requests: The extracted evidence_requests string.

    Returns:
        True if there are real evidence requests, False otherwise.
    """
    text = (requests or "").strip()
    if not text:
        return False

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    # Strict empty marker protocol (case-insensitive).
    if len(lines) == 1 and lines[0].lower() in ("- [p0] none", "[p0] none"):
        return False
    return True


async def report_evidence_node(state: TernionState) -> TernionState:
    """
    Phase 1.5: Report Evidence Verification - Arbiter collects requested evidence.

    This node collects additional evidence based on evidence_requests from council
    members before generating the final report. Uses tool calls only. Appends to
    existing evidence_bundle and evidence_gaps.

    Args:
        state: Current workflow state with evidence_requests from divergence.

    Returns:
        Updated state with appended evidence, ready for convergence.
    """
    evidence_requests = state.get("evidence_requests", "")
    thinking_logs = list(state.get("thinking_logs", []))
    resume_phase = str(state.get("report_evidence_resume_phase") or "").strip().lower()
    next_phase = (
        WorkflowPhase.OPTIMIZER.value
        if resume_phase == WorkflowPhase.OPTIMIZER.value
        else WorkflowPhase.EXECUTION.value
        if resume_phase == WorkflowPhase.EXECUTION.value
        else WorkflowPhase.CONVERGENCE.value
    )

    # Skip if no real evidence requests
    if not _has_real_evidence_requests(evidence_requests):
        logger.info("report_evidence_skip", reason="no_real_requests")
        log_manager.emit(
            level="INFO",
            category="WORKFLOW",
            message="Phase 1.5 skipped | No real evidence requests from council",
        )
        reconciled_gaps, evidence_chain_index = reconcile_evidence_chain(
            evidence_bundle=state.get("evidence_bundle") or "",
            evidence_gaps=state.get("evidence_gaps") or "",
            evidence_requests=evidence_requests,
        )
        return {
            **state,
            "current_phase": next_phase,
            "evidence_gaps": reconciled_gaps,
            "evidence_chain_index": evidence_chain_index,
            "thinking_logs": thinking_logs,
        }

    logger.info("workflow_report_evidence_start")
    log_manager.emit(
        level="INFO",
        category="WORKFLOW",
        message="Phase 1.5 started | Arbiter collecting requested evidence",
    )

    session_id = str(state.get("session_id") or "").strip()

    system_prompt = _prepend_global_security_rules(ARBITER_REPORT_EVIDENCE_PROMPT)
    messages: list[ChatMessage] = [
        ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
    ]

    # Add evidence_requests as user message (this is the only input the prompt needs)
    messages.append(
        ChatMessage(
            role=MessageRole.USER,
            content=f"[EVIDENCE_REQUESTS]\n{evidence_requests}",
        )
    )

    cursor_tools = _filter_read_only_cursor_tools(state.get("cursor_tools") or [])
    cursor_tool_choice = state.get("cursor_tool_choice")
    role_cfg = config_store.get_role_config("arbiter")

    history = state.get("conversation_history", [])
    assistant_with_tools_count = 0
    tool_msg_count = 0
    raw_tool_msg_count = 0
    dropped_tool_msg_count = 0
    pending_tool_call_ids: set[str] = set()
    for msg in history:
        role = msg.get("role")
        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                assistant_with_tools_count += 1
                pending_tool_call_ids = _collect_tool_call_ids(tool_calls)
                messages.append(
                    ChatMessage(
                        role=MessageRole.ASSISTANT,
                        content=msg.get("content"),
                        name=msg.get("name"),
                        tool_calls=tool_calls,
                    )
                )
            else:
                pending_tool_call_ids = set()
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if isinstance(tool_call_id, str) and tool_call_id:
                raw_tool_msg_count += 1
                if tool_call_id in pending_tool_call_ids:
                    tool_msg_count += 1
                    messages.append(
                        ChatMessage(
                            role=MessageRole.TOOL,
                            content=msg.get("content"),
                            name=msg.get("name"),
                            tool_call_id=tool_call_id,
                        )
                    )
                else:
                    dropped_tool_msg_count += 1
        else:
            pending_tool_call_ids = set()

    # Log message composition for debugging tool_call_id mismatch issues
    if raw_tool_msg_count > 0:
        log_manager.emit(
            level="DEBUG" if assistant_with_tools_count > 0 else "WARN",
            category="WORKFLOW",
            message=(
                f"report_evidence_messages_composed | "
                f"history_len={len(history)} | "
                f"assistant_with_tools={assistant_with_tools_count} | "
                f"tool_msgs={tool_msg_count} | "
                f"dropped_tool_msgs={dropped_tool_msg_count} | "
                f"final_msgs_len={len(messages)}"
            ),
        )
        if assistant_with_tools_count == 0 and raw_tool_msg_count > 0:
            # This will cause OpenAI 400 error - tool messages without preceding assistant tool_calls
            logger.warning(
                "report_evidence_tool_messages_without_assistant",
                history_len=len(history),
                tool_msg_count=raw_tool_msg_count,
                history_roles=[msg.get("role") for msg in history],
                history_has_tool_calls=[bool(msg.get("tool_calls")) for msg in history if msg.get("role") == "assistant"],
            )
        if dropped_tool_msg_count > 0:
            logger.warning(
                "report_evidence_orphan_tool_messages_dropped",
                history_len=len(history),
                dropped_tool_msg_count=dropped_tool_msg_count,
            )

    try:
        provider = provider_manager.get_provider_for_role("arbiter")
        model = role_cfg.model if role_cfg and role_cfg.model else None
        if not model:
            logger.error("arbiter_model_not_configured_report_evidence")
            error_msg = t(
                MessageKey.ROLE_CONFIG_INCOMPLETE,
                missing_roles=_format_role_names(["arbiter"]),
            )
            return {
                **state,
                # Keep phase at REPORT_EVIDENCE since error occurred here (phase consistency fix)
                "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                "errors": state.get("errors", []) + [error_msg],
                "thinking_logs": thinking_logs,
            }

        supports_native_tools = getattr(provider, "supports_native_tool_calls", False) is True
        supports_text_tools = bool(cursor_tools) and not supports_native_tools
        should_use_tool_calls = bool(cursor_tools) and (supports_native_tools or supports_text_tools)

        if supports_text_tools:
            messages.append(
                ChatMessage(
                    role=MessageRole.USER,
                    content=(
                        "[NON-OPENAI TOOL CALLS]\n\n"
                        f"{build_text_tool_calls_instruction(cursor_tools)}"
                    ),
                )
            )

        schedule_workflow_prompt_capture(
            build_workflow_prompt_payload(
                phase="report_evidence",
                role="arbiter_report_evidence",
                provider=provider.name,
                model=model,
                messages=messages,
                temperature=0.2,
                session_id=session_id,
            )
        )
        extra_kwargs: dict[str, Any] = {}
        if should_use_tool_calls and supports_native_tools:
            extra_kwargs["tools"] = cursor_tools
            if cursor_tool_choice is not None:
                extra_kwargs["tool_choice"] = cursor_tool_choice

        response = await _call_with_timeout(
            provider=provider,
            messages=messages,
            model=model,
            temperature=0.2,
            **extra_kwargs,
        )
        tool_calls = response.tool_calls if isinstance(response.tool_calls, list) else None
        if supports_text_tools and not tool_calls:
            parsed_tool_calls = extract_tool_calls_from_text(response.content)
            if parsed_tool_calls:
                response.tool_calls = parsed_tool_calls
                response.content = ""
                tool_calls = parsed_tool_calls

        usage = response.usage or {}
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        completion_tokens = (
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or 0
        )
        thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
        output_for_cost = (
            completion_tokens if provider.name != "google" else completion_tokens + thoughts_tokens
        )
        budget_manager.record_usage(
            provider=provider.name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_for_cost,
            thoughts_tokens=thoughts_tokens,
            context_length=usage.get("total_tokens", 0),
        )
        if input_tokens or output_for_cost or thoughts_tokens:
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    f"report_evidence_usage | provider={provider.name} | "
                    f"model={model} | "
                    f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens} | "
                    f"total={usage.get('total_tokens', input_tokens + output_for_cost)}"
                ),
            )

        if tool_calls:
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    "report_evidence_tool_calls_ready | "
                    f"session_id={session_id} | "
                    f"count={len(tool_calls)}"
                ),
            )
            return {
                **state,
                "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                "pending_tool_calls": tool_calls,
                "thinking_logs": thinking_logs,
            }

        # Parse and append evidence
        new_bundle, new_gaps = _parse_evidence_output(response.content)
        existing_bundle = state.get("evidence_bundle") or ""
        existing_gaps = state.get("evidence_gaps") or ""

        # Append new evidence to existing bundle (P1-1 fix: avoid duplicate headers)
        if new_bundle and "- None" not in new_bundle:
            # Strip EVIDENCE_BUNDLE: header from new_bundle to avoid duplicate headers
            new_bundle_content = new_bundle
            if new_bundle_content.startswith("EVIDENCE_BUNDLE:"):
                new_bundle_content = new_bundle_content[len("EVIDENCE_BUNDLE:"):].lstrip("\n")
            if existing_bundle and "- None" not in existing_bundle:
                # Append new evidence lines to existing bundle (after the header)
                updated_bundle = f"{existing_bundle}\n\n{new_bundle_content}"
            else:
                updated_bundle = new_bundle  # Use full new_bundle with header if no existing
        else:
            updated_bundle = existing_bundle

        # Merge gaps: preserve existing gaps and append new ones (P1-2 fix)
        # This prevents losing Phase 0 gaps that council didn't re-raise
        if new_gaps and "- None" not in new_gaps:
            if existing_gaps and "- None" not in existing_gaps:
                # Strip EVIDENCE_GAPS: header from new_gaps before merging
                new_gaps_content = new_gaps
                if new_gaps_content.startswith("EVIDENCE_GAPS:"):
                    new_gaps_content = new_gaps_content[len("EVIDENCE_GAPS:"):].lstrip("\n")
                # Merge: existing gaps + new gaps (dedupe handled by uniqueness of evidence items)
                updated_gaps = f"{existing_gaps}\n{new_gaps_content}"
            else:
                updated_gaps = new_gaps  # Use full new_gaps with header if no existing
        else:
            updated_gaps = existing_gaps

        log_manager.emit(
            level="INFO",
            category="WORKFLOW",
            message="Phase 1.5 complete | Evidence collected and appended",
        )
        reconciled_gaps, evidence_chain_index = reconcile_evidence_chain(
            evidence_bundle=updated_bundle,
            evidence_gaps=updated_gaps,
            evidence_requests=evidence_requests,
        )

        return {
            **state,
            "current_phase": next_phase,
            "evidence_bundle": updated_bundle,
            "evidence_gaps": reconciled_gaps,
            "evidence_chain_index": evidence_chain_index,
            "conversation_history": _filter_conversation_history_for_analysis(
                state.get("conversation_history", [])
            ),
            "thinking_logs": thinking_logs,
        }
    except Exception as e:
        logger.warning("report_evidence_collection_failed", error=str(e))
        log_manager.emit(
            level="WARN",
            category="WORKFLOW",
            message=f"Phase 1.5 evidence collection failed: {str(e)[:120]}",
        )
        # On failure, stop at this phase (not convergence) for consistency
        return {
            **state,
            # Keep phase at REPORT_EVIDENCE since error occurred here (phase consistency fix)
            "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
            "errors": state.get("errors", []) + [
                t(MessageKey.REPORT_EVIDENCE_COLLECTION_FAILED, error=str(e))
            ],
            "thinking_logs": thinking_logs,
        }


async def convergence_node(state: TernionState) -> TernionState:
    """
    Step 2: The Convergence - Arbiter Synthesis.

    The Arbiter synthesizes all ternion analyses,
    resolves conflicts, and produces a unified Ternion Analysis Report.

    Args:
        state: Current workflow state with ternion analyses

    Returns:
        Updated state with synthesized report
    """
    logger.info("workflow_convergence_start")
    log_manager.emit(
        level="INFO",
        category="WORKFLOW",
        message="Convergence phase started | Arbiter synthesizing analyses",
    )

    thinking_logs = list(state.get("thinking_logs", []))
    thinking_logs.append(t(MessageKey.CONVERGENCE_START))

    analyses = state.get("ternion_analyses", [])
    successful_analyses = [a for a in analyses if not a.get("error")]

    if not successful_analyses:
        logger.error("no_successful_analyses")
        error_msg = t(MessageKey.NO_TERNION_ANALYSES_AVAILABLE)
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + [error_msg],
            "ternion_report": "",
            "is_consensus": False,
        }

    # Get effective language for report generation
    user_config = config_store.load()
    language_code = user_config.language
    if language_code == "auto":
        language_code = user_config.browser_language or "en"

    language_name = get_language_name(language_code)
    instruction_template = get_report_language_instruction_template()
    language_instruction = (
        instruction_template.format(language_name=language_name) if instruction_template else ""
    )

    # Build synthesis prompt with language instruction
    convergence_prompt_with_lang = CONVERGENCE_PROMPT.format(language_instruction=language_instruction)

    evidence_bundle = state.get("evidence_bundle") or "EVIDENCE_BUNDLE:\n- None"
    evidence_gaps = state.get("evidence_gaps") or "EVIDENCE_GAPS:\n- None"
    evidence_requests = _extract_evidence_requests(successful_analyses)

    synthesis_content = (
        f"{evidence_bundle}\n\n"
        f"{evidence_gaps}\n\n"
        "EVIDENCE_REQUESTS:\n"
        f"{evidence_requests}\n\n"
        "Council Analyses:\n\n"
    )
    for analysis in successful_analyses:
        synthesis_content += f"### {analysis['ternion_id'].upper()}\n"
        synthesis_content += f"{analysis['analysis']}\n\n"

    messages: list[ChatMessage] = [
        ChatMessage(
            role=MessageRole.SYSTEM,
            content=_prepend_global_security_rules(convergence_prompt_with_lang),
        )
    ]

    history = state.get("conversation_history", [])
    for msg in history:
        messages.append(
            ChatMessage(
                role=MessageRole(msg["role"]),
                content=msg.get("content"),
                name=msg.get("name"),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id"),
            )
        )

    messages.append(ChatMessage(role=MessageRole.USER, content=synthesis_content))

    # Use Arbiter (Gemini with fallback)
    try:
        provider = provider_manager.get_provider_for_role("arbiter")

        # Get user-configured model from config_store
        role_cfg = config_store.get_role_config("arbiter")
        model = role_cfg.model if role_cfg and role_cfg.model else None

        # Hard validation: model must be explicitly configured
        if not model:
            logger.error("arbiter_model_not_configured")
            error_msg = t(
                MessageKey.ROLE_CONFIG_INCOMPLETE,
                missing_roles=_format_role_names(["arbiter"]),
            )
            return {
                **state,
                "errors": state.get("errors", []) + [
                    error_msg
                ],
                "thinking_logs": thinking_logs + [
                    t(MessageKey.CONVERGENCE_ERROR, error=error_msg)
                ],
            }

        # Get stream queue from state for real-time output (if available)
        stream_queue: StreamEventQueue | None = state.get("_stream_queue")
        session_id = state.get("session_id", "")

        # Use streaming call if queue is available, otherwise fall back to non-streaming
        schedule_workflow_prompt_capture(
            build_workflow_prompt_payload(
                phase="convergence",
                role="arbiter",
                provider=provider.name,
                model=model,
                messages=messages,
                temperature=0.5,
                session_id=session_id,
            )
        )
        response = await _call_with_stream(
            provider=provider,
            messages=messages,
            model=model,
            temperature=0.5,  # Lower temperature for synthesis
            stream_queue=stream_queue,
            phase="convergence",
            message_id=session_id,
        )
        usage = response.usage or {}
        input_tokens = (
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or 0
        )
        completion_tokens = (
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or 0
        )
        thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
        output_for_cost = completion_tokens if provider.name != "google" else completion_tokens + thoughts_tokens
        if input_tokens or output_for_cost or thoughts_tokens:
            budget_manager.record_usage(
                provider=provider.name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_for_cost,
                thoughts_tokens=thoughts_tokens,
                context_length=usage.get("total_tokens", 0),
            )
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    f"convergence_usage | provider={provider.name} | "
                    f"model={model} | "
                    f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens} | "
                    f"total={usage.get('total_tokens', input_tokens + output_for_cost)}"
                ),
            )

        preview = sanitize_for_preview(response.content, max_length=80)
        thinking_logs.append(t(MessageKey.CONVERGENCE_COMPLETE, preview=preview))

        # Determine execution mode from state or config (must be explicitly set)
        execution_mode_str = state.get("execution_mode", "") or config_store.load().execution_mode
        if execution_mode_str not in ("cursor_handoff", "ternion_full"):
            error_msg = t(MessageKey.EXECUTION_MODE_NOT_CONFIGURED)
            logger.error("execution_mode_not_configured")
            return {
                **state,
                "current_phase": WorkflowPhase.COMPLETE.value,
                "errors": state.get("errors", []) + [error_msg],
                "thinking_logs": thinking_logs + [t(MessageKey.CONVERGENCE_ERROR, error=error_msg)],
            }

        execution_mode = ExecutionMode(execution_mode_str)

        # Check if we should await user confirmation (Human-in-the-Loop)
        await_confirmation = state.get("await_confirmation", True)

        if await_confirmation:
            # Create a session for tracking
            session = session_store.create_session(
                ternion_report=response.content,
                execution_mode=execution_mode,
                original_context={
                    "conversation_history": state.get("conversation_history", []),
                    "cursor_system_prompt": state.get("cursor_system_prompt"),
                },
                evidence_bundle=str(state.get("evidence_bundle") or ""),
                evidence_gaps=str(state.get("evidence_gaps") or ""),
                evidence_requests=str(state.get("evidence_requests") or ""),
                evidence_chain_index=list(state.get("evidence_chain_index") or []),
                ternion_analyses=list(state.get("ternion_analyses") or []),
            )

            # Log session info and report
            log_manager.emit(
                level="INFO",
                category="SESSION",
                message=f"Session created: {session.session_id} | Mode: {execution_mode.value} | Status: AWAITING_CONFIRMATION"
            )
            log_manager.emit(
                level="INFO",
                category="REPORT",
                message=f"Ternion Report generated (Len: {len(response.content)} chars). Content Preview: {response.content[:200].replace(chr(10), ' ')}..."
            )

            # Generate a plain-text view of the report for display.
            display_report = format_report_for_display(session.ternion_report_raw)
            display_report_safe = sanitize_for_cursor_display(display_report)

            mode_description = (
                t(MessageKey.EXECUTION_MODE_DESC_TERNION_FULL)
                if execution_mode == ExecutionMode.TERNION_FULL
                else t(MessageKey.EXECUTION_MODE_DESC_CURSOR_HANDOFF)
            )
            session_path = f"~/.ternion/sessions/{session.session_id}.json"
            raw_note = t(
                MessageKey.REPORT_RAW_SESSION_NOTE,
                path=session_path,
                field="ternion_report_raw",
            )
            confirm_prompt_key = (
                MessageKey.REPORT_CONFIRM_PROMPT_CURSOR_HANDOFF
                if execution_mode == ExecutionMode.CURSOR_HANDOFF
                else MessageKey.REPORT_CONFIRM_PROMPT
            )
            confirm_prompt = t(
                confirm_prompt_key,
                mode_desc=mode_description,
            )

            session_markers = f"""TERNION_SESSION_ID={session.session_id}
TERNION_SESSION_STAGE=AWAITING_CONFIRMATION
TERNION_EXECUTION_MODE={execution_mode.value}
TERNION_REPORT_HASH={session.report_hash}"""

            final_output_suffix = f"""

---

{raw_note}

{confirm_prompt}

{session_markers}"""

            final_output = f"""{display_report_safe}

---

{raw_note}

{confirm_prompt}

{session_markers}"""

            logger.info(
                "convergence_awaiting_confirmation",
                session_id=session.session_id,
                execution_mode=execution_mode.value,
            )

            return {
                **state,
                "current_phase": WorkflowPhase.CONVERGENCE.value,  # Stay in convergence
                "ternion_report": response.content,
                "is_consensus": len(successful_analyses) > 1,
                "thinking_logs": thinking_logs,
                "session_id": session.session_id,
                "await_confirmation": True,
                "final_output": final_output,  # This will be returned to user
                "final_output_suffix": final_output_suffix,
            }
        else:
            # Direct execution mode (no confirmation required)
            session_id_str = str(session_id or "").strip()
            if session_id_str:
                session_store.update_session(
                    session_id_str,
                    ternion_report_raw=response.content,
                )
            return {
                **state,
                "current_phase": WorkflowPhase.EXECUTION.value,
                "ternion_report": response.content,
                "is_consensus": len(successful_analyses) > 1,
                "thinking_logs": thinking_logs,
            }
    except Exception as e:
        logger.error("convergence_failed", error=str(e))
        log_manager.emit(
            level="WARN",
            category="WORKFLOW",
            message=f"Arbiter failed: {str(e)[:80]}... Attempting ternion fallback",
        )

        # Try to use successful ternions as fallback Arbiter (Issue 2 fix)
        # Priority: ternion_a → ternion_b → ternion_c
        fallback_providers = []
        for analysis in successful_analyses:
            ternion_id = analysis.get("ternion_id")
            cfg = config_store.get_role_config(ternion_id)
            if cfg and cfg.provider and cfg.model:
                fallback_providers.append({
                    "ternion_id": ternion_id,
                    "provider": cfg.provider,
                    "model": cfg.model,
                })

        fallback_response = None
        fallback_provider_name = None
        fallback_model = None

        for fallback_cfg in fallback_providers:
            try:
                fallback_provider = provider_manager.get_provider(fallback_cfg["provider"])
                if not fallback_provider:
                    continue

                logger.info(
                    "convergence_fallback_attempt",
                    ternion_id=fallback_cfg["ternion_id"],
                    provider=fallback_cfg["provider"],
                )
                log_manager.emit(
                    level="INFO",
                    category="WORKFLOW",
                    message=f"Trying fallback Arbiter: {fallback_cfg['ternion_id']} ({fallback_cfg['provider']}/{fallback_cfg['model']})",
                )

                schedule_workflow_prompt_capture(
                    build_workflow_prompt_payload(
                        phase="convergence_fallback",
                        role=fallback_cfg["ternion_id"],
                        provider=fallback_cfg["provider"],
                        model=fallback_cfg["model"],
                        messages=messages,
                        temperature=0.5,
                        session_id=state.get("session_id", ""),
                    )
                )
                fallback_response = await _call_with_timeout(
                    provider=fallback_provider,
                    messages=messages,
                    model=fallback_cfg["model"],
                    temperature=0.5,
                )
                fallback_provider_name = fallback_provider.name
                fallback_model = fallback_cfg["model"]

                # Record usage for fallback
                usage = fallback_response.usage or {}
                input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
                completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
                thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
                output_for_cost = completion_tokens if fallback_provider.name != "google" else completion_tokens + thoughts_tokens
                budget_manager.record_usage(
                    provider=fallback_provider.name,
                    model=fallback_cfg["model"],
                    input_tokens=input_tokens,
                    output_tokens=output_for_cost,
                    thoughts_tokens=thoughts_tokens,
                    context_length=usage.get("total_tokens", 0),
                )
                if input_tokens or output_for_cost or thoughts_tokens:
                    log_manager.emit(
                        level="INFO",
                        category="WORKFLOW",
                        message=(
                            f"convergence_fallback_usage | provider={fallback_provider.name} | "
                            f"model={fallback_cfg['model']} | "
                            f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens}"
                        ),
                    )

                logger.info(
                    "convergence_fallback_success",
                    ternion_id=fallback_cfg["ternion_id"],
                    provider=fallback_cfg["provider"],
                )
                log_manager.emit(
                    level="INFO",
                    category="WORKFLOW",
                    message=f"Fallback Arbiter succeeded: {fallback_cfg['ternion_id']}",
                )
                break  # Success, exit fallback loop

            except Exception as fallback_error:
                logger.warning(
                    "convergence_fallback_failed",
                    ternion_id=fallback_cfg["ternion_id"],
                    error=str(fallback_error),
                )
                log_manager.emit(
                    level="WARN",
                    category="WORKFLOW",
                    message=f"Fallback Arbiter failed: {fallback_cfg['ternion_id']} - {str(fallback_error)[:50]}",
                )
                continue  # Try next fallback

        # If fallback succeeded, use the synthesized report
        if fallback_response:
            thinking_logs.append(t(MessageKey.CONVERGENCE_ERROR, error=f"Used fallback: {fallback_provider_name}/{fallback_model}"))
            preview = sanitize_for_preview(fallback_response.content, max_length=80)
            thinking_logs.append(t(MessageKey.CONVERGENCE_COMPLETE, preview=preview))

            # Continue with normal flow using fallback response
            execution_mode_str = state.get("execution_mode", "") or config_store.load().execution_mode
            if execution_mode_str not in ("cursor_handoff", "ternion_full"):
                error_msg = t(MessageKey.EXECUTION_MODE_NOT_CONFIGURED)
                logger.error("execution_mode_not_configured")
                return {
                    **state,
                    "current_phase": WorkflowPhase.COMPLETE.value,
                    "errors": state.get("errors", []) + [error_msg],
                    "thinking_logs": thinking_logs + [t(MessageKey.CONVERGENCE_ERROR, error=error_msg)],
                }

            execution_mode = ExecutionMode(execution_mode_str)
            await_confirmation = state.get("await_confirmation", True)

            if await_confirmation:
                session = session_store.create_session(
                    ternion_report=fallback_response.content,
                    execution_mode=execution_mode,
                    original_context={
                        "conversation_history": state.get("conversation_history", []),
                        "cursor_system_prompt": state.get("cursor_system_prompt"),
                    },
                    evidence_bundle=str(state.get("evidence_bundle") or ""),
                    evidence_gaps=str(state.get("evidence_gaps") or ""),
                    evidence_requests=str(state.get("evidence_requests") or ""),
                    evidence_chain_index=list(state.get("evidence_chain_index") or []),
                    ternion_analyses=list(state.get("ternion_analyses") or []),
                )

                log_manager.emit(
                    level="INFO",
                    category="SESSION",
                    message=f"Session created (via fallback Arbiter): {session.session_id} | Mode: {execution_mode.value}",
                )

                display_report = format_report_for_display(session.ternion_report_raw)
                display_report_safe = sanitize_for_cursor_display(display_report)
                mode_description = (
                    t(MessageKey.EXECUTION_MODE_DESC_TERNION_FULL)
                    if execution_mode == ExecutionMode.TERNION_FULL
                    else t(MessageKey.EXECUTION_MODE_DESC_CURSOR_HANDOFF)
                )
                session_path = f"~/.ternion/sessions/{session.session_id}.json"
                raw_note = t(
                    MessageKey.REPORT_RAW_SESSION_NOTE,
                    path=session_path,
                    field="ternion_report_raw",
                )
                confirm_prompt_key = (
                    MessageKey.REPORT_CONFIRM_PROMPT_CURSOR_HANDOFF
                    if execution_mode == ExecutionMode.CURSOR_HANDOFF
                    else MessageKey.REPORT_CONFIRM_PROMPT
                )
                confirm_prompt = t(
                    confirm_prompt_key,
                    mode_desc=mode_description,
                )

                session_markers = f"""TERNION_SESSION_ID={session.session_id}
TERNION_SESSION_STAGE=AWAITING_CONFIRMATION
TERNION_EXECUTION_MODE={execution_mode.value}
TERNION_REPORT_HASH={session.report_hash}"""

                final_output_suffix = f"""

---

{raw_note}

{confirm_prompt}

{session_markers}"""

                final_output = f"""{display_report_safe}

---

{raw_note}

{confirm_prompt}

{session_markers}"""

                return {
                    **state,
                    "current_phase": WorkflowPhase.CONVERGENCE.value,
                    "ternion_report": fallback_response.content,
                    "is_consensus": len(successful_analyses) > 1,
                    "thinking_logs": thinking_logs,
                    "session_id": session.session_id,
                    "await_confirmation": True,
                    "final_output": final_output,
                    "final_output_suffix": final_output_suffix,
                }
            else:
                session_id_str = str(state.get("session_id") or "").strip()
                if session_id_str:
                    session_store.update_session(
                        session_id_str,
                        ternion_report_raw=fallback_response.content,
                    )
                return {
                    **state,
                    "current_phase": WorkflowPhase.EXECUTION.value,
                    "ternion_report": fallback_response.content,
                    "is_consensus": len(successful_analyses) > 1,
                    "thinking_logs": thinking_logs,
                }

        # All fallbacks failed - use raw analysis as last resort
        fallback_report = successful_analyses[0]["analysis"]
        fallback_error = t(MessageKey.CONVERGENCE_ALL_ARBITERS_FAILED)
        thinking_logs.append(t(MessageKey.CONVERGENCE_ERROR, error=fallback_error))
        log_manager.emit(
            level="WARN",
            category="WORKFLOW",
            message="All Arbiter attempts failed, using raw ternion analysis as fallback",
        )

        execution_mode_str = state.get("execution_mode", "") or config_store.load().execution_mode

        if execution_mode_str == "cursor_handoff":
            execution_mode = ExecutionMode.CURSOR_HANDOFF
            session = session_store.create_session(
                ternion_report=fallback_report,
                execution_mode=execution_mode,
                original_context={
                    "conversation_history": state.get("conversation_history", []),
                    "cursor_system_prompt": state.get("cursor_system_prompt"),
                },
                evidence_bundle=str(state.get("evidence_bundle") or ""),
                evidence_gaps=str(state.get("evidence_gaps") or ""),
                evidence_requests=str(state.get("evidence_requests") or ""),
                evidence_chain_index=list(state.get("evidence_chain_index") or []),
                ternion_analyses=list(state.get("ternion_analyses") or []),
            )

            log_manager.emit(
                level="WARN",
                category="SESSION",
                message=f"Session created with raw analysis (all Arbiters failed): {session.session_id}",
            )

            display_report = format_report_for_display(session.ternion_report_raw)
            display_report_safe = sanitize_for_cursor_display(display_report)
            fallback_warning = t(MessageKey.CONVERGENCE_FALLBACK_WARNING)
            fallback_confirm = t(MessageKey.CONVERGENCE_FALLBACK_CONFIRM)
            session_path = f"~/.ternion/sessions/{session.session_id}.json"
            raw_note = t(
                MessageKey.REPORT_RAW_SESSION_NOTE,
                path=session_path,
                field="ternion_report_raw",
            )
            session_markers = f"""TERNION_SESSION_ID={session.session_id}
TERNION_SESSION_STAGE=AWAITING_CONFIRMATION
TERNION_EXECUTION_MODE={execution_mode.value}
TERNION_REPORT_HASH={session.report_hash}"""

            final_output_suffix = f"""

---

{fallback_warning}

{raw_note}

{fallback_confirm}

{session_markers}"""

            final_output = f"""{display_report_safe}

---

{fallback_warning}

{raw_note}

{fallback_confirm}

{session_markers}"""

            return {
                **state,
                "current_phase": WorkflowPhase.CONVERGENCE.value,
                "ternion_report": fallback_report,
                "is_consensus": False,
                "thinking_logs": thinking_logs,
                "session_id": session.session_id,
                "await_confirmation": True,
                "final_output": final_output,
                "final_output_suffix": final_output_suffix,
                "errors": state.get("errors", []) + [error_msg],
            }
        else:
            session_id_str = str(state.get("session_id") or "").strip()
            if session_id_str:
                session_store.update_session(
                    session_id_str,
                    ternion_report_raw=fallback_report,
                )
            return {
                **state,
                "current_phase": WorkflowPhase.EXECUTION.value,
                "ternion_report": fallback_report,
                "is_consensus": False,
                "thinking_logs": thinking_logs,
                "errors": state.get("errors", []) + [error_msg],
            }


async def execution_node(state: TernionState) -> TernionState:
    """
    Step 3: The Execution - Writer Produces Deliverables.

    The Writer produces the final deliverable(s) based on
    the Ternion Analysis Report. Uses Cursor's original system
    prompt to ensure output format compatibility.

    Args:
        state: Current workflow state with analysis report

    Returns:
        Updated state with Writer output
    """
    logger.info("workflow_execution_start")
    log_manager.emit(
        level="INFO",
        category="WORKFLOW",
        message="Execution phase started | Writer generating deliverable(s)",
    )

    thinking_logs = list(state.get("thinking_logs", []))
    thinking_logs.append(t(MessageKey.EXECUTION_START))

    # Build messages with Cursor's system prompt (for format compliance)
    cursor_prompt = state.get("cursor_system_prompt")
    ternion_report = state.get("ternion_report", "")
    history = state.get("conversation_history", [])
    latest_user_message = get_latest_user_message(history)
    history_len_before = len(history)
    tool_context_digest = ""
    truncated_history = False
    try:
        from ternion.utils.execution_history_compaction import (
            ExecutionHistoryCompactionConfig,
            compact_execution_history_for_writer,
        )

        history, tool_context_digest = compact_execution_history_for_writer(
            history,
            config=ExecutionHistoryCompactionConfig(),
        )
        truncated_history = len(history) != history_len_before
    except Exception:
        # Best-effort: do not block execution on compaction failures.
        tool_context_digest = ""
        truncated_history = False

    cursor_tools = _filter_execution_cursor_tools(state.get("cursor_tools") or [])
    cursor_tool_choice = state.get("cursor_tool_choice")
    role_cfg = config_store.get_role_config("writer")

    messages = []

    # Use Cursor's system prompt if available, otherwise fall back to Ternion's.
    # Note: Some provider backends only support a single system prompt. Keep exactly one.
    if cursor_prompt:
        messages.append(ChatMessage(role=MessageRole.SYSTEM, content=cursor_prompt))
    else:
        messages.append(
            ChatMessage(
                role=MessageRole.SYSTEM,
                content=_prepend_global_security_rules(EXECUTION_PROMPT),
            )
        )

    # Add conversation history
    for msg in history:
        messages.append(
            ChatMessage(
                role=MessageRole(msg["role"]),
                content=msg.get("content"),
                name=msg.get("name"),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id"),
            )
        )

    # Inject Writer constraints as a final user instruction without breaking client format rules.
    # This keeps provider compatibility while ensuring the Writer sees Ternion constraints even
    # when a client system prompt is present.
    writer_instructions = _prepend_global_security_rules(EXECUTION_PROMPT)

    # Build the final user instruction content
    revision_count = state.get("revision_count", 0)
    review_feedback = state.get("review_feedback", "")
    previous_code = state.get("generated_code", "")

    evidence_bundle = str(state.get("evidence_bundle") or "EVIDENCE_BUNDLE:\n- None")
    evidence_gaps = str(state.get("evidence_gaps") or "EVIDENCE_GAPS:\n- None")
    evidence_chain_index = list(state.get("evidence_chain_index") or [])
    topup_round_used = int(state.get("evidence_topup_round", 0) or 0)
    deliverable_policy_text, evidence_chain_lines, topup_status_lines = (
        _build_execution_policy_context(
            ternion_report=ternion_report,
            latest_user_message=latest_user_message,
            evidence_bundle=evidence_bundle,
            evidence_gaps=evidence_gaps,
            evidence_chain_index=evidence_chain_index,
            evidence_topup_round=topup_round_used,
        )
    )

    content_parts = [
        "[TERNION WRITER INSTRUCTIONS]\n\n",
        writer_instructions,
        "\n\n[TERNION ANALYSIS REPORT]\n\n",
        ternion_report,
        *evidence_chain_lines,
        "\n\n[DELIVERABLE POLICY]\n\n",
        deliverable_policy_text,
        *topup_status_lines,
    ]
    if tool_context_digest:
        content_parts.extend([
            "\n\n[TERNION TOOL CONTEXT DIGEST]\n\n",
            tool_context_digest,
        ])

    # If this is a revision round, always include reviewer feedback section
    # Even if feedback is empty, provide a placeholder to prevent Writer confusion
    if revision_count > 0:
        # Use placeholder if feedback is empty (e.g., truncated or missing)
        feedback_content = review_feedback.strip() if review_feedback else (
            "[NOTE] Reviewer requested revision but feedback content is empty or missing. "
            "Please carefully review your deliverable for potential issues based on "
            "the original analysis report."
        )
        # Use placeholder if previous code is empty (edge case)
        code_content = previous_code.strip() if previous_code else (
            "[NOTE] No previous deliverable found. This may indicate an error in the "
            "workflow. Please generate a fresh deliverable based on the analysis report."
        )
        content_parts.extend([
            "\n\n[REVIEWER FEEDBACK - REVISION REQUIRED]\n\n",
            feedback_content,
            "\n\n[CURRENT DELIVERABLE]\n\n",
            code_content,
            "\n\nAddress the issues above and revise the deliverable(s) based on the "
            "report and reviewer feedback, following the deliverable policy and allowed "
            "write scope.",
        ])
    else:
        content_parts.append(
            "\n\nProceed with the requested deliverable(s) based on the report above, "
            "and follow the deliverable policy and allowed write scope."
        )

    # Add the Ternion Analysis Report + Writer instructions as the final instruction.
    messages.append(
        ChatMessage(
            role=MessageRole.USER,
            content="".join(content_parts),
        )
    )

    # Use Writer (Claude with fallback)
    try:
        provider = provider_manager.get_provider_for_role("writer")

        # Get user-configured model from config_store
        model = role_cfg.model if role_cfg and role_cfg.model else None

        # Hard validation: model must be explicitly configured
        if not model:
            logger.error("writer_model_not_configured")
            error_msg = t(
                MessageKey.ROLE_CONFIG_INCOMPLETE,
                missing_roles=_format_role_names(["writer"]),
            )
            return {
                **state,
                "errors": state.get("errors", []) + [
                    error_msg
                ],
                "thinking_logs": thinking_logs + [
                    t(MessageKey.EXECUTION_ERROR, error=error_msg)
                ],
            }

        # Get stream queue from state for real-time output (if available)
        stream_queue: StreamEventQueue | None = state.get("_stream_queue")
        session_id = state.get("session_id", "")

        supports_native_tools = getattr(provider, "supports_native_tool_calls", False) is True
        supports_text_tools = bool(cursor_tools) and not supports_native_tools
        should_use_tool_calls = bool(cursor_tools) and (supports_native_tools or supports_text_tools)
        writer_timeout = WRITER_TIMEOUT_SECONDS

        if supports_text_tools and messages:
            last_msg = messages[-1]
            if last_msg.role == MessageRole.USER and isinstance(last_msg.content, str):
                last_msg.content = (
                    last_msg.content
                    + "\n\n[NON-OPENAI TOOL CALLS]\n\n"
                    + build_text_tool_calls_instruction(cursor_tools)
                )

        log_manager.emit(
            level="INFO",
            category="WORKFLOW",
            message=(
                "execution_writer_context | "
                f"session_id={session_id} | "
                f"history_messages={len(history)} | "
                f"history_truncated={truncated_history} | "
                f"digest_chars={len(tool_context_digest)} | "
                f"tools={len(cursor_tools)} | "
                f"revision_count={revision_count} | "
                f"timeout_seconds={writer_timeout}"
            ),
        )

        if should_use_tool_calls:
            extra_kwargs: dict[str, Any] = {}
            if supports_native_tools:
                extra_kwargs["tools"] = cursor_tools
                if cursor_tool_choice is not None:
                    extra_kwargs["tool_choice"] = cursor_tool_choice
            import time
            started = time.monotonic()
            if stream_queue:
                response = await _call_with_stream(
                    provider=provider,
                    messages=messages,
                    model=model,
                    temperature=0.3,
                    stream_queue=stream_queue,
                    phase="execution",
                    message_id=session_id,
                    timeout_seconds=writer_timeout,
                    detect_tool_calls=True,
                    **extra_kwargs,
                )
            else:
                response = await _call_with_timeout(
                    provider=provider,
                    messages=messages,
                    model=model,
                    temperature=0.3,
                    timeout_seconds=writer_timeout,
                    **extra_kwargs,
                )
            if supports_text_tools and not response.tool_calls:
                parsed_tool_calls = extract_tool_calls_from_text(response.content)
                if parsed_tool_calls:
                    response.tool_calls = parsed_tool_calls
                    response.content = ""
            elapsed = time.monotonic() - started
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    "execution_writer_call_done | "
                    f"session_id={session_id} | "
                    f"elapsed_seconds={elapsed:.2f} | "
                    f"tool_calls={len(response.tool_calls or []) if response.tool_calls else 0} | "
                    f"content_chars={len(response.content or '')}"
                ),
            )
            usage = response.usage or {}
            input_tokens = (
                usage.get("prompt_tokens")
                or usage.get("input_tokens")
                or 0
            )
            completion_tokens = (
                usage.get("completion_tokens")
                or usage.get("output_tokens")
                or 0
            )
            thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
            output_for_cost = (
                completion_tokens if provider.name != "google" else completion_tokens + thoughts_tokens
            )
            budget_manager.record_usage(
                provider=provider.name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_for_cost,
                thoughts_tokens=thoughts_tokens,
                context_length=usage.get("total_tokens", 0),
            )
            if input_tokens or output_for_cost or thoughts_tokens:
                log_manager.emit(
                    level="INFO",
                    category="WORKFLOW",
                    message=(
                        f"execution_usage | provider={provider.name} | "
                        f"model={model} | "
                        f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens} | "
                        f"total={usage.get('total_tokens', input_tokens + output_for_cost)}"
                    ),
                )
            if response.tool_calls:
                log_manager.emit(
                    level="INFO",
                    category="WORKFLOW",
                    message=(
                        "execution_writer_tool_calls_ready | "
                        f"session_id={session_id} | "
                        f"count={len(response.tool_calls)}"
                    ),
                )
                return {
                    **state,
                    "current_phase": WorkflowPhase.EXECUTION.value,
                    "pending_tool_calls": response.tool_calls,
                    "thinking_logs": thinking_logs,
                }
            if not (response.content or "").strip():
                raise ValueError("writer_returned_empty_output")
            topup_block = extract_evidence_requests_block(
                response.content,
                default_requester="execution",
            )
            if topup_block is not None:
                used_round = int(state.get("evidence_topup_round", 0) or 0)
                payload_error = _validate_evidence_requests_payload(topup_block.requests_text)
                policy_error = _validate_evidence_topup_request(
                    used_round=used_round,
                    final_request=topup_block.final_request,
                )
                topup_error = payload_error or policy_error
                if topup_error:
                    # Soft handling: retry once to avoid an extra user round-trip.
                    last = messages[-1] if messages else None
                    if (
                        last
                        and last.role == MessageRole.USER
                        and isinstance(last.content, str)
                    ):
                        last.content += (
                            "\n\n[TERNION EVIDENCE TOP-UP GUARDRAIL]\n\n"
                            f"{sanitize_for_cursor_display(topup_error)}\n\n"
                            "Proceed:\n"
                            "- If you still need evidence and TOPUP_ROUNDS_REMAINING > 0, re-issue the evidence top-up block with correct PURPOSE lines.\n"
                            "- If TOPUP_ROUNDS_REMAINING == 0, do NOT request more evidence. Proceed with the deliverable using existing evidence.\n"
                        )

                    response = await _call_with_stream(
                        provider=provider,
                        messages=messages,
                        model=model,
                        temperature=0.3,
                        stream_queue=stream_queue,
                        phase="execution",
                        message_id=session_id,
                        timeout_seconds=writer_timeout,
                        detect_tool_calls=True,
                        **extra_kwargs,
                    )
                    if supports_text_tools and not response.tool_calls:
                        parsed_tool_calls = extract_tool_calls_from_text(response.content)
                        if parsed_tool_calls:
                            response.tool_calls = parsed_tool_calls
                            response.content = ""
                    if response.tool_calls:
                        return {
                            **state,
                            "current_phase": WorkflowPhase.EXECUTION.value,
                            "pending_tool_calls": response.tool_calls,
                            "thinking_logs": thinking_logs,
                        }
                    if not (response.content or "").strip():
                        raise ValueError("writer_returned_empty_output")
                    retry_block = extract_evidence_requests_block(
                        response.content,
                        default_requester="execution",
                    )
                    if retry_block is not None:
                        used_round = int(state.get("evidence_topup_round", 0) or 0)
                        payload_error = _validate_evidence_requests_payload(
                            retry_block.requests_text
                        )
                        policy_error = _validate_evidence_topup_request(
                            used_round=used_round,
                            final_request=retry_block.final_request,
                        )
                        topup_error = payload_error or policy_error
                        if topup_error:
                            return {
                                **state,
                                "current_phase": WorkflowPhase.COMPLETE.value,
                                "errors": state.get("errors", []) + [topup_error],
                                "final_output": sanitize_for_cursor_display(topup_error),
                                "thinking_logs": thinking_logs,
                            }
                        return {
                            **state,
                            "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                            "evidence_requests": retry_block.requests_text,
                            "report_evidence_resume_phase": WorkflowPhase.EXECUTION.value,
                            "evidence_topup_round": used_round + 1,
                            "thinking_logs": thinking_logs,
                        }
                else:
                    return {
                        **state,
                        "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                        "evidence_requests": topup_block.requests_text,
                        "report_evidence_resume_phase": WorkflowPhase.EXECUTION.value,
                        "evidence_topup_round": used_round + 1,
                        "thinking_logs": thinking_logs,
                    }
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    "execution_writer_deliverable_done | "
                    f"session_id={session_id} | "
                    f"content_chars={len(response.content or '')}"
                ),
            )
            thinking_logs.append(t(MessageKey.EXECUTION_COMPLETE))
            return {
                **state,
                "current_phase": WorkflowPhase.OPTIMIZER.value,
                "generated_code": response.content,
                "thinking_logs": thinking_logs,
            }
        # Use streaming call if queue is available, otherwise fall back to non-streaming
        response = await _call_with_stream(
            provider=provider,
            messages=messages,
            model=model,
            temperature=0.3,  # Lower temperature for deterministic output
            stream_queue=stream_queue,
            phase="execution",
            message_id=session_id,
            timeout_seconds=writer_timeout,
        )
        if not (response.content or "").strip():
            raise ValueError("writer_returned_empty_output")
        topup_block = extract_evidence_requests_block(
            response.content,
            default_requester="execution",
        )
        if topup_block is not None:
            used_round = int(state.get("evidence_topup_round", 0) or 0)
            payload_error = _validate_evidence_requests_payload(topup_block.requests_text)
            policy_error = _validate_evidence_topup_request(
                used_round=used_round,
                final_request=topup_block.final_request,
            )
            topup_error = payload_error or policy_error
            if topup_error:
                last = messages[-1] if messages else None
                if (
                    last
                    and last.role == MessageRole.USER
                    and isinstance(last.content, str)
                ):
                    last.content += (
                        "\n\n[TERNION EVIDENCE TOP-UP GUARDRAIL]\n\n"
                        f"{sanitize_for_cursor_display(topup_error)}\n\n"
                        "Proceed:\n"
                        "- If you still need evidence and TOPUP_ROUNDS_REMAINING > 0, re-issue the evidence top-up block with correct PURPOSE lines.\n"
                        "- If TOPUP_ROUNDS_REMAINING == 0, do NOT request more evidence. Proceed with the deliverable using existing evidence.\n"
                    )
                response = await _call_with_stream(
                    provider=provider,
                    messages=messages,
                    model=model,
                    temperature=0.3,
                    stream_queue=stream_queue,
                    phase="execution",
                    message_id=session_id,
                    timeout_seconds=writer_timeout,
                )
                if not (response.content or "").strip():
                    raise ValueError("writer_returned_empty_output")
                retry_block = extract_evidence_requests_block(
                    response.content,
                    default_requester="execution",
                )
                if retry_block is not None:
                    used_round = int(state.get("evidence_topup_round", 0) or 0)
                    payload_error = _validate_evidence_requests_payload(
                        retry_block.requests_text
                    )
                    policy_error = _validate_evidence_topup_request(
                        used_round=used_round,
                        final_request=retry_block.final_request,
                    )
                    topup_error = payload_error or policy_error
                    if topup_error:
                        return {
                            **state,
                            "current_phase": WorkflowPhase.COMPLETE.value,
                            "errors": state.get("errors", []) + [topup_error],
                            "final_output": sanitize_for_cursor_display(topup_error),
                            "thinking_logs": thinking_logs,
                        }
                    return {
                        **state,
                        "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                        "evidence_requests": retry_block.requests_text,
                        "report_evidence_resume_phase": WorkflowPhase.EXECUTION.value,
                        "evidence_topup_round": used_round + 1,
                        "thinking_logs": thinking_logs,
                    }
            else:
                return {
                    **state,
                    "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                    "evidence_requests": topup_block.requests_text,
                    "report_evidence_resume_phase": WorkflowPhase.EXECUTION.value,
                    "evidence_topup_round": used_round + 1,
                    "thinking_logs": thinking_logs,
                }
        usage = response.usage or {}
        input_tokens = (
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or 0
        )
        completion_tokens = (
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or 0
        )
        thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
        output_for_cost = completion_tokens if provider.name != "google" else completion_tokens + thoughts_tokens
        if input_tokens or output_for_cost or thoughts_tokens:
            budget_manager.record_usage(
                provider=provider.name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_for_cost,
                thoughts_tokens=thoughts_tokens,
                context_length=usage.get("total_tokens", 0),
            )
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    f"execution_usage | provider={provider.name} | "
                    f"model={model} | "
                    f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens} | "
                    f"total={usage.get('total_tokens', input_tokens + output_for_cost)}"
                ),
            )

        log_manager.emit(
            level="INFO",
            category="WORKFLOW",
            message=(
                "execution_writer_deliverable_done | "
                f"session_id={session_id} | "
                f"content_chars={len(response.content or '')}"
            ),
        )
        thinking_logs.append(t(MessageKey.EXECUTION_COMPLETE))

        return {
            **state,
            "current_phase": WorkflowPhase.OPTIMIZER.value,
            "generated_code": response.content,
            "thinking_logs": thinking_logs,
        }
    except Exception as e:
        logger.error("execution_failed", error=str(e))
        log_manager.emit(
            level="ERROR",
            category="WORKFLOW",
            message=f"Execution failed | error={str(e)}",
        )
        error_msg = t(MessageKey.EXECUTION_FAILED, error=str(e))
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "generated_code": "",
            "errors": state.get("errors", []) + [error_msg],
            "thinking_logs": thinking_logs
            + [t(MessageKey.EXECUTION_ERROR, error=str(e))],
        }


async def final_check_node(state: TernionState) -> TernionState:
    """
    Step 4: The Final Check - Reviewer Verification.

    The Reviewer checks the generated code for security
    and logic issues. May approve or request revision.

    Args:
        state: Current workflow state with generated code

    Returns:
        Updated state with review result
    """
    logger.info("workflow_final_check_start")
    log_manager.emit(
        level="INFO",
        category="WORKFLOW",
        message="Final check phase started | Reviewer verifying code",
    )

    thinking_logs = list(state.get("thinking_logs", []))
    thinking_logs.append(t(MessageKey.REVIEW_START))

    generated_code = state.get("generated_code", "")
    revision_count = state.get("revision_count", 0)
    max_revisions = settings.discussion.max_revision_rounds

    # Check revision limit
    if revision_count >= max_revisions:
        logger.warning("max_revisions_reached", count=revision_count)
        log_manager.emit(
            level="INFO",
            category="WORKFLOW",
            message=(
                "Final check skipped | max revisions reached | "
                f"revision_count={revision_count} | max_revisions={max_revisions}"
            ),
        )
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "review_result": ReviewResult.APPROVED.value,
            "review_feedback": t(MessageKey.REVIEW_MAX_REVISIONS_REACHED),
            "final_output": generated_code,
            "thinking_logs": thinking_logs,
        }

    # Build review messages with analysis context
    ternion_report = state.get("ternion_report", "")

    # Build review content with analysis context for proper validation
    review_content_parts = [
        "[TERNION ANALYSIS REPORT]\n\n",
        ternion_report,
        "\n\n[IMPLEMENTATION TO REVIEW]\n\n",
        generated_code,
        "\n\nReview the implementation above for:\n",
        "1. Correctness: Does it properly address the issues identified in the analysis?\n",
        "2. Security: Are there any security vulnerabilities?\n",
        "3. Logic: Are there any logical errors or edge cases not handled?\n",
    ]

    messages = [
        ChatMessage(
            role=MessageRole.SYSTEM,
            content=_prepend_global_security_rules(FINAL_CHECK_PROMPT),
        ),
        ChatMessage(
            role=MessageRole.USER,
            content="".join(review_content_parts),
        ),
    ]

    # Use Reviewer (GPT with fallback)
    try:
        provider = provider_manager.get_provider_for_role("reviewer")

        # Get user-configured model from config_store
        role_cfg = config_store.get_role_config("reviewer")
        model = role_cfg.model if role_cfg and role_cfg.model else None

        # Hard validation: model must be explicitly configured
        if not model:
            logger.error("reviewer_model_not_configured")
            error_msg = t(
                MessageKey.ROLE_CONFIG_INCOMPLETE,
                missing_roles=_format_role_names(["reviewer"]),
            )
            return {
                **state,
                "errors": state.get("errors", []) + [
                    error_msg
                ],
                "thinking_logs": thinking_logs + [
                    t(MessageKey.FINAL_CHECK_ERROR, error=error_msg)
                ],
            }

        response = await _call_with_timeout(
            provider=provider,
            messages=messages,
            model=model,
            temperature=0.2,  # Low temperature for critical review
        )
        usage = response.usage or {}
        input_tokens = (
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or 0
        )
        completion_tokens = (
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or 0
        )
        thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
        output_for_cost = completion_tokens if provider.name != "google" else completion_tokens + thoughts_tokens
        if input_tokens or output_for_cost or thoughts_tokens:
            budget_manager.record_usage(
                provider=provider.name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_for_cost,
                thoughts_tokens=thoughts_tokens,
                context_length=usage.get("total_tokens", 0),
            )
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    f"final_check_usage | provider={provider.name} | "
                    f"model={model} | "
                    f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens} | "
                    f"total={usage.get('total_tokens', input_tokens + output_for_cost)}"
                ),
            )

        review_status = _parse_review_status(response.content)

        if review_status == ReviewResult.APPROVED:
            try:
                from ternion.utils.reviewer_output_capture import (
                    build_reviewer_capture_payload,
                    schedule_reviewer_output_capture,
                )

                schedule_reviewer_output_capture(
                    build_reviewer_capture_payload(
                        session_id=str(state.get("session_id") or ""),
                        stage=str(state.get("current_phase") or ""),
                        provider=provider.name,
                        model=model,
                        review_status="APPROVED",
                        review_feedback=response.content,
                        revision_count=revision_count,
                        generated_code=generated_code,
                    )
                )
            except Exception:
                pass
            thinking_logs.append(t(MessageKey.REVIEW_APPROVED))
            return {
                **state,
                "current_phase": WorkflowPhase.COMPLETE.value,
                "review_result": ReviewResult.APPROVED.value,
                "review_feedback": response.content,
                "final_output": generated_code,
                "thinking_logs": thinking_logs,
            }
        else:
            try:
                from ternion.utils.reviewer_output_capture import (
                    build_reviewer_capture_payload,
                    schedule_reviewer_output_capture,
                )

                schedule_reviewer_output_capture(
                    build_reviewer_capture_payload(
                        session_id=str(state.get("session_id") or ""),
                        stage=str(state.get("current_phase") or ""),
                        provider=provider.name,
                        model=model,
                        review_status="REVISION_NEEDED",
                        review_feedback=response.content,
                        revision_count=revision_count,
                        generated_code=generated_code,
                    )
                )
            except Exception:
                pass
            # Revision needed - will loop back to execution
            thinking_logs.append(t(MessageKey.REVIEW_REVISION))
            return {
                **state,
                "current_phase": WorkflowPhase.EXECUTION.value,
                "review_result": ReviewResult.REVISION_NEEDED.value,
                "review_feedback": response.content,
                "revision_count": revision_count + 1,
                "thinking_logs": thinking_logs,
            }
    except Exception as e:
        logger.warning("review_failed", error=str(e))
        log_manager.emit(
            level="WARN",
            category="WORKFLOW",
            message=f"Final check failed (skipped) | error={str(e)}",
        )
        error_msg = t(MessageKey.REVIEW_SKIPPED, error=str(e))
        try:
            from ternion.utils.reviewer_output_capture import (
                build_reviewer_capture_payload,
                schedule_reviewer_output_capture,
            )

            schedule_reviewer_output_capture(
                build_reviewer_capture_payload(
                    session_id=str(state.get("session_id") or ""),
                    stage=str(state.get("current_phase") or ""),
                    provider="(unknown)",
                    model="(unknown)",
                    review_status="SKIPPED",
                    review_feedback=error_msg,
                    revision_count=revision_count,
                    generated_code=generated_code,
                )
            )
        except Exception:
            pass
        # Skip review on failure, approve the code
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "review_result": ReviewResult.APPROVED.value,
            "review_feedback": error_msg,
            "final_output": generated_code,
            "errors": state.get("errors", []) + [error_msg],
            "thinking_logs": thinking_logs
            + [t(MessageKey.FINAL_CHECK_ERROR, error=str(e))],
        }


async def optimizer_node(state: TernionState) -> TernionState:
    """
    Development override: Optimizer phase (replaces Reviewer gate).

    The Optimizer validates the implementation against acceptance criteria,
    applies only necessary improvements via tool calls, and finally outputs:
    - an internal optimizer report (captured to disk; user-invisible)
    - a user-visible work summary report
    """
    logger.info("workflow_optimizer_start")
    log_manager.emit(
        level="INFO",
        category="WORKFLOW",
        message="Optimizer phase started | Validating and improving implementation",
    )

    thinking_logs = list(state.get("thinking_logs", []))

    # Use the Web UI language preference for Optimizer output (internal + user-visible summary).
    user_config = config_store.load()
    language_code = user_config.language
    if language_code == "auto":
        language_code = user_config.browser_language or "en"
    language_name = get_language_name(language_code)
    instruction_template = get_optimizer_language_instruction_template()
    language_instruction = (
        instruction_template.format(language_name=language_name) if instruction_template else ""
    )
    optimizer_prompt_with_lang = f"{OPTIMIZER_PROMPT}\n\nOUTPUT LANGUAGE:\n{language_instruction}\n"

    ternion_report = state.get("ternion_report", "")
    generated_code = state.get("generated_code", "")

    baseline = state.get("baseline_file_snapshots") or {}
    modified_files = state.get("modified_files") or []
    writer_output_files = state.get("writer_output_files") or {}

    history = state.get("conversation_history", [])
    latest_user_message = get_latest_user_message(history)
    history_len_before = len(history)
    tool_context_digest = ""
    truncated_history = False
    try:
        from ternion.utils.execution_history_compaction import (
            ExecutionHistoryCompactionConfig,
            compact_execution_history_for_writer,
        )

        history, tool_context_digest = compact_execution_history_for_writer(
            history,
            config=ExecutionHistoryCompactionConfig(),
        )
        truncated_history = len(history) != history_len_before
    except Exception:
        tool_context_digest = ""
        truncated_history = False

    cursor_tools = _filter_execution_cursor_tools(state.get("cursor_tools") or [])
    cursor_tool_choice = state.get("cursor_tool_choice")
    role_cfg = config_store.get_role_config("reviewer")

    messages: list[ChatMessage] = [
        ChatMessage(
            role=MessageRole.SYSTEM,
            content=_prepend_global_security_rules(optimizer_prompt_with_lang),
        )
    ]

    for msg in history:
        messages.append(
            ChatMessage(
                role=MessageRole(msg["role"]),
                content=msg.get("content"),
                name=msg.get("name"),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id"),
            )
        )

    optimizer_instructions = _prepend_global_security_rules(optimizer_prompt_with_lang)
    evidence_bundle = str(state.get("evidence_bundle") or "EVIDENCE_BUNDLE:\n- None")
    evidence_gaps = str(state.get("evidence_gaps") or "EVIDENCE_GAPS:\n- None")
    evidence_chain_index = list(state.get("evidence_chain_index") or [])
    topup_round_used = int(state.get("evidence_topup_round", 0) or 0)
    deliverable_policy_text, evidence_chain_lines, topup_status_lines = (
        _build_execution_policy_context(
            ternion_report=ternion_report,
            latest_user_message=latest_user_message,
            evidence_bundle=evidence_bundle,
            evidence_gaps=evidence_gaps,
            evidence_chain_index=evidence_chain_index,
            evidence_topup_round=topup_round_used,
        )
    )

    content_parts: list[str] = [
        "[TERNION OPTIMIZER INSTRUCTIONS]\n\n",
        optimizer_instructions,
        "\n\n[TERNION ANALYSIS REPORT]\n\n",
        ternion_report,
        *evidence_chain_lines,
        "\n\n[DELIVERABLE POLICY]\n\n",
        deliverable_policy_text,
        *topup_status_lines,
    ]
    if tool_context_digest:
        content_parts.extend([
            "\n\n[TERNION TOOL CONTEXT DIGEST]\n\n",
            tool_context_digest,
        ])

    if modified_files:
        content_parts.extend([
            "\n\n[MODIFIED FILES]\n\n",
            "\n".join(f"- {p}" for p in modified_files),
        ])

    if baseline:
        content_parts.append("\n\n[ORIGINAL CODE BASELINE - PRE-CHANGE]\n\n")
        for path, content in baseline.items():
            content_parts.extend([
                f"\n\nFILE: {path}\n",
                "-----\n",
                content,
                "\n-----\n",
            ])

    if writer_output_files:
        content_parts.append("\n\n[WRITER OUTPUT FILES - POST-CHANGE]\n\n")
        for path, content in writer_output_files.items():
            content_parts.extend([
                f"\n\nFILE: {path}\n",
                "-----\n",
                content,
                "\n-----\n",
            ])

    if generated_code:
        content_parts.extend([
            "\n\n[WRITER OUTPUT TEXT]\n\n",
            generated_code,
        ])

    messages.append(
        ChatMessage(
            role=MessageRole.USER,
            content="".join(content_parts),
        )
    )

    try:
        provider = provider_manager.get_provider_for_role("reviewer")
        model = role_cfg.model if role_cfg and role_cfg.model else None
        if not model:
            logger.error("optimizer_model_not_configured")
            error_msg = t(
                MessageKey.ROLE_CONFIG_INCOMPLETE,
                missing_roles=_format_role_names(["optimizer"]),
            )
            return {
                **state,
                "errors": state.get("errors", []) + [
                    error_msg
                ],
                "thinking_logs": thinking_logs + [
                    t(MessageKey.FINAL_CHECK_ERROR, error=error_msg)
                ],
                "current_phase": WorkflowPhase.COMPLETE.value,
            }

        supports_native_tools = getattr(provider, "supports_native_tool_calls", False) is True
        supports_text_tools = bool(cursor_tools) and not supports_native_tools
        should_use_tool_calls = bool(cursor_tools) and (supports_native_tools or supports_text_tools)

        if supports_text_tools and messages:
            last_msg = messages[-1]
            if last_msg.role == MessageRole.USER and isinstance(last_msg.content, str):
                last_msg.content = (
                    last_msg.content
                    + "\n\n[NON-OPENAI TOOL CALLS]\n\n"
                    + build_text_tool_calls_instruction(cursor_tools)
                )

        session_id = state.get("session_id", "")
        log_manager.emit(
            level="INFO",
            category="WORKFLOW",
            message=(
                "optimizer_context | "
                f"session_id={session_id} | "
                f"history_messages={len(history)} | "
                f"history_truncated={truncated_history} | "
                f"digest_chars={len(tool_context_digest)} | "
                f"tools={len(cursor_tools)} | "
                f"baseline_files={len(baseline)} | "
                f"writer_files={len(writer_output_files)}"
            ),
        )

        stream_queue: StreamEventQueue | None = state.get("_stream_queue")

        extra_kwargs: dict[str, Any] = {}
        if should_use_tool_calls and supports_native_tools:
            extra_kwargs["tools"] = cursor_tools
            if cursor_tool_choice is not None:
                extra_kwargs["tool_choice"] = cursor_tool_choice

        import time

        started = time.monotonic()
        optimizer_timeout = WRITER_TIMEOUT_SECONDS
        streamed_user_summary = False
        if stream_queue:
            response, streamed_user_summary = await _call_optimizer_with_stream(
                provider=provider,
                messages=messages,
                model=model,
                temperature=0.2,
                stream_queue=stream_queue,
                phase="optimizer",
                message_id=session_id,
                timeout_seconds=optimizer_timeout,
                detect_tool_calls=should_use_tool_calls,
                **extra_kwargs,
            )
        else:
            response = await _call_with_timeout(
                provider=provider,
                messages=messages,
                model=model,
                temperature=0.2,
                timeout_seconds=optimizer_timeout,
                **extra_kwargs,
            )
        if supports_text_tools and not response.tool_calls:
            parsed_tool_calls = extract_tool_calls_from_text(response.content)
            if parsed_tool_calls:
                response.tool_calls = parsed_tool_calls
                response.content = ""
        elapsed = time.monotonic() - started
        log_manager.emit(
            level="INFO",
            category="WORKFLOW",
            message=(
                "optimizer_call_done | "
                f"session_id={session_id} | "
                f"elapsed_seconds={elapsed:.2f} | "
                f"tool_calls={len(response.tool_calls or []) if response.tool_calls else 0} | "
                f"content_chars={len(response.content or '')}"
            ),
        )

        if response.tool_calls:
            return {
                **state,
                "current_phase": WorkflowPhase.OPTIMIZER.value,
                "pending_tool_calls": response.tool_calls,
                "thinking_logs": thinking_logs,
            }

        topup_block = extract_evidence_requests_block(
            response.content,
            default_requester="optimizer",
        )
        if topup_block is not None:
            used_round = int(state.get("evidence_topup_round", 0) or 0)
            payload_error = _validate_evidence_requests_payload(topup_block.requests_text)
            policy_error = _validate_evidence_topup_request(
                used_round=used_round,
                final_request=topup_block.final_request,
            )
            topup_error = payload_error or policy_error
            if topup_error:
                last = messages[-1] if messages else None
                if (
                    last
                    and last.role == MessageRole.USER
                    and isinstance(last.content, str)
                ):
                    last.content += (
                        "\n\n[TERNION EVIDENCE TOP-UP GUARDRAIL]\n\n"
                        f"{sanitize_for_cursor_display(topup_error)}\n\n"
                        "Proceed:\n"
                        "- If you still need evidence and TOPUP_ROUNDS_REMAINING > 0, re-issue the evidence top-up block with correct PURPOSE lines.\n"
                        "- If TOPUP_ROUNDS_REMAINING == 0, do NOT request more evidence. Proceed with the deliverable using existing evidence.\n"
                    )

                if stream_queue:
                    response, _streamed_user_summary = await _call_optimizer_with_stream(
                        provider=provider,
                        messages=messages,
                        model=model,
                        temperature=0.2,
                        stream_queue=stream_queue,
                        phase="optimizer",
                        message_id=session_id,
                        timeout_seconds=optimizer_timeout,
                        detect_tool_calls=should_use_tool_calls,
                        **extra_kwargs,
                    )
                else:
                    response = await _call_with_timeout(
                        provider=provider,
                        messages=messages,
                        model=model,
                        temperature=0.2,
                        timeout_seconds=optimizer_timeout,
                        **extra_kwargs,
                    )
                if supports_text_tools and not response.tool_calls:
                    parsed_tool_calls = extract_tool_calls_from_text(response.content)
                    if parsed_tool_calls:
                        response.tool_calls = parsed_tool_calls
                        response.content = ""
                if response.tool_calls:
                    return {
                        **state,
                        "current_phase": WorkflowPhase.OPTIMIZER.value,
                        "pending_tool_calls": response.tool_calls,
                        "thinking_logs": thinking_logs,
                    }

                retry_block = extract_evidence_requests_block(
                    response.content,
                    default_requester="optimizer",
                )
                if retry_block is not None:
                    used_round = int(state.get("evidence_topup_round", 0) or 0)
                    payload_error = _validate_evidence_requests_payload(
                        retry_block.requests_text
                    )
                    policy_error = _validate_evidence_topup_request(
                        used_round=used_round,
                        final_request=retry_block.final_request,
                    )
                    topup_error = payload_error or policy_error
                    if topup_error:
                        return {
                            **state,
                            "current_phase": WorkflowPhase.COMPLETE.value,
                            "errors": state.get("errors", []) + [topup_error],
                            "final_output": sanitize_for_cursor_display(topup_error),
                            "thinking_logs": thinking_logs,
                        }
                    return {
                        **state,
                        "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                        "evidence_requests": retry_block.requests_text,
                        "report_evidence_resume_phase": WorkflowPhase.OPTIMIZER.value,
                        "evidence_topup_round": used_round + 1,
                        "thinking_logs": thinking_logs,
                    }
            else:
                return {
                    **state,
                    "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                    "evidence_requests": topup_block.requests_text,
                    "report_evidence_resume_phase": WorkflowPhase.OPTIMIZER.value,
                    "evidence_topup_round": used_round + 1,
                    "thinking_logs": thinking_logs,
                }

        internal_report, user_summary = _split_optimizer_output(response.content or "")
        if not (user_summary or "").strip():
            user_summary = t(MessageKey.OPTIMIZER_OUTPUT_PROTOCOL_ERROR)
        user_summary_safe = sanitize_for_cursor_display(user_summary)
        if stream_queue and user_summary_safe and not streamed_user_summary:
            # Ensure the user-visible summary is streamed even if the optimizer
            # wrapper markers were missing or not detected during streaming.
            for i in range(0, len(user_summary_safe), 128):
                await stream_queue.put_token(
                    delta=user_summary_safe[i:i + 128],
                    phase="optimizer",
                    message_id=session_id,
                )

        try:
            from ternion.utils.reviewer_output_capture import (
                build_reviewer_capture_payload,
                schedule_reviewer_output_capture,
            )

            schedule_reviewer_output_capture(
                build_reviewer_capture_payload(
                    session_id=str(state.get("session_id") or ""),
                    stage=WorkflowPhase.OPTIMIZER.value,
                    provider=provider.name,
                    model=model,
                    review_status="OPTIMIZER_REPORT",
                    review_feedback=internal_report or (response.content or ""),
                    revision_count=int(state.get("revision_count", 0) or 0),
                    generated_code=generated_code,
                )
            )
        except Exception:
            pass

        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "optimizer_review_report": internal_report,
            "final_output": user_summary_safe,
            "thinking_logs": thinking_logs,
        }
    except Exception as e:
        logger.warning("optimizer_failed", error=str(e))
        log_manager.emit(
            level="WARN",
            category="WORKFLOW",
            message=f"Optimizer failed | error={str(e)}",
        )
        error_msg = t(MessageKey.OPTIMIZER_FAILED, error=str(e))
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + [error_msg],
            "final_output": sanitize_for_cursor_display(error_msg),
            "thinking_logs": thinking_logs,
        }

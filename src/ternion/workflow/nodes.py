"""
Node implementations for the Ternion LangGraph workflow.

Each node represents a step in the 4-step discussion flow.
"""

import asyncio
from typing import Any

import structlog

from ternion.core.budget import budget_manager
from ternion.core.config import settings
from ternion.core.config_store import config_store
from ternion.core.exceptions import TimeoutError as TernionTimeout
from ternion.core.models import ChatMessage, MessageRole
from ternion.core.session_store import (
    ExecutionMode,
    session_store,
)
from ternion.providers.base import ProviderResponse
from ternion.providers.manager import provider_manager
from ternion.router.prompts import (
    CONVERGENCE_PROMPT,
    DIVERGENCE_PROMPT,
    EXECUTION_PROMPT,
    FINAL_CHECK_PROMPT,
    GLOBAL_SECURITY_RULES,
    OPTIMIZER_PROMPT,
)
from ternion.utils.cursor_safety import sanitize_for_cursor_display, sanitize_for_preview
from ternion.utils.i18n import MessageKey, t
from ternion.utils.log_manager import log_manager
from ternion.utils.report_parser import format_report_for_display
from ternion.utils.tool_calls_parser import (
    build_text_tool_calls_instruction,
    extract_tool_calls_from_text,
)
from ternion.workflow.state import ReviewResult, TernionState, WorkflowPhase
from ternion.workflow.streaming_events import StreamEventQueue

logger = structlog.get_logger(__name__)

# Optimizer output wrapper markers (development override).
_OPTIMIZER_INTERNAL_BEGIN = "TERNION_OPTIMIZER_INTERNAL_REPORT_BEGIN"
_OPTIMIZER_INTERNAL_END = "TERNION_OPTIMIZER_INTERNAL_REPORT_END"
_OPTIMIZER_USER_BEGIN = "TERNION_OPTIMIZER_USER_SUMMARY_BEGIN"
_OPTIMIZER_USER_END = "TERNION_OPTIMIZER_USER_SUMMARY_END"

# Default timeout for provider calls (CR-030)
DEFAULT_TIMEOUT_SECONDS = settings.discussion.timeout_seconds


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
        )

        # Consume stream with an idle timeout between chunks.
        async def consume_stream() -> str:
            nonlocal full_content
            while True:
                try:
                    chunk = await asyncio.wait_for(stream_gen.__anext__(), timeout=timeout)
                except StopAsyncIteration:
                    break
                if not chunk:
                    continue
                full_content += chunk
                await stream_queue.put_token(
                    delta=chunk,
                    phase=phase,
                    message_id=message_id,
                )
            return full_content

        full_content = await consume_stream()

        # Signal completion with final content
        await stream_queue.put_final(
            content=full_content,
            phase=phase,
            message_id=message_id,
        )

        # Note: Token usage is tracked inside provider.chat_completion_stream
        # We return a simplified ProviderResponse here
        return ProviderResponse(
            content=full_content,
            finish_reason="stop",
            usage={},  # Usage is tracked by provider internally
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
        logger.exception("stream_error", provider=provider.name, error=str(e))
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

    Three ternion members (Gemini, GPT, Claude) analyze the problem
    concurrently, focusing on root cause analysis without writing code.

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
    system_prompt = _prepend_global_security_rules(DIVERGENCE_PROMPT)
    ternion_messages = [
        ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
    ]
    for msg in history:
        ternion_messages.append(
            ChatMessage(role=MessageRole(msg["role"]), content=msg["content"])
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
        error_msg = f"Ternion models not configured: {', '.join(unconfigured)}. Please configure in Web Control Panel."
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
                return {
                    "ternion_id": ternion_id,
                    "provider": provider_name,
                    "analysis": "",
                    "error": f"Provider {provider_name} not configured",
                }

            response = await _call_with_timeout(
                provider=provider,
                messages=ternion_messages,
                model=model,
                temperature=0.7,
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

    return {
        **state,
        "current_phase": WorkflowPhase.CONVERGENCE.value,
        "ternion_analyses": list(analyses),
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
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + ["No ternion analyses available"],
            "ternion_report": "",
            "is_consensus": False,
        }

    # Get effective language for report generation
    user_config = config_store.load()
    language_code = user_config.language
    if language_code == "auto":
        language_code = user_config.browser_language or "en"

    # Language code to full name mapping
    language_names = {
        "en": "English",
        "zh": "Simplified Chinese (简体中文)",
        "es": "Spanish (Español)",
        "fr": "French (Français)",
        "de": "German (Deutsch)",
        "ja": "Japanese (日本語)",
        "ko": "Korean (한국어)",
    }
    language_name = language_names.get(language_code, "English")

    # Create language instruction
    language_instruction = f"Generate the entire report in {language_name}. All headings, bullet points, and explanations must be in {language_name}."

    # Build synthesis prompt with language instruction
    convergence_prompt_with_lang = CONVERGENCE_PROMPT.format(language_instruction=language_instruction)

    synthesis_content = "Council Analyses:\n\n"
    for analysis in successful_analyses:
        synthesis_content += f"### {analysis['ternion_id'].upper()}\n"
        synthesis_content += f"{analysis['analysis']}\n\n"

    messages = [
        ChatMessage(
            role=MessageRole.SYSTEM,
            content=_prepend_global_security_rules(convergence_prompt_with_lang),
        ),
        ChatMessage(role=MessageRole.USER, content=synthesis_content),
    ]

    # Use Arbiter (Gemini with fallback)
    try:
        provider = provider_manager.get_provider_for_role("arbiter")

        # Get user-configured model from config_store
        role_cfg = config_store.get_role_config("arbiter")
        model = role_cfg.model if role_cfg and role_cfg.model else None

        # Hard validation: model must be explicitly configured
        if not model:
            logger.error("arbiter_model_not_configured")
            return {
                **state,
                "errors": state.get("errors", []) + [
                    "Arbiter model not configured. Please configure it in the Web Control Panel."
                ],
                "thinking_logs": thinking_logs + [
                    t(MessageKey.CONVERGENCE_ERROR, error="Arbiter model not configured")
                ],
            }

        # Get stream queue from state for real-time output (if available)
        stream_queue: StreamEventQueue | None = state.get("_stream_queue")
        session_id = state.get("session_id", "")

        # Use streaming call if queue is available, otherwise fall back to non-streaming
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
            }
        else:
            # Direct execution mode (no confirmation required)
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
                }
            else:
                return {
                    **state,
                    "current_phase": WorkflowPhase.EXECUTION.value,
                    "ternion_report": fallback_response.content,
                    "is_consensus": len(successful_analyses) > 1,
                    "thinking_logs": thinking_logs,
                }

        # All fallbacks failed - use raw analysis as last resort
        fallback_report = successful_analyses[0]["analysis"]
        thinking_logs.append(t(MessageKey.CONVERGENCE_ERROR, error="All Arbiters failed, using raw analysis"))
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
                "errors": state.get("errors", []) + [f"All Arbiter fallbacks failed: {str(e)}"],
            }
        else:
            return {
                **state,
                "current_phase": WorkflowPhase.EXECUTION.value,
                "ternion_report": fallback_report,
                "is_consensus": False,
                "thinking_logs": thinking_logs,
                "errors": state.get("errors", []) + [f"All Arbiter fallbacks failed: {str(e)}"],
            }


async def execution_node(state: TernionState) -> TernionState:
    """
    Step 3: The Execution - Writer Generates Code.

    The Writer generates the final code fix based on
    the Ternion Analysis Report. Uses Cursor's original system
    prompt to ensure output format compatibility.

    Args:
        state: Current workflow state with analysis report

    Returns:
        Updated state with generated code
    """
    logger.info("workflow_execution_start")
    log_manager.emit(
        level="INFO",
        category="WORKFLOW",
        message="Execution phase started | Writer generating code",
    )

    thinking_logs = list(state.get("thinking_logs", []))
    thinking_logs.append(t(MessageKey.EXECUTION_START))

    # Build messages with Cursor's system prompt (for format compliance)
    cursor_prompt = state.get("cursor_system_prompt")
    ternion_report = state.get("ternion_report", "")
    history = state.get("conversation_history", [])
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

    cursor_tools = state.get("cursor_tools") or []
    cursor_tool_choice = state.get("cursor_tool_choice")
    role_cfg = config_store.get_role_config("writer")
    provider_name = role_cfg.provider if role_cfg and role_cfg.provider else ""
    use_text_tool_calls = bool(cursor_tools) and provider_name and provider_name != "openai"

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

    content_parts = [
        "[TERNION WRITER INSTRUCTIONS]\n\n",
        writer_instructions,
        "\n\n[TERNION ANALYSIS REPORT]\n\n",
        ternion_report,
    ]
    if tool_context_digest:
        content_parts.extend([
            "\n\n[TERNION TOOL CONTEXT DIGEST]\n\n",
            tool_context_digest,
        ])
    if use_text_tool_calls:
        content_parts.extend([
            "\n\n[NON-OPENAI TOOL CALLS]\n\n",
            build_text_tool_calls_instruction(cursor_tools),
        ])

    # If this is a revision round, always include reviewer feedback section
    # Even if feedback is empty, provide a placeholder to prevent Writer confusion
    if revision_count > 0:
        # Use placeholder if feedback is empty (e.g., truncated or missing)
        feedback_content = review_feedback.strip() if review_feedback else (
            "[NOTE] Reviewer requested revision but feedback content is empty or missing. "
            "Please carefully review your implementation for potential issues based on "
            "the original analysis report."
        )
        # Use placeholder if previous code is empty (edge case)
        code_content = previous_code.strip() if previous_code else (
            "[NOTE] No previous implementation found. This may indicate an error in the "
            "workflow. Please generate a fresh implementation based on the analysis report."
        )
        content_parts.extend([
            "\n\n[REVIEWER FEEDBACK - REVISION REQUIRED]\n\n",
            feedback_content,
            "\n\n[CURRENT IMPLEMENTATION]\n\n",
            code_content,
            "\n\nAddress the issues above and revise the implementation.",
        ])
    else:
        content_parts.append("\n\nProceed with the implementation based on the report above.")

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
            return {
                **state,
                "errors": state.get("errors", []) + [
                    "Writer model not configured. Please configure it in the Web Control Panel."
                ],
                "thinking_logs": thinking_logs + [
                    t(MessageKey.EXECUTION_ERROR, error="Writer model not configured")
                ],
            }

        # Get stream queue from state for real-time output (if available)
        stream_queue: StreamEventQueue | None = state.get("_stream_queue")
        session_id = state.get("session_id", "")

        supports_native_tools = provider.name == "openai"
        supports_text_tools = bool(cursor_tools) and provider.name != "openai"
        should_use_tool_calls = bool(cursor_tools) and (supports_native_tools or supports_text_tools)

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
                f"revision_count={revision_count}"
            ),
        )

        if should_use_tool_calls:
            if stream_queue:
                await stream_queue.put_token(
                    delta="\n" + t(MessageKey.EXECUTION_START),
                    phase="execution",
                    message_id=session_id,
                )
            extra_kwargs: dict[str, Any] = {}
            if supports_native_tools:
                extra_kwargs["tools"] = cursor_tools
                if cursor_tool_choice is not None:
                    extra_kwargs["tool_choice"] = cursor_tool_choice
            import time
            started = time.monotonic()
            response = await _call_with_timeout(
                provider=provider,
                messages=messages,
                model=model,
                temperature=0.3,
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
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    "execution_writer_coding_done | "
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
            temperature=0.3,  # Lower temperature for code generation
            stream_queue=stream_queue,
            phase="execution",
            message_id=session_id,
        )
        if not (response.content or "").strip():
            raise ValueError("writer_returned_empty_output")
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

        log_manager.emit(
            level="INFO",
            category="WORKFLOW",
            message=(
                "execution_writer_coding_done | "
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
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "generated_code": "",
            "errors": state.get("errors", []) + [f"Execution failed: {str(e)}"],
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
            "review_feedback": "Max revisions reached, proceeding with current code.",
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
            return {
                **state,
                "errors": state.get("errors", []) + [
                    "Reviewer model not configured. Please configure it in the Web Control Panel."
                ],
                "thinking_logs": thinking_logs + [
                    t(MessageKey.FINAL_CHECK_ERROR, error="Reviewer model not configured")
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
                    review_feedback=f"Review skipped due to error: {str(e)}",
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
            "review_feedback": f"Review skipped due to error: {str(e)}",
            "final_output": generated_code,
            "errors": state.get("errors", []) + [f"Review skipped: {str(e)}"],
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
    language_names = {
        "en": "English",
        "zh": "Simplified Chinese (简体中文)",
        "es": "Spanish (Español)",
        "fr": "French (Français)",
        "de": "German (Deutsch)",
        "ja": "Japanese (日本語)",
        "ko": "Korean (한국어)",
    }
    language_name = language_names.get(language_code, "English")
    language_instruction = (
        "Generate BOTH the internal optimizer report and the user-visible work summary in "
        f"{language_name}. All headings, bullet points, and explanations must be in {language_name}. "
        "Do NOT translate the wrapper marker lines."
    )
    optimizer_prompt_with_lang = f"{OPTIMIZER_PROMPT}\n\nOUTPUT LANGUAGE:\n{language_instruction}\n"

    ternion_report = state.get("ternion_report", "")
    generated_code = state.get("generated_code", "")

    baseline = state.get("baseline_file_snapshots") or {}
    modified_files = state.get("modified_files") or []
    writer_output_files = state.get("writer_output_files") or {}

    history = state.get("conversation_history", [])
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

    cursor_tools = state.get("cursor_tools") or []
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
    content_parts: list[str] = [
        "[TERNION OPTIMIZER INSTRUCTIONS]\n\n",
        optimizer_instructions,
        "\n\n[TERNION ANALYSIS REPORT]\n\n",
        ternion_report,
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
            return {
                **state,
                "errors": state.get("errors", []) + [
                    "Optimizer model not configured. Please configure it in the Web Control Panel."
                ],
                "thinking_logs": thinking_logs + [
                    t(MessageKey.FINAL_CHECK_ERROR, error="Optimizer model not configured")
                ],
                "current_phase": WorkflowPhase.COMPLETE.value,
            }

        supports_native_tools = provider.name == "openai"
        supports_text_tools = bool(cursor_tools) and provider.name != "openai"
        should_use_tool_calls = bool(cursor_tools) and (supports_native_tools or supports_text_tools)

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
        if stream_queue:
            await stream_queue.put_token(
                delta="\n" + t(MessageKey.OPTIMIZER_START),
                phase="optimizer",
                message_id=session_id,
            )

        extra_kwargs: dict[str, Any] = {}
        if should_use_tool_calls and supports_native_tools:
            extra_kwargs["tools"] = cursor_tools
            if cursor_tool_choice is not None:
                extra_kwargs["tool_choice"] = cursor_tool_choice

        import time

        started = time.monotonic()
        response = await _call_with_timeout(
            provider=provider,
            messages=messages,
            model=model,
            temperature=0.2,
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

        internal_report, user_summary = _split_optimizer_output(response.content or "")
        if not (user_summary or "").strip():
            user_summary = t(MessageKey.OPTIMIZER_OUTPUT_PROTOCOL_ERROR)
        user_summary_safe = sanitize_for_cursor_display(user_summary)

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
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + [f"Optimizer failed: {str(e)}"],
            "final_output": sanitize_for_cursor_display(
                f"[Ternion Error] Optimizer failed: {str(e)}"
            ),
            "thinking_logs": thinking_logs,
        }

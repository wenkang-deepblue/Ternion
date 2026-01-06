"""
API routes for Ternion gateway.

Implements OpenAI-compatible endpoints for chat completions and models listing.
"""

import re

import structlog
from fastapi import APIRouter
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
from ternion.utils.i18n import MessageKey, get_web_base_url, t
from ternion.utils.log_manager import log_manager
from ternion.utils.report_parser import parse_structured_report
from ternion.utils.streaming import create_sse_stream

logger = structlog.get_logger(__name__)
router = APIRouter()

_PATCHLIKE_TRIGGERS = (
    "*** Begin Patch",
    "*** End Patch",
    "*** Update File:",
    "*** Add File:",
    "diff --git",
)


def _is_patch_or_diff_output(text: str) -> bool:
    """
    Detect whether an output likely contains a diff/patch that should remain "patch-only".

    This is used to avoid prefixing the final output with thinking logs, which can
    reduce Cursor's auto-apply stability in strict patch-only scenarios.
    """
    if not text:
        return False
    return any(trigger in text for trigger in _PATCHLIKE_TRIGGERS)


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


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@router.get("/v1/models")
async def list_models() -> ModelsListResponse:
    """List available models (OpenAI-compatible)."""
    # Intentionally expose only Ternion models.
    #
    # Rationale: When users enable "Override OpenAI Base URL" in Cursor to point at Ternion,
    # exposing passthrough provider models (gpt/claude/gemini) can cause accidental BYOK
    # usage and unexpected extra costs.
    return ModelsListResponse(data=list(TERNION_MODELS))


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

    # Convert messages to dict format for parsing
    messages_as_dicts = [
        {"role": msg.role.value if hasattr(msg.role, "value") else msg.role, "content": msg.content}
        for msg in request.messages
    ]

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

                return await handle_session_followup(session, intent, latest_message, request)

            elif session.stage in (SessionStage.CONFIRMED, SessionStage.EXECUTED):
                # Session already confirmed/executed - handle post-execution follow-up
                logger.info(
                    "session_post_execution",
                    session_id=session_id,
                    stage=session.stage.value,
                    execution_mode=session.execution_mode.value,
                )

                return await handle_post_execution_followup(session, latest_message, request)

            elif session.stage == SessionStage.REJECTED:
                # Session was rejected - provide clear guidance
                logger.info(
                    "session_rejected_followup",
                    session_id=session_id,
                    has_feedback=bool(session.last_user_feedback),
                )

                return await handle_rejected_session_followup(session, latest_message, request)

    # Extract context using MessageRouter
    context = message_router.extract_context(request.messages)

    # Set session management flags from user config
    user_config = config_store.load()
    context.await_confirmation = True  # Always require confirmation for new requests
    context.execution_mode = user_config.execution_mode

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
                    "message": "No LLM providers configured. "
                    f"Please add API keys in the Web Control Panel at {get_control_panel_url()}",
                    "type": "configuration_error",
                }
            },
        )

    # Check role configuration completeness (depends on execution mode)
    missing_roles = []
    required_roles = ["ternion_a", "ternion_b", "ternion_c", "arbiter"]
    if user_config.execution_mode == "ternion_full":
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
    budget_ok, budget_warning = budget_manager.check_budget(estimated_cost=0.15)
    if not budget_ok:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "message": budget_warning or "Budget exceeded",
                    "type": "budget_exceeded",
                }
            },
        )

    # Run the Ternion discussion workflow
    try:
        from ternion.workflow.graph import run_discussion

        final_state = await run_discussion(context)

        # Build output with thinking logs + final code
        thinking_logs = final_state.get("thinking_logs", [])
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

        # Add budget warning if approaching limit
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

        output = "".join(output_parts)

        # Return response
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
    if intent == Intent.CONFIRM:
        return await handle_confirmed_session(session, request)
    elif intent == Intent.REJECT:
        return await handle_rejected_session(session, user_message, request)
    elif intent == Intent.CLARIFY:
        # Answer question using existing report without re-running RCA
        return await handle_clarify_request(session, user_message, request)
    else:  # UNKNOWN
        return await handle_unknown_intent(session, request)


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
    session_store.update_session(session.session_id, stage=SessionStage.CONFIRMED)

    if session.execution_mode == ExecutionMode.CURSOR_HANDOFF:
        # Log session confirmation for handoff mode
        logger.info(
            "session_confirmed",
            session_id=session.session_id,
            execution_mode="cursor_handoff",
            action="generating_handoff_package",
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

        # Build output using the already-loaded config
        output_parts = []
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
    context.await_confirmation = True  # Still require confirmation for new report
    context.rejection_context = feedback
    context.execution_mode = session.execution_mode.value

    # Add rejection context to thinking
    logger.info(
        "session_rejected_reanalyze",
        session_id=session.session_id,
        feedback_preview=feedback[:100],
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

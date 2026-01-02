"""
Node implementations for the Ternion LangGraph workflow.

Each node represents a step in the 4-step discussion flow.
"""

import asyncio
import structlog
from typing import Any

from ternion.core.config import settings
from ternion.core.config_store import config_store
from ternion.core.budget import budget_manager
from ternion.core.models import ChatMessage, MessageRole
from ternion.providers.manager import provider_manager
from ternion.router.prompts import (
    DIVERGENCE_PROMPT,
    CONVERGENCE_PROMPT,
    EXECUTION_PROMPT,
    FINAL_CHECK_PROMPT,
    GLOBAL_SECURITY_RULES,
)
from ternion.utils.i18n import t, ThinkingLogKey
from ternion.utils.log_manager import log_manager
from ternion.workflow.state import TernionState, WorkflowPhase, ReviewResult

logger = structlog.get_logger(__name__)


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


def _sanitize_preview(text: str, max_length: int = 100) -> str:
    """
    Sanitize preview text to prevent triggering Cursor's apply logic.

    Breaks potential trigger patterns like code fences (```) that could
    cause unintended behavior when displayed in thinking logs.

    Args:
        text: Raw text to sanitize
        max_length: Maximum length of preview

    Returns:
        Sanitized preview string safe for display
    """
    if not text:
        return ""
    
    # Truncate and replace newlines
    preview = text[:max_length].replace("\n", " ")
    if len(text) > max_length:
        preview += "..."
    
    # Break code fence triggers by inserting zero-width space
    # This prevents Cursor from interpreting ``` as code block markers
    preview = preview.replace("```", "`\u200b`\u200b`")
    
    # Also break common markdown triggers that might cause issues
    preview = preview.replace("~~~", "~\u200b~\u200b~")
    
    return preview


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
    
    thinking_logs = list(state.get("thinking_logs", []))
    thinking_logs.append(t(ThinkingLogKey.DIVERGENCE_START))

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

            response = await provider.chat_completion(
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
        preview = _sanitize_preview(a["analysis"])
        thinking_logs.append(t(ThinkingLogKey.DIVERGENCE_ANALYSIS, ternion_id=a['ternion_id'], preview=preview))

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
    
    thinking_logs = list(state.get("thinking_logs", []))
    thinking_logs.append(t(ThinkingLogKey.CONVERGENCE_START))

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

    # Build synthesis prompt
    synthesis_content = "Council Analyses:\n\n"
    for analysis in successful_analyses:
        synthesis_content += f"### {analysis['ternion_id'].upper()}\n"
        synthesis_content += f"{analysis['analysis']}\n\n"

    messages = [
        ChatMessage(
            role=MessageRole.SYSTEM,
            content=_prepend_global_security_rules(CONVERGENCE_PROMPT),
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
                    t(ThinkingLogKey.CONVERGENCE_ERROR, error="Arbiter model not configured")
                ],
            }
        
        response = await provider.chat_completion(
            messages=messages,
            model=model,
            temperature=0.5,  # Lower temperature for synthesis
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

        preview = _sanitize_preview(response.content, max_length=80)
        thinking_logs.append(t(ThinkingLogKey.CONVERGENCE_COMPLETE, preview=preview))

        return {
            **state,
            "current_phase": WorkflowPhase.EXECUTION.value,
            "ternion_report": response.content,
            "is_consensus": len(successful_analyses) > 1,
            "thinking_logs": thinking_logs,
        }
    except Exception as e:
        logger.error("convergence_failed", error=str(e))
        # Use best available analysis as fallback
        return {
            **state,
            "current_phase": WorkflowPhase.EXECUTION.value,
            "ternion_report": successful_analyses[0]["analysis"],
            "is_consensus": False,
            "errors": state.get("errors", []) + [f"Convergence fallback: {str(e)}"],
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
    
    thinking_logs = list(state.get("thinking_logs", []))
    thinking_logs.append(t(ThinkingLogKey.EXECUTION_START))

    # Build messages with Cursor's system prompt (for format compliance)
    cursor_prompt = state.get("cursor_system_prompt")
    ternion_report = state.get("ternion_report", "")
    history = state.get("conversation_history", [])

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
            ChatMessage(role=MessageRole(msg["role"]), content=msg["content"])
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
        role_cfg = config_store.get_role_config("writer")
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
                    t(ThinkingLogKey.EXECUTION_ERROR, error="Writer model not configured")
                ],
            }
        
        response = await provider.chat_completion(
            messages=messages,
            model=model,
            temperature=0.3,  # Lower temperature for code generation
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
                    f"execution_usage | provider={provider.name} | "
                    f"model={model} | "
                    f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens} | "
                    f"total={usage.get('total_tokens', input_tokens + output_for_cost)}"
                ),
            )

        thinking_logs.append(t(ThinkingLogKey.EXECUTION_COMPLETE))

        return {
            **state,
            "current_phase": WorkflowPhase.FINAL_CHECK.value,
            "generated_code": response.content,
            "thinking_logs": thinking_logs,
        }
    except Exception as e:
        logger.error("execution_failed", error=str(e))
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "generated_code": "",
            "errors": state.get("errors", []) + [f"Execution failed: {str(e)}"],
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
    
    thinking_logs = list(state.get("thinking_logs", []))
    thinking_logs.append(t(ThinkingLogKey.REVIEW_START))

    generated_code = state.get("generated_code", "")
    revision_count = state.get("revision_count", 0)
    max_revisions = settings.discussion.max_revision_rounds

    # Check revision limit
    if revision_count >= max_revisions:
        logger.warning("max_revisions_reached", count=revision_count)
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "review_result": ReviewResult.APPROVED.value,
            "review_feedback": "Max revisions reached, proceeding with current code.",
            "final_output": generated_code,
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
                    t(ThinkingLogKey.FINAL_CHECK_ERROR, error="Reviewer model not configured")
                ],
            }
        
        response = await provider.chat_completion(
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
            thinking_logs.append(t(ThinkingLogKey.REVIEW_APPROVED))
            return {
                **state,
                "current_phase": WorkflowPhase.COMPLETE.value,
                "review_result": ReviewResult.APPROVED.value,
                "review_feedback": response.content,
                "final_output": generated_code,
                "thinking_logs": thinking_logs,
            }
        else:
            # Revision needed - will loop back to execution
            thinking_logs.append(t(ThinkingLogKey.REVIEW_REVISION))
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
        # Skip review on failure, approve the code
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "review_result": ReviewResult.APPROVED.value,
            "review_feedback": f"Review skipped due to error: {str(e)}",
            "final_output": generated_code,
            "errors": state.get("errors", []) + [f"Review skipped: {str(e)}"],
        }

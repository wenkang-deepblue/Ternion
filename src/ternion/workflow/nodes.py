"""
Node implementations for the Ternion LangGraph workflow.

Each node represents a step in the 4-step discussion flow.
"""

import asyncio
import structlog
from typing import Any

from ternion.core.config import settings
from ternion.core.models import ChatMessage, MessageRole
from ternion.providers.manager import provider_manager
from ternion.router.prompts import (
    DIVERGENCE_PROMPT,
    CONVERGENCE_PROMPT,
    EXECUTION_PROMPT,
    FINAL_CHECK_PROMPT,
)
from ternion.workflow.state import TernionState, WorkflowPhase, ReviewResult

logger = structlog.get_logger(__name__)


async def divergence_node(state: TernionState) -> TernionState:
    """
    Step 1: The Divergence - Parallel Root Cause Analysis.

    Three council members (Gemini, GPT, Claude) analyze the problem
    concurrently, focusing on root cause analysis without writing code.

    Args:
        state: Current workflow state

    Returns:
        Updated state with council analyses
    """
    logger.info("workflow_divergence_start")

    # Build messages for council - use Ternion RCA prompt, not Cursor's
    history = state.get("conversation_history", [])
    council_messages = [
        ChatMessage(role=MessageRole.SYSTEM, content=DIVERGENCE_PROMPT),
    ]
    for msg in history:
        council_messages.append(
            ChatMessage(role=MessageRole(msg["role"]), content=msg["content"])
        )

    # Run council analyses in parallel
    providers = ["google", "openai", "anthropic"]
    council_ids = ["council_1", "council_2", "council_3"]

    async def analyze(provider_name: str, council_id: str) -> dict[str, Any]:
        try:
            provider = provider_manager.get_provider(provider_name)
            if not provider:
                return {
                    "council_id": council_id,
                    "provider": provider_name,
                    "analysis": "",
                    "error": f"Provider {provider_name} not configured",
                }

            response = await provider.chat_completion(
                messages=council_messages,
                temperature=0.7,
            )
            return {
                "council_id": council_id,
                "provider": provider_name,
                "analysis": response.content,
                "error": None,
            }
        except Exception as e:
            logger.warning(
                "council_analysis_failed",
                council_id=council_id,
                provider=provider_name,
                error=str(e),
            )
            return {
                "council_id": council_id,
                "provider": provider_name,
                "analysis": "",
                "error": str(e),
            }

    # Execute concurrently
    tasks = [
        analyze(provider, council_id)
        for provider, council_id in zip(providers, council_ids)
    ]
    analyses = await asyncio.gather(*tasks)

    # Filter successful analyses
    successful = [a for a in analyses if not a.get("error")]
    logger.info(
        "workflow_divergence_complete",
        successful_count=len(successful),
        total_count=len(analyses),
    )

    return {
        **state,
        "current_phase": WorkflowPhase.CONVERGENCE.value,
        "council_analyses": list(analyses),
    }


async def convergence_node(state: TernionState) -> TernionState:
    """
    Step 2: The Convergence - Arbiter Synthesis.

    The Arbiter (Gemini) synthesizes all council analyses,
    resolves conflicts, and produces a unified Ternion Analysis Report.

    Args:
        state: Current workflow state with council analyses

    Returns:
        Updated state with synthesized report
    """
    logger.info("workflow_convergence_start")

    analyses = state.get("council_analyses", [])
    successful_analyses = [a for a in analyses if not a.get("error")]

    if not successful_analyses:
        logger.error("no_successful_analyses")
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + ["No council analyses available"],
            "ternion_report": "",
            "is_consensus": False,
        }

    # Build synthesis prompt
    synthesis_content = "Council Analyses:\n\n"
    for analysis in successful_analyses:
        synthesis_content += f"### {analysis['council_id'].upper()}\n"
        synthesis_content += f"{analysis['analysis']}\n\n"

    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content=CONVERGENCE_PROMPT),
        ChatMessage(role=MessageRole.USER, content=synthesis_content),
    ]

    # Use Arbiter (Gemini with fallback)
    try:
        provider = provider_manager.get_provider_for_role("arbiter")
        response = await provider.chat_completion(
            messages=messages,
            temperature=0.5,  # Lower temperature for synthesis
        )

        return {
            **state,
            "current_phase": WorkflowPhase.EXECUTION.value,
            "ternion_report": response.content,
            "is_consensus": len(successful_analyses) > 1,
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

    The Writer (Claude) generates the final code fix based on
    the Ternion Analysis Report. Uses Cursor's original system
    prompt to ensure output format compatibility.

    Args:
        state: Current workflow state with analysis report

    Returns:
        Updated state with generated code
    """
    logger.info("workflow_execution_start")

    # Build messages with Cursor's system prompt (for format compliance)
    cursor_prompt = state.get("cursor_system_prompt")
    ternion_report = state.get("ternion_report", "")
    history = state.get("conversation_history", [])

    messages = []

    # Use Cursor's system prompt if available, otherwise use our execution prompt
    if cursor_prompt:
        messages.append(ChatMessage(role=MessageRole.SYSTEM, content=cursor_prompt))
    else:
        messages.append(ChatMessage(role=MessageRole.SYSTEM, content=EXECUTION_PROMPT))

    # Add conversation history
    for msg in history:
        messages.append(
            ChatMessage(role=MessageRole(msg["role"]), content=msg["content"])
        )

    # Add the Ternion Analysis Report
    messages.append(
        ChatMessage(
            role=MessageRole.USER,
            content=f"[TERNION ANALYSIS REPORT]\n\n{ternion_report}\n\n"
            "Based on the above analysis, please implement the fix.",
        )
    )

    # Use Writer (Claude with fallback)
    try:
        provider = provider_manager.get_provider_for_role("writer")
        response = await provider.chat_completion(
            messages=messages,
            temperature=0.3,  # Lower temperature for code generation
        )

        return {
            **state,
            "current_phase": WorkflowPhase.FINAL_CHECK.value,
            "generated_code": response.content,
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

    The Reviewer (GPT) checks the generated code for security
    and logic issues. May approve or request revision.

    Args:
        state: Current workflow state with generated code

    Returns:
        Updated state with review result
    """
    logger.info("workflow_final_check_start")

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

    # Build review messages
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content=FINAL_CHECK_PROMPT),
        ChatMessage(
            role=MessageRole.USER,
            content=f"Review this code for security and logic issues:\n\n{generated_code}",
        ),
    ]

    # Use Reviewer (GPT with fallback)
    try:
        provider = provider_manager.get_provider_for_role("reviewer")
        response = await provider.chat_completion(
            messages=messages,
            temperature=0.2,  # Low temperature for critical review
        )

        review_text = response.content.lower()

        # Parse review result
        if "approved" in review_text or "lgtm" in review_text:
            return {
                **state,
                "current_phase": WorkflowPhase.COMPLETE.value,
                "review_result": ReviewResult.APPROVED.value,
                "review_feedback": response.content,
                "final_output": generated_code,
            }
        else:
            # Revision needed - will loop back to execution
            return {
                **state,
                "current_phase": WorkflowPhase.EXECUTION.value,
                "review_result": ReviewResult.REVISION_NEEDED.value,
                "review_feedback": response.content,
                "revision_count": revision_count + 1,
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

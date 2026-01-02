"""
LangGraph workflow definition for Ternion discussions.

Defines the state machine graph that orchestrates the 4-step discussion flow
with conditional edges for review loops.
"""

import structlog
from typing import Any

from langgraph.graph import StateGraph, END

from ternion.core.models import ChatMessage, MessageRole
from ternion.router.context import TernionContext
from ternion.workflow.state import TernionState, WorkflowPhase
from ternion.workflow.nodes import (
    divergence_node,
    convergence_node,
    execution_node,
    final_check_node,
)

logger = structlog.get_logger(__name__)


def should_continue_to_execution(state: TernionState) -> str:
    """
    Determine next step after convergence.

    Always proceeds to execution if we have a report.
    """
    if state.get("ternion_report"):
        return "execution"
    return END


def should_continue_after_review(state: TernionState) -> str:
    """
    Determine next step after review.

    Returns to execution if revision needed, otherwise ends.
    """
    phase = state.get("current_phase", "")

    if phase == WorkflowPhase.COMPLETE.value:
        return END
    elif phase == WorkflowPhase.EXECUTION.value:
        # Revision needed - loop back
        return "execution"
    else:
        return END


def create_workflow() -> StateGraph:
    """
    Create the Ternion discussion workflow graph.

    The workflow follows the 4-step diamond strategy:
    1. Divergence: Parallel analysis by council
    2. Convergence: Arbiter synthesis
    3. Execution: Writer generates code
    4. Final Check: Reviewer verification (with optional loop)

    Returns:
        Compiled LangGraph workflow
    """
    # Create the graph
    workflow = StateGraph(TernionState)

    # Add nodes for each step
    workflow.add_node("divergence", divergence_node)
    workflow.add_node("convergence", convergence_node)
    workflow.add_node("execution", execution_node)
    workflow.add_node("final_check", final_check_node)

    # Set entry point
    workflow.set_entry_point("divergence")

    # Add edges
    workflow.add_edge("divergence", "convergence")
    workflow.add_conditional_edges(
        "convergence",
        should_continue_to_execution,
        {
            "execution": "execution",
            END: END,
        },
    )
    workflow.add_edge("execution", "final_check")
    workflow.add_conditional_edges(
        "final_check",
        should_continue_after_review,
        {
            "execution": "execution",
            END: END,
        },
    )

    return workflow.compile()


# Global compiled workflow
_workflow = None


def get_workflow() -> StateGraph:
    """Get or create the compiled workflow."""
    global _workflow
    if _workflow is None:
        _workflow = create_workflow()
    return _workflow


async def run_discussion(context: TernionContext) -> dict[str, Any]:
    """
    Run the full Ternion discussion workflow.

    Args:
        context: The extracted context from the Cursor request

    Returns:
        Final state with generated output
    """
    logger.info(
        "discussion_starting",
        has_system_prompt=context.cursor_system_prompt is not None,
        history_length=len(context.conversation_history),
    )

    # Build initial state
    initial_state: TernionState = {
        "cursor_system_prompt": (
            context.cursor_system_prompt.content
            if context.cursor_system_prompt and isinstance(context.cursor_system_prompt.content, str)
            else None
        ),
        "conversation_history": [
            {"role": msg.role.value, "content": msg.content}
            for msg in context.conversation_history
            # Filter out system messages to prevent phase prompt override
            # Also preserve both str and list (multimodal) content
            if msg.content is not None and msg.role != MessageRole.SYSTEM
        ],
        "has_images": context.has_images,
        "current_phase": WorkflowPhase.DIVERGENCE.value,
        "council_analyses": [],
        "is_consensus": False,
        "ternion_report": "",
        "generated_code": "",
        "review_result": "",
        "review_feedback": "",
        "revision_count": 0,
        "errors": [],
        "thinking_logs": [],
        "final_output": "",
    }

    # Run the workflow
    workflow = get_workflow()
    final_state = await workflow.ainvoke(initial_state)

    logger.info(
        "discussion_complete",
        phase=final_state.get("current_phase"),
        revision_count=final_state.get("revision_count", 0),
        has_output=bool(final_state.get("final_output")),
        error_count=len(final_state.get("errors", [])),
    )

    return final_state

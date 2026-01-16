"""
LangGraph workflow definition for Ternion discussions.

Defines the state machine graph that orchestrates the 4-step discussion flow
with conditional edges for review loops.
"""

from typing import Any

import structlog
from langgraph.graph import END, StateGraph

from ternion.core.models import MessageRole
from ternion.router.context import TernionContext
from ternion.workflow.nodes import (
    convergence_node,
    divergence_node,
    execution_node,
    optimizer_node,
)
from ternion.workflow.state import TernionState, WorkflowPhase

logger = structlog.get_logger(__name__)


def should_continue_or_await_confirmation(state: TernionState) -> str:
    """
    Determine next step after convergence.

    If await_confirmation is True, stop workflow and return report to user.
    Otherwise, proceed to execution if we have a report.
    """
    # Human-in-the-loop: stop for user confirmation
    if state.get("await_confirmation"):
        logger.info("workflow_awaiting_confirmation", session_id=state.get("session_id"))
        return "await_confirmation"

    # Legacy behavior: proceed if we have a report
    if state.get("ternion_report"):
        return "execution"
    return END


def should_continue_after_execution(state: TernionState) -> str:
    """
    Determine next step after execution.

    Only proceed to optimizer if execution succeeded and advanced the workflow.
    """
    phase = state.get("current_phase", "")
    if phase == WorkflowPhase.OPTIMIZER.value:
        return "optimizer"
    return END


def should_continue_after_optimizer(_state: TernionState) -> str:
    """
    Determine next step after optimizer.

    The optimizer may emit tool calls (phase remains OPTIMIZER) or complete.
    In both cases, the LangGraph workflow should stop and let the server route
    any follow-ups via the tool-loop session.
    """
    return END


def create_workflow() -> StateGraph:
    """
    Create the Ternion discussion workflow graph.

    The workflow follows the 4-step diamond strategy:
    1. Divergence: Parallel analysis by council
    2. Convergence: Arbiter synthesis
    3. Execution: Writer generates code
    4. Optimizer: Evidence-based improvement and delivery (dev override)

    Returns:
        Compiled LangGraph workflow
    """
    # Create the graph
    workflow = StateGraph(TernionState)

    # Add nodes for each step
    workflow.add_node("divergence", divergence_node)
    workflow.add_node("convergence", convergence_node)
    workflow.add_node("execution", execution_node)
    workflow.add_node("optimizer", optimizer_node)

    # Set entry point
    workflow.set_entry_point("divergence")

    # Add edges
    workflow.add_edge("divergence", "convergence")
    workflow.add_conditional_edges(
        "convergence",
        should_continue_or_await_confirmation,
        {
            "execution": "execution",
            "await_confirmation": END,  # Stop for user confirmation
            END: END,
        },
    )
    workflow.add_conditional_edges(
        "execution",
        should_continue_after_execution,
        {
            "optimizer": "optimizer",
            END: END,
        },
    )
    workflow.add_conditional_edges(
        "optimizer",
        should_continue_after_optimizer,
        {
            END: END,
        },
    )

    return workflow.compile()  # type: ignore[return-value]


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
            {
                "role": msg.role.value,
                "content": msg.content,
                "name": msg.name,
                "tool_calls": msg.tool_calls,
                "tool_call_id": msg.tool_call_id,
            }
            for msg in context.conversation_history
            if msg.role != MessageRole.SYSTEM and (
                msg.content is not None
                or msg.tool_calls is not None
                or msg.tool_call_id is not None
            )
        ],
        "has_images": context.has_images,
        "current_phase": WorkflowPhase.DIVERGENCE.value,
        # Session management (Human-in-the-Loop)
        "session_id": getattr(context, "session_id", ""),
        "await_confirmation": getattr(context, "await_confirmation", True),  # Default: require confirmation
        "execution_mode": getattr(context, "execution_mode", ""),
        "rejection_context": getattr(context, "rejection_context", ""),
        # Streaming event queue (for real-time output)
        "_stream_queue": getattr(context, "_stream_queue", None),
        # Cursor tool calling (Agent mode)
        "cursor_tools": getattr(context, "cursor_tools", None),
        "cursor_tool_choice": getattr(context, "cursor_tool_choice", None),
        # Workflow outputs
        "ternion_analyses": [],
        "is_consensus": False,
        "ternion_report": "",
        "generated_code": "",
        "baseline_file_snapshots": {},
        "modified_files": [],
        "writer_output_files": {},
        "optimizer_review_report": "",
        "review_result": "",
        "review_feedback": "",
        "revision_count": 0,
        "errors": [],
        "thinking_logs": [],
        "final_output": "",
    }

    # Run the workflow
    workflow = get_workflow()
    final_state = await workflow.ainvoke(initial_state)  # type: ignore[attr-defined]

    logger.info(
        "discussion_complete",
        phase=final_state.get("current_phase"),
        revision_count=final_state.get("revision_count", 0),
        has_output=bool(final_state.get("final_output")),
        error_count=len(final_state.get("errors", [])),
    )

    return final_state

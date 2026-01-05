"""
Implementation Stage runner for Ternion TERNION_FULL mode.

Provides a standalone execution path for running Writer + Reviewer
without going through the full LangGraph workflow. This is used after
user confirms the analysis report to avoid re-running RCA.
"""

from typing import Any

import structlog

from ternion.workflow.nodes import execution_node, final_check_node
from ternion.workflow.state import WorkflowPhase, TernionState


logger = structlog.get_logger(__name__)


async def run_implementation_stage(state: TernionState) -> dict[str, Any]:
    """
    Run Execution + Final Check (+ revision loop) starting from an existing report.

    This function bypasses divergence and convergence phases, directly running
    the Writer and Reviewer with the already-confirmed Ternion report.

    Args:
        state: TernionState with ternion_report and conversation_history already set

    Returns:
        Final state dict with generated_code, final_output, and other results.
        If required fields are missing, returns an error state with explanation.
    """
    # Input validation: Check for required fields
    missing_fields = []
    
    if not state.get("ternion_report"):
        missing_fields.append("ternion_report")
    
    if not state.get("conversation_history"):
        missing_fields.append("conversation_history")
    
    if missing_fields:
        error_msg = f"[Ternion] Implementation stage cannot proceed: missing required fields: {', '.join(missing_fields)}"
        logger.error(
            "implementation_stage_validation_failed",
            missing_fields=missing_fields,
            session_id=state.get("session_id", "unknown"),
        )
        # Return error state instead of silently failing
        state["current_phase"] = WorkflowPhase.COMPLETE.value
        state["errors"] = state.get("errors", []) + [error_msg]
        state["final_output"] = error_msg
        return state
    
    # Ensure the state is positioned at EXECUTION phase.
    state["current_phase"] = WorkflowPhase.EXECUTION.value

    # Run execution + final_check loop
    while True:
        # Run Writer (execution_node)
        state = await execution_node(state)

        # Check if execution failed or workflow should stop
        if state.get("current_phase") != WorkflowPhase.FINAL_CHECK.value:
            return state

        # Run Reviewer (final_check_node)
        state = await final_check_node(state)

        # If approved, workflow is complete
        if state.get("current_phase") == WorkflowPhase.COMPLETE.value:
            return state

        # If not back to EXECUTION (revision), something unexpected happened
        if state.get("current_phase") != WorkflowPhase.EXECUTION.value:
            return state

        # Loop continues for revision

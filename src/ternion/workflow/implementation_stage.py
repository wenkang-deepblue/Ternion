"""
Implementation Stage runner for Ternion TERNION_FULL mode.

Provides a standalone execution path for running Writer + Reviewer
without going through the full LangGraph workflow. This is used after
user confirms the analysis report to avoid re-running RCA.
"""

from typing import Any

import structlog
from pathlib import Path

from ternion.workflow.nodes import execution_node, optimizer_node
from ternion.workflow.state import TernionState, WorkflowPhase

logger = structlog.get_logger(__name__)


def _read_file_snapshots(paths: list[str]) -> dict[str, str]:
    snapshots: dict[str, str] = {}
    for path in paths or []:
        if not isinstance(path, str) or not path.strip():
            continue
        try:
            p = Path(path)
            if not p.exists() or not p.is_file():
                continue
            snapshots[str(p)] = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
    return snapshots


async def run_implementation_stage(state: TernionState) -> dict[str, Any]:
    """
    Run Execution + Optimizer starting from an existing report.

    This function bypasses divergence and convergence phases, directly running
    the Writer and Optimizer with the already-confirmed Ternion report.

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

    # Default to EXECUTION unless caller provides a specific resume phase.
    phase = state.get("current_phase") or WorkflowPhase.EXECUTION.value
    if phase not in (WorkflowPhase.EXECUTION.value, WorkflowPhase.OPTIMIZER.value):
        phase = WorkflowPhase.EXECUTION.value
    state["current_phase"] = phase

    # Run execution + optimizer loop
    while True:
        phase = state.get("current_phase") or WorkflowPhase.EXECUTION.value

        if phase == WorkflowPhase.EXECUTION.value:
            state = await execution_node(state)

            # Stop immediately if tool calls are pending (server will route follow-up).
            if state.get("pending_tool_calls"):
                return state

            # Transition to optimizer when the Writer produced an implementation.
            if state.get("current_phase") == WorkflowPhase.OPTIMIZER.value:
                if not (state.get("writer_output_files") or {}):
                    state["writer_output_files"] = _read_file_snapshots(
                        list(state.get("modified_files") or [])
                    )
                continue

            return state

        if phase == WorkflowPhase.OPTIMIZER.value:
            state = await optimizer_node(state)

            # Stop immediately if tool calls are pending (server will route follow-up).
            if state.get("pending_tool_calls"):
                return state

            return state

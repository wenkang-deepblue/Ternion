"""
LangGraph workflow definition for Ternion discussions.

Defines the state machine graph that orchestrates the 4-step discussion flow
with conditional edges for review loops.
"""

import threading
from typing import Any

import structlog
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ternion.core.models import MessageRole
from ternion.router.context import TernionContext
from ternion.workflow.nodes import (
    convergence_node,
    divergence_node,
    evidence_node,
    execution_node,
    optimizer_node,
    report_evidence_node,
)
from ternion.workflow.state import TernionState, WorkflowPhase

logger = structlog.get_logger(__name__)


def should_continue_or_await_confirmation(state: TernionState) -> str:
    """
    Determine next step after convergence.

    If await_confirmation is True, stop workflow and return report to user.
    Otherwise, proceed to execution unless the workflow has errors.
    """
    # Human-in-the-loop: stop for user confirmation
    if state.get("await_confirmation"):
        logger.info("workflow_awaiting_confirmation", session_id=state.get("session_id"))
        return "await_confirmation"

    if state.get("errors"):
        return END
    return "execution"


def should_continue_after_evidence(state: TernionState) -> str:
    """
    Determine next step after evidence collection.

    If tool calls are pending or errors occurred, stop and await tool results.
    Otherwise, proceed to divergence.
    """
    if state.get("pending_tool_calls"):
        return END
    if state.get("errors"):
        return END
    return "divergence"


def should_continue_after_report_evidence(state: TernionState) -> str:
    """
    Determine next step after Phase 1.5 report evidence collection.

    If tool calls are pending or errors occurred, stop and await tool results.
    Otherwise, route by the phase selected by report_evidence_node.
    """
    if state.get("pending_tool_calls"):
        return END
    if state.get("errors"):
        return END

    phase = str(state.get("current_phase", "") or "").strip().lower()
    if phase == WorkflowPhase.EXECUTION.value:
        return "execution"
    if phase == WorkflowPhase.OPTIMIZER.value:
        return "optimizer"
    return "convergence"


def should_continue_after_execution(state: TernionState) -> str:
    """
    Determine next step after execution.

    Execution may continue to optimizer or request Phase 1.5 evidence top-up.
    """
    phase = str(state.get("current_phase", "") or "").strip().lower()
    if phase == WorkflowPhase.REPORT_EVIDENCE.value:
        return "report_evidence"
    if phase == WorkflowPhase.OPTIMIZER.value:
        return "optimizer"
    return END


def should_continue_after_optimizer(state: TernionState) -> str:
    """
    Determine next step after optimizer.

    Optimizer may request Phase 1.5 evidence top-up before finalizing.
    """
    phase = str(state.get("current_phase", "") or "").strip().lower()
    if phase == WorkflowPhase.REPORT_EVIDENCE.value:
        return "report_evidence"
    return END


def create_workflow(*, entry_point: str = "evidence") -> CompiledStateGraph:
    """
    Create the Ternion discussion workflow graph.

    The workflow implements an evidence-first discussion pipeline:
    - Phase 0: Evidence gathering
    - Phase 1: Divergence (parallel analysis by council)
    - Phase 1.5: Report evidence (top-up for council requests)
    - Phase 2: Convergence (arbiter synthesis)
    - Phase 3: Execution (Writer generates deliverables)
    - Phase 4: Optimizer (evidence-based improvement and delivery)

    Returns:
        Compiled LangGraph workflow
    """
    valid_entry_points = {
        "evidence",
        "divergence",
        "report_evidence",
        "convergence",
        "execution",
        "optimizer",
    }
    if entry_point not in valid_entry_points:
        raise ValueError(
            f"Invalid workflow entry point: {entry_point!r}. Must be one of: {sorted(valid_entry_points)}"
        )

    workflow = StateGraph(TernionState)

    workflow.add_node("evidence", evidence_node)
    workflow.add_node("divergence", divergence_node)
    workflow.add_node("report_evidence", report_evidence_node)
    workflow.add_node("convergence", convergence_node)
    workflow.add_node("execution", execution_node)
    workflow.add_node("optimizer", optimizer_node)

    workflow.set_entry_point(entry_point)

    workflow.add_conditional_edges(
        "evidence",
        should_continue_after_evidence,
        {
            "divergence": "divergence",
            END: END,
        },
    )
    # Divergence always leads to report_evidence (Phase 1.5)
    workflow.add_edge("divergence", "report_evidence")
    # Report evidence phase may pause for tool calls or proceed to convergence
    workflow.add_conditional_edges(
        "report_evidence",
        should_continue_after_report_evidence,
        {
            "convergence": "convergence",
            "execution": "execution",
            "optimizer": "optimizer",
            END: END,
        },
    )
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
            "report_evidence": "report_evidence",
            "optimizer": "optimizer",
            END: END,
        },
    )
    workflow.add_conditional_edges(
        "optimizer",
        should_continue_after_optimizer,
        {
            "report_evidence": "report_evidence",
            END: END,
        },
    )

    return workflow.compile()


# Global compiled workflow
_workflow: CompiledStateGraph | None = None
_report_evidence_workflow: CompiledStateGraph | None = None
_workflow_lock = threading.Lock()
_report_evidence_workflow_lock = threading.Lock()


def get_workflow() -> CompiledStateGraph:
    """Get or create the compiled workflow."""
    global _workflow
    if _workflow is None:
        with _workflow_lock:
            if _workflow is None:
                _workflow = create_workflow(entry_point="evidence")
    return _workflow


def get_report_evidence_workflow() -> CompiledStateGraph:
    """Get or create the compiled workflow starting from Phase 1.5."""
    global _report_evidence_workflow
    if _report_evidence_workflow is None:
        with _report_evidence_workflow_lock:
            if _report_evidence_workflow is None:
                _report_evidence_workflow = create_workflow(entry_point="report_evidence")
    return _report_evidence_workflow


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
            if context.cursor_system_prompt
            and isinstance(context.cursor_system_prompt.content, str)
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
            if msg.role != MessageRole.SYSTEM
            and (
                msg.content is not None
                or msg.tool_calls is not None
                or msg.tool_call_id is not None
            )
        ],
        "has_images": context.has_images,
        "workspace_root": getattr(context, "workspace_root", ""),
        "current_phase": WorkflowPhase.EVIDENCE.value,
        # Session management (Human-in-the-Loop)
        "session_id": getattr(context, "session_id", ""),
        "await_confirmation": getattr(
            context, "await_confirmation", True
        ),  # Default: require confirmation
        "execution_mode": getattr(context, "execution_mode", ""),
        "rejection_context": getattr(context, "rejection_context", ""),
        # Streaming event queue (for real-time output)
        "_stream_queue": getattr(context, "_stream_queue", None),
        # Cursor tool calling (Agent mode)
        "cursor_tools": getattr(context, "cursor_tools", None),
        "cursor_tool_choice": getattr(context, "cursor_tool_choice", None),
        "evidence_bundle": "",
        "evidence_gaps": "",
        # Workflow outputs
        "ternion_analyses": [],
        "evidence_requests": "",  # Phase 1.5: council member evidence requests
        "evidence_chain_index": [],
        "is_consensus": False,
        "ternion_report": "",
        "generated_code": "",
        "baseline_file_snapshots": {},
        "modified_files": [],
        "writer_output_files": {},
        "optimizer_review_report": "",
        "stabilized_document_paths": [],
        "review_feedback": "",
        "revision_count": 0,
        "errors": [],
        "thinking_logs": [],
        "final_output": "",
        "final_output_suffix": "",
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


async def resume_report_evidence(
    context: TernionContext,
    *,
    evidence_bundle: str,
    evidence_gaps: str,
    evidence_requests: str,
    ternion_analyses: list[dict[str, Any]],
    evidence_chain_index: list[dict[str, Any]] | None = None,
    evidence_topup_round: int = 0,
    report_evidence_resume_phase: str = "",
) -> dict[str, Any]:
    """
    Resume workflow from report_evidence phase (Phase 1.5) with preserved state.

    This function is used when Phase 1.5 tool loop returns tool results and needs
    to continue from report_evidence_node without re-running Phase 0/1.

    Args:
        context: The extracted context from the Cursor request (with tool results)
        evidence_bundle: Preserved evidence bundle from Phase 0
        evidence_gaps: Preserved evidence gaps from Phase 0
        evidence_requests: Council member evidence requests from Phase 1
        ternion_analyses: Council analyses from Phase 1
        evidence_chain_index: Preserved evidence request satisfaction index
        evidence_topup_round: Number of top-up rounds already used
        report_evidence_resume_phase: Target phase after report_evidence

    Returns:
        Final state with generated output
    """
    logger.info(
        "report_evidence_resume_starting",
        has_system_prompt=context.cursor_system_prompt is not None,
        history_length=len(context.conversation_history),
        has_evidence_requests=bool(evidence_requests),
    )

    # Build state for resuming from report_evidence phase
    resume_state: TernionState = {
        "cursor_system_prompt": (
            context.cursor_system_prompt.content
            if context.cursor_system_prompt
            and isinstance(context.cursor_system_prompt.content, str)
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
            if msg.role != MessageRole.SYSTEM
            and (
                msg.content is not None
                or msg.tool_calls is not None
                or msg.tool_call_id is not None
            )
        ],
        "has_images": context.has_images,
        "workspace_root": getattr(context, "workspace_root", ""),
        "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
        # Session management (Human-in-the-Loop)
        "session_id": getattr(context, "session_id", ""),
        "await_confirmation": getattr(context, "await_confirmation", True),
        "execution_mode": getattr(context, "execution_mode", ""),
        "rejection_context": getattr(context, "rejection_context", ""),
        # Streaming event queue (for real-time output)
        "_stream_queue": getattr(context, "_stream_queue", None),
        # Cursor tool calling (Agent mode)
        "cursor_tools": getattr(context, "cursor_tools", None),
        "cursor_tool_choice": getattr(context, "cursor_tool_choice", None),
        # Preserved Phase 0/1 state (critical for P0-1 fix)
        "evidence_bundle": evidence_bundle,
        "evidence_gaps": evidence_gaps,
        "evidence_requests": evidence_requests,
        "evidence_chain_index": list(evidence_chain_index or []),
        "evidence_topup_round": int(evidence_topup_round or 0),
        "report_evidence_resume_phase": str(report_evidence_resume_phase or ""),
        "ternion_analyses": ternion_analyses,
        # Workflow outputs (initialized)
        "is_consensus": False,
        "ternion_report": "",
        "generated_code": "",
        "baseline_file_snapshots": {},
        "modified_files": [],
        "writer_output_files": {},
        "optimizer_review_report": "",
        "stabilized_document_paths": [],
        "review_feedback": "",
        "revision_count": 0,
        "errors": [],
        "thinking_logs": [],
        "final_output": "",
        "final_output_suffix": "",
    }

    # Run workflow starting from report_evidence node
    workflow = get_report_evidence_workflow()
    final_state = await workflow.ainvoke(
        resume_state,
        config={"recursion_limit": 100},
    )

    logger.info(
        "report_evidence_resume_complete",
        phase=final_state.get("current_phase"),
        has_output=bool(final_state.get("final_output") or final_state.get("generated_code")),
        error_count=len(final_state.get("errors", [])),
    )

    return final_state

"""
State definitions for the Ternion LangGraph workflow.

Defines the TypedDict state that flows through the discussion graph.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, TypedDict


class WorkflowPhase(str, Enum):
    """Current phase of the workflow."""

    EVIDENCE = "evidence"
    DIVERGENCE = "divergence"
    REPORT_EVIDENCE = "report_evidence"  # Phase 1.5: collect evidence for council requests
    CONVERGENCE = "convergence"
    EXECUTION = "execution"
    OPTIMIZER = "optimizer"
    COMPLETE = "complete"


@dataclass
class CouncilAnalysis:
    """Analysis report from a council member.

    Attributes:
        council_id: Identifier ("council_1", "council_2", "council_3").
        provider: Actual provider name (internal only).
        analysis: The analysis content.
        error: Error message if analysis failed.
    """

    council_id: str
    provider: str
    analysis: str
    error: str | None = None


@dataclass
class DiscussionResult:
    """Final result of the Ternion discussion.

    Attributes:
        final_code: Generated code block.
        analysis_report: The consensus analysis report.
        review_passed: True if the review passed.
        revision_count: Number of revisions applied.
        providers_used: List of AI providers used.
        error: Error message if discussion failed.
    """

    final_code: str
    analysis_report: str
    review_passed: bool
    revision_count: int
    providers_used: list[str]
    error: str | None = None


class TernionState(TypedDict, total=False):
    """
    State that flows through the LangGraph workflow.

    This TypedDict defines all the data that persists across
    workflow nodes during a Ternion discussion.

    Attributes:
        cursor_system_prompt: Optional Cursor system prompt.
        conversation_history: List of conversation messages.
        has_images: Whether conversation has image content.
        cursor_tools: List of tool specifications.
        cursor_tool_choice: Force use of specific tool.
        workspace_root: Absolute path to workspace root.
        current_phase: The active workflow phase.
        evidence_bundle: Raw evidence bundle.
        evidence_gaps: Identified gaps in evidence.
        session_id: Unique session identifier.
        await_confirmation: If True, stop after convergence for user confirmation.
        execution_mode: Mode string ("ternion_full" or "cursor_handoff").
        rejection_context: User's rejection feedback for re-analysis.
        ternion_analyses: List of analysis results as dicts.
        evidence_requests: Evidence requested by council members for Phase 1.5.
        evidence_chain_index: Index of evidence chain items.
        evidence_topup_round: Number of Step E evidence top-ups.
        report_evidence_resume_phase: Target phase after Phase 1.5 top-up.
        is_consensus: True if council achieved consensus.
        ternion_report: Final synthesized report.
        generated_code: Generated implementation code.
        pending_tool_calls: Tool calls awaiting execution.
        review_feedback: Feedback from the execution review.
        revision_count: Number of revisions applied.
        baseline_file_snapshots: Snapshots of files before modification.
        modified_files: List of files modified in the workflow.
        writer_output_files: Written code snippets from the Writer.
        optimizer_review_report: Review report produced by Optimizer.
        stabilized_document_paths: List of stable document paths.
        errors: Error messages encountered.
        runtime_error_payload: Structured error data.
        thinking_logs: Cursor-compatible thinking stream logs.
        final_output: Final message sent to user.
        final_output_suffix: Suffix appended to final_output.
        _stream_queue: Internal queue for streaming outputs.
    """

    cursor_system_prompt: str | None
    conversation_history: list[dict[str, Any]]
    has_images: bool
    cursor_tools: list[dict[str, Any]] | None
    cursor_tool_choice: Any | None
    workspace_root: str

    current_phase: str

    evidence_bundle: str
    evidence_gaps: str

    session_id: str
    await_confirmation: bool
    execution_mode: str
    rejection_context: str

    ternion_analyses: list[dict[str, Any]]
    evidence_requests: str
    evidence_chain_index: list[dict[str, Any]]
    evidence_topup_round: int
    report_evidence_resume_phase: str

    is_consensus: bool
    ternion_report: str

    generated_code: str
    pending_tool_calls: list[dict[str, Any]]

    review_feedback: str
    revision_count: int

    baseline_file_snapshots: dict[str, str]
    modified_files: list[str]
    writer_output_files: dict[str, str]
    optimizer_review_report: str
    stabilized_document_paths: list[str]

    errors: list[str]
    runtime_error_payload: dict[str, Any]

    thinking_logs: list[str]

    final_output: str
    final_output_suffix: str

    _stream_queue: Any

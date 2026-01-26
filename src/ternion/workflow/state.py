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
    FINAL_CHECK = "final_check"
    OPTIMIZER = "optimizer"
    COMPLETE = "complete"


class ReviewResult(str, Enum):
    """Result from the reviewer."""

    APPROVED = "approved"
    REVISION_NEEDED = "revision_needed"


@dataclass
class CouncilAnalysis:
    """Analysis report from a council member."""

    council_id: str  # "council_1", "council_2", "council_3"
    provider: str  # Actual provider name (internal only)
    analysis: str  # The analysis content
    error: str | None = None  # Error message if analysis failed


@dataclass
class DiscussionResult:
    """Final result of the Ternion discussion."""

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
    """

    # Input context
    cursor_system_prompt: str | None
    conversation_history: list[dict[str, Any]]
    has_images: bool
    cursor_tools: list[dict[str, Any]] | None
    cursor_tool_choice: Any | None

    # Current phase
    current_phase: str

    # Evidence gathering outputs
    evidence_bundle: str
    evidence_gaps: str

    # Session management (Human-in-the-Loop)
    session_id: str  # Unique session identifier
    await_confirmation: bool  # If True, stop after convergence for user confirmation
    execution_mode: str  # "ternion_full" or "cursor_handoff"
    rejection_context: str  # User's rejection feedback for re-analysis

    # Step 1: Divergence outputs
    ternion_analyses: list[dict[str, Any]]  # List of analysis results as dicts
    evidence_requests: str  # Evidence requested by council members for Phase 1.5
    evidence_chain_index: list[dict[str, Any]]
    # Step E: Execution/Optimizer evidence top-up (shared counter across phases)
    evidence_topup_round: int
    # Step E: When using report_evidence as execution-time top-up, resume to this phase.
    report_evidence_resume_phase: str

    # Step 2: Convergence outputs
    is_consensus: bool
    ternion_report: str

    # Step 3: Execution outputs
    generated_code: str
    pending_tool_calls: list[dict[str, Any]]

    # Step 4: Final Check outputs (legacy; may be bypassed in dev override)
    review_result: str  # "approved" or "revision_needed"
    review_feedback: str
    revision_count: int

    # Step 4 (Dev Override): Optimizer inputs/outputs
    baseline_file_snapshots: dict[str, str]
    modified_files: list[str]
    writer_output_files: dict[str, str]
    optimizer_review_report: str

    # Error tracking
    errors: list[str]

    # Thinking stream logs (Cursor-compatible markdown)
    thinking_logs: list[str]

    # Final result
    final_output: str
    final_output_suffix: str

    # Streaming event queue (internal, for real-time output forwarding)
    # This is set by routes.py and consumed by nodes for streaming LLM output
    # Using Any to avoid LangGraph type resolution issues with forward references
    _stream_queue: Any

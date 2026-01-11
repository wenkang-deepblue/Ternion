"""
State definitions for the Ternion LangGraph workflow.

Defines the TypedDict state that flows through the discussion graph.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, TypedDict


class WorkflowPhase(str, Enum):
    """Current phase of the workflow."""

    DIVERGENCE = "divergence"
    CONVERGENCE = "convergence"
    EXECUTION = "execution"
    FINAL_CHECK = "final_check"
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

    # Current phase
    current_phase: str

    # Session management (Human-in-the-Loop)
    session_id: str  # Unique session identifier
    await_confirmation: bool  # If True, stop after convergence for user confirmation
    execution_mode: str  # "ternion_full" or "cursor_handoff"
    rejection_context: str  # User's rejection feedback for re-analysis

    # Step 1: Divergence outputs
    ternion_analyses: list[dict[str, Any]]  # List of analysis results as dicts

    # Step 2: Convergence outputs
    is_consensus: bool
    ternion_report: str

    # Step 3: Execution outputs
    generated_code: str

    # Step 4: Final Check outputs
    review_result: str  # "approved" or "revision_needed"
    review_feedback: str
    revision_count: int

    # Error tracking
    errors: list[str]

    # Thinking stream logs (Cursor-compatible markdown)
    thinking_logs: list[str]

    # Final result
    final_output: str

    # Streaming event queue (internal, for real-time output forwarding)
    # This is set by routes.py and consumed by nodes for streaming LLM output
    # Using Any to avoid LangGraph type resolution issues with forward references
    _stream_queue: Any

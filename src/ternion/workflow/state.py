"""
State definitions for the Ternion LangGraph workflow.

Defines the TypedDict state that flows through the discussion graph.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
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

    # Step 1: Divergence outputs
    council_analyses: list[dict[str, Any]]  # List of CouncilAnalysis as dicts

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

    # Final result
    final_output: str

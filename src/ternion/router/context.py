"""
Context dataclass for Ternion workflow.

Holds the decomposed message context extracted by MessageRouter.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from ternion.core.models import ChatMessage


class DiscussionPhase(Enum):
    """Current phase of the discussion workflow."""

    DIVERGENCE = auto()  # Parallel root cause analysis
    CONVERGENCE = auto()  # Arbiter synthesis
    EXECUTION = auto()  # Writer generates code
    FINAL_CHECK = auto()  # Reviewer verification


@dataclass
class TernionContext:
    """
    Holds the decomposed context from a Cursor request.

    This is the critical data structure that enables the Message Router
    to properly inject phase-specific prompts while preserving the
    original Cursor system prompt for final output formatting.
    """

    # The original Cursor system prompt (e.g., "Output in DIFF format...")
    # Stored for restoration during the EXECUTION phase
    cursor_system_prompt: ChatMessage | None = None

    # Conversation history (user messages, assistant responses, etc.)
    # This excludes the system prompt
    conversation_history: list[ChatMessage] = field(default_factory=list)

    # Extracted metadata (optional, for future use)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Flag indicating if multimodal content is present
    has_images: bool = False

    # Session management (Human-in-the-Loop)
    session_id: str = ""  # Existing session ID for follow-up requests
    await_confirmation: bool = True  # If True, stop after convergence for confirmation
    # Execution mode is intentionally empty by default. Must be explicitly configured in Web UI.
    execution_mode: str = ""  # "ternion_full" | "cursor_handoff" | ""
    rejection_context: str = ""  # User's rejection feedback for re-analysis

    @property
    def is_empty(self) -> bool:
        """Check if context has no meaningful content."""
        return not self.cursor_system_prompt and not self.conversation_history

    @property
    def total_messages(self) -> int:
        """Total number of messages including system prompt."""
        count = len(self.conversation_history)
        if self.cursor_system_prompt:
            count += 1
        return count

    def get_user_messages(self) -> list[ChatMessage]:
        """Get only user messages from history."""
        return [m for m in self.conversation_history if m.role.value == "user"]

    def get_last_user_message(self) -> ChatMessage | None:
        """Get the most recent user message."""
        user_messages = self.get_user_messages()
        return user_messages[-1] if user_messages else None

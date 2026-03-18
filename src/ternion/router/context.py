"""
Context dataclass for Ternion workflow.

Holds the decomposed message context extracted by MessageRouter.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Literal

from ternion.core.models import ChatMessage

if TYPE_CHECKING:
    from ternion.workflow.streaming_events import StreamEventQueue


class DiscussionPhase(Enum):
    """Current phase of the discussion workflow."""

    DIVERGENCE = auto()  # Phase 1: Independent root cause analysis (3 council members)
    CONVERGENCE = auto()  # Phase 2: Arbiter synthesizes analyses into a plan
    EXECUTION = auto()  # Phase 3: Writer generates the implementation
    FINAL_CHECK = auto()  # Phase 4: Optimizer applies targeted improvements (Reviewer path inactive)


ExecutionMode = Literal["ternion_full", "cursor_handoff", ""]


@dataclass
class TernionContext:
    """
    Holds the decomposed context from a Cursor request.

    This is the critical data structure that enables the Message Router
    to properly inject phase-specific prompts while preserving the
    original Cursor system prompt for final output formatting.
    """

    # The original Cursor system prompt (e.g., "Output in DIFF format...").
    # Stored here for injection into the message list during the EXECUTION phase
    # by the workflow layer (see workflow/nodes.py).
    cursor_system_prompt: ChatMessage | None = None

    # Conversation history (user messages, assistant responses, etc.)
    # This excludes the system prompt
    conversation_history: list[ChatMessage] = field(default_factory=list)

    # Reserved for request-level metadata (e.g., client_version, request_id).
    # Populated by the API handler layer.
    metadata: dict[str, Any] = field(default_factory=dict)

    # Flag indicating if multimodal content is present
    has_images: bool = False

    # Cursor tool calling (Agent mode)
    cursor_tools: list[dict[str, Any]] = field(default_factory=list)
    cursor_tool_choice: Any | None = None

    # Session management (Human-in-the-Loop)
    # Populated by the API handler from the request payload.
    # Empty string indicates a new session (no prior context).
    session_id: str = ""
    # If True, workflow pauses after CONVERGENCE and returns to caller for user confirmation.
    # Set to False for fully automated (non-interactive) runs.
    await_confirmation: bool = True
    # Execution mode is intentionally empty by default. Must be explicitly configured in Web UI.
    execution_mode: ExecutionMode = ""
    # Client-declared workspace root for the current Cursor conversation.
    # Empty string means the API layer could not determine a request-scoped workspace.
    workspace_root: str = ""
    # Best-effort local workspace path that is readable on the server host.
    local_workspace_root: str = ""
    # Path style used for client-declared path normalization ("posix" or "windows").
    workspace_path_style: str = ""
    # Source used to derive the client workspace root.
    workspace_root_source: str = ""
    # Populated when the user rejects the convergence report.
    # Contains the user's free-text feedback for the re-analysis cycle.
    rejection_context: str = ""

    # Injected post-construction by the streaming layer; not part of the public interface.
    _stream_queue: "StreamEventQueue | None" = field(default=None, init=False, repr=False)

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
        """Get only user messages from history.

        Returns:
            List of messages whose role is ``user``.
        """
        return [m for m in self.conversation_history if m.role.value == "user"]

    def get_last_user_message(self) -> ChatMessage | None:
        """Get the most recent user message.

        Returns:
            The most recent user message if present. Otherwise, ``None``.
        """
        user_messages = self.get_user_messages()
        return user_messages[-1] if user_messages else None

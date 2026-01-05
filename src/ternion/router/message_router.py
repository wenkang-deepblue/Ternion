"""
Message Router - The Critical Layer.

Handles message decomposition and reconstruction for the Ternion workflow.
This is NOT blind pass-through - we must decompose the Cursor request,
swap prompts per discussion phase, and restore the original prompt
for the final output to ensure format compatibility.
"""


import structlog

from ternion.core.models import (
    ChatMessage,
    ImageContent,
    MessageContent,
    MessageRole,
)
from ternion.router.context import DiscussionPhase, TernionContext
from ternion.router.prompts import PHASE_PROMPTS

logger = structlog.get_logger(__name__)


class MessageRouter:
    """
    Routes and transforms messages for different discussion phases.

    Key responsibilities:
    1. Extract and store Cursor's system prompt
    2. Extract conversation history
    3. Build phase-specific message lists with Ternion prompts
    4. Restore Cursor prompt for final output format compliance
    """

    def __init__(self) -> None:
        """Initialize the message router."""
        self._current_context: TernionContext | None = None

    @property
    def context(self) -> TernionContext | None:
        """Get the current context."""
        return self._current_context

    def extract_context(self, messages: list[ChatMessage]) -> TernionContext:
        """
        Extract and decompose the incoming message list.

        This separates the Cursor system prompt from the conversation history
        and stores it for later restoration during the EXECUTION phase.

        Args:
            messages: The original message list from the Cursor request

        Returns:
            TernionContext with decomposed components
        """
        if not messages:
            logger.warning("extract_context_empty", message_count=0)
            return TernionContext()

        # Check if first message is a system prompt
        cursor_system_prompt: ChatMessage | None = None
        conversation_history: list[ChatMessage] = []
        has_images = False

        for i, msg in enumerate(messages):
            # First system message is the Cursor system prompt
            if i == 0 and msg.role == MessageRole.SYSTEM:
                cursor_system_prompt = msg
                logger.debug(
                    "cursor_prompt_extracted",
                    content_preview=self._get_content_preview(msg.content),
                )
            else:
                conversation_history.append(msg)

                # Check for images in content
                if self._contains_images(msg.content):
                    has_images = True

        context = TernionContext(
            cursor_system_prompt=cursor_system_prompt,
            conversation_history=conversation_history,
            has_images=has_images,
        )

        self._current_context = context

        logger.info(
            "context_extracted",
            has_system_prompt=cursor_system_prompt is not None,
            history_length=len(conversation_history),
            has_images=has_images,
        )

        return context

    def build_phase_messages(
        self,
        phase: DiscussionPhase,
        context: TernionContext | None = None,
        additional_context: str | None = None,
    ) -> list[ChatMessage]:
        """
        Build messages for a specific discussion phase.

        For DIVERGENCE phase: Replace system prompt with analysis-focused prompt
        For EXECUTION phase: Restore Cursor's system prompt for output format

        Args:
            phase: The current discussion phase
            context: Optional context (uses stored context if not provided)
            additional_context: Additional context to inject (e.g., analysis report)

        Returns:
            List of messages configured for the specified phase
        """
        ctx = context or self._current_context
        if not ctx:
            raise ValueError("No context available. Call extract_context first.")

        messages: list[ChatMessage] = []

        # Get the appropriate system prompt for this phase
        if phase == DiscussionPhase.EXECUTION and ctx.cursor_system_prompt:
            # Restore Cursor's system prompt for proper output formatting
            messages.append(ctx.cursor_system_prompt)
            logger.debug("restored_cursor_prompt", phase=phase.name)
        else:
            # Use Ternion's phase-specific prompt
            phase_prompt = PHASE_PROMPTS.get(phase, PHASE_PROMPTS[DiscussionPhase.DIVERGENCE])
            messages.append(
                ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=phase_prompt,
                )
            )
            logger.debug("injected_ternion_prompt", phase=phase.name)

        # Add conversation history
        messages.extend(ctx.conversation_history)

        # Add additional context if provided (e.g., Ternion Analysis Report)
        if additional_context:
            messages.append(
                ChatMessage(
                    role=MessageRole.USER,
                    content=f"[Ternion Analysis Report]\n{additional_context}",
                )
            )

        return messages

    def build_council_messages(
        self,
        context: TernionContext | None = None,
    ) -> list[ChatMessage]:
        """
        Build messages for the Council members during DIVERGENCE phase.

        This replaces Cursor's system prompt with the RCA (Root Cause Analysis)
        prompt that instructs models to analyze, not write code.

        Args:
            context: Optional context (uses stored context if not provided)

        Returns:
            Messages configured for council analysis
        """
        return self.build_phase_messages(DiscussionPhase.DIVERGENCE, context)

    def build_writer_messages(
        self,
        analysis_report: str,
        context: TernionContext | None = None,
    ) -> list[ChatMessage]:
        """
        Build messages for the Writer during EXECUTION phase.

        This restores Cursor's system prompt to ensure the output
        matches the expected format (e.g., DIFF format).

        Args:
            analysis_report: The synthesized Ternion Analysis Report
            context: Optional context (uses stored context if not provided)

        Returns:
            Messages configured for code generation
        """
        return self.build_phase_messages(
            DiscussionPhase.EXECUTION,
            context,
            additional_context=analysis_report,
        )

    def _contains_images(self, content: MessageContent | None) -> bool:
        """Check if message content contains images."""
        if content is None:
            return False
        if isinstance(content, str):
            return False
        if isinstance(content, list):
            return any(isinstance(item, ImageContent) for item in content)
        return False

    def _get_content_preview(self, content: MessageContent | None, max_length: int = 50) -> str:
        """Get a preview of message content for logging."""
        if content is None:
            return "<empty>"
        if isinstance(content, str):
            return content[:max_length] + "..." if len(content) > max_length else content
        if isinstance(content, list):
            return f"<multipart: {len(content)} items>"
        return "<unknown>"

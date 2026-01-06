"""
Message Router - Context Extraction Layer.

Handles message decomposition from the Cursor request.
Extracts system prompt and conversation history for use by workflow nodes.

Note: Message assembly (phase-specific prompt injection) is handled by
workflow/nodes.py, which is the authoritative implementation.
"""


import structlog

from ternion.core.models import (
    ChatMessage,
    ImageContent,
    MessageContent,
    MessageRole,
)
from ternion.router.context import TernionContext

logger = structlog.get_logger(__name__)


class MessageRouter:
    """
    Routes and transforms messages for the Ternion workflow.

    Key responsibilities:
    1. Extract and store Cursor's system prompt
    2. Extract conversation history
    3. Detect multimodal content (images)

    Note: Phase-specific message assembly is handled by workflow nodes.
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

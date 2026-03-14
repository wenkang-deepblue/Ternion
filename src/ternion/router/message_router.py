"""
Message Router - Context Extraction Layer.

Handles message decomposition from the Cursor request.
Extracts system prompt and conversation history for use by workflow nodes.

Note: Phase-specific message assembly (prompt injection) is out of scope
for this module; see the workflow layer.
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
    """

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

        cursor_system_prompt: ChatMessage | None = None
        conversation_history: list[ChatMessage] = []
        has_images = False

        for i, msg in enumerate(messages):
            # Position-0 system message is assumed to be the Cursor system prompt.
            # Any SYSTEM message at position > 0 will be treated as conversation history.
            if i == 0 and msg.role == MessageRole.SYSTEM:
                cursor_system_prompt = msg
                logger.debug(
                    "cursor_prompt_extracted",
                    content_preview=self._get_content_preview(msg.content),
                )
            else:
                conversation_history.append(msg)

                if self._contains_images(msg.content):
                    has_images = True

        context = TernionContext(
            cursor_system_prompt=cursor_system_prompt,
            conversation_history=conversation_history,
            has_images=has_images,
        )

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
        # Fallback for unrecognized content types. Returns False (no images assumed).
        # To support a new content type, add an explicit branch above (before this fallback).
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

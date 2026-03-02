"""
Tests for the Message Router module.
"""

from ternion.core.models import ChatMessage, MessageRole
from ternion.router.context import TernionContext
from ternion.router.message_router import MessageRouter


class TestTernionContext:
    """Tests for TernionContext dataclass."""

    def test_empty_context(self) -> None:
        """Test empty context properties."""
        ctx = TernionContext()
        assert ctx.is_empty
        assert ctx.total_messages == 0
        assert ctx.get_last_user_message() is None

    def test_context_with_messages(self, sample_messages: list[ChatMessage]) -> None:
        """Test context with messages."""
        ctx = TernionContext(
            cursor_system_prompt=sample_messages[0],
            conversation_history=sample_messages[1:],
        )
        assert not ctx.is_empty
        assert ctx.total_messages == 3
        assert ctx.get_last_user_message() is not None


class TestMessageRouter:
    """Tests for MessageRouter class."""

    def test_extract_context_basic(self, sample_messages: list[ChatMessage]) -> None:
        """Test basic context extraction."""
        router = MessageRouter()
        context = router.extract_context(sample_messages)

        assert context.cursor_system_prompt is not None
        assert context.cursor_system_prompt.role == MessageRole.SYSTEM
        assert len(context.conversation_history) == 2
        assert not context.has_images

    def test_extract_context_no_system_prompt(
        self, messages_without_system: list[ChatMessage]
    ) -> None:
        """Test extraction when no system prompt is present."""
        router = MessageRouter()
        context = router.extract_context(messages_without_system)

        # First message is a user message, not system
        assert context.cursor_system_prompt is None
        assert len(context.conversation_history) == 1

    def test_extract_context_empty(self, empty_messages: list[ChatMessage]) -> None:
        """Test extraction with empty messages."""
        router = MessageRouter()
        context = router.extract_context(empty_messages)

        assert context.is_empty

    def test_context_property(self, sample_messages: list[ChatMessage]) -> None:
        """Test that context property returns stored context."""
        router = MessageRouter()
        assert router.context is None

        context = router.extract_context(sample_messages)
        assert router.context is context
        assert router.context.cursor_system_prompt is not None

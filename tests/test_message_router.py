"""
Tests for the Message Router module.
"""

import pytest

from ternion.core.models import ChatMessage, MessageRole
from ternion.router.context import DiscussionPhase, TernionContext
from ternion.router.message_router import MessageRouter
from ternion.router.prompts import DIVERGENCE_PROMPT


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

    def test_build_council_messages(self, sample_messages: list[ChatMessage]) -> None:
        """Test building messages for council (DIVERGENCE phase)."""
        router = MessageRouter()
        router.extract_context(sample_messages)

        council_messages = router.build_council_messages()

        # Should have Ternion prompt, not Cursor prompt
        assert len(council_messages) == 3  # 1 system + 2 history
        assert council_messages[0].role == MessageRole.SYSTEM
        assert council_messages[0].content == DIVERGENCE_PROMPT

    def test_build_writer_messages(self, sample_messages: list[ChatMessage]) -> None:
        """Test building messages for writer (EXECUTION phase)."""
        router = MessageRouter()
        router.extract_context(sample_messages)

        writer_messages = router.build_writer_messages(
            analysis_report="The bug is in the return statement."
        )

        # Should restore Cursor's system prompt
        assert writer_messages[0].role == MessageRole.SYSTEM
        assert "DIFF format" in str(writer_messages[0].content)
        # Should include analysis report
        assert any(
            "[Ternion Analysis Report]" in str(m.content)
            for m in writer_messages
        )

    def test_build_phase_messages_without_context(self) -> None:
        """Test building messages without extracting context first."""
        router = MessageRouter()

        with pytest.raises(ValueError, match="No context available"):
            router.build_phase_messages(DiscussionPhase.DIVERGENCE)

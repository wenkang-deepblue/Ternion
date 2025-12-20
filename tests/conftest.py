"""
Test configuration and fixtures.
"""

import pytest
from typing import Any

from ternion.core.models import ChatMessage, MessageRole


@pytest.fixture
def sample_messages() -> list[ChatMessage]:
    """Sample chat messages for testing."""
    return [
        ChatMessage(
            role=MessageRole.SYSTEM,
            content="You are a helpful assistant. Output code in DIFF format.",
        ),
        ChatMessage(
            role=MessageRole.USER,
            content="Previous context about the codebase...",
        ),
        ChatMessage(
            role=MessageRole.USER,
            content="Please fix this bug in my Python code:\n```python\ndef foo():\n    return None\n```",
        ),
    ]


@pytest.fixture
def messages_without_system() -> list[ChatMessage]:
    """Messages without a system prompt."""
    return [
        ChatMessage(
            role=MessageRole.USER,
            content="Hello, can you help me?",
        ),
    ]


@pytest.fixture
def empty_messages() -> list[ChatMessage]:
    """Empty message list."""
    return []

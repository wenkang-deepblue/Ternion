"""
Tests for tool calls retry mechanics.
"""

from __future__ import annotations
from collections.abc import AsyncIterator

import pytest

from ternion.core.models import ChatMessage, MessageRole
from ternion.providers.base import ProviderResponse
from ternion.workflow.nodes import _call_with_stream
from ternion.workflow.streaming_events import StreamEventQueue


class _FakeStreamingProvider:
    name = "anthropic"

    def __init__(self) -> None:
        self.stream_calls = 0
        self.chat_calls = 0

    async def chat_completion(
        self,
        *,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        **kwargs: object,
    ) -> ProviderResponse:
        self.chat_calls += 1
        return ProviderResponse(
            content="",
            finish_reason="tool_calls",
            tool_calls=[
                {
                    "id": "retry_call_01",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"target_file":"/abs/path"}'},
                }
            ],
            usage={},
        )

    def chat_completion_stream(
        self,
        *,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        **kwargs: object,
    ) -> AsyncIterator[str]:
        self.stream_calls += 1

        async def gen() -> AsyncIterator[str]:
            # Exceed the guard buffer to force at least one streamed token delta.
            yield "A" * 300
            yield (
                "TERNION_TOOL_CALLS_BEGIN\n"
                '{"tool_calls":[{"name":"grep","arguments":{"pattern":"x","path":"/"}}]}\n'
                "TERNION_TOOL_CALLS_END"
            )

        return gen()


@pytest.mark.asyncio
async def test_call_with_stream_mixed_output_triggers_tool_calls_retry() -> None:
    provider = _FakeStreamingProvider()
    stream_queue = StreamEventQueue()
    messages = [ChatMessage(role=MessageRole.USER, content="test")]

    response = await _call_with_stream(
        provider=provider,
        messages=messages,
        model="test-model",
        temperature=0.3,
        stream_queue=stream_queue,
        phase="execution",
        message_id="sess",
        timeout_seconds=5,
        detect_tool_calls=True,
        tool_calls_guard_chars=256,
        tool_calls_auto_retry_max=1,
    )

    assert provider.stream_calls == 1
    assert provider.chat_calls == 1
    assert response.finish_reason == "tool_calls"
    assert response.tool_calls is not None
    assert response.tool_calls[0].get("id") == "retry_call_01"

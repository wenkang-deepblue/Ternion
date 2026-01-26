import asyncio

import pytest

from ternion.workflow.nodes import _call_with_stream
from ternion.workflow.streaming_events import StreamEventQueue, StreamEventType


class _DummyStreamingProvider:
    def __init__(self, chunks: list[str]) -> None:
        self.name = "openai"
        self._chunks = list(chunks)

    async def chat_completion_stream(  # type: ignore[no-untyped-def]
        self,
        *,
        messages,
        model=None,
        temperature=0.7,
        **kwargs,
    ):
        for c in self._chunks:
            yield c


@pytest.mark.asyncio
async def test_call_with_stream_suppresses_evidence_topup_block_in_execution_phase() -> None:
    """
    Short-window buffering should prevent streaming an evidence top-up protocol block
    as token deltas (it is validated later by Step E guardrails and may be soft-retried).
    """
    provider = _DummyStreamingProvider(
        [
            " \n\nTERNION_EVIDENCE_REQUESTS_",
            "BEGIN\nREQUESTER: execution\n",
            "FINAL_REQUEST: false\n- [P0] path=src/app.py:1-2\n",
            "PURPOSE: Verify initialization.\nTERNION_EVIDENCE_REQUESTS_END\n",
        ]
    )
    queue = StreamEventQueue()

    resp = await _call_with_stream(
        provider=provider,
        messages=[],
        model="gpt-4",
        temperature=0.0,
        stream_queue=queue,
        phase="execution",
        message_id="test",
    )
    assert resp.content.lstrip().startswith("TERNION_EVIDENCE_REQUESTS_BEGIN")

    events = []
    while True:
        event = await asyncio.wait_for(queue.get(), timeout=1)
        assert event is not None
        events.append(event)
        if event.event_type == StreamEventType.FINAL_UPDATE:
            break

    token_events = [e for e in events if e.event_type == StreamEventType.TOKEN_DELTA]
    assert token_events == []


@pytest.mark.asyncio
async def test_call_with_stream_still_streams_normal_content_after_short_probe() -> None:
    provider = _DummyStreamingProvider(["Hello", " ", "world!"])
    queue = StreamEventQueue()

    resp = await _call_with_stream(
        provider=provider,
        messages=[],
        model="gpt-4",
        temperature=0.0,
        stream_queue=queue,
        phase="execution",
        message_id="test",
    )
    assert resp.content == "Hello world!"

    events = []
    while True:
        event = await asyncio.wait_for(queue.get(), timeout=1)
        assert event is not None
        events.append(event)
        if event.event_type == StreamEventType.FINAL_UPDATE:
            break

    token_events = [e for e in events if e.event_type == StreamEventType.TOKEN_DELTA]
    assert "".join(e.delta for e in token_events) == "Hello world!"


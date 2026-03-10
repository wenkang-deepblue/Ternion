import asyncio
from unittest.mock import MagicMock, patch

import pytest

from ternion.workflow.nodes import _call_optimizer_with_stream
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
async def test_call_optimizer_with_stream_suppresses_evidence_topup_block() -> None:
    mock_cfg = MagicMock()
    mock_cfg.language = "zh"
    mock_cfg.browser_language = "zh"

    with patch("ternion.utils.i18n._load_user_config") as mock_store:
        mock_store.return_value = mock_cfg

        provider = _DummyStreamingProvider(
            [
                " \n\nTERNION_EVIDENCE_REQUESTS_",
                "BEGIN\nREQUESTER: optimizer\n",
                "FINAL_REQUEST: false\n- [P0] path=src/app.py:1-2\n",
                "PURPOSE: Verify initialization.\nTERNION_EVIDENCE_REQUESTS_END\n",
            ]
        )
        queue = StreamEventQueue()

        resp, _streamed = await _call_optimizer_with_stream(
            provider=provider,
            messages=[],
            model="gpt-4",
            temperature=0.0,
            stream_queue=queue,
            phase="optimizer",
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
        assert len(token_events) == 1
        assert token_events[0].delta == "> **[Optimizer]**: 仍在生成交付内容...\n"
        assert "TERNION_EVIDENCE_REQUESTS_BEGIN" not in token_events[0].delta
        assert "TERNION_EVIDENCE_REQUESTS_END" not in token_events[0].delta
        assert "path=" not in token_events[0].delta
        assert "PURPOSE:" not in token_events[0].delta

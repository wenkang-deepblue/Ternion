from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.core.config_store import RoleConfig
from ternion.core.exceptions import RuntimeModelUnavailableError
from ternion.workflow.nodes import (
    _call_with_stream,
    _call_with_timeout,
    convergence_node,
)
from ternion.workflow.state import WorkflowPhase
from ternion.workflow.streaming_events import StreamEventQueue, StreamEventType


@pytest.mark.asyncio
async def test_call_with_timeout_reraises_runtime_model_unavailable() -> None:
    """Timeout wrapper should convert stale-model provider errors into structured exceptions."""
    provider = MagicMock()
    provider.name = "openai"
    provider.chat_completion = AsyncMock(side_effect=Exception("The requested model does not exist"))

    with pytest.raises(RuntimeModelUnavailableError) as exc_info:
        await _call_with_timeout(
            provider=provider,
            messages=[],
            model="gpt-5.4",
            temperature=0.2,
        )

    assert exc_info.value.provider == "openai"
    assert exc_info.value.model == "gpt-5.4"
    assert isinstance(exc_info.value.__cause__, Exception)


@pytest.mark.asyncio
async def test_call_with_stream_emits_structured_runtime_model_error() -> None:
    """Streaming wrapper should enqueue structured stale-model metadata before raising."""
    provider = MagicMock()
    provider.name = "openai"

    async def failing_stream():  # type: ignore[no-untyped-def]
        raise Exception("The requested model does not exist")
        yield ""

    provider.chat_completion_stream = MagicMock(return_value=failing_stream())
    stream_queue = StreamEventQueue()

    with pytest.raises(RuntimeModelUnavailableError):
        await _call_with_stream(
            provider=provider,
            messages=[],
            model="gpt-5.4",
            temperature=0.2,
            stream_queue=stream_queue,
            phase="convergence",
            message_id="msg-1",
        )

    stream_queue.close()
    events = [event async for event in stream_queue]
    error_events = [event for event in events if event.event_type == StreamEventType.ERROR]

    assert error_events
    assert error_events[0].metadata["code"] == "MODEL_UNAVAILABLE"
    assert error_events[0].metadata["provider"] == "openai"
    assert error_events[0].metadata["model"] == "gpt-5.4"
    assert error_events[0].metadata["refresh_suggested"] is True


@pytest.mark.asyncio
async def test_convergence_fallback_returns_runtime_model_unavailable_state() -> None:
    """Convergence fallback should preserve structured stale-model guidance."""
    mock_user_config = MagicMock()
    mock_user_config.language = "en"
    mock_user_config.browser_language = "en"
    mock_user_config.execution_mode = "cursor_handoff"

    fallback_provider = MagicMock()
    fallback_provider.name = "openai"

    role_configs = {
        "arbiter": RoleConfig(provider="openai", model="gpt-5.4"),
        "ternion_a": RoleConfig(provider="openai", model="gpt-5.4"),
        "ternion_b": RoleConfig(provider="openai", model="gpt-5.4"),
    }

    state = {
        "cursor_system_prompt": "You are a helpful assistant.",
        "conversation_history": [{"role": "user", "content": "Fix my bug"}],
        "current_phase": WorkflowPhase.CONVERGENCE.value,
        "session_id": "session-123",
        "await_confirmation": True,
        "execution_mode": "cursor_handoff",
        "ternion_analyses": [
            {"ternion_id": "ternion_a", "analysis": "Root cause A", "error": None},
            {"ternion_id": "ternion_b", "analysis": "Root cause B", "error": None},
        ],
        "thinking_logs": [],
        "errors": [],
    }

    with (
        patch("ternion.workflow.nodes.config_store") as mock_config_store,
        patch("ternion.workflow.nodes.provider_manager") as mock_provider_manager,
        patch("ternion.workflow.nodes._call_with_stream", new_callable=AsyncMock) as mock_call_stream,
        patch("ternion.workflow.nodes._call_with_timeout", new_callable=AsyncMock) as mock_call_timeout,
    ):
        mock_config_store.load.return_value = mock_user_config
        mock_config_store.get_role_config.side_effect = lambda role: role_configs.get(role)
        mock_provider_manager.get_provider_for_role.return_value = fallback_provider
        mock_provider_manager.get_provider.return_value = fallback_provider
        mock_call_stream.side_effect = Exception("arbiter failed before fallback")
        mock_call_timeout.side_effect = RuntimeModelUnavailableError(
            provider="openai",
            model="gpt-5.4",
            provider_message="model not found",
        )

        result = await convergence_node(state)

    assert result["current_phase"] == WorkflowPhase.COMPLETE.value
    assert result["runtime_error_payload"]["code"] == "MODEL_UNAVAILABLE"
    assert result["runtime_error_payload"]["provider"] == "openai"
    assert result["runtime_error_payload"]["model"] == "gpt-5.4"
    assert "openai / gpt-5.4" in result["final_output"]

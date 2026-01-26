import pytest

from unittest.mock import MagicMock

from ternion.core.config_store import RoleConfig
from ternion.core.models import ChatMessage, MessageRole
from ternion.providers.base import ProviderResponse
from ternion.workflow.nodes import execution_node


class _CapturingWriterProvider:
    name = "anthropic"

    def __init__(self) -> None:
        self.last_messages: list[ChatMessage] | None = None

    async def chat_completion(
        self,
        *,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        **kwargs: object,
    ) -> ProviderResponse:
        self.last_messages = messages
        return ProviderResponse(
            content="",
            finish_reason="tool_calls",
            tool_calls=[
                {
                    "type": "function",
                    "function": {
                        "name": "write",
                        "arguments": "{\"file_path\":\"/abs/path\",\"content\":\"x\"}",
                    },
                }
            ],
            usage={},
        )

    def chat_completion_stream(self, *args: object, **kwargs: object):
        raise AssertionError("streaming not used in this test")


@pytest.mark.asyncio
async def test_execution_injects_text_tool_calls_based_on_runtime_provider_capability(
    monkeypatch,
) -> None:
    provider = _CapturingWriterProvider()

    monkeypatch.setattr(
        "ternion.workflow.nodes.provider_manager.get_provider_for_role",
        lambda _role: provider,
    )

    mock_user_config = MagicMock()
    mock_user_config.language = "en"
    mock_user_config.browser_language = "en"
    monkeypatch.setattr("ternion.workflow.nodes.config_store.load", lambda: mock_user_config)

    # Simulate user config selecting OpenAI, but runtime provider is non-OpenAI.
    monkeypatch.setattr(
        "ternion.workflow.nodes.config_store.get_role_config",
        lambda _role: RoleConfig(provider="openai", model="gpt-test"),
    )

    state = {
        "current_phase": "execution",
        "ternion_report": "REPORT",
        "conversation_history": [{"role": "user", "content": "do it"}],
        "cursor_tools": [
            {
                "type": "function",
                "function": {
                    "name": "Write",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                },
            }
        ],
        "cursor_tool_choice": "auto",
        "session_id": "sess",
    }

    out = await execution_node(state)

    assert out.get("pending_tool_calls"), "Expected execution to return pending_tool_calls"
    assert provider.last_messages is not None

    last_user = next(
        (m for m in reversed(provider.last_messages) if m.role == MessageRole.USER),
        None,
    )
    assert last_user is not None
    assert isinstance(last_user.content, str)
    assert "[NON-OPENAI TOOL CALLS]" in last_user.content
    assert "TERNION_TOOL_CALLS_BEGIN" in last_user.content


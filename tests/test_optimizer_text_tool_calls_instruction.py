import pytest

from unittest.mock import MagicMock

from ternion.core.config_store import RoleConfig
from ternion.core.models import ChatMessage, MessageRole
from ternion.core.session_store import ExecutionMode
from ternion.providers.base import ProviderResponse
from ternion.workflow.nodes import optimizer_node


class _CapturingTextToolsProvider:
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
            content=(
                "TERNION_TOOL_CALLS_BEGIN\n"
                "{\"tool_calls\":[{\"name\":\"write\",\"arguments\":{\"file_path\":\"/abs/path\",\"content\":\"x\"}}]}\n"
                "TERNION_TOOL_CALLS_END"
            ),
            finish_reason="stop",
            usage={},
        )

    def chat_completion_stream(self, *args: object, **kwargs: object):
        raise AssertionError("streaming not used in this test")


@pytest.mark.asyncio
async def test_optimizer_injects_text_tool_calls_instruction_for_non_openai_provider(
    monkeypatch,
) -> None:
    provider = _CapturingTextToolsProvider()

    def _fake_get_provider_for_role(_role: str):
        return provider

    monkeypatch.setattr("ternion.workflow.nodes.provider_manager.get_provider_for_role", _fake_get_provider_for_role)

    mock_user_config = MagicMock()
    mock_user_config.language = "en"
    mock_user_config.browser_language = "en"
    monkeypatch.setattr("ternion.workflow.nodes.config_store.load", lambda: mock_user_config)
    monkeypatch.setattr(
        "ternion.workflow.nodes.config_store.get_role_config",
        lambda _role: RoleConfig(provider="anthropic", model="claude-test"),
    )

    state = {
        "current_phase": "optimizer",
        "execution_mode": ExecutionMode.TERNION_FULL.value,
        "ternion_report": "REPORT",
        "generated_code": "WRITER_OUTPUT",
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

    out = await optimizer_node(state)

    assert out.get("pending_tool_calls"), "Expected optimizer to return pending_tool_calls"
    assert provider.last_messages is not None

    last_user = next(
        (m for m in reversed(provider.last_messages) if m.role == MessageRole.USER),
        None,
    )
    assert last_user is not None
    assert isinstance(last_user.content, str)
    assert "[NON-OPENAI TOOL CALLS]" in last_user.content
    assert "TERNION_TOOL_CALLS_BEGIN" in last_user.content


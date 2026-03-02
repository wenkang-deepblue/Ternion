from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest import MonkeyPatch

from ternion.core.config_store import RoleConfig
from ternion.core.models import ChatMessage, MessageRole
from ternion.providers.base import ProviderResponse
from ternion.workflow.nodes import optimizer_node


class _CapturingProvider:
    name = "openai"
    supports_native_tool_calls = False

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
                "TERNION_OPTIMIZER_INTERNAL_REPORT_BEGIN\n"
                "- ok\n"
                "TERNION_OPTIMIZER_INTERNAL_REPORT_END\n"
                "TERNION_OPTIMIZER_USER_SUMMARY_BEGIN\n"
                "## Summary\n"
                "- ok\n"
                "TERNION_OPTIMIZER_USER_SUMMARY_END\n"
            ),
            finish_reason="stop",
            usage={},
        )

    def chat_completion_stream(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("streaming not used in this test")


@pytest.mark.asyncio
async def test_optimizer_prompt_includes_pytest_failure_status_and_retry_budget(
    monkeypatch: MonkeyPatch,
) -> None:
    provider = _CapturingProvider()

    def _fake_get_provider_for_role(_role: str) -> _CapturingProvider:
        return provider

    monkeypatch.setattr(
        "ternion.workflow.nodes.provider_manager.get_provider_for_role", _fake_get_provider_for_role
    )

    mock_user_config = MagicMock()
    mock_user_config.language = "en"
    mock_user_config.browser_language = "en"
    monkeypatch.setattr("ternion.workflow.nodes.config_store.load", lambda: mock_user_config)
    monkeypatch.setattr(
        "ternion.workflow.nodes.config_store.get_role_config",
        lambda _role: RoleConfig(provider="openai", model="gpt-test"),
    )

    state = {
        "current_phase": "optimizer",
        "execution_mode": "ternion_full",
        "ternion_report": "REPORT",
        "generated_code": "WRITER_OUTPUT",
        "conversation_history": [{"role": "user", "content": "do it"}],
        "cursor_tools": [],
        "cursor_tool_choice": None,
        "session_id": "sess",
        "tool_results_meta": {
            "ternion_sess_r0001_c00": {
                "shell_command": "python3 -m pytest -q",
                "shell_exit_code": 1,
                "shell_phase": "execution",
                "pytest_failed_tests": ["tests/test_server.py::test_example"],
                "pytest_error_type": "AssertionError",
                "pytest_summary_line": "1 failed, 372 passed in 1.00s",
                "pytest_trace_tail": "E   AssertionError: boom",
            },
            "ternion_sess_r0002_c00": {
                "shell_command": "python3 -m pytest -q tests/test_server.py::test_example",
                "shell_exit_code": 1,
                "shell_phase": "optimizer",
            },
            "ternion_sess_r0003_c00": {
                "shell_command": "python3 -m pytest -q tests/test_server.py::test_example",
                "shell_exit_code": 1,
                "shell_phase": "optimizer",
                "pytest_error_type": "AssertionError",
                "pytest_trace_tail": "E   AssertionError: boom",
            },
        },
    }

    _out = await optimizer_node(state)

    assert provider.last_messages is not None
    last_user = next(
        (m for m in reversed(provider.last_messages) if m.role == MessageRole.USER), None
    )
    assert last_user is not None
    assert isinstance(last_user.content, str)
    assert "[VERIFICATION STATUS - LAST PYTEST]" in last_user.content
    assert "tests/test_server.py::test_example" in last_user.content
    assert "AssertionError" in last_user.content

    assert "[OPTIMIZER VERIFICATION RETRY POLICY]" in last_user.content
    assert "OPTIMIZER_MAX_VERIFICATION_RETRIES: 2" in last_user.content
    assert "OPTIMIZER_FAILED_VERIFICATION_ATTEMPTS: 2" in last_user.content
    assert "OPTIMIZER_VERIFICATION_RETRIES_REMAINING: 0" in last_user.content

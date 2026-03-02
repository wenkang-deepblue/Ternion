from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.core.config_store import RoleConfig
from ternion.core.models import MessageRole
from ternion.workflow.nodes import execution_node
from ternion.workflow.state import WorkflowPhase


@pytest.mark.asyncio
async def test_execution_empty_output_retries_once_and_recovers() -> None:
    adapter = AsyncMock()
    adapter.name = "openai"
    adapter.supports_native_tool_calls = False

    first = MagicMock()
    first.content = ""
    first.tool_calls = None
    first.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    second = MagicMock()
    second.content = "final deliverable"
    second.tool_calls = None
    second.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    adapter.chat_completion.side_effect = [first, second]

    state = {
        "cursor_system_prompt": None,
        "ternion_report": "REPORT",
        "conversation_history": [{"role": "user", "content": "do the thing"}],
        "cursor_tools": [],
        "cursor_tool_choice": None,
        "session_id": "test-empty-retry",
        "execution_mode": "ternion_full",
        "revision_count": 0,
        "review_feedback": "",
        "generated_code": "",
        "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "evidence_chain_index": [],
        "evidence_topup_round": 0,
        "thinking_logs": [],
        "errors": [],
    }

    mock_user_config = MagicMock()
    mock_user_config.language = "en"
    mock_user_config.browser_language = "en"

    with (
        patch("ternion.workflow.nodes.config_store") as mock_config_store,
        patch("ternion.workflow.nodes.provider_manager") as mock_provider_mgr,
    ):
        mock_config_store.load.return_value = mock_user_config
        mock_config_store.get_role_config.return_value = RoleConfig(
            provider="openai",
            model="gpt-4",
        )
        mock_provider_mgr.get_provider_for_role.return_value = adapter

        out = await execution_node(state)

    assert adapter.chat_completion.call_count == 2
    assert out.get("current_phase") == WorkflowPhase.OPTIMIZER.value
    assert out.get("generated_code") == "final deliverable"

    second_call_messages = adapter.chat_completion.call_args_list[1].kwargs["messages"]
    last_user = next(
        (m for m in reversed(second_call_messages) if m.role == MessageRole.USER), None
    )
    assert last_user is not None
    assert isinstance(last_user.content, str)
    assert "[TERNION EMPTY OUTPUT GUARDRAIL]" in last_user.content


@pytest.mark.asyncio
async def test_execution_empty_output_retry_exhausted_returns_visible_error() -> None:
    adapter = AsyncMock()
    adapter.name = "openai"
    adapter.supports_native_tool_calls = False

    first = MagicMock()
    first.content = ""
    first.tool_calls = None
    first.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    second = MagicMock()
    second.content = ""
    second.tool_calls = None
    second.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    adapter.chat_completion.side_effect = [first, second]

    state = {
        "cursor_system_prompt": None,
        "ternion_report": "REPORT",
        "conversation_history": [{"role": "user", "content": "do the thing"}],
        "cursor_tools": [],
        "cursor_tool_choice": None,
        "session_id": "test-empty-retry-fail",
        "execution_mode": "ternion_full",
        "revision_count": 0,
        "review_feedback": "",
        "generated_code": "",
        "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "evidence_chain_index": [],
        "evidence_topup_round": 0,
        "thinking_logs": [],
        "errors": [],
    }

    mock_user_config = MagicMock()
    mock_user_config.language = "en"
    mock_user_config.browser_language = "en"

    with (
        patch("ternion.workflow.nodes.config_store") as mock_config_store,
        patch("ternion.workflow.nodes.provider_manager") as mock_provider_mgr,
    ):
        mock_config_store.load.return_value = mock_user_config
        mock_config_store.get_role_config.return_value = RoleConfig(
            provider="openai",
            model="gpt-4",
        )
        mock_provider_mgr.get_provider_for_role.return_value = adapter

        out = await execution_node(state)

    assert adapter.chat_completion.call_count == 2
    assert out.get("current_phase") == WorkflowPhase.COMPLETE.value
    assert out.get("generated_code") == ""
    assert "writer_returned_empty_output_after_retry" in str(out.get("final_output") or "")
    assert any(
        "writer_returned_empty_output_after_retry" in str(item)
        for item in (out.get("errors") or [])
    )

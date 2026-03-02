from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.core.config_store import RoleConfig
from ternion.core.models import MessageRole
from ternion.workflow.nodes import execution_node, optimizer_node
from ternion.workflow.state import WorkflowPhase


@pytest.mark.asyncio
async def test_execution_soft_retries_blocked_shell_tool_call_once() -> None:
    adapter = AsyncMock()
    adapter.name = "openai"
    adapter.supports_native_tool_calls = False

    first = MagicMock()
    first.content = ""
    first.tool_calls = [
        {
            "type": "function",
            "function": {"name": "Shell", "arguments": '{"command": "pwd && ls"}'},
        }
    ]
    first.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    second = MagicMock()
    second.content = ""
    second.tool_calls = [
        {
            "type": "function",
            "function": {"name": "Shell", "arguments": '{"command": "pwd"}'},
        }
    ]
    second.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    adapter.chat_completion.side_effect = [first, second]

    state = {
        "cursor_system_prompt": None,
        "ternion_report": "REPORT",
        "conversation_history": [{"role": "user", "content": "do the thing"}],
        "cursor_tools": [
            {"type": "function", "function": {"name": "Shell"}},
        ],
        "cursor_tool_choice": None,
        "session_id": "test-123",
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

    with (
        patch("ternion.workflow.nodes.config_store") as mock_config_store,
        patch("ternion.workflow.nodes.provider_manager") as mock_provider_mgr,
    ):
        mock_config_store.get_role_config.return_value = RoleConfig(
            provider="openai",
            model="gpt-4",
        )
        mock_provider_mgr.get_provider_for_role.return_value = adapter

        out = await execution_node(state)

    assert adapter.chat_completion.call_count == 2
    assert out.get("current_phase") == WorkflowPhase.EXECUTION.value
    tool_calls = out.get("pending_tool_calls") or []
    assert tool_calls and tool_calls[0]["function"]["name"] == "Shell"
    assert '"pwd"' in tool_calls[0]["function"]["arguments"]

    # Second call should include a short tool policy guardrail feedback.
    second_call_messages = adapter.chat_completion.call_args_list[1].kwargs["messages"]
    last_user = next(
        (m for m in reversed(second_call_messages) if m.role == MessageRole.USER), None
    )
    assert last_user is not None
    assert isinstance(last_user.content, str)
    assert "[TERNION TOOL POLICY GUARDRAIL]" in last_user.content
    assert "pwd && ls" in last_user.content


@pytest.mark.asyncio
async def test_optimizer_soft_retries_blocked_shell_tool_call_once() -> None:
    adapter = AsyncMock()
    adapter.name = "openai"
    adapter.supports_native_tool_calls = False

    first = MagicMock()
    first.content = ""
    first.tool_calls = [
        {
            "type": "function",
            "function": {"name": "Shell", "arguments": '{"command": "pwd && ls"}'},
        }
    ]
    first.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    second = MagicMock()
    second.content = ""
    second.tool_calls = [
        {
            "type": "function",
            "function": {"name": "Shell", "arguments": '{"command": "pwd"}'},
        }
    ]
    second.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    adapter.chat_completion.side_effect = [first, second]

    mock_user_config = MagicMock()
    mock_user_config.language = "en"
    mock_user_config.browser_language = "en"

    state = {
        "current_phase": WorkflowPhase.OPTIMIZER.value,
        "execution_mode": "ternion_full",
        "ternion_report": "REPORT",
        "generated_code": "WRITER_OUTPUT",
        "conversation_history": [{"role": "user", "content": "do it"}],
        "cursor_tools": [
            {"type": "function", "function": {"name": "Shell"}},
        ],
        "cursor_tool_choice": None,
        "session_id": "sess-1",
    }

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

        out = await optimizer_node(state)

    assert adapter.chat_completion.call_count == 2
    assert out.get("current_phase") == WorkflowPhase.OPTIMIZER.value
    tool_calls = out.get("pending_tool_calls") or []
    assert tool_calls and tool_calls[0]["function"]["name"] == "Shell"
    assert '"pwd"' in tool_calls[0]["function"]["arguments"]

    second_call_messages = adapter.chat_completion.call_args_list[1].kwargs["messages"]
    last_user = next(
        (m for m in reversed(second_call_messages) if m.role == MessageRole.USER), None
    )
    assert last_user is not None
    assert isinstance(last_user.content, str)
    assert "[TERNION TOOL POLICY GUARDRAIL]" in last_user.content
    assert "pwd && ls" in last_user.content


@pytest.mark.asyncio
async def test_execution_soft_retries_malformed_edit_notebook_tool_call_once() -> None:
    adapter = AsyncMock()
    adapter.name = "openai"
    adapter.supports_native_tool_calls = False

    first = MagicMock()
    first.content = ""
    first.tool_calls = [
        {
            "type": "function",
            "function": {
                "name": "EditNotebook",
                "arguments": (
                    '{"cell_idx":0,"is_new_cell":false,"cell_language":"python",'
                    '"old_string":"","new_string":"print(\'hi\')"}'
                ),
            },
        }
    ]
    first.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    second = MagicMock()
    second.content = ""
    second.tool_calls = [
        {
            "type": "function",
            "function": {
                "name": "Write",
                "arguments": '{"path":"/tmp/x.py","content":"print(\'ok\')\\n"}',
            },
        }
    ]
    second.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    adapter.chat_completion.side_effect = [first, second]

    state = {
        "cursor_system_prompt": None,
        "ternion_report": "REPORT",
        "conversation_history": [{"role": "user", "content": "do the thing"}],
        "cursor_tools": [
            {"type": "function", "function": {"name": "EditNotebook"}},
            {"type": "function", "function": {"name": "Write"}},
        ],
        "cursor_tool_choice": None,
        "session_id": "test-456",
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

    with (
        patch("ternion.workflow.nodes.config_store") as mock_config_store,
        patch("ternion.workflow.nodes.provider_manager") as mock_provider_mgr,
    ):
        mock_config_store.get_role_config.return_value = RoleConfig(
            provider="openai",
            model="gpt-4",
        )
        mock_provider_mgr.get_provider_for_role.return_value = adapter

        out = await execution_node(state)

    assert adapter.chat_completion.call_count == 2
    assert out.get("current_phase") == WorkflowPhase.EXECUTION.value
    tool_calls = out.get("pending_tool_calls") or []
    assert tool_calls and tool_calls[0]["function"]["name"] == "Write"

    second_call_messages = adapter.chat_completion.call_args_list[1].kwargs["messages"]
    last_user = next(
        (m for m in reversed(second_call_messages) if m.role == MessageRole.USER), None
    )
    assert last_user is not None
    assert isinstance(last_user.content, str)
    assert "[TERNION TOOL CALL VALIDATION]" in last_user.content
    assert "target_notebook" in last_user.content
    assert ".ipynb" in last_user.content


@pytest.mark.asyncio
async def test_optimizer_soft_retries_malformed_edit_notebook_tool_call_once() -> None:
    adapter = AsyncMock()
    adapter.name = "openai"
    adapter.supports_native_tool_calls = False

    first = MagicMock()
    first.content = ""
    first.tool_calls = [
        {
            "type": "function",
            "function": {
                "name": "EditNotebook",
                "arguments": (
                    '{"cell_idx":0,"is_new_cell":false,"cell_language":"python",'
                    '"old_string":"","new_string":"x"}'
                ),
            },
        }
    ]
    first.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    second = MagicMock()
    second.content = ""
    second.tool_calls = [
        {
            "type": "function",
            "function": {
                "name": "Write",
                "arguments": '{"path":"/tmp/y.py","content":"print(\'ok\')\\n"}',
            },
        }
    ]
    second.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    adapter.chat_completion.side_effect = [first, second]

    mock_user_config = MagicMock()
    mock_user_config.language = "en"
    mock_user_config.browser_language = "en"

    state = {
        "current_phase": WorkflowPhase.OPTIMIZER.value,
        "execution_mode": "ternion_full",
        "ternion_report": "REPORT",
        "generated_code": "WRITER_OUTPUT",
        "conversation_history": [{"role": "user", "content": "do it"}],
        "cursor_tools": [
            {"type": "function", "function": {"name": "EditNotebook"}},
            {"type": "function", "function": {"name": "Write"}},
        ],
        "cursor_tool_choice": None,
        "session_id": "sess-2",
    }

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

        out = await optimizer_node(state)

    assert adapter.chat_completion.call_count == 2
    assert out.get("current_phase") == WorkflowPhase.OPTIMIZER.value
    tool_calls = out.get("pending_tool_calls") or []
    assert tool_calls and tool_calls[0]["function"]["name"] == "Write"

    second_call_messages = adapter.chat_completion.call_args_list[1].kwargs["messages"]
    last_user = next(
        (m for m in reversed(second_call_messages) if m.role == MessageRole.USER), None
    )
    assert last_user is not None
    assert isinstance(last_user.content, str)
    assert "[TERNION TOOL CALL VALIDATION]" in last_user.content
    assert "target_notebook" in last_user.content

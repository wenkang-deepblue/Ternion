from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.core.config_store import RoleConfig
from ternion.workflow.nodes import execution_node
from ternion.workflow.state import WorkflowPhase


@pytest.mark.asyncio
async def test_execution_topup_final_required_is_soft_and_retries() -> None:
    """
    When the 2nd evidence top-up is missing FINAL_REQUEST=true, the Writer should
    be retried once in-process to avoid an extra user round-trip.
    """
    adapter = AsyncMock()
    adapter.name = "openai"
    adapter.supports_native_tool_calls = False

    first = MagicMock()
    first.content = (
        "TERNION_EVIDENCE_REQUESTS_BEGIN\n"
        "REQUESTER: execution\n"
        "FINAL_REQUEST: false\n"
        "- [P0] path=src/app.py:1-2\n"
        "PURPOSE: Verify initialization.\n"
        "TERNION_EVIDENCE_REQUESTS_END\n"
    )
    first.tool_calls = None
    first.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    second = MagicMock()
    second.content = (
        "TERNION_EVIDENCE_REQUESTS_BEGIN\n"
        "REQUESTER: execution\n"
        "FINAL_REQUEST: true\n"
        "- [P0] path=src/app.py:1-2\n"
        "PURPOSE: Verify initialization.\n"
        "TERNION_EVIDENCE_REQUESTS_END\n"
    )
    second.tool_calls = None
    second.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    adapter.chat_completion.side_effect = [first, second]

    state = {
        "cursor_system_prompt": None,
        "ternion_report": "REPORT",
        "conversation_history": [{"role": "user", "content": "do the thing"}],
        "cursor_tools": [],
        "cursor_tool_choice": None,
        "session_id": "test-123",
        "execution_mode": "ternion_full",
        "revision_count": 0,
        "review_feedback": "",
        "generated_code": "",
        "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "evidence_chain_index": [],
        "evidence_topup_round": 1,
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
    assert out.get("current_phase") == WorkflowPhase.REPORT_EVIDENCE.value
    assert out.get("evidence_topup_round") == 2
    assert "src/app.py" in (out.get("evidence_requests") or "")


@pytest.mark.asyncio
async def test_execution_topup_soft_retry_with_cursor_tools_text_mode() -> None:
    """
    Soft-retry should work when Cursor provides tools (text-tool mode) and the
    2nd evidence top-up is missing FINAL_REQUEST=true on the first attempt.
    """
    adapter = AsyncMock()
    adapter.name = "openai"
    adapter.supports_native_tool_calls = False

    first = MagicMock()
    first.content = (
        "TERNION_EVIDENCE_REQUESTS_BEGIN\n"
        "REQUESTER: execution\n"
        "FINAL_REQUEST: false\n"
        "- [P0] path=src/app.py:1-2\n"
        "PURPOSE: Verify initialization.\n"
        "TERNION_EVIDENCE_REQUESTS_END\n"
    )
    first.tool_calls = None
    first.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    second = MagicMock()
    second.content = (
        "TERNION_EVIDENCE_REQUESTS_BEGIN\n"
        "REQUESTER: execution\n"
        "FINAL_REQUEST: true\n"
        "- [P0] path=src/app.py:1-2\n"
        "PURPOSE: Verify initialization.\n"
        "TERNION_EVIDENCE_REQUESTS_END\n"
    )
    second.tool_calls = None
    second.usage = {"prompt_tokens": 1, "completion_tokens": 1}

    adapter.chat_completion.side_effect = [first, second]

    state = {
        "cursor_system_prompt": None,
        "ternion_report": "REPORT",
        "conversation_history": [{"role": "user", "content": "do the thing"}],
        "cursor_tools": [
            {"type": "function", "function": {"name": "write_file"}},
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
        "evidence_topup_round": 1,
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
    assert out.get("current_phase") == WorkflowPhase.REPORT_EVIDENCE.value
    assert out.get("evidence_topup_round") == 2
    assert out.get("report_evidence_resume_phase") == WorkflowPhase.EXECUTION.value

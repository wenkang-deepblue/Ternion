from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.core.config_store import RoleConfig
from ternion.router.prompts import EXECUTION_PROMPT
from ternion.workflow.nodes import execution_node


@pytest.mark.asyncio
async def test_execution_final_instruction_is_deliverable_aware() -> None:
    adapter = AsyncMock()
    adapter.name = "openai"
    adapter.supports_native_tool_calls = False

    response = MagicMock()
    response.content = "DONE"
    response.tool_calls = None
    response.usage = {}
    adapter.chat_completion.return_value = response

    state = {
        "cursor_system_prompt": None,
        "ternion_report": "Scope: documentation only. Non-goals: no code changes.",
        "conversation_history": [{"role": "user", "content": "doc-only request"}],
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

        await execution_node(state)

    messages = adapter.chat_completion.call_args.kwargs["messages"]
    content = messages[-1].content or ""
    assert "Proceed with the requested deliverable(s)" in content
    assert "[DELIVERABLE POLICY]" in content
    assert "Proceed with the implementation" not in content


@pytest.mark.asyncio
async def test_execution_revision_instruction_uses_deliverable_language() -> None:
    adapter = AsyncMock()
    adapter.name = "openai"
    adapter.supports_native_tool_calls = False

    response = MagicMock()
    response.content = "DONE"
    response.tool_calls = None
    response.usage = {}
    adapter.chat_completion.return_value = response

    state = {
        "cursor_system_prompt": None,
        "ternion_report": "Scope: documentation only. Non-goals: no code changes.",
        "conversation_history": [{"role": "user", "content": "doc-only request"}],
        "cursor_tools": [],
        "cursor_tool_choice": None,
        "session_id": "test-123",
        "execution_mode": "ternion_full",
        "revision_count": 1,
        "review_feedback": "Please improve the deliverable formatting.",
        "generated_code": "Draft content.",
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

        await execution_node(state)

    messages = adapter.chat_completion.call_args.kwargs["messages"]
    content = messages[-1].content or ""
    assert "[CURRENT DELIVERABLE]" in content
    assert "revise the deliverable(s)" in content


def test_execution_prompt_is_deliverable_aware() -> None:
    assert "Deliver the requested deliverable(s)" in EXECUTION_PROMPT
    assert "Follow any deliverable policy and allowed write scope" in EXECUTION_PROMPT
    assert "Proceed with the implementation" not in EXECUTION_PROMPT


def test_execution_prompt_avoids_code_block_directive() -> None:
    assert "Output the code block immediately" not in EXECUTION_PROMPT

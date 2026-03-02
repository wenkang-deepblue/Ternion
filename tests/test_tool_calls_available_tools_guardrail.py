from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.core.models import ChatCompletionRequest, ChatMessage, MessageRole
from ternion.core.session_store import ExecutionMode, Session, SessionStage
from ternion.server.routes import handle_execution_followup


def _minimal_cursor_tools(names: list[str]) -> list[dict]:
    tools: list[dict] = []
    for name in names:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        )
    return tools


@pytest.mark.asyncio
async def test_execution_followup_blocks_tool_calls_not_in_cursor_tools_list() -> None:
    session_id = "0123456789ab"
    session = Session(
        session_id=session_id,
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-02-15T00:00:00Z",
        updated_at="2026-02-15T00:00:00Z",
        cursor_tools=_minimal_cursor_tools(["Write", "Shell"]),
        execution_messages=[],
        pending_tool_calls=[],
        deferred_tool_calls=[],
        round_index=1,
        workflow_phase="execution",
    )

    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[ChatMessage(role=MessageRole.USER, content="continue")],
        stream=False,
    )

    final_state = {
        "current_phase": "execution",
        "pending_tool_calls": [
            {
                "id": "call_bad",
                "type": "function",
                "function": {
                    "name": "search_replace",
                    "arguments": '{"path":"/tmp/x","search":"a","replace":"b"}',
                },
            }
        ],
        "conversation_history": [],
        "ternion_report": "REPORT",
        "generated_code": "",
        "review_feedback": "",
        "revision_count": 0,
        "writer_output_files": {},
        "optimizer_review_report": "",
        "evidence_bundle": "",
        "evidence_gaps": "",
        "evidence_requests": "",
        "evidence_chain_index": [],
        "evidence_topup_round": 0,
        "report_evidence_resume_phase": "",
    }

    mock_user_config = MagicMock()
    mock_user_config.language = "en"
    mock_user_config.browser_language = "en"
    mock_user_config.show_thinking_logs = False
    mock_user_config.show_phase_indicators = True

    with (
        patch(
            "ternion.workflow.implementation_stage.run_implementation_stage", new_callable=AsyncMock
        ) as mock_run,
        patch("ternion.server.routes.config_store") as mock_config_store,
        patch("ternion.utils.i18n.config_store") as mock_i18n_config,
        patch("ternion.server.routes.session_store") as mock_session_store,
    ):
        mock_run.return_value = final_state
        mock_config_store.load.return_value = mock_user_config
        mock_i18n_config.load.return_value = mock_user_config
        mock_session_store.update_session.return_value = session

        resp = await handle_execution_followup(session, request, skip_budget_confirm=True)

        payload = json.loads(resp.body.decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        assert "Tool policy blocked" in content
        assert "search_replace" in content

        saw_confirmation = any(
            call.kwargs.get("stage") == SessionStage.AWAITING_CONFIRMATION
            and call.kwargs.get("confirmation_reason") == "tool_policy"
            for call in mock_session_store.update_session.call_args_list
        )
        assert saw_confirmation

        guardrail_events = [
            call.kwargs.get("append_guardrail_events") or []
            for call in mock_session_store.update_session.call_args_list
            if call.kwargs.get("stage") == SessionStage.AWAITING_CONFIRMATION
            and call.kwargs.get("confirmation_reason") == "tool_policy"
        ]
        assert guardrail_events and guardrail_events[0]
        assert any(e.get("type") == "tool_calls_not_in_cursor_tools" for e in guardrail_events[0])
        blocked: dict[str, object] = next(
            (e for e in guardrail_events[0] if e.get("type") == "tool_calls_not_in_cursor_tools"),
            {},
        )
        blocked_tools = blocked.get("blocked_tools")
        assert isinstance(blocked_tools, list)
        assert "search_replace" in blocked_tools


@pytest.mark.asyncio
async def test_execution_followup_rewrites_shell_alias_run_terminal_cmd_to_available_shell_tool() -> (
    None
):
    session_id = "0123456789ab"
    session = Session(
        session_id=session_id,
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-02-15T00:00:00Z",
        updated_at="2026-02-15T00:00:00Z",
        cursor_tools=_minimal_cursor_tools(["Shell"]),
        execution_messages=[],
        pending_tool_calls=[],
        deferred_tool_calls=[],
        round_index=1,
        workflow_phase="execution",
    )

    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[ChatMessage(role=MessageRole.USER, content="continue")],
        stream=False,
    )

    final_state = {
        "current_phase": "execution",
        "pending_tool_calls": [
            {
                "id": "call_shell",
                "type": "function",
                "function": {
                    "name": "run_terminal_cmd",
                    "arguments": '{"command":"python3 -m pytest -q"}',
                },
            }
        ],
        "conversation_history": [],
        "ternion_report": "REPORT",
        "generated_code": "",
        "review_feedback": "",
        "revision_count": 0,
        "writer_output_files": {},
        "optimizer_review_report": "",
        "evidence_bundle": "",
        "evidence_gaps": "",
        "evidence_requests": "",
        "evidence_chain_index": [],
        "evidence_topup_round": 0,
        "report_evidence_resume_phase": "",
    }

    mock_user_config = MagicMock()
    mock_user_config.language = "en"
    mock_user_config.browser_language = "en"
    mock_user_config.show_thinking_logs = False
    mock_user_config.show_phase_indicators = True

    with (
        patch(
            "ternion.workflow.implementation_stage.run_implementation_stage", new_callable=AsyncMock
        ) as mock_run,
        patch("ternion.server.routes.config_store") as mock_config_store,
        patch("ternion.utils.i18n.config_store") as mock_i18n_config,
        patch("ternion.server.routes.session_store") as mock_session_store,
        patch("ternion.server.routes._enforce_execution_tool_policy") as mock_tool_policy,
        patch("ternion.server.routes._enforce_deliverable_policy") as mock_deliverable_policy,
    ):
        mock_run.return_value = final_state
        mock_config_store.load.return_value = mock_user_config
        mock_i18n_config.load.return_value = mock_user_config
        mock_session_store.update_session.return_value = session
        mock_tool_policy.side_effect = lambda **kwargs: (kwargs["tool_calls"], None)
        mock_deliverable_policy.side_effect = lambda **kwargs: (
            kwargs["tool_calls"],
            None,
            None,
            None,
        )

        resp = await handle_execution_followup(session, request, skip_budget_confirm=True)

        payload = json.loads(resp.body.decode("utf-8"))
        tool_calls = payload["choices"][0]["message"]["tool_calls"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["function"]["name"] == "Shell"

        rewrite_events: list[dict] = []
        for call in mock_session_store.update_session.call_args_list:
            for ev in call.kwargs.get("append_guardrail_events") or []:
                if ev.get("type") == "tool_call_name_rewrite":
                    rewrite_events.append(ev)
        assert rewrite_events
        assert any(
            any(
                r.get("from") == "run_terminal_cmd" and r.get("to") == "Shell"
                for r in (ev.get("rewrites") or [])
            )
            for ev in rewrite_events
        )

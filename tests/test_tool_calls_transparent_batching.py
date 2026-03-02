import json
from unittest.mock import AsyncMock, patch

import pytest

from ternion.core.models import ChatCompletionRequest, ChatMessage, MessageRole
from ternion.core.session_store import ExecutionMode, Session, SessionStage
from ternion.server.routes import handle_execution_followup


@pytest.mark.asyncio
async def test_tool_calls_are_split_into_mutation_then_shell_batches() -> None:
    session = Session(
        session_id="0123456789ab",
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-02-15T00:00:00Z",
        updated_at="2026-02-15T00:00:00Z",
        cursor_system_prompt="",
        cursor_tools=[],
        cursor_tool_choice=None,
        execution_messages=[],
        pending_tool_calls=[],
        deferred_tool_calls=[],
        round_index=1,
        workflow_phase="execution",
    )

    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[
            ChatMessage(role=MessageRole.USER, content="continue"),
            ChatMessage(
                role=MessageRole.TOOL, tool_call_id="ternion_0123456789ab_r0001_c00", content="OK"
            ),
        ],
        stream=False,
    )

    final_state = {
        "current_phase": "execution",
        "pending_tool_calls": [
            {
                "id": "call_mutation",
                "type": "function",
                "function": {
                    "name": "ApplyPatch",
                    "arguments": '{"patch":"*** Begin Patch\\n*** End Patch\\n"}',
                },
            },
            {
                "id": "call_shell",
                "type": "function",
                "function": {
                    "name": "Shell",
                    "arguments": '{"command":"python3 -m pytest -q"}',
                },
            },
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

    with (
        patch(
            "ternion.workflow.implementation_stage.run_implementation_stage",
            new_callable=AsyncMock,
        ) as mock_run,
        patch("ternion.server.routes.session_store") as mock_session_store,
        patch("ternion.server.routes._enforce_execution_tool_policy") as mock_tool_policy,
        patch("ternion.server.routes._enforce_deliverable_policy") as mock_deliverable_policy,
    ):
        mock_run.return_value = final_state
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
        assert tool_calls[0]["function"]["name"] == "ApplyPatch"

        calls_with_pending = [
            kwargs
            for _args, kwargs in mock_session_store.update_session.call_args_list
            if kwargs.get("pending_tool_calls")
        ]
        assert calls_with_pending
        last = calls_with_pending[-1]
        deferred = last.get("deferred_tool_calls") or []
        assert len(deferred) == 1
        assert deferred[0]["id"] == "call_shell"


@pytest.mark.asyncio
async def test_deferred_shell_batch_is_emitted_without_llm_call() -> None:
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
        cursor_system_prompt="",
        cursor_tools=[],
        cursor_tool_choice=None,
        execution_messages=[],
        pending_tool_calls=[
            {
                "id": f"ternion_{session_id}_r0001_c00",
                "type": "function",
                "function": {"name": "ApplyPatch", "arguments": '{"patch":"x"}'},
            }
        ],
        deferred_tool_calls=[
            {
                "id": "call_shell",
                "type": "function",
                "function": {"name": "Shell", "arguments": '{"command":"python3 -m pytest -q"}'},
            }
        ],
        round_index=1,
        workflow_phase="execution",
    )

    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[
            ChatMessage(role=MessageRole.USER, content="continue"),
            ChatMessage(
                role=MessageRole.TOOL,
                tool_call_id=f"ternion_{session_id}_r0001_c00",
                content="RESULT",
            ),
        ],
        stream=False,
    )

    with (
        patch(
            "ternion.workflow.implementation_stage.run_implementation_stage",
            new_callable=AsyncMock,
        ) as mock_run,
        patch("ternion.server.routes.session_store") as mock_session_store,
        patch("ternion.server.routes._enforce_execution_tool_policy") as mock_tool_policy,
        patch("ternion.server.routes._enforce_deliverable_policy") as mock_deliverable_policy,
    ):
        mock_session_store.update_session.return_value = session
        mock_tool_policy.side_effect = lambda **kwargs: (kwargs["tool_calls"], None)
        mock_deliverable_policy.side_effect = lambda **kwargs: (
            kwargs["tool_calls"],
            None,
            None,
            None,
        )

        resp = await handle_execution_followup(session, request, skip_budget_confirm=True)

        mock_run.assert_not_awaited()

        payload = json.loads(resp.body.decode("utf-8"))
        tool_calls = payload["choices"][0]["message"]["tool_calls"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["function"]["name"] == "Shell"

        calls_with_pending = [
            kwargs
            for _args, kwargs in mock_session_store.update_session.call_args_list
            if kwargs.get("pending_tool_calls")
        ]
        assert calls_with_pending
        last = calls_with_pending[-1]
        assert last.get("deferred_tool_calls") == []

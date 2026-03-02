from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import StreamingResponse

from ternion.core.models import ChatCompletionRequest, ChatMessage, MessageRole
from ternion.core.session_store import ExecutionMode, Session, SessionStage
from ternion.server.routes import handle_report_evidence_followup


@pytest.mark.asyncio
async def test_report_evidence_followup_streaming_persists_final_stage() -> None:
    session = Session(
        session_id="0123456789ab",
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-01-11T00:00:00Z",
        updated_at="2026-01-11T00:00:00Z",
        workflow_phase="report_evidence",
    )
    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[
            ChatMessage(
                role=MessageRole.TOOL,
                tool_call_id="ternion_0123456789ab_r0001_c00",
                content="RESULT",
            ),
        ],
        stream=True,
    )
    final_state = {
        "current_phase": "complete",
        "final_output": "OK",
        "generated_code": "",
        "thinking_logs": [],
        "errors": [],
        "pending_tool_calls": [],
        "ternion_report": "REPORT",
        "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "evidence_requests": "- [P0] None",
        "evidence_chain_index": [],
        "ternion_analyses": [],
        "revision_count": 0,
        "review_feedback": "",
        "writer_output_files": {},
        "optimizer_review_report": "",
    }
    mock_user_config = MagicMock()
    mock_user_config.execution_mode = "ternion_full"
    mock_user_config.show_phase_indicators = True
    mock_user_config.show_thinking_logs = False

    with (
        patch(
            "ternion.workflow.graph.resume_report_evidence",
            new_callable=AsyncMock,
        ) as mock_resume,
        patch("ternion.server.routes.config_store") as mock_config_store,
        patch("ternion.server.routes.budget_manager") as mock_budget_manager,
        patch("ternion.server.routes.session_store") as mock_session_store,
    ):
        mock_resume.return_value = final_state
        mock_config_store.load.return_value = mock_user_config
        mock_budget_manager.check_budget.return_value = (True, None)
        mock_session_store.update_session.return_value = session

        resp = await handle_report_evidence_followup(session, request)
        assert isinstance(resp, StreamingResponse)
        async for _chunk in resp.body_iterator:
            pass

        assert mock_session_store.update_session.call_count >= 2
        saw_final = any(
            call.kwargs.get("stage") == SessionStage.EXECUTED
            and str(call.kwargs.get("workflow_phase")) == "complete"
            for call in mock_session_store.update_session.call_args_list
        )
        assert saw_final


@pytest.mark.asyncio
async def test_report_evidence_followup_streaming_non_terminal_without_output_keeps_resumable_stage() -> (
    None
):
    session = Session(
        session_id="0123456789ab",
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-01-11T00:00:00Z",
        updated_at="2026-01-11T00:00:00Z",
        workflow_phase="report_evidence",
    )
    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[
            ChatMessage(
                role=MessageRole.TOOL,
                tool_call_id="ternion_0123456789ab_r0001_c00",
                content="RESULT",
            ),
        ],
        stream=True,
    )
    final_state = {
        "current_phase": "report_evidence",
        "final_output": "",
        "generated_code": "",
        "thinking_logs": [],
        "errors": [],
        "pending_tool_calls": [],
        "ternion_report": "REPORT",
        "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "evidence_requests": "- [P0] None",
        "evidence_chain_index": [],
        "ternion_analyses": [],
        "revision_count": 0,
        "review_feedback": "",
        "writer_output_files": {},
        "optimizer_review_report": "",
    }
    mock_user_config = MagicMock()
    mock_user_config.execution_mode = "ternion_full"
    mock_user_config.show_phase_indicators = True
    mock_user_config.show_thinking_logs = False

    with (
        patch(
            "ternion.workflow.graph.resume_report_evidence",
            new_callable=AsyncMock,
        ) as mock_resume,
        patch("ternion.server.routes.config_store") as mock_config_store,
        patch("ternion.server.routes.budget_manager") as mock_budget_manager,
        patch("ternion.server.routes.session_store") as mock_session_store,
        patch("ternion.server.routes.log_manager.emit") as mock_emit,
    ):
        mock_resume.return_value = final_state
        mock_config_store.load.return_value = mock_user_config
        mock_budget_manager.check_budget.return_value = (True, None)
        mock_session_store.update_session.return_value = session

        resp = await handle_report_evidence_followup(session, request)
        assert isinstance(resp, StreamingResponse)
        async for _chunk in resp.body_iterator:
            pass

        stages = [
            call.kwargs.get("stage")
            for call in mock_session_store.update_session.call_args_list
            if call.kwargs.get("stage") is not None
        ]
        assert SessionStage.RCA_COMPLETE not in stages
        assert SessionStage.EXECUTION_IN_PROGRESS in stages

        warned = any(
            call.kwargs.get("level") == "WARN"
            and "followup_non_terminal_without_output" in str(call.kwargs.get("message", ""))
            for call in mock_emit.call_args_list
        )
        assert warned


@pytest.mark.asyncio
async def test_report_evidence_followup_non_streaming_non_terminal_without_output_keeps_resumable_stage() -> (
    None
):
    session = Session(
        session_id="0123456789ab",
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-01-11T00:00:00Z",
        updated_at="2026-01-11T00:00:00Z",
        workflow_phase="report_evidence",
    )
    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[
            ChatMessage(
                role=MessageRole.TOOL,
                tool_call_id="ternion_0123456789ab_r0001_c00",
                content="RESULT",
            ),
        ],
        stream=False,
    )
    final_state = {
        "current_phase": "report_evidence",
        "final_output": "",
        "generated_code": "",
        "thinking_logs": [],
        "errors": [],
        "pending_tool_calls": [],
        "ternion_report": "REPORT",
        "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "evidence_requests": "- [P0] None",
        "evidence_chain_index": [],
        "ternion_analyses": [],
        "revision_count": 0,
        "review_feedback": "",
        "writer_output_files": {},
        "optimizer_review_report": "",
    }
    mock_user_config = MagicMock()
    mock_user_config.execution_mode = "ternion_full"
    mock_user_config.show_phase_indicators = True
    mock_user_config.show_thinking_logs = False

    with (
        patch(
            "ternion.workflow.graph.resume_report_evidence",
            new_callable=AsyncMock,
        ) as mock_resume,
        patch("ternion.server.routes.config_store") as mock_config_store,
        patch("ternion.server.routes.budget_manager") as mock_budget_manager,
        patch("ternion.server.routes.session_store") as mock_session_store,
        patch("ternion.server.routes.log_manager.emit") as mock_emit,
    ):
        mock_resume.return_value = final_state
        mock_config_store.load.return_value = mock_user_config
        mock_budget_manager.check_budget.return_value = (True, None)
        mock_session_store.update_session.return_value = session

        _resp = await handle_report_evidence_followup(session, request)

        stages = [
            call.kwargs.get("stage")
            for call in mock_session_store.update_session.call_args_list
            if call.kwargs.get("stage") is not None
        ]
        assert SessionStage.RCA_COMPLETE not in stages
        assert SessionStage.EXECUTION_IN_PROGRESS in stages

        warned = any(
            call.kwargs.get("level") == "WARN"
            and "followup_non_terminal_without_output" in str(call.kwargs.get("message", ""))
            for call in mock_emit.call_args_list
        )
        assert warned


@pytest.mark.asyncio
async def test_report_evidence_followup_passes_resume_metadata_to_resume_workflow() -> None:
    session = Session(
        session_id="0123456789ab",
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-01-11T00:00:00Z",
        updated_at="2026-01-11T00:00:00Z",
        workflow_phase="report_evidence",
        evidence_chain_index=[{"request_id": "req-1"}],
        evidence_topup_round=1,
        report_evidence_resume_phase="execution",
    )
    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[
            ChatMessage(
                role=MessageRole.TOOL,
                tool_call_id="ternion_0123456789ab_r0001_c00",
                content="RESULT",
            ),
        ],
        stream=False,
    )
    final_state = {
        "current_phase": "report_evidence",
        "final_output": "",
        "generated_code": "",
        "thinking_logs": [],
        "errors": [],
        "pending_tool_calls": [],
        "ternion_report": "REPORT",
        "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "evidence_requests": "- [P0] None",
        "evidence_chain_index": [{"request_id": "req-1"}],
        "ternion_analyses": [],
        "revision_count": 0,
        "review_feedback": "",
        "writer_output_files": {},
        "optimizer_review_report": "",
    }
    mock_user_config = MagicMock()
    mock_user_config.execution_mode = "ternion_full"
    mock_user_config.show_phase_indicators = True
    mock_user_config.show_thinking_logs = False

    with (
        patch(
            "ternion.workflow.graph.resume_report_evidence",
            new_callable=AsyncMock,
        ) as mock_resume,
        patch("ternion.server.routes.config_store") as mock_config_store,
        patch("ternion.server.routes.budget_manager") as mock_budget_manager,
        patch("ternion.server.routes.session_store") as mock_session_store,
    ):
        mock_resume.return_value = final_state
        mock_config_store.load.return_value = mock_user_config
        mock_budget_manager.check_budget.return_value = (True, None)
        mock_session_store.update_session.return_value = session

        _resp = await handle_report_evidence_followup(session, request)

        assert mock_resume.await_count == 1
        kwargs = mock_resume.await_args.kwargs
        assert kwargs.get("evidence_chain_index") == session.evidence_chain_index
        assert kwargs.get("evidence_topup_round") == session.evidence_topup_round
        assert kwargs.get("report_evidence_resume_phase") == session.report_evidence_resume_phase


@pytest.mark.asyncio
async def test_report_evidence_followup_streaming_tool_calls_persists_topup_resume_phase_for_next_round() -> (
    None
):
    session = Session(
        session_id="0123456789ab",
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-01-11T00:00:00Z",
        updated_at="2026-01-11T00:00:00Z",
        workflow_phase="report_evidence",
        evidence_topup_round=0,
        report_evidence_resume_phase="",
        round_index=0,
    )
    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[
            ChatMessage(
                role=MessageRole.TOOL,
                tool_call_id="ternion_0123456789ab_r0001_c00",
                content="RESULT",
            ),
        ],
        stream=True,
    )
    final_state_round1 = {
        "current_phase": "report_evidence",
        "final_output": "",
        "generated_code": "",
        "thinking_logs": [],
        "errors": [],
        "pending_tool_calls": [
            {
                "id": "toolcall-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path":"/tmp/x"}'},
            }
        ],
        "ternion_report": "REPORT",
        "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "evidence_requests": "- [P0] None",
        "evidence_chain_index": [],
        "ternion_analyses": [],
        "evidence_topup_round": 1,
        "report_evidence_resume_phase": "execution",
    }
    final_state_round2 = {
        "current_phase": "report_evidence",
        "final_output": "",
        "generated_code": "",
        "thinking_logs": [],
        "errors": [],
        "pending_tool_calls": [],
        "ternion_report": "REPORT",
        "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "evidence_requests": "- [P0] None",
        "evidence_chain_index": [],
        "ternion_analyses": [],
        "evidence_topup_round": 1,
        "report_evidence_resume_phase": "execution",
    }
    mock_user_config = MagicMock()
    mock_user_config.execution_mode = "ternion_full"
    mock_user_config.show_phase_indicators = True
    mock_user_config.show_thinking_logs = False

    with (
        patch(
            "ternion.workflow.graph.resume_report_evidence",
            new_callable=AsyncMock,
        ) as mock_resume,
        patch("ternion.server.routes.config_store") as mock_config_store,
        patch("ternion.server.routes.budget_manager") as mock_budget_manager,
        patch("ternion.server.routes.session_store") as mock_session_store,
    ):
        mock_resume.side_effect = [final_state_round1, final_state_round2]
        mock_config_store.load.return_value = mock_user_config
        mock_budget_manager.check_budget.return_value = (True, None)
        mock_session_store.update_session.return_value = session
        mock_session_store.load_session.return_value = session

        resp1 = await handle_report_evidence_followup(session, request)
        assert isinstance(resp1, StreamingResponse)
        async for _chunk in resp1.body_iterator:
            pass

        tool_call_updates = [
            call.kwargs
            for call in mock_session_store.update_session.call_args_list
            if call.kwargs.get("stage") == SessionStage.AWAITING_TOOL_RESULTS
            and call.kwargs.get("pending_tool_calls")
        ]
        assert tool_call_updates
        persisted = tool_call_updates[-1]
        assert persisted.get("report_evidence_resume_phase") == "execution"
        assert persisted.get("evidence_topup_round") == 1

        session_next = Session.from_dict(session.to_dict())
        session_next.stage = SessionStage.AWAITING_TOOL_RESULTS
        session_next.workflow_phase = "report_evidence"
        session_next.evidence_topup_round = 1
        session_next.report_evidence_resume_phase = "execution"
        request_next = ChatCompletionRequest(
            model="ternion-team",
            messages=[
                ChatMessage(
                    role=MessageRole.TOOL,
                    tool_call_id="ternion_0123456789ab_r0002_c00",
                    content="RESULT-2",
                ),
            ],
            stream=False,
        )
        _resp2 = await handle_report_evidence_followup(session_next, request_next)

        kwargs = mock_resume.await_args.kwargs
        assert kwargs.get("evidence_topup_round") == 1
        assert kwargs.get("report_evidence_resume_phase") == "execution"


@pytest.mark.asyncio
async def test_report_evidence_followup_non_streaming_tool_calls_does_not_regress_topup_round() -> (
    None
):
    session = Session(
        session_id="0123456789ab",
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-01-11T00:00:00Z",
        updated_at="2026-01-11T00:00:00Z",
        workflow_phase="report_evidence",
        evidence_topup_round=1,
        report_evidence_resume_phase="execution",
        round_index=0,
    )
    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[
            ChatMessage(
                role=MessageRole.TOOL,
                tool_call_id="ternion_0123456789ab_r0001_c00",
                content="RESULT",
            ),
        ],
        stream=False,
    )
    final_state = {
        "current_phase": "report_evidence",
        "final_output": "",
        "generated_code": "",
        "thinking_logs": [],
        "errors": [],
        "pending_tool_calls": [
            {
                "id": "toolcall-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path":"/tmp/x"}'},
            }
        ],
        "ternion_report": "REPORT",
        "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "evidence_requests": "- [P0] None",
        "evidence_chain_index": [],
        "ternion_analyses": [],
        "evidence_topup_round": 0,
        "report_evidence_resume_phase": "",
    }
    mock_user_config = MagicMock()
    mock_user_config.execution_mode = "ternion_full"
    mock_user_config.show_phase_indicators = True
    mock_user_config.show_thinking_logs = False

    with (
        patch(
            "ternion.workflow.graph.resume_report_evidence",
            new_callable=AsyncMock,
        ) as mock_resume,
        patch("ternion.server.routes.config_store") as mock_config_store,
        patch("ternion.server.routes.budget_manager") as mock_budget_manager,
        patch("ternion.server.routes.session_store") as mock_session_store,
    ):
        mock_resume.return_value = final_state
        mock_config_store.load.return_value = mock_user_config
        mock_budget_manager.check_budget.return_value = (True, None)
        mock_session_store.update_session.return_value = session
        mock_session_store.load_session.return_value = session

        _resp = await handle_report_evidence_followup(session, request)

        tool_call_updates = [
            call.kwargs
            for call in mock_session_store.update_session.call_args_list
            if call.kwargs.get("stage") == SessionStage.AWAITING_TOOL_RESULTS
            and call.kwargs.get("pending_tool_calls")
        ]
        assert tool_call_updates
        persisted = tool_call_updates[-1]
        assert persisted.get("evidence_topup_round") == 1
        assert persisted.get("report_evidence_resume_phase") == "execution"

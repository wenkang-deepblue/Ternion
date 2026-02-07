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


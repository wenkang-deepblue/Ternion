from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.core.models import ChatCompletionRequest, ChatMessage, MessageRole
from ternion.core.session_store import ExecutionMode, Session, SessionStage
from ternion.server.routes import handle_execution_followup


@pytest.mark.asyncio
async def test_execution_followup_extracts_pytest_failure_details_into_meta() -> None:
    session_id = "0123456789ab"
    tool_call_id = f"ternion_{session_id}_r0001_c00"
    session = Session(
        session_id=session_id,
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-02-15T00:00:00Z",
        updated_at="2026-02-15T00:00:00Z",
        pending_tool_calls=[
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": "Shell",
                    "arguments": '{"command":"python3 -m pytest -q"}',
                },
            }
        ],
        execution_messages=[],
        tool_results_meta={},
        tool_results_raw={},
        tool_call_index={
            tool_call_id: {
                "tool_name": "Shell",
                "tool_arguments": '{"command":"python3 -m pytest -q"}',
                "workflow_phase": "execution",
                "round_index": 1,
            }
        },
        workflow_phase="execution",
        round_index=1,
    )

    raw_output = (
        "Exit code: 1\n\n"
        "Command output:\n\n"
        "============================= test session starts ==============================\n"
        "FAILED tests/test_server.py::test_example - AssertionError: boom\n"
        "E   AssertionError: boom\n"
        "=========================== short test summary info ============================\n"
        "FAILED tests/test_server.py::test_example - AssertionError: boom\n"
        "1 failed, 372 passed in 1.00s\n"
    )
    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[
            ChatMessage(role=MessageRole.USER, content="continue"),
            ChatMessage(role=MessageRole.TOOL, tool_call_id=tool_call_id, content=raw_output),
        ],
        stream=False,
    )

    mock_user_config = MagicMock()
    mock_user_config.show_thinking_logs = False
    mock_user_config.show_phase_indicators = True

    final_state = {
        "current_phase": "complete",
        "final_output": "OK",
        "final_output_suffix": "",
        "generated_code": "",
        "errors": [],
        "thinking_logs": [],
        "conversation_history": [],
        "modified_files": [],
        "baseline_file_snapshots": {},
        "writer_output_files": {},
        "optimizer_review_report": "",
        "pending_tool_calls": [],
    }

    with (
        patch(
            "ternion.workflow.implementation_stage.run_implementation_stage", new_callable=AsyncMock
        ) as mock_run,
        patch("ternion.server.routes.config_store") as mock_config_store,
        patch("ternion.server.routes.session_store") as mock_session_store,
    ):
        mock_run.return_value = final_state
        mock_config_store.load.return_value = mock_user_config
        mock_session_store.update_session.return_value = session

        _resp = await handle_execution_followup(session, request, skip_budget_confirm=True)

        assert mock_session_store.update_session.call_count >= 1
        _args, kwargs = mock_session_store.update_session.call_args_list[0]
        tool_results_meta = kwargs.get("tool_results_meta") or {}
        assert tool_call_id in tool_results_meta
        meta = tool_results_meta[tool_call_id]
        assert meta.get("shell_exit_code") == 1
        assert meta.get("pytest_failed_tests") == ["tests/test_server.py::test_example"]
        assert meta.get("pytest_error_type") == "AssertionError"
        assert "AssertionError" in (meta.get("pytest_trace_tail") or "")

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
async def test_execution_followup_records_shell_external_output_path_in_meta_and_index() -> None:
    session_id = "0123456789ab"
    tool_call_id = f"ternion_{session_id}_r0001_c00"
    external_path = "/tmp/agent-tools/ruff_check.txt"

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
        pending_tool_calls=[
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": "Shell",
                    "arguments": json.dumps({"command": "python3 -m ruff check ."}),
                },
            }
        ],
        deferred_tool_calls=[],
        round_index=1,
        workflow_phase="execution",
    )

    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[
            ChatMessage(
                role=MessageRole.TOOL,
                tool_call_id=tool_call_id,
                content=(
                    "Exit code: 1\n\n"
                    "Command output:\n\n"
                    "(truncated)\n"
                    f"output written to: {external_path}\n"
                ),
            ),
            ChatMessage(role=MessageRole.USER, content="continue"),
        ],
        stream=False,
    )

    final_state = {
        "current_phase": "execution",
        "pending_tool_calls": [],
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
        patch("ternion.utils.i18n._load_user_config") as mock_i18n_config,
        patch("ternion.server.routes.session_store") as mock_session_store,
    ):
        mock_run.return_value = final_state
        mock_config_store.load.return_value = mock_user_config
        mock_i18n_config.return_value = mock_user_config
        mock_session_store.update_session.return_value = session

        _resp = await handle_execution_followup(session, request, skip_budget_confirm=True)

        found = False
        for call in mock_session_store.update_session.call_args_list:
            ext = call.kwargs.get("append_external_outputs_index") or []
            if not ext:
                continue
            found = True
            assert any(item.get("path") == external_path for item in ext)

            meta_map = call.kwargs.get("tool_results_meta") or {}
            assert tool_call_id in meta_map
            assert meta_map[tool_call_id].get("shell_output_external_path") == external_path
            assert external_path in (
                meta_map[tool_call_id].get("shell_output_external_paths") or []
            )
            break

        assert found, "Expected append_external_outputs_index to be persisted via update_session"

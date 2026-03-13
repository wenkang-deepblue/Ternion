from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.core.models import ChatCompletionRequest, ChatMessage, MessageRole
from ternion.core.session_store import ExecutionMode, Session, SessionStage
from ternion.server.routes import handle_execution_followup


@pytest.mark.asyncio
async def test_execution_followup_doc_only_write_promotes_to_optimizer(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    doc_path = workspace / "docs" / "spec.md"
    doc_path.parent.mkdir(parents=True)
    doc_path.write_text("# Spec\nUpdated\n", encoding="utf-8")

    tool_call_id = "ternion_0123456789ab_r0001_c00"
    session = Session(
        session_id="0123456789ab",
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="## Scope & Non-Goals\n- Documentation only\n- Do not change code\n",
        ternion_report_safe="## Scope & Non-Goals\n- Documentation only\n- Do not change code\n",
        report_hash="hash",
        created_at="2026-03-13T00:00:00Z",
        updated_at="2026-03-13T00:00:00Z",
        workflow_phase="execution",
        workspace_root=str(workspace),
        cursor_system_prompt="SYS",
        execution_messages=[{"role": "user", "content": "请只更新文档。"}],
        pending_tool_calls=[
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": "Write",
                    "arguments": json.dumps(
                        {"path": str(doc_path), "content": "# Spec\nUpdated\n"},
                        ensure_ascii=False,
                    ),
                },
            }
        ],
        round_index=1,
    )

    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[
            ChatMessage(role=MessageRole.USER, content="continue"),
            ChatMessage(role=MessageRole.TOOL, tool_call_id=tool_call_id, content="ok"),
        ],
        stream=False,
        tools=[{"type": "function", "function": {"name": "Write"}}],
    )

    final_state = {
        "current_phase": "complete",
        "final_output": "OK",
        "final_output_suffix": "",
        "generated_code": "",
        "errors": [],
        "thinking_logs": [],
        "conversation_history": [],
        "modified_files": [str(doc_path)],
        "baseline_file_snapshots": {str(doc_path): ""},
        "writer_output_files": {str(doc_path): "# Spec\nUpdated\n"},
        "optimizer_review_report": "",
        "pending_tool_calls": [],
    }

    mock_user_config = MagicMock()
    mock_user_config.show_thinking_logs = False
    mock_user_config.show_phase_indicators = True

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

    initial_state = mock_run.await_args.args[0]
    assert initial_state["current_phase"] == "optimizer"
    assert initial_state["writer_output_files"][str(doc_path)] == "# Spec\nUpdated\n"
    assert str(doc_path) in (initial_state.get("stabilized_document_paths") or [])

    assert any(
        call.kwargs.get("workflow_phase") == "optimizer"
        and str(doc_path) in (call.kwargs.get("stabilized_document_paths") or [])
        for call in mock_session_store.update_session.call_args_list
    )

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.core.models import ChatCompletionRequest, ChatMessage, MessageRole
from ternion.core.session_store import ExecutionMode, Session, SessionStage
from ternion.server.routes import handle_execution_followup


@pytest.mark.asyncio
async def test_execution_followup_shell_side_effects_updates_modified_files_and_baseline() -> None:
    repo_root = Path.cwd().resolve()
    abs_path = str((repo_root / "docs" / "advanced_feature_plan.md").resolve())
    rel_path = "docs/advanced_feature_plan.md"

    tool_call_id = "ternion_0123456789ab_r0001_c00"
    session = Session(
        session_id="0123456789ab",
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-01-11T00:00:00Z",
        updated_at="2026-01-11T00:00:00Z",
        tool_call_index={
            tool_call_id: {
                "tool_name": "Shell",
                "tool_arguments": "{\"command\":\"black .\",\"description\":\"format\"}",
                "workflow_phase": "execution",
                "round_index": 1,
            }
        },
        tool_loop_pre_git_status={
            "repo_root": str(repo_root),
            "modified": [],
            "untracked": [],
            "round_index": 1,
            "workflow_phase": "execution",
        },
    )

    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[
            ChatMessage(role=MessageRole.USER, content="Continue"),
            ChatMessage(role=MessageRole.TOOL, tool_call_id=tool_call_id, content="completed in 12ms\nexit_code: 0"),
        ],
        stream=False,
    )

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

    mock_user_config = MagicMock()
    mock_user_config.show_thinking_logs = False
    mock_user_config.show_phase_indicators = True

    with (
        patch("ternion.workflow.implementation_stage.run_implementation_stage", new_callable=AsyncMock) as mock_run,
        patch("ternion.server.routes.config_store") as mock_config_store,
        patch("ternion.server.routes.session_store") as mock_session_store,
        patch("ternion.server.routes._try_get_git_status_snapshot") as mock_git_status,
        patch("ternion.server.routes._try_read_git_head_file") as mock_git_head,
    ):
        mock_run.return_value = final_state
        mock_config_store.load.return_value = mock_user_config
        mock_session_store.update_session.return_value = session
        mock_git_status.return_value = {"repo_root": str(repo_root), "modified": [abs_path], "untracked": []}
        mock_git_head.return_value = "BASELINE"

        _resp = await handle_execution_followup(session, request, skip_budget_confirm=True)

        assert mock_session_store.update_session.call_count >= 1
        _args, kwargs = mock_session_store.update_session.call_args_list[0]
        baseline = kwargs.get("baseline_file_snapshots") or {}
        modified_files = kwargs.get("modified_files") or []
        meta = (kwargs.get("tool_results_meta") or {}).get(tool_call_id) or {}

        assert abs_path in modified_files
        assert baseline.get(abs_path) == "BASELINE"
        assert meta.get("shell_dirty_added_count") == 1
        assert rel_path in (meta.get("shell_dirty_added_paths") or [])


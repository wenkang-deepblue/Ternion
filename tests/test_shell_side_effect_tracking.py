from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import StreamingResponse

from ternion.core.models import ChatCompletionRequest, ChatMessage, MessageRole
from ternion.core.session_store import ExecutionMode, Session, SessionStage
from ternion.server.routes import handle_execution_followup
from ternion.utils.i18n import MessageKey, t


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
                "tool_arguments": '{"command":"black .","description":"format"}',
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
            ChatMessage(
                role=MessageRole.TOOL,
                tool_call_id=tool_call_id,
                content="completed in 12ms\nexit_code: 0",
            ),
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
        patch(
            "ternion.workflow.implementation_stage.run_implementation_stage", new_callable=AsyncMock
        ) as mock_run,
        patch("ternion.server.routes.config_store") as mock_config_store,
        patch("ternion.server.routes.session_store") as mock_session_store,
        patch("ternion.server.routes._try_get_git_status_snapshot") as mock_git_status,
        patch("ternion.server.routes._try_read_git_head_file") as mock_git_head,
    ):
        mock_run.return_value = final_state
        mock_config_store.load.return_value = mock_user_config
        mock_session_store.update_session.return_value = session
        mock_git_status.return_value = {
            "repo_root": str(repo_root),
            "modified": [abs_path],
            "untracked": [],
        }
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


@pytest.mark.asyncio
async def test_execution_followup_streaming_pending_tool_calls_does_not_crash() -> None:
    """Streaming execution follow-up should persist pending tool calls without SSE crash."""
    session = Session(
        session_id="0123456789ab",
        stage=SessionStage.EXECUTION_IN_PROGRESS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-01-11T00:00:00Z",
        updated_at="2026-01-11T00:00:00Z",
        round_index=0,
        workflow_phase="execution",
        cursor_system_prompt="SYS",
        execution_messages=[{"role": "user", "content": "Continue"}],
        pending_tool_calls=[],
    )
    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[ChatMessage(role=MessageRole.USER, content="continue")],
        stream=True,
    )
    final_state = {
        "current_phase": "execution",
        "final_output": "",
        "generated_code": "",
        "errors": [],
        "thinking_logs": [],
        "conversation_history": [{"role": "user", "content": "Continue"}],
        "pending_tool_calls": [
            {
                "id": "call_abc",
                "type": "function",
                "function": {
                    "name": "Write",
                    "arguments": '{"path":"/Users/apple/Desktop/Ternion/docs/tmp.md","contents":"x"}',
                },
            }
        ],
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
        patch("ternion.server.routes._enforce_execution_tool_policy") as mock_tool_policy,
        patch("ternion.server.routes._enforce_deliverable_policy") as mock_deliverable_policy,
        patch("ternion.server.routes._ensure_baseline_snapshots_for_tool_calls") as mock_baseline,
        patch("ternion.server.routes._capture_tool_loop_pre_git_status") as mock_pre_git,
    ):
        mock_run.return_value = final_state
        mock_config_store.load.return_value = mock_user_config
        mock_session_store.update_session.return_value = session
        mock_tool_policy.side_effect = lambda **kwargs: (kwargs["tool_calls"], None)
        mock_deliverable_policy.side_effect = (
            lambda **kwargs: (
                kwargs["tool_calls"],
                None,
                None,
                None,
            )
        )
        mock_baseline.return_value = ({}, [])
        mock_pre_git.return_value = {}

        resp = await handle_execution_followup(session, request, skip_budget_confirm=True)
        assert isinstance(resp, StreamingResponse)
        async for _chunk in resp.body_iterator:
            pass

        saw_pending_update = any(
            call.kwargs.get("stage") == SessionStage.AWAITING_TOOL_RESULTS
            and call.kwargs.get("round_index") == 1
            and isinstance(call.kwargs.get("pending_tool_calls"), list)
            and len(call.kwargs.get("pending_tool_calls")) == 1
            for call in mock_session_store.update_session.call_args_list
        )
        assert saw_pending_update


@pytest.mark.asyncio
async def test_execution_followup_streaming_dedupes_adjacent_execution_phase_indicator() -> None:
    session = Session(
        session_id="0123456789ab",
        stage=SessionStage.EXECUTION_IN_PROGRESS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-01-11T00:00:00Z",
        updated_at="2026-01-11T00:00:00Z",
        round_index=0,
        workflow_phase="execution",
        execution_phase_announced=False,
        report_evidence_resume_phase="",
        cursor_system_prompt="SYS",
        execution_messages=[{"role": "user", "content": "Continue"}],
        pending_tool_calls=[],
    )
    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[ChatMessage(role=MessageRole.USER, content="continue")],
        stream=True,
    )
    final_state = {
        "current_phase": "complete",
        "final_output": "DONE",
        "generated_code": "",
        "errors": [],
        "thinking_logs": [],
        "conversation_history": [{"role": "user", "content": "Continue"}],
        "pending_tool_calls": [],
    }
    mock_user_config = MagicMock()
    mock_user_config.language = "en"
    mock_user_config.show_thinking_logs = False
    mock_user_config.show_phase_indicators = True

    async def run_impl_with_duplicate_phase(initial_state):  # type: ignore[no-untyped-def]
        queue = initial_state.get("_stream_queue")
        if queue is not None:
            await queue.put_phase_start("execution")
            await queue.put_phase_start("execution")
        return final_state

    with (
        patch(
            "ternion.workflow.implementation_stage.run_implementation_stage", new_callable=AsyncMock
        ) as mock_run,
        patch("ternion.server.routes.config_store") as mock_config_store,
        patch("ternion.utils.i18n._load_user_config") as mock_i18n_config,
        patch("ternion.server.routes.session_store") as mock_session_store,
    ):
        mock_run.side_effect = run_impl_with_duplicate_phase
        mock_config_store.load.return_value = mock_user_config
        mock_i18n_config.return_value = mock_user_config
        mock_session_store.update_session.return_value = session
        mock_session_store.load_session.return_value = session

        resp = await handle_execution_followup(session, request, skip_budget_confirm=True)
        assert isinstance(resp, StreamingResponse)

        chunks: list[dict] = []
        async for raw_chunk in resp.body_iterator:
            text = raw_chunk.decode("utf-8") if isinstance(raw_chunk, bytes) else str(raw_chunk)
            for line in text.splitlines():
                if not line.startswith("data: "):
                    continue
                payload = line.removeprefix("data: ").strip()
                if payload == "[DONE]":
                    continue
                chunks.append(json.loads(payload))

        content_parts = []
        for chunk in chunks:
            delta = (chunk.get("choices", [{}])[0] or {}).get("delta", {}) or {}
            content = delta.get("content")
            if isinstance(content, str):
                content_parts.append(content)
        merged = "".join(content_parts)

        execution_indicator = t(MessageKey.EXECUTION_START)
        assert merged.count(execution_indicator) == 1
        assert "DONE" in merged
        assert any(
            call.kwargs.get("execution_phase_announced") is True
            for call in mock_session_store.update_session.call_args_list
        )


@pytest.mark.asyncio
async def test_execution_followup_streaming_backfills_first_error_when_final_output_empty() -> None:
    session = Session(
        session_id="0123456789ab",
        stage=SessionStage.EXECUTION_IN_PROGRESS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-01-11T00:00:00Z",
        updated_at="2026-01-11T00:00:00Z",
        round_index=0,
        workflow_phase="execution",
        cursor_system_prompt="SYS",
        execution_messages=[{"role": "user", "content": "Continue"}],
        pending_tool_calls=[],
    )
    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[ChatMessage(role=MessageRole.USER, content="continue")],
        stream=True,
    )
    final_state = {
        "current_phase": "complete",
        "final_output": "",
        "generated_code": "",
        "errors": ["writer_returned_empty_output_after_retry"],
        "thinking_logs": [],
        "conversation_history": [{"role": "user", "content": "Continue"}],
        "pending_tool_calls": [],
    }
    mock_user_config = MagicMock()
    mock_user_config.language = "en"
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
        mock_session_store.load_session.return_value = session

        resp = await handle_execution_followup(session, request, skip_budget_confirm=True)
        assert isinstance(resp, StreamingResponse)

        content_parts: list[str] = []
        async for raw_chunk in resp.body_iterator:
            text = raw_chunk.decode("utf-8") if isinstance(raw_chunk, bytes) else str(raw_chunk)
            for line in text.splitlines():
                if not line.startswith("data: "):
                    continue
                payload = line.removeprefix("data: ").strip()
                if payload == "[DONE]":
                    continue
                chunk = json.loads(payload)
                delta = (chunk.get("choices", [{}])[0] or {}).get("delta", {}) or {}
                content = delta.get("content")
                if isinstance(content, str):
                    content_parts.append(content)

        merged = "".join(content_parts)
        assert "writer_returned_empty_output_after_retry" in merged


@pytest.mark.asyncio
async def test_execution_followup_streaming_hides_execution_start_after_announced() -> None:
    session = Session(
        session_id="0123456789ab",
        stage=SessionStage.EXECUTION_IN_PROGRESS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-01-11T00:00:00Z",
        updated_at="2026-01-11T00:00:00Z",
        round_index=0,
        workflow_phase="execution",
        execution_phase_announced=True,
        report_evidence_resume_phase="",
        cursor_system_prompt="SYS",
        execution_messages=[{"role": "user", "content": "Continue"}],
        pending_tool_calls=[],
    )
    request = ChatCompletionRequest(
        model="ternion-team",
        messages=[ChatMessage(role=MessageRole.USER, content="continue")],
        stream=True,
    )
    final_state = {
        "current_phase": "complete",
        "final_output": "DONE",
        "generated_code": "",
        "errors": [],
        "thinking_logs": [],
        "conversation_history": [{"role": "user", "content": "Continue"}],
        "pending_tool_calls": [],
    }
    mock_user_config = MagicMock()
    mock_user_config.language = "en"
    mock_user_config.show_thinking_logs = False
    mock_user_config.show_phase_indicators = True

    async def run_impl_with_execution_phase(initial_state):  # type: ignore[no-untyped-def]
        queue = initial_state.get("_stream_queue")
        if queue is not None:
            await queue.put_phase_start("execution")
        return final_state

    with (
        patch(
            "ternion.workflow.implementation_stage.run_implementation_stage", new_callable=AsyncMock
        ) as mock_run,
        patch("ternion.server.routes.config_store") as mock_config_store,
        patch("ternion.utils.i18n._load_user_config") as mock_i18n_config,
        patch("ternion.server.routes.session_store") as mock_session_store,
    ):
        mock_run.side_effect = run_impl_with_execution_phase
        mock_config_store.load.return_value = mock_user_config
        mock_i18n_config.return_value = mock_user_config
        mock_session_store.update_session.return_value = session
        mock_session_store.load_session.return_value = session

        resp = await handle_execution_followup(session, request, skip_budget_confirm=True)
        assert isinstance(resp, StreamingResponse)

        content_parts: list[str] = []
        async for raw_chunk in resp.body_iterator:
            text = raw_chunk.decode("utf-8") if isinstance(raw_chunk, bytes) else str(raw_chunk)
            for line in text.splitlines():
                if not line.startswith("data: "):
                    continue
                payload = line.removeprefix("data: ").strip()
                if payload == "[DONE]":
                    continue
                chunk = json.loads(payload)
                delta = (chunk.get("choices", [{}])[0] or {}).get("delta", {}) or {}
                content = delta.get("content")
                if isinstance(content, str):
                    content_parts.append(content)

        merged = "".join(content_parts)
        execution_indicator = t(MessageKey.EXECUTION_START)
        assert execution_indicator not in merged
        assert "DONE" in merged

"""
Tests for per-session turn locking in follow-up handlers (Phase C2).

Verifies that concurrent follow-ups for the same session serialize across
the whole turn (load -> merge -> workflow -> save), including the streaming
hand-off path where the SSE generator owns the lock release.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import StreamingResponse

from ternion.core.models import ChatCompletionRequest, ChatMessage, MessageRole
from ternion.core.session_store import (
    ExecutionMode,
    Session,
    SessionStage,
    get_session_lock,
)
from ternion.server.routes import (
    _SessionTurnLock,
    handle_evidence_followup,
    handle_execution_followup,
    handle_report_evidence_followup,
)

pytestmark = pytest.mark.asyncio


def _build_session(session_id: str) -> Session:
    return Session(
        session_id=session_id,
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_mode=ExecutionMode.TERNION_FULL,
        ternion_report_raw="REPORT",
        ternion_report_safe="REPORT",
        report_hash="hash",
        created_at="2026-01-11T00:00:00Z",
        updated_at="2026-01-11T00:00:00Z",
        workflow_phase="report_evidence",
    )


def _build_request(
    session_id: str, *, stream: bool, call_suffix: str = "c00"
) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="ternion-team",
        messages=[
            ChatMessage(
                role=MessageRole.TOOL,
                tool_call_id=f"ternion_{session_id}_r0001_{call_suffix}",
                content="RESULT",
            ),
        ],
        stream=stream,
    )


def _completed_final_state() -> dict:
    return {
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


def _patched_environment(mock_resume: AsyncMock, session: Session):
    mock_user_config = MagicMock()
    mock_user_config.execution_mode = "ternion_full"
    mock_user_config.show_phase_indicators = True
    mock_user_config.show_thinking_logs = False

    mock_config_store = patch("ternion.server.routes.config_store")
    mock_budget = patch("ternion.server.routes.budget_manager")
    mock_sessions = patch("ternion.server.routes.session_store")
    mock_workflow = patch(
        "ternion.workflow.graph.resume_report_evidence",
        mock_resume,
    )
    return mock_user_config, mock_config_store, mock_budget, mock_sessions, mock_workflow


class TestSessionTurnLockRelease:
    """The turn lock is always released once a turn fully completes."""

    async def test_non_streaming_turn_releases_lock(self):
        session = _build_session("aaaa11112222")
        request = _build_request(session.session_id, stream=False)
        mock_resume = AsyncMock(return_value=_completed_final_state())
        cfg, p_cfg, p_budget, p_sessions, p_wf = _patched_environment(mock_resume, session)

        with p_cfg as m_cfg, p_budget as m_budget, p_sessions as m_sessions, p_wf:
            m_cfg.load.return_value = cfg
            m_budget.check_budget.return_value = (True, None)
            m_sessions.update_session.return_value = session

            await handle_report_evidence_followup(session, request)

        assert get_session_lock(session.session_id).locked() is False

    async def test_streaming_turn_holds_lock_until_stream_consumed(self):
        session = _build_session("bbbb11112222")
        request = _build_request(session.session_id, stream=True)
        mock_resume = AsyncMock(return_value=_completed_final_state())
        cfg, p_cfg, p_budget, p_sessions, p_wf = _patched_environment(mock_resume, session)

        with p_cfg as m_cfg, p_budget as m_budget, p_sessions as m_sessions, p_wf:
            m_cfg.load.return_value = cfg
            m_budget.check_budget.return_value = (True, None)
            m_sessions.update_session.return_value = session

            resp = await handle_report_evidence_followup(session, request)
            assert isinstance(resp, StreamingResponse)
            # Lock ownership was handed off to the generator: still held.
            assert get_session_lock(session.session_id).locked() is True

            async for _chunk in resp.body_iterator:
                pass

        assert get_session_lock(session.session_id).locked() is False

    async def test_streaming_turn_releases_lock_when_stream_closed_early(self):
        session = _build_session("eeee11112222")
        request = _build_request(session.session_id, stream=True)
        mock_resume = AsyncMock(return_value=_completed_final_state())
        cfg, p_cfg, p_budget, p_sessions, p_wf = _patched_environment(mock_resume, session)

        with p_cfg as m_cfg, p_budget as m_budget, p_sessions as m_sessions, p_wf:
            m_cfg.load.return_value = cfg
            m_budget.check_budget.return_value = (True, None)
            m_sessions.update_session.return_value = session

            resp = await handle_report_evidence_followup(session, request)
            assert isinstance(resp, StreamingResponse)
            assert get_session_lock(session.session_id).locked() is True

            # Consume a single chunk, then close (client disconnect shape).
            iterator = resp.body_iterator
            await iterator.__anext__()
            await iterator.aclose()

        assert get_session_lock(session.session_id).locked() is False

    @pytest.mark.parametrize(
        ("handler", "inner_name"),
        [
            (handle_report_evidence_followup, "_report_evidence_followup_turn"),
            (handle_evidence_followup, "_evidence_followup_turn"),
            (handle_execution_followup, "_execution_followup_turn"),
        ],
    )
    async def test_wrapper_releases_lock_when_inner_turn_raises(self, handler, inner_name):
        session = _build_session("dddd11112222")
        request = _build_request(session.session_id, stream=False)

        with (
            patch(f"ternion.server.routes.{inner_name}", AsyncMock(side_effect=RuntimeError)),
            pytest.raises(RuntimeError),
        ):
            await handler(session, request)

        assert get_session_lock(session.session_id).locked() is False

    async def test_acquire_timeout_degrades_to_unlocked_turn(self):
        session = _build_session("ffff11112222")
        request = _build_request(session.session_id, stream=False)
        blocker = get_session_lock(session.session_id)
        await blocker.acquire()
        try:
            inner = AsyncMock(return_value="TURN_RESULT")
            with (
                patch.object(_SessionTurnLock, "_ACQUIRE_TIMEOUT_SECONDS", 0.05),
                patch("ternion.server.routes._report_evidence_followup_turn", inner),
            ):
                result = await asyncio.wait_for(
                    handle_report_evidence_followup(session, request), timeout=5
                )
        finally:
            blocker.release()

        # The turn completed without the lock instead of deadlocking, and the
        # degraded wrapper did not release the lock it never acquired.
        assert result == "TURN_RESULT"
        inner.assert_awaited_once()

    async def test_concurrent_turns_for_same_session_serialize(self):
        session = _build_session("cccc11112222")
        intervals: list[tuple[float, float]] = []

        async def slow_workflow(*args, **kwargs) -> dict:
            start = time.monotonic()
            await asyncio.sleep(0.05)
            intervals.append((start, time.monotonic()))
            return _completed_final_state()

        mock_resume = AsyncMock(side_effect=slow_workflow)
        cfg, p_cfg, p_budget, p_sessions, p_wf = _patched_environment(mock_resume, session)

        with p_cfg as m_cfg, p_budget as m_budget, p_sessions as m_sessions, p_wf:
            m_cfg.load.return_value = cfg
            m_budget.check_budget.return_value = (True, None)
            m_sessions.update_session.return_value = session

            await asyncio.gather(
                handle_report_evidence_followup(
                    session, _build_request(session.session_id, stream=False, call_suffix="c00")
                ),
                handle_report_evidence_followup(
                    session, _build_request(session.session_id, stream=False, call_suffix="c01")
                ),
            )

        assert len(intervals) == 2
        (start_a, end_a), (start_b, end_b) = sorted(intervals)
        # The second workflow segment must start only after the first ended.
        assert start_b >= end_a
        assert get_session_lock(session.session_id).locked() is False

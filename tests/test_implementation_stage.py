"""
Tests for the standalone implementation stage runner.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.workflow.implementation_stage import run_implementation_stage
from ternion.workflow.state import WorkflowPhase


@pytest.mark.asyncio
async def test_run_implementation_stage_missing_report_is_localized_with_browser_language() -> None:
    """Missing-field message should respect browser_language when language is 'auto'."""
    config = MagicMock()
    config.language = "auto"
    config.browser_language = "zh"

    with patch("ternion.utils.i18n._load_user_config") as mock_load_user_config:
        mock_load_user_config.return_value = config

        state = {
            "conversation_history": [{"role": "user", "content": "hi"}],
            # intentionally omit ternion_report
        }
        out = await run_implementation_stage(state)

        assert out["current_phase"] == WorkflowPhase.COMPLETE.value
        assert "实现阶段无法继续" in (out.get("final_output") or "")
        assert "ternion_report" in (out.get("final_output") or "")


@pytest.mark.asyncio
async def test_run_implementation_stage_supports_report_evidence_and_resumes_to_execution() -> None:
    """Implementation stage should run Phase 1.5 and resume back to execution."""
    state = {
        "ternion_report": "REPORT",
        "conversation_history": [{"role": "user", "content": "hi"}],
        "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
        "evidence_requests": "- [P0] path=foo.py:1-2",
        "report_evidence_resume_phase": WorkflowPhase.EXECUTION.value,
    }

    with (
        patch(
            "ternion.workflow.implementation_stage.report_evidence_node", new_callable=AsyncMock
        ) as mock_report_evidence,
        patch(
            "ternion.workflow.implementation_stage.execution_node", new_callable=AsyncMock
        ) as mock_execution,
    ):

        async def report_impl(s):  # type: ignore[no-untyped-def]
            return {**s, "current_phase": WorkflowPhase.EXECUTION.value}

        async def exec_impl(s):  # type: ignore[no-untyped-def]
            return {**s, "current_phase": WorkflowPhase.COMPLETE.value, "final_output": "DONE"}

        mock_report_evidence.side_effect = report_impl
        mock_execution.side_effect = exec_impl

        out = await run_implementation_stage(state)

    assert out.get("final_output") == "DONE"
    assert mock_report_evidence.await_count == 1
    assert mock_execution.await_count == 1


@pytest.mark.asyncio
async def test_run_implementation_stage_transitions_from_execution_to_report_evidence() -> None:
    """Execution node may request Phase 1.5; the runner must not terminate early."""
    state = {
        "ternion_report": "REPORT",
        "conversation_history": [{"role": "user", "content": "hi"}],
        "current_phase": WorkflowPhase.EXECUTION.value,
    }

    with (
        patch(
            "ternion.workflow.implementation_stage.execution_node", new_callable=AsyncMock
        ) as mock_execution,
        patch(
            "ternion.workflow.implementation_stage.report_evidence_node", new_callable=AsyncMock
        ) as mock_report_evidence,
    ):

        async def report_impl(s):  # type: ignore[no-untyped-def]
            return {**s, "current_phase": WorkflowPhase.EXECUTION.value}

        call_idx = {"n": 0}

        async def exec_impl(s):  # type: ignore[no-untyped-def]
            call_idx["n"] += 1
            if call_idx["n"] == 1:
                return {
                    **s,
                    "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                    "evidence_requests": "- [P0] path=foo.py:1-2\nPURPOSE: verify foo",
                    "report_evidence_resume_phase": WorkflowPhase.EXECUTION.value,
                }
            return {**s, "current_phase": WorkflowPhase.COMPLETE.value, "final_output": "DONE"}

        mock_execution.side_effect = exec_impl
        mock_report_evidence.side_effect = report_impl

        out = await run_implementation_stage(state)

    assert out.get("final_output") == "DONE"
    assert mock_report_evidence.await_count == 1
    assert mock_execution.await_count == 2


@pytest.mark.asyncio
async def test_run_implementation_stage_transitions_from_optimizer_to_report_evidence() -> None:
    """Optimizer node may request Phase 1.5; the runner must not terminate early."""
    state = {
        "ternion_report": "REPORT",
        "conversation_history": [{"role": "user", "content": "hi"}],
        "current_phase": WorkflowPhase.OPTIMIZER.value,
    }

    with (
        patch(
            "ternion.workflow.implementation_stage.optimizer_node", new_callable=AsyncMock
        ) as mock_optimizer,
        patch(
            "ternion.workflow.implementation_stage.report_evidence_node", new_callable=AsyncMock
        ) as mock_report_evidence,
    ):

        async def report_impl(s):  # type: ignore[no-untyped-def]
            return {**s, "current_phase": WorkflowPhase.OPTIMIZER.value}

        call_idx = {"n": 0}

        async def opt_impl(s):  # type: ignore[no-untyped-def]
            call_idx["n"] += 1
            if call_idx["n"] == 1:
                return {
                    **s,
                    "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                    "evidence_requests": "- [P0] path=bar.py:3-4\nPURPOSE: verify bar",
                    "report_evidence_resume_phase": WorkflowPhase.OPTIMIZER.value,
                }
            return {**s, "current_phase": WorkflowPhase.COMPLETE.value, "final_output": "DONE"}

        mock_optimizer.side_effect = opt_impl
        mock_report_evidence.side_effect = report_impl

        out = await run_implementation_stage(state)

    assert out.get("final_output") == "DONE"
    assert mock_report_evidence.await_count == 1
    assert mock_optimizer.await_count == 2

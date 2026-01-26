"""
Tests for the standalone implementation stage runner.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.workflow.implementation_stage import run_implementation_stage
from ternion.workflow.state import WorkflowPhase


@pytest.mark.asyncio
async def test_run_implementation_stage_missing_report_is_localized_with_browser_language():
    """Missing-field message should respect browser_language when language is 'auto'."""
    config = MagicMock()
    config.language = "auto"
    config.browser_language = "zh"

    with patch("ternion.utils.i18n.config_store") as mock_store:
        mock_store.load.return_value = config

        state = {
            "conversation_history": [{"role": "user", "content": "hi"}],
            # intentionally omit ternion_report
        }
        out = await run_implementation_stage(state)

        assert out["current_phase"] == WorkflowPhase.COMPLETE.value
        assert "实现阶段无法继续" in (out.get("final_output") or "")
        assert "ternion_report" in (out.get("final_output") or "")


@pytest.mark.asyncio
async def test_run_implementation_stage_supports_report_evidence_and_resumes_to_execution():
    """Implementation stage should run Phase 1.5 and resume back to execution."""
    state = {
        "ternion_report": "REPORT",
        "conversation_history": [{"role": "user", "content": "hi"}],
        "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
        "evidence_requests": "- [P0] path=foo.py:1-2",
        "report_evidence_resume_phase": WorkflowPhase.EXECUTION.value,
    }

    with (
        patch("ternion.workflow.implementation_stage.report_evidence_node", new_callable=AsyncMock) as mock_report_evidence,
        patch("ternion.workflow.implementation_stage.execution_node", new_callable=AsyncMock) as mock_execution,
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


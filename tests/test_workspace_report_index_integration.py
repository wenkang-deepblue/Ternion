"""Workflow integration tests for D3 historical report candidates."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.core.config_store import RoleConfig
from ternion.core.models import ChatMessage
from ternion.core.report_index import WorkspaceReportIndex
from ternion.core.session_store import compute_report_hash
from ternion.utils.evidence_repository import EvidenceRepository, build_evidence_item
from ternion.workflow.state import WorkflowPhase

REPORT = """## Root Cause
- The request routing boundary drops the active session state.

## Evidence / Logs
- Current routing evidence was collected.

## Scope & Non-Goals
- Historical conclusions remain hypotheses.

## Fix Plan / Recommendation
- Preserve state across the routing boundary.

## Verification
- Run focused routing tests.

## Risks & Rollback
- Fall back to fresh evidence collection.

## If not effective, then what?
- Inspect the next boundary.
"""

ANALYSIS = """### 1. Intent & Reality Gap
- The current request asks about routing state.

### 2. Critical Analysis (The Why / Trade-offs)
- Current evidence remains authoritative.

### 3. Evidence vs. Assumptions (Uncertainty Management)
- Evidence: src/routes.py:1-2.

### 4. Root Cause Hypothesis / Best Approach
- Most likely root cause: the verified routing boundary.

### 5. evidence_requests (Required)
- [P0] None
"""


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "routes.py").write_text(
        "def route(session):\n    return session\n",
        encoding="utf-8",
    )
    return workspace


def _records() -> list[dict]:
    return EvidenceRepository(
        items=[
            build_evidence_item(
                path="src/routes.py",
                lines="1-2",
                excerpt="def route(session):\n    return session",
                purpose="Verify the request routing boundary.",
            )
        ]
    ).to_records()


@pytest.mark.asyncio
async def test_divergence_receives_similar_reports_as_hypotheses_only(tmp_path: Path) -> None:
    from ternion.workflow.nodes import divergence_node

    workspace = _workspace(tmp_path)
    report_index = WorkspaceReportIndex(index_dir=tmp_path / "report-indexes")
    assert report_index.store_report(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        evidence_records=_records(),
        report=REPORT,
        query="Trace request routing session state",
        session_id="historical-session",
        report_hash=compute_report_hash(REPORT),
    )
    adapter = AsyncMock()
    adapter.name = "openai"
    adapter.chat_completion.return_value = MagicMock(content=ANALYSIS, usage={})
    evidence_bundle = EvidenceRepository.from_records(_records()).render_bundle()
    state = {
        "conversation_history": [
            {"role": "user", "content": "Investigate request routing session state"}
        ],
        "workspace_root": str(workspace),
        "local_workspace_root": str(workspace),
        "workspace_path_style": "posix",
        "session_id": "",
        "evidence_bundle": evidence_bundle,
        "evidence_items": _records(),
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "thinking_logs": [],
        "errors": [],
    }

    with (
        patch("ternion.workflow.nodes.workspace_report_index", report_index),
        patch("ternion.workflow.nodes.config_store") as mock_config_store,
        patch("ternion.workflow.nodes.provider_manager") as mock_provider_manager,
    ):
        mock_config_store.get_role_config.side_effect = lambda _role: RoleConfig(
            provider="openai",
            model="gpt-test",
        )
        mock_provider_manager.get_provider.return_value = adapter
        result = await divergence_node(state)

    assert result["current_phase"] == WorkflowPhase.REPORT_EVIDENCE.value
    assert len(result["ternion_analyses"]) == 3
    assert adapter.chat_completion.await_count == 3
    for call in adapter.chat_completion.await_args_list:
        messages: list[ChatMessage] = call.kwargs["messages"]
        system_prompt = str(messages[0].content or "")
        assert "is not evidence" in system_prompt
        assert "historical_root_cause=" not in system_prompt
        historical_prompt = str(messages[1].content or "")
        assert "[WORKSPACE_HISTORICAL_REPORT_CANDIDATES - HYPOTHESES ONLY]" in historical_prompt
        assert "never cite them as evidence" in historical_prompt
        assert "source_state=current" in historical_prompt
        assert "historical_root_cause=" in historical_prompt
        assert "def route(session):" not in historical_prompt

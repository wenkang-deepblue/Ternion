"""Workflow and routing integration tests for Phase D2 project profiles."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.core.config_store import RoleConfig
from ternion.core.models import ChatMessage, MessageRole
from ternion.core.project_profile import WorkspaceProjectProfile
from ternion.utils.evidence_repository import EvidenceRepository, build_evidence_item
from ternion.workflow.state import WorkflowPhase

REPORT = """## Root Cause
- The current application entrypoint delegates request handling.

## Evidence / Logs
- The entrypoint was collected.

## Scope & Non-Goals
- Navigation profile only.

## Fix Plan / Recommendation
- Keep fresh evidence authoritative.

## Verification
- Verify the source hash.

## Risks & Rollback
- Remove stale observations.

## If not effective, then what?
- Use normal evidence discovery.
"""


def _records() -> list[dict]:
    return EvidenceRepository(
        items=[
            build_evidence_item(
                path="src/app.py",
                lines="1-2",
                excerpt="def run():\n    return 'ok'",
                purpose="Verify the application entrypoint.",
            )
        ]
    ).to_records()


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.py").write_text(
        "def run():\n    return 'ok'\n",
        encoding="utf-8",
    )
    return workspace


@pytest.mark.asyncio
async def test_phase_zero_receives_profile_as_navigation_not_evidence(tmp_path: Path) -> None:
    from ternion.workflow.nodes import evidence_node

    workspace = _workspace(tmp_path)
    profile = WorkspaceProjectProfile(profile_dir=tmp_path / "profiles")
    assert profile.store_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        evidence_records=_records(),
        report=REPORT,
        query="Understand request routing",
    )
    adapter = AsyncMock()
    adapter.name = "openai"
    adapter.supports_native_tool_calls = True
    adapter.chat_completion.return_value = MagicMock(
        content=(
            "EVIDENCE_BUNDLE:\n"
            "- [FILE_EXCERPT] path=src/app.py | lines=1-2\n"
            "  PURPOSE: Verify current behavior.\n"
            "  EXCERPT_BEGIN\n"
            "  def run():\n"
            "      return 'ok'\n"
            "  EXCERPT_END\n\n"
            "EVIDENCE_GAPS:\n"
            "- None"
        ),
        tool_calls=None,
        usage={},
    )
    state = {
        "conversation_history": [{"role": "user", "content": "Inspect routing"}],
        "session_id": "",
        "workspace_root": str(workspace),
        "local_workspace_root": str(workspace),
        "workspace_path_style": "posix",
        "cursor_tools": [{"type": "function", "function": {"name": "read_file"}}],
        "cursor_tool_choice": "auto",
        "thinking_logs": [],
        "errors": [],
    }

    with (
        patch("ternion.workflow.nodes.workspace_project_profile", profile),
        patch("ternion.workflow.nodes.config_store") as mock_config_store,
        patch("ternion.workflow.nodes.provider_manager") as mock_provider_manager,
    ):
        mock_config_store.get_role_config.return_value = RoleConfig(
            provider="openai", model="gpt-test"
        )
        mock_provider_manager.get_provider_for_role.return_value = adapter
        result = await evidence_node(state)

    messages: list[ChatMessage] = adapter.chat_completion.call_args.kwargs["messages"]
    assert "PROJECT PROFILE IS NAVIGATION ONLY" in str(messages[0].content or "")
    profile_messages = [
        str(message.content or "")
        for message in messages
        if message.role == MessageRole.USER
        and "[WORKSPACE_PROJECT_PROFILE - NAVIGATION ONLY]" in str(message.content or "")
    ]
    assert len(profile_messages) == 1
    assert "NEVER copy profile conclusions into EVIDENCE_BUNDLE" in profile_messages[0]
    assert "src/app.py" in profile_messages[0]
    assert "def run():" not in profile_messages[0]
    assert result["current_phase"] == WorkflowPhase.DIVERGENCE.value
    assert "prior_orientation" not in result["evidence_bundle"]


@pytest.mark.asyncio
async def test_convergence_persists_current_profile_for_later_sessions(tmp_path: Path) -> None:
    from ternion.workflow.nodes import convergence_node

    workspace = _workspace(tmp_path)
    profile = WorkspaceProjectProfile(profile_dir=tmp_path / "profiles")
    user_config = MagicMock()
    user_config.language = "en"
    user_config.browser_language = "en"
    user_config.execution_mode = "cursor_handoff"
    provider = MagicMock(name="provider")
    provider.name = "openai"
    response = MagicMock(content=REPORT, usage={})
    session = MagicMock(
        session_id="session-d2",
        report_hash="report-hash",
        ternion_report_raw=REPORT,
    )
    state = {
        "conversation_history": [{"role": "user", "content": "Trace request routing"}],
        "current_phase": WorkflowPhase.CONVERGENCE.value,
        "session_id": "",
        "await_confirmation": True,
        "execution_mode": "cursor_handoff",
        "workspace_root": str(workspace),
        "local_workspace_root": str(workspace),
        "workspace_path_style": "posix",
        "workspace_root_source": "request",
        "evidence_bundle": EvidenceRepository.from_records(_records()).render_bundle(),
        "evidence_items": _records(),
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "evidence_requests": "",
        "evidence_chain_index": [],
        "ternion_analyses": [
            {"ternion_id": "ternion_a", "analysis": "Grounded analysis", "error": None}
        ],
        "thinking_logs": [],
        "errors": [],
    }

    with (
        patch("ternion.workflow.nodes.workspace_project_profile", profile),
        patch("ternion.workflow.nodes._call_with_stream", new=AsyncMock(return_value=response)),
        patch("ternion.workflow.nodes.config_store") as mock_config_store,
        patch("ternion.workflow.nodes.provider_manager") as mock_provider_manager,
        patch("ternion.workflow.nodes.session_store") as mock_session_store,
    ):
        mock_config_store.load.return_value = user_config
        mock_config_store.get_role_config.return_value = RoleConfig(
            provider="openai", model="gpt-test"
        )
        mock_provider_manager.get_provider_for_role.return_value = provider
        mock_session_store.create_session.return_value = session
        result = await convergence_node(state)

    lookup = profile.load_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
    )
    assert result["session_id"] == "session-d2"
    assert lookup.observation_count == 1
    assert "Trace request routing" in lookup.prompt
    assert "current application entrypoint" in lookup.prompt


@pytest.mark.asyncio
async def test_mutation_invalidation_covers_evidence_cache_and_project_profile() -> None:
    from ternion.server.routes import _invalidate_workspace_evidence_after_tool_result

    with (
        patch("ternion.server.routes.workspace_evidence_cache") as evidence_cache,
        patch("ternion.server.routes.workspace_project_profile") as project_profile,
    ):
        evidence_cache.invalidate_paths.return_value = 1
        project_profile.invalidate_paths.return_value = 1
        await _invalidate_workspace_evidence_after_tool_result(
            canonical_tool="write",
            tool_name="Write",
            tool_arguments='{"path":"src/app.py"}',
            workspace_root="/repo",
            workspace_path_style="posix",
        )
        evidence_cache.invalidate_paths.assert_called_once_with(
            workspace_root="/repo",
            workspace_path_style="posix",
            paths=["src/app.py"],
        )
        project_profile.invalidate_paths.assert_called_once_with(
            workspace_root="/repo",
            workspace_path_style="posix",
            paths=["src/app.py"],
        )

        await _invalidate_workspace_evidence_after_tool_result(
            canonical_tool="shell",
            tool_name="Shell",
            tool_arguments='{"command":"ruff format src"}',
            workspace_root="/repo",
            workspace_path_style="posix",
            shell_may_write=True,
        )
        evidence_cache.invalidate_workspace.assert_called_once_with(
            workspace_root="/repo",
            workspace_path_style="posix",
        )
        project_profile.invalidate_workspace.assert_called_once_with(
            workspace_root="/repo",
            workspace_path_style="posix",
        )

        evidence_cache.reset_mock()
        project_profile.reset_mock()
        await _invalidate_workspace_evidence_after_tool_result(
            canonical_tool="shell",
            tool_name="Shell",
            tool_arguments='{"command":"git status --short"}',
            workspace_root="/repo",
            workspace_path_style="posix",
            shell_may_write=False,
        )
        await _invalidate_workspace_evidence_after_tool_result(
            canonical_tool="readfile",
            tool_name="ReadFile",
            tool_arguments='{"path":"src/app.py"}',
            workspace_root="/repo",
            workspace_path_style="posix",
        )
        evidence_cache.invalidate_paths.assert_not_called()
        evidence_cache.invalidate_workspace.assert_not_called()
        project_profile.invalidate_paths.assert_not_called()
        project_profile.invalidate_workspace.assert_not_called()

"""Workflow and routing integration tests for Phase D1 evidence reuse."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.core.config_store import RoleConfig
from ternion.core.evidence_cache import WorkspaceEvidenceCache
from ternion.core.models import ChatMessage, MessageRole
from ternion.utils.evidence_repository import EvidenceRepository, build_evidence_item
from ternion.workflow.state import WorkflowPhase


def _records(path: str, lines: str, excerpt: str, purpose: str) -> list[dict[str, Any]]:
    return EvidenceRepository(
        items=[
            build_evidence_item(
                path=path,
                lines=lines,
                purpose=purpose,
                excerpt=excerpt,
            )
        ]
    ).to_records()


def _seed_cache(tmp_path: Path) -> tuple[Path, WorkspaceEvidenceCache]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "foo.py").write_text("alpha\nbeta\n", encoding="utf-8")
    cache = WorkspaceEvidenceCache(cache_dir=tmp_path / "cache")
    assert (
        cache.store_records(
            workspace_root=str(workspace),
            local_workspace_root=str(workspace),
            records=_records("foo.py", "1-2", "alpha\nbeta", "Prior verified purpose."),
            session_id="prior-session",
            phase="evidence",
        )
        == 1
    )
    return workspace, cache


@pytest.mark.asyncio
async def test_phase_zero_receives_revalidated_cross_session_evidence(tmp_path: Path) -> None:
    from ternion.workflow.nodes import evidence_node

    workspace, cache = _seed_cache(tmp_path)
    adapter = AsyncMock()
    adapter.name = "openai"
    adapter.supports_native_tool_calls = True
    adapter.chat_completion.return_value = MagicMock(
        content=(
            "EVIDENCE_BUNDLE:\n"
            "- [FILE_EXCERPT] path=foo.py | lines=1-2\n"
            "  PURPOSE: Verify the current implementation.\n"
            "  EXCERPT_BEGIN\n"
            "  alpha\n"
            "  beta\n"
            "  EXCERPT_END\n\n"
            "EVIDENCE_GAPS:\n"
            "- None"
        ),
        tool_calls=None,
        usage={},
    )
    state = {
        "conversation_history": [{"role": "user", "content": "Inspect foo.py"}],
        "session_id": "",
        "workspace_root": str(workspace),
        "local_workspace_root": str(workspace),
        "workspace_path_style": "posix",
        "cursor_tools": [{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
        "cursor_tool_choice": "auto",
        "thinking_logs": [],
        "errors": [],
    }

    with (
        patch("ternion.workflow.nodes.workspace_evidence_cache", cache),
        patch("ternion.workflow.nodes.config_store") as mock_config_store,
        patch("ternion.workflow.nodes.provider_manager") as mock_provider_manager,
    ):
        mock_config_store.get_role_config.return_value = RoleConfig(
            provider="openai", model="gpt-test"
        )
        mock_provider_manager.get_provider_for_role.return_value = adapter
        result = await evidence_node(state)

    messages: list[ChatMessage] = adapter.chat_completion.call_args.kwargs["messages"]
    cache_messages = [
        str(message.content or "")
        for message in messages
        if message.role == MessageRole.USER
        and "[CROSS_SESSION_EVIDENCE_CACHE" in str(message.content or "")
    ]
    assert len(cache_messages) == 1
    assert "path=foo.py | lines=1-2" in cache_messages[0]
    assert result["current_phase"] == WorkflowPhase.DIVERGENCE.value
    assert "path=foo.py" in result["evidence_bundle"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "evidence_request",
    [
        "- [P0] path=foo.py:1-2\nPURPOSE: Verify requested lines.",
        "- [P0] path=foo.py\nPURPOSE: Verify the complete file.",
        (
            "- [P0] path=foo.py:1-2\nPURPOSE: Verify requested lines.\n"
            "- [P0] path=foo.py:1-2\nPURPOSE: Verify requested lines."
        ),
    ],
)
async def test_phase_one_five_cache_hit_skips_tool_and_provider_rounds(
    tmp_path: Path,
    evidence_request: str,
) -> None:
    from ternion.workflow.nodes import report_evidence_node

    workspace, cache = _seed_cache(tmp_path)
    state = {
        "conversation_history": [{"role": "user", "content": "Inspect foo.py"}],
        "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
        "session_id": "current-session",
        "workspace_root": str(workspace),
        "local_workspace_root": str(workspace),
        "workspace_path_style": "posix",
        "cursor_tools": [{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
        "cursor_tool_choice": "auto",
        "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
        "evidence_items": [],
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "evidence_requests": evidence_request,
        "thinking_logs": [],
        "errors": [],
    }

    with (
        patch("ternion.workflow.nodes.workspace_evidence_cache", cache),
        patch("ternion.workflow.nodes.config_store") as mock_config_store,
        patch("ternion.workflow.nodes.provider_manager") as mock_provider_manager,
    ):
        mock_config_store.get_role_config.return_value = RoleConfig(
            provider="openai", model="gpt-test"
        )
        result = await report_evidence_node(state)

    assert result["current_phase"] == WorkflowPhase.CONVERGENCE.value
    assert not result.get("pending_tool_calls")
    assert result["evidence_chain_index"][0]["satisfied"] is True
    assert "Verify requested lines." in result["evidence_bundle"] or (
        "Verify the complete file." in result["evidence_bundle"]
    )
    mock_provider_manager.get_provider_for_role.assert_not_called()


@pytest.mark.asyncio
async def test_phase_one_five_injects_only_request_relevant_cached_ranges(
    tmp_path: Path,
) -> None:
    from ternion.workflow.nodes import report_evidence_node

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "foo.py").write_text("alpha\nbeta\ngamma\ndelta\n", encoding="utf-8")
    cache = WorkspaceEvidenceCache(cache_dir=tmp_path / "cache")
    assert (
        cache.store_records(
            workspace_root=str(workspace),
            local_workspace_root=str(workspace),
            records=[
                *_records("foo.py", "1-1", "alpha", "Relevant range."),
                *_records("foo.py", "4-4", "delta", "Unrelated range."),
            ],
            session_id="prior-session",
            phase="evidence",
        )
        == 1
    )
    state = {
        "conversation_history": [{"role": "user", "content": "Inspect line one"}],
        "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
        "session_id": "current-session",
        "workspace_root": str(workspace),
        "local_workspace_root": str(workspace),
        "workspace_path_style": "posix",
        "cursor_tools": [{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
        "cursor_tool_choice": "auto",
        "evidence_bundle": "EVIDENCE_BUNDLE:\n- None",
        "evidence_items": [],
        "evidence_gaps": "EVIDENCE_GAPS:\n- None",
        "evidence_requests": "- [P0] path=foo.py:1-1\nPURPOSE: Verify line one.",
        "thinking_logs": [],
        "errors": [],
    }

    with (
        patch("ternion.workflow.nodes.workspace_evidence_cache", cache),
        patch("ternion.workflow.nodes.config_store") as mock_config_store,
        patch("ternion.workflow.nodes.provider_manager") as mock_provider_manager,
    ):
        mock_config_store.get_role_config.return_value = RoleConfig(
            provider="openai", model="gpt-test"
        )
        result = await report_evidence_node(state)

    assert result["current_phase"] == WorkflowPhase.CONVERGENCE.value
    assert "alpha" in result["evidence_bundle"]
    assert "delta" not in result["evidence_bundle"]
    assert "Unrelated range." not in result["evidence_bundle"]
    mock_provider_manager.get_provider_for_role.assert_not_called()


def test_mutation_results_invalidate_path_and_write_capable_shell_invalidates_workspace() -> None:
    from ternion.server.routes import _invalidate_workspace_evidence_after_tool_result

    with patch("ternion.server.routes.workspace_evidence_cache") as cache:
        cache.invalidate_paths.return_value = 1
        _invalidate_workspace_evidence_after_tool_result(
            canonical_tool="write",
            tool_name="Write",
            tool_arguments='{"path":"src/app.py"}',
            workspace_root="/repo",
            workspace_path_style="posix",
        )
        cache.invalidate_paths.assert_called_once_with(
            workspace_root="/repo",
            workspace_path_style="posix",
            paths=["src/app.py"],
        )

        _invalidate_workspace_evidence_after_tool_result(
            canonical_tool="shell",
            tool_name="Shell",
            tool_arguments='{"command":"ruff format src"}',
            workspace_root="/repo",
            workspace_path_style="posix",
            shell_may_write=True,
        )
        cache.invalidate_workspace.assert_called_once_with(
            workspace_root="/repo",
            workspace_path_style="posix",
        )

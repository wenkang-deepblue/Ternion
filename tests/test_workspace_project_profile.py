"""Tests for the D2 workspace project-profile store."""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

from ternion.core.project_profile import WorkspaceProjectProfile
from ternion.utils.evidence_repository import EvidenceRepository, build_evidence_item

REPORT = """## Root Cause
- The request is routed through the application entrypoint and service layer.
- Confidence: High because both modules were collected as evidence.

## Evidence / Logs
- Current files were inspected.

## Scope & Non-Goals
- Navigation only.

## Fix Plan / Recommendation
- Keep discovery narrow.

## Verification
- Verify current files.

## Risks & Rollback
- Stale paths must be rejected.

## If not effective, then what?
- Collect fresh evidence.
"""


def _records(
    *items: tuple[str, str, str, str],
) -> list[dict]:
    return EvidenceRepository(
        items=[
            build_evidence_item(
                path=path,
                lines=lines,
                excerpt=excerpt,
                purpose=purpose,
            )
            for path, lines, excerpt, purpose in items
        ]
    ).to_records()


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "src" / "core").mkdir(parents=True)
    (workspace / "src" / "app.py").write_text("from core import service\nrun()\n", encoding="utf-8")
    (workspace / "src" / "core" / "service.py").write_text(
        "def handle():\n    return 'ok'\n",
        encoding="utf-8",
    )
    return workspace


def _profile_records() -> list[dict]:
    return _records(
        (
            "src/app.py",
            "1-2",
            "from core import service\nrun()",
            "Verify the application entrypoint.",
        ),
        (
            "src/core/service.py",
            "1-2",
            "def handle():\n    return 'ok'",
            "Verify the key service module.",
        ),
    )


def test_store_and_load_render_current_navigation_without_excerpts(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    profile_dir = tmp_path / "profiles"
    profile = WorkspaceProjectProfile(profile_dir=profile_dir)

    stored = profile.store_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        evidence_records=_profile_records(),
        report=REPORT,
        query="Trace request routing",
        session_id="session-a",
    )
    lookup = profile.load_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
    )

    assert stored is True
    assert lookup.observation_count == 1
    assert lookup.source_paths == ("src/app.py", "src/core/service.py")
    assert "PROJECT_DIRECTORIES:" in lookup.prompt
    assert "src/core" in lookup.prompt
    assert "ENTRYPOINT_CANDIDATES:" in lookup.prompt
    assert "src/app.py" in lookup.prompt
    assert "Trace request routing" in lookup.prompt
    assert "request is routed through the application entrypoint" in lookup.prompt
    assert "from core import service" not in lookup.prompt
    assert "return 'ok'" not in lookup.prompt

    manifest_path = next(profile_dir.glob("*.json.gz"))
    with gzip.open(manifest_path, "rt", encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert len(manifest["sources"]["src/app.py"]["content_hash"]) == 64
    if os.name == "posix":
        assert profile_dir.stat().st_mode & 0o777 == 0o700
        assert manifest_path.stat().st_mode & 0o777 == 0o600


def test_changed_source_drops_dependent_observation_fail_closed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    profile_dir = tmp_path / "profiles"
    profile = WorkspaceProjectProfile(profile_dir=profile_dir)
    assert profile.store_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        evidence_records=_profile_records(),
        report=REPORT,
    )

    (workspace / "src" / "app.py").write_text("changed\n", encoding="utf-8")
    lookup = profile.load_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
    )

    assert lookup.prompt == ""
    assert lookup.stale_paths == ("src/app.py",)
    assert lookup.skipped_reason == "no_current_observations"
    assert list(profile_dir.glob("*.json.gz")) == []


def test_unverifiable_workspace_and_mismatched_excerpt_are_not_persisted(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    profile = WorkspaceProjectProfile(profile_dir=tmp_path / "profiles")

    assert not profile.store_profile(
        workspace_root=str(workspace),
        local_workspace_root="",
        evidence_records=_profile_records(),
        report=REPORT,
    )
    assert not profile.store_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        evidence_records=_records(
            ("src/app.py", "1-1", "fabricated", "Unverified source."),
        ),
        report=REPORT,
    )
    lookup = profile.load_profile(
        workspace_root=str(workspace),
        local_workspace_root="",
    )
    assert lookup.skipped_reason == "local_workspace_unavailable"


def test_unstructured_degraded_report_is_not_persisted(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    profile = WorkspaceProjectProfile(profile_dir=tmp_path / "profiles")

    assert not profile.store_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        evidence_records=_profile_records(),
        report="Raw council analysis without the structured report contract.",
    )


def test_duplicate_observation_is_replaced_and_oldest_is_pruned(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    profile = WorkspaceProjectProfile(
        profile_dir=tmp_path / "profiles",
        max_observations=2,
    )
    for query in ("first", "first", "second", "third"):
        assert profile.store_profile(
            workspace_root=str(workspace),
            local_workspace_root=str(workspace),
            evidence_records=_profile_records(),
            report=REPORT,
            query=query,
        )

    lookup = profile.load_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
    )

    assert lookup.observation_count == 2
    assert "query=third" in lookup.prompt
    assert "query=second" in lookup.prompt
    assert "query=first" not in lookup.prompt


def test_workspace_source_cap_prefers_the_newest_observation(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    profile = WorkspaceProjectProfile(
        profile_dir=tmp_path / "profiles",
        max_sources=1,
        max_observations=3,
    )
    assert profile.store_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        evidence_records=_records(
            (
                "src/app.py",
                "1-2",
                "from core import service\nrun()",
                "Verify the application entrypoint.",
            )
        ),
        report=REPORT,
        query="older",
    )
    assert profile.store_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        evidence_records=_records(
            (
                "src/core/service.py",
                "1-2",
                "def handle():\n    return 'ok'",
                "Verify the service layer.",
            )
        ),
        report=REPORT,
        query="newer",
    )

    lookup = profile.load_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
    )
    assert lookup.source_paths == ("src/core/service.py",)
    assert lookup.observation_count == 1
    assert "query=newer" in lookup.prompt
    assert "query=older" not in lookup.prompt


def test_path_and_workspace_invalidation_remove_current_profile(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    profile = WorkspaceProjectProfile(profile_dir=tmp_path / "profiles")
    assert profile.store_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        evidence_records=_profile_records(),
        report=REPORT,
    )

    removed = profile.invalidate_paths(
        workspace_root=str(workspace),
        paths=["src/app.py"],
    )
    assert removed == 1
    assert (
        profile.load_profile(
            workspace_root=str(workspace),
            local_workspace_root=str(workspace),
        ).prompt
        == ""
    )

    assert profile.store_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        evidence_records=_profile_records(),
        report=REPORT,
    )
    assert profile.invalidate_workspace(workspace_root=str(workspace)) is True
    assert profile.invalidate_workspace(workspace_root=str(workspace)) is False


def test_rendered_profile_is_bounded(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    profile = WorkspaceProjectProfile(
        profile_dir=tmp_path / "profiles",
        max_prompt_chars=700,
    )
    for index in range(3):
        assert profile.store_profile(
            workspace_root=str(workspace),
            local_workspace_root=str(workspace),
            evidence_records=_profile_records(),
            report=REPORT,
            query=f"request-{index}-" + ("x" * 160),
        )

    lookup = profile.load_profile(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
    )
    assert 0 < len(lookup.prompt) <= 700

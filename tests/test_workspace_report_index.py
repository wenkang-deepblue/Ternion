"""Tests for the D3 workspace historical-report index."""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

import pytest

import ternion.core.report_index as report_index_module
from ternion.core.report_index import WorkspaceReportIndex
from ternion.core.session_store import compute_report_hash
from ternion.utils.evidence_repository import EvidenceRepository, build_evidence_item


def _report(root_cause: str = "Request routing loses the active session state.") -> str:
    return f"""## Root Cause
- {root_cause}

## Evidence / Logs
- Current routing files were inspected.

## Scope & Non-Goals
- Historical reports remain hypotheses.

## Fix Plan / Recommendation
- Preserve the session state across the routing boundary.

## Verification
- Re-run the focused routing tests.

## Risks & Rollback
- Fall back to fresh evidence collection.

## If not effective, then what?
- Inspect the next request boundary.
"""


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "routes.py").write_text(
        "def route(session):\n    return session\n",
        encoding="utf-8",
    )
    return workspace


def _records(excerpt: str = "def route(session):\n    return session") -> list[dict]:
    return EvidenceRepository(
        items=[
            build_evidence_item(
                path="src/routes.py",
                lines="1-2",
                excerpt=excerpt,
                purpose="Verify the request routing boundary.",
            )
        ]
    ).to_records()


def _store(
    index: WorkspaceReportIndex,
    workspace: Path,
    *,
    query: str = "Trace request routing session state",
    report: str | None = None,
    session_id: str = "session-a",
) -> bool:
    report_text = report or _report()
    return index.store_report(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        evidence_records=_records(),
        report=report_text,
        query=query,
        session_id=session_id,
        report_hash=compute_report_hash(report_text),
    )


def test_store_and_exact_lookup_render_current_hypothesis_without_excerpts(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    index_dir = tmp_path / "report-indexes"
    index = WorkspaceReportIndex(index_dir=index_dir)
    report = _report()

    assert _store(index, workspace, report=report)
    lookup = index.find_similar_reports(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        query="Trace request routing session state",
    )

    assert lookup.candidate_count == 1
    assert lookup.current_count == 1
    assert lookup.stale_count == 0
    assert lookup.candidate_session_ids == ("session-a",)
    assert "source_state=current" in lookup.prompt
    assert f"report_hash={compute_report_hash(report)}" in lookup.prompt
    assert "historical_root_cause=Request routing loses the active session state." in lookup.prompt
    assert "def route(session):" not in lookup.prompt
    assert "return session" not in lookup.prompt

    manifest_path = next(index_dir.glob("*.json.gz"))
    with gzip.open(manifest_path, "rt", encoding="utf-8") as handle:
        manifest = json.load(handle)
    entry = manifest["entries"][0]
    assert entry["session_id"] == "session-a"
    assert entry["report_hash"] == compute_report_hash(report)
    assert len(entry["source_files"][0]["content_hash"]) == 64
    assert "excerpt" not in json.dumps(entry)
    if os.name == "posix":
        assert index_dir.stat().st_mode & 0o777 == 0o700
        assert manifest_path.stat().st_mode & 0o777 == 0o600


def test_similarity_matches_related_queries_and_rejects_unrelated_queries(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    index = WorkspaceReportIndex(index_dir=tmp_path / "report-indexes")
    assert _store(index, workspace, query="Trace request routing through the session service")

    related = index.find_similar_reports(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        query="Investigate session service request routing behavior",
    )
    unrelated = index.find_similar_reports(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        query="Review database migration schema constraints",
    )

    assert related.candidate_count == 1
    assert unrelated.candidate_count == 0
    assert unrelated.skipped_reason == "no_similar_reports"


def test_similarity_supports_chinese_queries_without_vector_dependencies(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    index = WorkspaceReportIndex(index_dir=tmp_path / "report-indexes")
    assert _store(index, workspace, query="修复请求路由中的会话状态错误")

    lookup = index.find_similar_reports(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        query="调查请求路由会话状态异常",
    )

    assert lookup.candidate_count == 1
    assert "prior_query=修复请求路由中的会话状态错误" in lookup.prompt


def test_changed_source_is_retained_and_labeled_stale(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    index_dir = tmp_path / "report-indexes"
    index = WorkspaceReportIndex(index_dir=index_dir)
    assert _store(index, workspace)
    (workspace / "src" / "routes.py").write_text(
        "def route(session):\n    return None\n",
        encoding="utf-8",
    )

    lookup = index.find_similar_reports(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        query="Trace request routing session state",
    )

    assert lookup.candidate_count == 1
    assert lookup.current_count == 0
    assert lookup.stale_count == 1
    assert "source_state=stale" in lookup.prompt
    assert "stale_or_missing_paths=src/routes.py" in lookup.prompt
    with gzip.open(next(index_dir.glob("*.json.gz")), "rt", encoding="utf-8") as handle:
        assert len(json.load(handle)["entries"]) == 1


def test_store_rejects_unstructured_hash_mismatch_and_unverified_sources(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    index = WorkspaceReportIndex(index_dir=tmp_path / "report-indexes")

    assert not index.store_report(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        evidence_records=_records(),
        report="Unstructured report",
        query="Trace request routing",
        session_id="session-a",
    )
    assert not index.store_report(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        evidence_records=_records(),
        report=_report(),
        query="Trace request routing",
        session_id="session-a",
        report_hash="0000000000000000",
    )
    assert not index.store_report(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        evidence_records=_records("forged excerpt\nthat does not match"),
        report=_report(),
        query="Trace request routing",
        session_id="session-a",
    )


def test_duplicate_replacement_and_oldest_entry_pruning(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    index_dir = tmp_path / "report-indexes"
    index = WorkspaceReportIndex(index_dir=index_dir, max_entries=2)
    assert _store(index, workspace)
    assert _store(index, workspace)
    with gzip.open(next(index_dir.glob("*.json.gz")), "rt", encoding="utf-8") as handle:
        assert len(json.load(handle)["entries"]) == 1

    assert _store(
        index,
        workspace,
        query="Trace request routing state transition",
        report=_report("The first state transition is incomplete."),
        session_id="session-b",
    )
    assert _store(
        index,
        workspace,
        query="Trace request routing response transition",
        report=_report("The response transition is incomplete."),
        session_id="session-c",
    )
    with gzip.open(next(index_dir.glob("*.json.gz")), "rt", encoding="utf-8") as handle:
        entries = json.load(handle)["entries"]
    assert len(entries) == 2
    assert [entry["session_id"] for entry in entries] == ["session-b", "session-c"]


def test_candidate_count_and_prompt_size_are_bounded(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    index = WorkspaceReportIndex(
        index_dir=tmp_path / "report-indexes",
        max_candidates=2,
        max_prompt_chars=2_500,
        similarity_threshold=0.1,
    )
    for number in range(4):
        assert _store(
            index,
            workspace,
            query=f"Trace request routing session state variant {number}",
            report=_report(f"Routing state variant {number} is incomplete. " + ("detail " * 80)),
            session_id=f"session-{number}",
        )

    lookup = index.find_similar_reports(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        query="Trace request routing session state",
    )

    assert 0 < lookup.candidate_count <= 2
    assert len(lookup.prompt) <= 2_500


def test_lookup_computes_current_query_terms_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path)
    index = WorkspaceReportIndex(
        index_dir=tmp_path / "report-indexes",
        similarity_threshold=0.1,
    )
    assert _store(index, workspace, query="Trace request routing state variant alpha")
    assert _store(index, workspace, query="Trace request routing state variant beta")

    current_query = "Investigate request routing session behavior"
    original_query_terms = report_index_module._query_terms
    calls: list[str] = []

    def counting_query_terms(value: str) -> set[str]:
        calls.append(value)
        return original_query_terms(value)

    monkeypatch.setattr(report_index_module, "_query_terms", counting_query_terms)
    lookup = index.find_similar_reports(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        query=current_query,
    )

    assert lookup.candidate_count == 2
    assert calls.count(current_query) == 1


def test_single_candidate_prompt_truncates_only_at_line_boundary() -> None:
    candidate = {
        "session_id": "session-a",
        "report_hash": "a" * 16,
        "observed_at": "2026-07-18T00:00:00Z",
        "similarity": 1.0,
        "source_state": "stale",
        "query": "query " * 100,
        "root_cause": "root cause " * 150,
        "recommendation": "recommendation " * 100,
        "verification": "verification " * 100,
        "source_files": [{"path": "src/" + ("a" * 900), "content_hash": "b" * 64}],
        "stale_paths": ["src/" + ("a" * 900)],
    }
    full_prompt = report_index_module._render_candidates_text([candidate])

    prompt, selected = report_index_module._render_candidates([candidate], max_chars=2_500)

    assert len(full_prompt) > 2_500
    assert selected == [candidate]
    assert len(prompt) <= 2_500
    assert full_prompt.startswith(prompt)
    assert full_prompt[len(prompt)] == "\n"


def test_corrupt_manifest_falls_back_closed_and_can_be_replaced(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    index_dir = tmp_path / "report-indexes"
    index = WorkspaceReportIndex(index_dir=index_dir)
    assert _store(index, workspace)
    manifest_path = next(index_dir.glob("*.json.gz"))
    manifest_path.write_bytes(b"not-a-gzip-manifest")

    lookup = index.find_similar_reports(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        query="Trace request routing session state",
    )
    assert lookup.prompt == ""
    assert lookup.skipped_reason == "no_similar_reports"
    assert _store(index, workspace)
    assert (
        index.find_similar_reports(
            workspace_root=str(workspace),
            local_workspace_root=str(workspace),
            query="Trace request routing session state",
        ).candidate_count
        == 1
    )


def test_tampered_entry_is_dropped_fail_closed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    index_dir = tmp_path / "report-indexes"
    index = WorkspaceReportIndex(index_dir=index_dir)
    assert _store(index, workspace)
    manifest_path = next(index_dir.glob("*.json.gz"))
    with gzip.open(manifest_path, "rt", encoding="utf-8") as handle:
        manifest = json.load(handle)
    manifest["entries"][0]["root_cause"] = "Tampered conclusion"
    with gzip.open(manifest_path, "wt", encoding="utf-8") as handle:
        json.dump(manifest, handle)

    lookup = index.find_similar_reports(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        query="Trace request routing session state",
    )

    assert lookup.prompt == ""
    assert lookup.skipped_reason == "no_similar_reports"
    assert not manifest_path.exists()


def test_current_session_is_excluded_and_local_verification_is_required(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    index = WorkspaceReportIndex(index_dir=tmp_path / "report-indexes")
    assert _store(index, workspace, session_id="session-current")

    excluded = index.find_similar_reports(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        query="Trace request routing session state",
        current_session_id="session-current",
    )
    unavailable = index.find_similar_reports(
        workspace_root=str(workspace),
        local_workspace_root="",
        query="Trace request routing session state",
    )

    assert excluded.candidate_count == 0
    assert excluded.skipped_reason == "no_similar_reports"
    assert unavailable.candidate_count == 0
    assert unavailable.skipped_reason == "local_workspace_unavailable"

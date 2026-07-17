"""Tests for workspace-scoped, content-addressed evidence caching."""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

from ternion.core.evidence_cache import WorkspaceEvidenceCache
from ternion.utils.evidence_repository import EvidenceRepository, build_evidence_item


def _records(
    path: str,
    *,
    lines: str,
    excerpt: str,
    purpose: str = "Verify current behavior.",
) -> list[dict]:
    repository = EvidenceRepository(
        items=[
            build_evidence_item(
                path=path,
                lines=lines,
                purpose=purpose,
                excerpt=excerpt,
            )
        ]
    )
    return repository.to_records()


def test_store_and_load_revalidates_current_file_hash(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "src" / "sample.py"
    source.parent.mkdir(parents=True)
    source.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    cache = WorkspaceEvidenceCache(cache_dir=tmp_path / "cache")

    updated = cache.store_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        records=_records("src/sample.py", lines="2-3", excerpt="beta\ngamma"),
        session_id="session-a",
        phase="evidence",
    )
    lookup = cache.load_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
    )

    assert updated == 1
    assert lookup.hit_paths == ("src/sample.py",)
    repository = EvidenceRepository.from_records(lookup.records)
    assert [(item.path, item.lines, item.excerpt) for item in repository.items] == [
        ("src/sample.py", "2-3", "beta\ngamma")
    ]
    assert repository.items[0].file_total_lines == 3


def test_store_accepts_numbered_tool_excerpt_only_when_lines_match(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "sample.py"
    workspace.mkdir()
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    cache = WorkspaceEvidenceCache(cache_dir=tmp_path / "cache")

    accepted = cache.store_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        records=_records("sample.py", lines="1-2", excerpt="1|alpha\n2|beta"),
    )
    rejected = cache.store_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        records=_records("sample.py", lines="1-2", excerpt="1|alpha\n2|changed"),
    )

    assert accepted == 1
    assert rejected == 0
    lookup = cache.load_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
    )
    assert lookup.hit_paths == ("sample.py",)


def test_content_change_invalidates_stale_entry(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "sample.py"
    source.write_text("before\n", encoding="utf-8")
    cache = WorkspaceEvidenceCache(cache_dir=tmp_path / "cache")
    cache.store_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        records=_records("sample.py", lines="1-1", excerpt="before"),
    )

    source.write_text("after\n", encoding="utf-8")
    lookup = cache.load_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
    )

    assert lookup.records == []
    assert lookup.stale_paths == ("sample.py",)
    assert (
        cache.load_records(
            workspace_root=str(workspace),
            local_workspace_root=str(workspace),
        ).stale_paths
        == ()
    )


def test_load_rejects_tampered_excerpt_even_when_file_hash_matches(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "sample.py").write_text("trusted\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    cache = WorkspaceEvidenceCache(cache_dir=cache_dir)
    cache.store_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        records=_records("sample.py", lines="1-1", excerpt="trusted"),
    )

    manifest_path = next(cache_dir.glob("*.json.gz"))
    with gzip.open(manifest_path, "rt", encoding="utf-8") as handle:
        manifest = json.load(handle)
    entry = next(iter(manifest["files"].values()))
    entry["records"][0]["excerpt"] = "tampered"
    with gzip.open(manifest_path, "wt", encoding="utf-8") as handle:
        json.dump(manifest, handle)

    lookup = cache.load_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
    )

    assert lookup.records == []
    assert lookup.stale_paths == ("sample.py",)


def test_same_content_hash_accumulates_verified_ranges(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "sample.py").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    cache = WorkspaceEvidenceCache(cache_dir=tmp_path / "cache")

    cache.store_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        records=_records("sample.py", lines="1-1", excerpt="alpha", purpose="First range."),
    )
    cache.store_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        records=_records("sample.py", lines="2-2", excerpt="beta", purpose="Second range."),
    )
    lookup = cache.load_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
    )

    repository = EvidenceRepository.from_records(lookup.records)
    assert len(repository.items) == 1
    assert repository.items[0].lines == "1-2"
    assert repository.items[0].excerpt == "alpha\nbeta"
    assert repository.items[0].purpose == "First range. / Second range."


def test_explicit_path_and_workspace_invalidation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.py").write_text("a\n", encoding="utf-8")
    (workspace / "b.py").write_text("b\n", encoding="utf-8")
    cache = WorkspaceEvidenceCache(cache_dir=tmp_path / "cache")
    cache.store_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        records=[
            *_records("a.py", lines="1-1", excerpt="a"),
            *_records("b.py", lines="1-1", excerpt="b"),
        ],
    )

    assert (
        cache.invalidate_paths(
            workspace_root=str(workspace),
            paths=[str(workspace / "a.py")],
        )
        == 1
    )
    lookup = cache.load_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
    )
    assert lookup.hit_paths == ("b.py",)
    assert cache.invalidate_workspace(workspace_root=str(workspace)) is True
    assert (
        cache.load_records(
            workspace_root=str(workspace),
            local_workspace_root=str(workspace),
        ).records
        == []
    )


def test_unverifiable_workspace_and_escaping_path_fail_closed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "secret.py"
    secret.write_text("secret\n", encoding="utf-8")
    cache = WorkspaceEvidenceCache(cache_dir=tmp_path / "cache")

    assert (
        cache.store_records(
            workspace_root=str(workspace),
            local_workspace_root=str(workspace),
            records=_records("../secret.py", lines="1-1", excerpt="secret"),
        )
        == 0
    )
    skipped = cache.load_records(
        workspace_root=str(workspace),
        local_workspace_root="",
    )
    assert skipped.records == []
    assert skipped.skipped_reason == "local_workspace_unavailable"


def test_cache_files_use_private_permissions(tmp_path: Path) -> None:
    if os.name == "nt":
        return
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "sample.py").write_text("value\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    cache = WorkspaceEvidenceCache(cache_dir=cache_dir)
    cache.store_records(
        workspace_root=str(workspace),
        local_workspace_root=str(workspace),
        records=_records("sample.py", lines="1-1", excerpt="value"),
    )

    manifest = next(cache_dir.glob("*.json.gz"))
    assert cache_dir.stat().st_mode & 0o777 == 0o700
    assert manifest.stat().st_mode & 0o777 == 0o600

"""Workspace-scoped, content-addressed evidence cache.

Cached evidence is reusable only when Ternion can read the workspace locally
and verify the current file content against the stored full-file SHA-256. The
cache is therefore an optimization, never an alternate source of truth: remote
or unverifiable workspaces fall back to the normal evidence tool loop.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from ternion.core.workspace_memory import (
    ensure_private_directory,
    evidence_item_matches_file,
    load_workspace_manifest,
    now_iso_z,
    read_current_workspace_file,
    relative_workspace_path,
    save_workspace_manifest,
    workspace_identity,
)
from ternion.utils.evidence_chain import EvidenceItem
from ternion.utils.evidence_repository import EvidenceRepository, build_evidence_item

logger = structlog.get_logger(__name__)
_now_iso_z = now_iso_z

EVIDENCE_CACHE_VERSION = 1
DEFAULT_EVIDENCE_CACHE_DIR = Path.home() / ".ternion" / "evidence_cache"
DEFAULT_MAX_CACHEABLE_FILE_BYTES = 5_000_000
DEFAULT_MAX_WORKSPACE_FILES = 256
DEFAULT_MAX_LOOKUP_FILES = 24


@dataclass(frozen=True)
class EvidenceCacheLookup:
    """Result of a workspace evidence-cache lookup."""

    records: list[dict[str, Any]]
    hit_paths: tuple[str, ...] = ()
    stale_paths: tuple[str, ...] = ()
    skipped_reason: str = ""


class WorkspaceEvidenceCache:
    """Persist verified evidence excerpts by workspace, path, and file hash."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        *,
        max_cacheable_file_bytes: int = DEFAULT_MAX_CACHEABLE_FILE_BYTES,
        max_workspace_files: int = DEFAULT_MAX_WORKSPACE_FILES,
    ) -> None:
        """Initialize the cache store.

        Args:
            cache_dir: Cache directory override used by tests and custom deployments.
            max_cacheable_file_bytes: Largest source file eligible for caching.
            max_workspace_files: Maximum current file entries retained per workspace.
        """
        self.cache_dir = cache_dir or DEFAULT_EVIDENCE_CACHE_DIR
        self.max_cacheable_file_bytes = max(1, int(max_cacheable_file_bytes))
        self.max_workspace_files = max(1, int(max_workspace_files))
        self._lock = threading.RLock()
        ensure_private_directory(self.cache_dir)

    def load_records(
        self,
        *,
        workspace_root: str,
        local_workspace_root: str,
        workspace_path_style: str = "",
        paths: set[str] | None = None,
        max_files: int = DEFAULT_MAX_LOOKUP_FILES,
    ) -> EvidenceCacheLookup:
        """Load evidence whose full-file hash still matches the local workspace.

        Args:
            workspace_root: Client-declared workspace root.
            local_workspace_root: Server-local path for the same workspace.
            workspace_path_style: Declared client path style.
            paths: Optional path filter. Values may be relative or absolute.
            max_files: Maximum valid file entries returned, newest first.

        Returns:
            Verified records plus hit/stale path diagnostics.
        """
        identity = workspace_identity(workspace_root, workspace_path_style)
        if not identity:
            return EvidenceCacheLookup(records=[], skipped_reason="workspace_unresolved")
        if not str(local_workspace_root or "").strip():
            return EvidenceCacheLookup(records=[], skipped_reason="local_workspace_unavailable")

        requested_paths: set[str] | None = None
        if paths is not None:
            requested_paths = {
                relative
                for path in paths
                if (
                    relative := relative_workspace_path(
                        path,
                        workspace_root=workspace_root,
                        workspace_path_style=workspace_path_style,
                    )
                )
            }
            if not requested_paths:
                return EvidenceCacheLookup(records=[], skipped_reason="no_cacheable_paths")

        with self._lock:
            manifest_path = self._manifest_path(identity)
            manifest = self._load_manifest(manifest_path, identity)
            files = manifest["files"]
            candidates = [
                entry
                for relative, entry in files.items()
                if isinstance(entry, dict)
                and (requested_paths is None or relative in requested_paths)
            ]
            candidates.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)

            records: list[dict[str, Any]] = []
            hit_paths: list[str] = []
            stale_paths: list[str] = []
            manifest_changed = False
            for entry in candidates[: max(1, int(max_files))]:
                relative_path = str(entry.get("path") or "")
                current = read_current_workspace_file(
                    relative_path,
                    workspace_root=workspace_root,
                    local_workspace_root=local_workspace_root,
                    workspace_path_style=workspace_path_style,
                    max_file_bytes=self.max_cacheable_file_bytes,
                )
                if current is None or current.content_hash != str(entry.get("content_hash") or ""):
                    files.pop(relative_path, None)
                    stale_paths.append(relative_path)
                    manifest_changed = True
                    continue

                entry_records = entry.get("records")
                if not isinstance(entry_records, list):
                    files.pop(relative_path, None)
                    stale_paths.append(relative_path)
                    manifest_changed = True
                    continue
                entry_repo = EvidenceRepository.from_records(entry_records)
                verified_items = [
                    self._rebuild_verified_item(
                        item,
                        relative_path=relative_path,
                        file_lines=current.lines,
                    )
                    for item in entry_repo.items
                    if relative_workspace_path(
                        item.path,
                        workspace_root=workspace_root,
                        workspace_path_style=workspace_path_style,
                    )
                    == relative_path
                    and evidence_item_matches_file(item, current.lines)
                ]
                if not verified_items:
                    files.pop(relative_path, None)
                    stale_paths.append(relative_path)
                    manifest_changed = True
                    continue

                verified_repo = EvidenceRepository(items=verified_items)
                verified_repo.file_meta = {relative_path: len(current.lines)}
                verified_records = verified_repo.to_records()
                if verified_records != entry_records:
                    entry["records"] = verified_records
                    manifest_changed = True
                records.extend(verified_records)
                hit_paths.append(relative_path)

            if manifest_changed:
                self._save_manifest(manifest_path, manifest)

        return EvidenceCacheLookup(
            records=records,
            hit_paths=tuple(hit_paths),
            stale_paths=tuple(stale_paths),
        )

    def store_records(
        self,
        *,
        workspace_root: str,
        local_workspace_root: str,
        workspace_path_style: str = "",
        records: list[dict[str, Any]],
        session_id: str = "",
        phase: str = "",
    ) -> int:
        """Verify and persist evidence records for locally readable files.

        Existing ranges for the same ``(path, content_hash)`` are merged through
        ``EvidenceRepository`` so repeated sessions accumulate useful coverage
        without duplicating excerpts. Records that do not match the current file
        bytes are rejected.

        Returns:
            Number of file entries updated.
        """
        identity = workspace_identity(workspace_root, workspace_path_style)
        if not identity or not str(local_workspace_root or "").strip() or not records:
            return 0

        source_repo = EvidenceRepository.from_records(records)
        grouped: dict[str, list[EvidenceItem]] = {}
        for item in source_repo.items:
            relative = relative_workspace_path(
                item.path,
                workspace_root=workspace_root,
                workspace_path_style=workspace_path_style,
            )
            if relative:
                grouped.setdefault(relative, []).append(item)
        if not grouped:
            return 0

        updated_paths = 0
        with self._lock:
            manifest_path = self._manifest_path(identity)
            manifest = self._load_manifest(manifest_path, identity)
            files = manifest["files"]
            manifest_changed = False

            for relative_path, items in grouped.items():
                current = read_current_workspace_file(
                    relative_path,
                    workspace_root=workspace_root,
                    local_workspace_root=local_workspace_root,
                    workspace_path_style=workspace_path_style,
                    max_file_bytes=self.max_cacheable_file_bytes,
                )
                existing = files.get(relative_path)
                if current is None:
                    if files.pop(relative_path, None) is not None:
                        manifest_changed = True
                    continue
                if isinstance(existing, dict) and str(existing.get("content_hash") or "") != (
                    current.content_hash
                ):
                    files.pop(relative_path, None)
                    existing = None
                    manifest_changed = True

                verified_items = [
                    self._rebuild_verified_item(
                        item,
                        relative_path=relative_path,
                        file_lines=current.lines,
                    )
                    for item in items
                    if evidence_item_matches_file(item, current.lines)
                ]
                if not verified_items:
                    continue

                entry_repo = EvidenceRepository()
                if isinstance(existing, dict) and isinstance(existing.get("records"), list):
                    entry_repo = EvidenceRepository.from_records(existing["records"])
                entry_repo.merge_items(verified_items)
                entry_repo.file_meta = {relative_path: len(current.lines)}

                existing_entry = existing if isinstance(existing, dict) else {}
                source_sessions = [
                    str(value)
                    for value in existing_entry.get("source_sessions", [])
                    if isinstance(value, str) and value
                ]
                if session_id and session_id not in source_sessions:
                    source_sessions.append(session_id)
                files[relative_path] = {
                    "path": relative_path,
                    "content_hash": current.content_hash,
                    "size": current.size,
                    "mtime_ns": current.mtime_ns,
                    "records": entry_repo.to_records(),
                    "source_sessions": source_sessions[-10:],
                    "last_phase": str(phase or ""),
                    "updated_at": _now_iso_z(),
                }
                updated_paths += 1
                manifest_changed = True

            if self._prune_files(files):
                manifest_changed = True
            if manifest_changed:
                self._save_manifest(manifest_path, manifest)

        return updated_paths

    def invalidate_paths(
        self,
        *,
        workspace_root: str,
        workspace_path_style: str = "",
        paths: list[str],
    ) -> int:
        """Remove cached entries for paths observed in a mutation tool result."""
        identity = workspace_identity(workspace_root, workspace_path_style)
        if not identity or not paths:
            return 0
        relative_paths = {
            relative
            for path in paths
            if (
                relative := relative_workspace_path(
                    path,
                    workspace_root=workspace_root,
                    workspace_path_style=workspace_path_style,
                )
            )
        }
        if not relative_paths:
            return 0

        with self._lock:
            manifest_path = self._manifest_path(identity)
            manifest = self._load_manifest(manifest_path, identity)
            files = manifest["files"]
            removed = sum(1 for path in relative_paths if files.pop(path, None) is not None)
            if removed:
                self._save_manifest(manifest_path, manifest)
            return removed

    def invalidate_workspace(
        self,
        *,
        workspace_root: str,
        workspace_path_style: str = "",
    ) -> bool:
        """Remove all cached evidence for a workspace."""
        identity = workspace_identity(workspace_root, workspace_path_style)
        if not identity:
            return False
        with self._lock:
            path = self._manifest_path(identity)
            try:
                path.unlink()
            except FileNotFoundError:
                return False
            except OSError as exc:
                logger.warning(
                    "workspace_evidence_cache_invalidate_failed",
                    workspace_hash=identity,
                    error=str(exc),
                )
                return False
            return True

    @staticmethod
    def _rebuild_verified_item(
        item: EvidenceItem,
        *,
        relative_path: str,
        file_lines: list[str],
    ) -> EvidenceItem:
        """Rebuild trusted metadata after excerpt-to-file verification."""
        return build_evidence_item(
            path=relative_path,
            lines=item.lines,
            file_total_lines=len(file_lines),
            purpose=item.purpose,
            excerpt=item.excerpt,
        )

    def _manifest_path(self, identity: str) -> Path:
        return self.cache_dir / f"{identity}.json.gz"

    @staticmethod
    def _new_manifest(identity: str) -> dict[str, Any]:
        return {
            "version": EVIDENCE_CACHE_VERSION,
            "workspace_hash": identity,
            "files": {},
        }

    def _load_manifest(self, path: Path, identity: str) -> dict[str, Any]:
        return load_workspace_manifest(
            path,
            identity=identity,
            version=EVIDENCE_CACHE_VERSION,
            new_manifest=self._new_manifest,
            collection_defaults={"files": dict},
            logger=logger,
            failure_event="workspace_evidence_cache_load_failed",
        )

    def _save_manifest(self, path: Path, manifest: dict[str, Any]) -> None:
        save_workspace_manifest(path, manifest)

    def _prune_files(self, files: dict[str, Any]) -> bool:
        if len(files) <= self.max_workspace_files:
            return False
        ordered = sorted(
            files.items(),
            key=lambda pair: str(pair[1].get("updated_at") or "")
            if isinstance(pair[1], dict)
            else "",
        )
        for path, _entry in ordered[: len(files) - self.max_workspace_files]:
            files.pop(path, None)
        return True


workspace_evidence_cache = WorkspaceEvidenceCache()

"""Workspace-scoped, content-addressed evidence cache.

Cached evidence is reusable only when Ternion can read the workspace locally
and verify the current file content against the stored full-file SHA-256. The
cache is therefore an optimization, never an alternate source of truth: remote
or unverifiable workspaces fall back to the normal evidence tool loop.
"""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from ternion.utils.evidence_chain import EvidenceItem
from ternion.utils.evidence_repository import EvidenceRepository, build_evidence_item
from ternion.utils.workspace_paths import (
    normalize_declared_workspace_path,
    normalize_local_file_path,
    workspace_relative_path,
)

logger = structlog.get_logger(__name__)

EVIDENCE_CACHE_VERSION = 1
DEFAULT_EVIDENCE_CACHE_DIR = Path.home() / ".ternion" / "evidence_cache"
DEFAULT_MAX_CACHEABLE_FILE_BYTES = 5_000_000
DEFAULT_MAX_WORKSPACE_FILES = 256
DEFAULT_MAX_LOOKUP_FILES = 24

_NUMBERED_LINE_RE = re.compile(r"^\s*(\d+)\|(.*)$")


@dataclass(frozen=True)
class EvidenceCacheLookup:
    """Result of a workspace evidence-cache lookup."""

    records: list[dict[str, Any]]
    hit_paths: tuple[str, ...] = ()
    stale_paths: tuple[str, ...] = ()
    skipped_reason: str = ""


@dataclass(frozen=True)
class _CurrentFile:
    """Locally verified file state used for cache validation."""

    content_hash: str
    size: int
    mtime_ns: int
    lines: list[str]


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
        self._ensure_dir()

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
        identity = self._workspace_identity(workspace_root, workspace_path_style)
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
                    relative := self._relative_path(
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
                current = self._read_current_file(
                    relative_path,
                    workspace_root=workspace_root,
                    local_workspace_root=local_workspace_root,
                    workspace_path_style=workspace_path_style,
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
                    if self._relative_path(
                        item.path,
                        workspace_root=workspace_root,
                        workspace_path_style=workspace_path_style,
                    )
                    == relative_path
                    and self._item_matches_file(item, current.lines)
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
        identity = self._workspace_identity(workspace_root, workspace_path_style)
        if not identity or not str(local_workspace_root or "").strip() or not records:
            return 0

        source_repo = EvidenceRepository.from_records(records)
        grouped: dict[str, list[EvidenceItem]] = {}
        for item in source_repo.items:
            relative = self._relative_path(
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
                current = self._read_current_file(
                    relative_path,
                    workspace_root=workspace_root,
                    local_workspace_root=local_workspace_root,
                    workspace_path_style=workspace_path_style,
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
                    if self._item_matches_file(item, current.lines)
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
        identity = self._workspace_identity(workspace_root, workspace_path_style)
        if not identity or not paths:
            return 0
        relative_paths = {
            relative
            for path in paths
            if (
                relative := self._relative_path(
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
        identity = self._workspace_identity(workspace_root, workspace_path_style)
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

    def _workspace_identity(self, workspace_root: str, workspace_path_style: str) -> str:
        normalized, detected_style = normalize_declared_workspace_path(workspace_root)
        style = str(workspace_path_style or detected_style or "")
        if not normalized or not style:
            return ""
        identity_path = normalized.lower() if style == "windows" else normalized
        payload = f"{style}\n{identity_path}".encode()
        return hashlib.sha256(payload).hexdigest()[:24]

    def _relative_path(
        self,
        path: str,
        *,
        workspace_root: str,
        workspace_path_style: str,
    ) -> str:
        relative = workspace_relative_path(
            str(path or ""),
            workspace_root=workspace_root,
            workspace_path_style=workspace_path_style,
        )
        if relative is None or relative == "":
            return ""
        return relative.replace("\\", "/")

    def _read_current_file(
        self,
        relative_path: str,
        *,
        workspace_root: str,
        local_workspace_root: str,
        workspace_path_style: str,
    ) -> _CurrentFile | None:
        local_path = normalize_local_file_path(
            relative_path,
            workspace_root=workspace_root,
            workspace_path_style=workspace_path_style,
            local_workspace_root=local_workspace_root,
        )
        if not local_path:
            return None
        path = Path(local_path)
        try:
            stat = path.stat()
            if not path.is_file() or stat.st_size > self.max_cacheable_file_bytes:
                return None
            data = path.read_bytes()
        except OSError:
            return None
        text = data.decode("utf-8", errors="replace")
        return _CurrentFile(
            content_hash=hashlib.sha256(data).hexdigest(),
            size=len(data),
            mtime_ns=stat.st_mtime_ns,
            lines=text.splitlines(),
        )

    @staticmethod
    def _item_matches_file(item: EvidenceItem, file_lines: list[str]) -> bool:
        if item.line_range is None:
            return item.excerpt.splitlines() == file_lines
        start, end = item.line_range
        if start < 1 or end < start or end > len(file_lines):
            return False
        excerpt_lines = item.excerpt.splitlines()
        if len(excerpt_lines) != end - start + 1:
            return False

        numbered_matches = [_NUMBERED_LINE_RE.match(line) for line in excerpt_lines]
        if all(match is not None for match in numbered_matches):
            for expected_number, match, source_line in zip(
                range(start, end + 1),
                numbered_matches,
                file_lines[start - 1 : end],
                strict=True,
            ):
                if match is None:
                    return False
                if int(match.group(1)) != expected_number or match.group(2) != source_line:
                    return False
            return True

        return excerpt_lines == file_lines[start - 1 : end]

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
        if not path.exists():
            return self._new_manifest(identity)
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError, TypeError) as exc:
            logger.warning(
                "workspace_evidence_cache_load_failed",
                workspace_hash=identity,
                error=str(exc),
            )
            return self._new_manifest(identity)
        if not isinstance(payload, dict):
            return self._new_manifest(identity)
        if payload.get("version") != EVIDENCE_CACHE_VERSION:
            return self._new_manifest(identity)
        if payload.get("workspace_hash") != identity:
            return self._new_manifest(identity)
        if not isinstance(payload.get("files"), dict):
            payload["files"] = {}
        return payload

    def _save_manifest(self, path: Path, manifest: dict[str, Any]) -> None:
        self._ensure_dir()
        data = gzip.compress(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            compresslevel=6,
        )
        fd, temp_path = tempfile.mkstemp(dir=self.cache_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, path)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def _ensure_dir(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self.cache_dir, 0o700)

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


def _now_iso_z() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


workspace_evidence_cache = WorkspaceEvidenceCache()

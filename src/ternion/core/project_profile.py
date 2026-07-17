"""Workspace-scoped project profiles used only for Phase 0 navigation.

Profiles summarize evidence-backed paths and prior report orientations so a
later workflow can start with narrower discovery. They are never evidence:
every stored source is bound to the current full-file SHA-256, stale
observations are removed, and the rendered profile contains no file excerpts.
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
from ternion.utils.evidence_repository import EvidenceRepository
from ternion.utils.report_parser import parse_structured_report
from ternion.utils.workspace_paths import (
    normalize_declared_workspace_path,
    normalize_local_file_path,
    workspace_relative_path,
)

logger = structlog.get_logger(__name__)

PROJECT_PROFILE_VERSION = 1
DEFAULT_PROJECT_PROFILE_DIR = Path.home() / ".ternion" / "project_profiles"
DEFAULT_MAX_SOURCE_FILE_BYTES = 5_000_000
DEFAULT_MAX_PROFILE_SOURCES = 12
DEFAULT_MAX_PROFILE_OBSERVATIONS = 3
DEFAULT_MAX_PROFILE_PROMPT_CHARS = 5_000

_NUMBERED_LINE_RE = re.compile(r"^\s*(\d+)\|(.*)$")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_ENTRYPOINT_NAMES = {
    "__main__.py",
    "app.py",
    "main.py",
    "routes.py",
    "server.py",
    "index.js",
    "index.ts",
    "index.tsx",
    "main.js",
    "main.ts",
    "main.tsx",
    "package.json",
    "pyproject.toml",
}


@dataclass(frozen=True)
class ProjectProfileLookup:
    """Result of a workspace project-profile lookup."""

    prompt: str = ""
    source_paths: tuple[str, ...] = ()
    stale_paths: tuple[str, ...] = ()
    observation_count: int = 0
    skipped_reason: str = ""


@dataclass(frozen=True)
class _CurrentFile:
    """Current local file state used to validate profile sources."""

    content_hash: str
    size: int
    mtime_ns: int
    lines: list[str]


class WorkspaceProjectProfile:
    """Persist a small, current workspace map for evidence discovery."""

    def __init__(
        self,
        profile_dir: Path | None = None,
        *,
        max_source_file_bytes: int = DEFAULT_MAX_SOURCE_FILE_BYTES,
        max_sources: int = DEFAULT_MAX_PROFILE_SOURCES,
        max_observations: int = DEFAULT_MAX_PROFILE_OBSERVATIONS,
        max_prompt_chars: int = DEFAULT_MAX_PROFILE_PROMPT_CHARS,
    ) -> None:
        """Initialize the project-profile store.

        Args:
            profile_dir: Storage directory override for tests or deployments.
            max_source_file_bytes: Largest source file eligible for validation.
            max_sources: Maximum current source files retained per workspace.
            max_observations: Maximum recent report orientations retained.
            max_prompt_chars: Maximum rendered Phase 0 navigation block size.
        """
        self.profile_dir = profile_dir or DEFAULT_PROJECT_PROFILE_DIR
        self.max_source_file_bytes = max(1, int(max_source_file_bytes))
        self.max_sources = max(1, int(max_sources))
        self.max_observations = max(1, int(max_observations))
        self.max_prompt_chars = max(500, int(max_prompt_chars))
        self._lock = threading.RLock()
        self._ensure_dir()

    def load_profile(
        self,
        *,
        workspace_root: str,
        local_workspace_root: str,
        workspace_path_style: str = "",
    ) -> ProjectProfileLookup:
        """Load a profile after revalidating every referenced source file.

        Args:
            workspace_root: Client-declared workspace root.
            local_workspace_root: Server-local path for the same workspace.
            workspace_path_style: Declared client path style.

        Returns:
            A bounded navigation prompt and validation diagnostics.
        """
        identity = self._workspace_identity(workspace_root, workspace_path_style)
        if not identity:
            return ProjectProfileLookup(skipped_reason="workspace_unresolved")
        if not str(local_workspace_root or "").strip():
            return ProjectProfileLookup(skipped_reason="local_workspace_unavailable")

        with self._lock:
            path = self._profile_path(identity)
            if not path.exists():
                return ProjectProfileLookup(skipped_reason="profile_not_found")
            manifest = self._load_manifest(path, identity)
            manifest, stale_paths, changed = self._validated_manifest(
                manifest,
                workspace_root=workspace_root,
                local_workspace_root=local_workspace_root,
                workspace_path_style=workspace_path_style,
            )
            observations = manifest["observations"]
            if changed:
                if observations:
                    self._save_manifest(path, manifest)
                else:
                    self._remove_path(path)
            if not observations:
                return ProjectProfileLookup(
                    stale_paths=tuple(stale_paths),
                    skipped_reason="no_current_observations",
                )
            prompt = self._render_profile(manifest)
            return ProjectProfileLookup(
                prompt=prompt,
                source_paths=tuple(manifest["sources"]),
                stale_paths=tuple(stale_paths),
                observation_count=len(observations),
            )

    def store_profile(
        self,
        *,
        workspace_root: str,
        local_workspace_root: str,
        workspace_path_style: str = "",
        evidence_records: list[dict[str, Any]],
        report: str,
        query: str = "",
        session_id: str = "",
    ) -> bool:
        """Store a compact report orientation backed by current evidence files.

        The report summary remains navigation-only. Evidence records are used
        solely to identify and hash current source files; excerpts are never
        rendered into the profile.

        Args:
            workspace_root: Client-declared workspace root.
            local_workspace_root: Server-local path for the same workspace.
            workspace_path_style: Declared client path style.
            evidence_records: Structured evidence records for the report.
            report: Final Arbiter report to summarize deterministically.
            query: User request associated with the report.
            session_id: Source session identifier for traceability.

        Returns:
            True when a current profile observation was persisted.
        """
        identity = self._workspace_identity(workspace_root, workspace_path_style)
        summary = _summarize_report(report)
        if (
            not identity
            or not str(local_workspace_root or "").strip()
            or not evidence_records
            or not summary
        ):
            return False

        sources = self._verified_sources(
            evidence_records,
            workspace_root=workspace_root,
            local_workspace_root=local_workspace_root,
            workspace_path_style=workspace_path_style,
        )
        if not sources:
            return False
        sources = dict(list(sources.items())[: self.max_sources])

        with self._lock:
            path = self._profile_path(identity)
            manifest = self._load_manifest(path, identity)
            manifest, _, _ = self._validated_manifest(
                manifest,
                workspace_root=workspace_root,
                local_workspace_root=local_workspace_root,
                workspace_path_style=workspace_path_style,
            )
            manifest_sources = manifest["sources"]
            manifest_sources.update(sources)

            source_paths = list(sources)
            observation_id = _observation_id(
                query=query,
                summary=summary,
                source_paths=source_paths,
                sources=manifest_sources,
            )
            observations = [
                item
                for item in manifest["observations"]
                if str(item.get("id") or "") != observation_id
            ]
            observations.append(
                {
                    "id": observation_id,
                    "query": _bounded_single_line(query, 200),
                    "summary": summary,
                    "source_paths": source_paths,
                    "source_session": _bounded_single_line(session_id, 120),
                    "observed_at": _now_iso_z(),
                }
            )
            manifest["observations"] = observations[-self.max_observations :]
            self._enforce_source_cap(manifest)
            self._drop_unreferenced_sources(manifest)
            manifest["updated_at"] = _now_iso_z()
            self._save_manifest(path, manifest)
            return True

    def invalidate_paths(
        self,
        *,
        workspace_root: str,
        workspace_path_style: str = "",
        paths: list[str],
    ) -> int:
        """Remove observations that depend on files changed by a tool result."""
        identity = self._workspace_identity(workspace_root, workspace_path_style)
        if not identity or not paths:
            return 0
        targets = {
            relative
            for raw_path in paths
            if (
                relative := self._relative_path(
                    raw_path,
                    workspace_root=workspace_root,
                    workspace_path_style=workspace_path_style,
                )
            )
        }
        if not targets:
            return 0

        with self._lock:
            profile_path = self._profile_path(identity)
            if not profile_path.exists():
                return 0
            manifest = self._load_manifest(profile_path, identity)
            observations = manifest["observations"]
            kept = [
                item
                for item in observations
                if not targets.intersection(_observation_source_paths(item))
            ]
            removed = len(observations) - len(kept)
            if not removed:
                return 0
            manifest["observations"] = kept
            self._drop_unreferenced_sources(manifest)
            if kept:
                manifest["updated_at"] = _now_iso_z()
                self._save_manifest(profile_path, manifest)
            else:
                self._remove_path(profile_path)
            return removed

    def invalidate_workspace(
        self,
        *,
        workspace_root: str,
        workspace_path_style: str = "",
    ) -> bool:
        """Remove the complete navigation profile for a workspace."""
        identity = self._workspace_identity(workspace_root, workspace_path_style)
        if not identity:
            return False
        with self._lock:
            return self._remove_path(self._profile_path(identity))

    def _verified_sources(
        self,
        evidence_records: list[dict[str, Any]],
        *,
        workspace_root: str,
        local_workspace_root: str,
        workspace_path_style: str,
    ) -> dict[str, dict[str, Any]]:
        repository = EvidenceRepository.from_records(evidence_records)
        grouped: dict[str, list[EvidenceItem]] = {}
        for item in repository.items:
            relative = self._relative_path(
                item.path,
                workspace_root=workspace_root,
                workspace_path_style=workspace_path_style,
            )
            if relative:
                grouped.setdefault(relative, []).append(item)

        sources: dict[str, dict[str, Any]] = {}
        for relative_path, items in grouped.items():
            current = self._read_current_file(
                relative_path,
                workspace_root=workspace_root,
                local_workspace_root=local_workspace_root,
                workspace_path_style=workspace_path_style,
            )
            if current is None:
                continue
            verified = [item for item in items if _item_matches_file(item, current.lines)]
            if not verified:
                continue
            purposes = _merge_purposes(item.purpose for item in verified)
            sources[relative_path] = {
                "path": relative_path,
                "content_hash": current.content_hash,
                "size": current.size,
                "mtime_ns": current.mtime_ns,
                "purpose": _bounded_single_line(purposes, 180),
                "observed_at": _now_iso_z(),
            }
        return sources

    def _validated_manifest(
        self,
        manifest: dict[str, Any],
        *,
        workspace_root: str,
        local_workspace_root: str,
        workspace_path_style: str,
    ) -> tuple[dict[str, Any], list[str], bool]:
        sources = manifest["sources"]
        valid_sources: dict[str, dict[str, Any]] = {}
        stale_paths: list[str] = []
        changed = False
        for relative_path, entry in sources.items():
            if not isinstance(entry, dict):
                changed = True
                continue
            current = self._read_current_file(
                relative_path,
                workspace_root=workspace_root,
                local_workspace_root=local_workspace_root,
                workspace_path_style=workspace_path_style,
            )
            if current is None or current.content_hash != str(entry.get("content_hash") or ""):
                stale_paths.append(relative_path)
                changed = True
                continue
            valid_sources[relative_path] = entry

        valid_observations: list[dict[str, Any]] = []
        for item in manifest["observations"]:
            if not isinstance(item, dict):
                changed = True
                continue
            source_paths = _observation_source_paths(item)
            if (
                not source_paths
                or not str(item.get("summary") or "").strip()
                or any(path not in valid_sources for path in source_paths)
            ):
                changed = True
                continue
            valid_observations.append(item)

        manifest["sources"] = valid_sources
        manifest["observations"] = valid_observations[-self.max_observations :]
        self._enforce_source_cap(manifest)
        before_sources = set(valid_sources)
        self._drop_unreferenced_sources(manifest)
        if set(manifest["sources"]) != before_sources:
            changed = True
        return manifest, stale_paths, changed

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
            if not path.is_file() or stat.st_size > self.max_source_file_bytes:
                return None
            data = path.read_bytes()
        except OSError:
            return None
        return _CurrentFile(
            content_hash=hashlib.sha256(data).hexdigest(),
            size=len(data),
            mtime_ns=stat.st_mtime_ns,
            lines=data.decode("utf-8", errors="replace").splitlines(),
        )

    def _render_profile(self, manifest: dict[str, Any]) -> str:
        sources = list(manifest["sources"].values())
        observations = list(reversed(manifest["observations"]))
        while True:
            rendered = _render_profile_text(sources, observations)
            if len(rendered) <= self.max_prompt_chars:
                return rendered
            if len(observations) > 1:
                observations.pop()
                continue
            if len(sources) > 3:
                sources.pop()
                continue
            return rendered[: self.max_prompt_chars].rstrip()

    def _workspace_identity(self, workspace_root: str, workspace_path_style: str) -> str:
        normalized, detected_style = normalize_declared_workspace_path(workspace_root)
        style = str(workspace_path_style or detected_style or "")
        if not normalized or not style:
            return ""
        identity_path = normalized.lower() if style == "windows" else normalized
        return hashlib.sha256(f"{style}\n{identity_path}".encode()).hexdigest()[:24]

    @staticmethod
    def _relative_path(
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

    def _profile_path(self, identity: str) -> Path:
        return self.profile_dir / f"{identity}.json.gz"

    @staticmethod
    def _new_manifest(identity: str) -> dict[str, Any]:
        return {
            "version": PROJECT_PROFILE_VERSION,
            "workspace_hash": identity,
            "updated_at": "",
            "sources": {},
            "observations": [],
        }

    def _load_manifest(self, path: Path, identity: str) -> dict[str, Any]:
        if not path.exists():
            return self._new_manifest(identity)
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError, TypeError) as exc:
            logger.warning(
                "workspace_project_profile_load_failed",
                workspace_hash=identity,
                error=str(exc),
            )
            return self._new_manifest(identity)
        if not isinstance(payload, dict):
            return self._new_manifest(identity)
        if payload.get("version") != PROJECT_PROFILE_VERSION:
            return self._new_manifest(identity)
        if payload.get("workspace_hash") != identity:
            return self._new_manifest(identity)
        if not isinstance(payload.get("sources"), dict):
            payload["sources"] = {}
        if not isinstance(payload.get("observations"), list):
            payload["observations"] = []
        return payload

    def _save_manifest(self, path: Path, manifest: dict[str, Any]) -> None:
        self._ensure_dir()
        data = gzip.compress(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            compresslevel=6,
        )
        fd, temp_path = tempfile.mkstemp(dir=self.profile_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(temp_path)
            raise

    def _ensure_dir(self) -> None:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self.profile_dir, 0o700)

    @staticmethod
    def _drop_unreferenced_sources(manifest: dict[str, Any]) -> None:
        referenced = {
            path for item in manifest["observations"] for path in _observation_source_paths(item)
        }
        manifest["sources"] = {
            path: entry for path, entry in manifest["sources"].items() if path in referenced
        }

    def _enforce_source_cap(self, manifest: dict[str, Any]) -> None:
        observations = manifest["observations"]
        while observations:
            referenced = {path for item in observations for path in _observation_source_paths(item)}
            if len(referenced) <= self.max_sources:
                return
            observations.pop(0)

    @staticmethod
    def _remove_path(path: Path) -> bool:
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            logger.warning(
                "workspace_project_profile_remove_failed", path=str(path), error=str(exc)
            )
            return False
        return True


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


def _summarize_report(report: str) -> str:
    parsed = parse_structured_report(report)
    if not parsed.root_cause.strip():
        return ""
    return _bounded_single_line(parsed.root_cause, 700)


def _bounded_single_line(value: str, limit: int) -> str:
    text = str(value or "").replace("```", " ").replace("`", "")
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
    text = re.sub(r"(?m)^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _merge_purposes(purposes: Any) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for raw in purposes:
        for part in str(raw or "").split(" / "):
            cleaned = part.strip()
            if cleaned and cleaned not in seen:
                merged.append(cleaned)
                seen.add(cleaned)
    return " / ".join(merged)


def _observation_source_paths(observation: dict[str, Any]) -> list[str]:
    return [
        str(path)
        for path in observation.get("source_paths", [])
        if isinstance(path, str) and path.strip()
    ]


def _observation_id(
    *,
    query: str,
    summary: str,
    source_paths: list[str],
    sources: dict[str, dict[str, Any]],
) -> str:
    source_fingerprints = [
        f"{path}:{str(sources.get(path, {}).get('content_hash') or '')}" for path in source_paths
    ]
    payload = "\n".join([query.strip(), summary.strip(), *source_fingerprints])
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def _render_profile_text(
    sources: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> str:
    paths = [str(item.get("path") or "") for item in sources if item.get("path")]
    directories = sorted({str(Path(path).parent).replace("\\", "/") or "." for path in paths})
    entrypoints = [
        path
        for path in paths
        if Path(path).name.lower() in _ENTRYPOINT_NAMES
        or any(
            term
            in str(next((s.get("purpose") for s in sources if s.get("path") == path), "")).lower()
            for term in ("entrypoint", "entry point", "startup", "bootstrap", "routing")
        )
    ]

    lines = [
        "PROJECT_DIRECTORIES:",
        *[f"- {directory}" for directory in directories],
        "KEY_FILES_AND_PURPOSE_HINTS:",
    ]
    for item in sources:
        path = str(item.get("path") or "")
        purpose = str(item.get("purpose") or "")
        suffix = f" | purpose_hint={purpose}" if purpose else ""
        lines.append(f"- {path}{suffix}")
    if entrypoints:
        lines.extend(["ENTRYPOINT_CANDIDATES:", *[f"- {path}" for path in entrypoints]])
    lines.append("RECENT_REPORT_ORIENTATIONS:")
    for item in observations:
        query = str(item.get("query") or "")
        summary = str(item.get("summary") or "")
        source_paths = ", ".join(_observation_source_paths(item))
        lines.append(f"- query={query or '(not recorded)'}")
        lines.append(f"  prior_orientation={summary}")
        lines.append(f"  current_source_paths={source_paths}")
    return "\n".join(lines).strip()


def _now_iso_z() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


workspace_project_profile = WorkspaceProjectProfile()

"""Workspace-scoped project profiles used only for Phase 0 navigation.

Profiles summarize evidence-backed paths and prior report orientations so a
later workflow can start with narrower discovery. They are never evidence:
every stored source is bound to the current full-file SHA-256, stale
observations are removed, and the rendered profile contains no file excerpts.
"""

from __future__ import annotations

import hashlib
import re
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
from ternion.utils.evidence_repository import EvidenceRepository
from ternion.utils.report_parser import parse_structured_report

logger = structlog.get_logger(__name__)
_now_iso_z = now_iso_z

PROJECT_PROFILE_VERSION = 1
DEFAULT_PROJECT_PROFILE_DIR = Path.home() / ".ternion" / "project_profiles"
DEFAULT_MAX_SOURCE_FILE_BYTES = 5_000_000
DEFAULT_MAX_PROFILE_SOURCES = 12
DEFAULT_MAX_PROFILE_OBSERVATIONS = 3
DEFAULT_MAX_PROFILE_PROMPT_CHARS = 5_000

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
        ensure_private_directory(self.profile_dir)

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
        identity = workspace_identity(workspace_root, workspace_path_style)
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
        identity = workspace_identity(workspace_root, workspace_path_style)
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
        identity = workspace_identity(workspace_root, workspace_path_style)
        if not identity or not paths:
            return 0
        targets = {
            relative
            for raw_path in paths
            if (
                relative := relative_workspace_path(
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
        identity = workspace_identity(workspace_root, workspace_path_style)
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
            relative = relative_workspace_path(
                item.path,
                workspace_root=workspace_root,
                workspace_path_style=workspace_path_style,
            )
            if relative:
                grouped.setdefault(relative, []).append(item)

        sources: dict[str, dict[str, Any]] = {}
        for relative_path, items in grouped.items():
            current = read_current_workspace_file(
                relative_path,
                workspace_root=workspace_root,
                local_workspace_root=local_workspace_root,
                workspace_path_style=workspace_path_style,
                max_file_bytes=self.max_source_file_bytes,
            )
            if current is None:
                continue
            verified = [item for item in items if evidence_item_matches_file(item, current.lines)]
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
            current = read_current_workspace_file(
                relative_path,
                workspace_root=workspace_root,
                local_workspace_root=local_workspace_root,
                workspace_path_style=workspace_path_style,
                max_file_bytes=self.max_source_file_bytes,
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

    def _render_profile(self, manifest: dict[str, Any]) -> str:
        sources = list(manifest["sources"].values())
        observations = list(reversed(manifest["observations"]))
        while True:
            referenced_paths = {
                path for item in observations for path in _observation_source_paths(item)
            }
            visible_sources = [
                item for item in sources if str(item.get("path") or "") in referenced_paths
            ]
            rendered = _render_profile_text(visible_sources, observations)
            if len(rendered) <= self.max_prompt_chars:
                return rendered
            if len(observations) > 1:
                observations.pop()
                continue
            if len(visible_sources) > 3:
                visible_path = str(visible_sources[-1].get("path") or "")
                sources = [item for item in sources if str(item.get("path") or "") != visible_path]
                continue
            return rendered[: self.max_prompt_chars].rstrip()

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
        return load_workspace_manifest(
            path,
            identity=identity,
            version=PROJECT_PROFILE_VERSION,
            new_manifest=self._new_manifest,
            collection_defaults={"sources": dict, "observations": list},
            logger=logger,
            failure_event="workspace_project_profile_load_failed",
        )

    def _save_manifest(self, path: Path, manifest: dict[str, Any]) -> None:
        save_workspace_manifest(path, manifest)

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
    purpose_by_path = {
        str(item.get("path") or ""): str(item.get("purpose") or "")
        for item in sources
        if item.get("path")
    }
    paths = list(purpose_by_path)
    visible_paths = set(paths)
    directories = sorted({str(Path(path).parent).replace("\\", "/") or "." for path in paths})
    entrypoints = [
        path
        for path in paths
        if Path(path).name.lower() in _ENTRYPOINT_NAMES
        or any(
            term in purpose_by_path[path].lower()
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
        source_paths = ", ".join(
            path for path in _observation_source_paths(item) if path in visible_paths
        )
        lines.append(f"- query={query or '(not recorded)'}")
        lines.append(f"  prior_orientation={summary}")
        lines.append(f"  current_source_paths={source_paths}")
    return "\n".join(lines).strip()


workspace_project_profile = WorkspaceProjectProfile()

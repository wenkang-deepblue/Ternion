"""Workspace-scoped historical report index for bounded cross-session reuse.

The index stores compact report conclusions and the hashes of their verified
source files. Similar prior reports are exposed only as untrusted hypotheses:
they never become evidence, satisfy evidence gaps, or bypass current-source
collection. Source hashes are rechecked on every lookup so candidates are
explicitly labeled current or stale without deleting useful history.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import structlog

from ternion.core.session_store import compute_report_hash
from ternion.core.workspace_memory import (
    bounded_single_line,
    collect_verified_evidence_sources,
    ensure_private_directory,
    load_workspace_manifest,
    now_iso_z,
    read_current_workspace_file,
    save_workspace_manifest,
    workspace_identity,
)
from ternion.utils.report_parser import parse_structured_report

logger = structlog.get_logger(__name__)
_now_iso_z = now_iso_z

REPORT_INDEX_VERSION = 1
DEFAULT_REPORT_INDEX_DIR = Path.home() / ".ternion" / "report_indexes"
DEFAULT_MAX_SOURCE_FILE_BYTES = 5_000_000
DEFAULT_MAX_REPORT_SOURCES = 12
DEFAULT_MAX_REPORT_ENTRIES = 50
DEFAULT_MAX_REPORT_CANDIDATES = 3
DEFAULT_MAX_REPORT_PROMPT_CHARS = 8_000
DEFAULT_REPORT_SIMILARITY_THRESHOLD = 0.28

_REPORT_HASH_RE = re.compile(r"^[0-9a-f]{16}$")
_CONTENT_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ENTRY_ID_RE = re.compile(r"^[0-9a-f]{24}$")
_ENTRY_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ASCII_TERM_RE = re.compile(r"[a-z0-9][a-z0-9_./-]*")
_CJK_SEQUENCE_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_NON_WORD_RE = re.compile(r"[^a-z0-9\u3400-\u4dbf\u4e00-\u9fff]+")
_STOP_TERMS = {
    "a",
    "an",
    "and",
    "analyze",
    "code",
    "current",
    "file",
    "fix",
    "for",
    "in",
    "inspect",
    "issue",
    "of",
    "please",
    "problem",
    "project",
    "request",
    "the",
    "to",
    "with",
    "代码",
    "当前",
    "检查",
    "请帮",
    "问题",
    "项目",
}
_ENTRY_HASH_FIELDS = (
    "id",
    "session_id",
    "query",
    "report_hash",
    "root_cause",
    "recommendation",
    "verification",
    "source_files",
    "observed_at",
)


@dataclass(frozen=True)
class ReportIndexLookup:
    """Result of a workspace historical-report similarity lookup."""

    prompt: str = ""
    candidate_session_ids: tuple[str, ...] = ()
    candidate_count: int = 0
    current_count: int = 0
    stale_count: int = 0
    skipped_reason: str = ""


class WorkspaceReportIndex:
    """Persist and retrieve bounded historical report candidates by workspace."""

    def __init__(
        self,
        index_dir: Path | None = None,
        *,
        max_source_file_bytes: int = DEFAULT_MAX_SOURCE_FILE_BYTES,
        max_sources: int = DEFAULT_MAX_REPORT_SOURCES,
        max_entries: int = DEFAULT_MAX_REPORT_ENTRIES,
        max_candidates: int = DEFAULT_MAX_REPORT_CANDIDATES,
        max_prompt_chars: int = DEFAULT_MAX_REPORT_PROMPT_CHARS,
        similarity_threshold: float = DEFAULT_REPORT_SIMILARITY_THRESHOLD,
    ) -> None:
        """Initialize the historical report index.

        Args:
            index_dir: Storage directory override for tests or deployments.
            max_source_file_bytes: Largest source file eligible for validation.
            max_sources: Maximum verified source files stored per report.
            max_entries: Maximum historical reports retained per workspace.
            max_candidates: Maximum similar reports returned per lookup.
            max_prompt_chars: Maximum rendered hypothesis block size.
            similarity_threshold: Minimum deterministic lexical similarity.
        """
        self.index_dir = index_dir or DEFAULT_REPORT_INDEX_DIR
        self.max_source_file_bytes = max(1, int(max_source_file_bytes))
        self.max_sources = max(1, int(max_sources))
        self.max_entries = max(1, int(max_entries))
        self.max_candidates = max(1, int(max_candidates))
        self.max_prompt_chars = max(2_500, int(max_prompt_chars))
        self.similarity_threshold = min(1.0, max(0.0, float(similarity_threshold)))
        self._lock = threading.RLock()
        ensure_private_directory(self.index_dir)

    def store_report(
        self,
        *,
        workspace_root: str,
        local_workspace_root: str,
        workspace_path_style: str = "",
        evidence_records: list[dict[str, Any]],
        report: str,
        query: str,
        session_id: str = "",
        report_hash: str = "",
    ) -> bool:
        """Index a compact structured report backed by verified current sources.

        Args:
            workspace_root: Client-declared workspace root.
            local_workspace_root: Server-local path for the same workspace.
            workspace_path_style: Declared client path style.
            evidence_records: Structured evidence records supporting the report.
            report: Final structured Arbiter report.
            query: User request associated with the report.
            session_id: Source session identifier for traceability.
            report_hash: Expected session report hash, when already persisted.

        Returns:
            True when a report entry was persisted.
        """
        identity = workspace_identity(workspace_root, workspace_path_style)
        normalized_query = bounded_single_line(query, 400)
        parsed = parse_structured_report(report)
        computed_hash = compute_report_hash(report)
        if (
            not identity
            or not str(local_workspace_root or "").strip()
            or not evidence_records
            or not normalized_query
            or not _query_terms(normalized_query)
            or not parsed.root_cause.strip()
            or (report_hash and report_hash != computed_hash)
        ):
            return False

        verified_sources = collect_verified_evidence_sources(
            evidence_records,
            workspace_root=workspace_root,
            local_workspace_root=local_workspace_root,
            workspace_path_style=workspace_path_style,
            max_file_bytes=self.max_source_file_bytes,
            max_sources=self.max_sources,
        )
        if not verified_sources:
            return False

        source_files = [
            {"path": source.path, "content_hash": source.current.content_hash}
            for source in verified_sources
        ]
        entry_id = _report_entry_id(
            query=normalized_query,
            report_hash=computed_hash,
            source_files=source_files,
        )
        entry: dict[str, Any] = {
            "id": entry_id,
            "session_id": bounded_single_line(session_id, 120),
            "query": normalized_query,
            "report_hash": computed_hash,
            "root_cause": bounded_single_line(parsed.root_cause, 1_000),
            "recommendation": bounded_single_line(parsed.fix_plan, 1_000),
            "verification": bounded_single_line(parsed.verification, 700),
            "source_files": source_files,
            "observed_at": _now_iso_z(),
        }
        entry["entry_hash"] = _report_entry_hash(entry)

        with self._lock:
            path = self._index_path(identity)
            manifest = self._load_manifest(path, identity)
            entries, _ = _validated_entries(
                manifest["entries"],
                max_sources=self.max_sources,
            )
            entries = [item for item in entries if str(item.get("id") or "") != entry_id]
            entries.append(entry)
            manifest["entries"] = entries[-self.max_entries :]
            manifest["updated_at"] = _now_iso_z()
            self._save_manifest(path, manifest)
        return True

    def find_similar_reports(
        self,
        *,
        workspace_root: str,
        local_workspace_root: str,
        workspace_path_style: str = "",
        query: str,
        current_session_id: str = "",
    ) -> ReportIndexLookup:
        """Find similar historical reports and label their current source state.

        Args:
            workspace_root: Client-declared workspace root.
            local_workspace_root: Server-local path for the same workspace.
            workspace_path_style: Declared client path style.
            query: Current user request.
            current_session_id: Session excluded from its own historical lookup.

        Returns:
            A bounded hypotheses-only prompt plus lookup diagnostics.
        """
        identity = workspace_identity(workspace_root, workspace_path_style)
        query_text = bounded_single_line(query, 400)
        query_terms = _query_terms(query_text)
        if not identity:
            return ReportIndexLookup(skipped_reason="workspace_unresolved")
        if not str(local_workspace_root or "").strip():
            return ReportIndexLookup(skipped_reason="local_workspace_unavailable")
        if not query_terms:
            return ReportIndexLookup(skipped_reason="query_not_indexable")

        with self._lock:
            path = self._index_path(identity)
            if not path.exists():
                return ReportIndexLookup(skipped_reason="index_not_found")
            manifest = self._load_manifest(path, identity)
            entries, changed = _validated_entries(
                manifest["entries"],
                max_sources=self.max_sources,
            )
            if len(entries) > self.max_entries:
                entries = entries[-self.max_entries :]
                changed = True
            if changed:
                manifest["entries"] = entries[-self.max_entries :]
                if entries:
                    manifest["updated_at"] = _now_iso_z()
                    self._save_manifest(path, manifest)
                else:
                    self._remove_path(path)

        scored: list[dict[str, Any]] = []
        for entry in entries:
            if current_session_id and entry.get("session_id") == current_session_id:
                continue
            similarity = _query_similarity(query_text, str(entry.get("query") or ""))
            if similarity < self.similarity_threshold:
                continue
            candidate = dict(entry)
            candidate["similarity"] = similarity
            scored.append(candidate)
        scored.sort(
            key=lambda item: (
                float(item.get("similarity") or 0.0),
                str(item.get("observed_at") or ""),
            ),
            reverse=True,
        )
        candidates = scored[: self.max_candidates]
        if not candidates:
            return ReportIndexLookup(skipped_reason="no_similar_reports")

        current_files: dict[str, Any] = {}
        for candidate in candidates:
            stale_paths: list[str] = []
            for source in _source_files(candidate):
                source_path = source["path"]
                if source_path not in current_files:
                    current_files[source_path] = read_current_workspace_file(
                        source_path,
                        workspace_root=workspace_root,
                        local_workspace_root=local_workspace_root,
                        workspace_path_style=workspace_path_style,
                        max_file_bytes=self.max_source_file_bytes,
                    )
                current = current_files[source_path]
                if current is None or current.content_hash != source["content_hash"]:
                    stale_paths.append(source_path)
            candidate["source_state"] = "stale" if stale_paths else "current"
            candidate["stale_paths"] = stale_paths

        prompt, rendered_candidates = _render_candidates(
            candidates,
            max_chars=self.max_prompt_chars,
        )
        current_count = sum(item.get("source_state") == "current" for item in rendered_candidates)
        stale_count = len(rendered_candidates) - current_count
        session_ids = tuple(
            session_id
            for item in rendered_candidates
            if (session_id := str(item.get("session_id") or ""))
        )
        return ReportIndexLookup(
            prompt=prompt,
            candidate_session_ids=session_ids,
            candidate_count=len(rendered_candidates),
            current_count=current_count,
            stale_count=stale_count,
        )

    def _index_path(self, identity: str) -> Path:
        return self.index_dir / f"{identity}.json.gz"

    @staticmethod
    def _new_manifest(identity: str) -> dict[str, Any]:
        return {
            "version": REPORT_INDEX_VERSION,
            "workspace_hash": identity,
            "updated_at": "",
            "entries": [],
        }

    def _load_manifest(self, path: Path, identity: str) -> dict[str, Any]:
        return load_workspace_manifest(
            path,
            identity=identity,
            version=REPORT_INDEX_VERSION,
            new_manifest=self._new_manifest,
            collection_defaults={"entries": list},
            logger=logger,
            failure_event="workspace_report_index_load_failed",
        )

    def _save_manifest(self, path: Path, manifest: dict[str, Any]) -> None:
        save_workspace_manifest(path, manifest)

    @staticmethod
    def _remove_path(path: Path) -> bool:
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            logger.warning("workspace_report_index_remove_failed", path=str(path), error=str(exc))
            return False
        return True


def _source_files(entry: dict[str, Any]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for source in entry.get("source_files", []):
        if not isinstance(source, dict):
            continue
        path = source.get("path")
        content_hash = source.get("content_hash")
        if isinstance(path, str) and isinstance(content_hash, str):
            sources.append({"path": path, "content_hash": content_hash})
    return sources


def _validated_entries(
    raw_entries: list[Any],
    *,
    max_sources: int,
) -> tuple[list[dict[str, Any]], bool]:
    valid: list[dict[str, Any]] = []
    changed = False
    for entry in raw_entries:
        if not isinstance(entry, dict) or not _report_entry_is_valid(
            entry,
            max_sources=max_sources,
        ):
            changed = True
            continue
        valid.append(entry)
    return valid, changed


def _report_entry_is_valid(entry: dict[str, Any], *, max_sources: int) -> bool:
    source_files = _source_files(entry)
    if (
        not _is_bounded_string(entry.get("id"), 24)
        or not _ENTRY_ID_RE.fullmatch(entry["id"])
        or not _is_bounded_string(entry.get("session_id"), 120, allow_empty=True)
        or not _is_bounded_string(entry.get("query"), 400)
        or not _is_bounded_string(entry.get("root_cause"), 1_000)
        or not _is_bounded_string(entry.get("recommendation"), 1_000, allow_empty=True)
        or not _is_bounded_string(entry.get("verification"), 700, allow_empty=True)
        or not _is_bounded_string(entry.get("observed_at"), 64)
        or not _REPORT_HASH_RE.fullmatch(str(entry.get("report_hash") or ""))
        or not _ENTRY_HASH_RE.fullmatch(str(entry.get("entry_hash") or ""))
        or not source_files
        or len(source_files) > max(1, int(max_sources))
        or len(source_files) != len(entry.get("source_files", []))
        or len({source["path"] for source in source_files}) != len(source_files)
        or any(
            not _is_bounded_string(source["path"], 1_000)
            or not _CONTENT_HASH_RE.fullmatch(source["content_hash"])
            for source in source_files
        )
    ):
        return False
    return str(entry.get("entry_hash") or "") == _report_entry_hash(entry)


def _is_bounded_string(value: Any, limit: int, *, allow_empty: bool = False) -> bool:
    if not isinstance(value, str) or len(value) > limit or "\n" in value or "\r" in value:
        return False
    return allow_empty or bool(value)


def _report_entry_hash(entry: dict[str, Any]) -> str:
    payload = {field: entry.get(field) for field in _ENTRY_HASH_FIELDS}
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _report_entry_id(
    *,
    query: str,
    report_hash: str,
    source_files: list[dict[str, str]],
) -> str:
    source_fingerprints = [f"{source['path']}:{source['content_hash']}" for source in source_files]
    payload = "\n".join([query.casefold(), report_hash, *source_fingerprints])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _query_terms(value: str) -> set[str]:
    text = str(value or "").casefold()
    terms: set[str] = set()
    for token in _ASCII_TERM_RE.findall(text):
        parts = [part for part in re.split(r"[./_-]+", token) if part]
        for candidate in [token, *parts]:
            if len(candidate) >= 2 and candidate not in _STOP_TERMS:
                terms.add(candidate)
    for sequence in _CJK_SEQUENCE_RE.findall(text):
        if len(sequence) == 1:
            if sequence not in _STOP_TERMS:
                terms.add(sequence)
            continue
        if len(sequence) <= 8 and sequence not in _STOP_TERMS:
            terms.add(sequence)
        for index in range(len(sequence) - 1):
            term = sequence[index : index + 2]
            if term not in _STOP_TERMS:
                terms.add(term)
    return terms


def _query_similarity(current_query: str, historical_query: str) -> float:
    current_normalized = _NON_WORD_RE.sub("", current_query.casefold())
    historical_normalized = _NON_WORD_RE.sub("", historical_query.casefold())
    if current_normalized and current_normalized == historical_normalized:
        return 1.0

    current_terms = _query_terms(current_query)
    historical_terms = _query_terms(historical_query)
    if not current_terms or not historical_terms:
        return 0.0
    intersection = current_terms.intersection(historical_terms)
    if not intersection:
        return 0.0
    containment = len(intersection) / min(len(current_terms), len(historical_terms))
    jaccard = len(intersection) / len(current_terms.union(historical_terms))
    sequence_ratio = SequenceMatcher(
        None,
        current_normalized,
        historical_normalized,
        autojunk=False,
    ).ratio()
    return (0.6 * containment) + (0.3 * jaccard) + (0.1 * sequence_ratio)


def _render_candidates(
    candidates: list[dict[str, Any]],
    *,
    max_chars: int,
) -> tuple[str, list[dict[str, Any]]]:
    selected = list(candidates)
    while selected:
        rendered = _render_candidates_text(selected)
        if len(rendered) <= max_chars:
            return rendered, selected
        if len(selected) > 1:
            selected.pop()
            continue
        return rendered[:max_chars].rstrip(), selected
    return "", []


def _render_candidates_text(candidates: list[dict[str, Any]]) -> str:
    lines = ["HISTORICAL_REPORT_CANDIDATES:"]
    for item in candidates:
        source_paths = ", ".join(source["path"] for source in _source_files(item))
        stale_paths = ", ".join(str(path) for path in item.get("stale_paths", []))
        lines.append(
            "- "
            f"session_id={str(item.get('session_id') or '(unavailable)')} | "
            f"report_hash={str(item.get('report_hash') or '')} | "
            f"observed_at={str(item.get('observed_at') or '')} | "
            f"similarity={float(item.get('similarity') or 0.0):.3f} | "
            f"source_state={str(item.get('source_state') or 'stale')}"
        )
        lines.append(f"  prior_query={bounded_single_line(str(item.get('query') or ''), 300)}")
        lines.append(
            f"  historical_root_cause={bounded_single_line(str(item.get('root_cause') or ''), 700)}"
        )
        recommendation = bounded_single_line(str(item.get("recommendation") or ""), 550)
        if recommendation:
            lines.append(f"  historical_recommendation={recommendation}")
        verification = bounded_single_line(str(item.get("verification") or ""), 350)
        if verification:
            lines.append(f"  historical_verification={verification}")
        lines.append(f"  historical_source_paths={bounded_single_line(source_paths, 600)}")
        if stale_paths:
            lines.append(f"  stale_or_missing_paths={bounded_single_line(stale_paths, 600)}")
    return "\n".join(lines)


workspace_report_index = WorkspaceReportIndex()

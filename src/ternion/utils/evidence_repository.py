"""
Structured evidence repository (single source of truth for evidence items).

The repository holds parsed ``EvidenceItem`` objects plus file-level metadata and
renders the canonical ``EVIDENCE_BUNDLE`` text consumed by prompts and persisted
in sessions. Strings exist only at the LLM boundaries:

- parse boundary: LLM bundle output -> structured items (``from_bundle_text``)
- render boundary: structured items -> canonical bundle text (``render_bundle``)

Internal stage-to-stage transfer should use ``to_records()`` / ``from_records()``
(JSON-safe dicts) with the canonical bundle text kept as a derived, in-sync view.

Merging is strictly lossless:
- exact duplicates collapse (purposes merged)
- ranges fully contained in a verified-identical larger excerpt are dropped
- overlapping/adjacent same-format excerpts are spliced only when the shared
  region is verified byte-identical
Conflicting or unverifiable content is always kept as-is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from ternion.utils.evidence_chain import (
    EvidenceItem,
    canonicalize_evidence_path,
    evidence_paths_equivalent,
    hash_excerpt_text,
    parse_evidence_bundle,
)

# Soft budget for the rendered bundle. Exceeding it never drops evidence
# (first-priority principle: evidence completeness beats token savings);
# callers should log for observability so oversized bundles are visible.
EVIDENCE_BUNDLE_SOFT_CAP_CHARS = 50_000

_BUNDLE_HEADER = "EVIDENCE_BUNDLE:"
_FILE_EXCERPT_PREFIX = "- [FILE_EXCERPT]"
_FILE_META_PREFIX = "- [FILE_META]"
_NONE_MARKER = "- None"
_NUMBERED_LINE_RE = re.compile(r"^\s*(\d+)\|")

RECORD_KIND_EXCERPT = "excerpt"
RECORD_KIND_FILE_META = "file_meta"
RECORD_KIND_PRESERVED_TEXT = "preserved_text"


def build_evidence_item(
    *,
    path: str,
    lines: str = "",
    file_total_lines: int | None = None,
    purpose: str = "",
    excerpt: str = "",
) -> EvidenceItem:
    """
    Build an EvidenceItem with derived range and content hashes.

    Args:
        path: File path for the excerpt.
        lines: "start-end" line range string (may be empty).
        file_total_lines: Total lines of the file when known.
        purpose: PURPOSE metadata line content.
        excerpt: Normalized excerpt text (no format indent).

    Returns:
        A fully populated EvidenceItem.
    """
    line_range: tuple[int, int] | None = None
    match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", lines or "")
    if match:
        start, end = int(match.group(1)), int(match.group(2))
        if end >= start:
            line_range = (start, end)
    normalized_excerpt = (excerpt or "").rstrip()
    excerpt_hash = hash_excerpt_text(normalized_excerpt)
    return EvidenceItem(
        path=path,
        lines=(lines or "").strip(),
        line_range=line_range,
        file_total_lines=file_total_lines,
        purpose=(purpose or "").strip(),
        excerpt=normalized_excerpt,
        excerpt_hash=excerpt_hash,
        excerpt_hash_raw=excerpt_hash,
    )


def _merge_purposes(*purposes: str) -> str:
    """Merge purpose strings keeping unique, non-empty entries in order."""
    unique: list[str] = []
    seen: set[str] = set()
    for raw in purposes:
        for part in (raw or "").split(" / "):
            cleaned = part.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            unique.append(cleaned)
    return " / ".join(unique)


def _single_line_purpose(purpose: str) -> str:
    """Collapse a purpose string onto a single protocol-safe line."""
    return re.sub(r"\s*\n\s*", " / ", (purpose or "").strip())


def _excerpt_lines(item: EvidenceItem) -> list[str]:
    return item.excerpt.split("\n") if item.excerpt else []


def _excerpt_format(lines: list[str]) -> str:
    """Classify excerpt line format: "numbered" (every line "N|...") or "plain"."""
    if lines and all(_NUMBERED_LINE_RE.match(line) for line in lines):
        return "numbered"
    return "plain"


def _comparable_lines(lines: list[str], fmt: str) -> list[str]:
    """Return content lines with numbered prefixes stripped for comparison."""
    if fmt == "numbered":
        return [_NUMBERED_LINE_RE.sub("", line, count=1) for line in lines]
    return lines


def _range_line_count_is_sane(item: EvidenceItem, lines: list[str]) -> bool:
    if item.line_range is None:
        return False
    start, end = item.line_range
    return len(lines) == (end - start + 1)


@dataclass
class EvidenceRepository:
    """
    Structured store for evidence items and file-level metadata.

    Attributes:
        items: Parsed evidence excerpts in stable (temporal/range) order.
        file_meta: path -> total_lines learned from FILE_META entries (last-seen wins).
        preserved_text: Verbatim non-protocol payload captured before the first
            protocol entry (kept losslessly for wholly/partially malformed bundles).
    """

    items: list[EvidenceItem] = field(default_factory=list)
    file_meta: dict[str, int] = field(default_factory=dict)
    preserved_text: str = ""

    # ------------------------------------------------------------------
    # Construction (parse boundary)
    # ------------------------------------------------------------------

    @classmethod
    def from_bundle_text(cls, bundle: str) -> EvidenceRepository:
        """
        Parse an EVIDENCE_BUNDLE text into a repository.

        Leading non-protocol lines (before the first FILE_EXCERPT/FILE_META entry)
        are preserved verbatim so malformed payloads are never silently dropped.

        Args:
            bundle: Raw bundle string (with or without the header line).

        Returns:
            A populated EvidenceRepository.
        """
        repo = cls()
        text = (bundle or "").strip()
        if not text:
            return repo

        repo.items = list(parse_evidence_bundle(text))
        repo.file_meta = _parse_file_meta(text)
        repo.preserved_text = _extract_leading_preserved_text(text)
        repo._consolidate()
        return repo

    @classmethod
    def from_records(cls, records: list[dict[str, Any]] | None) -> EvidenceRepository:
        """
        Rebuild a repository from persisted JSON-safe records.

        Args:
            records: Records produced by ``to_records()``.

        Returns:
            A populated EvidenceRepository.
        """
        repo = cls()
        preserved_parts: list[str] = []
        for record in records or []:
            if not isinstance(record, dict):
                continue
            kind = str(record.get("kind") or RECORD_KIND_EXCERPT)
            if kind == RECORD_KIND_PRESERVED_TEXT:
                text = str(record.get("text") or "")
                if text.strip():
                    preserved_parts.append(text)
                continue
            if kind == RECORD_KIND_FILE_META:
                path = str(record.get("path") or "").strip()
                total = record.get("file_total_lines")
                if path and isinstance(total, int) and total > 0:
                    repo.file_meta[path] = total
                continue
            item = _record_to_item(record)
            if item is not None:
                repo.items.append(item)
        repo.preserved_text = "\n".join(preserved_parts)
        # to_records() output is already consolidated, so this is a no-op on the
        # standard path; it keeps the consolidated-repository invariant
        # self-enforcing for hand-built or legacy record payloads.
        repo._consolidate()
        return repo

    @classmethod
    def from_state(
        cls,
        *,
        evidence_items: list[dict[str, Any]] | None,
        evidence_bundle: str,
    ) -> EvidenceRepository:
        """
        Build a repository from workflow/session state.

        Prefers structured records; falls back to parsing the (canonical) bundle
        text for legacy sessions that predate structured persistence.

        Args:
            evidence_items: Structured records when available.
            evidence_bundle: Bundle text fallback.

        Returns:
            A populated EvidenceRepository.
        """
        if evidence_items:
            return cls.from_records(evidence_items)
        return cls.from_bundle_text(evidence_bundle or "")

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def merge_bundle_text(self, bundle: str) -> int:
        """
        Parse and merge another bundle text into this repository.

        Args:
            bundle: Bundle text to merge (e.g. a Phase 1.5 append-only output).

        Returns:
            Number of parsed items ingested (before consolidation).
        """
        incoming = EvidenceRepository.from_bundle_text(bundle)
        if incoming.preserved_text.strip():
            self.preserved_text = (
                f"{self.preserved_text}\n{incoming.preserved_text}".strip("\n")
                if self.preserved_text.strip()
                else incoming.preserved_text
            )
        for path, total in incoming.file_meta.items():
            self.file_meta[path] = total
        self.merge_items(incoming.items)
        return len(incoming.items)

    def merge_items(self, new_items: list[EvidenceItem]) -> None:
        """
        Merge structured items with lossless deduplication and consolidation.

        Args:
            new_items: Items to append before consolidation.
        """
        self.items.extend(item for item in new_items or [] if isinstance(item, EvidenceItem))
        self._consolidate()

    def _consolidate(self) -> None:
        """Run exact dedup + verified subsumption/overlap/adjacency merging."""
        groups = _group_indices_by_equivalent_path(self.items)

        deduped: list[EvidenceItem] = []
        kept_index_map: dict[int, int] = {}
        for group in groups:
            by_key: dict[tuple[str, str], int] = {}
            for idx in group:
                item = self.items[idx]
                key = (item.lines, item.excerpt_hash)
                existing_idx = by_key.get(key)
                if existing_idx is None:
                    by_key[key] = len(deduped)
                    kept_index_map[idx] = len(deduped)
                    deduped.append(item)
                    continue
                existing = deduped[existing_idx]
                merged_purpose = _merge_purposes(existing.purpose, item.purpose)
                total = existing.file_total_lines or item.file_total_lines
                if merged_purpose != existing.purpose or total != existing.file_total_lines:
                    deduped[existing_idx] = replace(
                        existing, purpose=merged_purpose, file_total_lines=total
                    )

        # Restore original temporal order before range consolidation.
        deduped_ordered = [deduped[kept_index_map[idx]] for idx in sorted(kept_index_map)]
        self.items = _consolidate_ranges(deduped_ordered)

    # ------------------------------------------------------------------
    # Serialization / rendering (render boundary)
    # ------------------------------------------------------------------

    def is_empty(self) -> bool:
        """Return True when the repository holds no evidence payload at all."""
        return not self.items and not self.file_meta and not self.preserved_text.strip()

    def to_records(self) -> list[dict[str, Any]]:
        """Serialize the repository to JSON-safe records (first-class persistence)."""
        records: list[dict[str, Any]] = []
        if self.preserved_text.strip():
            records.append(
                {
                    "kind": RECORD_KIND_PRESERVED_TEXT,
                    "text": self.preserved_text,
                }
            )
        for item in self.items:
            records.append(
                {
                    "kind": RECORD_KIND_EXCERPT,
                    "path": item.path,
                    "lines": item.lines,
                    "line_range": list(item.line_range) if item.line_range else None,
                    "file_total_lines": item.file_total_lines,
                    "purpose": item.purpose,
                    "excerpt": item.excerpt,
                    "excerpt_hash": item.excerpt_hash,
                    "excerpt_hash_raw": item.excerpt_hash_raw,
                }
            )
        for path, total in self.file_meta.items():
            records.append(
                {
                    "kind": RECORD_KIND_FILE_META,
                    "path": path,
                    "file_total_lines": total,
                }
            )
        return records

    def render_bundle(self) -> str:
        """
        Render the canonical EVIDENCE_BUNDLE text.

        The output is deterministic for a given repository content, which keeps
        the prompt prefix byte-stable across tool-loop rounds (prompt caching).

        Returns:
            Canonical bundle string, "EVIDENCE_BUNDLE:\\n- None" when empty.
        """
        if self.is_empty():
            return f"{_BUNDLE_HEADER}\n{_NONE_MARKER}"

        blocks: list[str] = [_BUNDLE_HEADER]
        if self.preserved_text.strip():
            blocks.append(self.preserved_text.rstrip())
        for item in self.items:
            header = f"{_FILE_EXCERPT_PREFIX} path={item.path}"
            if item.lines:
                header += f" | lines={item.lines}"
            if item.file_total_lines:
                header += f" | total_lines={item.file_total_lines}"
            lines: list[str] = [header]
            purpose = _single_line_purpose(item.purpose)
            if purpose:
                lines.append(f"  PURPOSE: {purpose}")
            lines.append("  EXCERPT_BEGIN")
            for excerpt_line in _excerpt_lines(item):
                lines.append(f"  {excerpt_line}")
            lines.append("  EXCERPT_END")
            blocks.append("\n".join(lines))
        for path, total in self.file_meta.items():
            blocks.append(f"{_FILE_META_PREFIX} path={path} | total_lines={total}")
        return "\n".join(blocks)


def _record_to_item(record: dict[str, Any]) -> EvidenceItem | None:
    path = str(record.get("path") or "")
    if not path:
        return None
    lines = str(record.get("lines") or "")
    line_range_raw = record.get("line_range")
    line_range: tuple[int, int] | None = None
    if (
        isinstance(line_range_raw, (list, tuple))
        and len(line_range_raw) == 2
        and all(isinstance(v, int) for v in line_range_raw)
    ):
        line_range = (line_range_raw[0], line_range_raw[1])
    total_raw = record.get("file_total_lines")
    file_total_lines = total_raw if isinstance(total_raw, int) and total_raw > 0 else None
    excerpt = str(record.get("excerpt") or "")
    excerpt_hash = str(record.get("excerpt_hash") or "") or hash_excerpt_text(excerpt)
    excerpt_hash_raw = str(record.get("excerpt_hash_raw") or "") or excerpt_hash
    return EvidenceItem(
        path=path,
        lines=lines,
        line_range=line_range,
        file_total_lines=file_total_lines,
        purpose=str(record.get("purpose") or ""),
        excerpt=excerpt,
        excerpt_hash=excerpt_hash,
        excerpt_hash_raw=excerpt_hash_raw,
    )


def _parse_file_meta(bundle: str) -> dict[str, int]:
    """Collect FILE_META total_lines entries (last-seen per path wins)."""
    meta: dict[str, int] = {}
    for raw in (bundle or "").splitlines():
        stripped = raw.strip()
        if not stripped.startswith(_FILE_META_PREFIX):
            continue
        header = stripped[len(_FILE_META_PREFIX) :].strip()
        fields: dict[str, str] = {}
        for part in header.split("|"):
            part = part.strip()
            if "=" in part:
                key, value = part.split("=", 1)
                fields[key.strip()] = value.strip()
        path = fields.get("path", "").strip().strip('"').strip("'").strip("`")
        total_text = fields.get("total_lines", "").strip()
        if path and total_text.isdigit() and int(total_text) > 0:
            meta[path] = int(total_text)
    return meta


def _extract_leading_preserved_text(bundle: str) -> str:
    """
    Capture non-protocol lines between the header and the first protocol entry.

    This keeps wholly or partially malformed LLM payloads visible instead of
    silently dropping them during canonicalization.
    """
    lines = (bundle or "").splitlines()
    collected: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped == _BUNDLE_HEADER:
            continue
        if stripped.startswith((_FILE_EXCERPT_PREFIX, _FILE_META_PREFIX)):
            break
        if stripped == _NONE_MARKER:
            continue
        collected.append(raw)
    text = "\n".join(collected).strip("\n")
    return text if text.strip() else ""


def _group_indices_by_equivalent_path(items: list[EvidenceItem]) -> list[list[int]]:
    """
    Group item indices by best-effort path equivalence.

    Suffix matching keeps absolute and repo-relative notations of the same file
    in one group so cross-phase duplicates can consolidate.

    Inherited assumption (same heuristic the reconcile matching layer accepted):
    a repo-relative path and an absolute path sharing that suffix refer to the
    same file. Two genuinely different files could collide only when they share
    the suffix AND byte-identical content at the same line range (every merge is
    content-verified), in which case a duplicate path notation is collapsed but
    no excerpt content is lost.
    """
    groups: list[list[int]] = []
    representatives: list[str] = []
    exact: dict[str, int] = {}
    for idx, item in enumerate(items):
        canonical = canonicalize_evidence_path(item.path)
        group_idx = exact.get(canonical)
        if group_idx is None:
            for candidate_idx, representative in enumerate(representatives):
                if evidence_paths_equivalent(representative, canonical):
                    group_idx = candidate_idx
                    break
        if group_idx is None:
            group_idx = len(groups)
            groups.append([])
            representatives.append(canonical)
        exact[canonical] = group_idx
        groups[group_idx].append(idx)
    return groups


def _consolidate_ranges(items: list[EvidenceItem]) -> list[EvidenceItem]:
    """
    Consolidate same-file range items via verified subsumption/overlap/adjacency.

    Items without a range, with inconsistent line counts, or whose shared content
    fails verification are kept untouched (conservative, lossless).
    """
    removed: set[int] = set()
    replaced: dict[int, EvidenceItem] = {}

    for indices in _group_indices_by_equivalent_path(items):
        mergeable: list[int] = []
        for idx in indices:
            item = replaced.get(idx, items[idx])
            lines = _excerpt_lines(item)
            if _range_line_count_is_sane(item, lines):
                mergeable.append(idx)
        if len(mergeable) < 2:
            continue

        mergeable.sort(key=lambda i: (replaced.get(i, items[i]).line_range or (0, 0)))
        current_idx = mergeable[0]
        for next_idx in mergeable[1:]:
            current = replaced.get(current_idx, items[current_idx])
            candidate = replaced.get(next_idx, items[next_idx])
            merged = _try_merge_pair(current, candidate)
            if merged is None:
                current_idx = next_idx
                continue
            replaced[current_idx] = merged
            removed.add(next_idx)

    result: list[EvidenceItem] = []
    for idx, item in enumerate(items):
        if idx in removed:
            continue
        result.append(replaced.get(idx, item))
    return result


def _try_merge_pair(current: EvidenceItem, candidate: EvidenceItem) -> EvidenceItem | None:
    """
    Try to merge two same-file range items (current.start <= candidate.start).

    Returns:
        The merged item, or None when merging would not be verifiably lossless.
    """
    if current.line_range is None or candidate.line_range is None:
        return None
    cur_start, cur_end = current.line_range
    cand_start, cand_end = candidate.line_range

    cur_lines = _excerpt_lines(current)
    cand_lines = _excerpt_lines(candidate)
    cur_fmt = _excerpt_format(cur_lines)
    cand_fmt = _excerpt_format(cand_lines)

    merged_purpose = _merge_purposes(current.purpose, candidate.purpose)
    merged_total = current.file_total_lines or candidate.file_total_lines

    # Subsumption: candidate fully inside current; verified on content lines so
    # numbered and plain excerpts of the same region can still collapse.
    if cand_end <= cur_end:
        offset = cand_start - cur_start
        cur_cmp = _comparable_lines(cur_lines, cur_fmt)
        cand_cmp = _comparable_lines(cand_lines, cand_fmt)
        if cur_cmp[offset : offset + len(cand_cmp)] != cand_cmp:
            return None
        return replace(current, purpose=merged_purpose, file_total_lines=merged_total)

    # Overlap/adjacency splice requires the same raw line format.
    if cur_fmt != cand_fmt:
        return None
    if cand_start > cur_end + 1:
        return None

    if cand_start <= cur_end:
        overlap_len = cur_end - cand_start + 1
        if cur_lines[-overlap_len:] != cand_lines[:overlap_len]:
            return None
        merged_lines = cur_lines + cand_lines[overlap_len:]
    else:
        merged_lines = cur_lines + cand_lines

    merged_excerpt = "\n".join(merged_lines)
    merged_hash = hash_excerpt_text(merged_excerpt)
    return EvidenceItem(
        path=current.path,
        lines=f"{cur_start}-{cand_end}",
        line_range=(cur_start, cand_end),
        file_total_lines=merged_total,
        purpose=merged_purpose,
        excerpt=merged_excerpt,
        excerpt_hash=merged_hash,
        excerpt_hash_raw=merged_hash,
    )


def canonicalize_evidence_bundle_text(bundle: str) -> tuple[str, list[dict[str, Any]]]:
    """
    Canonicalize a bundle text through the repository.

    Args:
        bundle: Raw bundle string (LLM output or legacy session value).

    Returns:
        Tuple of (canonical_bundle_text, structured_records).
    """
    repo = EvidenceRepository.from_bundle_text(bundle)
    return repo.render_bundle(), repo.to_records()


def derive_evidence_records(bundle: str) -> list[dict[str, Any]]:
    """
    Derive structured records from a bundle text (session persistence helper).

    Args:
        bundle: Bundle string (canonical or legacy).

    Returns:
        JSON-safe records mirroring the bundle content.
    """
    return EvidenceRepository.from_bundle_text(bundle).to_records()

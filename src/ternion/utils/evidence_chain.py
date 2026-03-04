"""
Deterministic evidence chain parsing and reconciliation utilities.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_FILE_EXCERPT_PREFIX = "- [FILE_EXCERPT]"
_FILE_META_PREFIX = "- [FILE_META]"
_BUNDLE_HEADER = "EVIDENCE_BUNDLE:"
_GAPS_HEADER = "EVIDENCE_GAPS:"
_PURPOSE_PREFIX = "PURPOSE:"
_MISSING_PURPOSE_TAG = "[MISSING_PURPOSE]"
MatchScope = Literal[
    "range_level",
    "range_level_partial",
    "file_level",
    "file_level_partial",
    "file_level_full",
    "none",
]


@dataclass(frozen=True)
class EvidenceItem:
    """Parsed evidence item from an evidence bundle."""

    # excerpt_hash uses normalized excerpt lines for stable references.
    # excerpt_hash_raw retains tool output formatting for traceability and may vary.
    path: str
    lines: str
    line_range: tuple[int, int] | None
    file_total_lines: int | None
    purpose: str
    excerpt: str
    excerpt_hash: str
    excerpt_hash_raw: str


@dataclass(frozen=True)
class EvidenceRequest:
    """Parsed evidence request from council analyses."""

    request_id: str
    request: str
    purpose: str
    path: str | None
    lines: str | None
    ref: str | None


def _strip_optional_bullet(line: str) -> str:
    """Strip leading '- ' bullet from a line if present."""
    stripped = line.lstrip()
    if stripped.startswith("- "):
        return stripped[2:].lstrip()
    return stripped


def _extract_purpose(line: str) -> str | None:
    """Extract PURPOSE value from a line, or None if not a purpose line."""
    normalized = _strip_optional_bullet(line).strip()
    if normalized.upper().startswith(_PURPOSE_PREFIX):
        return normalized[len(_PURPOSE_PREFIX) :].strip()
    return None


def _strip_format_indent(line: str) -> str:
    """Strip the 2-space format indent used inside EXCERPT blocks."""
    if line.startswith("  "):
        return line[2:]
    return line


def _parse_header_fields(header: str) -> dict[str, str]:
    """Parse 'key=value | key=value' header into a dict."""
    fields: dict[str, str] = {}
    for part in header.split("|"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key.strip()] = value.strip()
    return fields


def _parse_line_range(value: str | None) -> tuple[int, int] | None:
    """Parse a 'start-end' line range string into a tuple, or None."""
    if not value:
        return None
    match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*(?:$|\s)", value)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    if end < start:
        return None
    return start, end


def _parse_total_lines(value: str | None) -> int | None:
    """Parse a positive integer total_lines value, or None."""
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned.isdigit():
        return None
    total = int(cleaned)
    if total <= 0:
        return None
    return total


def _normalize_path(path: str | None) -> str:
    """Strip whitespace and surrounding quotes/backticks from a path."""
    if not path:
        return ""
    cleaned = path.strip().strip('"').strip("'").strip("`")
    return cleaned


# Strip trailing annotations: fullwidth parens "（...）" or whitespace+ASCII parens " (...)".
_CN_PAREN_TAIL_RE = re.compile(r"（.*$")
_WS_PAREN_TAIL_RE = re.compile(r"\s+\(.*$")
_TRAILING_PUNCT_CHARS = "，,。.;；"


def _clean_path_value(value: str | None) -> str:
    """
    Normalize a path-like field value from evidence requests/gaps.

    This is intentionally conservative: it strips surrounding quotes/backticks and removes
    trailing annotation text in fullwidth parentheses "（...）" or in whitespace-delimited
    parentheses " (...)".
    """
    cleaned = _normalize_path(value)
    if not cleaned:
        return ""
    cleaned = cleaned.split("|", 1)[0].strip()
    cleaned = _CN_PAREN_TAIL_RE.sub("", cleaned).strip()
    cleaned = _WS_PAREN_TAIL_RE.sub("", cleaned).strip()
    return cleaned.rstrip(_TRAILING_PUNCT_CHARS).strip()


def _canonicalize_path_for_match(value: str | None) -> str:
    """
    Canonicalize a path string for best-effort matching.

    Notes:
    - This does NOT resolve relative paths to absolute paths.
    - This does expand "~" when present.
    """
    s = _clean_path_value(value)
    if not s:
        return ""
    s = s.replace("\\", "/")
    s = re.sub(r"/{2,}", "/", s).strip()
    if s.startswith("./"):
        s = s[2:]
    if s.startswith("~"):
        with contextlib.suppress(Exception):
            s = str(Path(s).expanduser())
        s = s.replace("\\", "/")
        s = re.sub(r"/{2,}", "/", s).strip()
    return s


def _is_absolute_like(path: str) -> bool:
    if not path:
        return False
    if path.startswith(("/", "\\")):
        return True
    return bool(re.match(r"^[A-Za-z]:/", path))


def _paths_equivalent(left: str | None, right: str | None) -> bool:
    left_canon = _canonicalize_path_for_match(left)
    right_canon = _canonicalize_path_for_match(right)
    if not left_canon or not right_canon:
        return False
    if left_canon == right_canon:
        return True
    left_abs = _is_absolute_like(left_canon)
    right_abs = _is_absolute_like(right_canon)
    if not left_abs and right_abs and right_canon.endswith("/" + left_canon):
        return True
    return bool(left_abs and not right_abs and left_canon.endswith("/" + right_canon))


def _lookup_total_lines_info(
    target_path: str,
    total_lines_index: dict[str, dict[str, object]],
) -> dict[str, object] | None:
    if not target_path or not isinstance(total_lines_index, dict):
        return None
    direct = total_lines_index.get(target_path)
    if isinstance(direct, dict):
        return direct

    candidates: list[tuple[int, dict[str, object]]] = []
    for key, info in total_lines_index.items():
        if not isinstance(info, dict):
            continue
        if _paths_equivalent(target_path, key):
            candidates.append((len(str(key)), info))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _hash_excerpt(excerpt: str) -> str:
    digest = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    return digest[:16]


def parse_evidence_bundle(bundle: str) -> list[EvidenceItem]:
    """
    Parse evidence bundle into structured evidence items.
    """
    lines = (bundle or "").splitlines()
    items: list[EvidenceItem] = []
    idx = 0
    while idx < len(lines):
        raw = lines[idx]
        stripped = raw.strip()
        if stripped.startswith(_FILE_EXCERPT_PREFIX):
            header = stripped[len(_FILE_EXCERPT_PREFIX) :].strip()
            fields = _parse_header_fields(header)
            path = _normalize_path(fields.get("path", ""))
            lines_value = fields.get("lines", "").strip()
            line_range = _parse_line_range(lines_value)
            file_total_lines = _parse_total_lines(fields.get("total_lines"))
            purpose = ""
            idx += 1
            while idx < len(lines):
                candidate = lines[idx].strip()
                if candidate == "EXCERPT_BEGIN":
                    idx += 1
                    break
                maybe_purpose = _extract_purpose(lines[idx])
                if maybe_purpose is not None:
                    purpose = maybe_purpose
                idx += 1
            excerpt_lines: list[str] = []
            excerpt_lines_raw: list[str] = []
            while idx < len(lines):
                candidate = lines[idx].strip()
                if candidate == "EXCERPT_END":
                    idx += 1
                    break
                excerpt_lines_raw.append(lines[idx])
                excerpt_lines.append(_strip_format_indent(lines[idx]))
                idx += 1
            excerpt = "\n".join(excerpt_lines).rstrip()
            excerpt_raw = "\n".join(excerpt_lines_raw).rstrip()
            items.append(
                EvidenceItem(
                    path=path,
                    lines=lines_value,
                    line_range=line_range,
                    file_total_lines=file_total_lines,
                    purpose=purpose,
                    excerpt=excerpt,
                    excerpt_hash=_hash_excerpt(excerpt),
                    excerpt_hash_raw=_hash_excerpt(excerpt_raw),
                )
            )
            continue
        idx += 1
    return items


def _parse_total_lines_index(bundle: str) -> dict[str, dict[str, object]]:
    """
    Build a per-path total_lines index from an evidence bundle.

    Selection rule:
    - Treat the evidence bundle as append-only and use the *latest* (last-seen)
      positive total_lines value for a given path.
    """
    lines = (bundle or "").splitlines()
    totals_by_path: dict[str, list[int]] = {}
    for raw in lines:
        stripped = (raw or "").strip()
        if stripped.startswith(_FILE_META_PREFIX):
            header = stripped[len(_FILE_META_PREFIX) :].strip()
        elif stripped.startswith(_FILE_EXCERPT_PREFIX):
            header = stripped[len(_FILE_EXCERPT_PREFIX) :].strip()
        else:
            continue

        fields = _parse_header_fields(header)
        path = _normalize_path(fields.get("path", ""))
        total = _parse_total_lines(fields.get("total_lines"))
        if not path or total is None:
            continue
        totals_by_path.setdefault(path, []).append(total)

    index: dict[str, dict[str, object]] = {}
    for path, totals in totals_by_path.items():
        if not totals:
            continue
        candidates: list[int] = []
        seen: set[int] = set()
        for item in totals:
            if item in seen:
                continue
            seen.add(item)
            candidates.append(item)
        selected = totals[-1]
        index[path] = {
            "total_lines_selected": selected,
            "total_lines_candidates": candidates,
            "total_lines_conflict": len(candidates) > 1,
            "total_lines_source": "bundle_latest",
        }
    return index


def _extract_field(text: str, key: str) -> str | None:
    if not text or not key:
        return None
    pattern = re.compile(
        rf"(?:^|\s){re.escape(key)}\s*=\s*(?P<value>.+?)(?=\s+\w+\s*=|\s*\|\s*|$)",
        flags=re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    value = match.group("value").strip()
    return value or None


def _split_path_and_lines(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    cleaned = _clean_path_value(value)
    match = re.match(r"^(.*):(\d+\s*-\s*\d+)(?:\s+.*)?$", cleaned)
    if match:
        return _clean_path_value(match.group(1)), match.group(2).replace(" ", "")
    return cleaned, None


def _looks_like_path(value: str) -> bool:
    if "/" in value or "\\" in value:
        return True
    lowered = value.lower()
    return lowered.endswith((".py", ".js", ".ts", ".tsx", ".json", ".yaml", ".yml", ".md"))


def _extract_target_from_ref(ref: str | None) -> tuple[str | None, str | None]:
    if not ref:
        return None, None
    cleaned = _clean_path_value(ref)
    match = re.match(r"^(.*):(\d+\s*-\s*\d+)(?:\s+.*)?$", cleaned)
    if match:
        return _clean_path_value(match.group(1)), match.group(2).replace(" ", "")
    if _looks_like_path(cleaned):
        return _clean_path_value(cleaned), None
    return None, None


def merge_adjacent_or_overlapping_ranges(
    ranges: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """
    Merge ranges using the rule: merge only when overlapping or adjacent.
    """
    normalized: list[tuple[int, int]] = []
    for start, end in ranges or []:
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start <= 0 or end <= 0:
            continue
        if end < start:
            continue
        normalized.append((start, end))
    if not normalized:
        return []

    normalized.sort(key=lambda r: (r[0], r[1]))
    merged: list[tuple[int, int]] = []
    cur_start, cur_end = normalized[0]
    for start, end in normalized[1:]:
        if start <= cur_end + 1:
            cur_end = max(cur_end, end)
            continue
        merged.append((cur_start, cur_end))
        cur_start, cur_end = start, end
    merged.append((cur_start, cur_end))
    return merged


def compute_missing_ranges(
    *,
    request_range: tuple[int, int],
    covered_ranges: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """
    Compute missing subranges within request_range that are not covered.
    """
    start, end = request_range
    if start <= 0 or end <= 0 or end < start:
        return []

    clipped: list[tuple[int, int]] = []
    for c_start, c_end in covered_ranges or []:
        if not isinstance(c_start, int) or not isinstance(c_end, int):
            continue
        if c_end < c_start:
            continue
        if c_end < start or c_start > end:
            continue
        clipped.append((max(start, c_start), min(end, c_end)))

    merged = merge_adjacent_or_overlapping_ranges(clipped)
    if not merged:
        return [(start, end)]

    gaps: list[tuple[int, int]] = []
    cursor = start
    for seg_start, seg_end in merged:
        if seg_start > cursor:
            gaps.append((cursor, seg_start - 1))
        cursor = max(cursor, seg_end + 1)
        if cursor > end:
            break
    if cursor <= end:
        gaps.append((cursor, end))
    return gaps


def is_deterministic_range_request(
    request: EvidenceRequest,
) -> tuple[str, tuple[int, int]] | None:
    """
    Return (path, line_range) when the request is a deterministic single-file range request.
    """
    target_path, request_range = _resolve_request_target(request)
    if not target_path or request_range is None:
        return None

    start, end = request_range
    if start < 1 or end < start:
        return None

    cleaned = _normalize_path(target_path)
    if not cleaned:
        return None
    if cleaned.startswith(("~", "/", "\\")):
        return None
    cleaned = cleaned.removeprefix("./").removeprefix(".\\")
    if ":" in cleaned:
        return None
    if any(ch.isspace() for ch in cleaned):
        return None
    parts = [p for p in re.split(r"[\\/]+", cleaned) if p]
    if any(p == ".." for p in parts):
        return None
    normalized = "/".join(parts)
    if not normalized:
        return None
    return normalized, (start, end)


def parse_evidence_requests(requests: str) -> list[EvidenceRequest]:
    """
    Parse evidence requests and associated PURPOSE lines into structured entries.
    """
    lines = [line for line in (requests or "").splitlines() if line.strip()]
    entries: list[EvidenceRequest] = []
    current_request: str | None = None
    current_purpose: str = ""

    def is_none_marker(line: str) -> bool:
        normalized = line.strip().lower()
        return normalized in ("- [p0] none", "[p0] none")

    if not lines:
        return []
    if len(lines) == 1 and is_none_marker(lines[0]):
        return []

    for raw in lines:
        if is_none_marker(raw):
            continue
        maybe_purpose = _extract_purpose(raw)
        if maybe_purpose is not None:
            if current_request is not None and not current_purpose:
                current_purpose = maybe_purpose
            continue
        if current_request is not None:
            entries.append(_build_request_entry(current_request, current_purpose))
        current_request = raw.strip()
        current_purpose = ""

    if current_request is not None:
        entries.append(_build_request_entry(current_request, current_purpose))
    return entries


def _build_request_entry(request_line: str, purpose: str) -> EvidenceRequest:
    normalized = _strip_optional_bullet(request_line).strip()
    path_field = _extract_field(normalized, "path") or _extract_field(normalized, "file")
    lines_field = _extract_field(normalized, "lines")
    ref_field = _extract_field(normalized, "ref")
    path, path_lines = _split_path_and_lines(path_field)
    if not lines_field and path_lines:
        lines_field = path_lines
    request_id = _hash_request_id(normalized, purpose)
    return EvidenceRequest(
        request_id=request_id,
        request=normalized,
        purpose=purpose,
        path=path,
        lines=lines_field,
        ref=ref_field,
    )


def _hash_request_id(request: str, purpose: str) -> str:
    payload = f"{request}\n{purpose}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _resolve_request_target(
    request: EvidenceRequest,
) -> tuple[str | None, tuple[int, int] | None]:
    target_path = _normalize_path(request.path)
    target_lines = request.lines
    if not target_path and request.ref:
        ref_path, ref_lines = _extract_target_from_ref(request.ref)
        target_path = _normalize_path(ref_path)
        if not target_lines:
            target_lines = ref_lines
    return target_path or None, _parse_line_range(target_lines)


def _clip_range_to_eof_if_possible(
    *,
    target_path: str,
    request_range: tuple[int, int],
    total_lines_index: dict[str, dict[str, object]],
) -> tuple[tuple[int, int], dict[str, object]]:
    info = _lookup_total_lines_info(target_path, total_lines_index)
    total_lines_selected: int | None = None
    total_lines_candidates: list[object] = []
    total_lines_conflict = False
    total_lines_source = ""
    if isinstance(info, dict):
        selected_raw = info.get("total_lines_selected")
        if isinstance(selected_raw, int):
            total_lines_selected = selected_raw

        candidates_raw = info.get("total_lines_candidates")
        if isinstance(candidates_raw, list):
            total_lines_candidates = list(candidates_raw)

        conflict_raw = info.get("total_lines_conflict")
        if isinstance(conflict_raw, bool):
            total_lines_conflict = conflict_raw

        source_raw = info.get("total_lines_source")
        if isinstance(source_raw, str):
            total_lines_source = source_raw
    if total_lines_selected is None or total_lines_selected <= 0:
        return request_range, {}

    start, end = request_range
    clipped_range = request_range
    clip_applied = bool(end > total_lines_selected and total_lines_selected >= start)
    if clip_applied:
        clipped_range = (start, total_lines_selected)

    meta: dict[str, object] = {
        "total_lines_selected": total_lines_selected,
        "total_lines_candidates": total_lines_candidates,
        "total_lines_conflict": total_lines_conflict,
        "total_lines_source": total_lines_source,
        "eof_clip_applied": clip_applied,
    }
    return clipped_range, meta


def _match_request_to_evidence(
    request: EvidenceRequest,
    evidence: list[EvidenceItem],
    *,
    total_lines_index: dict[str, dict[str, object]],
) -> tuple[list[EvidenceItem], MatchScope, dict[str, object]]:
    target_path, request_range = _resolve_request_target(request)
    if not target_path:
        return [], "none", {}
    matches: list[EvidenceItem] = []
    if request_range is not None:
        effective_range, clip_meta = _clip_range_to_eof_if_possible(
            target_path=target_path,
            request_range=request_range,
            total_lines_index=total_lines_index,
        )
        request_range = effective_range
        for item in evidence:
            if not _paths_equivalent(item.path, target_path):
                continue
            if item.line_range is None:
                continue
            if not _ranges_overlap(item.line_range, request_range):
                continue
            matches.append(item)
        if not matches:
            return [], "none", clip_meta
        ranges = [item.line_range for item in matches if item.line_range is not None]
        if _range_is_fully_covered(request_range, ranges):
            return matches, "range_level", clip_meta
        return matches, "range_level_partial", clip_meta

    for item in evidence:
        if not _paths_equivalent(item.path, target_path):
            continue
        matches.append(item)
    return matches, "file_level" if matches else "none", {}


def _is_full_file_covered(
    path: str,
    evidence_items: list[EvidenceItem],
    *,
    total_lines_index: dict[str, dict[str, object]],
) -> bool:
    if not path:
        return False
    matching = [item for item in evidence_items if _paths_equivalent(item.path, path)]
    if not matching:
        return False
    info = _lookup_total_lines_info(path, total_lines_index)
    total_lines: int | None = None
    if isinstance(info, dict):
        selected_raw = info.get("total_lines_selected")
        if isinstance(selected_raw, int):
            total_lines = selected_raw
    if total_lines is None or total_lines <= 0:
        return False
    segments: list[tuple[int, int]] = []
    for item in matching:
        if item.line_range is None:
            continue
        segments.append(item.line_range)
    if not segments:
        return False
    segments.sort(key=lambda r: (r[0], r[1]))
    if segments[0][0] != 1:
        return False
    current_end = segments[0][1]
    for start, end in segments[1:]:
        if start > current_end + 1:
            return False
        current_end = max(current_end, end)
    return current_end >= total_lines


def _parse_gap_lines(gaps: str) -> list[str]:
    text = (gaps or "").strip()
    if not text:
        return []
    lines = text.splitlines()
    in_gaps = False
    collected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == _GAPS_HEADER:
            in_gaps = True
            continue
        if stripped == _BUNDLE_HEADER:
            in_gaps = False
            continue
        if not in_gaps and stripped and _GAPS_HEADER not in text:
            collected.append(stripped)
            continue
        if in_gaps and stripped:
            if stripped == "- None":
                continue
            collected.append(stripped)
    return collected


def _gap_target(line: str) -> tuple[str | None, str | None]:
    normalized = _strip_optional_bullet(line).strip()
    path_field = _extract_field(normalized, "path")
    lines_field = _extract_field(normalized, "lines")
    ref_field = _extract_field(normalized, "ref")
    path, path_lines = _split_path_and_lines(path_field)
    if not lines_field and path_lines:
        lines_field = path_lines
    if not path and ref_field:
        ref_path, ref_lines = _extract_target_from_ref(ref_field)
        path = ref_path
        if not lines_field:
            lines_field = ref_lines
    return _normalize_path(path), lines_field


def _gap_key(line: str) -> str:
    prefix = "missing_purpose|" if _MISSING_PURPOSE_TAG in line else ""
    path, lines = _gap_target(line)
    if path and lines:
        return f"{prefix}path={path}|lines={lines}"
    if path:
        return f"{prefix}path={path}"
    ref_field = _extract_field(_strip_optional_bullet(line).strip(), "ref")
    if ref_field:
        return f"{prefix}ref={ref_field.strip()}"
    return f"{prefix}line={line.strip()}"


def _gap_is_missing_purpose(line: str) -> bool:
    return _MISSING_PURPOSE_TAG in line


def _build_missing_purpose_gap(item: EvidenceItem) -> str | None:
    path = _normalize_path(item.path)
    if not path:
        return None
    if item.lines:
        return f"- {_MISSING_PURPOSE_TAG} ref={path}:{item.lines}"
    return f"- {_MISSING_PURPOSE_TAG} path={path}"


def _collect_missing_purpose_gaps(evidence_items: list[EvidenceItem]) -> list[str]:
    gaps: list[str] = []
    for item in evidence_items:
        if (item.purpose or "").strip():
            continue
        gap_line = _build_missing_purpose_gap(item)
        if gap_line:
            gaps.append(gap_line)
    return gaps


def _ranges_overlap(
    left: tuple[int, int],
    right: tuple[int, int],
) -> bool:
    return not (left[1] < right[0] or left[0] > right[1])


def _range_is_fully_covered(
    request_range: tuple[int, int],
    evidence_ranges: list[tuple[int, int]],
) -> bool:
    if not evidence_ranges:
        return False
    start, end = request_range
    if start > end:
        return False
    clipped: list[tuple[int, int]] = []
    for r_start, r_end in evidence_ranges:
        if not _ranges_overlap((r_start, r_end), request_range):
            continue
        clipped.append((max(start, r_start), min(end, r_end)))
    if not clipped:
        return False
    clipped.sort(key=lambda r: (r[0], r[1]))
    if clipped[0][0] > start:
        return False
    current_end = clipped[0][1]
    for seg_start, seg_end in clipped[1:]:
        if seg_start > current_end + 1:
            return False
        current_end = max(current_end, seg_end)
        if current_end >= end:
            return True
    return current_end >= end


def _build_gap_from_request(request: EvidenceRequest) -> str:
    path = _normalize_path(request.path)
    if path:
        if request.lines:
            return f"- [MISSING_LOCATION] ref={path}:{request.lines}"
        return f"- [MISSING_FILE] path={path}"
    if request.ref:
        return f"- [MISSING_LOCATION] ref={request.ref}"
    return f"- [MISSING_LOCATION] ref={request.request}"


def _build_evidence_gaps(lines: list[str]) -> str:
    if not lines:
        return f"{_GAPS_HEADER}\n- None"
    return f"{_GAPS_HEADER}\n" + "\n".join(lines)


def reconcile_evidence_chain(
    *,
    evidence_bundle: str,
    evidence_gaps: str,
    evidence_requests: str,
) -> tuple[str, list[dict[str, object]]]:
    """
    Reconcile evidence requests/gaps against evidence bundle.

    Returns:
        (reconciled_gaps, evidence_chain_index)
    """
    evidence_items = parse_evidence_bundle(evidence_bundle)
    total_lines_index = _parse_total_lines_index(evidence_bundle)
    requests = parse_evidence_requests(evidence_requests)
    gap_lines = _parse_gap_lines(evidence_gaps)

    chain_index: list[dict[str, object]] = []
    unsatisfied_requests: list[EvidenceRequest] = []
    for request in requests:
        matches, match_scope, clip_meta = _match_request_to_evidence(
            request,
            evidence_items,
            total_lines_index=total_lines_index,
        )
        target_path, request_range = _resolve_request_target(request)
        if request_range is None and target_path:
            full_covered = _is_full_file_covered(
                target_path,
                evidence_items,
                total_lines_index=total_lines_index,
            )
            if full_covered:
                match_scope = "file_level_full"
            else:
                match_scope = "file_level_partial" if matches else "none"
        satisfied = bool(matches) and match_scope in {"range_level", "file_level_full"}
        refs = [
            {
                "path": item.path,
                "lines": item.lines,
                "excerpt_hash": item.excerpt_hash,
                "excerpt_hash_raw": item.excerpt_hash_raw,
                "total_lines": item.file_total_lines,
            }
            for item in matches
        ]
        chain_index.append(
            {
                "request_id": request.request_id,
                "request": request.request,
                "purpose": request.purpose,
                "satisfied": satisfied,
                "match_scope": match_scope,
                "evidence_refs": refs,
                **(
                    clip_meta
                    if isinstance(clip_meta, dict)
                    and (
                        bool(clip_meta.get("eof_clip_applied"))
                        or bool(clip_meta.get("total_lines_conflict"))
                    )
                    else {}
                ),
            }
        )
        if not satisfied:
            unsatisfied_requests.append(request)

    reconciled: list[str] = []
    seen_keys: set[str] = set()
    for line in gap_lines:
        if _gap_is_missing_purpose(line):
            key = _gap_key(line)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            reconciled.append(line)
            continue
        path, lines = _gap_target(line)
        target_range = _parse_line_range(lines)
        if path and target_range is not None:
            target_range, _ = _clip_range_to_eof_if_possible(
                target_path=path,
                request_range=target_range,
                total_lines_index=total_lines_index,
            )
            ranges = [
                item.line_range
                for item in evidence_items
                if _paths_equivalent(item.path, path) and item.line_range is not None
            ]
            if _range_is_fully_covered(target_range, ranges):
                continue
        if (
            path
            and target_range is None
            and _is_full_file_covered(
                path,
                evidence_items,
                total_lines_index=total_lines_index,
            )
        ):
            continue
        key = _gap_key(line)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        reconciled.append(line)

    for request in unsatisfied_requests:
        gap_line = _build_gap_from_request(request)
        key = _gap_key(gap_line)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        reconciled.append(gap_line)

    for gap_line in _collect_missing_purpose_gaps(evidence_items):
        key = _gap_key(gap_line)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        reconciled.append(gap_line)

    return _build_evidence_gaps(reconciled), chain_index


def merge_missing_purpose_gaps(
    *,
    evidence_bundle: str,
    evidence_gaps: str,
) -> str:
    """
    Ensure missing PURPOSE metadata is surfaced as evidence gaps.
    """
    evidence_items = parse_evidence_bundle(evidence_bundle)
    missing_lines = _collect_missing_purpose_gaps(evidence_items)
    if not missing_lines:
        return evidence_gaps
    existing_lines = _parse_gap_lines(evidence_gaps)
    seen_keys = {_gap_key(line) for line in existing_lines}
    merged = list(existing_lines)
    for line in missing_lines:
        key = _gap_key(line)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append(line)
    return _build_evidence_gaps(merged)

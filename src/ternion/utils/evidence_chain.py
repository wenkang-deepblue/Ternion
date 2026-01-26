"""
Deterministic evidence chain parsing and reconciliation utilities.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal


_FILE_EXCERPT_PREFIX = "- [FILE_EXCERPT]"
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
    stripped = line.lstrip()
    if stripped.startswith("- "):
        return stripped[2:].lstrip()
    return stripped


def _extract_purpose(line: str) -> str | None:
    normalized = _strip_optional_bullet(line).strip()
    if normalized.upper().startswith(_PURPOSE_PREFIX):
        return normalized[len(_PURPOSE_PREFIX):].strip()
    return None


def _strip_format_indent(line: str) -> str:
    if line.startswith("  "):
        return line[2:]
    return line


def _parse_header_fields(header: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in header.split("|"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key.strip()] = value.strip()
    return fields


def _parse_line_range(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", value)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    if end < start:
        return None
    return start, end


def _parse_total_lines(value: str | None) -> int | None:
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
    if not path:
        return ""
    cleaned = path.strip().strip('"').strip("'")
    return cleaned


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
            header = stripped[len(_FILE_EXCERPT_PREFIX):].strip()
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


def _extract_field(text: str, key: str) -> str | None:
    marker = f"{key}="
    if marker not in text:
        return None
    remainder = text.split(marker, 1)[1]
    if " | " in remainder:
        value = remainder.split(" | ", 1)[0]
    else:
        value = remainder
    return value.strip() or None


def _split_path_and_lines(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    cleaned = _normalize_path(value)
    match = re.match(r"^(.*):(\d+\s*-\s*\d+)$", cleaned)
    if match:
        return _normalize_path(match.group(1)), match.group(2).replace(" ", "")
    return cleaned, None


def _looks_like_path(value: str) -> bool:
    if "/" in value or "\\" in value:
        return True
    lowered = value.lower()
    return lowered.endswith((".py", ".js", ".ts", ".tsx", ".json", ".yaml", ".yml", ".md"))


def _extract_target_from_ref(ref: str | None) -> tuple[str | None, str | None]:
    if not ref:
        return None, None
    cleaned = ref.strip()
    match = re.match(r"^(.*):(\d+\s*-\s*\d+)$", cleaned)
    if match:
        return _normalize_path(match.group(1)), match.group(2).replace(" ", "")
    if _looks_like_path(cleaned):
        return _normalize_path(cleaned), None
    return None, None


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
    path_field = _extract_field(normalized, "path")
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
    payload = f"{request}\n{purpose}".encode("utf-8")
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


def _match_request_to_evidence(
    request: EvidenceRequest, evidence: list[EvidenceItem]
) -> tuple[list[EvidenceItem], MatchScope]:
    target_path, request_range = _resolve_request_target(request)
    if not target_path:
        return [], "none"
    matches: list[EvidenceItem] = []
    if request_range is not None:
        for item in evidence:
            if _normalize_path(item.path) != target_path:
                continue
            if item.line_range is None:
                continue
            if not _ranges_overlap(item.line_range, request_range):
                continue
            matches.append(item)
        if not matches:
            return [], "none"
        ranges = [item.line_range for item in matches if item.line_range is not None]
        if _range_is_fully_covered(request_range, ranges):
            return matches, "range_level"
        return matches, "range_level_partial"

    for item in evidence:
        if _normalize_path(item.path) != target_path:
            continue
        matches.append(item)
    return matches, "file_level" if matches else "none"


def _is_full_file_covered(path: str, evidence_items: list[EvidenceItem]) -> bool:
    if not path:
        return False
    matching = [item for item in evidence_items if _normalize_path(item.path) == path]
    if not matching:
        return False
    totals = {item.file_total_lines for item in matching if item.file_total_lines}
    if len(totals) != 1:
        return False
    total_lines = totals.pop()
    if not total_lines:
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
    requests = parse_evidence_requests(evidence_requests)
    gap_lines = _parse_gap_lines(evidence_gaps)

    chain_index: list[dict[str, object]] = []
    unsatisfied_requests: list[EvidenceRequest] = []
    for request in requests:
        matches, match_scope = _match_request_to_evidence(request, evidence_items)
        target_path, request_range = _resolve_request_target(request)
        if request_range is None and target_path:
            full_covered = _is_full_file_covered(target_path, evidence_items)
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
            ranges = [
                item.line_range
                for item in evidence_items
                if _normalize_path(item.path) == path and item.line_range is not None
            ]
            if _range_is_fully_covered(target_range, ranges):
                continue
        if path and target_range is None and _is_full_file_covered(path, evidence_items):
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

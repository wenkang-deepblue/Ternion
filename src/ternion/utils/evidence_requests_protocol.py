"""
Deterministic parsing for Writer/Optimizer evidence top-up requests.

This module defines a strict, low-ambiguity text protocol that the Execution
(Writer) and Optimizer can emit when they require additional evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


EVIDENCE_REQUESTS_BEGIN = "TERNION_EVIDENCE_REQUESTS_BEGIN"
EVIDENCE_REQUESTS_END = "TERNION_EVIDENCE_REQUESTS_END"

_REQUESTER_PREFIX = "REQUESTER"
_FINAL_REQUEST_PREFIX = "FINAL_REQUEST"


@dataclass(frozen=True)
class EvidenceRequestsBlock:
    """Parsed evidence-requests protocol block."""

    requester: str
    final_request: bool
    requests_text: str


def extract_evidence_requests_block(
    text: str | None,
    *,
    default_requester: str | None = None,
) -> EvidenceRequestsBlock | None:
    """
    Extract a strict evidence-requests protocol block.

    The block must start with EVIDENCE_REQUESTS_BEGIN as the first non-empty line
    and contain EVIDENCE_REQUESTS_END.

    The block may contain metadata lines:
    - REQUESTER: execution|optimizer
    - FINAL_REQUEST: true|false

    Args:
        text: Assistant content.
        default_requester: Used when REQUESTER line is missing.

    Returns:
        EvidenceRequestsBlock if detected, otherwise None.
    """
    if not text or not isinstance(text, str):
        return None

    stripped = text.strip()
    if not stripped:
        return None

    if not stripped.startswith(EVIDENCE_REQUESTS_BEGIN):
        return None

    start = stripped.find(EVIDENCE_REQUESTS_BEGIN) + len(EVIDENCE_REQUESTS_BEGIN)
    end = stripped.find(EVIDENCE_REQUESTS_END, start)
    if end <= start:
        return None

    payload = stripped[start:end].strip()
    if not payload:
        return None

    requester: str | None = None
    final_request: bool | None = None
    request_lines: list[str] = []

    for raw in payload.splitlines():
        line = raw.strip()
        if not line:
            continue

        parsed_requester = _parse_key_value(line, _REQUESTER_PREFIX)
        if parsed_requester is not None:
            requester = parsed_requester.lower().strip()
            continue

        parsed_final = _parse_key_value(line, _FINAL_REQUEST_PREFIX)
        if parsed_final is not None:
            final_request = _parse_bool(parsed_final)
            continue

        request_lines.append(raw.rstrip())

    if requester is None:
        requester = (default_requester or "").strip().lower() or None
    if requester not in ("execution", "optimizer"):
        return None

    if final_request is None:
        final_request = False

    requests_text = "\n".join([line for line in request_lines if line.strip()]).strip()
    if not requests_text:
        return None

    return EvidenceRequestsBlock(
        requester=requester,
        final_request=bool(final_request),
        requests_text=requests_text,
    )


def _parse_key_value(line: str, key: str) -> str | None:
    normalized = line.strip()
    match = re.match(rf"^{re.escape(key)}\s*[:=]\s*(.+)$", normalized, flags=re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _parse_bool(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip().lower()
    return normalized in ("1", "true", "yes", "y", "final")


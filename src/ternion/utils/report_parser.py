"""
Structured report parsing utilities.

This module provides deterministic parsing for the Arbiter's structured
"Ternion Analysis Report" so downstream features (handoff packaging,
clarification excerpts) can extract specific sections without using LLM
semantic understanding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_H2_RE = re.compile(r"(?m)^##\s+(?P<title>.+?)\s*$")


@dataclass(frozen=True)
class ParsedReport:
    """Parsed sections from a structured Arbiter report."""

    root_cause: str = ""
    evidence: str = ""
    scope: str = ""
    fix_plan: str = ""
    verification: str = ""
    risks: str = ""
    if_not_effective: str = ""

    @property
    def is_structured(self) -> bool:
        """Whether the report contains any recognized structured section."""
        return any(
            [
                self.root_cause,
                self.evidence,
                self.scope,
                self.fix_plan,
                self.verification,
                self.risks,
                self.if_not_effective,
            ]
        )


def _normalize_title(title: str) -> str:
    """Normalize a heading title for matching."""
    return re.sub(r"\s+", " ", (title or "").strip().lower())


def parse_structured_report(report: str) -> ParsedReport:
    """
    Parse the Arbiter report into named sections.

    Expected headings are level-2 Markdown headings:
    - ## Root Cause
    - ## Evidence / Logs
    - ## Scope & Non-Goals
    - ## Fix Plan / Recommendation
    - ## Verification
    - ## Risks & Rollback
    - ## If not effective, then what?

    The parser is tolerant to minor variations in punctuation/spacing.

    Args:
        report: Raw report text.

    Returns:
        ParsedReport with extracted sections (missing sections are empty strings).
    """
    text = report or ""
    if not text:
        return ParsedReport()

    matches = list(_H2_RE.finditer(text))
    if not matches:
        return ParsedReport()

    # Slice content between headings.
    sections_by_title: dict[str, str] = {}
    for i, m in enumerate(matches):
        title = m.group("title")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip("\n").strip()
        sections_by_title[_normalize_title(title)] = body

    def pick(*candidates: str) -> str:
        for c in candidates:
            key = _normalize_title(c)
            if key in sections_by_title and sections_by_title[key].strip():
                return sections_by_title[key].strip()
        return ""

    root_cause = pick("Root Cause")
    evidence = pick("Evidence / Logs", "Evidence/Logs", "Evidence")
    scope = pick("Scope & Non-Goals", "Scope & Non-Goals", "Scope and Non-Goals", "Scope")
    fix_plan = pick("Fix Plan / Recommendation", "Fix Plan/Recommendation", "Fix Plan", "Recommendation")
    verification = pick("Verification")
    risks = pick("Risks & Rollback", "Risks and Rollback", "Risks & Rollback Strategy", "Risks")
    if_not_effective = pick("If not effective, then what?", "If not effective", "Next Steps If Not Effective")

    return ParsedReport(
        root_cause=root_cause,
        evidence=evidence,
        scope=scope,
        fix_plan=fix_plan,
        verification=verification,
        risks=risks,
        if_not_effective=if_not_effective,
    )



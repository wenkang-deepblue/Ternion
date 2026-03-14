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

from ternion.utils.i18n import MessageKey, t

_H2_RE = re.compile(r"(?m)^##\s+(?P<title>.+?)\s*$")
_MD_HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+")
_MD_BLOCKQUOTE_RE = re.compile(r"(?m)^\s{0,3}>\s?")
_MD_HR_RE = re.compile(r"(?m)^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


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
    fix_plan = pick(
        "Fix Plan / Recommendation", "Fix Plan/Recommendation", "Fix Plan", "Recommendation"
    )
    verification = pick("Verification")
    risks = pick("Risks & Rollback", "Risks and Rollback", "Risks & Rollback Strategy", "Risks")
    if_not_effective = pick(
        "If not effective, then what?", "If not effective", "Next Steps If Not Effective"
    )

    return ParsedReport(
        root_cause=root_cause,
        evidence=evidence,
        scope=scope,
        fix_plan=fix_plan,
        verification=verification,
        risks=risks,
        if_not_effective=if_not_effective,
    )


def _strip_markdown_for_display(text: str) -> str:
    """
    Best-effort Markdown -> plain text for UIs that do not render Markdown.

    This is intentionally conservative: it removes formatting markers while
    preserving line breaks and list structure as much as possible.
    """
    if not text:
        return ""

    out = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove headings / blockquote markers at line start
    out = _MD_HEADING_RE.sub("", out)
    out = _MD_BLOCKQUOTE_RE.sub("", out)

    # Drop horizontal rules (visual only)
    out = _MD_HR_RE.sub("", out)

    # Convert images/links to their visible text
    out = _MD_IMAGE_RE.sub(lambda m: (m.group(1) or "").strip(), out)
    out = _MD_LINK_RE.sub(lambda m: (m.group(1) or "").strip(), out)

    # Remove common emphasis/code markers
    out = out.replace("**", "").replace("__", "")
    out = out.replace("`", "")

    # Normalize list markers (keep structure, just unify bullets)
    out = re.sub(r"(?m)^\s*\*\s+", "- ", out)

    # Collapse excessive blank lines
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def format_report_for_display(report: str) -> str:
    """
    Format an Arbiter Markdown report into a plain-text view for display.

    Args:
        report: Raw markdown report text.

    Returns:
        The formatted plain-text representation of the report.
    """
    text = (report or "").strip()
    if not text:
        return ""

    parsed = parse_structured_report(text)
    if not parsed.is_structured:
        return _strip_markdown_for_display(text)

    def section(title: str, body: str) -> str:
        body_clean = _strip_markdown_for_display(body).strip()
        if not body_clean:
            body_clean = t(MessageKey.REPORT_SECTION_MISSING_PLACEHOLDER)
        return f"【{title}】\n{body_clean}"

    parts = [
        section(t(MessageKey.REPORT_SECTION_ROOT_CAUSE_TITLE), parsed.root_cause),
        section(t(MessageKey.REPORT_SECTION_EVIDENCE_TITLE), parsed.evidence),
        section(t(MessageKey.REPORT_SECTION_SCOPE_TITLE), parsed.scope),
        section(t(MessageKey.REPORT_SECTION_FIX_PLAN_TITLE), parsed.fix_plan),
        section(t(MessageKey.REPORT_SECTION_VERIFICATION_TITLE), parsed.verification),
        section(t(MessageKey.REPORT_SECTION_RISKS_TITLE), parsed.risks),
        section(t(MessageKey.REPORT_SECTION_IF_NOT_EFFECTIVE_TITLE), parsed.if_not_effective),
    ]

    return "\n\n".join(parts).strip()

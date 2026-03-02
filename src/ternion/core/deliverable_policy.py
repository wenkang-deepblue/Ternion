"""
Deliverable policy classification for Execution/Optimizer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from ternion.utils.language_resources import get_deliverable_policy_patterns


class DeliverableType(str, Enum):
    """Supported deliverable types for Execution/Optimizer."""

    DOC_ONLY = "doc-only"
    CODE_CHANGE = "code-change"
    MIXED = "mixed"
    ANALYSIS_ONLY = "analysis-only"


@dataclass(frozen=True)
class DeliverablePolicy:
    """Resolved deliverable policy used for prompt injection and enforcement."""

    deliverable_type: DeliverableType
    allowed_write_scope: str
    source: str
    reason: str

    @property
    def allow_mutations(self) -> bool:
        return self.deliverable_type != DeliverableType.ANALYSIS_ONLY


class DeliverableReason(str, Enum):
    """Reason codes for deliverable policy classification."""

    EMPTY_INPUT = "empty_input"
    EXPLICIT_ANALYSIS_ONLY = "explicit_analysis_only"
    DOC_ONLY_WITH_CODE_SIGNALS = "doc_only_with_code_signals"
    EXPLICIT_DOC_ONLY = "explicit_doc_only"
    DOC_AND_CODE_SIGNALS = "doc_and_code_signals"
    DOC_SIGNALS = "doc_signals"
    CODE_SIGNALS = "code_signals"
    NO_CODE_SIGNALS = "no_code_signals"
    NO_CLEAR_SIGNALS = "no_clear_deliverable_signals"
    DEFAULT_CODE_CHANGE = "default_code_change"


def _has_any_pattern(text: str, patterns: list[str]) -> bool:
    if not text:
        return False
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE) for pattern in patterns)


@dataclass(frozen=True)
class _DeliverableSignal:
    deliverable_type: DeliverableType | None
    explicit: bool
    reason: str
    source: str


def _classify_signals(text: str, *, source: str) -> _DeliverableSignal:
    normalized = (text or "").strip()
    if not normalized:
        return _DeliverableSignal(None, False, DeliverableReason.EMPTY_INPUT.value, source)

    patterns = get_deliverable_policy_patterns()

    if _has_any_pattern(normalized, patterns.analysis_only):
        return _DeliverableSignal(
            DeliverableType.ANALYSIS_ONLY,
            True,
            DeliverableReason.EXPLICIT_ANALYSIS_ONLY.value,
            source,
        )

    if _has_any_pattern(normalized, patterns.doc_only):
        no_code = _has_any_pattern(normalized, patterns.no_code)
        code_hint = _has_any_pattern(normalized, patterns.code_hints) and not no_code
        if code_hint and not no_code:
            return _DeliverableSignal(
                DeliverableType.MIXED,
                False,
                DeliverableReason.DOC_ONLY_WITH_CODE_SIGNALS.value,
                source,
            )
        return _DeliverableSignal(
            DeliverableType.DOC_ONLY,
            True,
            DeliverableReason.EXPLICIT_DOC_ONLY.value,
            source,
        )

    no_code = _has_any_pattern(normalized, patterns.no_code)
    doc_hint = _has_any_pattern(normalized, patterns.doc_hints)
    code_hint = _has_any_pattern(normalized, patterns.code_hints) and not no_code

    if doc_hint and code_hint:
        return _DeliverableSignal(
            DeliverableType.MIXED,
            False,
            DeliverableReason.DOC_AND_CODE_SIGNALS.value,
            source,
        )
    if doc_hint:
        return _DeliverableSignal(
            DeliverableType.DOC_ONLY,
            False,
            DeliverableReason.DOC_SIGNALS.value,
            source,
        )
    if code_hint:
        return _DeliverableSignal(
            DeliverableType.CODE_CHANGE,
            False,
            DeliverableReason.CODE_SIGNALS.value,
            source,
        )
    if no_code:
        return _DeliverableSignal(
            DeliverableType.DOC_ONLY,
            False,
            DeliverableReason.NO_CODE_SIGNALS.value,
            source,
        )

    return _DeliverableSignal(
        None,
        False,
        DeliverableReason.NO_CLEAR_SIGNALS.value,
        source,
    )


def resolve_deliverable_policy(user_message: str, ternion_report: str) -> DeliverablePolicy:
    """
    Resolve deliverable policy from user instruction and report context.

    Priority:
    1) Explicit user instruction
    2) Explicit report guidance
    3) Implicit user signals
    4) Implicit report signals
    5) Default to code-change
    """
    user_signal = _classify_signals(user_message, source="user_message")
    if user_signal.explicit and user_signal.deliverable_type is not None:
        return _build_policy(user_signal)

    report_signal = _classify_signals(ternion_report, source="report")
    if report_signal.explicit and report_signal.deliverable_type is not None:
        return _build_policy(report_signal)

    if user_signal.deliverable_type is not None:
        return _build_policy(user_signal)

    if report_signal.deliverable_type is not None:
        return _build_policy(report_signal)

    default_signal = _DeliverableSignal(
        DeliverableType.CODE_CHANGE,
        False,
        DeliverableReason.DEFAULT_CODE_CHANGE.value,
        "default",
    )
    return _build_policy(default_signal)


def _build_policy(signal: _DeliverableSignal) -> DeliverablePolicy:
    deliverable_type = signal.deliverable_type or DeliverableType.CODE_CHANGE
    if deliverable_type == DeliverableType.ANALYSIS_ONLY:
        allowed_scope = "none"
    elif deliverable_type == DeliverableType.DOC_ONLY:
        allowed_scope = "docs/**"
    else:
        allowed_scope = "repo/**"

    return DeliverablePolicy(
        deliverable_type=deliverable_type,
        allowed_write_scope=allowed_scope,
        source=signal.source,
        reason=signal.reason,
    )


def format_deliverable_policy_for_prompt(policy: DeliverablePolicy) -> str:
    """
    Format deliverable policy for injection into Writer/Optimizer prompts.
    """
    lines = [
        f"DELIVERABLE_TYPE: {policy.deliverable_type.value}",
        f"ALLOWED_WRITE_SCOPE: {policy.allowed_write_scope}",
        f"SOURCE: {policy.source}",
        f"REASON: {policy.reason}",
        "RULES:",
        "- Classify the deliverable type before acting, then follow this policy strictly.",
        "- If DELIVERABLE_TYPE=analysis-only, do NOT call mutation tools or write files.",
        "- If DELIVERABLE_TYPE=doc-only, only write under docs/**.",
    ]
    return "\n".join(lines).strip()

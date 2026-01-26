"""
Deliverable policy classification for Execution/Optimizer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


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


_DOC_ONLY_PATTERNS = [
    r"\bdoc[-\s]?only\b",
    r"\bdocs?\s+only\b",
    r"\bdocumentation\s+only\b",
    r"\bonly\s+docs?\b",
    r"\bonly\s+documentation\b",
    r"(只要文档|仅文档|只写文档|只做文档|只需要文档|仅需文档)",
]

_ANALYSIS_ONLY_PATTERNS = [
    r"\banalysis\s+only\b",
    r"\brecommendation\s+only\b",
    r"\bno\s+file\s+changes\b",
    r"\bdo\s+not\s+(write|modify|change)\s+files\b",
    r"(只分析|仅分析|只给建议|不落盘|不写文件|不修改文件)",
]

_NO_CODE_PATTERNS = [
    r"\bno\s+code\s+changes?\b",
    r"\bdo\s+not\s+(change|modify|touch)\s+code\b",
    r"(不改代码|不要改代码|无需改代码|不修改代码)",
]

_DOC_HINTS = [
    r"\bdoc(?:umentation)?\b",
    r"\bdesign\s+doc\b",
    r"\bspec(?:ification)?\b",
    r"\bplan\b",
    r"(文档|方案|设计|规格|计划|说明|蓝图|方案文档|文档落盘)",
]

_CODE_HINTS = [
    r"\bcode\b",
    r"\bimplement(?:ation)?\b",
    r"\bfix(?:es|ing)?\b",
    r"\bbug(?:fix)?\b",
    r"\bpatch\b",
    r"\brefactor(?:ing)?\b",
    r"\bmodify(?:ing)?\b",
    r"\bupdate(?:ing)?\b",
    r"\bchange(?:s|ing)?\b",
    r"\badd(?:ing)?\b",
    r"\btest(?:s|ing)?\b",
    r"\bconfig(?:uration)?\b",
    r"(代码|实现|修复|改代码|修改代码|更新代码|重构|测试|配置|补丁)",
]


def _has_any_pattern(text: str, patterns: list[str]) -> bool:
    if not text:
        return False
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE):
            return True
    return False


@dataclass(frozen=True)
class _DeliverableSignal:
    deliverable_type: DeliverableType | None
    explicit: bool
    reason: str
    source: str


def _classify_signals(text: str, *, source: str) -> _DeliverableSignal:
    normalized = (text or "").strip()
    if not normalized:
        return _DeliverableSignal(None, False, "empty input", source)

    if _has_any_pattern(normalized, _ANALYSIS_ONLY_PATTERNS):
        return _DeliverableSignal(
            DeliverableType.ANALYSIS_ONLY,
            True,
            "explicit analysis-only instruction",
            source,
        )

    if _has_any_pattern(normalized, _DOC_ONLY_PATTERNS):
        no_code = _has_any_pattern(normalized, _NO_CODE_PATTERNS)
        code_hint = _has_any_pattern(normalized, _CODE_HINTS) and not no_code
        if code_hint and not no_code:
            return _DeliverableSignal(
                DeliverableType.MIXED,
                False,
                "doc-only phrasing with code-change signals",
                source,
            )
        return _DeliverableSignal(
            DeliverableType.DOC_ONLY,
            True,
            "explicit doc-only instruction",
            source,
        )

    no_code = _has_any_pattern(normalized, _NO_CODE_PATTERNS)
    doc_hint = _has_any_pattern(normalized, _DOC_HINTS)
    code_hint = _has_any_pattern(normalized, _CODE_HINTS) and not no_code

    if doc_hint and code_hint:
        return _DeliverableSignal(
            DeliverableType.MIXED,
            False,
            "doc and code signals detected",
            source,
        )
    if doc_hint:
        return _DeliverableSignal(
            DeliverableType.DOC_ONLY,
            False,
            "documentation signals detected",
            source,
        )
    if code_hint:
        return _DeliverableSignal(
            DeliverableType.CODE_CHANGE,
            False,
            "code-change signals detected",
            source,
        )
    if no_code:
        return _DeliverableSignal(
            DeliverableType.DOC_ONLY,
            False,
            "no-code instruction detected",
            source,
        )

    return _DeliverableSignal(None, False, "no clear deliverable signals", source)


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
        "defaulted to code-change",
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

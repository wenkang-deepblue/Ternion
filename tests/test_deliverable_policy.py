"""
Tests for deliverable policy classification.
"""

from ternion.core.deliverable_policy import (
    DeliverableType,
    extract_explicit_deliverable_boundary,
    resolve_deliverable_policy,
)


def test_resolve_deliverable_policy_doc_only_from_user() -> None:
    policy = resolve_deliverable_policy("请只输出方案文档，不要改代码。", "")
    assert policy.deliverable_type == DeliverableType.DOC_ONLY
    assert policy.allowed_write_scope == "workspace-document-files"


def test_resolve_deliverable_policy_analysis_only_from_user() -> None:
    policy = resolve_deliverable_policy("只分析，不落盘。", "")
    assert policy.deliverable_type == DeliverableType.ANALYSIS_ONLY
    assert policy.allowed_write_scope == "none"


def test_resolve_deliverable_policy_mixed_from_user() -> None:
    policy = resolve_deliverable_policy("请更新文档并修复代码。", "")
    assert policy.deliverable_type == DeliverableType.MIXED
    assert policy.allowed_write_scope == "repo/**"


def test_resolve_deliverable_policy_doc_only_spanish() -> None:
    policy = resolve_deliverable_policy("Solo documentación, por favor.", "")
    assert policy.deliverable_type == DeliverableType.DOC_ONLY


def test_resolve_deliverable_policy_analysis_only_spanish() -> None:
    policy = resolve_deliverable_policy("Solo análisis, sin cambios de archivos.", "")
    assert policy.deliverable_type == DeliverableType.ANALYSIS_ONLY


def test_doc_hint_with_code_signals_becomes_mixed() -> None:
    policy = resolve_deliverable_policy("方案文档落盘，并修复代码。", "")
    assert policy.deliverable_type == DeliverableType.MIXED


def test_explicit_doc_only_with_code_signals_becomes_mixed() -> None:
    policy = resolve_deliverable_policy("doc-only，但也请改代码。", "")
    assert policy.deliverable_type == DeliverableType.MIXED


def test_extract_explicit_deliverable_boundary_from_report_line() -> None:
    boundary = extract_explicit_deliverable_boundary(
        "## Summary\n- **Deliverable Boundary (MANDATORY)**: `doc-only`\n- Update API details."
    )
    assert boundary == DeliverableType.DOC_ONLY


def test_explicit_user_boundary_locks_doc_only_despite_code_hints() -> None:
    policy = resolve_deliverable_policy(
        "Deliverable Boundary (MANDATORY): doc-only\n请写文档，并讨论 API / 数据库 / 实现细节。",
        "",
    )
    assert policy.deliverable_type == DeliverableType.DOC_ONLY
    assert policy.allowed_write_scope == "workspace-document-files"
    assert policy.source == "user_explicit_boundary"


def test_explicit_report_boundary_locks_doc_only_despite_code_hints() -> None:
    report = (
        "## Scope & Non-Goals\n"
        "- **Deliverable Boundary (MANDATORY)**: `doc-only`\n"
        "- Explain API endpoints, database schema, and implementation details.\n"
    )
    policy = resolve_deliverable_policy("", report)
    assert policy.deliverable_type == DeliverableType.DOC_ONLY
    assert policy.allowed_write_scope == "workspace-document-files"
    assert policy.source == "report_explicit_boundary"


def test_resolve_deliverable_policy_uses_report_when_user_empty() -> None:
    report = "Scope: documentation only. Non-goals: no code changes."
    policy = resolve_deliverable_policy("", report)
    assert policy.deliverable_type == DeliverableType.DOC_ONLY


def test_resolve_deliverable_policy_analysis_only_from_report_hyphen() -> None:
    policy = resolve_deliverable_policy("", "Scope: analysis-only. Non-goals: no file changes.")
    assert policy.deliverable_type == DeliverableType.ANALYSIS_ONLY
    assert policy.allowed_write_scope == "none"

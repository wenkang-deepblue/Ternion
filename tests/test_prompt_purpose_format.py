from ternion.router.prompts import (
    ARBITER_EVIDENCE_PROMPT,
    ARBITER_REPORT_EVIDENCE_PROMPT,
    DIVERGENCE_PROMPT,
    OPTIMIZER_PROMPT,
)


def test_arbiter_evidence_prompt_includes_purpose_field_format() -> None:
    expected = (
        "EVIDENCE_BUNDLE:\n"
        "- [FILE_EXCERPT] path=<file_path> | lines=<start-end>\n"
        "  PURPOSE: <why this excerpt is needed; what it verifies>\n"
        "  EXCERPT_BEGIN"
    )
    assert expected in ARBITER_EVIDENCE_PROMPT
    assert "EXACTLY 2 top-level sections" in ARBITER_EVIDENCE_PROMPT
    assert "PURPOSE must never appear inside EXCERPT_BEGIN/END" in ARBITER_EVIDENCE_PROMPT


def test_report_evidence_prompt_includes_purpose_field_format() -> None:
    expected = (
        "EVIDENCE_BUNDLE:\n"
        "- [FILE_EXCERPT] path=<file_path> | lines=<start-end> | total_lines=<N>\n"
        "  PURPOSE: <why this excerpt is needed; what it verifies>\n"
        "  EXCERPT_BEGIN"
    )
    assert expected in ARBITER_REPORT_EVIDENCE_PROMPT
    assert "EXACTLY 2 top-level sections" in ARBITER_REPORT_EVIDENCE_PROMPT
    assert "PURPOSE must never appear inside EXCERPT_BEGIN/END" in ARBITER_REPORT_EVIDENCE_PROMPT
    assert "PURPOSE MAPPING (MANDATORY)" in ARBITER_REPORT_EVIDENCE_PROMPT
    assert "Do NOT repeat previously collected evidence" in ARBITER_REPORT_EVIDENCE_PROMPT


def test_divergence_prompt_requires_purpose_in_requests() -> None:
    assert (
        "Each request MUST be immediately followed by a single-line PURPOSE field."
        in DIVERGENCE_PROMPT
    )
    assert "PURPOSE must be its own line as `PURPOSE: ...`" in DIVERGENCE_PROMPT


def test_optimizer_prompt_includes_phase_15_evidence_topup_wrapper_protocol() -> None:
    assert "TERNION_EVIDENCE_REQUESTS_BEGIN" in OPTIMIZER_PROMPT
    assert "TERNION_EVIDENCE_REQUESTS_END" in OPTIMIZER_PROMPT
    assert "REQUESTER: optimizer" in OPTIMIZER_PROMPT

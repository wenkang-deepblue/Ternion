from ternion.utils.evidence_chain import (
    compute_missing_ranges,
    is_deterministic_range_request,
    merge_adjacent_or_overlapping_ranges,
    merge_missing_purpose_gaps,
    parse_evidence_requests,
    reconcile_evidence_chain,
)


def test_reconcile_evidence_chain_matches_requests_and_updates_gaps() -> None:
    evidence_bundle = (
        "EVIDENCE_BUNDLE:\n"
        "- [FILE_EXCERPT] path=src/app.py | lines=10-20\n"
        "  PURPOSE: Verify handler logic\n"
        "  EXCERPT_BEGIN\n"
        "  def handler():\n"
        "      return 1\n"
        "  EXCERPT_END\n"
    )
    evidence_gaps = (
        "EVIDENCE_GAPS:\n"
        "- [MISSING_LOCATION] ref=src/app.py:12-18\n"
        "- [MISSING_FILE] path=src/missing.py\n"
    )
    evidence_requests = (
        "- [P0] path=src/app.py:12-18\n"
        "- PURPOSE: Verify handler logic.\n"
        "- [P1] path=src/missing.py\n"
        "PURPOSE: Need missing file content.\n"
    )

    reconciled_gaps, index = reconcile_evidence_chain(
        evidence_bundle=evidence_bundle,
        evidence_gaps=evidence_gaps,
        evidence_requests=evidence_requests,
    )

    assert reconciled_gaps == (
        "EVIDENCE_GAPS:\n"
        "- [MISSING_FILE] path=src/missing.py"
    )
    assert len(index) == 2
    assert index[0]["satisfied"] is True
    assert index[0]["match_scope"] == "range_level"
    assert index[0]["purpose"] == "Verify handler logic."
    assert index[0]["evidence_refs"]
    assert index[0]["evidence_refs"][0]["path"] == "src/app.py"
    assert "excerpt_hash_raw" in index[0]["evidence_refs"][0]
    assert index[1]["satisfied"] is False
    assert index[1]["match_scope"] == "none"
    assert index[1]["purpose"] == "Need missing file content."


def test_reconcile_mixed_none_marker_keeps_real_requests() -> None:
    evidence_requests = (
        "- [P0] None\n"
        "- [P0] path=src/app.py:1-2\n"
        "PURPOSE: Verify initialization.\n"
    )
    reconciled_gaps, index = reconcile_evidence_chain(
        evidence_bundle="EVIDENCE_BUNDLE:\n- None",
        evidence_gaps="EVIDENCE_GAPS:\n- None",
        evidence_requests=evidence_requests,
    )

    assert len(index) == 1
    assert index[0]["request"].startswith("[P0] path=src/app.py:1-2")
    assert reconciled_gaps == (
        "EVIDENCE_GAPS:\n"
        "- [MISSING_LOCATION] ref=src/app.py:1-2"
    )


def test_reconcile_dedupes_duplicate_gaps() -> None:
    evidence_gaps = (
        "EVIDENCE_GAPS:\n"
        "- [MISSING_LOCATION] ref=src/app.py:10-20\n"
        "- [MISSING_LOCATION] ref=src/app.py:10-20\n"
    )
    reconciled_gaps, index = reconcile_evidence_chain(
        evidence_bundle="EVIDENCE_BUNDLE:\n- None",
        evidence_gaps=evidence_gaps,
        evidence_requests="- [P0] None",
    )

    assert index == []
    assert reconciled_gaps == (
        "EVIDENCE_GAPS:\n"
        "- [MISSING_LOCATION] ref=src/app.py:10-20"
    )


def test_ref_and_path_lines_are_equivalent_for_matching() -> None:
    evidence_bundle = (
        "EVIDENCE_BUNDLE:\n"
        "- [FILE_EXCERPT] path=src/app.py | lines=10-20\n"
        "  PURPOSE: Verify handler logic\n"
        "  EXCERPT_BEGIN\n"
        "  def handler():\n"
        "      return 1\n"
        "  EXCERPT_END\n"
    )
    evidence_requests = (
        "- [P0] ref=src/app.py:12-18\n"
        "PURPOSE: Verify handler logic.\n"
    )
    reconciled_gaps, index = reconcile_evidence_chain(
        evidence_bundle=evidence_bundle,
        evidence_gaps="EVIDENCE_GAPS:\n- None",
        evidence_requests=evidence_requests,
    )

    assert reconciled_gaps == "EVIDENCE_GAPS:\n- None"
    assert index[0]["satisfied"] is True
    assert index[0]["match_scope"] == "range_level"


def test_range_level_multi_segment_coverage_is_satisfied() -> None:
    evidence_bundle = (
        "EVIDENCE_BUNDLE:\n"
        "- [FILE_EXCERPT] path=src/app.py | lines=10-15\n"
        "  PURPOSE: Verify handler logic\n"
        "  EXCERPT_BEGIN\n"
        "  a = 1\n"
        "  EXCERPT_END\n"
        "- [FILE_EXCERPT] path=src/app.py | lines=16-20\n"
        "  PURPOSE: Verify handler logic\n"
        "  EXCERPT_BEGIN\n"
        "  b = 2\n"
        "  EXCERPT_END\n"
    )
    evidence_requests = (
        "- [P0] path=src/app.py:10-20\n"
        "PURPOSE: Verify handler logic.\n"
    )
    reconciled_gaps, index = reconcile_evidence_chain(
        evidence_bundle=evidence_bundle,
        evidence_gaps="EVIDENCE_GAPS:\n- None",
        evidence_requests=evidence_requests,
    )

    assert reconciled_gaps == "EVIDENCE_GAPS:\n- None"
    assert index[0]["satisfied"] is True
    assert index[0]["match_scope"] == "range_level"


def test_range_level_partial_coverage_remains_gap() -> None:
    evidence_bundle = (
        "EVIDENCE_BUNDLE:\n"
        "- [FILE_EXCERPT] path=src/app.py | lines=10-14\n"
        "  PURPOSE: Verify handler logic\n"
        "  EXCERPT_BEGIN\n"
        "  a = 1\n"
        "  EXCERPT_END\n"
        "- [FILE_EXCERPT] path=src/app.py | lines=16-20\n"
        "  PURPOSE: Verify handler logic\n"
        "  EXCERPT_BEGIN\n"
        "  b = 2\n"
        "  EXCERPT_END\n"
    )
    evidence_requests = (
        "- [P0] path=src/app.py:10-20\n"
        "PURPOSE: Verify handler logic.\n"
    )
    reconciled_gaps, index = reconcile_evidence_chain(
        evidence_bundle=evidence_bundle,
        evidence_gaps="EVIDENCE_GAPS:\n- None",
        evidence_requests=evidence_requests,
    )

    assert index[0]["satisfied"] is False
    assert index[0]["match_scope"] == "range_level_partial"
    assert reconciled_gaps == (
        "EVIDENCE_GAPS:\n"
        "- [MISSING_LOCATION] ref=src/app.py:10-20"
    )


def test_path_only_requests_are_file_level_matches() -> None:
    evidence_bundle = (
        "EVIDENCE_BUNDLE:\n"
        "- [FILE_EXCERPT] path=src/app.py | lines=1-2\n"
        "  PURPOSE: Verify imports\n"
        "  EXCERPT_BEGIN\n"
        "  import os\n"
        "  import sys\n"
        "  EXCERPT_END\n"
    )
    evidence_requests = (
        "- [P0] path=src/app.py\n"
        "PURPOSE: Need full file context.\n"
    )
    reconciled_gaps, index = reconcile_evidence_chain(
        evidence_bundle=evidence_bundle,
        evidence_gaps="EVIDENCE_GAPS:\n- None",
        evidence_requests=evidence_requests,
    )

    assert index[0]["satisfied"] is False
    assert index[0]["match_scope"] == "file_level_partial"
    assert index[0]["evidence_refs"]
    assert reconciled_gaps == (
        "EVIDENCE_GAPS:\n"
        "- [MISSING_FILE] path=src/app.py"
    )


def test_file_level_full_coverage_is_satisfied() -> None:
    evidence_bundle = (
        "EVIDENCE_BUNDLE:\n"
        "- [FILE_EXCERPT] path=src/app.py | lines=1-2 | total_lines=4\n"
        "  PURPOSE: Full file evidence\n"
        "  EXCERPT_BEGIN\n"
        "  a = 1\n"
        "  b = 2\n"
        "  EXCERPT_END\n"
        "- [FILE_EXCERPT] path=src/app.py | lines=3-4 | total_lines=4\n"
        "  PURPOSE: Full file evidence\n"
        "  EXCERPT_BEGIN\n"
        "  c = 3\n"
        "  d = 4\n"
        "  EXCERPT_END\n"
    )
    evidence_requests = (
        "- [P0] path=src/app.py\n"
        "PURPOSE: Need full file context.\n"
    )
    reconciled_gaps, index = reconcile_evidence_chain(
        evidence_bundle=evidence_bundle,
        evidence_gaps="EVIDENCE_GAPS:\n- None",
        evidence_requests=evidence_requests,
    )

    assert reconciled_gaps == "EVIDENCE_GAPS:\n- None"
    assert index[0]["satisfied"] is True
    assert index[0]["match_scope"] == "file_level_full"


def test_file_level_partial_coverage_remains_gap() -> None:
    evidence_bundle = (
        "EVIDENCE_BUNDLE:\n"
        "- [FILE_EXCERPT] path=src/app.py | lines=1-2 | total_lines=4\n"
        "  PURPOSE: Full file evidence\n"
        "  EXCERPT_BEGIN\n"
        "  a = 1\n"
        "  b = 2\n"
        "  EXCERPT_END\n"
    )
    evidence_requests = (
        "- [P0] path=src/app.py\n"
        "PURPOSE: Need full file context.\n"
    )
    reconciled_gaps, index = reconcile_evidence_chain(
        evidence_bundle=evidence_bundle,
        evidence_gaps="EVIDENCE_GAPS:\n- None",
        evidence_requests=evidence_requests,
    )

    assert index[0]["satisfied"] is False
    assert index[0]["match_scope"] == "file_level_partial"
    assert reconciled_gaps == (
        "EVIDENCE_GAPS:\n"
        "- [MISSING_FILE] path=src/app.py"
    )


def test_missing_purpose_is_added_to_gaps() -> None:
    evidence_bundle = (
        "EVIDENCE_BUNDLE:\n"
        "- [FILE_EXCERPT] path=src/app.py | lines=1-2\n"
        "  EXCERPT_BEGIN\n"
        "  a = 1\n"
        "  EXCERPT_END\n"
    )
    reconciled_gaps, index = reconcile_evidence_chain(
        evidence_bundle=evidence_bundle,
        evidence_gaps="EVIDENCE_GAPS:\n- None",
        evidence_requests="- [P0] None",
    )

    assert index == []
    assert reconciled_gaps == (
        "EVIDENCE_GAPS:\n"
        "- [MISSING_PURPOSE] ref=src/app.py:1-2"
    )


def test_merge_missing_purpose_gaps_is_deduped() -> None:
    evidence_bundle = (
        "EVIDENCE_BUNDLE:\n"
        "- [FILE_EXCERPT] path=src/app.py | lines=1-2\n"
        "  EXCERPT_BEGIN\n"
        "  a = 1\n"
        "  EXCERPT_END\n"
    )
    evidence_gaps = (
        "EVIDENCE_GAPS:\n"
        "- [MISSING_PURPOSE] ref=src/app.py:1-2"
    )

    merged = merge_missing_purpose_gaps(
        evidence_bundle=evidence_bundle,
        evidence_gaps=evidence_gaps,
    )

    assert merged == evidence_gaps


def test_range_request_allows_trailing_comment_in_path_range() -> None:
    evidence_bundle = (
        "EVIDENCE_BUNDLE:\n"
        "- [FILE_EXCERPT] path=src/app.py | lines=10-20\n"
        "  PURPOSE: Verify handler logic\n"
        "  EXCERPT_BEGIN\n"
        "  def handler():\n"
        "      return 1\n"
        "  EXCERPT_END\n"
    )
    evidence_requests = (
        "- [P0] path=src/app.py:10-20 need confirm insert point\n"
        "PURPOSE: Verify handler logic.\n"
    )
    reconciled_gaps, index = reconcile_evidence_chain(
        evidence_bundle=evidence_bundle,
        evidence_gaps="EVIDENCE_GAPS:\n- None",
        evidence_requests=evidence_requests,
    )

    assert reconciled_gaps == "EVIDENCE_GAPS:\n- None"
    assert index[0]["satisfied"] is True
    assert index[0]["match_scope"] == "range_level"


def test_range_request_allows_trailing_comment_in_lines_field() -> None:
    evidence_bundle = (
        "EVIDENCE_BUNDLE:\n"
        "- [FILE_EXCERPT] path=src/app.py | lines=10-20\n"
        "  PURPOSE: Verify handler logic\n"
        "  EXCERPT_BEGIN\n"
        "  def handler():\n"
        "      return 1\n"
        "  EXCERPT_END\n"
    )
    evidence_requests = (
        "- [P0] path=src/app.py lines=10-20 need confirm insert point\n"
        "PURPOSE: Verify handler logic.\n"
    )
    reconciled_gaps, index = reconcile_evidence_chain(
        evidence_bundle=evidence_bundle,
        evidence_gaps="EVIDENCE_GAPS:\n- None",
        evidence_requests=evidence_requests,
    )

    assert reconciled_gaps == "EVIDENCE_GAPS:\n- None"
    assert index[0]["satisfied"] is True
    assert index[0]["match_scope"] == "range_level"


def test_merge_adjacent_or_overlapping_ranges_does_not_merge_gaps() -> None:
    merged = merge_adjacent_or_overlapping_ranges([
        (30, 60),
        (100, 150),
        (61, 99),
    ])
    assert merged == [(30, 150)]

    merged = merge_adjacent_or_overlapping_ranges([
        (30, 60),
        (100, 150),
    ])
    assert merged == [(30, 60), (100, 150)]


def test_compute_missing_ranges_returns_gaps() -> None:
    missing = compute_missing_ranges(
        request_range=(10, 20),
        covered_ranges=[(10, 14), (16, 20)],
    )
    assert missing == [(15, 15)]


def test_is_deterministic_range_request_matches_supported_shapes() -> None:
    entries = parse_evidence_requests(
        "- [P0] path=web/src/App.tsx:290-310\n"
        "PURPOSE: verify\n"
        "- [P1] path=src/app.py lines=1-2\n"
        "PURPOSE: verify\n"
        "- [P0] ref=src/app.py:10-20 trailing\n"
        "PURPOSE: verify\n"
    )
    assert len(entries) == 3

    det0 = is_deterministic_range_request(entries[0])
    det1 = is_deterministic_range_request(entries[1])
    det2 = is_deterministic_range_request(entries[2])
    assert det0 == ("web/src/App.tsx", (290, 310))
    assert det1 == ("src/app.py", (1, 2))
    assert det2 == ("src/app.py", (10, 20))

    non_det = parse_evidence_requests(
        "- [P0] path=web/src/components/RoleModelConfig.tsx: 下拉 options 渲染相关代码段\n"
        "PURPOSE: locate\n"
    )
    assert is_deterministic_range_request(non_det[0]) is None

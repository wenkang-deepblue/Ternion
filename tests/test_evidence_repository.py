"""Tests for the structured evidence repository (Phase B1/B2)."""

from ternion.utils.evidence_chain import (
    parse_evidence_bundle,
    reconcile_evidence_chain,
)
from ternion.utils.evidence_repository import (
    EVIDENCE_BUNDLE_SOFT_CAP_CHARS,
    EvidenceRepository,
    build_evidence_item,
    canonicalize_evidence_bundle_text,
    derive_evidence_records,
)


def _bundle_with_items(*blocks: str) -> str:
    return "EVIDENCE_BUNDLE:\n" + "\n".join(blocks)


def _excerpt_block(
    path: str,
    lines: str,
    excerpt_lines: list[str],
    *,
    purpose: str = "Check behavior.",
    total_lines: int | None = None,
) -> str:
    header = f"- [FILE_EXCERPT] path={path} | lines={lines}"
    if total_lines is not None:
        header += f" | total_lines={total_lines}"
    body = "\n".join(f"  {line}" for line in excerpt_lines)
    return f"{header}\n  PURPOSE: {purpose}\n  EXCERPT_BEGIN\n{body}\n  EXCERPT_END"


class TestRoundTrip:
    def test_parse_render_round_trip_is_idempotent(self) -> None:
        bundle = _bundle_with_items(
            _excerpt_block("src/app.py", "1-3", ["def a():", "    pass", ""], total_lines=30),
        )
        repo = EvidenceRepository.from_bundle_text(bundle)
        rendered = repo.render_bundle()

        repo2 = EvidenceRepository.from_bundle_text(rendered)
        assert repo2.render_bundle() == rendered
        assert len(repo2.items) == 1
        assert repo2.items[0].path == "src/app.py"
        assert repo2.items[0].line_range == (1, 3)
        assert repo2.items[0].file_total_lines == 30
        assert repo2.items[0].excerpt_hash == repo.items[0].excerpt_hash

    def test_empty_bundle_renders_none_marker(self) -> None:
        assert EvidenceRepository.from_bundle_text("").render_bundle() == (
            "EVIDENCE_BUNDLE:\n- None"
        )
        assert EvidenceRepository.from_bundle_text("EVIDENCE_BUNDLE:\n- None").render_bundle() == (
            "EVIDENCE_BUNDLE:\n- None"
        )

    def test_unparseable_payload_is_preserved_verbatim(self) -> None:
        bundle = "EVIDENCE_BUNDLE:\nSome free-form model output\nthat is not protocol-shaped."
        canonical, records = canonicalize_evidence_bundle_text(bundle)
        assert "Some free-form model output" in canonical
        assert records and records[0]["kind"] == "preserved_text"

        # Round trip keeps the preserved payload stable.
        repo2 = EvidenceRepository.from_bundle_text(canonical)
        assert "Some free-form model output" in repo2.render_bundle()

    def test_preserved_text_survives_merge_with_items(self) -> None:
        repo = EvidenceRepository.from_bundle_text("EVIDENCE_BUNDLE:\nfree text payload")
        repo.merge_bundle_text(_bundle_with_items(_excerpt_block("src/a.py", "1-1", ["x = 1"])))
        rendered = repo.render_bundle()
        assert "free text payload" in rendered
        assert "- [FILE_EXCERPT] path=src/a.py" in rendered

        # Leading preserved text is re-captured on re-parse (round trip stable).
        repo2 = EvidenceRepository.from_bundle_text(rendered)
        assert "free text payload" in repo2.render_bundle()
        assert len(repo2.items) == 1

    def test_records_round_trip(self) -> None:
        bundle = _bundle_with_items(
            _excerpt_block("src/app.py", "5-6", ["a = 1", "b = 2"], total_lines=10),
            "- [FILE_META] path=src/other.py | total_lines=44",
        )
        records = derive_evidence_records(bundle)
        repo = EvidenceRepository.from_records(records)
        assert len(repo.items) == 1
        assert repo.file_meta == {"src/other.py": 44}
        assert repo.render_bundle() == EvidenceRepository.from_bundle_text(bundle).render_bundle()

    def test_from_state_prefers_records_and_falls_back_to_bundle(self) -> None:
        bundle = _bundle_with_items(_excerpt_block("src/a.py", "1-1", ["x = 1"]))
        records = derive_evidence_records(bundle)

        repo = EvidenceRepository.from_state(evidence_items=records, evidence_bundle="")
        assert len(repo.items) == 1

        repo_fallback = EvidenceRepository.from_state(evidence_items=None, evidence_bundle=bundle)
        assert len(repo_fallback.items) == 1


class TestLosslessMerging:
    def test_exact_duplicates_collapse_and_merge_purposes(self) -> None:
        repo = EvidenceRepository.from_bundle_text(
            _bundle_with_items(
                _excerpt_block("src/a.py", "1-2", ["x = 1", "y = 2"], purpose="First reason."),
            )
        )
        repo.merge_bundle_text(
            _bundle_with_items(
                _excerpt_block("src/a.py", "1-2", ["x = 1", "y = 2"], purpose="Second reason."),
            )
        )
        assert len(repo.items) == 1
        assert "First reason." in repo.items[0].purpose
        assert "Second reason." in repo.items[0].purpose

    def test_overlapping_ranges_splice_when_content_verifies(self) -> None:
        # Lines 1-4 of the same file; two reads overlap on lines 3-4.
        repo = EvidenceRepository.from_bundle_text(
            _bundle_with_items(
                _excerpt_block("src/a.py", "1-4", ["l1", "l2", "l3", "l4"]),
            )
        )
        repo.merge_items(
            [
                build_evidence_item(
                    path="src/a.py",
                    lines="3-6",
                    purpose="Extend coverage.",
                    excerpt="l3\nl4\nl5\nl6",
                )
            ]
        )
        assert len(repo.items) == 1
        merged = repo.items[0]
        assert merged.line_range == (1, 6)
        assert merged.excerpt == "l1\nl2\nl3\nl4\nl5\nl6"
        assert "Extend coverage." in merged.purpose

    def test_adjacent_ranges_concatenate(self) -> None:
        repo = EvidenceRepository.from_bundle_text(
            _bundle_with_items(_excerpt_block("src/a.py", "1-2", ["l1", "l2"]))
        )
        repo.merge_items([build_evidence_item(path="src/a.py", lines="3-4", excerpt="l3\nl4")])
        assert len(repo.items) == 1
        assert repo.items[0].line_range == (1, 4)
        assert repo.items[0].excerpt == "l1\nl2\nl3\nl4"

    def test_conflicting_overlap_keeps_both_items(self) -> None:
        repo = EvidenceRepository.from_bundle_text(
            _bundle_with_items(_excerpt_block("src/a.py", "1-4", ["l1", "l2", "l3", "l4"]))
        )
        repo.merge_items(
            [
                build_evidence_item(
                    path="src/a.py",
                    lines="3-6",
                    excerpt="DIFFERENT\nl4\nl5\nl6",
                )
            ]
        )
        # Overlap region mismatch: never merged, nothing dropped.
        assert len(repo.items) == 2

    def test_subsumed_range_drops_only_when_content_matches(self) -> None:
        repo = EvidenceRepository.from_bundle_text(
            _bundle_with_items(
                _excerpt_block("src/a.py", "1-4", ["l1", "l2", "l3", "l4"], purpose="Full block.")
            )
        )
        repo.merge_items(
            [
                build_evidence_item(
                    path="src/a.py",
                    lines="2-3",
                    purpose="Inner detail.",
                    excerpt="l2\nl3",
                )
            ]
        )
        assert len(repo.items) == 1
        assert repo.items[0].line_range == (1, 4)
        assert "Inner detail." in repo.items[0].purpose

    def test_numbered_subrange_collapses_into_plain_superset(self) -> None:
        # Deterministic-mined excerpts use "N|content"; plain excerpts do not.
        repo = EvidenceRepository.from_bundle_text(
            _bundle_with_items(_excerpt_block("src/a.py", "10-12", ["alpha", "beta", "gamma"]))
        )
        repo.merge_items(
            [
                build_evidence_item(
                    path="src/a.py",
                    lines="11-12",
                    excerpt="11|beta\n12|gamma",
                )
            ]
        )
        assert len(repo.items) == 1
        assert repo.items[0].line_range == (10, 12)

    def test_cross_format_overlap_is_not_spliced(self) -> None:
        repo = EvidenceRepository.from_bundle_text(
            _bundle_with_items(_excerpt_block("src/a.py", "1-3", ["l1", "l2", "l3"]))
        )
        repo.merge_items(
            [
                build_evidence_item(
                    path="src/a.py",
                    lines="3-5",
                    excerpt="3|l3\n4|l4\n5|l5",
                )
            ]
        )
        # Formats differ and neither contains the other: keep both.
        assert len(repo.items) == 2

    def test_relative_and_absolute_paths_dedupe_via_canonicalization(self) -> None:
        repo = EvidenceRepository.from_bundle_text(
            _bundle_with_items(_excerpt_block("/repo/src/a.py", "1-1", ["x = 1"], purpose="Abs."))
        )
        repo.merge_items(
            [build_evidence_item(path="src/a.py", lines="1-1", purpose="Rel.", excerpt="x = 1")]
        )
        # Suffix-equivalent paths group together; identical content collapses.
        assert len(repo.items) == 1


class TestFileMetaAndReconcileCompat:
    def test_file_meta_last_seen_wins_and_renders(self) -> None:
        repo = EvidenceRepository.from_bundle_text(
            "EVIDENCE_BUNDLE:\n- [FILE_META] path=src/a.py | total_lines=100"
        )
        repo.merge_bundle_text("EVIDENCE_BUNDLE:\n- [FILE_META] path=src/a.py | total_lines=120")
        assert repo.file_meta == {"src/a.py": 120}
        assert "- [FILE_META] path=src/a.py | total_lines=120" in repo.render_bundle()

    def test_reconcile_sees_canonical_render_identically(self) -> None:
        bundle = _bundle_with_items(
            _excerpt_block("src/app.py", "10-20", [f"line{i}" for i in range(10, 21)]),
        )
        canonical, _ = canonicalize_evidence_bundle_text(bundle)
        requests = "- [P0] path=src/app.py:10-20\nPURPOSE: Verify the handler."

        gaps_raw, index_raw = reconcile_evidence_chain(
            evidence_bundle=bundle,
            evidence_gaps="EVIDENCE_GAPS:\n- None",
            evidence_requests=requests,
        )
        gaps_canon, index_canon = reconcile_evidence_chain(
            evidence_bundle=canonical,
            evidence_gaps="EVIDENCE_GAPS:\n- None",
            evidence_requests=requests,
        )
        assert index_raw[0]["satisfied"] is True
        assert index_canon[0]["satisfied"] is True
        assert gaps_raw == gaps_canon

    def test_merged_overlaps_still_satisfy_range_requests(self) -> None:
        repo = EvidenceRepository.from_bundle_text(
            _bundle_with_items(_excerpt_block("src/a.py", "1-5", ["a", "b", "c", "d", "e"]))
        )
        repo.merge_items(
            [build_evidence_item(path="src/a.py", lines="4-8", excerpt="d\ne\nf\ng\nh")]
        )
        rendered = repo.render_bundle()
        _, index = reconcile_evidence_chain(
            evidence_bundle=rendered,
            evidence_gaps="EVIDENCE_GAPS:\n- None",
            evidence_requests="- [P0] path=src/a.py:2-7\nPURPOSE: Check merged coverage.",
        )
        assert index[0]["satisfied"] is True

    def test_purpose_newlines_render_on_single_protocol_line(self) -> None:
        repo = EvidenceRepository()
        repo.merge_items(
            [
                build_evidence_item(
                    path="src/a.py",
                    lines="1-1",
                    purpose="First line.\nSecond line.",
                    excerpt="x = 1",
                )
            ]
        )
        rendered = repo.render_bundle()
        items = parse_evidence_bundle(rendered)
        assert len(items) == 1
        assert items[0].purpose == "First line. / Second line."

    def test_soft_cap_constant_is_exported(self) -> None:
        assert EVIDENCE_BUNDLE_SOFT_CAP_CHARS == 50_000

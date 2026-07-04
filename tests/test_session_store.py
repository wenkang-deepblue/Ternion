"""
Tests for the session store module.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from ternion.core.session_store import (
    ExecutionMode,
    Session,
    SessionStage,
    SessionStore,
    compute_report_hash,
    generate_session_id,
)


class TestSessionId:
    """Tests for session ID generation."""

    def test_generate_session_id_length(self) -> None:
        """Session ID should be 12 characters."""
        session_id = generate_session_id()
        assert len(session_id) == 12

    def test_generate_session_id_unique(self) -> None:
        """Consecutive IDs should be unique."""
        ids = [generate_session_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_generate_session_id_alphanumeric(self) -> None:
        """Session ID should be alphanumeric."""
        session_id = generate_session_id()
        assert session_id.isalnum()


class TestReportHash:
    """Tests for report hash computation."""

    def test_compute_report_hash_length(self) -> None:
        """Hash should be 16 characters."""
        report_hash = compute_report_hash("test report")
        assert len(report_hash) == 16

    def test_compute_report_hash_deterministic(self) -> None:
        """Same input should produce same hash."""
        report = "Test report content"
        hash1 = compute_report_hash(report)
        hash2 = compute_report_hash(report)
        assert hash1 == hash2

    def test_compute_report_hash_different(self) -> None:
        """Different inputs should produce different hashes."""
        hash1 = compute_report_hash("Report A")
        hash2 = compute_report_hash("Report B")
        assert hash1 != hash2


class TestSession:
    """Tests for Session dataclass."""

    def test_session_to_dict(self) -> None:
        """Session should serialize to dict correctly."""
        session = Session(
            session_id="test123",
            stage=SessionStage.AWAITING_CONFIRMATION,
            execution_mode=ExecutionMode.CURSOR_HANDOFF,
            ternion_report_raw="Test report with ```code```",
            ternion_report_safe="Test report with `​`​`code`​`​`",  # ZWSP inserted
            report_hash="abc123",
            created_at="2026-01-02T00:00:00Z",
            updated_at="2026-01-02T00:00:00Z",
        )
        data = session.to_dict()

        assert data["session_id"] == "test123"
        assert data["stage"] == "awaiting_confirmation"
        assert data["execution_mode"] == "cursor_handoff"
        assert data["ternion_report_raw"] == "Test report with ```code```"
        assert data["ternion_report_safe"] == "Test report with `​`​`code`​`​`"
        # Backward compatibility property
        assert session.ternion_report == "Test report with ```code```"

    def test_session_from_dict_new_format(self) -> None:
        """Session should deserialize from new dual-field dict correctly."""
        data = {
            "session_id": "test456",
            "stage": "confirmed",
            "execution_mode": "ternion_full",
            "ternion_report_raw": "Another report",
            "ternion_report_safe": "Another report (sanitized)",
            "report_hash": "def456",
            "created_at": "2026-01-02T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
            "last_user_feedback": "",
            "original_context": {},
            "generated_code": "",
            "review_feedback": "",
        }
        session = Session.from_dict(data)

        assert session.session_id == "test456"
        assert session.stage == SessionStage.CONFIRMED
        assert session.execution_mode == ExecutionMode.TERNION_FULL
        assert session.ternion_report_raw == "Another report"
        assert session.ternion_report_safe == "Another report (sanitized)"
        assert session.guardrail_events == []
        assert session.external_outputs_index == []
        # Backward compatibility property
        assert session.ternion_report == "Another report"

    def test_session_from_dict_legacy_format(self) -> None:
        """Session should migrate legacy single-field format on load."""
        # Simulate legacy session format without separate raw/safe fields
        legacy_data = {
            "session_id": "legacy789",
            "stage": "awaiting_confirmation",
            "execution_mode": "cursor_handoff",
            "ternion_report": "Old format report with ```code```",
            "report_hash": "ghi789",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "last_user_feedback": "",
            "original_context": {},
            "generated_code": "",
            "review_feedback": "",
        }
        session = Session.from_dict(legacy_data)

        assert session.session_id == "legacy789"
        # Raw should contain original content
        assert session.ternion_report_raw == "Old format report with ```code```"
        # Safe should be sanitized (ZWSP inserted in code fences)
        assert "```" not in session.ternion_report_safe or "\u200b" in session.ternion_report_safe
        # Backward compatibility property returns raw
        assert session.ternion_report == "Old format report with ```code```"
        assert session.guardrail_events == []
        assert session.external_outputs_index == []


class TestSessionStore:
    """Tests for SessionStore class."""

    @pytest.fixture
    def temp_sessions_dir(self) -> Iterator[Path]:
        """Create a temporary directory for session storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def store(self, temp_sessions_dir: Path) -> SessionStore:
        """Create a SessionStore with temporary directory."""
        return SessionStore(sessions_dir=temp_sessions_dir)

    def test_create_session(self, store: SessionStore) -> None:
        """Should create a new session with correct fields."""
        workspace_root = "/tmp/test-workspace"
        local_workspace_root = "/tmp/test-workspace"
        session = store.create_session(
            ternion_report="Test report content",
            execution_mode=ExecutionMode.CURSOR_HANDOFF,
            workspace_root=workspace_root,
            local_workspace_root=local_workspace_root,
            workspace_path_style="posix",
            workspace_root_source="explicit_workspace_path",
        )

        assert len(session.session_id) == 12
        assert session.stage == SessionStage.AWAITING_CONFIRMATION
        assert session.execution_mode == ExecutionMode.CURSOR_HANDOFF
        assert session.ternion_report == "Test report content"
        assert session.report_hash == compute_report_hash("Test report content")
        assert session.workspace_root == workspace_root
        assert session.local_workspace_root == local_workspace_root
        assert session.workspace_path_style == "posix"
        assert session.workspace_root_source == "explicit_workspace_path"

    def test_from_dict_defaults_workspace_boundary_fields(self) -> None:
        """Older session payloads should gain empty workspace boundary fields."""
        session = Session.from_dict(
            {
                "session_id": "abc123def456",
                "stage": "awaiting_confirmation",
                "execution_mode": "cursor_handoff",
                "ternion_report_raw": "Test report",
                "ternion_report_safe": "Test report",
                "report_hash": "deadbeefdeadbeef",
                "created_at": "2026-03-18T00:00:00Z",
                "updated_at": "2026-03-18T00:00:00Z",
            }
        )

        assert session.workspace_root == ""
        assert session.local_workspace_root == ""
        assert session.workspace_path_style == ""
        assert session.workspace_root_source == ""

    def test_create_session_persists_to_file(
        self, store: SessionStore, temp_sessions_dir: Path
    ) -> None:
        """Created session should be saved to disk."""
        session = store.create_session(
            ternion_report="Test",
            execution_mode=ExecutionMode.TERNION_FULL,
        )

        session_file = temp_sessions_dir / f"{session.session_id}.json"
        assert session_file.exists()

    def test_create_session_canonicalizes_evidence_requests(self, store: SessionStore) -> None:
        """Session creation should persist only structured evidence requests."""
        session = store.create_session(
            ternion_report="Test",
            execution_mode=ExecutionMode.TERNION_FULL,
            evidence_requests=(
                "Narrative noise\n"
                "- [P0] path=src/app.py:1-2\n"
                "PURPOSE: Verify entrypoint.\n"
                "<file_write>\n"
            ),
        )

        assert session.evidence_requests == (
            "- [P0] path=src/app.py:1-2\nPURPOSE: Verify entrypoint."
        )

    def test_create_session_derives_evidence_items_from_bundle(self, store: SessionStore) -> None:
        """Structured evidence records should mirror the persisted bundle."""
        bundle = (
            "EVIDENCE_BUNDLE:\n"
            "- [FILE_EXCERPT] path=src/app.py | lines=1-2\n"
            "  PURPOSE: Verify entrypoint.\n"
            "  EXCERPT_BEGIN\n"
            "  def main():\n"
            "      pass\n"
            "  EXCERPT_END"
        )
        session = store.create_session(
            ternion_report="Test",
            execution_mode=ExecutionMode.TERNION_FULL,
            evidence_bundle=bundle,
        )

        assert len(session.evidence_items) == 1
        record = session.evidence_items[0]
        assert record["kind"] == "excerpt"
        assert record["path"] == "src/app.py"
        assert record["line_range"] == [1, 2]
        assert record["purpose"] == "Verify entrypoint."

        loaded = store.load_session(session.session_id)
        assert loaded is not None
        assert loaded.evidence_items == session.evidence_items

    def test_update_session_rederives_evidence_items_with_bundle(self, store: SessionStore) -> None:
        """Bundle updates without explicit records re-derive the structured view."""
        session = store.create_session(
            ternion_report="Test",
            execution_mode=ExecutionMode.TERNION_FULL,
        )
        assert session.evidence_items == []

        bundle = (
            "EVIDENCE_BUNDLE:\n"
            "- [FILE_EXCERPT] path=src/a.py | lines=3-3\n"
            "  PURPOSE: Check constant.\n"
            "  EXCERPT_BEGIN\n"
            "  X = 1\n"
            "  EXCERPT_END"
        )
        updated = store.update_session(session.session_id, evidence_bundle=bundle)
        assert updated is not None
        assert len(updated.evidence_items) == 1
        assert updated.evidence_items[0]["path"] == "src/a.py"

    def test_update_session_explicit_evidence_items_win(self, store: SessionStore) -> None:
        """Explicit structured records take precedence over derivation."""
        session = store.create_session(
            ternion_report="Test",
            execution_mode=ExecutionMode.TERNION_FULL,
        )
        explicit = [{"kind": "excerpt", "path": "src/x.py", "lines": "", "excerpt": "pass"}]
        updated = store.update_session(
            session.session_id,
            evidence_bundle="EVIDENCE_BUNDLE:\n- None",
            evidence_items=explicit,
        )
        assert updated is not None
        assert updated.evidence_items == explicit

    def test_from_dict_defaults_evidence_items(self) -> None:
        """Legacy session payloads without records load with an empty list."""
        data = {
            "session_id": "legacy1234567",
            "stage": "rca_complete",
            "execution_mode": "ternion_full",
            "ternion_report_raw": "Report",
            "ternion_report_safe": "Report",
            "report_hash": compute_report_hash("Report"),
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        session = Session.from_dict(data)
        assert session.evidence_items == []

    def test_load_session(self, store: SessionStore) -> None:
        """Should load a previously created session."""
        original = store.create_session(
            ternion_report="Load test report",
            execution_mode=ExecutionMode.CURSOR_HANDOFF,
            original_context={"key": "value"},
        )

        loaded = store.load_session(original.session_id)

        assert loaded is not None
        assert loaded.session_id == original.session_id
        assert loaded.ternion_report == "Load test report"
        assert loaded.original_context == {"key": "value"}

    def test_load_session_not_found(self, store: SessionStore) -> None:
        """Should return None for non-existent session."""
        result = store.load_session("nonexistent123")
        assert result is None

    def test_update_session_stage(self, store: SessionStore) -> None:
        """Should update session stage."""
        session = store.create_session(
            ternion_report="Update test",
            execution_mode=ExecutionMode.CURSOR_HANDOFF,
        )

        updated = store.update_session(
            session.session_id,
            stage=SessionStage.CONFIRMED,
        )

        assert updated is not None
        assert updated.stage == SessionStage.CONFIRMED

    def test_update_session_canonicalizes_evidence_requests(self, store: SessionStore) -> None:
        """Session updates should canonicalize evidence request persistence."""
        session = store.create_session(
            ternion_report="Update test",
            execution_mode=ExecutionMode.TERNION_FULL,
        )

        updated = store.update_session(
            session.session_id,
            evidence_requests=("junk\n- [P0] path=docs/spec.md\nPURPOSE: Verify docs scope.\n"),
            stabilized_document_paths=["/tmp/doc.md"],
        )

        assert updated is not None
        assert updated.evidence_requests == (
            "- [P0] path=docs/spec.md\nPURPOSE: Verify docs scope."
        )
        assert updated.stabilized_document_paths == ["/tmp/doc.md"]

        # Verify persistence
        reloaded = store.load_session(session.session_id)
        assert reloaded is not None
        assert reloaded.evidence_requests == (
            "- [P0] path=docs/spec.md\nPURPOSE: Verify docs scope."
        )
        assert reloaded.stabilized_document_paths == ["/tmp/doc.md"]

    def test_update_session_appends_guardrail_events_and_external_outputs_index(
        self, store: SessionStore
    ) -> None:
        session = store.create_session(
            ternion_report="Traceability test",
            execution_mode=ExecutionMode.TERNION_FULL,
        )

        updated = store.update_session(
            session.session_id,
            append_guardrail_events=[{"type": "tool_policy_blocked", "phase": "execution"}],
            append_external_outputs_index=[{"kind": "shell_output", "path": "/tmp/x.txt"}],
        )
        assert updated is not None

        reloaded = store.load_session(session.session_id)
        assert reloaded is not None
        assert len(reloaded.guardrail_events) == 1
        assert reloaded.guardrail_events[0]["type"] == "tool_policy_blocked"
        assert reloaded.guardrail_events[0]["phase"] == "execution"
        assert reloaded.guardrail_events[0].get("ts")

        assert len(reloaded.external_outputs_index) == 1
        assert reloaded.external_outputs_index[0]["kind"] == "shell_output"
        assert reloaded.external_outputs_index[0]["path"] == "/tmp/x.txt"
        assert reloaded.external_outputs_index[0].get("ts")

    def test_update_session_feedback(self, store: SessionStore) -> None:
        """Should update user feedback."""
        session = store.create_session(
            ternion_report="Feedback test",
            execution_mode=ExecutionMode.CURSOR_HANDOFF,
        )

        updated = store.update_session(
            session.session_id,
            stage=SessionStage.REJECTED,
            last_user_feedback="This analysis is incorrect",
        )

        assert updated.last_user_feedback == "This analysis is incorrect"

    def test_update_session_report_updates_safe_and_hash(self, store: SessionStore) -> None:
        """Should update report fields when report becomes available later."""
        session = store.create_session(
            ternion_report="",
            execution_mode=ExecutionMode.TERNION_FULL,
            stage=SessionStage.AWAITING_TOOL_RESULTS,
        )

        new_report = "New report with ```code```"
        updated = store.update_session(
            session.session_id,
            ternion_report_raw=new_report,
        )

        assert updated is not None
        assert updated.ternion_report_raw == new_report
        assert updated.ternion_report_safe != new_report
        assert updated.report_hash == compute_report_hash(new_report)

    def test_update_session_populates_tool_call_index(self, store: SessionStore) -> None:
        """Setting pending_tool_calls should populate tool_call_index for backfill."""
        session = store.create_session(
            ternion_report="Tool call index test",
            execution_mode=ExecutionMode.TERNION_FULL,
        )
        tool_calls = [
            {
                "id": "ternion_test_r0001_c00",
                "type": "function",
                "function": {
                    "name": "Write",
                    "arguments": '{"path":"docs/test.md","contents":"hi"}',
                },
            }
        ]
        updated = store.update_session(
            session.session_id,
            pending_tool_calls=tool_calls,
            workflow_phase="execution",
            round_index=1,
        )

        assert updated is not None
        assert "ternion_test_r0001_c00" in (updated.tool_call_index or {})
        meta = updated.tool_call_index["ternion_test_r0001_c00"]
        assert meta.get("tool_name") == "Write"

        # Clearing pending_tool_calls should not erase the index.
        store.update_session(session.session_id, pending_tool_calls=[])
        reloaded = store.load_session(session.session_id)
        assert reloaded is not None
        assert "ternion_test_r0001_c00" in (reloaded.tool_call_index or {})

    def test_update_session_not_found(self, store: SessionStore) -> None:
        """Should return None when updating non-existent session."""
        result = store.update_session("nonexistent", stage=SessionStage.CONFIRMED)
        assert result is None

    def test_delete_session(self, store: SessionStore, temp_sessions_dir: Path) -> None:
        """Should delete session file."""
        session = store.create_session(
            ternion_report="Delete test",
            execution_mode=ExecutionMode.CURSOR_HANDOFF,
        )
        session_file = temp_sessions_dir / f"{session.session_id}.json"
        assert session_file.exists()

        result = store.delete_session(session.session_id)

        assert result is True
        assert not session_file.exists()

    def test_delete_session_not_found(self, store: SessionStore) -> None:
        """Should return False when deleting non-existent session."""
        result = store.delete_session("nonexistent")
        assert result is False

    def test_list_sessions(self, store: SessionStore) -> None:
        """Should list all sessions."""
        store.create_session("Report 1", ExecutionMode.CURSOR_HANDOFF)
        store.create_session("Report 2", ExecutionMode.TERNION_FULL)
        store.create_session("Report 3", ExecutionMode.CURSOR_HANDOFF)

        sessions = store.list_sessions()

        assert len(sessions) == 3

    def test_list_sessions_filter_by_stage(self, store: SessionStore) -> None:
        """Should filter sessions by stage."""
        s1 = store.create_session("Report 1", ExecutionMode.CURSOR_HANDOFF)
        s2 = store.create_session("Report 2", ExecutionMode.CURSOR_HANDOFF)
        store.update_session(s1.session_id, stage=SessionStage.CONFIRMED)

        pending = store.list_sessions(stage=SessionStage.AWAITING_CONFIRMATION)
        confirmed = store.list_sessions(stage=SessionStage.CONFIRMED)

        assert len(pending) == 1
        assert len(confirmed) == 1
        assert pending[0].session_id == s2.session_id
        assert confirmed[0].session_id == s1.session_id

    def test_get_pending_sessions(self, store: SessionStore) -> None:
        """Should get only pending sessions."""
        s1 = store.create_session("Report 1", ExecutionMode.CURSOR_HANDOFF)
        s2 = store.create_session("Report 2", ExecutionMode.CURSOR_HANDOFF)
        store.update_session(s1.session_id, stage=SessionStage.EXECUTED)

        pending = store.get_pending_sessions()

        assert len(pending) == 1
        assert pending[0].session_id == s2.session_id


class TestSessionStoreRobustness:
    """Tests for session persistence robustness."""

    @pytest.fixture
    def temp_sessions_dir(self) -> Iterator[Path]:
        """Create a temporary directory for session storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def store(self, temp_sessions_dir: Path) -> SessionStore:
        """Create a SessionStore with temporary directory."""
        return SessionStore(sessions_dir=temp_sessions_dir)

    def test_load_corrupted_session_returns_none(
        self, store: SessionStore, temp_sessions_dir: Path
    ) -> None:
        """Loading a corrupted session file should return None."""
        # Create a valid session first
        session = store.create_session("Test report", ExecutionMode.CURSOR_HANDOFF)
        session_path = temp_sessions_dir / f"{session.session_id}.json"

        # Corrupt the session file
        with open(session_path, "w", encoding="utf-8") as f:
            f.write("{ invalid json content")

        # Load should return None
        loaded = store.load_session(session.session_id)
        assert loaded is None

    def test_load_corrupted_session_emits_log(
        self, store: SessionStore, temp_sessions_dir: Path
    ) -> None:
        """Loading a corrupted session should emit a warning to log_manager."""
        from unittest.mock import patch

        # Create a valid session first
        session = store.create_session("Test report", ExecutionMode.CURSOR_HANDOFF)
        session_path = temp_sessions_dir / f"{session.session_id}.json"

        # Corrupt the session file
        with open(session_path, "w", encoding="utf-8") as f:
            f.write("not valid json")

        # Mock log_manager.emit and verify it's called
        with patch("ternion.core.session_store.log_manager") as mock_log_manager:
            loaded = store.load_session(session.session_id)
            assert loaded is None
            mock_log_manager.emit.assert_called_once()
            call_args = mock_log_manager.emit.call_args
            assert call_args.kwargs["level"] == "WARN"
            assert call_args.kwargs["category"] == "SESSION"
            assert session.session_id in call_args.kwargs["message"]

    def test_atomic_write_creates_valid_file(
        self, store: SessionStore, temp_sessions_dir: Path
    ) -> None:
        """Atomic write should create a valid JSON session file."""
        session = store.create_session(
            ternion_report="Test atomic write",
            execution_mode=ExecutionMode.TERNION_FULL,
        )

        session_path = temp_sessions_dir / f"{session.session_id}.json"
        assert session_path.exists()

        # Verify file contains valid JSON
        import json

        with open(session_path, encoding="utf-8") as f:
            data = json.load(f)

        assert data["session_id"] == session.session_id
        assert data["ternion_report_raw"] == "Test atomic write"

    def test_atomic_write_no_temp_files_left(
        self, store: SessionStore, temp_sessions_dir: Path
    ) -> None:
        """Atomic write should not leave temp files after successful save."""
        store.create_session("Test 1", ExecutionMode.CURSOR_HANDOFF)
        store.create_session("Test 2", ExecutionMode.TERNION_FULL)

        # Check no .tmp files remain
        tmp_files = list(temp_sessions_dir.glob("*.tmp"))
        assert len(tmp_files) == 0

        # But session files exist
        session_files = list(temp_sessions_dir.glob("*.json"))
        assert len(session_files) == 2

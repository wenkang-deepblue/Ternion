"""
Tests for session cold/hot storage separation and archiving (Phase C1/C4).

Covers:
- Cold field externalization to per-session sidecar files
- Cursor tools schema deduplication into the shared content-addressed store
- Transparent restoration on load (including degraded modes)
- Backward compatibility with legacy inline-format session files
- Terminal session archiving into self-contained gzip files
- Per-session asyncio lock registry
"""

import asyncio
import gzip
import json
from datetime import UTC, datetime, timedelta

import pytest

from ternion.core.session_store import (
    ExecutionMode,
    SessionStage,
    SessionStore,
    get_session_lock,
)

pytestmark = pytest.mark.asyncio


COLD_PAYLOAD = {
    "tool_results_raw": {"ternion_abc_r0001_c00": "raw tool output " * 200},
    "baseline_file_snapshots": {"src/app.py": "print('baseline')\n" * 100},
    "writer_output_files": {"src/app.py": "print('updated')\n" * 100},
}

CURSOR_TOOLS = [
    {"type": "function", "function": {"name": "Read", "parameters": {"type": "object"}}},
    {"type": "function", "function": {"name": "Write", "parameters": {"type": "object"}}},
]


def _create_session_with_cold_data(store: SessionStore):
    return store.create_session(
        ternion_report="# Report",
        execution_mode=ExecutionMode.TERNION_FULL,
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        cursor_tools=CURSOR_TOOLS,
        tool_results_raw=dict(COLD_PAYLOAD["tool_results_raw"]),
        baseline_file_snapshots=dict(COLD_PAYLOAD["baseline_file_snapshots"]),
        writer_output_files=dict(COLD_PAYLOAD["writer_output_files"]),
    )


class TestColdFieldExternalization:
    """Cold fields live in sidecar files; loads remain fully transparent."""

    async def test_round_trip_restores_cold_fields(self, tmp_path):
        store = SessionStore(sessions_dir=tmp_path)
        session = _create_session_with_cold_data(store)

        on_disk = json.loads((tmp_path / f"{session.session_id}.json").read_text())
        for field_name in ("tool_results_raw", "baseline_file_snapshots", "writer_output_files"):
            stub = on_disk[field_name]
            assert isinstance(stub, dict)
            assert "__ternion_external__" in stub
            sidecar = tmp_path / session.session_id / stub["__ternion_external__"]
            assert sidecar.exists()

        loaded = store.load_session(session.session_id)
        assert loaded is not None
        assert loaded.tool_results_raw == COLD_PAYLOAD["tool_results_raw"]
        assert loaded.baseline_file_snapshots == COLD_PAYLOAD["baseline_file_snapshots"]
        assert loaded.writer_output_files == COLD_PAYLOAD["writer_output_files"]
        assert loaded.cursor_tools == CURSOR_TOOLS

    async def test_main_file_shrinks_significantly(self, tmp_path):
        store = SessionStore(sessions_dir=tmp_path)
        session = _create_session_with_cold_data(store)

        main_size = (tmp_path / f"{session.session_id}.json").stat().st_size
        inline_size = len(json.dumps(session.to_dict()))
        assert main_size < inline_size / 2

    async def test_empty_cold_fields_stay_inline(self, tmp_path):
        store = SessionStore(sessions_dir=tmp_path)
        session = store.create_session(
            ternion_report="# Report",
            execution_mode=ExecutionMode.TERNION_FULL,
        )

        on_disk = json.loads((tmp_path / f"{session.session_id}.json").read_text())
        assert on_disk["tool_results_raw"] == {}
        assert on_disk["cursor_tools"] == []
        assert not (tmp_path / session.session_id).exists()

    async def test_update_session_refreshes_sidecar(self, tmp_path):
        store = SessionStore(sessions_dir=tmp_path)
        session = _create_session_with_cold_data(store)

        updated_raw = dict(COLD_PAYLOAD["tool_results_raw"])
        updated_raw["ternion_abc_r0002_c00"] = "second round output"
        store.update_session(session.session_id, tool_results_raw=updated_raw)

        loaded = store.load_session(session.session_id)
        assert loaded is not None
        assert loaded.tool_results_raw == updated_raw

    async def test_missing_sidecar_degrades_to_empty(self, tmp_path):
        store = SessionStore(sessions_dir=tmp_path)
        session = _create_session_with_cold_data(store)

        (tmp_path / session.session_id / "tool_results_raw.json.gz").unlink()

        loaded = store.load_session(session.session_id)
        assert loaded is not None
        assert loaded.tool_results_raw == {}
        # Other cold fields are unaffected by one missing sidecar.
        assert loaded.baseline_file_snapshots == COLD_PAYLOAD["baseline_file_snapshots"]

    async def test_legacy_inline_session_still_loads(self, tmp_path):
        store = SessionStore(sessions_dir=tmp_path)
        session = _create_session_with_cold_data(store)

        # Simulate a pre-C1 session file with everything inline.
        legacy_path = tmp_path / f"{session.session_id}.json"
        legacy_path.write_text(json.dumps(session.to_dict(), ensure_ascii=False), encoding="utf-8")

        loaded = store.load_session(session.session_id)
        assert loaded is not None
        assert loaded.tool_results_raw == COLD_PAYLOAD["tool_results_raw"]
        assert loaded.cursor_tools == CURSOR_TOOLS

    async def test_delete_session_removes_sidecar_dir(self, tmp_path):
        store = SessionStore(sessions_dir=tmp_path)
        session = _create_session_with_cold_data(store)
        assert (tmp_path / session.session_id).is_dir()

        assert store.delete_session(session.session_id) is True
        assert not (tmp_path / f"{session.session_id}.json").exists()
        assert not (tmp_path / session.session_id).exists()


class TestCursorToolsDeduplication:
    """Identical tools schemas are stored once in the shared store."""

    async def test_two_sessions_share_one_schema_file(self, tmp_path):
        store = SessionStore(sessions_dir=tmp_path)
        first = store.create_session(
            ternion_report="# A",
            execution_mode=ExecutionMode.TERNION_FULL,
            cursor_tools=CURSOR_TOOLS,
        )
        second = store.create_session(
            ternion_report="# B",
            execution_mode=ExecutionMode.TERNION_FULL,
            cursor_tools=CURSOR_TOOLS,
        )

        shared_files = list((tmp_path / "shared_tool_schemas").glob("*.json.gz"))
        assert len(shared_files) == 1

        for session in (first, second):
            loaded = store.load_session(session.session_id)
            assert loaded is not None
            assert loaded.cursor_tools == CURSOR_TOOLS

    async def test_missing_shared_schema_degrades_to_empty(self, tmp_path):
        store = SessionStore(sessions_dir=tmp_path)
        session = store.create_session(
            ternion_report="# A",
            execution_mode=ExecutionMode.TERNION_FULL,
            cursor_tools=CURSOR_TOOLS,
        )

        for shared_file in (tmp_path / "shared_tool_schemas").glob("*.json.gz"):
            shared_file.unlink()

        loaded = store.load_session(session.session_id)
        assert loaded is not None
        assert loaded.cursor_tools == []


class TestSessionArchiving:
    """Terminal sessions past the age threshold move into gzip archives."""

    def _age_session(self, store: SessionStore, session_id: str, days: int) -> None:
        path = store.sessions_dir / f"{session_id}.json"
        data = json.loads(path.read_text())
        old = (datetime.now(UTC) - timedelta(days=days)).isoformat().replace("+00:00", "Z")
        data["updated_at"] = old
        data["created_at"] = old
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    async def test_archives_old_terminal_sessions(self, tmp_path):
        store = SessionStore(sessions_dir=tmp_path)
        session = _create_session_with_cold_data(store)
        store.update_session(session.session_id, stage=SessionStage.EXECUTED)
        self._age_session(store, session.session_id, days=45)

        archived = store.archive_old_sessions(days=30)
        assert archived == 1
        assert not (tmp_path / f"{session.session_id}.json").exists()
        assert not (tmp_path / session.session_id).exists()

        archive_path = tmp_path / "archive" / f"{session.session_id}.json.gz"
        assert archive_path.exists()
        with gzip.open(archive_path, "rt", encoding="utf-8") as f:
            payload = json.load(f)
        # Archive is self-contained: cold data is inlined, not referenced.
        assert payload["tool_results_raw"] == COLD_PAYLOAD["tool_results_raw"]
        assert payload["cursor_tools"] == CURSOR_TOOLS

    async def test_skips_recent_and_non_terminal_sessions(self, tmp_path):
        store = SessionStore(sessions_dir=tmp_path)

        recent_terminal = store.create_session(
            ternion_report="# recent",
            execution_mode=ExecutionMode.TERNION_FULL,
        )
        store.update_session(recent_terminal.session_id, stage=SessionStage.EXECUTED)

        old_in_progress = store.create_session(
            ternion_report="# awaiting",
            execution_mode=ExecutionMode.TERNION_FULL,
            stage=SessionStage.AWAITING_TOOL_RESULTS,
        )
        self._age_session(store, old_in_progress.session_id, days=90)

        old_awaiting_confirm = store.create_session(
            ternion_report="# gate",
            execution_mode=ExecutionMode.CURSOR_HANDOFF,
            stage=SessionStage.AWAITING_CONFIRMATION,
        )
        self._age_session(store, old_awaiting_confirm.session_id, days=90)

        assert store.archive_old_sessions(days=30) == 0
        assert store.load_session(recent_terminal.session_id) is not None
        assert store.load_session(old_in_progress.session_id) is not None
        assert store.load_session(old_awaiting_confirm.session_id) is not None

    async def test_archive_dir_not_scanned_by_list_sessions(self, tmp_path):
        store = SessionStore(sessions_dir=tmp_path)
        session = store.create_session(
            ternion_report="# done",
            execution_mode=ExecutionMode.TERNION_FULL,
        )
        store.update_session(session.session_id, stage=SessionStage.EXECUTED)
        self._age_session(store, session.session_id, days=60)

        assert store.archive_old_sessions(days=30) == 1
        assert store.list_sessions() == []


class TestSessionLockRegistry:
    """Per-session locks serialize concurrent read-modify-write turns."""

    async def test_same_session_returns_same_lock(self):
        lock_a = get_session_lock("sess-lock-a")
        lock_b = get_session_lock("sess-lock-a")
        lock_c = get_session_lock("sess-lock-c")
        assert lock_a is lock_b
        assert lock_a is not lock_c

    async def test_lock_serializes_read_modify_write(self, tmp_path):
        store = SessionStore(sessions_dir=tmp_path)
        session = store.create_session(
            ternion_report="# lock test",
            execution_mode=ExecutionMode.TERNION_FULL,
        )
        started = asyncio.Event()

        async def merge_turn(message_id: str, hold: float) -> None:
            async with get_session_lock(session.session_id):
                started.set()
                current = store.load_session(session.session_id)
                assert current is not None
                messages = list(current.execution_messages)
                # Yield control mid-turn to expose lost-update races.
                await asyncio.sleep(hold)
                messages.append({"role": "tool", "tool_call_id": message_id, "content": "ok"})
                store.update_session(session.session_id, execution_messages=messages)

        await asyncio.gather(merge_turn("call-1", 0.05), merge_turn("call-2", 0.0))

        final = store.load_session(session.session_id)
        assert final is not None
        ids = {m["tool_call_id"] for m in final.execution_messages}
        assert ids == {"call-1", "call-2"}

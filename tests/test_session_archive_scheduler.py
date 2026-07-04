"""Tests for the session archive background scheduler (Phase C4)."""

import asyncio
from unittest.mock import patch

import pytest

from ternion.server import session_archive
from ternion.server.session_archive import run_session_archive_scheduler

pytestmark = pytest.mark.asyncio


class TestSessionArchiveScheduler:
    """The archive loop runs passes on schedule and stops cleanly."""

    async def test_stop_during_initial_delay_runs_no_pass(self):
        stop_event = asyncio.Event()
        with patch.object(session_archive.session_store, "archive_old_sessions") as mock_archive:
            task = asyncio.create_task(run_session_archive_scheduler(stop_event))
            await asyncio.sleep(0.01)
            stop_event.set()
            await asyncio.wait_for(task, timeout=1.0)
        mock_archive.assert_not_called()

    async def test_runs_archive_pass_after_initial_delay(self):
        stop_event = asyncio.Event()
        with (
            patch.object(session_archive, "ARCHIVE_INITIAL_DELAY_SECONDS", 0.01),
            patch.object(
                session_archive.session_store, "archive_old_sessions", return_value=2
            ) as mock_archive,
        ):
            task = asyncio.create_task(run_session_archive_scheduler(stop_event))
            await asyncio.sleep(0.1)
            stop_event.set()
            await asyncio.wait_for(task, timeout=1.0)
        mock_archive.assert_called_once_with(session_archive.ARCHIVE_AFTER_DAYS)

    async def test_archive_failure_does_not_kill_loop(self):
        stop_event = asyncio.Event()
        with (
            patch.object(session_archive, "ARCHIVE_INITIAL_DELAY_SECONDS", 0.01),
            patch.object(session_archive, "ARCHIVE_INTERVAL_SECONDS", 0.01),
            patch.object(
                session_archive.session_store,
                "archive_old_sessions",
                side_effect=OSError("disk error"),
            ) as mock_archive,
        ):
            task = asyncio.create_task(run_session_archive_scheduler(stop_event))
            for _ in range(200):
                if mock_archive.call_count >= 2:
                    break
                await asyncio.sleep(0.02)
            stop_event.set()
            await asyncio.wait_for(task, timeout=2.0)
        assert mock_archive.call_count >= 2

"""
Background scheduler for session archiving.

Periodically moves terminal sessions that have been idle for a long time into
gzip archives (see SessionStore.archive_old_sessions). Archiving is
conservative by design: sessions never expire, and only terminal-stage
sessions past the age threshold are compacted.
"""

import asyncio

import structlog

from ternion.core.session_store import session_store

logger = structlog.get_logger(__name__)

# Archive terminal sessions untouched for this many days.
ARCHIVE_AFTER_DAYS = 30

# Delay the first archive pass so startup is never slowed by a disk sweep.
ARCHIVE_INITIAL_DELAY_SECONDS = 600

# Run one archive pass per day afterwards.
ARCHIVE_INTERVAL_SECONDS = 24 * 60 * 60


async def _wait_or_stop(stop_event: asyncio.Event, timeout_seconds: float) -> bool:
    """Wait for the stop event up to a timeout.

    Args:
        stop_event: Event signalling scheduler shutdown.
        timeout_seconds: Maximum time to wait before returning.

    Returns:
        True if the stop event was set (caller should exit), False on timeout.
    """
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=timeout_seconds)
        return True
    except TimeoutError:
        return False


async def run_session_archive_scheduler(stop_event: asyncio.Event) -> None:
    """
    Run the periodic session archive loop until the stop event is set.

    The archive pass itself is synchronous disk I/O, so it runs in a worker
    thread to keep the event loop responsive. Failures are logged and the
    loop continues; archiving is best-effort maintenance, never critical path.

    Args:
        stop_event: Event signalling scheduler shutdown.
    """
    if await _wait_or_stop(stop_event, ARCHIVE_INITIAL_DELAY_SECONDS):
        return

    while True:
        try:
            archived = await asyncio.to_thread(
                session_store.archive_old_sessions, ARCHIVE_AFTER_DAYS
            )
            if archived:
                logger.info("session_archive_pass_complete", archived_count=archived)
        except Exception:
            logger.warning("session_archive_pass_failed", exc_info=True)

        if await _wait_or_stop(stop_event, ARCHIVE_INTERVAL_SECONDS):
            return

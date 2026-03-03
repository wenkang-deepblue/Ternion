"""
Streaming event mechanism for real-time LLM output forwarding.

This module provides a queue-based event system that allows workflow nodes
to emit incremental tokens to SSE consumers in real-time, solving the
"all-at-once" output problem.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StreamEventType(str, Enum):
    """Types of streaming events."""

    TOKEN_DELTA = "token_delta"  # Incremental token/text chunk
    FINAL_UPDATE = "final_update"  # Final complete content
    PHASE_START = "phase_start"  # Workflow phase started
    PHASE_END = "phase_end"  # Workflow phase ended
    ERROR = "error"  # Error occurred


@dataclass
class StreamEvent:
    """
    A streaming event for real-time output forwarding.

    Attributes:
        event_type: Type of the event (token_delta, final_update, etc.)
        delta: Incremental text content (for token_delta events)
        content: Full content (for final_update events)
        phase: Current workflow phase
        message_id: Unique identifier for the message/run
        seq: Sequence number for ordering
        metadata: Additional event-specific data
    """

    event_type: StreamEventType
    delta: str = ""
    content: str = ""
    phase: str = ""
    message_id: str = ""
    seq: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class StreamEventQueue:
    """
    Async queue for streaming events between workflow nodes and SSE output.

    This queue is designed for a single consumer (one `async for` loop). If multiple
    consumers iterate the same queue concurrently, only one consumer will receive
    the sentinel close event and others may block indefinitely.

    Usage:
        # In routes.py:
        queue = StreamEventQueue()

        # Pass to workflow via state
        state["_stream_queue"] = queue

        # Start workflow in background task
        asyncio.create_task(run_workflow(state))

        # Consume events for SSE
        async for event in queue:
            yield format_sse_event(event)

        # In nodes.py:
        queue = state.get("_stream_queue")
        if queue:
            await queue.put(StreamEvent(
                event_type=StreamEventType.TOKEN_DELTA,
                delta=chunk,
                phase="convergence",
            ))
    """

    def __init__(self, maxsize: int = 0) -> None:
        """
        Initialize the event queue.

        Args:
            maxsize: Maximum queue size (0 = unlimited)
        """
        self._queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue(maxsize=maxsize)
        self._closed = False
        self._seq = 0

    async def put(self, event: StreamEvent) -> None:
        """
        Put an event into the queue.

        Args:
            event: The streaming event to enqueue
        """
        if self._closed:
            return
        self._seq += 1
        event.seq = self._seq
        await self._queue.put(event)

    async def put_token(
        self,
        delta: str,
        phase: str = "",
        message_id: str = "",
        **metadata: Any,
    ) -> None:
        """
        Convenience method to put a token delta event.

        Args:
            delta: The incremental text
            phase: Current workflow phase
            message_id: Message identifier
            **metadata: Additional metadata
        """
        await self.put(
            StreamEvent(
                event_type=StreamEventType.TOKEN_DELTA,
                delta=delta,
                phase=phase,
                message_id=message_id,
                metadata=dict(metadata),
            )
        )

    async def put_final(
        self,
        content: str,
        phase: str = "",
        message_id: str = "",
        **metadata: Any,
    ) -> None:
        """
        Convenience method to put a final update event.

        Args:
            content: The complete final content
            phase: Current workflow phase
            message_id: Message identifier
            **metadata: Additional metadata
        """
        await self.put(
            StreamEvent(
                event_type=StreamEventType.FINAL_UPDATE,
                content=content,
                phase=phase,
                message_id=message_id,
                metadata=dict(metadata),
            )
        )

    async def put_phase_start(self, phase: str, **metadata: Any) -> None:
        """
        Signal the start of a workflow phase.

        Args:
            phase: Workflow phase label.
            **metadata: Additional metadata.
        """
        await self.put(
            StreamEvent(
                event_type=StreamEventType.PHASE_START,
                phase=phase,
                metadata=dict(metadata),
            )
        )

    async def put_phase_end(self, phase: str, **metadata: Any) -> None:
        """
        Signal the end of a workflow phase.

        Args:
            phase: Workflow phase label.
            **metadata: Additional metadata.
        """
        await self.put(
            StreamEvent(
                event_type=StreamEventType.PHASE_END,
                phase=phase,
                metadata=dict(metadata),
            )
        )

    async def put_error(self, error_message: str, phase: str = "", **metadata: Any) -> None:
        """
        Put an error event.

        Args:
            error_message: The error message
            phase: Current workflow phase
            **metadata: Additional metadata
        """
        await self.put(
            StreamEvent(
                event_type=StreamEventType.ERROR,
                content=error_message,
                phase=phase,
                metadata=dict(metadata),
            )
        )

    def close(self) -> None:
        """
        Close the queue, signaling no more events will be sent.

        This puts a None sentinel value to signal consumers to stop.
        """
        if not self._closed:
            self._closed = True
            # Put None as sentinel to signal end
            try:
                self._queue.put_nowait(None)
            except asyncio.QueueFull:
                # If the queue is full (maxsize > 0), the sentinel may not fit.
                # Consumers should also rely on the `is_closed` flag.
                pass

    async def get(self) -> StreamEvent | None:
        """
        Get the next event from the queue.

        Returns:
            The next StreamEvent, or None if queue is closed
        """
        return await self._queue.get()

    def __aiter__(self) -> "StreamEventQueue":
        """Make the queue async iterable."""
        return self

    async def __anext__(self) -> StreamEvent:
        """
        Get the next event for async iteration.

        Raises:
            StopAsyncIteration: When queue is closed
        """
        event = await self.get()
        if event is None:
            raise StopAsyncIteration
        return event

    @property
    def is_closed(self) -> bool:
        """Check if the queue is closed."""
        return self._closed

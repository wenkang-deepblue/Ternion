"""
SSE streaming utilities for OpenAI-compatible responses.

Provides generators for creating Server-Sent Events streams that match
the OpenAI streaming response format.
"""

import json
import time
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any

import structlog

from ternion.core.models import ChatCompletionChunk, ChoiceDelta, StreamChoice

if TYPE_CHECKING:
    from ternion.workflow.streaming_events import StreamEventQueue

logger = structlog.get_logger(__name__)


def create_sse_stream(
    model: str,
    content: str,
) -> Generator[str, None, None]:
    """
    Create a simple SSE stream from a complete content string.

    This is a utility for creating placeholder responses. In production,
    the actual LLM provider streams will be used.

    Uses fixed-size chunks (128 characters) to amortize SSE framing overhead
    (previously used word-splitting, which caused excessive SSE events).

    Args:
        model: Model name to include in the response
        content: The complete content to stream

    Yields:
        SSE-formatted data strings
    """
    CHUNK_SIZE = 128

    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    for i in range(0, len(content), CHUNK_SIZE):
        text = content[i : i + CHUNK_SIZE]

        chunk = ChatCompletionChunk(
            id=chunk_id,
            created=created,
            model=model,
            choices=[
                StreamChoice(
                    delta=ChoiceDelta(content=text),
                )
            ],
        )
        yield f"data: {chunk.model_dump_json()}\n\n"

    final_chunk = ChatCompletionChunk(
        id=chunk_id,
        created=created,
        model=model,
        choices=[
            StreamChoice(
                delta=ChoiceDelta(),
                finish_reason="stop",
            )
        ],
    )
    yield f"data: {final_chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"


def create_sse_tool_calls_stream(
    model: str,
    tool_calls: list[dict[str, Any]],
    *,
    content: str | None = None,
) -> Generator[str, None, None]:
    """
    Create an OpenAI-compatible SSE stream that returns tool calls.

    This is used to drive Cursor Agent tool execution even when the server-side
    implementation is non-streaming.
    """
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    first_delta = ChoiceDelta(
        role="assistant",
        content=content,
        tool_calls=tool_calls,
    )
    first_chunk = ChatCompletionChunk(
        id=chunk_id,
        created=created,
        model=model,
        choices=[StreamChoice(delta=first_delta)],
    )
    yield f"data: {first_chunk.model_dump_json()}\n\n"

    final_chunk = ChatCompletionChunk(
        id=chunk_id,
        created=created,
        model=model,
        choices=[
            StreamChoice(
                delta=ChoiceDelta(),
                finish_reason="tool_calls",
            )
        ],
    )
    yield f"data: {final_chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"


async def stream_sse_chunks(
    chunks: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """
    Convert content chunks to SSE format with error handling.

    Args:
        chunks: Async generator of content strings from LLM

    Yields:
        SSE-formatted data strings
    """
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    try:
        async for content in chunks:
            chunk = ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model="ternion-team",
                choices=[
                    StreamChoice(
                        delta=ChoiceDelta(content=content),
                    )
                ],
            )
            yield f"data: {chunk.model_dump_json()}\n\n"

        final_chunk = ChatCompletionChunk(
            id=chunk_id,
            created=created,
            model="ternion-team",
            choices=[
                StreamChoice(
                    delta=ChoiceDelta(),
                    finish_reason="stop",
                )
            ],
        )
        yield f"data: {final_chunk.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.exception("stream_interrupted", error=str(e))
        yield format_sse_error("STREAM_INTERRUPTED", str(e))


def format_sse_error(error_code: str, detail: str = "") -> str:
    """
    Format an error as an SSE event with error code for i18n.

    Args:
        error_code: Error code for frontend i18n lookup (e.g., 'STREAM_INTERRUPTED')
        detail: Raw error detail for debugging/visibility console

    Returns:
        SSE-formatted error event string
    """
    error_data = {
        "error": {
            "code": error_code,
            "detail": detail,
            "type": "stream_error",
        }
    }
    return f"data: {json.dumps(error_data)}\n\ndata: [DONE]\n\n"


async def create_sse_stream_from_queue(
    model: str,
    queue: "StreamEventQueue",
) -> AsyncGenerator[str, None]:
    """
    Create an SSE stream from a StreamEventQueue for real-time LLM output.

    This function consumes events from the queue and converts them to
    OpenAI-compatible SSE format, enabling true streaming output.

    Args:
        model: Model name to include in the response
        queue: StreamEventQueue to consume events from

    Yields:
        SSE-formatted data strings in real-time
    """
    from ternion.workflow.streaming_events import StreamEventType

    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    try:
        async for event in queue:
            if event.event_type == StreamEventType.TOKEN_DELTA:
                # Forward token delta as SSE chunk
                if event.delta:
                    chunk = ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=model,
                        choices=[
                            StreamChoice(
                                delta=ChoiceDelta(content=event.delta),
                            )
                        ],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"

            elif event.event_type == StreamEventType.ERROR:
                # Forward error event
                yield format_sse_error("STREAM_ERROR", event.content)
                return

            # PHASE_START, PHASE_END, and FINAL_UPDATE events are informational
            # and don't need to be sent as separate SSE events (the tokens have
            # already been sent as TOKEN_DELTA events)

        # Stream completed successfully - send final chunk
        final_chunk = ChatCompletionChunk(
            id=chunk_id,
            created=created,
            model=model,
            choices=[
                StreamChoice(
                    delta=ChoiceDelta(),
                    finish_reason="stop",
                )
            ],
        )
        yield f"data: {final_chunk.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.exception("sse_stream_from_queue_error", error=str(e))
        yield format_sse_error("STREAM_INTERRUPTED", str(e))

"""
SSE streaming utilities for OpenAI-compatible responses.

Provides generators for creating Server-Sent Events streams that match
the OpenAI streaming response format.
"""

import json
import time
import uuid
from collections.abc import AsyncGenerator, Generator

import structlog

from ternion.core.models import ChatCompletionChunk, ChoiceDelta, StreamChoice

logger = structlog.get_logger(__name__)


def create_sse_stream(
    model: str,
    content: str,
) -> Generator[str, None, None]:
    """
    Create a simple SSE stream from a complete content string.

    This is a utility for creating placeholder responses. In production,
    the actual LLM provider streams will be used.

    Args:
        model: Model name to include in the response
        content: The complete content to stream

    Yields:
        SSE-formatted data strings
    """
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    words = content.split(" ")
    for i, word in enumerate(words):
        text = f" {word}" if i > 0 else word

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

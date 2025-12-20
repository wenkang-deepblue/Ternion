"""
SSE streaming utilities for OpenAI-compatible responses.

Provides generators for creating Server-Sent Events streams that match
the OpenAI streaming response format.
"""

import json
import time
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

from ternion.core.models import ChatCompletionChunk, ChoiceDelta, StreamChoice


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

    # Stream content word by word for a more realistic effect
    words = content.split(" ")
    for i, word in enumerate(words):
        # Add space before word (except first)
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

    # Send final chunk with finish_reason
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
    Convert content chunks to SSE format.

    Args:
        chunks: Async generator of content strings from LLM

    Yields:
        SSE-formatted data strings
    """
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

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

    # Send final chunk
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


def format_sse_error(message: str) -> str:
    """
    Format an error message as an SSE event.

    Useful for sending errors during streaming.
    """
    error_data = {
        "error": {
            "message": message,
            "type": "stream_error",
        }
    }
    return f"data: {json.dumps(error_data)}\n\ndata: [DONE]\n\n"

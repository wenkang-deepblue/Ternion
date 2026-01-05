"""
Pydantic models for OpenAI-compatible API.

These models ensure full compatibility with the OpenAI Chat Completions API,
including multimodal support for images.
"""

import time
import uuid
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ============================================================================
# Message Content Types (for multimodal support)
# ============================================================================


class TextContent(BaseModel):
    """Text content in a message."""

    type: Literal["text"] = "text"
    text: str


class ImageUrl(BaseModel):
    """Image URL specification."""

    url: str  # Can be a URL or base64 data URI
    detail: Literal["auto", "low", "high"] = "auto"


class ImageContent(BaseModel):
    """Image content in a message."""

    type: Literal["image_url"] = "image_url"
    image_url: ImageUrl


# Union type for message content
MessageContent = str | list[TextContent | ImageContent]


# ============================================================================
# Chat Messages
# ============================================================================


class MessageRole(str, Enum):
    """Valid message roles."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatMessage(BaseModel):
    """A single chat message."""

    role: MessageRole
    content: MessageContent | None = None
    name: str | None = None
    tool_calls: list[Any] | None = None
    tool_call_id: str | None = None


# ============================================================================
# Chat Completion Request
# ============================================================================


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""

    model: str
    messages: list[ChatMessage]
    temperature: float | None = 1.0
    top_p: float | None = 1.0
    n: int | None = 1
    stream: bool | None = False
    stop: str | list[str] | None = None
    max_tokens: int | None = None
    presence_penalty: float | None = 0.0
    frequency_penalty: float | None = 0.0
    logit_bias: dict[str, float] | None = None
    user: str | None = None

    # Additional fields that may be passed
    tools: list[Any] | None = None
    tool_choice: Any | None = None
    response_format: dict[str, str] | None = None


# ============================================================================
# Chat Completion Response
# ============================================================================


class ChoiceDelta(BaseModel):
    """Delta content for streaming responses."""

    role: str | None = None
    content: str | None = None
    tool_calls: list[Any] | None = None


class StreamChoice(BaseModel):
    """A single choice in a streaming response."""

    index: int = 0
    delta: ChoiceDelta
    finish_reason: Literal["stop", "length", "tool_calls"] | None = None


class ChatCompletionChunk(BaseModel):
    """A single chunk in a streaming response."""

    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[StreamChoice]


class UsageInfo(BaseModel):
    """Token usage information."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Choice(BaseModel):
    """A single choice in a non-streaming response."""

    index: int = 0
    message: ChatMessage
    finish_reason: Literal["stop", "length", "tool_calls"] = "stop"


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response (non-streaming)."""

    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[Choice]
    usage: UsageInfo = Field(default_factory=UsageInfo)


# ============================================================================
# Models List Response
# ============================================================================


class ModelInfo(BaseModel):
    """Information about an available model."""

    id: str
    object: Literal["model"] = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "ternion"


class ModelsListResponse(BaseModel):
    """Response for /v1/models endpoint."""

    object: Literal["list"] = "list"
    data: list[ModelInfo]


# ============================================================================
# Error Response
# ============================================================================


class ErrorDetail(BaseModel):
    """Error detail information."""

    message: str
    type: str = "server_error"
    code: str | None = None


class ErrorResponse(BaseModel):
    """OpenAI-compatible error response."""

    error: ErrorDetail

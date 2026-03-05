"""
Pydantic models for OpenAI-compatible API.

These models ensure full compatibility with the OpenAI Chat Completions API,
including multimodal support for images.
"""

import time
import uuid
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

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

    # ------------------------------------------------------------------------
    # Compatibility fields (Cursor / OpenAI Responses API)
    # ------------------------------------------------------------------------
    # Cursor (newer versions) may send OpenAI "Responses API"-style payloads to an
    # OpenAI-compatible endpoint. Those payloads use `input` (or sometimes `prompt`)
    # instead of `messages`. We accept these fields and coerce them into `messages`
    # during validation to remain compatible across Cursor versions.
    input: Any | None = None
    prompt: str | None = None
    max_output_tokens: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_compat_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Map Responses API token field → Chat Completions field.
        if data.get("max_tokens") is None and isinstance(data.get("max_output_tokens"), int):
            data["max_tokens"] = data.get("max_output_tokens")

        # Coerce Responses API `input`/`prompt` into Chat Completions `messages`.
        if not data.get("messages"):
            if "input" in data:
                data["messages"] = cls._input_to_messages(data.get("input"))
            elif isinstance(prompt := data.get("prompt"), str) and prompt:
                data["messages"] = [{"role": "user", "content": prompt}]

        return data

    @staticmethod
    def _normalize_input_content(content: Any) -> Any:
        """
        Best-effort normalization of Responses API content into ChatMessage content.

        - `input_text` → `text`
        - `input_image` → `image_url`
        """
        if content is None:
            return ""
        if isinstance(content, str):
            return content

        # Responses-style single content part as object
        if isinstance(content, dict):
            return ChatCompletionRequest._normalize_input_content([content])

        if isinstance(content, list):
            normalized: list[dict[str, Any]] = []
            for part in content:
                if part is None:
                    continue
                if isinstance(part, str):
                    normalized.append({"type": "text", "text": part})
                    continue
                if not isinstance(part, dict):
                    normalized.append({"type": "text", "text": str(part)})
                    continue

                ptype = str(part.get("type", "") or "").strip()
                if ptype in {"input_text", "text", "output_text"}:
                    text = part.get("text")
                    if text is None:
                        # Some clients may use `content` or `delta` for text chunks.
                        text = (
                            part.get("content")
                            if part.get("content") is not None
                            else part.get("delta")
                        )
                    normalized.append({"type": "text", "text": "" if text is None else str(text)})
                    continue

                if ptype in {"input_image", "image_url"}:
                    # Try several common shapes:
                    # - {"type":"image_url","image_url":{"url":"...","detail":"auto"}}
                    # - {"type":"input_image","image_url":"..."}
                    # - {"type":"input_image","image_url":{"url":"..."}}
                    url = ""
                    detail: str = "auto"
                    image_url = (
                        part.get("image_url")
                        if part.get("image_url") is not None
                        else part.get("url")
                    )
                    if isinstance(image_url, dict):
                        url = str(image_url.get("url") or "")
                        detail_val = image_url.get("detail")
                        if isinstance(detail_val, str):
                            detail = detail_val
                    elif isinstance(image_url, str):
                        url = image_url

                    if detail not in {"auto", "low", "high"}:
                        detail = "auto"
                    normalized.append(
                        {"type": "image_url", "image_url": {"url": url, "detail": detail}}
                    )
                    continue

                # Fallback: preserve information as text.
                normalized.append({"type": "text", "text": str(part)})

            # If we only ended up with text parts, returning a list is still valid
            # (multimodal format). Keep it as list for deterministic parsing.
            return normalized

        return str(content)

    @staticmethod
    def _input_to_messages(input_value: Any) -> list[dict[str, Any]]:
        """Convert Responses API `input` into Chat Completions `messages`."""
        if input_value is None:
            return [{"role": "user", "content": ""}]
        if isinstance(input_value, str):
            return [{"role": "user", "content": input_value}]

        items: list[Any] = input_value if isinstance(input_value, list) else [input_value]

        messages: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict) and "role" in item:
                role = item.get("role") or "user"
                content = item.get("content")
                if content is None and "text" in item:
                    content = item.get("text")
                messages.append(
                    {
                        "role": role,
                        "content": ChatCompletionRequest._normalize_input_content(content),
                    }
                )
            else:
                # Fallback: treat unknown input shapes as a single user message.
                messages.append({"role": "user", "content": str(item)})
        return messages


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

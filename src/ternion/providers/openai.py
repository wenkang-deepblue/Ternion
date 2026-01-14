"""
OpenAI provider adapter.

Implements chat completion using the OpenAI API with full multimodal support.
"""

from collections.abc import AsyncGenerator
from typing import Any

import structlog
from openai import AsyncOpenAI

from ternion.core.models import ChatMessage, ImageContent, MessageRole, TextContent
from ternion.providers.base import BaseProvider, ProviderResponse
from ternion.utils.log_manager import log_manager

logger = structlog.get_logger(__name__)


class OpenAIProvider(BaseProvider):
    """
    OpenAI API provider adapter.

    Supports GPT-4, GPT-4 Vision, and other OpenAI models with
    full multimodal (image) support.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        default_model: str = "gpt-4-turbo",
        **kwargs: Any,
    ) -> None:
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
            base_url: Optional custom base URL (for Azure or proxies)
            default_model: Default model to use
            **kwargs: Additional configuration
        """
        super().__init__(api_key, **kwargs)
        self._default_model = default_model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    @property
    def name(self) -> str:
        """Return provider name."""
        return "openai"

    @property
    def default_model(self) -> str:
        """Return default model."""
        return self._default_model

    async def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """
        Generate a non-streaming chat completion.

        Args:
            messages: List of chat messages
            model: Model to use (defaults to gpt-4-turbo)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            ProviderResponse with the generated content
        """
        model = model or self._default_model
        converted = self._convert_messages(messages)

        logger.debug(
            "openai_chat_completion",
            model=model,
            message_count=len(messages),
        )

        # Build API parameters - only include max_tokens if specified
        api_params: dict[str, Any] = {
            "model": model,
            "messages": converted,
            "temperature": temperature,
            "stream": False,
            **kwargs,
        }
        if max_tokens is not None:
            api_params["max_tokens"] = max_tokens
        try:
            response = await self._client.chat.completions.create(**api_params)  # type: ignore
        except Exception as e:
            if self._is_non_chat_model_error(e):
                prompt = self._messages_to_prompt(messages)
                if prompt is None:
                    raise
                completion_params: dict[str, Any] = {
                    "model": model,
                    "prompt": prompt,
                    "temperature": temperature,
                    **kwargs,
                }
                if max_tokens is not None:
                    completion_params["max_tokens"] = max_tokens
                completion = await self._client.completions.create(**completion_params)  # type: ignore
                choice = completion.choices[0]
                usage = completion.usage

                prompt_tokens = usage.prompt_tokens if usage else 0
                completion_tokens = usage.completion_tokens if usage else 0
                total_tokens = usage.total_tokens if usage else 0

                logger.info(
                    "openai_token_usage",
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    reasoning_tokens=0,
                    total_tokens=total_tokens,
                )

                log_manager.emit_token_usage(
                    provider="openai",
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    thoughts_tokens=0,
                    total_tokens=total_tokens,
                )

                return ProviderResponse(
                    content=getattr(choice, "text", "") or "",
                    finish_reason=getattr(choice, "finish_reason", None),
                    usage={
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "reasoning_tokens": 0,
                        "total_tokens": total_tokens,
                    },
                    raw_response=completion,
                )
            raise

        choice = response.choices[0]
        usage = response.usage
        tool_calls = None
        if hasattr(choice, "message") and choice.message is not None:
            raw_tool_calls = getattr(choice.message, "tool_calls", None)
            if raw_tool_calls:
                tool_calls = []
                for item in raw_tool_calls:
                    if isinstance(item, dict):
                        tool_calls.append(item)
                    elif hasattr(item, "model_dump"):
                        tool_calls.append(item.model_dump())
                    elif hasattr(item, "to_dict"):
                        tool_calls.append(item.to_dict())
                    else:
                        tool_calls.append({
                            "id": getattr(item, "id", ""),
                            "type": getattr(item, "type", ""),
                            "function": getattr(item, "function", None),
                        })

        # Extract token counts
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        # Extract reasoning tokens if available (included in completion_tokens)
        reasoning_tokens = 0
        if usage and hasattr(usage, "completion_tokens_details") and usage.completion_tokens_details:
            reasoning_tokens = getattr(usage.completion_tokens_details, "reasoning_tokens", 0) or 0

        logger.info(
            "openai_token_usage",
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning_tokens=reasoning_tokens,
            total_tokens=total_tokens,
        )

        # Emit to UI log panel
        log_manager.emit_token_usage(
            provider="openai",
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            thoughts_tokens=reasoning_tokens,
            total_tokens=total_tokens,
        )

        return ProviderResponse(
            content=choice.message.content or "",
            finish_reason=choice.finish_reason,
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "reasoning_tokens": reasoning_tokens,
                "total_tokens": total_tokens,
            },
            raw_response=response,
        )

    async def chat_completion_stream(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming chat completion.

        Args:
            messages: List of chat messages
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Yields:
            Content chunks as they are generated
        """
        model = model or self._default_model
        converted = self._convert_messages(messages)

        logger.debug(
            "openai_chat_completion_stream",
            model=model,
            message_count=len(messages),
        )

        # Build API parameters - only include max_tokens if specified
        api_params: dict[str, Any] = {
            "model": model,
            "messages": converted,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
            **kwargs,
        }
        if max_tokens is not None:
            api_params["max_tokens"] = max_tokens

        stream = await self._client.chat.completions.create(**api_params)  # type: ignore

        received_text = ""
        usage_data = None

        async for chunk in stream:
            # Check for usage data in final chunk
            if hasattr(chunk, "usage") and chunk.usage:
                usage_data = chunk.usage

            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                received_text += content
                yield content

        # Log token usage after stream completes
        if usage_data:
            prompt_tokens = usage_data.prompt_tokens or 0
            completion_tokens = usage_data.completion_tokens or 0
            total_tokens = usage_data.total_tokens or 0

            # Extract reasoning tokens if available
            reasoning_tokens = 0
            if hasattr(usage_data, "completion_tokens_details") and usage_data.completion_tokens_details:
                reasoning_tokens = getattr(usage_data.completion_tokens_details, "reasoning_tokens", 0) or 0

            logger.info(
                "openai_token_usage",
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                reasoning_tokens=reasoning_tokens,
                total_tokens=total_tokens,
            )

            log_manager.emit_token_usage(
                provider="openai",
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                thoughts_tokens=reasoning_tokens,
                total_tokens=total_tokens,
            )

            # Record usage for cost tracking
            from ternion.core.budget import budget_manager
            budget_manager.record_usage(
                provider="openai",
                model=model,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                thoughts_tokens=reasoning_tokens,
            )
        elif received_text:
            # Fallback: estimate tokens from received content
            from ternion.utils.token_estimator import estimate_tokens_from_text

            estimated_output = estimate_tokens_from_text(received_text)
            logger.warning(
                "openai_token_usage_estimated",
                model=model,
                estimated_output_tokens=estimated_output,
            )

            log_manager.emit_token_usage_interrupted(
                provider="openai",
                model=model,
                prompt_tokens=0,
                received_output_tokens=estimated_output,
                estimated_remaining=0,
                estimated_total=estimated_output,
            )
            # Record estimated usage for interrupted streams
            from ternion.core.budget import budget_manager
            budget_manager.record_usage(
                provider="openai",
                model=model,
                input_tokens=0,
                output_tokens=estimated_output,
                thoughts_tokens=0,
            )

    async def is_available(self) -> bool:
        """
        Check if OpenAI API is available.

        Returns:
            True if API key is set and API is reachable
        """
        if not self.api_key:
            return False

        try:
            # Make a minimal API call to check availability
            await self._client.models.list()
            return True
        except Exception as e:
            logger.warning("openai_unavailable", error=str(e))
            return False

    def _convert_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """
        Convert ChatMessage objects to OpenAI format.

        Handles multimodal content (text + images) for vision models.

        Args:
            messages: List of ChatMessage objects

        Returns:
            List of dictionaries in OpenAI's expected format
        """
        result = []
        for msg in messages:
            out: dict[str, Any] = {"role": msg.role.value}
            if msg.name:
                out["name"] = msg.name

            # Tool role messages must include tool_call_id for OpenAI compatibility.
            if msg.role == MessageRole.TOOL:
                out["content"] = self._content_to_text(msg.content) or ""
                if msg.tool_call_id:
                    out["tool_call_id"] = msg.tool_call_id
                result.append(out)
                continue

            if isinstance(msg.content, str):
                out["content"] = msg.content
            elif isinstance(msg.content, list):
                # Multimodal content
                content_parts = []
                for part in msg.content:
                    if isinstance(part, TextContent):
                        content_parts.append({
                            "type": "text",
                            "text": part.text,
                        })
                    elif isinstance(part, ImageContent):
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {
                                "url": part.image_url.url,
                                "detail": part.image_url.detail,
                            },
                        })
                out["content"] = content_parts
            elif msg.content is None:
                out["content"] = None
            else:
                out["content"] = str(msg.content)

            if msg.tool_calls:
                out["tool_calls"] = msg.tool_calls

            result.append(out)
        return result

    @staticmethod
    def _is_non_chat_model_error(error: Exception) -> bool:
        """
        Detect errors that indicate a model is not compatible with /v1/chat/completions.

        We intentionally keep this logic conservative and only trigger the fallback when the
        provider explicitly indicates the endpoint mismatch.
        """
        msg = str(error).lower()
        return ("not a chat model" in msg) and ("v1/chat/completions" in msg)

    def _messages_to_prompt(self, messages: list[ChatMessage]) -> str | None:
        """
        Convert chat messages into a single prompt string for /v1/completions fallback.

        Returns None if messages contain images (unsupported for text completions fallback).
        """
        parts: list[str] = []
        for msg in messages:
            role = msg.role.value.upper()
            text = self._content_to_text(msg.content)
            if text is None:
                return None
            parts.append(f"{role}:\n{text}\n\n")
        parts.append("ASSISTANT:\n")
        return "".join(parts)

    @staticmethod
    def _content_to_text(content: object) -> str | None:
        """Best-effort conversion of message content into plain text."""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            out: list[str] = []
            for part in content:
                if isinstance(part, TextContent):
                    out.append(part.text)
                elif isinstance(part, ImageContent):
                    return None
                else:
                    out.append(str(part))
            return "\n".join(out)
        return str(content)

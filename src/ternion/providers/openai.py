"""
OpenAI provider adapter.

Implements chat completion using the OpenAI API with full multimodal support.
"""

import structlog
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI

from ternion.core.models import ChatMessage, ImageContent, TextContent
from ternion.providers.base import BaseProvider, ProviderResponse

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

        response = await self._client.chat.completions.create(
            model=model,
            messages=converted,  # type: ignore
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            **kwargs,
        )

        choice = response.choices[0]
        return ProviderResponse(
            content=choice.message.content or "",
            finish_reason=choice.finish_reason,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
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

        stream = await self._client.chat.completions.create(
            model=model,
            messages=converted,  # type: ignore
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

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
            if isinstance(msg.content, str):
                result.append({
                    "role": msg.role.value,
                    "content": msg.content,
                })
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
                result.append({
                    "role": msg.role.value,
                    "content": content_parts,
                })
            else:
                result.append({
                    "role": msg.role.value,
                    "content": str(msg.content) if msg.content else "",
                })
        return result

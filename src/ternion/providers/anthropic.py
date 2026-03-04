"""
Anthropic provider adapter.

Implements chat completion using the Anthropic API with full multimodal support.
"""

from collections.abc import AsyncGenerator
from typing import Any

import httpx
import structlog
from anthropic import AsyncAnthropic

from ternion.core.budget import budget_manager
from ternion.core.models import ChatMessage, ImageContent, MessageRole, TextContent
from ternion.providers.base import BaseProvider, ProviderResponse
from ternion.utils.log_manager import log_manager

logger = structlog.get_logger(__name__)


class AnthropicProvider(BaseProvider):
    """
    Anthropic API provider adapter.

    Supports Claude 3+ models with full multimodal (image) support.
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = "claude-3-5-sonnet-latest",
        **kwargs: Any,
    ) -> None:
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key
            default_model: Default model to use
            **kwargs: Additional configuration
        """
        super().__init__(api_key, **kwargs)
        self._default_model = default_model
        self._client = AsyncAnthropic(api_key=api_key)

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def default_model(self) -> str:
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
            model: Model to use (defaults to claude-3-5-sonnet)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            ProviderResponse with the generated content
        """
        model = model or self._default_model
        system_prompt, converted = self._convert_messages(messages)

        logger.debug(
            "anthropic_chat_completion",
            model=model,
            message_count=len(messages),
        )

        response = await self._client.messages.create(
            model=model,
            messages=converted,
            system=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            **kwargs,
        )

        content = ""
        thinking_text = ""
        for block in response.content:
            if hasattr(block, "type"):
                if block.type == "thinking" and hasattr(block, "thinking"):
                    thinking_text += block.thinking
                elif block.type == "text" and hasattr(block, "text"):
                    content += block.text
            elif hasattr(block, "text"):
                content += block.text

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        total_tokens = input_tokens + output_tokens

        # Anthropic does not report thinking tokens separately; estimate from UTF-8 byte length
        # (4 bytes/token heuristic). This count is already subsumed in output_tokens.
        thinking_tokens = len(thinking_text.encode("utf-8")) // 4 if thinking_text else 0

        logger.info(
            "anthropic_token_usage",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            total_tokens=total_tokens,
        )

        log_manager.emit_token_usage(
            provider="anthropic",
            model=model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            thoughts_tokens=thinking_tokens,
            total_tokens=total_tokens,
        )

        budget_manager.record_usage(
            provider="anthropic",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thoughts_tokens=thinking_tokens,
            context_length=total_tokens,
        )

        return ProviderResponse(
            content=content,
            finish_reason=response.stop_reason,
            usage={
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "thoughts_tokens": thinking_tokens,
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
        system_prompt, converted = self._convert_messages(messages)

        logger.debug(
            "anthropic_chat_completion_stream",
            model=model,
            message_count=len(messages),
        )

        async with self._client.messages.stream(
            model=model,
            messages=converted,
            system=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            **kwargs,
        ) as stream:
            received_text = ""
            async for text in stream.text_stream:
                received_text += text
                yield text

            final_message = await stream.get_final_message()
            if final_message and final_message.usage:
                input_tokens = final_message.usage.input_tokens
                output_tokens = final_message.usage.output_tokens
                total_tokens = input_tokens + output_tokens

                thinking_tokens = 0
                if final_message.content:
                    for block in final_message.content:
                        if (
                            hasattr(block, "type")
                            and block.type == "thinking"
                            and hasattr(block, "thinking")
                        ):
                            thinking_tokens += len(block.thinking.encode("utf-8")) // 4

                logger.info(
                    "anthropic_token_usage",
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    thinking_tokens=thinking_tokens,
                    total_tokens=total_tokens,
                )

                log_manager.emit_token_usage(
                    provider="anthropic",
                    model=model,
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                    thoughts_tokens=thinking_tokens,
                    total_tokens=total_tokens,
                )

                budget_manager.record_usage(
                    provider="anthropic",
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    thoughts_tokens=thinking_tokens,
                    context_length=total_tokens,
                )
            elif received_text:
                # Usage metadata unavailable; estimate token count from received text length as fallback.
                from ternion.utils.token_estimator import estimate_tokens_from_text

                estimated_output = estimate_tokens_from_text(received_text)
                logger.warning(
                    "anthropic_token_usage_estimated",
                    model=model,
                    estimated_output_tokens=estimated_output,
                )

                log_manager.emit_token_usage_interrupted(
                    provider="anthropic",
                    model=model,
                    prompt_tokens=0,
                    received_output_tokens=estimated_output,
                    estimated_remaining=0,
                    estimated_total=estimated_output,
                )
                budget_manager.record_usage(
                    provider="anthropic",
                    model=model,
                    input_tokens=0,
                    output_tokens=estimated_output,
                    thoughts_tokens=0,
                )

    async def is_available(self) -> bool:
        """
        Check if Anthropic API is available.

        Returns:
            True if API key is set and API is reachable
        """
        if not self.api_key:
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    timeout=10.0,
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning("anthropic_unavailable", error=str(e))
            return False

    def _convert_messages(self, messages: list[ChatMessage]) -> tuple[str, list[dict[str, Any]]]:
        """
        Convert ChatMessage objects to Anthropic format.

        Anthropic requires the system prompt to be separate from messages.
        Handles multimodal content (text + images) for vision models.

        Args:
            messages: List of ChatMessage objects

        Returns:
            Tuple of (system_prompt, converted_messages)
        """
        system_prompt = ""
        result = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                if isinstance(msg.content, str):
                    system_prompt = msg.content
                continue

            role = "user" if msg.role == MessageRole.USER else "assistant"

            if isinstance(msg.content, str):
                result.append(
                    {
                        "role": role,
                        "content": msg.content,
                    }
                )
            elif isinstance(msg.content, list):
                content_parts = []
                for part in msg.content:
                    if isinstance(part, TextContent):
                        content_parts.append(
                            {
                                "type": "text",
                                "text": part.text,
                            }
                        )
                    elif isinstance(part, ImageContent):
                        image_data = self._extract_image_data(part.image_url.url)
                        if image_data:
                            content_parts.append(
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": image_data["media_type"],
                                        "data": image_data["data"],
                                    },
                                }
                            )
                        else:
                            logger.warning(
                                "anthropic_image_extract_failed",
                                url=part.image_url.url[:50],
                            )
                result.append(
                    {
                        "role": role,
                        "content": content_parts,
                    }
                )
            else:
                result.append(
                    {
                        "role": role,
                        "content": str(msg.content) if msg.content else "",
                    }
                )

        return system_prompt, result

    def _extract_image_data(self, url: str) -> dict[str, str] | None:
        """
        Extract base64 image data from a data URL or fetch from URL.

        Args:
            url: Image URL or data URI

        Returns:
            Dict with media_type and data, or None if extraction fails
        """
        if url.startswith("data:"):
            # Parse data URI: data:image/png;base64,<data>
            try:
                header, data = url.split(",", 1)
                media_type = header.split(";")[0].replace("data:", "")
                return {"media_type": media_type, "data": data}
            except Exception:
                return None
        else:
            # Remote URL fetching is intentionally unsupported; only data URIs are accepted.
            logger.warning("image_url_not_supported", url=url[:50])
            return None

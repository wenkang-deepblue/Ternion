"""
Anthropic provider adapter.

Implements chat completion using the Anthropic API with full multimodal support.
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import structlog
from anthropic import AsyncAnthropic

from ternion.core.budget import budget_manager
from ternion.core.model_catalog import model_catalog_service
from ternion.core.models import ChatMessage, ImageContent, MessageRole, TextContent
from ternion.providers.base import BaseProvider, ProviderResponse
from ternion.providers.resilience import (
    RETRY_MAX_ATTEMPTS,
    compute_backoff_delay,
    get_provider_semaphore,
    get_retry_after_seconds,
    is_retryable_provider_error,
    run_with_provider_resilience,
)
from ternion.utils.log_manager import log_manager
from ternion.utils.model_ids import normalize_anthropic_model_id_for_api

logger = structlog.get_logger(__name__)

# Default output budget when callers do not request one.
_DEFAULT_MAX_OUTPUT_TOKENS = 4096

# Smallest max-output limit across supported Anthropic models (Claude Opus 4.1);
# used to clamp requests when the catalog has no entry for the model.
_FALLBACK_MAX_OUTPUT_TOKENS = 32000


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
        cache_prompt: bool = True,
        **kwargs: Any,
    ) -> ProviderResponse:
        """
        Generate a non-streaming chat completion.

        Args:
            messages: List of chat messages
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate (clamped to the model's
                catalog max_output_tokens)
            cache_prompt: Mark stable prefixes (system + conversation tail) with
                cache_control breakpoints for Anthropic prompt caching
            **kwargs: Additional parameters

        Returns:
            ProviderResponse with the generated content
        """
        model = model or self._default_model
        api_model = self._resolve_api_model_id(model)
        system_prompt, converted = self._convert_messages(messages)
        system_param, converted = self._apply_prompt_caching(system_prompt, converted, cache_prompt)
        effective_max_tokens = self._clamp_max_tokens(model, max_tokens)

        logger.debug(
            "anthropic_chat_completion",
            model=model,
            api_model=api_model,
            message_count=len(messages),
            cache_prompt=cache_prompt,
            max_tokens=effective_max_tokens,
        )

        response = await run_with_provider_resilience(
            self.name,
            lambda: self._client.messages.create(
                model=api_model,
                messages=converted,
                system=system_param,
                temperature=temperature,
                max_tokens=effective_max_tokens,
                **kwargs,
            ),
            operation_name="chat_completion",
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

        cache_read_tokens, cache_write_tokens = self._extract_cache_usage(response.usage)
        # Anthropic reports cached prompt tokens separately from input_tokens;
        # normalize to a total that includes both cache subsets.
        input_tokens = response.usage.input_tokens + cache_read_tokens + cache_write_tokens
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
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
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
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )

        return ProviderResponse(
            content=content,
            finish_reason=response.stop_reason,
            usage={
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "thoughts_tokens": thinking_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cache_write_tokens": cache_write_tokens,
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
        cache_prompt: bool = True,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming chat completion.

        Transient open failures (rate limit, overload) are retried with backoff
        as long as no chunk has been yielded yet.

        Args:
            messages: List of chat messages
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate (clamped to the model's
                catalog max_output_tokens)
            cache_prompt: Mark stable prefixes with cache_control breakpoints
            **kwargs: Additional parameters

        Yields:
            Content chunks as they are generated
        """
        model = model or self._default_model
        api_model = self._resolve_api_model_id(model)
        system_prompt, converted = self._convert_messages(messages)
        system_param, converted = self._apply_prompt_caching(system_prompt, converted, cache_prompt)
        effective_max_tokens = self._clamp_max_tokens(model, max_tokens)

        logger.debug(
            "anthropic_chat_completion_stream",
            model=model,
            api_model=api_model,
            message_count=len(messages),
            cache_prompt=cache_prompt,
            max_tokens=effective_max_tokens,
        )

        async with get_provider_semaphore(self.name):
            attempt = 0
            while True:
                attempt += 1
                yielded_any = False
                try:
                    async for text in self._stream_and_record(
                        model=model,
                        api_model=api_model,
                        converted=converted,
                        system_param=system_param,
                        temperature=temperature,
                        max_tokens=effective_max_tokens,
                        extra_kwargs=kwargs,
                    ):
                        yielded_any = True
                        yield text
                    return
                except Exception as exc:
                    if (
                        yielded_any
                        or attempt >= RETRY_MAX_ATTEMPTS
                        or not is_retryable_provider_error(exc)
                    ):
                        raise
                    delay = compute_backoff_delay(attempt, get_retry_after_seconds(exc))
                    logger.warning(
                        "provider_call_retry",
                        provider=self.name,
                        operation="chat_completion_stream",
                        attempt=attempt,
                        max_attempts=RETRY_MAX_ATTEMPTS,
                        delay_seconds=round(delay, 2),
                        error=str(exc)[:200],
                    )
                    await asyncio.sleep(delay)

    async def _stream_and_record(
        self,
        *,
        model: str,
        api_model: str,
        converted: list[dict[str, Any]],
        system_param: str | list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        extra_kwargs: dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        """Open one streaming request, yield text chunks, and record final usage."""
        async with self._client.messages.stream(
            model=api_model,
            messages=converted,
            system=system_param,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra_kwargs,
        ) as stream:
            received_text = ""
            async for text in stream.text_stream:
                received_text += text
                yield text

            final_message = await stream.get_final_message()
            if final_message and final_message.usage:
                cache_read_tokens, cache_write_tokens = self._extract_cache_usage(
                    final_message.usage
                )
                input_tokens = (
                    final_message.usage.input_tokens + cache_read_tokens + cache_write_tokens
                )
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
                    cache_read_tokens=cache_read_tokens,
                    cache_write_tokens=cache_write_tokens,
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
                    cache_read_tokens=cache_read_tokens,
                    cache_write_tokens=cache_write_tokens,
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

    @staticmethod
    def _resolve_api_model_id(model: str) -> str:
        """Resolve the Anthropic API model ID from the catalog when available."""
        catalog_model = model_catalog_service.get_model_cached(model)
        if catalog_model is not None and catalog_model.provider == "anthropic":
            if catalog_model.api_model_id:
                return catalog_model.api_model_id
            return catalog_model.id
        return normalize_anthropic_model_id_for_api(model)

    @staticmethod
    def _clamp_max_tokens(model: str, max_tokens: int | None) -> int:
        """
        Clamp the requested output budget to the model's catalog max_output_tokens.

        Anthropic rejects requests whose max_tokens exceeds the model limit, so
        oversized phase budgets are reduced instead of failing the call.

        Args:
            model: Configured model ID used for catalog lookup.
            max_tokens: Requested output budget, or None for the default.

        Returns:
            Effective max_tokens value safe to send to the API.
        """
        requested = (
            max_tokens
            if isinstance(max_tokens, int) and max_tokens > 0
            else _DEFAULT_MAX_OUTPUT_TOKENS
        )
        limit: int | None = None
        try:
            catalog_model = model_catalog_service.get_model_cached(model)
        except Exception:
            catalog_model = None
        if catalog_model is not None:
            raw_limit = getattr(catalog_model, "max_output_tokens", None)
            if isinstance(raw_limit, int) and raw_limit > 0:
                limit = raw_limit
        if limit is None:
            limit = _FALLBACK_MAX_OUTPUT_TOKENS
        return min(requested, limit)

    @staticmethod
    def _apply_prompt_caching(
        system_prompt: str,
        converted: list[dict[str, Any]],
        cache_prompt: bool,
    ) -> tuple[str | list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Attach Anthropic cache_control breakpoints to stable prompt prefixes.

        Places at most two breakpoints: one on the system block and one on the
        final content block of the last message, enabling incremental prefix
        caching across multi-round tool loops (previous rounds become cache
        reads on the next call).

        Args:
            system_prompt: Extracted system prompt string (may be empty).
            converted: Anthropic-format message list.
            cache_prompt: When False, return inputs unchanged.

        Returns:
            Tuple of (system parameter, message list) ready for messages.create.
        """
        if not cache_prompt:
            return system_prompt, converted

        cache_control = {"type": "ephemeral"}

        system_param: str | list[dict[str, Any]] = system_prompt
        if system_prompt:
            system_param = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": cache_control,
                }
            ]

        if not converted:
            return system_param, converted

        messages = list(converted)
        last_message = dict(messages[-1])
        content = last_message.get("content")
        if isinstance(content, str):
            if content:
                last_message["content"] = [
                    {
                        "type": "text",
                        "text": content,
                        "cache_control": cache_control,
                    }
                ]
                messages[-1] = last_message
        elif isinstance(content, list) and content:
            blocks = list(content)
            last_block = blocks[-1]
            if isinstance(last_block, dict):
                blocks[-1] = {**last_block, "cache_control": cache_control}
                last_message["content"] = blocks
                messages[-1] = last_message
        return system_param, messages

    @staticmethod
    def _extract_cache_usage(usage: Any) -> tuple[int, int]:
        """
        Extract prompt-cache token counts from an Anthropic usage object.

        Args:
            usage: Usage object from an Anthropic response.

        Returns:
            Tuple of (cache_read_tokens, cache_write_tokens); zeros when absent.
        """
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        return int(cache_read), int(cache_write)

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
        Extract base64 image data from a data URI.

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

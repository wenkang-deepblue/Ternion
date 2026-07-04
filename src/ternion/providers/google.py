"""
Google Gemini provider adapter.

Implements chat completion using the Google Generative AI API (new SDK) with multimodal support.
"""

from collections.abc import AsyncGenerator
from typing import Any

import structlog

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover
    # Optional dependency. Keep module importable even if Google SDK is not installed.
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]

from ternion.core.budget import budget_manager
from ternion.core.models import ChatMessage, ImageContent, MessageRole, TextContent
from ternion.providers.base import BaseProvider, ProviderResponse, clamp_max_output_tokens
from ternion.providers.resilience import (
    get_provider_semaphore,
    run_with_provider_resilience,
    run_with_retry,
)
from ternion.utils.log_manager import log_manager
from ternion.utils.token_estimator import estimate_tokens_from_text

logger = structlog.get_logger(__name__)


class GoogleProvider(BaseProvider):
    """
    Google Generative AI (Gemini) provider adapter.

    Supports Gemini models with full multimodal (image) support.
    Uses the modern `google-genai` SDK (v1.0+).
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = "gemini-2.0-flash",
        **kwargs: Any,
    ) -> None:
        """
        Initialize Google provider.

        Args:
            api_key: Google API key
            default_model: Default model to use
            **kwargs: Additional configuration
        """
        super().__init__(api_key, **kwargs)
        self._default_model = default_model
        if genai is None:
            raise ImportError(
                "Google provider optional dependency missing. "
                "Please install the Google GenAI SDK (google-genai) to use Gemini."
            )
        self._client = genai.Client(api_key=api_key)

    @property
    def name(self) -> str:
        return "google"

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
            model: Model to use (defaults to gemini-2.0-flash)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            cache_prompt: Accepted for interface parity; Gemini applies implicit
                context caching automatically on stable prefixes
            **kwargs: Additional parameters

        Returns:
            ProviderResponse with the generated content
        """
        del cache_prompt  # Gemini implicit caching is automatic; no request flag exists.
        model_name = model or self._default_model
        max_tokens = clamp_max_output_tokens(model_name, max_tokens)
        system_instruction, contents = self._convert_messages(messages)

        logger.debug(
            "google_chat_completion",
            model=model_name,
            message_count=len(messages),
            max_tokens=max_tokens,
        )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction if system_instruction else None,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        response = await run_with_provider_resilience(
            self.name,
            lambda: self._client.aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            ),
            operation_name="chat_completion",
        )

        usage_metadata = response.usage_metadata
        prompt_tokens = (usage_metadata.prompt_token_count or 0) if usage_metadata else 0
        candidates_tokens = (usage_metadata.candidates_token_count or 0) if usage_metadata else 0

        thoughts_tokens = 0
        cache_read_tokens = 0
        if usage_metadata:
            # thoughts_token_count is model-dependent; absent on standard models.
            thoughts_tokens = getattr(usage_metadata, "thoughts_token_count", 0) or 0
            # cached_content_token_count is the prompt subset served from Gemini's
            # implicit/explicit context cache; it is included in prompt_token_count.
            cache_read_tokens = getattr(usage_metadata, "cached_content_token_count", 0) or 0

        total_tokens = (usage_metadata.total_token_count or 0) if usage_metadata else 0
        output_tokens = candidates_tokens + thoughts_tokens

        logger.info(
            "gemini_token_usage",
            model=model_name,
            prompt_tokens=prompt_tokens,
            candidates_tokens=candidates_tokens,
            thoughts_tokens=thoughts_tokens,
            cache_read_tokens=cache_read_tokens,
            total_tokens=total_tokens,
        )

        log_manager.emit_token_usage(
            provider="google",
            model=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=output_tokens,
            thoughts_tokens=thoughts_tokens,
            total_tokens=total_tokens,
        )

        budget_manager.record_usage(
            provider="google",
            model=model_name,
            input_tokens=prompt_tokens,
            output_tokens=output_tokens,
            thoughts_tokens=thoughts_tokens,
            context_length=total_tokens,
            cache_read_tokens=cache_read_tokens,
        )

        text_content = response.text or ""

        return ProviderResponse(
            content=text_content,
            finish_reason="stop",
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": candidates_tokens,
                "thoughts_tokens": thoughts_tokens,
                "cache_read_tokens": cache_read_tokens,
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

        Args:
            messages: List of chat messages
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            cache_prompt: Accepted for interface parity; Gemini applies implicit
                context caching automatically on stable prefixes
            **kwargs: Additional parameters

        Yields:
            Content chunks as they are generated
        """
        del cache_prompt  # Gemini implicit caching is automatic; no request flag exists.
        model_name = model or self._default_model
        max_tokens = clamp_max_output_tokens(model_name, max_tokens)
        system_instruction, contents = self._convert_messages(messages)

        logger.debug(
            "google_chat_completion_stream",
            model=model_name,
            message_count=len(messages),
            max_tokens=max_tokens,
        )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction if system_instruction else None,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        last_chunk = None
        received_text = ""

        async with get_provider_semaphore(self.name):
            response_stream = await run_with_retry(
                self.name,
                lambda: self._client.aio.models.generate_content_stream(
                    model=model_name,
                    contents=contents,
                    config=config,
                ),
                operation_name="chat_completion_stream",
            )

            async for chunk in response_stream:
                last_chunk = chunk
                if chunk.text:
                    received_text += chunk.text
                    yield chunk.text

        # Google SDK only populates usage_metadata on the final streaming chunk; track last_chunk to capture it.
        if last_chunk and hasattr(last_chunk, "usage_metadata") and last_chunk.usage_metadata:
            usage_metadata = last_chunk.usage_metadata
            prompt_tokens = (usage_metadata.prompt_token_count or 0) if usage_metadata else 0
            candidates_tokens = (
                (usage_metadata.candidates_token_count or 0) if usage_metadata else 0
            )
            thoughts_tokens = getattr(usage_metadata, "thoughts_token_count", 0) or 0
            cache_read_tokens = getattr(usage_metadata, "cached_content_token_count", 0) or 0
            total_tokens = (usage_metadata.total_token_count or 0) if usage_metadata else 0
            output_tokens = candidates_tokens + thoughts_tokens

            logger.info(
                "gemini_token_usage",
                model=model_name,
                prompt_tokens=prompt_tokens,
                candidates_tokens=candidates_tokens,
                thoughts_tokens=thoughts_tokens,
                cache_read_tokens=cache_read_tokens,
                total_tokens=total_tokens,
            )

            log_manager.emit_token_usage(
                provider="google",
                model=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=output_tokens,
                thoughts_tokens=thoughts_tokens,
                total_tokens=total_tokens,
            )

            budget_manager.record_usage(
                provider="google",
                model=model_name,
                input_tokens=prompt_tokens,
                output_tokens=output_tokens,
                thoughts_tokens=thoughts_tokens,
                context_length=total_tokens,
                cache_read_tokens=cache_read_tokens,
            )
        elif received_text:
            estimated_output = estimate_tokens_from_text(received_text)
            logger.warning(
                "gemini_token_usage_estimated",
                model=model_name,
                estimated_output_tokens=estimated_output,
            )
            log_manager.emit_token_usage_interrupted(
                provider="google",
                model=model_name,
                prompt_tokens=0,
                received_output_tokens=estimated_output,
                estimated_remaining=0,
                estimated_total=estimated_output,
            )
            budget_manager.record_usage(
                provider="google",
                model=model_name,
                input_tokens=0,
                output_tokens=estimated_output,
                thoughts_tokens=0,
            )

    async def is_available(self) -> bool:
        """
        Check if Google API is available.

        Returns:
            True if API key is set and API is reachable
        """
        if not self.api_key:
            return False

        try:
            # google-genai v1.0 returns an async pager, not a direct awaitable;
            # pull the first item to confirm reachability without exhausting the page.
            pager = await self._client.aio.models.list()
            aiter = pager.__aiter__()
            try:
                await aiter.__anext__()
                return True
            except StopAsyncIteration:
                return False
            finally:
                aclose = getattr(aiter, "aclose", None)
                if aclose is not None:
                    await aclose()
        except Exception as e:
            logger.warning("google_unavailable", error=str(e))
            return False

    def _convert_messages(self, messages: list[ChatMessage]) -> tuple[str, list[dict[str, Any]]]:
        """
        Convert ChatMessage objects to Google Gemini format.

        System messages are extracted into a separate instruction string; the Gemini API
        does not accept them inline in contents. TOOL-role messages are mapped to "model"
        with a warning, as native tool calling is not supported by this provider.

        Args:
            messages: List of ChatMessage objects

        Returns:
            Tuple of (system_instruction, contents_list)
        """
        system_instruction = ""
        contents = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                if isinstance(msg.content, str):
                    system_instruction = msg.content
                continue

            if msg.role == MessageRole.TOOL:
                logger.warning(
                    "google_tool_role_mapped_to_model",
                    message_name=msg.name,
                    tool_call_id=getattr(msg, "tool_call_id", None),
                )
            role = "user" if msg.role == MessageRole.USER else "model"
            parts = self._convert_content_to_parts(msg.content)

            contents.append(
                {
                    "role": role,
                    "parts": parts,
                }
            )

        return system_instruction, contents

    def _convert_content_to_parts(self, content: Any) -> list[Any]:
        """
        Convert message content to Gemini parts format.

        Args:
            content: Message content (string or list of content parts)

        Returns:
            List of part dicts in Gemini API format
        """
        if isinstance(content, str):
            return [{"text": content}]

        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, TextContent):
                    parts.append({"text": part.text})
                elif isinstance(part, ImageContent):
                    image_data = self._extract_image_data(part.image_url.url)
                    if image_data:
                        parts.append(
                            {
                                "inline_data": {
                                    "mime_type": image_data["mime_type"],
                                    "data": image_data["data"],
                                }
                            }
                        )
                    else:
                        logger.warning(
                            "google_image_extract_failed",
                            url=part.image_url.url[:50],
                        )
            return parts

        return [{"text": str(content) if content else ""}]

    def _extract_image_data(self, url: str) -> dict[str, str] | None:
        """
        Extract base64 image data from a data URL.

        Args:
            url: Image URL or data URI

        Returns:
            Dict with mime_type and data, or None if extraction fails
        """
        if url.startswith("data:"):
            try:
                header, data = url.split(",", 1)
                mime_type = header.split(";")[0].replace("data:", "")
                return {"mime_type": mime_type, "data": data}
            except Exception:
                return None
        else:
            logger.warning("image_url_not_supported", url=url[:50])
            return None

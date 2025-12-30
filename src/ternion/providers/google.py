"""
Google Gemini provider adapter.

Implements chat completion using the Google Generative AI API with multimodal support.
"""

import base64
import structlog
from collections.abc import AsyncGenerator
from typing import Any

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from ternion.core.budget import budget_manager
from ternion.core.models import ChatMessage, ImageContent, MessageRole, TextContent
from ternion.providers.base import BaseProvider, ProviderResponse
from ternion.utils.log_manager import log_manager
from ternion.utils.token_estimator import estimate_tokens_from_text

logger = structlog.get_logger(__name__)


class GoogleProvider(BaseProvider):
    """
    Google Generative AI (Gemini) provider adapter.

    Supports Gemini models with full multimodal (image) support.
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
        genai.configure(api_key=api_key)

    @property
    def name(self) -> str:
        """Return provider name."""
        return "google"

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
            model: Model to use (defaults to gemini-2.0-flash)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            ProviderResponse with the generated content
        """
        model_name = model or self._default_model
        system_instruction, history, last_message = self._convert_messages(messages)

        logger.debug(
            "google_chat_completion",
            model=model_name,
            message_count=len(messages),
        )

        # Create model with system instruction
        gen_model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction if system_instruction else None,
        )

        # Start chat with history
        chat = gen_model.start_chat(history=history)

        # Generate response
        config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        response = await chat.send_message_async(
            last_message,
            generation_config=config,
        )

        # Extract token counts from usage_metadata
        usage_metadata = response.usage_metadata
        prompt_tokens = usage_metadata.prompt_token_count if usage_metadata else 0
        candidates_tokens = usage_metadata.candidates_token_count if usage_metadata else 0
        thoughts_tokens = getattr(usage_metadata, "thoughts_token_count", 0) or 0
        total_tokens = usage_metadata.total_token_count if usage_metadata else 0
        output_tokens = candidates_tokens + thoughts_tokens

        logger.info(
            "gemini_token_usage",
            model=model_name,
            prompt_tokens=prompt_tokens,
            candidates_tokens=candidates_tokens,
            thoughts_tokens=thoughts_tokens,
            total_tokens=total_tokens,
        )

        # Emit to UI log panel
        log_manager.emit_token_usage(
            provider="google",
            model=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=output_tokens,
            thoughts_tokens=thoughts_tokens,
            total_tokens=total_tokens,
        )

        return ProviderResponse(
            content=response.text,
            finish_reason="stop",
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": candidates_tokens,
                "thoughts_tokens": thoughts_tokens,
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
        model_name = model or self._default_model
        system_instruction, history, last_message = self._convert_messages(messages)

        logger.debug(
            "google_chat_completion_stream",
            model=model_name,
            message_count=len(messages),
        )

        # Create model with system instruction
        gen_model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction if system_instruction else None,
        )

        # Start chat with history
        chat = gen_model.start_chat(history=history)

        # Generate streaming response
        config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        response = await chat.send_message_async(
            last_message,
            generation_config=config,
            stream=True,
        )

        last_chunk = None
        received_text = ""
        async for chunk in response:
            last_chunk = chunk
            if chunk.text:
                received_text += chunk.text
                yield chunk.text

        # Log token usage from the final chunk
        if last_chunk and hasattr(last_chunk, "usage_metadata") and last_chunk.usage_metadata:
            usage_metadata = last_chunk.usage_metadata
            prompt_tokens = usage_metadata.prompt_token_count if usage_metadata else 0
            candidates_tokens = usage_metadata.candidates_token_count if usage_metadata else 0
            thoughts_tokens = getattr(usage_metadata, "thoughts_token_count", 0) or 0
            total_tokens = usage_metadata.total_token_count if usage_metadata else 0
            output_tokens = candidates_tokens + thoughts_tokens

            logger.info(
                "gemini_token_usage",
                model=model_name,
                prompt_tokens=prompt_tokens,
                candidates_tokens=output_tokens,
                thoughts_tokens=thoughts_tokens,
                total_tokens=total_tokens,
            )

            # Emit to UI log panel
            log_manager.emit_token_usage(
                provider="google",
                model=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=output_tokens,
                thoughts_tokens=thoughts_tokens,
                total_tokens=total_tokens,
            )

            # Record usage for cost tracking
            budget_manager.record_usage(
                provider="google",
                model=model_name,
                input_tokens=prompt_tokens,
                output_tokens=output_tokens,
                thoughts_tokens=thoughts_tokens,
                context_length=total_tokens,
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
            # Record estimated usage for interrupted streams
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
            # List models to check availability
            models = genai.list_models()
            return len(list(models)) > 0
        except Exception as e:
            logger.warning("google_unavailable", error=str(e))
            return False

    def _convert_messages(
        self, messages: list[ChatMessage]
    ) -> tuple[str, list[dict[str, Any]], Any]:
        """
        Convert ChatMessage objects to Google Gemini format.

        Gemini uses a different format:
        - System instruction is separate
        - History is a list of {"role": "user"|"model", "parts": [...]}
        - Last message is passed separately

        Args:
            messages: List of ChatMessage objects

        Returns:
            Tuple of (system_instruction, history, last_message_parts)
        """
        system_instruction = ""
        history = []
        last_message = None

        for i, msg in enumerate(messages):
            # Extract system instruction
            if msg.role == MessageRole.SYSTEM:
                if isinstance(msg.content, str):
                    system_instruction = msg.content
                continue

            # Convert role names
            role = "user" if msg.role == MessageRole.USER else "model"
            parts = self._convert_content_to_parts(msg.content)

            if i == len(messages) - 1:
                # Last message - will be sent as the current message
                last_message = parts
            else:
                history.append({
                    "role": role,
                    "parts": parts,
                })

        return system_instruction, history, last_message or ""

    def _convert_content_to_parts(self, content: Any) -> list[Any]:
        """
        Convert message content to Gemini parts format.

        Args:
            content: Message content (string or list of content parts)

        Returns:
            List of parts for Gemini API
        """
        if isinstance(content, str):
            return [content]

        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, TextContent):
                    parts.append(part.text)
                elif isinstance(part, ImageContent):
                    image_data = self._extract_image_data(part.image_url.url)
                    if image_data:
                        parts.append({
                            "inline_data": {
                                "mime_type": image_data["mime_type"],
                                "data": image_data["data"],
                            }
                        })
            return parts

        return [str(content) if content else ""]

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

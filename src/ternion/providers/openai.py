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
                try:
                    return await self._responses_chat_completion(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        **kwargs,
                    )
                except Exception:
                    prompt = self._messages_to_prompt(messages)
                    if prompt is None:
                        raise
                    completion_params: dict[str, Any] = {
                        "model": model,
                        "prompt": prompt,
                        "temperature": temperature,
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

        try:
            stream = await self._client.chat.completions.create(**api_params)  # type: ignore
            async for chunk in self._consume_chat_stream(stream, model=model):
                yield chunk
            return
        except Exception as e:
            if not self._is_non_chat_model_error(e):
                raise

        async for chunk in self._responses_chat_completion_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        ):
            yield chunk

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

    async def _responses_chat_completion(
        self,
        *,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int | None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """
        Generate a non-streaming completion using the OpenAI Responses API.

        This supports models that are not compatible with /v1/chat/completions (e.g. gpt-5, codex).
        """
        input_items = self._convert_messages_to_responses_input(messages)

        params: dict[str, Any] = {
            "model": model,
            "input": input_items,
            "temperature": temperature,
            **self._filter_responses_kwargs(kwargs),
        }
        if max_tokens is not None:
            params["max_output_tokens"] = max_tokens

        response = await self._client.responses.create(**params)  # type: ignore

        content = getattr(response, "output_text", "") or ""
        tool_calls = self._extract_tool_calls_from_responses(response)
        usage = getattr(response, "usage", None)
        usage_dict = self._usage_dict_from_responses_usage(usage)

        logger.info(
            "openai_token_usage",
            model=model,
            prompt_tokens=usage_dict.get("prompt_tokens", 0),
            completion_tokens=usage_dict.get("completion_tokens", 0),
            reasoning_tokens=usage_dict.get("reasoning_tokens", 0),
            total_tokens=usage_dict.get("total_tokens", 0),
        )

        log_manager.emit_token_usage(
            provider="openai",
            model=model,
            prompt_tokens=usage_dict.get("prompt_tokens", 0),
            completion_tokens=usage_dict.get("completion_tokens", 0),
            thoughts_tokens=usage_dict.get("reasoning_tokens", 0),
            total_tokens=usage_dict.get("total_tokens", 0),
        )

        return ProviderResponse(
            content=content,
            finish_reason="tool_calls" if tool_calls else "stop",
            tool_calls=tool_calls,
            usage=usage_dict,
            raw_response=response,
        )

    async def _responses_chat_completion_stream(
        self,
        *,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int | None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming completion using the OpenAI Responses API.

        Yields only `response.output_text.delta` events.
        """
        input_items = self._convert_messages_to_responses_input(messages)

        params: dict[str, Any] = {
            "model": model,
            "input": input_items,
            "temperature": temperature,
            "stream": True,
            **self._filter_responses_kwargs(kwargs),
        }
        if max_tokens is not None:
            params["max_output_tokens"] = max_tokens

        stream = await self._client.responses.create(**params)  # type: ignore

        received_text = ""
        usage_dict: dict[str, int] | None = None

        async for event in stream:
            etype = getattr(event, "type", None)
            if etype == "response.output_text.delta":
                delta = getattr(event, "delta", "") or ""
                if delta:
                    received_text += delta
                    yield delta
                continue

            if etype == "response.completed":
                response = getattr(event, "response", None)
                usage = getattr(response, "usage", None)
                usage_dict = self._usage_dict_from_responses_usage(usage)

        if usage_dict is not None:
            logger.info(
                "openai_token_usage",
                model=model,
                prompt_tokens=usage_dict.get("prompt_tokens", 0),
                completion_tokens=usage_dict.get("completion_tokens", 0),
                reasoning_tokens=usage_dict.get("reasoning_tokens", 0),
                total_tokens=usage_dict.get("total_tokens", 0),
            )

            log_manager.emit_token_usage(
                provider="openai",
                model=model,
                prompt_tokens=usage_dict.get("prompt_tokens", 0),
                completion_tokens=usage_dict.get("completion_tokens", 0),
                thoughts_tokens=usage_dict.get("reasoning_tokens", 0),
                total_tokens=usage_dict.get("total_tokens", 0),
            )

            from ternion.core.budget import budget_manager

            budget_manager.record_usage(
                provider="openai",
                model=model,
                input_tokens=usage_dict.get("prompt_tokens", 0),
                output_tokens=usage_dict.get("completion_tokens", 0),
                thoughts_tokens=usage_dict.get("reasoning_tokens", 0),
            )
            return

        if received_text:
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

            from ternion.core.budget import budget_manager

            budget_manager.record_usage(
                provider="openai",
                model=model,
                input_tokens=0,
                output_tokens=estimated_output,
                thoughts_tokens=0,
            )

    async def _consume_chat_stream(
        self,
        stream: Any,
        *,
        model: str,
    ) -> AsyncGenerator[str, None]:
        """Consume a chat.completions streaming response and yield text deltas."""
        received_text = ""
        usage_data = None

        async for chunk in stream:
            if hasattr(chunk, "usage") and chunk.usage:
                usage_data = chunk.usage

            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                received_text += content
                yield content

        if usage_data:
            prompt_tokens = usage_data.prompt_tokens or 0
            completion_tokens = usage_data.completion_tokens or 0
            total_tokens = usage_data.total_tokens or 0

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

            from ternion.core.budget import budget_manager

            budget_manager.record_usage(
                provider="openai",
                model=model,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                thoughts_tokens=reasoning_tokens,
            )
            return

        if received_text:
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

            from ternion.core.budget import budget_manager

            budget_manager.record_usage(
                provider="openai",
                model=model,
                input_tokens=0,
                output_tokens=estimated_output,
                thoughts_tokens=0,
            )

    @staticmethod
    def _filter_responses_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
        """
        Filter kwargs for OpenAI Responses API.

        This prevents leaking chat-completions-only params into /v1/responses calls.
        """
        allowed = {
            "tools",
            "tool_choice",
            "parallel_tool_calls",
            "max_tool_calls",
            "top_p",
            "user",
            "metadata",
            "truncation",
            "reasoning",
            "instructions",
            "text",
        }
        filtered: dict[str, Any] = {}
        for key, value in (kwargs or {}).items():
            if key in allowed:
                filtered[key] = value
        return filtered

    def _convert_messages_to_responses_input(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """
        Convert ChatMessage objects into OpenAI Responses API `input` items.
        """
        items: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == MessageRole.TOOL:
                tool_text = self._content_to_text(msg.content) or ""
                call_id = msg.tool_call_id or ""
                items.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": tool_text,
                })
                continue

            content: Any
            if isinstance(msg.content, str):
                content = msg.content
            elif isinstance(msg.content, list):
                parts: list[dict[str, Any]] = []
                for part in msg.content:
                    if isinstance(part, TextContent):
                        parts.append({"type": "input_text", "text": part.text})
                    elif isinstance(part, ImageContent):
                        parts.append({
                            "type": "input_image",
                            "image_url": part.image_url.url,
                            "detail": part.image_url.detail,
                        })
                    else:
                        parts.append({"type": "input_text", "text": str(part)})
                content = parts
            elif msg.content is None:
                content = ""
            else:
                content = str(msg.content)

            if msg.role != MessageRole.ASSISTANT or content != "" or not msg.tool_calls:
                items.append({"role": msg.role.value, "content": content})

            if msg.role == MessageRole.ASSISTANT and msg.tool_calls:
                for tc in msg.tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    function = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                    name = function.get("name")
                    arguments = function.get("arguments")
                    tc_call_id = tc.get("id")
                    if not isinstance(name, str) or not name.strip():
                        continue
                    if not isinstance(tc_call_id, str) or not tc_call_id.strip():
                        continue
                    if arguments is None:
                        arguments_str = "{}"
                    elif isinstance(arguments, str):
                        arguments_str = arguments
                    else:
                        import json

                        arguments_str = json.dumps(arguments, ensure_ascii=False)

                    items.append({
                        "type": "function_call",
                        "call_id": tc_call_id,
                        "id": tc_call_id,
                        "name": name,
                        "arguments": arguments_str,
                    })

        return items

    @staticmethod
    def _usage_dict_from_responses_usage(usage: Any) -> dict[str, int]:
        """Normalize Responses API usage into the ProviderResponse usage format."""
        if not usage:
            return {}
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", 0) or 0

        reasoning_tokens = 0
        details = getattr(usage, "output_tokens_details", None)
        if details is not None:
            reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0

        return {
            "prompt_tokens": int(input_tokens),
            "completion_tokens": int(output_tokens),
            "reasoning_tokens": int(reasoning_tokens),
            "total_tokens": int(total_tokens),
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
        }

    @staticmethod
    def _extract_tool_calls_from_responses(response: Any) -> list[dict[str, Any]] | None:
        """Extract tool calls from a Responses API response and convert to chat tool_calls format."""
        output = getattr(response, "output", None)
        if not isinstance(output, list):
            return None

        tool_calls: list[dict[str, Any]] = []
        for item in output:
            itype = getattr(item, "type", None)
            if itype != "function_call":
                continue

            name = getattr(item, "name", None)
            arguments = getattr(item, "arguments", None)
            call_id = getattr(item, "call_id", None) or getattr(item, "id", None)
            if not isinstance(name, str) or not name.strip():
                continue
            if not isinstance(call_id, str) or not call_id.strip():
                continue
            if not isinstance(arguments, str):
                arguments = "{}" if arguments is None else str(arguments)

            tool_calls.append({
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            })

        return tool_calls or None

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

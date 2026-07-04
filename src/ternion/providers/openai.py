"""
OpenAI provider adapter.

Implements chat completion using the OpenAI API with full multimodal support.
"""

import hashlib
import json
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from openai import AsyncOpenAI

from ternion.core.budget import budget_manager
from ternion.core.config import settings
from ternion.core.models import ChatMessage, ImageContent, MessageRole, TextContent
from ternion.providers.base import BaseProvider, ProviderResponse, clamp_max_output_tokens
from ternion.providers.resilience import (
    get_provider_semaphore,
    run_with_provider_resilience,
    run_with_retry,
)
from ternion.utils.log_manager import log_manager
from ternion.utils.token_estimator import estimate_tokens_from_text
from ternion.utils.tool_calls_parser import encode_stream_tool_calls

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
            timeout=float(settings.discussion.timeout_seconds or 600),
        )

    @property
    def name(self) -> str:
        return "openai"

    @property
    def default_model(self) -> str:
        return self._default_model

    @property
    def supports_native_tool_calls(self) -> bool:
        """Overrides base class default; OpenAI's /v1/chat/completions natively accepts `tools` and `tool_choice`."""
        return True

    @staticmethod
    def _is_json_body_parse_error(error: Exception) -> bool:
        """Return whether the error indicates the request JSON body could not be parsed."""
        status_code = getattr(error, "status_code", None)
        response = getattr(error, "response", None)
        if status_code is None and response is not None:
            status_code = getattr(response, "status_code", None)

        detail_parts = [str(error)]
        body = getattr(error, "body", None)
        if body is not None:
            if isinstance(body, (dict, list)):
                try:
                    detail_parts.append(json.dumps(body, ensure_ascii=False))
                except Exception:
                    detail_parts.append(str(body))
            else:
                detail_parts.append(str(body))

        combined = " ".join(part for part in detail_parts if part).lower()
        has_json_body_context = "json" in combined and "body" in combined
        has_parse_signal = any(
            marker in combined for marker in ("parse", "parsing", "parsed", "invalid", "malformed")
        )
        if has_json_body_context and has_parse_signal:
            return True

        return status_code in {400, 422} and has_json_body_context

    @staticmethod
    def _build_chat_payload_diagnostics(api_params: dict[str, Any]) -> dict[str, Any]:
        """Summarize chat payload shape without logging payload contents."""
        messages = api_params.get("messages")
        tools = api_params.get("tools")

        assistant_tool_call_messages = 0
        assistant_tool_call_total = 0
        assistant_internal_tool_call_total = 0
        assistant_write_tool_call_total = 0
        assistant_non_string_tool_call_arguments_total = 0
        assistant_non_dict_tool_call_function_total = 0
        assistant_max_tool_call_arguments_chars = 0
        tool_message_total = 0
        max_string_content_chars = 0
        non_string_content_serialize_error_total = 0
        tool_call_names_preview: list[str] = []

        if isinstance(messages, list):
            for msg in messages:
                if not isinstance(msg, dict):
                    continue

                role = msg.get("role")
                content = msg.get("content")
                if isinstance(content, str):
                    max_string_content_chars = max(max_string_content_chars, len(content))
                elif isinstance(content, list):
                    try:
                        content_chars = len(json.dumps(content, ensure_ascii=False))
                        max_string_content_chars = max(max_string_content_chars, content_chars)
                    except Exception:
                        non_string_content_serialize_error_total += 1

                if role == "tool":
                    tool_message_total += 1

                if role != "assistant":
                    continue

                tool_calls = msg.get("tool_calls")
                if not isinstance(tool_calls, list) or not tool_calls:
                    continue

                assistant_tool_call_messages += 1
                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict):
                        continue

                    assistant_tool_call_total += 1
                    if any(str(key).startswith("responses_api_") for key in tool_call):
                        assistant_internal_tool_call_total += 1

                    function = tool_call.get("function")
                    if not isinstance(function, dict):
                        assistant_non_dict_tool_call_function_total += 1
                        continue

                    name = function.get("name")
                    if isinstance(name, str) and name:
                        if len(tool_call_names_preview) < 5 and name not in tool_call_names_preview:
                            tool_call_names_preview.append(name)
                        if name.strip().lower() in {"write", "writefile"}:
                            assistant_write_tool_call_total += 1

                    arguments = function.get("arguments")
                    if isinstance(arguments, str):
                        assistant_max_tool_call_arguments_chars = max(
                            assistant_max_tool_call_arguments_chars,
                            len(arguments),
                        )
                    else:
                        assistant_non_string_tool_call_arguments_total += 1

        diagnostics: dict[str, Any] = {
            "payload_message_count": len(messages) if isinstance(messages, list) else 0,
            "payload_tools_count": len(tools) if isinstance(tools, list) else 0,
            "payload_tool_message_count": tool_message_total,
            "payload_assistant_tool_call_messages": assistant_tool_call_messages,
            "payload_assistant_tool_call_total": assistant_tool_call_total,
            "payload_assistant_internal_tool_call_total": assistant_internal_tool_call_total,
            "payload_assistant_write_tool_call_total": assistant_write_tool_call_total,
            "payload_assistant_non_string_tool_call_arguments_total": (
                assistant_non_string_tool_call_arguments_total
            ),
            "payload_assistant_non_dict_tool_call_function_total": (
                assistant_non_dict_tool_call_function_total
            ),
            "payload_assistant_max_tool_call_arguments_chars": (
                assistant_max_tool_call_arguments_chars
            ),
            "payload_max_string_content_chars": max_string_content_chars,
            "payload_non_string_content_serialize_error_total": (
                non_string_content_serialize_error_total
            ),
            "payload_tool_call_names_preview": ",".join(tool_call_names_preview),
            "payload_json_dump_ok": False,
            "payload_json_utf8_ok": False,
            "payload_chars": 0,
            "payload_sha256_16": "",
            "payload_json_dump_error": "",
            "payload_json_utf8_error": "",
        }

        try:
            payload_text = json.dumps(api_params, ensure_ascii=False)
            diagnostics["payload_json_dump_ok"] = True
            diagnostics["payload_chars"] = len(payload_text)
            try:
                payload_bytes = payload_text.encode("utf-8")
                diagnostics["payload_json_utf8_ok"] = True
                diagnostics["payload_sha256_16"] = hashlib.sha256(payload_bytes).hexdigest()[:16]
            except UnicodeEncodeError as exc:
                diagnostics["payload_json_utf8_error"] = f"{exc.reason}@{exc.start}"
        except Exception as exc:
            diagnostics["payload_json_dump_error"] = f"{type(exc).__name__}: {exc}"

        return diagnostics

    def _log_chat_payload_diagnostics(
        self,
        *,
        event_name: str,
        model: str,
        api_mode: str,
        error: Exception,
        api_params: dict[str, Any],
    ) -> None:
        """Emit payload diagnostics without masking the original provider exception."""
        try:
            diagnostics = self._build_chat_payload_diagnostics(api_params)
        except Exception as diagnostics_error:
            logger.error(
                "openai_chat_payload_diagnostics_failed",
                model=model,
                api_mode=api_mode,
                error=str(error),
                diagnostics_error=str(diagnostics_error),
            )
            return

        logger.error(
            event_name,
            model=model,
            api_mode=api_mode,
            error=str(error),
            **diagnostics,
        )

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
            model: Model to use (defaults to gpt-4-turbo)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            cache_prompt: Accepted for interface parity; OpenAI applies prompt
                caching automatically on stable prefixes
            **kwargs: Additional parameters

        Returns:
            ProviderResponse with the generated content
        """
        del cache_prompt  # OpenAI prefix caching is automatic; no request flag exists.
        model = model or self._default_model
        api_mode = kwargs.pop("api_mode", None)
        max_tokens = clamp_max_output_tokens(model, max_tokens)
        converted = self._convert_messages(messages)

        logger.debug(
            "openai_chat_completion",
            model=model,
            message_count=len(messages),
            api_mode=api_mode or "auto",
            max_tokens=max_tokens,
        )

        # Proactive routing: skip Chat Completions entirely for Responses API models.
        if api_mode == "responses":
            return await self._responses_chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )

        api_params: dict[str, Any] = {
            "model": model,
            "messages": converted,
            "stream": False,
            **kwargs,
        }
        if self._supports_temperature(model):
            api_params["temperature"] = temperature
        if max_tokens is not None:
            api_params[self._max_output_tokens_param(model)] = max_tokens
        try:
            response = await run_with_provider_resilience(
                self.name,
                lambda: self._client.chat.completions.create(**api_params),  # type: ignore
                operation_name="chat_completion",
            )
        except Exception as e:
            if self._is_json_body_parse_error(e):
                self._log_chat_payload_diagnostics(
                    event_name="openai_chat_completion_json_body_parse_error",
                    model=model,
                    api_mode=api_mode or "auto",
                    error=e,
                    api_params=api_params,
                )
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
                    completion = await run_with_provider_resilience(
                        self.name,
                        lambda: self._client.completions.create(**completion_params),  # type: ignore
                        operation_name="legacy_completion",
                    )
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

                    budget_manager.record_usage(
                        provider="openai",
                        model=model,
                        input_tokens=prompt_tokens,
                        output_tokens=completion_tokens,
                        thoughts_tokens=0,
                        context_length=total_tokens,
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
                        tool_calls.append(
                            {
                                "id": getattr(item, "id", ""),
                                "type": getattr(item, "type", ""),
                                "function": getattr(item, "function", None),
                            }
                        )

        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        # reasoning_tokens is a subset of completion_tokens; avoid double-counting in usage totals.
        reasoning_tokens = 0
        if (
            usage
            and hasattr(usage, "completion_tokens_details")
            and usage.completion_tokens_details
        ):
            reasoning_tokens = getattr(usage.completion_tokens_details, "reasoning_tokens", 0) or 0

        # cached_tokens is the prompt subset served from OpenAI's automatic prefix cache.
        cache_read_tokens = self._extract_cached_prompt_tokens(usage)

        logger.info(
            "openai_token_usage",
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning_tokens=reasoning_tokens,
            cache_read_tokens=cache_read_tokens,
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

        budget_manager.record_usage(
            provider="openai",
            model=model,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            thoughts_tokens=reasoning_tokens,
            context_length=total_tokens,
            cache_read_tokens=cache_read_tokens,
        )

        return ProviderResponse(
            content=(
                (choice.message.content if getattr(choice, "message", None) is not None else "")
                or ""
            ),
            finish_reason=choice.finish_reason,
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "reasoning_tokens": reasoning_tokens,
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
            cache_prompt: Accepted for interface parity; OpenAI applies prompt
                caching automatically on stable prefixes
            **kwargs: Additional parameters

        Yields:
            Content chunks as they are generated
        """
        del cache_prompt  # OpenAI prefix caching is automatic; no request flag exists.
        model = model or self._default_model
        api_mode = kwargs.pop("api_mode", None)
        max_tokens = clamp_max_output_tokens(model, max_tokens)
        converted = self._convert_messages(messages)

        logger.debug(
            "openai_chat_completion_stream",
            model=model,
            message_count=len(messages),
            api_mode=api_mode or "auto",
            max_tokens=max_tokens,
        )

        # Proactive routing: skip Chat Completions entirely for Responses API models.
        if api_mode == "responses":
            async for chunk in self._responses_chat_completion_stream(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            ):
                yield chunk
            return

        api_params: dict[str, Any] = {
            "model": model,
            "messages": converted,
            "stream": True,
            "stream_options": {"include_usage": True},
            **kwargs,
        }
        if self._supports_temperature(model):
            api_params["temperature"] = temperature
        if max_tokens is not None:
            api_params[self._max_output_tokens_param(model)] = max_tokens

        try:
            async with get_provider_semaphore(self.name):
                stream = await run_with_retry(
                    self.name,
                    lambda: self._client.chat.completions.create(**api_params),  # type: ignore
                    operation_name="chat_completion_stream",
                )
                async for chunk in self._consume_chat_stream(stream, model=model):
                    yield chunk
                return
        except Exception as e:
            if self._is_json_body_parse_error(e):
                self._log_chat_payload_diagnostics(
                    event_name="openai_chat_completion_stream_json_body_parse_error",
                    model=model,
                    api_mode=api_mode or "auto",
                    error=e,
                    api_params=api_params,
                )
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

            # OpenAI rejects tool-role messages without tool_call_id; always include it even if empty.
            if msg.role == MessageRole.TOOL:
                out["content"] = self._content_to_text(msg.content) or ""
                if msg.tool_call_id:
                    out["tool_call_id"] = msg.tool_call_id
                result.append(out)
                continue

            if isinstance(msg.content, str):
                out["content"] = msg.content
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
                        content_parts.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": part.image_url.url,
                                    "detail": part.image_url.detail,
                                },
                            }
                        )
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

        Args:
            messages: List of chat messages
            model: Model ID to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            ProviderResponse with the generated content
        """
        input_items, previous_response_id = self._prepare_responses_input(messages)

        params = self._build_responses_request_params(
            model=model,
            input_items=input_items,
            temperature=temperature,
            max_tokens=max_tokens,
            kwargs=kwargs,
            previous_response_id=previous_response_id,
        )

        response = await run_with_provider_resilience(
            self.name,
            lambda: self._client.responses.create(**params),  # type: ignore
            operation_name="responses_completion",
        )

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
            cache_read_tokens=usage_dict.get("cache_read_tokens", 0),
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

        if usage_dict:
            budget_manager.record_usage(
                provider="openai",
                model=model,
                input_tokens=usage_dict.get("prompt_tokens", 0),
                output_tokens=usage_dict.get("completion_tokens", 0),
                thoughts_tokens=usage_dict.get("reasoning_tokens", 0),
                context_length=usage_dict.get("total_tokens", 0),
                cache_read_tokens=usage_dict.get("cache_read_tokens", 0),
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

        Args:
            messages: List of chat messages
            model: Model ID to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Yields:
            Content chunks as they are generated
        """
        input_items, previous_response_id = self._prepare_responses_input(messages)

        params = self._build_responses_request_params(
            model=model,
            input_items=input_items,
            temperature=temperature,
            max_tokens=max_tokens,
            kwargs=kwargs,
            stream=True,
            previous_response_id=previous_response_id,
        )

        async with get_provider_semaphore(self.name):
            stream = await run_with_retry(
                self.name,
                lambda: self._client.responses.create(**params),  # type: ignore
                operation_name="responses_stream",
            )

            received_text = ""
            usage_dict: dict[str, int] | None = None
            final_response: Any = None

            async for event in stream:
                etype = getattr(event, "type", None)
                if etype == "response.output_text.delta":
                    delta = getattr(event, "delta", "") or ""
                    if delta:
                        received_text += delta
                        yield delta
                    continue

                if etype == "response.completed":
                    final_response = getattr(event, "response", None)
                    usage = (
                        getattr(final_response, "usage", None)
                        if final_response is not None
                        else None
                    )
                    usage_dict = self._usage_dict_from_responses_usage(usage)

        if usage_dict is not None:
            logger.info(
                "openai_token_usage",
                model=model,
                prompt_tokens=usage_dict.get("prompt_tokens", 0),
                completion_tokens=usage_dict.get("completion_tokens", 0),
                reasoning_tokens=usage_dict.get("reasoning_tokens", 0),
                cache_read_tokens=usage_dict.get("cache_read_tokens", 0),
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

            budget_manager.record_usage(
                provider="openai",
                model=model,
                input_tokens=usage_dict.get("prompt_tokens", 0),
                output_tokens=usage_dict.get("completion_tokens", 0),
                thoughts_tokens=usage_dict.get("reasoning_tokens", 0),
                cache_read_tokens=usage_dict.get("cache_read_tokens", 0),
            )
        elif received_text:
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

            budget_manager.record_usage(
                provider="openai",
                model=model,
                input_tokens=0,
                output_tokens=estimated_output,
                thoughts_tokens=0,
            )

        tool_calls = (
            self._extract_tool_calls_from_responses(final_response)
            if final_response is not None
            else None
        )
        if tool_calls:
            yield encode_stream_tool_calls(tool_calls)

    async def _consume_chat_stream(
        self,
        stream: Any,
        *,
        model: str,
    ) -> AsyncGenerator[str, None]:
        """
        Drain a streaming chat.completions response, aggregating tool call deltas and reporting usage.

        Tool call chunks are accumulated by index and emitted as a single encoded payload after the
        stream ends. Text content is suppressed once any tool_calls delta is observed.

        Args:
            stream: Async streaming response from openai.chat.completions.create.
            model: Model name for token usage logging and budget recording.

        Yields:
            Text delta strings, followed by an encoded tool call payload if tool calls were present.
        """
        received_text = ""
        usage_data = None
        tool_calls_by_index: dict[int, dict[str, Any]] = {}
        saw_tool_calls = False
        suppress_text = False

        async for chunk in stream:
            if hasattr(chunk, "usage") and chunk.usage:
                usage_data = chunk.usage

            if not getattr(chunk, "choices", None):
                continue
            choice0 = chunk.choices[0]
            delta = getattr(choice0, "delta", None)
            if delta is None:
                continue

            delta_tool_calls = getattr(delta, "tool_calls", None)
            if delta_tool_calls:
                saw_tool_calls = True
                suppress_text = True

                for item in delta_tool_calls:
                    idx = getattr(item, "index", None)
                    if idx is None and isinstance(item, dict):
                        idx = item.get("index")
                    if not isinstance(idx, int):
                        idx = 0

                    call = tool_calls_by_index.get(idx)
                    if call is None:
                        call = {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                        tool_calls_by_index[idx] = call

                    tc_id = getattr(item, "id", None)
                    if tc_id is None and isinstance(item, dict):
                        tc_id = item.get("id")
                    if isinstance(tc_id, str) and tc_id:
                        call["id"] = tc_id

                    tc_type = getattr(item, "type", None)
                    if tc_type is None and isinstance(item, dict):
                        tc_type = item.get("type")
                    if isinstance(tc_type, str) and tc_type:
                        call["type"] = tc_type

                    func = getattr(item, "function", None)
                    if func is None and isinstance(item, dict):
                        func = item.get("function")
                    if func:
                        name = getattr(func, "name", None)
                        if name is None and isinstance(func, dict):
                            name = func.get("name")
                        if isinstance(name, str) and name:
                            call["function"]["name"] = name

                        args = getattr(func, "arguments", None)
                        if args is None and isinstance(func, dict):
                            args = func.get("arguments")
                        if isinstance(args, str) and args:
                            call["function"]["arguments"] = call["function"]["arguments"] + args

                continue

            content = getattr(delta, "content", None)
            if content and not suppress_text:
                received_text += content
                yield content

        if usage_data:
            prompt_tokens = usage_data.prompt_tokens or 0
            completion_tokens = usage_data.completion_tokens or 0
            total_tokens = usage_data.total_tokens or 0

            reasoning_tokens = 0
            if (
                hasattr(usage_data, "completion_tokens_details")
                and usage_data.completion_tokens_details
            ):
                reasoning_tokens = (
                    getattr(usage_data.completion_tokens_details, "reasoning_tokens", 0) or 0
                )

            cache_read_tokens = self._extract_cached_prompt_tokens(usage_data)

            logger.info(
                "openai_token_usage",
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                reasoning_tokens=reasoning_tokens,
                cache_read_tokens=cache_read_tokens,
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

            budget_manager.record_usage(
                provider="openai",
                model=model,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                thoughts_tokens=reasoning_tokens,
                cache_read_tokens=cache_read_tokens,
            )
        if saw_tool_calls and tool_calls_by_index:
            ordered = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index.keys())]
            yield encode_stream_tool_calls(ordered)
            return

        if usage_data is None and received_text:
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

            budget_manager.record_usage(
                provider="openai",
                model=model,
                input_tokens=0,
                output_tokens=estimated_output,
                thoughts_tokens=0,
            )

    @staticmethod
    def _convert_tools_for_responses_api(tools: list[Any]) -> list[dict[str, Any]]:
        """
        Convert Chat Completions tool schemas to Responses API format.

        Chat Completions format nests name/parameters inside a ``function`` key::

            {"type": "function", "function": {"name": "read", "parameters": {...}}}

        The Responses API requires ``name`` and ``parameters`` at the top level::

            {"type": "function", "name": "read", "parameters": {...}}

        Tools already in Responses format (top-level ``name``) are passed through unchanged.

        Args:
            tools: List of tool definitions in either format.

        Returns:
            List of tool definitions in Responses API format.
        """
        converted: list[dict[str, Any]] = []
        for tool in tools or []:
            if not isinstance(tool, dict):
                continue

            # Already in Responses API format (has top-level name).
            if isinstance(tool.get("name"), str) and tool["name"].strip():
                converted.append(tool)
                continue

            # Chat Completions format: extract from nested function key.
            fn = tool.get("function")
            if not isinstance(fn, dict):
                continue
            name = fn.get("name")
            if not isinstance(name, str) or not name.strip():
                continue

            resp_tool: dict[str, Any] = {
                "type": "function",
                "name": name,
            }
            if "description" in fn:
                resp_tool["description"] = fn["description"]
            if "parameters" in fn:
                resp_tool["parameters"] = fn["parameters"]
            if "strict" in fn:
                resp_tool["strict"] = fn["strict"]
            converted.append(resp_tool)
        return converted

    @staticmethod
    def _filter_responses_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
        """
        Strip kwargs unsupported by the OpenAI Responses API (/v1/responses) before forwarding.

        Also converts ``tools`` from Chat Completions schema to Responses API schema
        when a nested ``function`` key is detected (see ``_convert_tools_for_responses_api``).

        Args:
            kwargs: Raw kwargs passed to chat_completion methods.

        Returns:
            Filtered dict containing only Responses API-compatible keys.
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

        # Convert tools from Chat Completions format to Responses API format.
        if "tools" in filtered and isinstance(filtered["tools"], list):
            filtered["tools"] = OpenAIProvider._convert_tools_for_responses_api(filtered["tools"])

        return filtered

    @staticmethod
    def _normalize_model_name(model: str) -> str:
        """Normalize a model ID for capability checks."""
        return str(model or "").strip().lower()

    @classmethod
    def _supports_temperature(cls, model: str) -> bool:
        """Return whether the target model accepts the temperature parameter."""
        normalized = cls._normalize_model_name(model)
        return not normalized.startswith("gpt-5")

    @classmethod
    def _max_output_tokens_param(cls, model: str) -> str:
        """
        Return the Chat Completions parameter name for the output token budget.

        Reasoning models (gpt-5 family) reject the legacy max_tokens parameter
        and require max_completion_tokens instead.
        """
        normalized = cls._normalize_model_name(model)
        if normalized.startswith("gpt-5"):
            return "max_completion_tokens"
        return "max_tokens"

    @staticmethod
    def _extract_cached_prompt_tokens(usage: Any) -> int:
        """
        Extract the cached prompt token count from a Chat Completions usage object.

        Args:
            usage: Usage object from a chat.completions response or stream chunk.

        Returns:
            Number of prompt tokens served from the automatic prefix cache.
        """
        details = getattr(usage, "prompt_tokens_details", None)
        if details is None:
            return 0
        cached = getattr(details, "cached_tokens", 0) or 0
        return int(cached)

    @classmethod
    def _build_responses_request_params(
        cls,
        *,
        model: str,
        input_items: list[dict[str, Any]],
        temperature: float,
        max_tokens: int | None,
        kwargs: dict[str, Any],
        stream: bool = False,
        previous_response_id: str | None = None,
    ) -> dict[str, Any]:
        """Build a sanitized Responses API request payload."""
        params: dict[str, Any] = {
            "model": model,
            "input": input_items,
            **cls._filter_responses_kwargs(kwargs),
        }
        if stream:
            params["stream"] = True
        if isinstance(previous_response_id, str) and previous_response_id.strip():
            params["previous_response_id"] = previous_response_id.strip()
        if cls._supports_temperature(model):
            params["temperature"] = temperature
        if max_tokens is not None:
            params["max_output_tokens"] = max_tokens
        return params

    def _prepare_responses_input(
        self,
        messages: list[ChatMessage],
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Prepare Responses API input items, preferring `previous_response_id` tool follow-ups.

        Returns:
            Tuple of `(input_items, previous_response_id)`.
        """
        followup = self._build_responses_tool_followup_input(messages)
        if followup is not None:
            input_items, previous_response_id = followup
            logger.info(
                "openai_responses_followup_resume",
                previous_response_id=previous_response_id,
                message_count=len(messages),
                input_item_count=len(input_items),
            )
            return input_items, previous_response_id

        if self._has_responses_tool_followup_without_response_id(messages):
            logger.warning(
                "openai_responses_followup_missing_response_id",
                message_count=len(messages),
            )

        return self._convert_messages_to_responses_input(messages), None

    def _build_responses_tool_followup_input(
        self,
        messages: list[ChatMessage],
    ) -> tuple[list[dict[str, Any]], str] | None:
        """
        Build follow-up input using `previous_response_id` after a Responses API tool turn.

        This avoids replaying reasoning items manually for GPT-5 reasoning models.
        """
        for idx in range(len(messages) - 1, -1, -1):
            msg = messages[idx]
            if msg.role != MessageRole.ASSISTANT or not msg.tool_calls:
                continue

            response_ids = {
                tc.get("responses_api_response_id")
                for tc in msg.tool_calls
                if isinstance(tc, dict)
                and isinstance(tc.get("responses_api_response_id"), str)
                and tc.get("responses_api_response_id", "").strip()
            }
            if len(response_ids) != 1:
                continue

            suffix = messages[idx + 1 :]
            if not suffix or any(item.role != MessageRole.TOOL for item in suffix):
                continue

            tool_call_map: dict[str, str] = {}
            for tc in msg.tool_calls:
                if not isinstance(tc, dict):
                    continue
                internal_id = tc.get("id")
                if not isinstance(internal_id, str) or not internal_id.strip():
                    continue
                _item_id, call_id = self._extract_responses_api_ids(tc)
                if isinstance(call_id, str) and call_id.strip():
                    tool_call_map[internal_id] = call_id

            input_items: list[dict[str, Any]] = []
            for tool_msg in suffix:
                raw_tool_call_id = tool_msg.tool_call_id or ""
                call_id = tool_call_map.get(raw_tool_call_id, raw_tool_call_id)
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": self._content_to_text(tool_msg.content) or "",
                    }
                )

            if input_items:
                return input_items, next(iter(response_ids))

        return None

    def _has_responses_tool_followup_without_response_id(
        self,
        messages: list[ChatMessage],
    ) -> bool:
        """Return whether a tool follow-up exists but lacks preserved response metadata."""
        for idx in range(len(messages) - 1, -1, -1):
            msg = messages[idx]
            if msg.role != MessageRole.ASSISTANT or not msg.tool_calls:
                continue
            suffix = messages[idx + 1 :]
            if not suffix or any(item.role != MessageRole.TOOL for item in suffix):
                continue
            return True
        return False

    def _convert_messages_to_responses_input(
        self, messages: list[ChatMessage]
    ) -> list[dict[str, Any]]:
        """
        Convert ChatMessage objects into OpenAI Responses API `input` items.

        Tool-role messages are mapped to `function_call_output` items; assistant tool_calls
        are expanded into separate `function_call` items per the Responses API schema.
        When follow-up history was rewritten for Cursor routing, preserved
        ``responses_api_call_id`` and ``responses_api_item_id`` metadata is used
        to restore the original OpenAI identifiers.

        Args:
            messages: Conversation history including any tool interaction turns.

        Returns:
            List of input items compatible with /v1/responses `input` parameter.
        """
        items: list[dict[str, Any]] = []
        responses_call_ids_by_tool_id: dict[str, str] = {}
        for msg in messages:
            if msg.role == MessageRole.TOOL:
                tool_text = self._content_to_text(msg.content) or ""
                raw_tool_call_id = msg.tool_call_id or ""
                call_id = responses_call_ids_by_tool_id.get(raw_tool_call_id, raw_tool_call_id)
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": tool_text,
                    }
                )
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
                        parts.append(
                            {
                                "type": "input_image",
                                "image_url": part.image_url.url,
                                "detail": part.image_url.detail,
                            }
                        )
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
                    tc_internal_id = tc.get("id")
                    responses_item_id, responses_call_id = self._extract_responses_api_ids(tc)
                    if not isinstance(name, str) or not name.strip():
                        continue
                    if not isinstance(tc_internal_id, str) or not tc_internal_id.strip():
                        continue
                    tc_call_id = responses_call_id or tc_internal_id
                    responses_call_ids_by_tool_id[tc_internal_id] = tc_call_id
                    if arguments is None:
                        arguments_str = "{}"
                    elif isinstance(arguments, str):
                        arguments_str = arguments
                    else:
                        import json

                        arguments_str = json.dumps(arguments, ensure_ascii=False)

                    item: dict[str, Any] = {
                        "type": "function_call",
                        "call_id": tc_call_id,
                        "name": name,
                        "arguments": arguments_str,
                    }
                    if responses_item_id is not None:
                        item["id"] = responses_item_id
                    items.append(item)

        return items

    @staticmethod
    def _extract_responses_api_ids(tool_call: dict[str, Any]) -> tuple[str | None, str | None]:
        """
        Extract preserved Responses API identifiers from a tool call dictionary.

        Args:
            tool_call: Tool call payload stored in conversation history.

        Returns:
            Tuple of ``(responses_item_id, responses_call_id)``.
        """
        raw_id = tool_call.get("id")
        item_id = tool_call.get("responses_api_item_id")
        call_id = tool_call.get("responses_api_call_id") or tool_call.get("call_id")

        if not isinstance(item_id, str) or not item_id.strip():
            item_id = raw_id if isinstance(raw_id, str) and raw_id.startswith("fc_") else None
        if not isinstance(call_id, str) or not call_id.strip():
            call_id = raw_id if isinstance(raw_id, str) and raw_id.startswith("call_") else None

        normalized_item_id = (
            item_id.strip() if isinstance(item_id, str) and item_id.strip() else None
        )
        normalized_call_id = (
            call_id.strip() if isinstance(call_id, str) and call_id.strip() else None
        )
        return normalized_item_id, normalized_call_id

    @staticmethod
    def _usage_dict_from_responses_usage(usage: Any) -> dict[str, int]:
        """
        Normalize Responses API usage object into the ProviderResponse usage dict format.

        Args:
            usage: Usage object from /v1/responses response, or None.

        Returns:
            Dict with keys: prompt_tokens, completion_tokens, reasoning_tokens,
            cache_read_tokens, total_tokens, input_tokens, output_tokens.
            Empty dict if usage is None.
        """
        if not usage:
            return {}
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", 0) or 0

        reasoning_tokens = 0
        details = getattr(usage, "output_tokens_details", None)
        if details is not None:
            reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0

        cache_read_tokens = 0
        input_details = getattr(usage, "input_tokens_details", None)
        if input_details is not None:
            cache_read_tokens = getattr(input_details, "cached_tokens", 0) or 0

        return {
            "prompt_tokens": int(input_tokens),
            "completion_tokens": int(output_tokens),
            "reasoning_tokens": int(reasoning_tokens),
            "cache_read_tokens": int(cache_read_tokens),
            "total_tokens": int(total_tokens),
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
        }

    @staticmethod
    def _extract_tool_calls_from_responses(response: Any) -> list[dict[str, Any]] | None:
        """
        Extract function_call items from a Responses API response output list.

        Converts Responses API `function_call` output items to the OpenAI chat/completions
        `tool_calls` schema for downstream compatibility.

        Args:
            response: Completed response object from /v1/responses.

        Returns:
            List of tool call dicts in chat/completions format, or None if no function calls present.
        """
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
            response_item_id = getattr(item, "id", None)
            response_call_id = getattr(item, "call_id", None)
            response_id = getattr(response, "id", None)
            call_id = response_call_id or response_item_id
            if not isinstance(name, str) or not name.strip():
                continue
            if not isinstance(call_id, str) or not call_id.strip():
                continue
            if not isinstance(arguments, str):
                arguments = "{}" if arguments is None else str(arguments)

            tool_call: dict[str, Any] = {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
            if isinstance(response_item_id, str) and response_item_id.strip():
                tool_call["responses_api_item_id"] = response_item_id
            if isinstance(response_call_id, str) and response_call_id.strip():
                tool_call["responses_api_call_id"] = response_call_id
            if isinstance(response_id, str) and response_id.strip():
                tool_call["responses_api_response_id"] = response_id
            tool_calls.append(tool_call)

        return tool_calls or None

    @staticmethod
    def _is_non_chat_model_error(error: Exception) -> bool:
        """
        Detect errors indicating model incompatibility with /v1/chat/completions.

        Conservative by design: triggers the Responses API fallback only on explicit
        endpoint-mismatch errors, not on general API failures.

        Args:
            error: Exception raised by the chat completions client.

        Returns:
            True if the error signals a non-chat model routing failure.
        """
        msg = str(error).lower()
        return ("not a chat model" in msg) and ("v1/chat/completions" in msg)

    def _messages_to_prompt(self, messages: list[ChatMessage]) -> str | None:
        """
        Convert chat messages into a single prompt string for /v1/completions fallback.

        Args:
            messages: Conversation history to format.

        Returns:
            Formatted prompt string, or None if any message contains image content
            which is incompatible with the /v1/completions endpoint.
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
        """
        Convert message content to plain text on a best-effort basis.

        Args:
            content: Message content; may be str, list of content parts, or None.

        Returns:
            Plain text string, or None if the content contains image parts that cannot
            be represented as text (signals to caller that fallback is not possible).
        """
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

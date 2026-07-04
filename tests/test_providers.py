"""
Tests for provider adapters.
"""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from ternion.core.models import ChatMessage, MessageRole
from ternion.providers.base import BaseProvider, ProviderResponse


class TestProviderResponse:
    """Tests for ProviderResponse dataclass."""

    def test_empty_response(self) -> None:
        """Test empty response properties."""
        response = ProviderResponse()
        assert response.content == ""
        assert response.finish_reason is None
        assert not response.is_complete

    def test_complete_response(self) -> None:
        """Test complete response."""
        response = ProviderResponse(
            content="Hello, world!",
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )
        assert response.content == "Hello, world!"
        assert response.is_complete
        assert response.usage["total_tokens"] == 15


class TestBaseProvider:
    """Tests for BaseProvider abstract class."""

    def test_convert_messages_string_content(self) -> None:
        """Test message conversion with string content."""

        # Create a concrete implementation for testing
        class TestProvider(BaseProvider):
            @property
            def name(self) -> str:
                return "test"

            @property
            def default_model(self) -> str:
                return "test-model"

            async def chat_completion(
                self,
                *args: object,
                **kwargs: object,
            ) -> ProviderResponse:
                raise AssertionError("chat_completion not used in this test")

            async def chat_completion_stream(
                self,
                messages: list[ChatMessage],
                model: str | None = None,
                temperature: float = 0.0,
                max_tokens: int | None = None,
                **kwargs: Any,
            ) -> AsyncGenerator[str, None]:
                yield "test"

            async def is_available(self) -> bool:
                return True

        provider = TestProvider(api_key="test-key")
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content="You are helpful."),
            ChatMessage(role=MessageRole.USER, content="Hello"),
        ]

        converted = provider._convert_messages(messages)

        assert len(converted) == 2
        assert converted[0]["role"] == "system"
        assert converted[0]["content"] == "You are helpful."
        assert converted[1]["role"] == "user"
        assert converted[1]["content"] == "Hello"


class TestProviderManager:
    """Tests for ProviderManager."""

    def test_get_provider_not_configured(self) -> None:
        """Test getting a provider that is not configured."""
        from ternion.providers.manager import ProviderManager

        # Create manager with mocked config_store (no API keys)
        # Use only config_store (settings fallback is not supported)
        with patch("ternion.providers.manager.config_store") as mock_config_store:
            # Mock config_store: no API keys
            mock_config_store.get_provider_api_key.return_value = None

            manager = ProviderManager()
            assert manager.get_provider("openai") is None
            assert not manager.has_providers

    def test_available_providers_list(self) -> None:
        """Test listing available providers."""
        from ternion.providers.manager import provider_manager

        # The list depends on environment configuration
        providers = provider_manager.available_providers
        assert isinstance(providers, list)


class TestOpenAIProviderFallback:
    """Tests for OpenAI provider fallbacks."""

    def test_non_chat_model_error_detection(self) -> None:
        """Trigger fallback only for explicit chat endpoint mismatch errors."""
        from ternion.providers.openai import OpenAIProvider

        err = RuntimeError(
            "Error code: 404 - {'error': {'message': 'This is not a chat model and thus not supported in the v1/chat/completions endpoint. Did you mean to use v1/completions?'}}"
        )
        assert OpenAIProvider._is_non_chat_model_error(err) is True

        other = RuntimeError("Error code: 404 - {'error': {'message': 'Model not found'}}")
        assert OpenAIProvider._is_non_chat_model_error(other) is False


class TestOpenAIJsonBodyDiagnostics:
    """Tests for OpenAI JSON body parse diagnostics."""

    def test_json_body_parse_error_detection_handles_message_variants(self) -> None:
        """JSON-body parse detection should tolerate status-code and message variations."""
        from ternion.providers.openai import OpenAIProvider

        class MockOpenAIError(RuntimeError):
            """Minimal error object with OpenAI-like attributes."""

            def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
                super().__init__(message)
                self.status_code = status_code
                self.body = body

        assert OpenAIProvider._is_json_body_parse_error(
            MockOpenAIError(
                "Failed to parse JSON body",
                status_code=400,
                body={"error": {"message": "Malformed JSON body"}},
            )
        )
        assert OpenAIProvider._is_json_body_parse_error(
            MockOpenAIError("Could not parse the JSON body for this request")
        )
        assert not OpenAIProvider._is_json_body_parse_error(
            MockOpenAIError("Model not found", status_code=404)
        )

    def test_build_chat_payload_diagnostics_summarizes_structure_without_content(self) -> None:
        """Diagnostics should capture structural counts and serialization failures safely."""
        from ternion.providers.openai import OpenAIProvider

        diagnostics = OpenAIProvider._build_chat_payload_diagnostics(
            {
                "messages": [
                    {"role": "tool", "content": "RESULT_A"},
                    {
                        "role": "assistant",
                        "content": [object()],
                        "tool_calls": [
                            {
                                "id": "call_write",
                                "type": "function",
                                "responses_api_call_id": "resp_call",
                                "function": {
                                    "name": "Write",
                                    "arguments": '{"file_path":"docs/a.md","content":"x"}',
                                },
                            },
                            {
                                "id": "call_bad_args",
                                "type": "function",
                                "function": {"name": "Edit", "arguments": {"path": "docs/a.md"}},
                            },
                            {
                                "id": "call_bad_function",
                                "type": "function",
                                "function": "not-a-dict",
                            },
                        ],
                    },
                ],
                "tools": [{"type": "function"}, {"type": "function"}],
            }
        )

        assert diagnostics["payload_message_count"] == 2
        assert diagnostics["payload_tools_count"] == 2
        assert diagnostics["payload_tool_message_count"] == 1
        assert diagnostics["payload_assistant_tool_call_messages"] == 1
        assert diagnostics["payload_assistant_tool_call_total"] == 3
        assert diagnostics["payload_assistant_internal_tool_call_total"] == 1
        assert diagnostics["payload_assistant_write_tool_call_total"] == 1
        assert diagnostics["payload_assistant_non_string_tool_call_arguments_total"] == 1
        assert diagnostics["payload_assistant_non_dict_tool_call_function_total"] == 1
        assert diagnostics["payload_non_string_content_serialize_error_total"] == 1
        assert diagnostics["payload_tool_call_names_preview"] == "Write,Edit"

    @pytest.mark.asyncio
    async def test_chat_completion_preserves_original_error_when_diagnostics_fail(self) -> None:
        """Diagnostics failures should not mask the original chat-completions exception."""
        from ternion.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        original_error = RuntimeError("Failed to parse JSON body")

        with (
            patch.object(
                provider._client.chat.completions,
                "create",
                AsyncMock(side_effect=original_error),
            ),
            patch.object(
                provider,
                "_build_chat_payload_diagnostics",
                side_effect=RuntimeError("diagnostics failed"),
            ),
            patch("ternion.providers.openai.logger.error") as mock_logger_error,
            pytest.raises(RuntimeError) as exc_info,
        ):
            await provider.chat_completion(
                messages=[ChatMessage(role=MessageRole.USER, content="Hello")],
                model="gpt-4.1",
            )

        assert exc_info.value is original_error
        assert (
            mock_logger_error.call_args_list[0].args[0] == "openai_chat_payload_diagnostics_failed"
        )

    @pytest.mark.asyncio
    async def test_chat_completion_stream_preserves_original_error_when_diagnostics_fail(
        self,
    ) -> None:
        """Diagnostics failures should not mask the original streaming exception."""
        from ternion.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        original_error = RuntimeError("Failed to parse JSON body")

        with (
            patch.object(
                provider._client.chat.completions,
                "create",
                AsyncMock(side_effect=original_error),
            ),
            patch.object(
                provider,
                "_build_chat_payload_diagnostics",
                side_effect=RuntimeError("diagnostics failed"),
            ),
            patch("ternion.providers.openai.logger.error") as mock_logger_error,
            pytest.raises(RuntimeError) as exc_info,
        ):
            async for _ in provider.chat_completion_stream(
                messages=[ChatMessage(role=MessageRole.USER, content="Hello")],
                model="gpt-4.1",
            ):
                pass

        assert exc_info.value is original_error
        assert (
            mock_logger_error.call_args_list[0].args[0] == "openai_chat_payload_diagnostics_failed"
        )


class TestConvertToolsForResponsesApi:
    """Tests for Chat Completions → Responses API tool schema conversion."""

    def test_converts_chat_completions_format(self) -> None:
        """Nested function key should be flattened to top-level name/parameters."""
        from ternion.providers.openai import OpenAIProvider

        chat_tools = [
            {
                "type": "function",
                "function": {
                    "name": "Read",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                },
            }
        ]
        converted = OpenAIProvider._convert_tools_for_responses_api(chat_tools)
        assert len(converted) == 1
        assert converted[0]["name"] == "Read"
        assert converted[0]["description"] == "Read a file"
        assert "parameters" in converted[0]
        assert "function" not in converted[0]

    def test_passthrough_responses_format(self) -> None:
        """Tools already in Responses format should pass through unchanged."""
        from ternion.providers.openai import OpenAIProvider

        resp_tools = [
            {
                "type": "function",
                "name": "Grep",
                "description": "Search files",
                "parameters": {"type": "object"},
            }
        ]
        converted = OpenAIProvider._convert_tools_for_responses_api(resp_tools)
        assert len(converted) == 1
        assert converted[0]["name"] == "Grep"

    def test_skips_invalid_tools(self) -> None:
        """Non-dict entries and tools without name/function should be skipped."""
        from ternion.providers.openai import OpenAIProvider

        bad_tools = [
            "not a dict",
            {"type": "function"},  # no function or name
            {"type": "function", "function": {}},  # function without name
            {"type": "function", "function": {"name": ""}},  # empty name
        ]
        converted = OpenAIProvider._convert_tools_for_responses_api(bad_tools)
        assert converted == []

    def test_empty_list(self) -> None:
        """Empty or None input should return an empty list."""
        from ternion.providers.openai import OpenAIProvider

        assert OpenAIProvider._convert_tools_for_responses_api([]) == []
        assert OpenAIProvider._convert_tools_for_responses_api(None) == []  # type: ignore[arg-type]


class TestResolveApiMode:
    """Tests for _resolve_api_mode helper in workflow nodes."""

    def test_returns_responses_for_openai_responses_model(self) -> None:
        """OpenAI model with mode='responses' in catalog should return 'responses'."""
        from unittest.mock import MagicMock

        from ternion.workflow.nodes import _resolve_api_mode

        provider = MagicMock()
        provider.name = "openai"

        catalog_model = MagicMock()
        catalog_model.mode = "responses"

        with patch("ternion.workflow.nodes.model_catalog_service") as mock_catalog:
            mock_catalog.get_model_cached.return_value = catalog_model
            result = _resolve_api_mode(provider, "gpt-5-pro")

        assert result == "responses"

    def test_returns_none_for_openai_chat_model(self) -> None:
        """OpenAI model with mode='chat' should return None (use default routing)."""
        from unittest.mock import MagicMock

        from ternion.workflow.nodes import _resolve_api_mode

        provider = MagicMock()
        provider.name = "openai"

        catalog_model = MagicMock()
        catalog_model.mode = "chat"

        with patch("ternion.workflow.nodes.model_catalog_service") as mock_catalog:
            mock_catalog.get_model_cached.return_value = catalog_model
            result = _resolve_api_mode(provider, "gpt-5")

        assert result is None

    def test_returns_none_for_non_openai_provider(self) -> None:
        """Non-OpenAI providers should always return None."""
        from unittest.mock import MagicMock

        from ternion.workflow.nodes import _resolve_api_mode

        provider = MagicMock()
        provider.name = "anthropic"
        result = _resolve_api_mode(provider, "claude-sonnet-4-5")
        assert result is None

    def test_returns_none_when_model_not_in_catalog(self) -> None:
        """Unknown model should return None (fall back to default routing)."""
        from unittest.mock import MagicMock

        from ternion.workflow.nodes import _resolve_api_mode

        provider = MagicMock()
        provider.name = "openai"

        with patch("ternion.workflow.nodes.model_catalog_service") as mock_catalog:
            mock_catalog.get_model_cached.return_value = None
            result = _resolve_api_mode(provider, "unknown-model")

        assert result is None


class TestOpenAIResponsesCompatibility:
    """Tests for Responses API compatibility fallbacks."""

    def test_extract_tool_calls_from_responses_preserves_response_ids(self) -> None:
        """Responses tool-call extraction should keep original item/call/response identifiers."""
        from ternion.providers.openai import OpenAIProvider

        response = type(
            "MockResponse",
            (),
            {
                "id": "resp_123",
                "output": [
                    type(
                        "FunctionCallItem",
                        (),
                        {
                            "type": "function_call",
                            "id": "fc_123",
                            "call_id": "call_123",
                            "name": "Read",
                            "arguments": '{"path":"/tmp/a.py"}',
                        },
                    )()
                ],
            },
        )()

        tool_calls = OpenAIProvider._extract_tool_calls_from_responses(response)

        assert tool_calls is not None
        assert tool_calls[0]["id"] == "call_123"
        assert tool_calls[0]["responses_api_item_id"] == "fc_123"
        assert tool_calls[0]["responses_api_call_id"] == "call_123"
        assert tool_calls[0]["responses_api_response_id"] == "resp_123"

    def test_convert_messages_to_responses_input_restores_original_call_ids(self) -> None:
        """Responses follow-up history should replay original OpenAI function-call IDs."""
        from ternion.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        messages = [
            ChatMessage(
                role=MessageRole.ASSISTANT,
                content=None,
                tool_calls=[
                    {
                        "id": "ternion_0123456789ab_r0001_c00",
                        "type": "function",
                        "function": {"name": "Read", "arguments": '{"path":"/tmp/a.py"}'},
                        "responses_api_item_id": "fc_123",
                        "responses_api_call_id": "call_123",
                    }
                ],
            ),
            ChatMessage(
                role=MessageRole.TOOL,
                content="RESULT_A",
                tool_call_id="ternion_0123456789ab_r0001_c00",
            ),
        ]

        converted = provider._convert_messages_to_responses_input(messages)

        assert converted == [
            {
                "type": "function_call",
                "id": "fc_123",
                "call_id": "call_123",
                "name": "Read",
                "arguments": '{"path":"/tmp/a.py"}',
            },
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": "RESULT_A",
            },
        ]

    @pytest.mark.asyncio
    async def test_gpt5_responses_model_omits_temperature(self) -> None:
        """Responses API payload should omit unsupported temperature for GPT-5 models."""
        from ternion.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]

        response = type(
            "MockResponse",
            (),
            {"output_text": "ok", "output": [], "usage": None},
        )()

        with patch.object(
            provider._client.responses,
            "create",
            AsyncMock(return_value=response),
        ) as mock_create:
            await provider.chat_completion(
                messages=messages,
                model="gpt-5.4-pro",
                temperature=0.3,
                api_mode="responses",
            )

        assert "temperature" not in mock_create.await_args.kwargs

    @pytest.mark.asyncio
    async def test_responses_tool_followup_uses_previous_response_id(self) -> None:
        """Tool-result follow-ups should resume via previous_response_id instead of replaying function calls."""
        from ternion.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        messages = [
            ChatMessage(
                role=MessageRole.ASSISTANT,
                content=None,
                tool_calls=[
                    {
                        "id": "ternion_0123456789ab_r0001_c00",
                        "type": "function",
                        "function": {"name": "Read", "arguments": '{"path":"/tmp/a.py"}'},
                        "responses_api_item_id": "fc_123",
                        "responses_api_call_id": "call_123",
                        "responses_api_response_id": "resp_123",
                    }
                ],
            ),
            ChatMessage(
                role=MessageRole.TOOL,
                content="RESULT_A",
                tool_call_id="ternion_0123456789ab_r0001_c00",
            ),
        ]

        response = type(
            "MockResponse",
            (),
            {"output_text": "ok", "output": [], "usage": None},
        )()

        with patch.object(
            provider._client.responses,
            "create",
            AsyncMock(return_value=response),
        ) as mock_create:
            await provider.chat_completion(
                messages=messages,
                model="gpt-5.4-pro",
                temperature=0.3,
                api_mode="responses",
            )

        kwargs = mock_create.await_args.kwargs
        assert kwargs["previous_response_id"] == "resp_123"
        assert kwargs["input"] == [
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": "RESULT_A",
            }
        ]

    @pytest.mark.asyncio
    async def test_gpt5_chat_model_omits_temperature(self) -> None:
        """Chat Completions payload should omit unsupported temperature for GPT-5 models."""
        from ternion.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]

        chat_choice = type(
            "MockChoice",
            (),
            {
                "message": type("MockMessage", (), {"content": "ok", "tool_calls": None})(),
                "finish_reason": "stop",
            },
        )()
        chat_response = type(
            "MockChatResponse",
            (),
            {
                "choices": [chat_choice],
                "usage": type(
                    "MockUsage",
                    (),
                    {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                        "completion_tokens_details": None,
                    },
                )(),
            },
        )()

        with patch.object(
            provider._client.chat.completions,
            "create",
            AsyncMock(return_value=chat_response),
        ) as mock_create:
            await provider.chat_completion(
                messages=messages,
                model="gpt-5.4",
                temperature=0.3,
            )

        assert "temperature" not in mock_create.await_args.kwargs


class TestAnthropicProviderModelNormalization:
    """Tests for Anthropic API model ID normalization."""

    @pytest.mark.asyncio
    async def test_chat_completion_normalizes_latest_snapshot_id(self) -> None:
        """Anthropic chat completions should use the canonical 4.6+ API model ID."""
        from ternion.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]
        response = type(
            "MockAnthropicResponse",
            (),
            {
                "content": [type("TextBlock", (), {"type": "text", "text": "ok"})()],
                "usage": type(
                    "MockUsage",
                    (),
                    {"input_tokens": 1, "output_tokens": 1},
                )(),
                "stop_reason": "end_turn",
            },
        )()

        with (
            patch.object(
                provider._client.messages,
                "create",
                AsyncMock(return_value=response),
            ) as mock_create,
            patch("ternion.providers.anthropic.model_catalog_service") as mock_catalog,
            patch("ternion.providers.anthropic.log_manager.emit_token_usage"),
            patch("ternion.providers.anthropic.budget_manager.record_usage"),
        ):
            # Hermetic: no catalog entry, so the naming-rule fallback is exercised
            # regardless of the developer machine's real ~/.ternion catalog cache.
            mock_catalog.get_model_cached.return_value = None
            await provider.chat_completion(
                messages=messages,
                model="claude-opus-4-6-20260205",
            )

        assert mock_create.await_args.kwargs["model"] == "claude-opus-4-6"

    @pytest.mark.asyncio
    async def test_chat_completion_prefers_catalog_api_model_id(self) -> None:
        """Anthropic chat completions should prefer the catalog API model ID."""
        from ternion.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]
        response = type(
            "MockAnthropicResponse",
            (),
            {
                "content": [type("TextBlock", (), {"type": "text", "text": "ok"})()],
                "usage": type(
                    "MockUsage",
                    (),
                    {"input_tokens": 1, "output_tokens": 1},
                )(),
                "stop_reason": "end_turn",
            },
        )()
        catalog_model = type(
            "MockCatalogModel",
            (),
            {
                "provider": "anthropic",
                "id": "claude-opus-4-8",
                "api_model_id": "claude-opus-4-8",
            },
        )()

        with (
            patch.object(
                provider._client.messages,
                "create",
                AsyncMock(return_value=response),
            ) as mock_create,
            patch("ternion.providers.anthropic.model_catalog_service") as mock_catalog_service,
            patch("ternion.providers.anthropic.log_manager.emit_token_usage"),
            patch("ternion.providers.anthropic.budget_manager.record_usage"),
        ):
            mock_catalog_service.get_model_cached.return_value = catalog_model
            await provider.chat_completion(
                messages=messages,
                model="claude-opus-4-8-source",
            )

        assert mock_create.await_args.kwargs["model"] == "claude-opus-4-8"

    @pytest.mark.asyncio
    async def test_chat_completion_stream_normalizes_latest_snapshot_id(self) -> None:
        """Anthropic streaming calls should use the canonical 4.6+ API model ID."""
        from ternion.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]

        class MockStreamContext:
            """Minimal async stream context used by the Anthropic provider tests."""

            def __init__(self) -> None:
                self.text_stream = self._text_stream()

            async def __aenter__(self) -> "MockStreamContext":
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                tb: object | None,
            ) -> None:
                return None

            async def get_final_message(self) -> object:
                return type(
                    "MockFinalMessage",
                    (),
                    {
                        "usage": type(
                            "MockUsage",
                            (),
                            {"input_tokens": 1, "output_tokens": 1},
                        )(),
                        "content": [],
                    },
                )()

            async def _text_stream(self) -> AsyncGenerator[str, None]:
                yield "ok"

        with (
            patch.object(
                provider._client.messages,
                "stream",
                return_value=MockStreamContext(),
            ) as mock_stream,
            patch("ternion.providers.anthropic.model_catalog_service") as mock_catalog,
            patch("ternion.providers.anthropic.log_manager.emit_token_usage"),
            patch("ternion.providers.anthropic.budget_manager.record_usage"),
        ):
            # Hermetic: no catalog entry, so the naming-rule fallback is exercised
            # regardless of the developer machine's real ~/.ternion catalog cache.
            mock_catalog.get_model_cached.return_value = None
            chunks = [
                chunk
                async for chunk in provider.chat_completion_stream(
                    messages=messages,
                    model="claude-sonnet-4-6-20260217",
                )
            ]

        assert chunks == ["ok"]
        assert mock_stream.call_args.kwargs["model"] == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_chat_completion_stream_prefers_catalog_api_model_id(self) -> None:
        """Anthropic streaming calls should prefer the catalog API model ID."""
        from ternion.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]
        catalog_model = type(
            "MockCatalogModel",
            (),
            {
                "provider": "anthropic",
                "id": "claude-sonnet-4-8",
                "api_model_id": "claude-sonnet-4-8",
            },
        )()

        class MockStreamContext:
            """Minimal async stream context used by the Anthropic provider tests."""

            def __init__(self) -> None:
                self.text_stream = self._text_stream()

            async def __aenter__(self) -> "MockStreamContext":
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                tb: object | None,
            ) -> None:
                return None

            async def get_final_message(self) -> object:
                return type(
                    "MockFinalMessage",
                    (),
                    {
                        "usage": type(
                            "MockUsage",
                            (),
                            {"input_tokens": 1, "output_tokens": 1},
                        )(),
                        "content": [],
                    },
                )()

            async def _text_stream(self) -> AsyncGenerator[str, None]:
                yield "ok"

        with (
            patch.object(
                provider._client.messages,
                "stream",
                return_value=MockStreamContext(),
            ) as mock_stream,
            patch("ternion.providers.anthropic.model_catalog_service") as mock_catalog_service,
            patch("ternion.providers.anthropic.log_manager.emit_token_usage"),
            patch("ternion.providers.anthropic.budget_manager.record_usage"),
        ):
            mock_catalog_service.get_model_cached.return_value = catalog_model
            chunks = [
                chunk
                async for chunk in provider.chat_completion_stream(
                    messages=messages,
                    model="claude-sonnet-4-8-source",
                )
            ]

        assert chunks == ["ok"]
        assert mock_stream.call_args.kwargs["model"] == "claude-sonnet-4-8"


class TestAnthropicPromptCaching:
    """Tests for Anthropic prompt caching, output clamping, and cache metering."""

    @staticmethod
    def _build_response(
        input_tokens: int = 10,
        output_tokens: int = 5,
        **usage_extra: int,
    ) -> Any:
        usage_attrs = {"input_tokens": input_tokens, "output_tokens": output_tokens}
        usage_attrs.update(usage_extra)
        return type(
            "MockAnthropicResponse",
            (),
            {
                "content": [type("TextBlock", (), {"type": "text", "text": "ok"})()],
                "usage": type("MockUsage", (), usage_attrs)(),
                "stop_reason": "end_turn",
            },
        )()

    @pytest.mark.asyncio
    async def test_cache_breakpoints_applied_by_default(self) -> None:
        """System and final message should carry cache_control breakpoints."""
        from ternion.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content="System rules"),
            ChatMessage(role=MessageRole.USER, content="First question"),
            ChatMessage(role=MessageRole.USER, content="Second question"),
        ]

        with (
            patch.object(
                provider._client.messages,
                "create",
                AsyncMock(return_value=self._build_response()),
            ) as mock_create,
            patch("ternion.providers.anthropic.log_manager.emit_token_usage"),
            patch("ternion.providers.anthropic.budget_manager.record_usage"),
        ):
            await provider.chat_completion(messages=messages, model="claude-sonnet-4-6")

        kwargs = mock_create.await_args.kwargs
        system_param = kwargs["system"]
        assert isinstance(system_param, list)
        assert system_param[0]["cache_control"] == {"type": "ephemeral"}
        assert system_param[0]["text"] == "System rules"

        sent_messages = kwargs["messages"]
        assert isinstance(sent_messages[-1]["content"], list)
        assert sent_messages[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
        # Earlier messages keep their original plain-string content.
        assert sent_messages[0]["content"] == "First question"

    @pytest.mark.asyncio
    async def test_cache_prompt_false_keeps_plain_payload(self) -> None:
        """Disabling cache_prompt must leave system and messages untouched."""
        from ternion.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content="System rules"),
            ChatMessage(role=MessageRole.USER, content="Question"),
        ]

        with (
            patch.object(
                provider._client.messages,
                "create",
                AsyncMock(return_value=self._build_response()),
            ) as mock_create,
            patch("ternion.providers.anthropic.log_manager.emit_token_usage"),
            patch("ternion.providers.anthropic.budget_manager.record_usage"),
        ):
            await provider.chat_completion(
                messages=messages,
                model="claude-sonnet-4-6",
                cache_prompt=False,
            )

        kwargs = mock_create.await_args.kwargs
        assert kwargs["system"] == "System rules"
        assert kwargs["messages"][-1]["content"] == "Question"

    @pytest.mark.asyncio
    async def test_max_tokens_clamped_to_catalog_limit(self) -> None:
        """Requested max_tokens above the model limit must be clamped."""
        from ternion.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]
        catalog_model = type(
            "MockCatalogModel",
            (),
            {
                "provider": "anthropic",
                "id": "claude-opus-4-1-20250805",
                "api_model_id": "claude-opus-4-1-20250805",
                "max_output_tokens": 32000,
            },
        )()

        with (
            patch.object(
                provider._client.messages,
                "create",
                AsyncMock(return_value=self._build_response()),
            ) as mock_create,
            patch("ternion.providers.anthropic.model_catalog_service") as mock_catalog,
            patch("ternion.providers.anthropic.log_manager.emit_token_usage"),
            patch("ternion.providers.anthropic.budget_manager.record_usage"),
        ):
            mock_catalog.get_model_cached.return_value = catalog_model
            await provider.chat_completion(
                messages=messages,
                model="claude-opus-4-1-20250805",
                max_tokens=65536,
            )

        assert mock_create.await_args.kwargs["max_tokens"] == 32000

    @pytest.mark.asyncio
    async def test_cache_tokens_normalized_into_usage(self) -> None:
        """Cache read/write counts should be added to total input tokens."""
        from ternion.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]
        response = self._build_response(
            input_tokens=10,
            output_tokens=5,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=20,
        )

        with (
            patch.object(
                provider._client.messages,
                "create",
                AsyncMock(return_value=response),
            ),
            patch("ternion.providers.anthropic.log_manager.emit_token_usage"),
            patch("ternion.providers.anthropic.budget_manager.record_usage") as mock_record,
        ):
            result = await provider.chat_completion(
                messages=messages,
                model="claude-sonnet-4-6",
            )

        record_kwargs = mock_record.call_args.kwargs
        assert record_kwargs["input_tokens"] == 130
        assert record_kwargs["cache_read_tokens"] == 100
        assert record_kwargs["cache_write_tokens"] == 20
        assert result.usage["prompt_tokens"] == 130
        assert result.usage["cache_read_tokens"] == 100
        assert result.usage["cache_write_tokens"] == 20

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_then_succeeds(self) -> None:
        """Transient 429 errors should be retried at the provider layer."""
        from ternion.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]

        rate_limit_error = Exception("rate limited")
        rate_limit_error.status_code = 429  # type: ignore[attr-defined]

        with (
            patch.object(
                provider._client.messages,
                "create",
                AsyncMock(side_effect=[rate_limit_error, self._build_response()]),
            ) as mock_create,
            patch("ternion.providers.resilience.asyncio.sleep", new=AsyncMock()),
            patch("ternion.providers.anthropic.log_manager.emit_token_usage"),
            patch("ternion.providers.anthropic.budget_manager.record_usage"),
        ):
            result = await provider.chat_completion(
                messages=messages,
                model="claude-sonnet-4-6",
            )

        assert mock_create.await_count == 2
        assert result.content == "ok"


class TestOpenAICacheMetering:
    """Tests for OpenAI cached-token capture and output token parameter mapping."""

    @staticmethod
    def _build_chat_response(cached_tokens: int = 0) -> Any:
        from types import SimpleNamespace

        usage = SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=10,
            total_tokens=110,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=2),
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
        )
        choice = SimpleNamespace(
            message=SimpleNamespace(content="ok", tool_calls=None),
            finish_reason="stop",
        )
        return SimpleNamespace(choices=[choice], usage=usage)

    @pytest.mark.asyncio
    async def test_non_streaming_records_usage_with_cached_tokens(self) -> None:
        """Non-streaming chat completions must record usage including cache reads."""
        from ternion.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]

        with (
            patch.object(
                provider._client.chat.completions,
                "create",
                AsyncMock(return_value=self._build_chat_response(cached_tokens=60)),
            ),
            patch("ternion.providers.openai.log_manager.emit_token_usage"),
            patch("ternion.providers.openai.budget_manager.record_usage") as mock_record,
        ):
            result = await provider.chat_completion(messages=messages, model="gpt-4o")

        record_kwargs = mock_record.call_args.kwargs
        assert record_kwargs["input_tokens"] == 100
        assert record_kwargs["output_tokens"] == 10
        assert record_kwargs["cache_read_tokens"] == 60
        assert result.usage["cache_read_tokens"] == 60

    @pytest.mark.asyncio
    async def test_gpt5_chat_uses_max_completion_tokens(self) -> None:
        """gpt-5 chat models must receive max_completion_tokens, not max_tokens."""
        from ternion.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]

        with (
            patch.object(
                provider._client.chat.completions,
                "create",
                AsyncMock(return_value=self._build_chat_response()),
            ) as mock_create,
            patch("ternion.core.model_catalog.model_catalog_service") as mock_catalog,
            patch("ternion.providers.openai.log_manager.emit_token_usage"),
            patch("ternion.providers.openai.budget_manager.record_usage"),
        ):
            mock_catalog.get_model_cached.return_value = None
            await provider.chat_completion(
                messages=messages,
                model="gpt-5.4",
                max_tokens=1234,
            )

        kwargs = mock_create.await_args.kwargs
        assert kwargs["max_completion_tokens"] == 1234
        assert "max_tokens" not in kwargs

    @pytest.mark.asyncio
    async def test_legacy_chat_model_uses_max_tokens(self) -> None:
        """Non gpt-5 chat models keep the legacy max_tokens parameter."""
        from ternion.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]

        with (
            patch.object(
                provider._client.chat.completions,
                "create",
                AsyncMock(return_value=self._build_chat_response()),
            ) as mock_create,
            patch("ternion.core.model_catalog.model_catalog_service") as mock_catalog,
            patch("ternion.providers.openai.log_manager.emit_token_usage"),
            patch("ternion.providers.openai.budget_manager.record_usage"),
        ):
            mock_catalog.get_model_cached.return_value = None
            await provider.chat_completion(
                messages=messages,
                model="gpt-4o",
                max_tokens=1234,
            )

        kwargs = mock_create.await_args.kwargs
        assert kwargs["max_tokens"] == 1234
        assert "max_completion_tokens" not in kwargs


class TestGoogleCacheMetering:
    """Tests for Gemini cached-content token capture."""

    @pytest.mark.asyncio
    async def test_records_cached_content_tokens(self) -> None:
        """cached_content_token_count should be reported as cache_read_tokens."""
        from types import SimpleNamespace

        from ternion.providers.google import GoogleProvider

        provider = GoogleProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]
        usage_metadata = SimpleNamespace(
            prompt_token_count=100,
            candidates_token_count=8,
            thoughts_token_count=0,
            cached_content_token_count=40,
            total_token_count=108,
        )
        response = SimpleNamespace(usage_metadata=usage_metadata, text="ok")

        with (
            patch.object(
                provider._client.aio.models,
                "generate_content",
                AsyncMock(return_value=response),
            ),
            patch("ternion.providers.google.log_manager.emit_token_usage"),
            patch("ternion.providers.google.budget_manager.record_usage") as mock_record,
        ):
            result = await provider.chat_completion(
                messages=messages,
                model="gemini-3-pro-preview",
            )

        record_kwargs = mock_record.call_args.kwargs
        assert record_kwargs["input_tokens"] == 100
        assert record_kwargs["cache_read_tokens"] == 40
        assert result.usage["cache_read_tokens"] == 40


class TestMaxOutputTokensClamping:
    """Tests for catalog-based output budget clamping in OpenAI/Google adapters."""

    @staticmethod
    def _catalog_model_with_limit(limit: int) -> Any:
        return type(
            "MockCatalogModel",
            (),
            {"max_output_tokens": limit},
        )()

    @pytest.mark.asyncio
    async def test_openai_clamps_to_catalog_limit(self) -> None:
        """Oversized budgets must be reduced to the model's catalog limit."""
        from ternion.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]

        with (
            patch.object(
                provider._client.chat.completions,
                "create",
                AsyncMock(return_value=TestOpenAICacheMetering._build_chat_response()),
            ) as mock_create,
            patch("ternion.core.model_catalog.model_catalog_service") as mock_catalog,
            patch("ternion.providers.openai.log_manager.emit_token_usage"),
            patch("ternion.providers.openai.budget_manager.record_usage"),
        ):
            mock_catalog.get_model_cached.return_value = self._catalog_model_with_limit(8192)
            await provider.chat_completion(
                messages=messages,
                model="gpt-5.4",
                max_tokens=65536,
            )

        assert mock_create.await_args.kwargs["max_completion_tokens"] == 8192

    @pytest.mark.asyncio
    async def test_openai_passes_through_when_catalog_unknown(self) -> None:
        """Without a catalog entry the requested budget is preserved unchanged."""
        from ternion.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]

        with (
            patch.object(
                provider._client.chat.completions,
                "create",
                AsyncMock(return_value=TestOpenAICacheMetering._build_chat_response()),
            ) as mock_create,
            patch("ternion.core.model_catalog.model_catalog_service") as mock_catalog,
            patch("ternion.providers.openai.log_manager.emit_token_usage"),
            patch("ternion.providers.openai.budget_manager.record_usage"),
        ):
            mock_catalog.get_model_cached.return_value = None
            await provider.chat_completion(
                messages=messages,
                model="gpt-4o",
                max_tokens=4096,
            )

        assert mock_create.await_args.kwargs["max_tokens"] == 4096

    @pytest.mark.asyncio
    async def test_google_clamps_to_catalog_limit(self) -> None:
        """Gemini output budgets must be reduced to the model's catalog limit."""
        from types import SimpleNamespace

        from ternion.providers.google import GoogleProvider

        provider = GoogleProvider(api_key="test-key")
        messages = [ChatMessage(role=MessageRole.USER, content="Hello")]
        usage_metadata = SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=5,
            thoughts_token_count=0,
            cached_content_token_count=0,
            total_token_count=15,
        )
        response = SimpleNamespace(usage_metadata=usage_metadata, text="ok")

        with (
            patch.object(
                provider._client.aio.models,
                "generate_content",
                AsyncMock(return_value=response),
            ) as mock_generate,
            patch("ternion.core.model_catalog.model_catalog_service") as mock_catalog,
            patch("ternion.providers.google.log_manager.emit_token_usage"),
            patch("ternion.providers.google.budget_manager.record_usage"),
        ):
            mock_catalog.get_model_cached.return_value = self._catalog_model_with_limit(4096)
            await provider.chat_completion(
                messages=messages,
                model="gemini-3-pro-preview",
                max_tokens=131072,
            )

        config = mock_generate.await_args.kwargs["config"]
        assert config.max_output_tokens == 4096

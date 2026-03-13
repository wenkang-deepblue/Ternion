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
        # settings fallback has been removed - only config_store is used
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

        with patch(
            "ternion.workflow.nodes.model_catalog_service"
        ) as mock_catalog:
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

        with patch(
            "ternion.workflow.nodes.model_catalog_service"
        ) as mock_catalog:
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

        with patch(
            "ternion.workflow.nodes.model_catalog_service"
        ) as mock_catalog:
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
                ]
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
            patch("ternion.providers.anthropic.log_manager.emit_token_usage"),
            patch("ternion.providers.anthropic.budget_manager.record_usage"),
        ):
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
            patch("ternion.providers.anthropic.log_manager.emit_token_usage"),
            patch("ternion.providers.anthropic.budget_manager.record_usage"),
        ):
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


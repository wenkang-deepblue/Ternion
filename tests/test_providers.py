"""
Tests for provider adapters.
"""

from unittest.mock import patch

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

            async def chat_completion(self, *args, **kwargs):
                pass

            async def chat_completion_stream(self, *args, **kwargs):
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

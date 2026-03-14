"""
Base provider interface for LLM adapters.

All provider implementations must inherit from BaseProvider and implement
the required abstract methods for chat completion.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from ternion.core.models import ChatMessage


@dataclass
class ProviderResponse:
    """
    Response from an LLM provider.

    Encapsulates both streaming and non-streaming responses.
    """

    content: str = ""
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    usage: dict[str, int] = field(default_factory=dict)
    raw_response: Any = None

    @property
    def is_complete(self) -> bool:
        """True when the provider has issued a finish_reason, indicating no further chunks will follow."""
        return self.finish_reason is not None


class BaseProvider(ABC):
    """
    Abstract base class for LLM providers.

    All provider implementations (OpenAI, Anthropic, Google) must implement:
    - chat_completion: Non-streaming chat completion
    - chat_completion_stream: Streaming chat completion
    - is_available: Check if provider is configured and reachable
    """

    def __init__(self, api_key: str, **kwargs: Any) -> None:
        """
        Initialize provider with API key.

        Args:
            api_key: The API key for authentication
            **kwargs: Additional provider-specific configuration
        """
        self.api_key = api_key
        self._kwargs = kwargs

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier; must match the key used in config_store and ProviderManager._providers."""
        ...

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Fallback model used when no model is specified in chat_completion calls."""
        ...

    @property
    def supports_native_tool_calls(self) -> bool:
        """
        Whether this provider supports OpenAI-compatible native tool calling.

        Native tool calling means:
        - the client can send `tools` / `tool_choice`
        - the model can return structured `tool_calls` without a text protocol

        Providers that do not support native tool calling should return False and
        use a text-based tool-call protocol instead.
        """
        return False

    @abstractmethod
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
            model: Model to use (defaults to provider's default)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            ProviderResponse with the generated content
        """
        ...

    @abstractmethod
    def chat_completion_stream(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming chat completion.

        This method returns an async generator that yields content chunks.
        Implementations should be async generators (async def with yield).

        Args:
            messages: List of chat messages
            model: Model to use (defaults to provider's default)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Yields:
            Content chunks as they are generated
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if the provider is available and properly configured.

        Returns:
            True if provider can be used, False otherwise
        """
        ...

    def _convert_messages(self, messages: list[ChatMessage]) -> Any:
        """
        Convert ChatMessage objects to provider-specific format.

        Override this method in subclasses to handle provider-specific
        message format requirements (especially for multimodal content).
        The return type varies by provider:
        - OpenAI: list[dict[str, Any]]
        - Anthropic: tuple[str, list[dict[str, Any]]] (system_prompt, messages)
        - Google: tuple[str, list[dict[str, Any]]] (system_instruction, contents_list)

        Args:
            messages: List of ChatMessage objects

        Returns:
            Provider-specific message format; structure varies by subclass.
        """
        result = []
        for msg in messages:
            if isinstance(msg.content, str | list):
                result.append(
                    {
                        "role": msg.role.value,
                        "content": msg.content,
                    }
                )
            else:
                result.append(
                    {
                        "role": msg.role.value,
                        "content": str(msg.content) if msg.content else "",
                    }
                )
        return result

"""
Provider manager for handling multiple LLM providers.

Provides unified access to providers with fallback logic and role-based
provider selection.
"""

import structlog
from collections.abc import AsyncGenerator
from typing import Any

from ternion.core.config import settings
from ternion.core.exceptions import AllProvidersUnavailable, ProviderError
from ternion.core.models import ChatMessage
from ternion.providers.base import BaseProvider, ProviderResponse
from ternion.providers.openai import OpenAIProvider
from ternion.providers.anthropic import AnthropicProvider
from ternion.providers.google import GoogleProvider

logger = structlog.get_logger(__name__)


class ProviderManager:
    """
    Manages LLM providers with fallback support.

    Initializes providers from configuration and provides methods to get
    providers by name or by role (with automatic fallback).
    """

    def __init__(self) -> None:
        """Initialize provider manager with configured providers."""
        self._providers: dict[str, BaseProvider] = {}
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """Initialize all configured providers."""
        # OpenAI
        if settings.providers.openai.api_key:
            self._providers["openai"] = OpenAIProvider(
                api_key=settings.providers.openai.api_key,
                base_url=settings.providers.openai.base_url,
                default_model=settings.providers.openai.default_model or "gpt-4-turbo",
            )
            logger.info("provider_initialized", provider="openai")

        # Anthropic
        if settings.providers.anthropic.api_key:
            self._providers["anthropic"] = AnthropicProvider(
                api_key=settings.providers.anthropic.api_key,
                default_model=settings.providers.anthropic.default_model or "claude-3-5-sonnet-latest",
            )
            logger.info("provider_initialized", provider="anthropic")

        # Google
        if settings.providers.google.api_key:
            self._providers["google"] = GoogleProvider(
                api_key=settings.providers.google.api_key,
                default_model=settings.providers.google.default_model or "gemini-2.0-flash",
            )
            logger.info("provider_initialized", provider="google")

        if not self._providers:
            logger.warning("no_providers_configured")

    def get_provider(self, name: str) -> BaseProvider | None:
        """
        Get a provider by name.

        Args:
            name: Provider name ('openai', 'anthropic', 'google')

        Returns:
            Provider instance or None if not configured
        """
        return self._providers.get(name)

    def get_provider_for_role(self, role: str) -> BaseProvider:
        """
        Get a provider for a specific discussion role.

        Uses configuration to determine primary and fallback providers.

        Args:
            role: Role name ('arbiter', 'writer', 'reviewer')

        Returns:
            Provider instance

        Raises:
            AllProvidersUnavailable: If no providers are available for the role
        """
        role_config = getattr(settings.discussion.roles, role, None)
        if not role_config:
            raise ValueError(f"Unknown role: {role}")

        # Try primary provider
        primary = role_config.primary
        if primary in self._providers:
            logger.debug("using_primary_provider", role=role, provider=primary)
            return self._providers[primary]

        # Try fallback providers
        for fallback in role_config.fallback:
            if fallback in self._providers:
                logger.warning(
                    "using_fallback_provider",
                    role=role,
                    primary=primary,
                    fallback=fallback,
                )
                return self._providers[fallback]

        raise AllProvidersUnavailable(role)

    async def chat_completion(
        self,
        provider_name: str,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """
        Execute chat completion with a specific provider.

        Args:
            provider_name: Name of the provider to use
            messages: Chat messages
            model: Optional model override
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            **kwargs: Additional parameters

        Returns:
            ProviderResponse from the provider

        Raises:
            ProviderError: If provider fails
            ValueError: If provider not found
        """
        provider = self.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Provider not configured: {provider_name}")

        try:
            return await provider.chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        except Exception as e:
            raise ProviderError(str(e), provider_name) from e

    async def chat_completion_stream(
        self,
        provider_name: str,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Execute streaming chat completion with a specific provider.

        Args:
            provider_name: Name of the provider to use
            messages: Chat messages
            model: Optional model override
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            **kwargs: Additional parameters

        Yields:
            Content chunks from the provider

        Raises:
            ProviderError: If provider fails
            ValueError: If provider not found
        """
        provider = self.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Provider not configured: {provider_name}")

        try:
            async for chunk in provider.chat_completion_stream(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            ):
                yield chunk
        except Exception as e:
            raise ProviderError(str(e), provider_name) from e

    async def chat_completion_with_fallback(
        self,
        role: str,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """
        Execute chat completion with automatic fallback on failure.

        Tries primary provider first, then falls back to configured fallbacks.

        Args:
            role: Discussion role ('arbiter', 'writer', 'reviewer')
            messages: Chat messages
            model: Optional model override
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            **kwargs: Additional parameters

        Returns:
            ProviderResponse from successful provider

        Raises:
            AllProvidersUnavailable: If all providers fail
        """
        role_config = getattr(settings.discussion.roles, role, None)
        if not role_config:
            raise ValueError(f"Unknown role: {role}")

        providers_to_try = [role_config.primary] + role_config.fallback
        last_error: Exception | None = None

        for provider_name in providers_to_try:
            if provider_name not in self._providers:
                continue

            try:
                provider = self._providers[provider_name]
                result = await provider.chat_completion(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                logger.info(
                    "chat_completion_success",
                    role=role,
                    provider=provider_name,
                )
                return result
            except Exception as e:
                logger.warning(
                    "provider_failed",
                    role=role,
                    provider=provider_name,
                    error=str(e),
                )
                last_error = e

        logger.error(
            "all_providers_failed",
            role=role,
            tried=providers_to_try,
        )
        raise AllProvidersUnavailable(role) from last_error

    @property
    def available_providers(self) -> list[str]:
        """List of configured provider names."""
        return list(self._providers.keys())

    @property
    def has_providers(self) -> bool:
        """Check if any providers are configured."""
        return len(self._providers) > 0


# Global provider manager instance
provider_manager = ProviderManager()

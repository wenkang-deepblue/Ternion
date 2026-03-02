"""
Provider manager for handling multiple LLM providers.

Provides unified access to providers with role-based selection.
All role configuration must be explicitly set via Web Control Panel.
No automatic fallback - user must configure all roles.
"""

from collections.abc import AsyncGenerator
from typing import Any

import structlog

from ternion.core.config import settings
from ternion.core.config_store import config_store
from ternion.core.exceptions import AllProvidersUnavailable, ProviderError
from ternion.core.models import ChatMessage
from ternion.providers.anthropic import AnthropicProvider
from ternion.providers.base import BaseProvider, ProviderResponse
from ternion.providers.google import GoogleProvider
from ternion.providers.openai import OpenAIProvider
from ternion.utils.i18n import MessageKey, t

logger = structlog.get_logger(__name__)


class ProviderManager:
    """
    Manages LLM providers.

    Initializes providers from configuration and provides methods to get
    providers by name or by role. All configuration must be explicitly
    set via Web Control Panel.

    Configuration source: Web Control Panel (config_store) - ~/.ternion/config.json
    """

    def __init__(self) -> None:
        """Initialize provider manager with configured providers."""
        self._providers: dict[str, BaseProvider] = {}
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """
        Initialize all configured providers.

        Loads providers configured via Web Control Panel (config_store).
        """
        self._providers.clear()

        for name in ("openai", "anthropic", "google"):
            # Use Web Control Panel configuration
            api_key = config_store.get_provider_api_key(name)
            if api_key:
                self._create_provider(name, api_key)

        if not self._providers:
            logger.warning(
                "no_providers_configured",
                hint=t(MessageKey.NO_PROVIDERS_CONFIGURED),
            )

    def _create_provider(self, name: str, api_key: str) -> None:
        """
        Create a provider instance by name.

        Args:
            name: Provider name ('openai', 'anthropic', 'google')
            api_key: API key for the provider
        """
        try:
            if name == "openai":
                # base_url can optionally come from settings for proxy support
                env_config = getattr(settings.providers, "openai", None)
                self._providers[name] = OpenAIProvider(
                    api_key=api_key,
                    base_url=env_config.base_url if env_config else None,
                )
            elif name == "anthropic":
                self._providers[name] = AnthropicProvider(api_key=api_key)
            elif name == "google":
                self._providers[name] = GoogleProvider(api_key=api_key)
            logger.info("provider_initialized", provider=name)
        except Exception as e:
            logger.error("provider_init_failed", provider=name, error=str(e))

    def reload(self) -> None:
        """
        Reload providers from configuration.

        Call this after Web Control Panel config changes (API key add/delete/select)
        to ensure providers reflect the latest configuration.
        """
        config_store.reload()
        self._initialize_providers()
        logger.info("providers_reloaded", available=list(self._providers.keys()))

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

        Args:
            role: Role name ('arbiter', 'writer', 'reviewer', 'ternion_a', 'ternion_b', 'ternion_c')

        Returns:
            Provider instance

        Raises:
            AllProvidersUnavailable: If no providers are available for the role
        """
        # Require explicit Web Control Panel configuration
        role_cfg = config_store.get_role_config(role)

        if not role_cfg or not role_cfg.provider:
            raise AllProvidersUnavailable(t(MessageKey.ROLE_NOT_CONFIGURED, role=role))

        provider = self._providers.get(role_cfg.provider)
        if provider:
            logger.debug(
                "using_ui_configured_provider",
                role=role,
                provider=role_cfg.provider,
            )
            return provider

        # Provider configured but not available (API key not set)
        raise AllProvidersUnavailable(
            t(
                MessageKey.PROVIDER_UNAVAILABLE,
                role=role,
                provider=role_cfg.provider,
            )
        )

    async def chat_completion(
        self,
        provider_name: str,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout_seconds: int | None = None,
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
            timeout_seconds: Optional timeout override (default: from config)
            **kwargs: Additional parameters

        Returns:
            ProviderResponse from the provider

        Raises:
            ProviderError: If provider fails
            TimeoutError: If request times out (CR-030)
            ValueError: If provider not found
        """
        import asyncio

        from ternion.core.config import settings
        from ternion.core.exceptions import TimeoutError as TernionTimeout
        from ternion.utils.log_manager import log_manager

        provider = self.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Provider not configured: {provider_name}")

        # Use provided timeout or fall back to config default
        timeout = timeout_seconds or settings.discussion.timeout_seconds

        try:
            return await asyncio.wait_for(
                provider.chat_completion(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                ),
                timeout=timeout,
            )
        except TimeoutError:
            log_manager.emit(
                "ERROR",
                "LLM",
                f"Provider timeout: {provider_name} did not respond within {timeout}s",
            )
            raise TernionTimeout(
                operation=f"chat_completion ({provider_name})",
                timeout_seconds=timeout,
            ) from None
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

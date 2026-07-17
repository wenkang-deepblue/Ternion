"""
Custom exceptions for Ternion.

All exceptions inherit from TernionError for easy catching.
"""

from typing import Any


class TernionError(Exception):
    """Base exception for all Ternion errors."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        """Initialize TernionError.

        Args:
            message: The error message.
            status_code: The associated HTTP status code.
        """
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ProviderError(TernionError):
    """Error from an LLM provider."""

    def __init__(
        self,
        message: str,
        provider: str,
        status_code: int = 502,
    ) -> None:
        """Initialize ProviderError.

        Args:
            message: The error message from the provider.
            provider: The name of the LLM provider.
            status_code: The associated HTTP status code.
        """
        self.provider = provider
        super().__init__(f"[{provider}] {message}", status_code)


class RuntimeModelUnavailableError(TernionError):
    """Provider rejected a configured runtime model because it no longer exists."""

    def __init__(self, provider: str, model: str, provider_message: str = "") -> None:
        """Initialize RuntimeModelUnavailableError.

        Args:
            provider: The name of the LLM provider.
            model: The name of the unavailable model.
            provider_message: Optional detailed message from the provider.
        """
        self.provider = provider
        self.model = model
        self.provider_message = provider_message
        self.code = "MODEL_UNAVAILABLE"
        self.refresh_suggested = True
        message = provider_message or f"Configured model is unavailable: {provider} / {model}"
        super().__init__(message, status_code=400)

    def to_payload(self) -> dict[str, Any]:
        """Serialize the runtime error into a stable structured payload.

        Returns:
            A dictionary containing the error payload.
        """
        payload = {
            "code": self.code,
            "provider": self.provider,
            "model": self.model,
            "refresh_suggested": self.refresh_suggested,
        }
        if self.provider_message:
            payload["provider_message"] = self.provider_message
        return payload


class AllProvidersUnavailable(TernionError):
    """All LLM providers failed or are unavailable."""

    def __init__(self, role: str) -> None:
        """Initialize AllProvidersUnavailable.

        Args:
            role: The role for which no providers were available.
        """
        self.role = role
        super().__init__(
            f"All providers unavailable for role: {role}",
            status_code=503,
        )


class ConfigurationError(TernionError):
    """Configuration error."""

    def __init__(self, message: str) -> None:
        """Initialize ConfigurationError.

        Args:
            message: The configuration error message.
        """
        super().__init__(message, status_code=500)


class TernionTimeoutError(TernionError):
    """Operation timed out."""

    def __init__(self, operation: str, timeout_seconds: int) -> None:
        """Initialize TernionTimeoutError.

        Args:
            operation: The name of the timed-out operation.
            timeout_seconds: The duration after which the timeout occurred.
        """
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Operation '{operation}' timed out after {timeout_seconds}s",
            status_code=504,
        )


class ValidationError(TernionError):
    """Request validation error."""

    def __init__(self, message: str) -> None:
        """Initialize ValidationError.

        Args:
            message: The validation error message.
        """
        super().__init__(message, status_code=400)

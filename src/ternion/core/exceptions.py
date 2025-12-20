"""
Custom exceptions for Ternion.

All exceptions inherit from TernionError for easy catching.
"""


class TernionError(Exception):
    """Base exception for all Ternion errors."""

    def __init__(self, message: str, status_code: int = 500) -> None:
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
        self.provider = provider
        super().__init__(f"[{provider}] {message}", status_code)


class AllProvidersUnavailable(TernionError):
    """All LLM providers failed or are unavailable."""

    def __init__(self, role: str) -> None:
        self.role = role
        super().__init__(
            f"All providers unavailable for role: {role}",
            status_code=503,
        )


class ConfigurationError(TernionError):
    """Configuration error."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=500)


class TimeoutError(TernionError):
    """Operation timed out."""

    def __init__(self, operation: str, timeout_seconds: int) -> None:
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Operation '{operation}' timed out after {timeout_seconds}s",
            status_code=504,
        )


class ValidationError(TernionError):
    """Request validation error."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400)

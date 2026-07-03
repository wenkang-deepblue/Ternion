"""
Shared resilience primitives for LLM provider adapters.

Provides per-provider concurrency limiting and a unified retry policy with
exponential backoff (plus jitter) for transient provider failures such as
rate limits, overloads, and transient network errors.
"""

import asyncio
import random
import weakref
from collections.abc import Awaitable, Callable

import structlog

logger = structlog.get_logger(__name__)

# Maximum concurrent in-flight requests per provider within one event loop.
PROVIDER_MAX_CONCURRENT_REQUESTS = 3

RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.0
RETRY_MAX_DELAY_SECONDS = 30.0

# 529 is Anthropic's "overloaded" status; 408 is request timeout.
_RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504, 529})

# Client-side errors that must never be retried (auth, validation, missing model).
_NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403, 404, 409, 413, 422})

# Message markers consulted only when no HTTP status can be extracted.
_RETRYABLE_MESSAGE_MARKERS = (
    "rate limit",
    "rate_limit",
    "overloaded",
    "service unavailable",
    "temporarily unavailable",
    "connection error",
    "connection reset",
    "connection aborted",
    "timed out",
    "timeout",
)

# Semaphores are bound to the event loop that first acquires them, so they are
# keyed per running loop to stay safe across test loops and restarts.
_loop_semaphores: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[str, asyncio.Semaphore]
] = weakref.WeakKeyDictionary()


def get_provider_semaphore(provider_name: str) -> asyncio.Semaphore:
    """
    Return the per-provider concurrency semaphore for the running event loop.

    Args:
        provider_name: Provider identifier ('openai', 'anthropic', 'google').

    Returns:
        Semaphore limiting concurrent requests to PROVIDER_MAX_CONCURRENT_REQUESTS.
    """
    loop = asyncio.get_running_loop()
    per_loop = _loop_semaphores.get(loop)
    if per_loop is None:
        per_loop = {}
        _loop_semaphores[loop] = per_loop
    semaphore = per_loop.get(provider_name)
    if semaphore is None:
        semaphore = asyncio.Semaphore(PROVIDER_MAX_CONCURRENT_REQUESTS)
        per_loop[provider_name] = semaphore
    return semaphore


def _extract_status_code(error: Exception) -> int | None:
    """Extract an HTTP status code from a provider SDK exception, best effort."""
    for attr in ("status_code", "code", "status"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(error, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    return None


def is_retryable_provider_error(error: Exception) -> bool:
    """
    Classify whether a provider error is transient and safe to retry.

    Status codes take precedence over message matching: explicit client errors
    (400/401/403/404/...) are never retried even if their message happens to
    contain a transient-looking marker.

    Args:
        error: Exception raised by a provider SDK call.

    Returns:
        True when the error looks transient (rate limit, overload, network).
    """
    if isinstance(error, asyncio.CancelledError):  # pragma: no cover - defensive
        return False

    status = _extract_status_code(error)
    if status is not None:
        if status in _NON_RETRYABLE_STATUS_CODES:
            return False
        return status in _RETRYABLE_STATUS_CODES

    message = str(error).lower()
    return any(marker in message for marker in _RETRYABLE_MESSAGE_MARKERS)


def get_retry_after_seconds(error: Exception) -> float | None:
    """
    Extract a Retry-After hint (in seconds) from a provider error, best effort.

    Args:
        error: Exception raised by a provider SDK call.

    Returns:
        Retry delay in seconds when present and numeric, otherwise None.
    """
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        raw = headers.get("retry-after")
    except Exception:
        return None
    if raw is None:
        return None
    try:
        seconds = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return seconds


def compute_backoff_delay(attempt: int, retry_after_seconds: float | None = None) -> float:
    """
    Compute the delay before the next retry attempt.

    Honors an explicit Retry-After hint when available; otherwise applies
    exponential backoff with proportional jitter, capped at
    RETRY_MAX_DELAY_SECONDS.

    Args:
        attempt: 1-based index of the attempt that just failed.
        retry_after_seconds: Optional server-provided retry hint.

    Returns:
        Delay in seconds.
    """
    if retry_after_seconds is not None:
        return min(retry_after_seconds, RETRY_MAX_DELAY_SECONDS)
    base = RETRY_BASE_DELAY_SECONDS * (2 ** max(attempt - 1, 0))
    capped = min(base, RETRY_MAX_DELAY_SECONDS)
    return capped + random.uniform(0, capped / 2)


async def run_with_retry[T](
    provider_name: str,
    operation: Callable[[], Awaitable[T]],
    *,
    operation_name: str = "chat_completion",
    max_attempts: int = RETRY_MAX_ATTEMPTS,
) -> T:
    """
    Execute a provider operation with the unified retry policy.

    Args:
        provider_name: Provider identifier for logging.
        operation: Zero-argument coroutine factory performing the SDK call.
        operation_name: Label used in retry logs.
        max_attempts: Maximum total attempts including the first call.

    Returns:
        The operation result.

    Raises:
        Exception: The last error when attempts are exhausted or the error is
            not retryable.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return await operation()
        except Exception as exc:
            if attempt >= max_attempts or not is_retryable_provider_error(exc):
                raise
            delay = compute_backoff_delay(attempt, get_retry_after_seconds(exc))
            logger.warning(
                "provider_call_retry",
                provider=provider_name,
                operation=operation_name,
                attempt=attempt,
                max_attempts=max_attempts,
                delay_seconds=round(delay, 2),
                error=str(exc)[:200],
            )
            await asyncio.sleep(delay)


async def run_with_provider_resilience[T](
    provider_name: str,
    operation: Callable[[], Awaitable[T]],
    *,
    operation_name: str = "chat_completion",
    max_attempts: int = RETRY_MAX_ATTEMPTS,
) -> T:
    """
    Execute a non-streaming provider operation with concurrency limiting and retry.

    Args:
        provider_name: Provider identifier.
        operation: Zero-argument coroutine factory performing the SDK call.
        operation_name: Label used in retry logs.
        max_attempts: Maximum total attempts including the first call.

    Returns:
        The operation result.
    """
    async with get_provider_semaphore(provider_name):
        return await run_with_retry(
            provider_name,
            operation,
            operation_name=operation_name,
            max_attempts=max_attempts,
        )


__all__ = [
    "PROVIDER_MAX_CONCURRENT_REQUESTS",
    "RETRY_BASE_DELAY_SECONDS",
    "RETRY_MAX_ATTEMPTS",
    "RETRY_MAX_DELAY_SECONDS",
    "compute_backoff_delay",
    "get_provider_semaphore",
    "get_retry_after_seconds",
    "is_retryable_provider_error",
    "run_with_provider_resilience",
    "run_with_retry",
]

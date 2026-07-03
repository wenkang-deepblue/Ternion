"""
Tests for shared provider resilience primitives (retry policy and semaphores).
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from ternion.providers.resilience import (
    PROVIDER_MAX_CONCURRENT_REQUESTS,
    RETRY_MAX_DELAY_SECONDS,
    compute_backoff_delay,
    get_provider_semaphore,
    get_retry_after_seconds,
    is_retryable_provider_error,
    run_with_provider_resilience,
    run_with_retry,
)


class _StatusError(Exception):
    """Test error carrying an HTTP status code like provider SDK exceptions."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class TestRetryClassification:
    """Tests for is_retryable_provider_error."""

    def test_rate_limit_status_is_retryable(self) -> None:
        """HTTP 429 should be classified as retryable."""
        assert is_retryable_provider_error(_StatusError("rate limited", 429)) is True

    def test_overloaded_status_is_retryable(self) -> None:
        """Anthropic 529 overloaded should be classified as retryable."""
        assert is_retryable_provider_error(_StatusError("overloaded", 529)) is True

    def test_server_errors_are_retryable(self) -> None:
        """Transient 5xx statuses should be classified as retryable."""
        for status in (500, 502, 503, 504):
            assert is_retryable_provider_error(_StatusError("server error", status)) is True

    def test_client_errors_are_not_retryable(self) -> None:
        """Explicit client errors must never be retried."""
        for status in (400, 401, 403, 404, 422):
            assert is_retryable_provider_error(_StatusError("client error", status)) is False

    def test_status_takes_precedence_over_message(self) -> None:
        """A 404 with transient-looking text must stay non-retryable."""
        error = _StatusError("model temporarily unavailable", 404)
        assert is_retryable_provider_error(error) is False

    def test_message_markers_without_status(self) -> None:
        """Without a status code, transient message markers drive the decision."""
        assert is_retryable_provider_error(Exception("Connection reset by peer")) is True
        assert is_retryable_provider_error(Exception("Request timed out")) is True
        assert is_retryable_provider_error(Exception("The model is overloaded")) is True
        assert is_retryable_provider_error(Exception("invalid request payload")) is False

    def test_status_from_response_attribute(self) -> None:
        """Status codes nested on error.response should be honored."""
        error = Exception("boom")
        error.response = SimpleNamespace(status_code=503)  # type: ignore[attr-defined]
        assert is_retryable_provider_error(error) is True


class TestRetryAfter:
    """Tests for get_retry_after_seconds."""

    def test_extracts_numeric_retry_after(self) -> None:
        """Numeric retry-after headers should be parsed as seconds."""
        error = Exception("rate limited")
        error.response = SimpleNamespace(headers={"retry-after": "7"})  # type: ignore[attr-defined]
        assert get_retry_after_seconds(error) == 7.0

    def test_returns_none_without_headers(self) -> None:
        """Errors without response headers yield no retry hint."""
        assert get_retry_after_seconds(Exception("boom")) is None

    def test_ignores_non_numeric_values(self) -> None:
        """HTTP-date style retry-after values are ignored."""
        error = Exception("rate limited")
        error.response = SimpleNamespace(  # type: ignore[attr-defined]
            headers={"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}
        )
        assert get_retry_after_seconds(error) is None


class TestBackoffDelay:
    """Tests for compute_backoff_delay."""

    def test_honors_retry_after_hint(self) -> None:
        """An explicit retry-after hint overrides exponential backoff."""
        assert compute_backoff_delay(1, retry_after_seconds=5.0) == 5.0

    def test_retry_after_capped_at_max(self) -> None:
        """Retry-after hints are capped at the maximum delay."""
        assert compute_backoff_delay(1, retry_after_seconds=900.0) == RETRY_MAX_DELAY_SECONDS

    def test_exponential_growth_with_jitter(self) -> None:
        """Backoff grows exponentially with proportional jitter."""
        with patch("ternion.providers.resilience.random.uniform", return_value=0.0):
            assert compute_backoff_delay(1) == 1.0
            assert compute_backoff_delay(2) == 2.0
            assert compute_backoff_delay(3) == 4.0


class TestRunWithRetry:
    """Tests for run_with_retry."""

    @pytest.mark.asyncio
    async def test_succeeds_after_transient_failures(self) -> None:
        """Transient failures should be retried until success."""
        operation = AsyncMock(
            side_effect=[_StatusError("rate limited", 429), _StatusError("overloaded", 529), "ok"]
        )
        with patch("ternion.providers.resilience.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            result = await run_with_retry("openai", operation, max_attempts=3)
        assert result == "ok"
        assert operation.await_count == 3
        assert mock_sleep.await_count == 2

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_immediately(self) -> None:
        """Non-retryable errors must not consume extra attempts."""
        operation = AsyncMock(side_effect=_StatusError("bad request", 400))
        with (
            patch("ternion.providers.resilience.asyncio.sleep", new=AsyncMock()) as mock_sleep,
            pytest.raises(_StatusError),
        ):
            await run_with_retry("openai", operation, max_attempts=3)
        assert operation.await_count == 1
        assert mock_sleep.await_count == 0

    @pytest.mark.asyncio
    async def test_exhausted_attempts_raise_last_error(self) -> None:
        """The final transient error is raised when attempts run out."""
        operation = AsyncMock(side_effect=_StatusError("rate limited", 429))
        with (
            patch("ternion.providers.resilience.asyncio.sleep", new=AsyncMock()),
            pytest.raises(_StatusError),
        ):
            await run_with_retry("openai", operation, max_attempts=2)
        assert operation.await_count == 2


class TestProviderSemaphore:
    """Tests for get_provider_semaphore and run_with_provider_resilience."""

    @pytest.mark.asyncio
    async def test_same_loop_returns_same_semaphore(self) -> None:
        """Repeated lookups within one loop must return the same semaphore."""
        first = get_provider_semaphore("openai")
        second = get_provider_semaphore("openai")
        other = get_provider_semaphore("anthropic")
        assert first is second
        assert first is not other

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self) -> None:
        """No more than the configured number of operations may run at once."""
        active = 0
        peak = 0

        async def operation() -> str:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return "done"

        results = await asyncio.gather(
            *(
                run_with_provider_resilience("google", operation, max_attempts=1)
                for _ in range(PROVIDER_MAX_CONCURRENT_REQUESTS + 3)
            )
        )
        assert all(result == "done" for result in results)
        assert peak <= PROVIDER_MAX_CONCURRENT_REQUESTS

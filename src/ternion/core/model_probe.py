"""
Model availability probe service for control-panel saves.

This module performs low-cost provider-side model metadata checks before
role/model assignments are persisted.
"""

import httpx
import openai as openai_sdk
import structlog
from openai import AsyncOpenAI
from pydantic import BaseModel

try:
    from google import genai
except ImportError:  # pragma: no cover
    genai = None  # type: ignore[assignment]

logger = structlog.get_logger(__name__)

# Lowercase substrings matched against provider error messages for probe classification.
MODEL_UNAVAILABLE_KEYWORDS = (
    "model not found",
    "does not exist",
    "unsupported model",
    "invalid model",
    "not available",
    "has been deprecated",
    "was retired",
    "unknown model",
    "no model was found",
)
TIMEOUT_KEYWORDS = (
    "timeout",
    "timed out",
    "deadline exceeded",
)
CONNECTION_KEYWORDS = (
    "connection error",
    "connection failed",
    "network error",
    "service unavailable",
    "temporarily unavailable",
)


class ModelAvailabilityProbeResult(BaseModel):
    """Result of a provider-side model availability probe."""

    ok: bool
    provider: str
    model: str
    code: str = "SUCCESS"
    message: str = ""
    refresh_suggested: bool = False


def is_model_unavailable_error(provider: str, error_message: str) -> bool:
    """Return whether an error message indicates a retired or missing model.

    Args:
        provider: Reserved for future provider-specific keyword matching.
        error_message: Error text returned by a provider SDK or HTTP client.
    """
    _ = provider
    lowered = error_message.lower()
    return any(keyword in lowered for keyword in MODEL_UNAVAILABLE_KEYWORDS)


class ModelAvailabilityProbeService:
    """Probe provider metadata endpoints before saving model selections."""

    def __init__(self, request_timeout: float = 10.0) -> None:
        """Initialize the probe service.

        Args:
            request_timeout: Timeout in seconds for outbound provider requests.
        """
        self.request_timeout = request_timeout

    async def probe_model(
        self,
        provider: str,
        model: str,
        api_key: str,
    ) -> ModelAvailabilityProbeResult:
        """Probe a specific provider/model pair with a low-cost metadata request."""
        if provider == "openai":
            result = await self._probe_openai_model(api_key=api_key, model=model)
        elif provider == "google":
            result = await self._probe_google_model(api_key=api_key, model=model)
        elif provider == "anthropic":
            result = await self._probe_anthropic_model(api_key=api_key, model=model)
        else:
            raise ValueError(f"Unsupported provider for model probe: {provider}")

        if result.ok:
            logger.info("model_probe_succeeded", provider=provider, model=model)
        else:
            logger.warning(
                "model_probe_failed",
                provider=provider,
                model=model,
                code=result.code,
                refresh_suggested=result.refresh_suggested,
                message=result.message,
            )
        return result

    async def _probe_openai_model(
        self,
        *,
        api_key: str,
        model: str,
    ) -> ModelAvailabilityProbeResult:
        """Probe an OpenAI model via ``GET /v1/models/{model}``."""
        client = AsyncOpenAI(api_key=api_key, timeout=self.request_timeout)
        try:
            await client.models.retrieve(model)
            return self._build_success_result(provider="openai", model=model)
        except Exception as exc:
            return self._classify_probe_exception(provider="openai", model=model, exc=exc)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                try:
                    await close()
                except Exception as close_exc:
                    logger.debug(
                        "model_probe_client_close_failed",
                        provider="openai",
                        model=model,
                        exc_type=type(close_exc).__name__,
                        error=str(close_exc),
                    )

    async def _probe_google_model(
        self,
        *,
        api_key: str,
        model: str,
    ) -> ModelAvailabilityProbeResult:
        """Probe a Google model via ``models.get()``."""
        if genai is None:  # pragma: no cover
            return self._build_failure_result(
                provider="google",
                model=model,
                code="MODEL_PROBE_CONNECTION_ERROR",
                message="Google GenAI SDK is not installed.",
            )

        client = genai.Client(api_key=api_key)
        try:
            await client.aio.models.get(model=self._normalize_google_model_name(model))
            return self._build_success_result(provider="google", model=model)
        except Exception as exc:
            return self._classify_probe_exception(provider="google", model=model, exc=exc)
        finally:
            aio_client = getattr(client, "aio", None)
            aclose = getattr(aio_client, "aclose", None)
            if callable(aclose):
                try:
                    await aclose()
                except Exception as close_exc:
                    logger.debug(
                        "model_probe_client_close_failed",
                        provider="google",
                        model=model,
                        exc_type=type(close_exc).__name__,
                        error=str(close_exc),
                    )

    async def _probe_anthropic_model(
        self,
        *,
        api_key: str,
        model: str,
    ) -> ModelAvailabilityProbeResult:
        """Probe an Anthropic model via ``GET /v1/models/{model}``."""
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                response = await client.get(
                    f"https://api.anthropic.com/v1/models/{model}",
                    headers=headers,
                )
                response.raise_for_status()
            return self._build_success_result(provider="anthropic", model=model)
        except Exception as exc:
            return self._classify_probe_exception(provider="anthropic", model=model, exc=exc)

    def _classify_probe_exception(
        self,
        *,
        provider: str,
        model: str,
        exc: Exception,
    ) -> ModelAvailabilityProbeResult:
        """Map provider/SDK exceptions to stable control-panel error codes."""
        message = self._extract_error_message(exc)
        status_code = self._extract_status_code(exc)

        if self._is_timeout_error(exc, message):
            return self._build_failure_result(
                provider=provider,
                model=model,
                code="MODEL_PROBE_TIMEOUT",
                message=message,
            )

        if status_code in {401, 403}:
            return self._build_failure_result(
                provider=provider,
                model=model,
                code="MODEL_PROBE_AUTH_ERROR",
                message=message,
            )

        if status_code == 404 or is_model_unavailable_error(provider, message):
            return self._build_failure_result(
                provider=provider,
                model=model,
                code="MODEL_UNAVAILABLE",
                message=message,
                refresh_suggested=True,
            )

        if status_code is not None and 500 <= status_code < 600:
            return self._build_failure_result(
                provider=provider,
                model=model,
                code="MODEL_PROBE_CONNECTION_ERROR",
                message=message,
            )

        if self._is_connection_error(exc, message):
            return self._build_failure_result(
                provider=provider,
                model=model,
                code="MODEL_PROBE_CONNECTION_ERROR",
                message=message,
            )

        logger.exception(
            "model_probe_unclassified_exception",
            provider=provider,
            model=model,
            exc_type=type(exc).__name__,
            message=message,
        )
        # Unclassified failures degrade to a connection-style error for the control panel.
        return self._build_failure_result(
            provider=provider,
            model=model,
            code="MODEL_PROBE_CONNECTION_ERROR",
            message=message,
        )

    @staticmethod
    def _build_success_result(provider: str, model: str) -> ModelAvailabilityProbeResult:
        """Build a successful probe result."""
        return ModelAvailabilityProbeResult(
            ok=True,
            provider=provider,
            model=model,
            code="SUCCESS",
        )

    @staticmethod
    def _build_failure_result(
        *,
        provider: str,
        model: str,
        code: str,
        message: str,
        refresh_suggested: bool = False,
    ) -> ModelAvailabilityProbeResult:
        """Build a failed probe result."""
        return ModelAvailabilityProbeResult(
            ok=False,
            provider=provider,
            model=model,
            code=code,
            message=message,
            refresh_suggested=refresh_suggested,
        )

    @staticmethod
    def _normalize_google_model_name(model: str) -> str:
        """Normalize a Gemini model ID into the resource format expected by ``models.get``."""
        if model.startswith("models/"):
            return model
        return f"models/{model}"

    @staticmethod
    def _extract_error_message(exc: Exception) -> str:
        """Extract a stable human-readable message from an exception."""
        message = getattr(exc, "message", None)
        if isinstance(message, str) and message.strip():
            return message.strip()

        text = str(exc).strip()
        if text:
            return text
        return type(exc).__name__

    @staticmethod
    def _extract_status_code(exc: Exception) -> int | None:
        """Extract an HTTP-like status code from SDK or HTTP exceptions."""
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int):
            return status_code

        # Some SDKs expose HTTP-like statuses on `.code` instead of `.status_code`.
        code = getattr(exc, "code", None)
        if isinstance(code, int) and 100 <= code <= 599:
            return code

        response = getattr(exc, "response", None)
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status

        return None

    @staticmethod
    def _is_timeout_error(exc: Exception, message: str) -> bool:
        """Return whether an exception represents a timeout."""
        timeout_error_cls = getattr(openai_sdk, "APITimeoutError", None)
        if timeout_error_cls is not None and isinstance(exc, timeout_error_cls):
            return True
        if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
            return True
        lowered = message.lower()
        return any(keyword in lowered for keyword in TIMEOUT_KEYWORDS)

    @staticmethod
    def _is_connection_error(exc: Exception, message: str) -> bool:
        """Return whether an exception represents a transport or availability failure."""
        connection_error_cls = getattr(openai_sdk, "APIConnectionError", None)
        if connection_error_cls is not None and isinstance(exc, connection_error_cls):
            return True
        if isinstance(exc, (httpx.NetworkError, httpx.ConnectError)):
            return True
        lowered = message.lower()
        return any(keyword in lowered for keyword in CONNECTION_KEYWORDS)


model_availability_probe_service = ModelAvailabilityProbeService()

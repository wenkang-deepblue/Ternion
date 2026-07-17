"""
Tests for provider-side model availability probing.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ternion.core.exceptions import RuntimeModelUnavailableError
from ternion.core.model_probe import (
    ModelAvailabilityProbeService,
    classify_runtime_model_unavailable,
    is_model_unavailable_error,
)
from ternion.utils.model_ids import normalize_anthropic_model_id_for_api

ASYNC_OPENAI_PATCH = "ternion.core.model_probe.AsyncOpenAI"
GENAI_CLIENT_PATCH = "ternion.core.model_probe.genai.Client"
HTTPX_ASYNC_CLIENT_PATCH = "ternion.core.model_probe.httpx.AsyncClient"


class FakeProbeError(Exception):
    """Simple exception carrying provider-like status metadata."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _build_http_status_error(status_code: int, message: str) -> httpx.HTTPStatusError:
    """Create an ``HTTPStatusError`` with a response status code."""
    request = httpx.Request("GET", "https://api.anthropic.com/v1/models/example")
    response = httpx.Response(status_code=status_code, request=request)
    return httpx.HTTPStatusError(message, request=request, response=response)


class TestModelAvailabilityProbeService:
    """Tests for provider-side model availability probing."""

    def test_normalize_anthropic_model_id_for_api_latest_snapshot(self) -> None:
        """Claude 4.6+ snapshot IDs should normalize to Anthropic's canonical API IDs."""
        assert normalize_anthropic_model_id_for_api("claude-opus-4-6-20260205") == "claude-opus-4-6"
        assert (
            normalize_anthropic_model_id_for_api("claude-sonnet-4-6-20260217")
            == "claude-sonnet-4-6"
        )
        assert (
            normalize_anthropic_model_id_for_api("claude-sonnet-4-5-20250929")
            == "claude-sonnet-4-5-20250929"
        )

    async def test_probe_openai_model_success(self) -> None:
        """OpenAI probe should succeed when ``models.retrieve`` returns normally."""
        service = ModelAvailabilityProbeService(request_timeout=7.0)
        mock_client = MagicMock()
        mock_client.models.retrieve = AsyncMock(return_value={"id": "gpt-5.2-2025-12-11"})
        mock_client.close = AsyncMock()

        with patch(ASYNC_OPENAI_PATCH, return_value=mock_client) as mock_ctor:
            result = await service.probe_model(
                provider="openai",
                model="gpt-5.2-2025-12-11",
                api_key="sk-test",
            )

        assert result.ok is True
        assert result.code == "SUCCESS"
        mock_ctor.assert_called_once_with(api_key="sk-test", timeout=7.0)
        mock_client.models.retrieve.assert_awaited_once_with("gpt-5.2-2025-12-11")
        mock_client.close.assert_awaited_once()

    async def test_probe_openai_model_maps_404_to_model_unavailable(self) -> None:
        """OpenAI probe should map 404 to ``MODEL_UNAVAILABLE``."""
        service = ModelAvailabilityProbeService()
        mock_client = MagicMock()
        mock_client.models.retrieve = AsyncMock(
            side_effect=FakeProbeError("model not found", status_code=404)
        )
        mock_client.close = AsyncMock()

        with patch(ASYNC_OPENAI_PATCH, return_value=mock_client):
            result = await service.probe_model(
                provider="openai",
                model="gpt-5.2-2025-12-11",
                api_key="sk-test",
            )

        assert result.ok is False
        assert result.code == "MODEL_UNAVAILABLE"
        assert result.refresh_suggested is True

    async def test_probe_openai_model_maps_401_to_auth_error(self) -> None:
        """OpenAI probe should map 401/403 to ``MODEL_PROBE_AUTH_ERROR``."""
        service = ModelAvailabilityProbeService()
        mock_client = MagicMock()
        mock_client.models.retrieve = AsyncMock(
            side_effect=FakeProbeError("unauthorized", status_code=401)
        )
        mock_client.close = AsyncMock()

        with patch(ASYNC_OPENAI_PATCH, return_value=mock_client):
            result = await service.probe_model(
                provider="openai",
                model="gpt-5.2-2025-12-11",
                api_key="sk-test",
            )

        assert result.ok is False
        assert result.code == "MODEL_PROBE_AUTH_ERROR"
        assert result.refresh_suggested is False

    async def test_probe_google_model_success(self) -> None:
        """Google probe should call ``models.get`` with the resource name."""
        service = ModelAvailabilityProbeService()
        mock_client = MagicMock()
        mock_client.aio.models.get = AsyncMock(return_value={"name": "models/gemini-3-pro"})
        mock_client.aio.aclose = AsyncMock()

        with patch(GENAI_CLIENT_PATCH, return_value=mock_client) as mock_ctor:
            result = await service.probe_model(
                provider="google",
                model="gemini-3-pro",
                api_key="google-key",
            )

        assert result.ok is True
        assert result.code == "SUCCESS"
        mock_ctor.assert_called_once_with(api_key="google-key")
        mock_client.aio.models.get.assert_awaited_once_with(model="models/gemini-3-pro")
        mock_client.aio.aclose.assert_awaited_once()

    async def test_probe_google_model_maps_404_to_model_unavailable(self) -> None:
        """Google probe should map missing-model responses to ``MODEL_UNAVAILABLE``."""
        service = ModelAvailabilityProbeService()
        mock_client = MagicMock()
        mock_client.aio.models.get = AsyncMock(
            side_effect=FakeProbeError("model not found", code=404)
        )
        mock_client.aio.aclose = AsyncMock()

        with patch(GENAI_CLIENT_PATCH, return_value=mock_client):
            result = await service.probe_model(
                provider="google",
                model="gemini-3-pro",
                api_key="google-key",
            )

        assert result.ok is False
        assert result.code == "MODEL_UNAVAILABLE"
        assert result.refresh_suggested is True

    async def test_probe_google_model_maps_401_to_auth_error(self) -> None:
        """Google probe should map auth failures to ``MODEL_PROBE_AUTH_ERROR``."""
        service = ModelAvailabilityProbeService()
        mock_client = MagicMock()
        mock_client.aio.models.get = AsyncMock(
            side_effect=FakeProbeError("permission denied", code=403)
        )
        mock_client.aio.aclose = AsyncMock()

        with patch(GENAI_CLIENT_PATCH, return_value=mock_client):
            result = await service.probe_model(
                provider="google",
                model="gemini-3-pro",
                api_key="google-key",
            )

        assert result.ok is False
        assert result.code == "MODEL_PROBE_AUTH_ERROR"

    async def test_probe_anthropic_model_success(self) -> None:
        """Anthropic probe should succeed on an HTTP 200 metadata lookup."""
        service = ModelAvailabilityProbeService(request_timeout=9.0)
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client
        mock_context.__aexit__.return_value = None

        with patch(HTTPX_ASYNC_CLIENT_PATCH, return_value=mock_context) as mock_ctor:
            result = await service.probe_model(
                provider="anthropic",
                model="claude-sonnet-4-5-20250929",
                api_key="anthropic-key",
            )

        assert result.ok is True
        assert result.code == "SUCCESS"
        mock_ctor.assert_called_once_with(timeout=9.0)
        mock_client.get.assert_awaited_once()
        _, kwargs = mock_client.get.await_args
        assert kwargs["headers"]["x-api-key"] == "anthropic-key"

    async def test_probe_anthropic_model_normalizes_latest_snapshot_id(self) -> None:
        """Anthropic probe should call the API with the canonical 4.6+ model ID."""
        service = ModelAvailabilityProbeService()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client
        mock_context.__aexit__.return_value = None

        with patch(HTTPX_ASYNC_CLIENT_PATCH, return_value=mock_context):
            result = await service.probe_model(
                provider="anthropic",
                model="claude-opus-4-6-20260205",
                api_key="anthropic-key",
            )

        assert result.ok is True
        args, _ = mock_client.get.await_args
        assert args[0] == "https://api.anthropic.com/v1/models/claude-opus-4-6"

    async def test_probe_anthropic_model_prefers_catalog_api_model_id(self) -> None:
        """Anthropic probe should prefer catalog-derived API IDs over raw source keys."""
        service = ModelAvailabilityProbeService()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client
        mock_context.__aexit__.return_value = None
        catalog_model = MagicMock(
            provider="anthropic",
            id="claude-opus-4-8",
            api_model_id="claude-opus-4-8",
        )

        with (
            patch(HTTPX_ASYNC_CLIENT_PATCH, return_value=mock_context),
            patch("ternion.core.model_probe.model_catalog_service") as mock_catalog_service,
        ):
            mock_catalog_service.get_model_cached.return_value = catalog_model
            result = await service.probe_model(
                provider="anthropic",
                model="claude-opus-4-8-source",
                api_key="anthropic-key",
            )

        assert result.ok is True
        args, _ = mock_client.get.await_args
        assert args[0] == "https://api.anthropic.com/v1/models/claude-opus-4-8"

    async def test_probe_anthropic_model_maps_404_to_model_unavailable(self) -> None:
        """Anthropic probe should map 404 responses to ``MODEL_UNAVAILABLE``."""
        service = ModelAvailabilityProbeService()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = FakeProbeError(
            "model not found",
            status_code=404,
        )
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client
        mock_context.__aexit__.return_value = None

        with patch(HTTPX_ASYNC_CLIENT_PATCH, return_value=mock_context):
            result = await service.probe_model(
                provider="anthropic",
                model="claude-sonnet-4-5-20250929",
                api_key="anthropic-key",
            )

        assert result.ok is False
        assert result.code == "MODEL_UNAVAILABLE"
        assert result.refresh_suggested is True

    async def test_probe_anthropic_model_maps_401_to_auth_error(self) -> None:
        """Anthropic probe should map auth failures to ``MODEL_PROBE_AUTH_ERROR``."""
        service = ModelAvailabilityProbeService()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = _build_http_status_error(401, "unauthorized")
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client
        mock_context.__aexit__.return_value = None

        with patch(HTTPX_ASYNC_CLIENT_PATCH, return_value=mock_context):
            result = await service.probe_model(
                provider="anthropic",
                model="claude-sonnet-4-5-20250929",
                api_key="anthropic-key",
            )

        assert result.ok is False
        assert result.code == "MODEL_PROBE_AUTH_ERROR"

    async def test_probe_anthropic_model_404_falls_back_to_chat_and_succeeds(self) -> None:
        """Anthropic probe should accept a model when metadata 404s but chat succeeds."""
        service = ModelAvailabilityProbeService()

        mock_client = MagicMock()
        mock_meta_response = MagicMock()
        mock_meta_response.raise_for_status.side_effect = _build_http_status_error(404, "not found")
        mock_chat_response = MagicMock()
        mock_chat_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_meta_response)
        mock_client.post = AsyncMock(return_value=mock_chat_response)

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client
        mock_context.__aexit__.return_value = None

        with patch(HTTPX_ASYNC_CLIENT_PATCH, return_value=mock_context):
            result = await service.probe_model(
                provider="anthropic",
                model="claude-opus-4-6-20260205",
                api_key="anthropic-key",
            )

        assert result.ok is True
        assert result.code == "SUCCESS"

    async def test_probe_anthropic_model_404_falls_back_to_chat_and_fails(self) -> None:
        """Anthropic probe should report unavailable when both metadata and chat fail."""
        service = ModelAvailabilityProbeService()

        mock_client = MagicMock()
        mock_meta_response = MagicMock()
        mock_meta_response.raise_for_status.side_effect = _build_http_status_error(404, "not found")
        mock_client.get = AsyncMock(return_value=mock_meta_response)
        mock_client.post = AsyncMock(side_effect=FakeProbeError("model not found", status_code=404))

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client
        mock_context.__aexit__.return_value = None

        with patch(HTTPX_ASYNC_CLIENT_PATCH, return_value=mock_context):
            result = await service.probe_model(
                provider="anthropic",
                model="claude-opus-4-6-20260205",
                api_key="anthropic-key",
            )

        assert result.ok is False
        assert result.code == "MODEL_UNAVAILABLE"
        assert result.refresh_suggested is True

    async def test_probe_openai_model_maps_timeout_to_timeout_error(self) -> None:
        """OpenAI probe should map timeout exceptions to ``MODEL_PROBE_TIMEOUT``."""
        service = ModelAvailabilityProbeService()

        timeout_client = MagicMock()
        timeout_client.models.retrieve = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))
        timeout_client.close = AsyncMock()

        with patch(ASYNC_OPENAI_PATCH, return_value=timeout_client):
            timeout_result = await service.probe_model(
                provider="openai",
                model="gpt-5.2-2025-12-11",
                api_key="sk-test",
            )

        assert timeout_result.code == "MODEL_PROBE_TIMEOUT"

    async def test_probe_openai_model_maps_connection_error(self) -> None:
        """OpenAI probe should map transport failures to connection errors."""
        service = ModelAvailabilityProbeService()
        connection_client = MagicMock()
        connection_client.models.retrieve = AsyncMock(
            side_effect=httpx.ConnectError("network error")
        )
        connection_client.close = AsyncMock()

        with patch(ASYNC_OPENAI_PATCH, return_value=connection_client):
            connection_result = await service.probe_model(
                provider="openai",
                model="gpt-5.2-2025-12-11",
                api_key="sk-test",
            )

        assert connection_result.code == "MODEL_PROBE_CONNECTION_ERROR"

    async def test_probe_openai_model_maps_5xx_to_connection_error(self) -> None:
        """OpenAI probe should map provider 5xx responses to connection errors."""
        service = ModelAvailabilityProbeService()
        mock_client = MagicMock()
        mock_client.models.retrieve = AsyncMock(
            side_effect=FakeProbeError("service unavailable", status_code=503)
        )
        mock_client.close = AsyncMock()

        with patch(ASYNC_OPENAI_PATCH, return_value=mock_client):
            result = await service.probe_model(
                provider="openai",
                model="gpt-5.2-2025-12-11",
                api_key="sk-test",
            )

        assert result.ok is False
        assert result.code == "MODEL_PROBE_CONNECTION_ERROR"

    async def test_probe_openai_model_maps_keyword_only_unavailable(self) -> None:
        """OpenAI probe should map keyword-only unavailable messages to 404-style failures."""
        service = ModelAvailabilityProbeService()
        mock_client = MagicMock()
        mock_client.models.retrieve = AsyncMock(
            side_effect=Exception("The requested model does not exist")
        )
        mock_client.close = AsyncMock()

        with patch(ASYNC_OPENAI_PATCH, return_value=mock_client):
            result = await service.probe_model(
                provider="openai",
                model="gpt-5.2-2025-12-11",
                api_key="sk-test",
            )

        assert result.ok is False
        assert result.code == "MODEL_UNAVAILABLE"
        assert result.refresh_suggested is True

    async def test_probe_openai_model_maps_generic_exception_to_connection_error(self) -> None:
        """OpenAI probe should map unexpected generic exceptions to connection errors."""
        service = ModelAvailabilityProbeService()
        mock_client = MagicMock()
        mock_client.models.retrieve = AsyncMock(side_effect=RuntimeError("unexpected failure"))
        mock_client.close = AsyncMock()

        with patch(ASYNC_OPENAI_PATCH, return_value=mock_client):
            result = await service.probe_model(
                provider="openai",
                model="gpt-5.2-2025-12-11",
                api_key="sk-test",
            )

        assert result.ok is False
        assert result.code == "MODEL_PROBE_CONNECTION_ERROR"

    async def test_probe_google_model_keeps_prefixed_model_name(self) -> None:
        """Google probe should not add a second ``models/`` prefix."""
        service = ModelAvailabilityProbeService()
        mock_client = MagicMock()
        mock_client.aio.models.get = AsyncMock(return_value={"name": "models/gemini-3-pro"})
        mock_client.aio.aclose = AsyncMock()

        with patch(GENAI_CLIENT_PATCH, return_value=mock_client):
            result = await service.probe_model(
                provider="google",
                model="models/gemini-3-pro",
                api_key="google-key",
            )

        assert result.ok is True
        mock_client.aio.models.get.assert_awaited_once_with(model="models/gemini-3-pro")

    async def test_probe_model_raises_for_unsupported_provider(self) -> None:
        """Unsupported providers should fail fast instead of returning a probe result."""
        service = ModelAvailabilityProbeService()

        with pytest.raises(ValueError, match="Unsupported provider"):
            await service.probe_model(provider="unknown", model="test-model", api_key="sk-test")

    def test_is_model_unavailable_error_matches_common_retirement_messages(self) -> None:
        """Fallback unavailable detection should recognize common provider phrases."""
        assert is_model_unavailable_error("openai", "This model was retired yesterday") is True
        assert is_model_unavailable_error("openai", "provider temporarily unavailable") is False

    def test_classify_runtime_model_unavailable_maps_404(self) -> None:
        """Runtime classification should map HTTP 404 to a structured stale-model error."""
        error = classify_runtime_model_unavailable(
            provider="openai",
            model="gpt-5.4",
            exc=FakeProbeError("model not found", status_code=404),
        )

        assert isinstance(error, RuntimeModelUnavailableError)
        assert error.provider == "openai"
        assert error.model == "gpt-5.4"
        assert error.provider_message == "model not found"

    def test_classify_runtime_model_unavailable_maps_keyword_only_error(self) -> None:
        """Runtime classification should fall back to message matching when no status exists."""
        error = classify_runtime_model_unavailable(
            provider="openai",
            model="gpt-5.4",
            exc=Exception("The requested model does not exist"),
        )

        assert isinstance(error, RuntimeModelUnavailableError)
        assert error.model == "gpt-5.4"

    def test_classify_runtime_model_unavailable_skips_transient_status_codes(self) -> None:
        """Runtime classification should not turn transient provider failures into stale models."""
        error = classify_runtime_model_unavailable(
            provider="openai",
            model="gpt-5.4",
            exc=FakeProbeError("service temporarily not available", status_code=503),
        )

        assert error is None

    def test_classify_runtime_model_unavailable_returns_none_for_generic_error(self) -> None:
        """Runtime classification should ignore unrelated generic exceptions."""
        error = classify_runtime_model_unavailable(
            provider="openai",
            model="gpt-5.4",
            exc=RuntimeError("unexpected failure"),
        )

        assert error is None

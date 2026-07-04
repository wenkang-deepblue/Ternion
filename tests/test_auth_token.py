"""
Tests for bearer-token authentication on publicly exposed endpoints (Phase C5).

Covers:
- Path protection classification
- Local direct request exemption
- Tunneled (forwarded) requests requiring the installation token
- Token generation and persistence
- The /api/auth-token endpoint
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ternion.core.config_store import ConfigStore
from ternion.server.app import app
from ternion.server.auth import is_protected_path

FORWARDED = {"x-forwarded-for": "203.0.113.7", "x-forwarded-proto": "https"}


class TestProtectedPathClassification:
    """Only the OpenAI-compatible API and /api require authentication."""

    @pytest.mark.parametrize(
        "path",
        [
            "/chat/completions",
            "/responses",
            "/models",
            "/v1/chat/completions",
            "/v1/models",
            "/v1/v1/chat/completions",
            "/api/config",
            "/api/ports",
            "/api/api-keys/add",
        ],
    )
    def test_protected_paths(self, path):
        assert is_protected_path(path, "POST") is True

    @pytest.mark.parametrize(
        "path",
        [
            "/",
            "/health",
            "/v1",
            "/v1/",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/panel",
            "/panel/assets/app.js",
        ],
    )
    def test_exempt_paths(self, path):
        assert is_protected_path(path, "GET") is False

    def test_options_preflight_always_exempt(self):
        assert is_protected_path("/v1/chat/completions", "OPTIONS") is False


class TestAuthMiddleware:
    """Tunneled requests need the token; local direct requests do not."""

    def _client(self) -> TestClient:
        return TestClient(app)

    def test_local_direct_request_passes_without_token(self):
        # TestClient has no forwarding headers -> treated as local direct.
        response = self._client().get("/api/ports")
        assert response.status_code == 200

    def test_forwarded_request_without_token_rejected(self):
        mock_config = MagicMock()
        mock_config.auth_token = "secret-token"
        with patch("ternion.server.auth.config_store") as mock_store:
            mock_store.load.return_value = mock_config
            response = self._client().get("/api/ports", headers=FORWARDED)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_api_key"

    def test_forwarded_request_with_wrong_token_rejected(self):
        mock_config = MagicMock()
        mock_config.auth_token = "secret-token"
        with patch("ternion.server.auth.config_store") as mock_store:
            mock_store.load.return_value = mock_config
            response = self._client().get(
                "/api/ports",
                headers={**FORWARDED, "Authorization": "Bearer wrong"},
            )
        assert response.status_code == 401

    def test_forwarded_request_with_valid_token_passes(self):
        mock_config = MagicMock()
        mock_config.auth_token = "secret-token"
        with patch("ternion.server.auth.config_store") as mock_store:
            mock_store.load.return_value = mock_config
            response = self._client().get(
                "/api/ports",
                headers={**FORWARDED, "Authorization": "Bearer secret-token"},
            )
        assert response.status_code == 200

    def test_forwarded_request_rejected_when_no_token_configured(self):
        # Empty token means nothing can match: fail closed for tunneled calls.
        mock_config = MagicMock()
        mock_config.auth_token = ""
        with patch("ternion.server.auth.config_store") as mock_store:
            mock_store.load.return_value = mock_config
            response = self._client().get(
                "/api/ports",
                headers={**FORWARDED, "Authorization": "Bearer anything"},
            )
        assert response.status_code == 401

    def test_forwarded_health_probe_stays_public(self):
        response = self._client().get("/health", headers=FORWARDED)
        assert response.status_code == 200

    def test_forwarded_v1_chat_requires_token(self):
        mock_config = MagicMock()
        mock_config.auth_token = "secret-token"
        with patch("ternion.server.auth.config_store") as mock_store:
            mock_store.load.return_value = mock_config
            response = self._client().post(
                "/v1/chat/completions",
                json={"model": "ternion-team", "messages": [{"role": "user", "content": "hi"}]},
                headers=FORWARDED,
            )
        assert response.status_code == 401


class TestTokenLifecycle:
    """The token is generated once and persisted with the config."""

    def test_ensure_auth_token_generates_and_persists(self, tmp_path):
        store = ConfigStore(config_path=tmp_path / "config.json")
        token = store.ensure_auth_token()
        assert len(token) >= 32
        # Second call returns the same token without regenerating.
        assert store.ensure_auth_token() == token
        # Persisted to disk.
        reloaded = ConfigStore(config_path=tmp_path / "config.json")
        assert reloaded.load().auth_token == token

    def test_auth_token_not_in_safe_dict(self, tmp_path):
        store = ConfigStore(config_path=tmp_path / "config.json")
        store.ensure_auth_token()
        assert "auth_token" not in store.to_safe_dict()

    def test_auth_token_endpoint_returns_token(self):
        with patch("ternion.server.control_routes.config_store") as mock_store:
            mock_store.ensure_auth_token.return_value = "endpoint-token"
            response = TestClient(app).get("/api/auth-token")
        assert response.status_code == 200
        assert response.json() == {"auth_token": "endpoint-token"}

    def test_auth_token_endpoint_protected_from_tunnel(self):
        mock_config = MagicMock()
        mock_config.auth_token = "secret-token"
        with patch("ternion.server.auth.config_store") as mock_store:
            mock_store.load.return_value = mock_config
            response = TestClient(app).get("/api/auth-token", headers=FORWARDED)
        assert response.status_code == 401

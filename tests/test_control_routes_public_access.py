"""Tests for public-access control-panel routes."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from ternion.core.config_store import UserConfig
from ternion.server.app import app

CONTROL_ROUTES_CONFIG_STORE = "ternion.server.control_routes.config_store"
CONTROL_ROUTES_LOG_MANAGER = "ternion.server.control_routes.log_manager"


def test_get_public_access_prefers_configured_url() -> None:
    """Configured public URLs should win over request-origin detection."""
    config = UserConfig()
    config.public_access.mode = "local_tunnel"
    config.public_access.public_base_url = "https://configured.example/v1"

    with patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store:
        mock_config_store.load.return_value = config

        client = TestClient(app)
        response = client.get(
            "/api/public-access",
            headers={
                "x-forwarded-proto": "https",
                "x-forwarded-host": "service-abc.run.app",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "mode": "local_tunnel",
        "configured_public_base_url": "https://configured.example",
        "effective_public_base_url": "https://configured.example",
        "effective_source": "config",
        "cursor_override_base_url": "https://configured.example",
        "configured": True,
        "requires_public_url": True,
    }


def test_get_public_access_uses_forwarded_public_origin_when_config_missing() -> None:
    """Cloud Run-style forwarded headers should produce an effective public base URL."""
    with patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store:
        mock_config_store.load.return_value = UserConfig()

        client = TestClient(app)
        response = client.get(
            "/api/public-access",
            headers={
                "x-forwarded-proto": "https",
                "x-forwarded-host": "ternion-service-abc.run.app",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "mode": "none",
        "configured_public_base_url": "",
        "effective_public_base_url": "https://ternion-service-abc.run.app",
        "effective_source": "request_origin",
        "cursor_override_base_url": "https://ternion-service-abc.run.app",
        "configured": True,
        "requires_public_url": True,
    }


def test_get_public_access_ignores_local_request_origin() -> None:
    """Local request origins should not be treated as public-access URLs."""
    with patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store:
        mock_config_store.load.return_value = UserConfig()

        client = TestClient(app)
        response = client.get(
            "/api/public-access",
            headers={
                "x-forwarded-proto": "http",
                "x-forwarded-host": "127.0.0.1:9110",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "mode": "none",
        "configured_public_base_url": "",
        "effective_public_base_url": "",
        "effective_source": "none",
        "cursor_override_base_url": "",
        "configured": False,
        "requires_public_url": True,
    }


def test_update_public_access_saves_canonicalized_public_url() -> None:
    """POST should persist normalized public-access values and return effective state."""
    config = UserConfig()

    with (
        patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
        patch(CONTROL_ROUTES_LOG_MANAGER) as mock_log_manager,
    ):
        mock_config_store.load.return_value = config

        client = TestClient(app)
        response = client.post(
            "/api/public-access",
            json={
                "mode": "local_tunnel",
                "public_base_url": "https://configured.example/v1/",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "mode": "local_tunnel",
        "configured_public_base_url": "https://configured.example",
        "effective_public_base_url": "https://configured.example",
        "effective_source": "config",
        "cursor_override_base_url": "https://configured.example",
        "configured": True,
        "requires_public_url": True,
    }
    assert config.public_access.mode == "local_tunnel"
    assert config.public_access.public_base_url == "https://configured.example"
    mock_config_store.save.assert_called_once_with(config)
    mock_log_manager.emit.assert_called_once()


def test_update_public_access_partial_mode_only_preserves_url() -> None:
    """Sending only `mode` should preserve the existing public base URL."""
    config = UserConfig()
    config.public_access.mode = "none"
    config.public_access.public_base_url = "https://existing.example"

    with (
        patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
        patch(CONTROL_ROUTES_LOG_MANAGER),
    ):
        mock_config_store.load.return_value = config

        client = TestClient(app)
        response = client.post(
            "/api/public-access",
            json={"mode": "cloud_run"},
        )

    assert response.status_code == 200
    assert config.public_access.mode == "cloud_run"
    assert config.public_access.public_base_url == "https://existing.example"
    assert response.json()["configured_public_base_url"] == "https://existing.example"


def test_update_public_access_partial_url_only_preserves_mode() -> None:
    """Sending only `public_base_url` should preserve the existing mode."""
    config = UserConfig()
    config.public_access.mode = "custom"
    config.public_access.public_base_url = "https://existing.example"

    with (
        patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
        patch(CONTROL_ROUTES_LOG_MANAGER),
    ):
        mock_config_store.load.return_value = config

        client = TestClient(app)
        response = client.post(
            "/api/public-access",
            json={"public_base_url": "https://new.example/v1"},
        )

    assert response.status_code == 200
    assert config.public_access.mode == "custom"
    assert config.public_access.public_base_url == "https://new.example"
    assert response.json()["mode"] == "custom"
    assert response.json()["configured_public_base_url"] == "https://new.example"


def test_update_public_access_rejects_invalid_mode() -> None:
    """POST should reject unsupported public-access modes."""
    with patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store:
        mock_config_store.load.return_value = UserConfig()

        client = TestClient(app)
        response = client.post(
            "/api/public-access",
            json={"mode": "invalid-mode"},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "INVALID_PUBLIC_ACCESS_MODE"}


def test_update_public_access_rejects_invalid_public_base_url() -> None:
    """POST should reject malformed public base URLs instead of silently clearing them."""
    with patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store:
        mock_config_store.load.return_value = UserConfig()

        client = TestClient(app)
        response = client.post(
            "/api/public-access",
            json={"public_base_url": "not-a-url"},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "INVALID_PUBLIC_BASE_URL"}

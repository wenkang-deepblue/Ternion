"""Tests for public-access control-panel routes."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ternion.core.config_store import UserConfig
from ternion.server.app import app

CONTROL_ROUTES_CONFIG_STORE = "ternion.server.control_routes.config_store"
CONTROL_ROUTES_LOG_MANAGER = "ternion.server.control_routes.log_manager"
PUBLIC_ACCESS_NGROK_DETECT = "ternion.core.public_access.detect_ngrok_public_base_url"


@pytest.fixture(autouse=True)
def _exempt_auth_for_detection_tests():
    """
    Treat every request in this module as a local direct request.

    These tests simulate tunneled origins via forwarded headers to exercise
    public-access detection; bearer-token authentication for such requests
    is covered separately in test_auth_token.py.
    """
    with patch("ternion.server.auth.is_local_direct_request", return_value=True):
        yield


def test_get_public_access_local_request_origin_beats_configured_url() -> None:
    """In local mode, a live public request origin should beat saved config."""
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
        "deployment_environment": "local",
        "detection_method": "request_origin",
        "detected_public_base_url": "https://service-abc.run.app",
        "configured_public_base_url": "https://configured.example",
        "effective_public_base_url": "https://service-abc.run.app",
        "effective_source": "request_origin",
        "cursor_override_base_url": "https://service-abc.run.app",
        "configured": True,
        "requires_public_url": True,
    }


def test_get_public_access_local_uses_ngrok_detection_when_request_origin_missing() -> None:
    """Local mode should use ngrok auto-discovery when no public request origin exists."""
    config = UserConfig()
    config.public_access.mode = "local_tunnel"
    config.public_access.public_base_url = "https://demo.ngrok.app/v1"

    with (
        patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
        patch(PUBLIC_ACCESS_NGROK_DETECT, return_value=("https://live.ngrok.app", "ngrok_api")),
    ):
        mock_config_store.load.return_value = config

        client = TestClient(app)
        response = client.get(
            "/api/public-access",
            headers={
                "x-forwarded-proto": "http",
                "x-forwarded-host": "127.0.0.1:9120",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "mode": "local_tunnel",
        "deployment_environment": "local",
        "detection_method": "ngrok_api",
        "detected_public_base_url": "https://live.ngrok.app",
        "configured_public_base_url": "https://demo.ngrok.app",
        "effective_public_base_url": "https://live.ngrok.app",
        "effective_source": "ngrok_api",
        "cursor_override_base_url": "https://live.ngrok.app",
        "configured": True,
        "requires_public_url": True,
    }


def test_get_public_access_local_falls_back_to_config_when_ngrok_missing() -> None:
    """Local mode should fall back to saved config when ngrok auto-discovery fails."""
    config = UserConfig()
    config.public_access.mode = "local_tunnel"
    config.public_access.public_base_url = "https://demo.ngrok.app/v1"

    with (
        patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
        patch(PUBLIC_ACCESS_NGROK_DETECT, return_value=("", "none")),
    ):
        mock_config_store.load.return_value = config

        client = TestClient(app)
        response = client.get(
            "/api/public-access",
            headers={
                "x-forwarded-proto": "http",
                "x-forwarded-host": "127.0.0.1:9120",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "mode": "local_tunnel",
        "deployment_environment": "local",
        "detection_method": "manual_config",
        "detected_public_base_url": "",
        "configured_public_base_url": "https://demo.ngrok.app",
        "effective_public_base_url": "https://demo.ngrok.app",
        "effective_source": "config",
        "cursor_override_base_url": "https://demo.ngrok.app",
        "configured": True,
        "requires_public_url": True,
    }


def test_get_public_access_passes_configured_backend_port_to_ngrok_detection() -> None:
    """Local mode should probe ngrok using the configured backend port."""
    config = UserConfig()
    config.public_access.mode = "local_tunnel"
    config.public_access.public_base_url = ""
    config.ports.backend = 9234

    with (
        patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
        patch(PUBLIC_ACCESS_NGROK_DETECT, return_value=("https://port-aware.ngrok.app", "ngrok_api")) as mock_detect,
    ):
        mock_config_store.load.return_value = config

        client = TestClient(app)
        response = client.get(
            "/api/public-access",
            headers={
                "x-forwarded-proto": "http",
                "x-forwarded-host": "127.0.0.1:9120",
            },
        )

    assert response.status_code == 200
    mock_detect.assert_called_once_with(9234)
    assert response.json()["effective_public_base_url"] == "https://port-aware.ngrok.app"
    assert response.json()["effective_source"] == "ngrok_api"


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
        "deployment_environment": "local",
        "detection_method": "request_origin",
        "detected_public_base_url": "https://ternion-service-abc.run.app",
        "configured_public_base_url": "",
        "effective_public_base_url": "https://ternion-service-abc.run.app",
        "effective_source": "request_origin",
        "cursor_override_base_url": "https://ternion-service-abc.run.app",
        "configured": True,
        "requires_public_url": True,
    }


def test_get_public_access_uses_request_base_url_when_forwarded_headers_absent() -> None:
    """Public deployments without forwarded headers should still resolve from the request URL."""
    with patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store:
        mock_config_store.load.return_value = UserConfig()

        client = TestClient(app, base_url="https://ternion.example.com")
        response = client.get("/api/public-access")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "none",
        "deployment_environment": "local",
        "detection_method": "request_origin",
        "detected_public_base_url": "https://ternion.example.com",
        "configured_public_base_url": "",
        "effective_public_base_url": "https://ternion.example.com",
        "effective_source": "request_origin",
        "cursor_override_base_url": "https://ternion.example.com",
        "configured": True,
        "requires_public_url": True,
    }


def test_get_public_access_ignores_local_request_origin() -> None:
    """Local request origins should not be treated as public-access URLs."""
    with (
        patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
        patch(PUBLIC_ACCESS_NGROK_DETECT, return_value=("", "none")),
    ):
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
        "deployment_environment": "local",
        "detection_method": "none",
        "detected_public_base_url": "",
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
        patch(PUBLIC_ACCESS_NGROK_DETECT, return_value=("", "none")),
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
        "deployment_environment": "local",
        "detection_method": "manual_config",
        "detected_public_base_url": "",
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
        patch(PUBLIC_ACCESS_NGROK_DETECT, return_value=("", "none")),
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
        patch(PUBLIC_ACCESS_NGROK_DETECT, return_value=("", "none")),
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


def test_get_public_access_reports_cloud_run_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The route should expose Cloud Run deployment environment when present."""
    monkeypatch.setenv("K_SERVICE", "ternion-service")
    with (
        patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
        patch(PUBLIC_ACCESS_NGROK_DETECT) as mock_detect,
    ):
        mock_config_store.load.return_value = UserConfig()

        client = TestClient(app, base_url="https://ternion.run.app")
        response = client.get("/api/public-access")

    assert response.status_code == 200
    mock_detect.assert_not_called()
    assert response.json()["deployment_environment"] == "cloud_run"
    assert response.json()["detection_method"] == "request_origin"
    assert response.json()["detected_public_base_url"] == "https://ternion.run.app"
    assert response.json()["effective_source"] == "request_origin"
    assert response.json()["effective_public_base_url"] == "https://ternion.run.app"


def test_get_public_access_cloud_run_request_origin_beats_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cloud Run should prefer the current public request origin over saved config."""
    monkeypatch.setenv("K_SERVICE", "ternion-service")
    config = UserConfig()
    config.public_access.mode = "cloud_run"
    config.public_access.public_base_url = "https://configured.example"

    with (
        patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
        patch(PUBLIC_ACCESS_NGROK_DETECT) as mock_detect,
    ):
        mock_config_store.load.return_value = config

        client = TestClient(app, base_url="https://ternion.run.app")
        response = client.get("/api/public-access")

    assert response.status_code == 200
    mock_detect.assert_not_called()
    assert response.json() == {
        "mode": "cloud_run",
        "deployment_environment": "cloud_run",
        "detection_method": "request_origin",
        "detected_public_base_url": "https://ternion.run.app",
        "configured_public_base_url": "https://configured.example",
        "effective_public_base_url": "https://ternion.run.app",
        "effective_source": "request_origin",
        "cursor_override_base_url": "https://ternion.run.app",
        "configured": True,
        "requires_public_url": True,
    }


def test_get_public_access_cloud_run_forwarded_origin_beats_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cloud Run should prefer forwarded public origin over saved config."""
    monkeypatch.setenv("K_SERVICE", "ternion-service")
    config = UserConfig()
    config.public_access.mode = "cloud_run"
    config.public_access.public_base_url = "https://configured.example"

    with (
        patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
        patch(PUBLIC_ACCESS_NGROK_DETECT) as mock_detect,
    ):
        mock_config_store.load.return_value = config

        client = TestClient(app)
        response = client.get(
            "/api/public-access",
            headers={
                "x-forwarded-proto": "https",
                "x-forwarded-host": "ternion-forwarded.run.app",
            },
        )

    assert response.status_code == 200
    mock_detect.assert_not_called()
    assert response.json() == {
        "mode": "cloud_run",
        "deployment_environment": "cloud_run",
        "detection_method": "request_origin",
        "detected_public_base_url": "https://ternion-forwarded.run.app",
        "configured_public_base_url": "https://configured.example",
        "effective_public_base_url": "https://ternion-forwarded.run.app",
        "effective_source": "request_origin",
        "cursor_override_base_url": "https://ternion-forwarded.run.app",
        "configured": True,
        "requires_public_url": True,
    }


def test_get_public_access_cloud_run_falls_back_to_config_when_origin_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cloud Run should fall back to saved config when request-origin is unavailable."""
    monkeypatch.setenv("K_SERVICE", "ternion-service")
    config = UserConfig()
    config.public_access.mode = "cloud_run"
    config.public_access.public_base_url = "https://configured.example/v1"

    with (
        patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
        patch(PUBLIC_ACCESS_NGROK_DETECT) as mock_detect,
    ):
        mock_config_store.load.return_value = config

        client = TestClient(app)
        response = client.get(
            "/api/public-access",
            headers={
                "x-forwarded-proto": "http",
                "x-forwarded-host": "127.0.0.1:9110",
            },
        )

    assert response.status_code == 200
    mock_detect.assert_not_called()
    assert response.json() == {
        "mode": "cloud_run",
        "deployment_environment": "cloud_run",
        "detection_method": "manual_config",
        "detected_public_base_url": "",
        "configured_public_base_url": "https://configured.example",
        "effective_public_base_url": "https://configured.example",
        "effective_source": "config",
        "cursor_override_base_url": "https://configured.example",
        "configured": True,
        "requires_public_url": True,
    }


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

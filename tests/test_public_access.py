"""Tests for public-access URL canonicalization and config persistence."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest

from ternion.core.config_store import ConfigStore, UserConfig
from ternion.core.public_access import (
    build_public_origin,
    detect_deployment_environment,
    detect_ngrok_public_base_url,
    is_local_origin,
    matches_backend_addr,
    normalize_public_base_url,
    resolve_public_access_state,
)


def test_normalize_public_base_url_canonicalizes_root_url() -> None:
    """Canonicalization should strip a trailing slash and remove a terminal `/v1`."""
    assert normalize_public_base_url("https://example.com/") == "https://example.com"
    assert normalize_public_base_url("https://example.com/v1") == "https://example.com"
    assert normalize_public_base_url("https://example.com/base/v1") == "https://example.com/base"
    assert normalize_public_base_url("https://example.com/v1/") == "https://example.com"


def test_normalize_public_base_url_rejects_invalid_values() -> None:
    """Canonicalization should fail closed for empty or malformed values."""
    assert normalize_public_base_url("") == ""
    assert normalize_public_base_url("not-a-url") == ""
    assert normalize_public_base_url("ftp://example.com") == ""


def test_normalize_public_base_url_preserves_non_terminal_v1() -> None:
    """Only a terminal lowercase `/v1` segment should be stripped."""
    assert normalize_public_base_url("https://example.com/v1/api") == "https://example.com/v1/api"
    assert normalize_public_base_url("https://example.com/V1") == "https://example.com/V1"


def test_is_local_origin_distinguishes_local_and_public_hosts() -> None:
    """Local/private origins should be rejected while public origins are allowed."""
    assert is_local_origin("http://localhost:9110") is True
    assert is_local_origin("http://192.168.1.1") is True
    assert is_local_origin("https://10.0.0.1") is True
    assert is_local_origin("http://myhost") is True
    assert is_local_origin("https://service.run.app") is False


def test_build_public_origin_handles_public_and_local_inputs() -> None:
    """Public origin builder should normalize forwarded values and reject local ones."""
    assert build_public_origin("https", "service.run.app") == "https://service.run.app"
    assert build_public_origin("https", "127.0.0.1:9110") == ""
    assert build_public_origin("https", "host1.example.com, host2.example.com") == (
        "https://host1.example.com"
    )
    assert build_public_origin("", "service.run.app") == ""


def test_detect_deployment_environment_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deployment detection should default to local outside Cloud Run."""
    monkeypatch.delenv("K_SERVICE", raising=False)
    assert detect_deployment_environment() == "local"


def test_detect_deployment_environment_treats_empty_k_service_as_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty Cloud Run service variable should still be treated as local."""
    monkeypatch.setenv("K_SERVICE", "")
    assert detect_deployment_environment() == "local"


def test_detect_deployment_environment_recognizes_cloud_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cloud Run should be detected via its runtime environment variable."""
    monkeypatch.setenv("K_SERVICE", "ternion-service")
    assert detect_deployment_environment() == "cloud_run"


def test_matches_backend_addr_accepts_supported_local_targets() -> None:
    """ngrok tunnel targets should match the local backend port across common forms."""
    assert matches_backend_addr("http://127.0.0.1:9110", 9110) is True
    assert matches_backend_addr("https://localhost:9110", 9110) is True
    assert matches_backend_addr("localhost:9110", 9110) is True
    assert matches_backend_addr("0.0.0.0:9110", 9110) is True
    assert matches_backend_addr("9110", 9110) is True


def test_matches_backend_addr_rejects_unrelated_targets() -> None:
    """Only localhost-style addresses for the configured backend port should match."""
    assert matches_backend_addr("http://127.0.0.1:9120", 9110) is False
    assert matches_backend_addr("https://example.com:9110", 9110) is False
    assert matches_backend_addr("", 9110) is False


def test_detect_ngrok_public_base_url_prefers_matching_https_tunnel() -> None:
    """ngrok detection should return the matching HTTPS tunnel for the backend port."""
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "tunnels": [
            {
                "proto": "http",
                "public_url": "http://ignored.ngrok.app",
                "config": {"addr": "http://127.0.0.1:9110"},
            },
            {
                "proto": "https",
                "public_url": "https://ternion.ngrok.app/v1",
                "config": {"addr": "http://127.0.0.1:9110"},
            },
        ]
    }

    with patch("ternion.core.public_access.httpx.get", return_value=response) as mock_get:
        assert detect_ngrok_public_base_url(9110) == ("https://ternion.ngrok.app", "ngrok_api")

    mock_get.assert_called_once_with("http://127.0.0.1:4040/api/tunnels", timeout=1.0)


def test_detect_ngrok_public_base_url_falls_back_to_localhost_probe() -> None:
    """ngrok detection should try localhost when the default loopback probe fails."""
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "tunnels": [
            {
                "proto": "https",
                "public_url": "https://localhost-probe.ngrok.app",
                "config": {"addr": "localhost:9110"},
            }
        ]
    }

    with patch(
        "ternion.core.public_access.httpx.get",
        side_effect=[httpx.ConnectError("default probe failed"), response],
    ) as mock_get:
        assert detect_ngrok_public_base_url(9110) == (
            "https://localhost-probe.ngrok.app",
            "ngrok_api",
        )

    assert mock_get.call_count == 2


def test_detect_ngrok_public_base_url_returns_none_without_matching_https_tunnel() -> None:
    """ngrok detection should fail closed when no matching HTTPS tunnel exists."""
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "tunnels": [
            {
                "proto": "https",
                "public_url": "https://other.ngrok.app",
                "config": {"addr": "http://127.0.0.1:9120"},
            }
        ]
    }

    with patch("ternion.core.public_access.httpx.get", return_value=response):
        assert detect_ngrok_public_base_url(9110) == ("", "none")


def test_detect_ngrok_public_base_url_returns_none_when_ngrok_is_unavailable() -> None:
    """ngrok detection should stay best-effort when both probes are unreachable."""
    with patch(
        "ternion.core.public_access.httpx.get",
        side_effect=[
            httpx.ConnectError("loopback probe failed"),
            httpx.ConnectError("localhost probe failed"),
        ],
    ):
        assert detect_ngrok_public_base_url(9110) == ("", "none")


def test_detect_ngrok_public_base_url_ignores_non_mapping_payload() -> None:
    """ngrok detection should ignore non-dict JSON payloads instead of raising."""
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.side_effect = [[{"proto": "https"}], {"tunnels": []}]

    with patch("ternion.core.public_access.httpx.get", return_value=response):
        assert detect_ngrok_public_base_url(9110) == ("", "none")


def test_detect_ngrok_public_base_url_ignores_malformed_tunnels_shape() -> None:
    """ngrok detection should ignore malformed tunnel collections."""
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.side_effect = [
        {"tunnels": {"proto": "https"}},
        {"tunnels": ["not-a-dict"]},
    ]

    with patch("ternion.core.public_access.httpx.get", return_value=response):
        assert detect_ngrok_public_base_url(9110) == ("", "none")


def test_resolve_public_access_state_local_request_origin_beats_config() -> None:
    """In local mode, a live public request origin should beat saved config."""
    with patch("ternion.core.public_access.detect_ngrok_public_base_url") as mock_detect:
        assert resolve_public_access_state(
            "https://configured.example/v1",
            request_origin="https://detected.example",
            deployment_environment="local",
        ) == {
            "deployment_environment": "local",
            "detection_method": "request_origin",
            "detected_public_base_url": "https://detected.example",
            "effective_public_base_url": "https://detected.example",
            "effective_source": "request_origin",
        }

    mock_detect.assert_not_called()


def test_resolve_public_access_state_local_uses_ngrok_detection_before_config() -> None:
    """In local mode, ngrok detection should beat manual config when origin is unavailable."""
    with patch(
        "ternion.core.public_access.detect_ngrok_public_base_url",
        return_value=("https://ternion.ngrok.app", "ngrok_api"),
    ) as mock_detect:
        assert resolve_public_access_state(
            "https://configured.example/v1",
            deployment_environment="local",
            backend_port=9110,
        ) == {
            "deployment_environment": "local",
            "detection_method": "ngrok_api",
            "detected_public_base_url": "https://ternion.ngrok.app",
            "effective_public_base_url": "https://ternion.ngrok.app",
            "effective_source": "ngrok_api",
        }

    mock_detect.assert_called_once_with(9110)


def test_resolve_public_access_state_local_falls_back_to_config_when_ngrok_missing() -> None:
    """In local mode, config should still be used when ngrok auto-discovery fails."""
    with patch(
        "ternion.core.public_access.detect_ngrok_public_base_url",
        return_value=("", "none"),
    ) as mock_detect:
        assert resolve_public_access_state(
            "https://configured.example/v1",
            deployment_environment="local",
            backend_port=9110,
        ) == {
            "deployment_environment": "local",
            "detection_method": "manual_config",
            "detected_public_base_url": "",
            "effective_public_base_url": "https://configured.example",
            "effective_source": "config",
        }

    mock_detect.assert_called_once_with(9110)


def test_resolve_public_access_state_cloud_run_prefers_request_origin() -> None:
    """Cloud Run should prioritize the current public request origin over saved config."""
    with patch("ternion.core.public_access.detect_ngrok_public_base_url") as mock_detect:
        assert resolve_public_access_state(
            "https://configured.example",
            request_origin="https://service-abc.run.app/v1",
            deployment_environment="cloud_run",
        ) == {
            "deployment_environment": "cloud_run",
            "detection_method": "request_origin",
            "detected_public_base_url": "https://service-abc.run.app",
            "effective_public_base_url": "https://service-abc.run.app",
            "effective_source": "request_origin",
        }

    mock_detect.assert_not_called()


def test_resolve_public_access_state_cloud_run_falls_back_to_config_when_origin_missing() -> None:
    """Cloud Run should still use saved config when no public request origin is available."""
    with patch("ternion.core.public_access.detect_ngrok_public_base_url") as mock_detect:
        assert resolve_public_access_state(
            "https://configured.example/v1",
            deployment_environment="cloud_run",
        ) == {
            "deployment_environment": "cloud_run",
            "detection_method": "manual_config",
            "detected_public_base_url": "",
            "effective_public_base_url": "https://configured.example",
            "effective_source": "config",
        }

    mock_detect.assert_not_called()


def test_resolve_public_access_state_cloud_run_returns_none_without_any_signal() -> None:
    """Cloud Run should resolve to none when neither origin nor config is available."""
    with patch("ternion.core.public_access.detect_ngrok_public_base_url") as mock_detect:
        assert resolve_public_access_state(
            "",
            deployment_environment="cloud_run",
        ) == {
            "deployment_environment": "cloud_run",
            "detection_method": "none",
            "detected_public_base_url": "",
            "effective_public_base_url": "",
            "effective_source": "none",
        }

    mock_detect.assert_not_called()


def test_resolve_public_access_state_returns_none_without_any_signal() -> None:
    """Runtime state should stay empty when neither config nor request-origin exists."""
    with patch(
        "ternion.core.public_access.detect_ngrok_public_base_url",
        return_value=("", "none"),
    ) as mock_detect:
        assert resolve_public_access_state(
            "",
            deployment_environment="local",
            backend_port=9110,
        ) == {
            "deployment_environment": "local",
            "detection_method": "none",
            "detected_public_base_url": "",
            "effective_public_base_url": "",
            "effective_source": "none",
        }

    mock_detect.assert_called_once_with(9110)


def test_config_store_save_canonicalizes_public_access_values(tmp_path: Path) -> None:
    """Saving config should persist the public base URL without a `/v1` suffix."""
    store = ConfigStore(config_path=tmp_path / "config.json")
    config = UserConfig()
    config.public_access.mode = "local_tunnel"
    config.public_access.public_base_url = "https://example.com/v1"

    store.save(config)

    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["public_access"]["mode"] == "local_tunnel"
    assert saved["public_access"]["public_base_url"] == "https://example.com"


def test_config_store_load_migrates_invalid_public_access_mode(tmp_path: Path) -> None:
    """Loading config should recover invalid public-access values without dropping config."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "public_access": {
                    "mode": "invalid-mode",
                    "public_base_url": "https://example.com/v1",
                }
            }
        ),
        encoding="utf-8",
    )

    store = ConfigStore(config_path=config_path)
    config = store.load()

    assert config.public_access.mode == "none"
    assert config.public_access.public_base_url == "https://example.com"


def test_config_store_save_sanitizes_invalid_public_access_mode(tmp_path: Path) -> None:
    """Saving config should reset invalid public-access modes to `none`."""
    store = ConfigStore(config_path=tmp_path / "config.json")
    config = UserConfig()
    config.public_access.mode = "invalid-mode"  # type: ignore[assignment]
    config.public_access.public_base_url = "https://example.com"

    store.save(config)

    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["public_access"]["mode"] == "none"


def test_config_store_safe_dict_includes_public_access(tmp_path: Path) -> None:
    """Safe config export should include public-access settings for API consumers."""
    store = ConfigStore(config_path=tmp_path / "config.json")
    config = UserConfig()
    config.public_access.mode = "cloud_run"
    config.public_access.public_base_url = "https://service.example"
    store._config = config

    safe = store.to_safe_dict()

    assert safe["public_access"] == {
        "mode": "cloud_run",
        "public_base_url": "https://service.example",
    }

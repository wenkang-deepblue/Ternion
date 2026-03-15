from unittest.mock import patch

import pytest

import ternion.utils.i18n as i18n
from ternion.core.config import DEFAULT_BACKEND_PORT, DEFAULT_WEB_PORT, normalize_port
from ternion.core.config_store import PortsConfig, UserConfig
from ternion.utils.i18n import MessageKey, get_web_base_url, t


def test_get_web_base_url_default() -> None:
    """Test default standalone development Control Panel URL."""
    with (
        patch("ternion.core.config_store.ConfigStore.load") as mock_load,
        patch("ternion.utils.i18n.has_embedded_panel_assets", return_value=False),
    ):
        mock_load.return_value = UserConfig()
        assert get_web_base_url() == "http://127.0.0.1:9120"


def test_get_web_base_url_custom() -> None:
    """Test custom standalone development Control Panel URL."""
    custom_config = UserConfig(ports=PortsConfig(web=8080))
    with (
        patch("ternion.core.config_store.ConfigStore.load") as mock_load,
        patch("ternion.utils.i18n.has_embedded_panel_assets", return_value=False),
    ):
        mock_load.return_value = custom_config
        assert get_web_base_url() == "http://127.0.0.1:8080"


def test_get_web_base_url_prefers_embedded_panel_mount() -> None:
    """Test embedded Control Panel URL when packaged assets are available."""
    custom_config = UserConfig(ports=PortsConfig(backend=9222, web=8080))
    with (
        patch("ternion.core.config_store.ConfigStore.load") as mock_load,
        patch("ternion.utils.i18n.has_embedded_panel_assets", return_value=True),
    ):
        mock_load.return_value = custom_config
        assert get_web_base_url() == "http://127.0.0.1:9222/panel"


def test_get_web_base_url_falls_back_when_config_missing() -> None:
    """Test default development URL when no user config is available."""
    with (
        patch("ternion.utils.i18n._load_user_config", return_value=None),
        patch("ternion.utils.i18n.has_embedded_panel_assets", return_value=False),
    ):
        assert get_web_base_url() == "http://127.0.0.1:9120"


def test_get_embedded_panel_base_url_falls_back_when_config_missing() -> None:
    """Test default embedded panel URL when no user config is available."""
    with patch("ternion.utils.i18n._load_user_config", return_value=None):
        assert i18n.get_embedded_panel_base_url() == "http://127.0.0.1:9110/panel"


def test_get_web_base_url_rejects_invalid_web_port_values() -> None:
    """Test invalid standalone development ports fall back to the default."""
    invalid_config = UserConfig(ports=PortsConfig(web=9120))
    invalid_config.ports.web = 0
    with (
        patch("ternion.core.config_store.ConfigStore.load") as mock_load,
        patch("ternion.utils.i18n.has_embedded_panel_assets", return_value=False),
    ):
        mock_load.return_value = invalid_config
        assert get_web_base_url() == "http://127.0.0.1:9120"


def test_get_embedded_panel_base_url_rejects_invalid_backend_port_values() -> None:
    """Test invalid embedded backend ports fall back to the default."""
    invalid_config = UserConfig(ports=PortsConfig(backend=9110))
    invalid_config.ports.backend = True
    with patch("ternion.utils.i18n._load_user_config", return_value=invalid_config):
        assert i18n.get_embedded_panel_base_url() == "http://127.0.0.1:9110/panel"


def test_t_injects_web_url() -> None:
    """Test that t() injects web_url into messages."""
    with (
        patch("ternion.core.config_store.ConfigStore.load") as mock_load,
        patch("ternion.utils.i18n.has_embedded_panel_assets", return_value=False),
    ):
        mock_load.return_value = UserConfig()

        msg = t(MessageKey.EXECUTION_MODE_NOT_CONFIGURED)
        assert "http://127.0.0.1:9120" in msg
        assert "Config -> Execution Mode" in msg


def test_t_injects_custom_web_url() -> None:
    """Test that t() injects custom web_url into messages."""
    custom_config = UserConfig(ports=PortsConfig(web=3000))
    with (
        patch("ternion.core.config_store.ConfigStore.load") as mock_load,
        patch("ternion.utils.i18n.has_embedded_panel_assets", return_value=False),
    ):
        mock_load.return_value = custom_config

        msg = t(MessageKey.NO_PROVIDERS_CONFIGURED)
        assert "http://127.0.0.1:3000" in msg


def test_t_injects_embedded_panel_url() -> None:
    """Test embedded panel URLs when packaged assets are available."""
    custom_config = UserConfig(ports=PortsConfig(backend=9555, web=3000))
    with (
        patch("ternion.core.config_store.ConfigStore.load") as mock_load,
        patch("ternion.utils.i18n.has_embedded_panel_assets", return_value=True),
    ):
        mock_load.return_value = custom_config

        msg = t(MessageKey.NO_PROVIDERS_CONFIGURED)
        assert "http://127.0.0.1:9555/panel" in msg


def test_t_allows_explicit_web_url() -> None:
    """Test that explicitly provided web_url overrides default."""
    msg = t(MessageKey.NO_PROVIDERS_CONFIGURED, web_url="http://example.com")
    assert "http://example.com" in msg
    assert "127.0.0.1" not in msg


def test_load_translations_does_not_cache_failures() -> None:
    """Test failed translation loads do not poison future successful loads."""
    original_cache = i18n._translations_cache
    i18n._translations_cache = None
    try:
        with patch("pathlib.Path.read_text", side_effect=OSError("boom")):
            assert i18n._load_translations() == {}
            assert i18n._translations_cache is None

        with patch(
            "pathlib.Path.read_text",
            return_value='{"en":{"no_providers_configured":"Panel: {web_url}"}}',
        ):
            translations = i18n._load_translations()

        assert translations["en"]["no_providers_configured"] == "Panel: {web_url}"
    finally:
        i18n._translations_cache = original_cache


def test_load_translations_logs_invalid_top_level_structure() -> None:
    """Test invalid translation payload structures are logged and not cached."""
    original_cache = i18n._translations_cache
    i18n._translations_cache = None
    try:
        with (
            patch("pathlib.Path.read_text", return_value='["invalid"]'),
            patch("ternion.utils.i18n.logger") as mock_logger,
        ):
            assert i18n._load_translations() == {}

        mock_logger.warning.assert_called_once_with(
            "i18n_translations_invalid_structure",
            path=str(i18n._TRANSLATIONS_PATH),
            actual_type="list",
        )
        assert i18n._translations_cache is None
    finally:
        i18n._translations_cache = original_cache


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        (1, DEFAULT_BACKEND_PORT, 1),
        (65535, DEFAULT_BACKEND_PORT, 65535),
        (65536, DEFAULT_BACKEND_PORT, DEFAULT_BACKEND_PORT),
        (-1, DEFAULT_BACKEND_PORT, DEFAULT_BACKEND_PORT),
        (None, DEFAULT_WEB_PORT, DEFAULT_WEB_PORT),
        (False, DEFAULT_WEB_PORT, DEFAULT_WEB_PORT),
        (3.14, DEFAULT_WEB_PORT, DEFAULT_WEB_PORT),
    ],
)
def test_normalize_port_handles_boundary_and_invalid_values(
    value: object, default: int, expected: int
) -> None:
    """Test normalize_port accepts valid bounds and rejects invalid values."""
    assert normalize_port(value, default) == expected

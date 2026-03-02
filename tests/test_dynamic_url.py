from unittest.mock import patch

from ternion.core.config_store import PortsConfig, UserConfig
from ternion.utils.i18n import MessageKey, get_web_base_url, t


def test_get_web_base_url_default() -> None:
    """Test default web base URL."""
    # Mock config_store.load to return default or empty config
    with patch("ternion.core.config_store.ConfigStore.load") as mock_load:
        mock_load.return_value = UserConfig()
        assert get_web_base_url() == "http://localhost:9120"


def test_get_web_base_url_custom() -> None:
    """Test custom web base URL."""
    custom_config = UserConfig(ports=PortsConfig(web=8080))
    with patch("ternion.core.config_store.ConfigStore.load") as mock_load:
        mock_load.return_value = custom_config
        assert get_web_base_url() == "http://localhost:8080"


def test_t_injects_web_url() -> None:
    """Test that t() injects web_url into messages."""
    # Test with default config
    with patch("ternion.core.config_store.ConfigStore.load") as mock_load:
        mock_load.return_value = UserConfig()

        # Test EXECUTION_MODE_NOT_CONFIGURED message
        msg = t(MessageKey.EXECUTION_MODE_NOT_CONFIGURED)
        assert "http://localhost:9120" in msg
        assert "Config -> Execution Mode" in msg


def test_t_injects_custom_web_url() -> None:
    """Test that t() injects custom web_url into messages."""
    custom_config = UserConfig(ports=PortsConfig(web=3000))
    with patch("ternion.core.config_store.ConfigStore.load") as mock_load:
        mock_load.return_value = custom_config

        # Test NO_PROVIDERS_CONFIGURED message
        msg = t(MessageKey.NO_PROVIDERS_CONFIGURED)
        assert "http://localhost:3000" in msg


def test_t_allows_explicit_web_url() -> None:
    """Test that explicitly provided web_url overrides default."""
    msg = t(MessageKey.NO_PROVIDERS_CONFIGURED, web_url="http://example.com")
    assert "http://example.com" in msg
    assert "localhost" not in msg

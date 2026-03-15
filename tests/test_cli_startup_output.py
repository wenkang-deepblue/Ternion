"""Tests for CLI startup guidance output."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from ternion.__main__ import build_startup_message, main
from ternion.core.config import DEFAULT_BACKEND_PORT, settings


def _make_config(backend_port: object) -> SimpleNamespace:
    """Create a lightweight config object for CLI startup tests."""
    return SimpleNamespace(ports=SimpleNamespace(backend=backend_port))


def test_build_startup_message_uses_backend_port() -> None:
    """Build the startup summary with the configured backend port."""
    message = build_startup_message(9234)

    assert "Ternion is running." in message
    assert "http://127.0.0.1:9234/v1" in message
    assert "http://127.0.0.1:9234/panel" in message
    assert "http://127.0.0.1:9234/docs" in message
    assert "Override OpenAI Base URL" in message
    assert "https://your-public-url/v1" in message


def test_main_prints_startup_guidance_before_starting_server(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Print startup guidance and launch uvicorn with the resolved backend port."""
    mock_config_store = Mock()
    mock_config_store.load.return_value = _make_config(9345)

    with (
        patch("ternion.__main__.setup_logging") as mock_setup_logging,
        patch("ternion.__main__.get_config_store", return_value=mock_config_store),
        patch("ternion.__main__.uvicorn.run") as mock_uvicorn_run,
    ):
        main()

    captured = capsys.readouterr()

    mock_setup_logging.assert_called_once_with(settings.server.log_level)
    assert "http://127.0.0.1:9345/v1" in captured.out
    assert "http://127.0.0.1:9345/panel" in captured.out
    assert "http://127.0.0.1:9345/docs" in captured.out
    assert captured.err == ""
    mock_uvicorn_run.assert_called_once_with(
        "ternion.server.app:app",
        host=settings.server.host,
        port=9345,
        reload=False,
        log_level=settings.server.log_level.lower(),
    )


def test_main_falls_back_to_default_backend_port_for_invalid_config_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Fall back to the default backend port when config provides an invalid value."""
    mock_config_store = Mock()
    mock_config_store.load.return_value = _make_config("invalid")

    with (
        patch("ternion.__main__.setup_logging"),
        patch("ternion.__main__.get_config_store", return_value=mock_config_store),
        patch("ternion.__main__.uvicorn.run") as mock_uvicorn_run,
    ):
        main()

    captured = capsys.readouterr()

    assert f"http://127.0.0.1:{DEFAULT_BACKEND_PORT}/v1" in captured.out
    assert f"http://127.0.0.1:{DEFAULT_BACKEND_PORT}/panel" in captured.out
    mock_uvicorn_run.assert_called_once_with(
        "ternion.server.app:app",
        host=settings.server.host,
        port=DEFAULT_BACKEND_PORT,
        reload=False,
        log_level=settings.server.log_level.lower(),
    )

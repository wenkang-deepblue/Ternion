"""Tests for CLI startup guidance output."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from ternion.__main__ import (
    PortInitializationError,
    _config_exists,
    build_startup_message,
    initialize_ports,
    main,
    prompt_for_port,
    resolve_runtime_ports,
)
from ternion.core.config import DEFAULT_BACKEND_PORT, DEFAULT_WEB_PORT, settings


def _make_config(backend_port: object, web_port: object = DEFAULT_WEB_PORT) -> SimpleNamespace:
    """Create a lightweight config object for CLI startup tests."""
    return SimpleNamespace(ports=SimpleNamespace(backend=backend_port, web=web_port))


def test_build_startup_message_uses_backend_port() -> None:
    """Build the startup summary with the configured backend port."""
    message = build_startup_message(9234)

    assert "Ternion is running." in message
    assert "http://127.0.0.1:9234/v1" in message
    assert "http://127.0.0.1:9234/panel" in message
    assert "http://127.0.0.1:9234/docs" in message
    assert "Override OpenAI Base URL" in message
    assert "https://your-public-url" in message


def test_main_prints_startup_guidance_before_starting_server(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Print startup guidance and launch uvicorn with the resolved backend port."""
    mock_config_store = Mock()
    mock_config_store.load.return_value = _make_config(9345)
    mock_config_store.config_path.exists.return_value = True

    with (
        patch("ternion.__main__.setup_logging") as mock_setup_logging,
        patch("ternion.__main__.get_config_store", return_value=mock_config_store),
        patch("ternion.__main__.uvicorn.run") as mock_uvicorn_run,
    ):
        main([])

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
    mock_config_store.config_path.exists.return_value = True

    with (
        patch("ternion.__main__.setup_logging"),
        patch("ternion.__main__.get_config_store", return_value=mock_config_store),
        patch("ternion.__main__.uvicorn.run") as mock_uvicorn_run,
    ):
        main([])

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


def test_main_runs_first_time_initialization_before_starting_server(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """First interactive run should initialize ports and then start the server."""
    mock_config_store = Mock()
    mock_config_store.config_path.exists.return_value = False

    with (
        patch("ternion.__main__.setup_logging"),
        patch("ternion.__main__.get_config_store", return_value=mock_config_store),
        patch("ternion.__main__.sys.stdin.isatty", return_value=True),
        patch("ternion.__main__.initialize_ports", return_value=9456) as mock_initialize_ports,
        patch("ternion.__main__.uvicorn.run") as mock_uvicorn_run,
    ):
        main([])

    captured = capsys.readouterr()

    mock_initialize_ports.assert_called_once_with(mock_config_store)
    assert "http://127.0.0.1:9456/v1" in captured.out
    assert "http://127.0.0.1:9456/panel" in captured.out
    mock_uvicorn_run.assert_called_once_with(
        "ternion.server.app:app",
        host=settings.server.host,
        port=9456,
        reload=False,
        log_level=settings.server.log_level.lower(),
    )


def test_main_skips_first_time_initialization_when_stdin_is_not_a_tty(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-interactive startup should not block on first-run initialization."""
    mock_config_store = Mock()
    mock_config_store.load.return_value = _make_config(9345)
    mock_config_store.config_path.exists.return_value = False

    with (
        patch("ternion.__main__.setup_logging"),
        patch("ternion.__main__.get_config_store", return_value=mock_config_store),
        patch("ternion.__main__.sys.stdin.isatty", return_value=False),
        patch("ternion.__main__.initialize_ports") as mock_initialize_ports,
        patch("ternion.__main__.uvicorn.run") as mock_uvicorn_run,
    ):
        exit_code = main([])

    captured = capsys.readouterr()

    assert exit_code == 0
    mock_initialize_ports.assert_not_called()
    assert "http://127.0.0.1:9345/v1" in captured.out
    mock_uvicorn_run.assert_called_once()


def test_prompt_for_port_accepts_default_value_when_input_is_empty() -> None:
    """Use the default port when the user presses Enter and the port is available."""
    outputs: list[str] = []

    with patch("ternion.__main__.is_port_available", return_value=True):
        selected = prompt_for_port(
            "Backend port",
            DEFAULT_BACKEND_PORT,
            input_fn=lambda _prompt: "",
            output_fn=outputs.append,
        )

    assert selected == DEFAULT_BACKEND_PORT
    assert outputs == []


def test_prompt_for_port_accepts_upper_bound_port() -> None:
    """Allow the maximum valid port value."""
    with patch("ternion.__main__.is_port_available", return_value=True):
        selected = prompt_for_port(
            "Backend port",
            DEFAULT_BACKEND_PORT,
            input_fn=lambda _prompt: "65535",
            output_fn=lambda _message: None,
        )

    assert selected == 65535


def test_prompt_for_port_retries_until_port_is_valid_and_available() -> None:
    """Retry for invalid, duplicate, and occupied ports before accepting input."""
    responses = iter(["abc", "80", "9110", "9234", "9235"])
    outputs: list[str] = []

    with patch("ternion.__main__.is_port_available", side_effect=lambda port: port != 9234):
        selected = prompt_for_port(
            "Web UI port",
            DEFAULT_WEB_PORT,
            reserved_ports={9110},
            input_fn=lambda _prompt: next(responses),
            output_fn=outputs.append,
        )

    assert selected == 9235
    assert outputs == [
        "Invalid port. Please enter a number between 1024 and 65535.",
        "Invalid port. Please enter a number between 1024 and 65535.",
        "Port 9110 is already assigned to another Ternion service. Please enter a different port.",
        "Port 9234 is already in use. Please enter a different port.",
    ]


def test_prompt_for_port_rejects_out_of_range_upper_bound() -> None:
    """Reject 65536 and accept a later valid port."""
    responses = iter(["65536", "9235"])
    outputs: list[str] = []

    with patch("ternion.__main__.is_port_available", return_value=True):
        selected = prompt_for_port(
            "Backend port",
            DEFAULT_BACKEND_PORT,
            input_fn=lambda _prompt: next(responses),
            output_fn=outputs.append,
        )

    assert selected == 9235
    assert outputs == ["Invalid port. Please enter a number between 1024 and 65535."]


def test_prompt_for_port_raises_friendly_error_on_eof() -> None:
    """Convert EOFError into a friendly initialization error."""
    with pytest.raises(
        PortInitializationError,
        match="Port configuration cancelled because no interactive input was available.",
    ):
        prompt_for_port(
            "Backend port",
            DEFAULT_BACKEND_PORT,
            input_fn=lambda _prompt: (_ for _ in ()).throw(EOFError()),
            output_fn=lambda _message: None,
        )


def test_prompt_for_port_raises_friendly_error_on_keyboard_interrupt() -> None:
    """Convert KeyboardInterrupt into a friendly initialization error."""
    with pytest.raises(
        PortInitializationError,
        match="Port configuration cancelled by the user.",
    ):
        prompt_for_port(
            "Backend port",
            DEFAULT_BACKEND_PORT,
            input_fn=lambda _prompt: (_ for _ in ()).throw(KeyboardInterrupt()),
            output_fn=lambda _message: None,
        )


def test_prompt_for_port_stops_after_max_attempts() -> None:
    """Abort after too many invalid attempts instead of retrying forever."""
    outputs: list[str] = []

    with pytest.raises(
        PortInitializationError,
        match="Port configuration failed after 3 invalid attempts.",
    ):
        prompt_for_port(
            "Backend port",
            DEFAULT_BACKEND_PORT,
            input_fn=lambda _prompt: "invalid",
            output_fn=outputs.append,
            max_attempts=3,
        )

    assert outputs == [
        "Invalid port. Please enter a number between 1024 and 65535.",
        "Invalid port. Please enter a number between 1024 and 65535.",
        "Invalid port. Please enter a number between 1024 and 65535.",
    ]


def test_resolve_runtime_ports_uses_saved_backend_config() -> None:
    """Server startup should reuse the saved backend port."""
    mock_config_store = Mock()
    mock_config_store.load.return_value = _make_config(9444, 9555)

    backend_port = resolve_runtime_ports(mock_config_store)

    assert backend_port == 9444
    mock_config_store.save.assert_not_called()


def test_initialize_ports_prompts_and_saves_backend_configuration() -> None:
    """Interactive initialization should prompt for the released backend port and persist it."""
    mock_config_store = Mock()
    mock_config_store.load.return_value = _make_config(DEFAULT_BACKEND_PORT, DEFAULT_WEB_PORT)
    outputs: list[str] = []

    with patch("ternion.__main__.is_port_available", return_value=True):
        backend_port = initialize_ports(
            mock_config_store,
            input_fn=lambda _prompt: "9345",
            output_fn=outputs.append,
        )

    assert backend_port == 9345
    mock_config_store.save.assert_called_once()
    saved_config = mock_config_store.save.call_args.args[0]
    assert saved_config.ports.backend == 9345
    assert saved_config.ports.web == DEFAULT_WEB_PORT
    assert outputs == [
        "Configure the Ternion backend port for this installation. Press Enter to keep the current value.",
        "Port configuration saved.",
        "Backend API: http://127.0.0.1:9345/v1",
        "Control Panel: http://127.0.0.1:9345/panel",
        "API Docs: http://127.0.0.1:9345/docs",
    ]


def test_initialize_ports_keeps_default_backend_port_when_input_is_empty() -> None:
    """Interactive initialization should keep the current backend port on empty input."""
    mock_config_store = Mock()
    mock_config_store.load.return_value = _make_config(9222, DEFAULT_WEB_PORT)
    outputs: list[str] = []

    with patch("ternion.__main__.is_port_available", return_value=True):
        backend_port = initialize_ports(
            mock_config_store,
            input_fn=lambda _prompt: "",
            output_fn=outputs.append,
        )

    assert backend_port == 9222
    saved_config = mock_config_store.save.call_args.args[0]
    assert saved_config.ports.backend == 9222
    assert outputs[0] == (
        "Configure the Ternion backend port for this installation. Press Enter to keep the current value."
    )


def test_initialize_ports_raises_friendly_error_when_save_fails() -> None:
    """Initialization should surface a friendly message when persistence fails."""
    mock_config_store = Mock()
    mock_config_store.load.return_value = _make_config(DEFAULT_BACKEND_PORT, DEFAULT_WEB_PORT)
    mock_config_store.save.side_effect = OSError("disk full")

    with (
        patch("ternion.__main__.is_port_available", return_value=True),
        pytest.raises(
            PortInitializationError,
            match="Failed to save the port configuration. Check file permissions and disk space.",
        ),
    ):
        initialize_ports(
            mock_config_store,
            input_fn=lambda _prompt: "9345",
            output_fn=lambda _message: None,
        )


def test_main_init_command_runs_port_initialization() -> None:
    """The init subcommand should dispatch to the interactive initializer."""
    with patch("ternion.__main__.run_init") as mock_run_init:
        exit_code = main(["init"])

    assert exit_code == mock_run_init.return_value
    mock_run_init.assert_called_once_with()


def test_config_exists_returns_true_when_config_file_exists() -> None:
    """Treat existing config files as non-first-run installations."""
    mock_config_store = Mock()
    mock_config_store.config_path.exists.return_value = True

    assert _config_exists(mock_config_store) is True


def test_config_exists_returns_false_when_config_file_is_missing() -> None:
    """Treat a missing config file as a first-run installation."""
    mock_config_store = Mock()
    mock_config_store.config_path.exists.return_value = False

    assert _config_exists(mock_config_store) is False


def test_config_exists_returns_false_when_store_has_no_config_path() -> None:
    """Unexpected stores should not silently skip first-run initialization."""

    class PathlessStore:
        """Minimal stub without a config_path attribute."""

    with patch("ternion.__main__.logger.warning") as mock_warning:
        assert _config_exists(PathlessStore()) is False

    mock_warning.assert_called_once_with("config_store_missing_config_path")


def test_config_exists_returns_false_when_config_path_is_invalid() -> None:
    """Unexpected config_path values should not silently skip first-run initialization."""

    class InvalidPathStore:
        """Minimal stub with a malformed config_path."""

        config_path = "not-a-path"

    with patch("ternion.__main__.logger.warning") as mock_warning:
        assert _config_exists(InvalidPathStore()) is False

    mock_warning.assert_called_once_with(
        "config_store_invalid_config_path",
        config_path_type="str",
    )

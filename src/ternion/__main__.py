"""
Entry point for running Ternion as a module.

Usage:
    python -m ternion
    # or
    ternion (if installed)
"""

import argparse
import errno
import socket
import sys
from collections.abc import Callable
from textwrap import dedent

import structlog
import uvicorn

from ternion.core.config import DEFAULT_BACKEND_PORT, get_default_local_host, normalize_port, settings
from ternion.core.config_store import ConfigStore, get_config_store
from ternion.utils.logging import setup_logging

logger = structlog.get_logger(__name__)


class PortInitializationError(RuntimeError):
    """Raised when the interactive port initialization flow cannot complete."""


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the released entrypoint."""
    parser = argparse.ArgumentParser(
        prog="ternion",
        description="Run Ternion or initialize its local port configuration.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("run", "init"),
        default="run",
        help="Use 'init' to configure the backend port manually, or omit it to start the server.",
    )
    return parser


def build_local_service_url(port: int, path: str) -> str:
    """Build a canonical local service URL for CLI guidance output.

    Args:
        port: Local TCP port exposed by the backend service.
        path: URL path suffix beginning with `/`.

    Returns:
        A canonical local URL using the standard loopback host.
    """
    return f"http://{get_default_local_host()}:{port}{path}"


def build_startup_message(backend_port: int) -> str:
    """Build the CLI startup guidance shown before the server enters its run loop.

    Args:
        backend_port: Local TCP port exposed by the backend service.

    Returns:
        A multi-line startup summary for local access and Cursor tunnel setup.
    """
    local_api_url = build_local_service_url(backend_port, "/v1")
    control_panel_url = build_local_service_url(backend_port, "/panel")
    api_docs_url = build_local_service_url(backend_port, "/docs")
    public_base_url = "https://your-public-url"

    return dedent(
        f"""\
        Ternion is running.
        Local API:      {local_api_url}
        Control Panel:  {control_panel_url}
        API Docs:       {api_docs_url}

        To use Ternion in Cursor, expose this local service through a public HTTPS tunnel,
        then set Cursor's Override OpenAI Base URL to:
        {public_base_url}
        """
    ).strip()


def emit_startup_message(backend_port: int) -> None:
    """Write the CLI startup guidance to standard output.

    Args:
        backend_port: Local TCP port exposed by the backend service.
    """
    print(build_startup_message(backend_port), flush=True)


def is_port_available(port: int) -> bool:
    """Return whether a local TCP port can be bound on the default loopback host.

    Raises:
        PortInitializationError: The local probe cannot complete due to a system error.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((get_default_local_host(), port))
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                return False
            if exc.errno == errno.EACCES:
                raise PortInitializationError(
                    f"Port {port} cannot be checked because the system denied access."
                ) from exc
            if exc.errno == errno.EADDRNOTAVAIL:
                raise PortInitializationError(
                    "The local loopback address is unavailable, so port probing cannot continue."
                ) from exc
            raise PortInitializationError(
                f"Port {port} could not be checked due to a system error: {exc.strerror or exc}."
            ) from exc
    return True


def prompt_for_port(
    label: str,
    default_port: int,
    *,
    reserved_ports: set[int] | None = None,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    max_attempts: int = 10,
) -> int:
    """Prompt for a valid TCP port, retrying until the value is acceptable."""
    reserved_ports = reserved_ports or set()
    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        try:
            raw_value = input_fn(f"{label} [default: {default_port}]: ").strip()
        except EOFError as exc:
            raise PortInitializationError(
                "Port configuration cancelled because no interactive input was available."
            ) from exc
        except KeyboardInterrupt as exc:
            raise PortInitializationError("Port configuration cancelled by the user.") from exc

        if not raw_value:
            candidate = default_port
        else:
            try:
                candidate = int(raw_value)
            except ValueError:
                output_fn("Invalid port. Please enter a number between 1024 and 65535.")
                continue

        if candidate < 1024 or candidate > 65535:
            output_fn("Invalid port. Please enter a number between 1024 and 65535.")
            continue

        if candidate in reserved_ports:
            output_fn(
                f"Port {candidate} is already assigned to another Ternion service. "
                "Please enter a different port."
            )
            continue

        if not is_port_available(candidate):
            output_fn(f"Port {candidate} is already in use. Please enter a different port.")
            continue

        return candidate

    raise PortInitializationError(
        f"Port configuration failed after {max_attempts} invalid attempts."
    )


def resolve_runtime_ports(config_store: ConfigStore) -> int:
    """Resolve the backend port from the saved user configuration."""
    config = config_store.load()
    return normalize_port(config.ports.backend, DEFAULT_BACKEND_PORT)


def _config_exists(config_store: ConfigStore) -> bool:
    """Return whether the persisted user configuration file exists.

    When the store structure is unexpected, log the anomaly and allow the
    first-run initialization path to proceed instead of silently skipping it.
    """
    config_path = getattr(config_store, "config_path", None)
    if config_path is None:
        logger.warning("config_store_missing_config_path")
        return False
    exists = getattr(config_path, "exists", None)
    if not callable(exists):
        logger.warning("config_store_invalid_config_path", config_path_type=type(config_path).__name__)
        return False
    return bool(exists())


def initialize_ports(
    config_store: ConfigStore,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    """Interactively configure and persist the released installation backend port."""
    config = config_store.load()
    current_backend = resolve_runtime_ports(config_store)

    output_fn(
        "Configure the Ternion backend port for this installation. "
        "Press Enter to keep the current value."
    )
    backend_port = prompt_for_port(
        "Backend port",
        current_backend,
        input_fn=input_fn,
        output_fn=output_fn,
    )

    config.ports.backend = backend_port
    try:
        config_store.save(config)
    except Exception as exc:
        raise PortInitializationError(
            "Failed to save the port configuration. Check file permissions and disk space."
        ) from exc
    output_fn("Port configuration saved.")
    output_fn(f"Backend API: {build_local_service_url(backend_port, '/v1')}")
    output_fn(f"Control Panel: {build_local_service_url(backend_port, '/panel')}")
    output_fn(f"API Docs: {build_local_service_url(backend_port, '/docs')}")
    return backend_port


def run_server() -> int:
    """Start the Ternion server using the saved port configuration."""
    setup_logging(settings.server.log_level)
    config_store = get_config_store()
    try:
        if not _config_exists(config_store) and sys.stdin.isatty():
            backend_port = initialize_ports(config_store)
        else:
            backend_port = resolve_runtime_ports(config_store)
    except PortInitializationError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1
    emit_startup_message(backend_port)
    uvicorn.run(
        "ternion.server.app:app",
        host=settings.server.host,
        port=backend_port,
        reload=False,
        log_level=settings.server.log_level.lower(),
    )
    return 0


def run_init() -> int:
    """Run the interactive port initialization flow for released installations."""
    setup_logging(settings.server.log_level)
    config_store = get_config_store()
    try:
        initialize_ports(config_store)
    except PortInitializationError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch the released CLI entrypoint."""
    args = build_parser().parse_args(argv)
    if args.command == "init":
        return run_init()

    return run_server()


if __name__ == "__main__":
    raise SystemExit(main())

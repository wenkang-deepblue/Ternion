"""
Entry point for running Ternion as a module.

Usage:
    python -m ternion
    # or
    ternion (if installed)
"""

from textwrap import dedent

import uvicorn

from ternion.core.config import (
    DEFAULT_BACKEND_PORT,
    get_default_local_host,
    normalize_port,
    settings,
)
from ternion.core.config_store import get_config_store
from ternion.utils.logging import setup_logging


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


def main() -> None:
    """Start the Ternion server."""
    setup_logging(settings.server.log_level)

    config_store = get_config_store()
    user_config = config_store.load()
    backend_port = normalize_port(
        getattr(user_config.ports, "backend", DEFAULT_BACKEND_PORT),
        DEFAULT_BACKEND_PORT,
    )

    emit_startup_message(backend_port)

    uvicorn.run(
        "ternion.server.app:app",
        host=settings.server.host,
        port=backend_port,
        reload=False,
        log_level=settings.server.log_level.lower(),
    )


if __name__ == "__main__":
    main()

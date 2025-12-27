"""
Entry point for running Ternion as a module.

Usage:
    python -m ternion
    # or
    ternion (if installed)
"""

import uvicorn

from ternion.core.config import settings
from ternion.core.config_store import get_config_store
from ternion.utils.logging import setup_logging


def main() -> None:
    """Start the Ternion server."""
    setup_logging(settings.server.log_level)

    # Load user-configured ports from config store
    config_store = get_config_store()
    user_config = config_store.load()
    backend_port = user_config.ports.backend

    uvicorn.run(
        "ternion.server.app:app",
        host=settings.server.host,
        port=backend_port,
        reload=False,
        log_level=settings.server.log_level.lower(),
    )


if __name__ == "__main__":
    main()

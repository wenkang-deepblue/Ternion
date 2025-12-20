"""
Entry point for running Ternion as a module.

Usage:
    python -m ternion
    # or
    ternion (if installed)
"""

import uvicorn

from ternion.core.config import settings
from ternion.utils.logging import setup_logging


def main() -> None:
    """Start the Ternion server."""
    setup_logging(settings.server.log_level)

    uvicorn.run(
        "ternion.server.app:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=False,
        log_level=settings.server.log_level.lower(),
    )


if __name__ == "__main__":
    main()

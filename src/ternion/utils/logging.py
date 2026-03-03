"""
Logging configuration for Ternion.

Sets up structured logging using structlog with optional file output.
"""

import logging
import sys

import structlog
from rich.console import Console
from rich.logging import RichHandler


def setup_logging(
    level: str = "info",
    log_file: str | None = None,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Log level (debug, info, warning, error)
        log_file: Optional path to log file
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [
        RichHandler(
            console=Console(stderr=True),
            show_time=True,
            show_path=False,
            rich_tracebacks=True,
        )
    ]

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        handlers.append(file_handler)

    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Return a structlog logger instance for the given name.

    Args:
        name: Logger name, usually `__name__`.

    Returns:
        A bound logger instance.
    """
    return structlog.get_logger(name)

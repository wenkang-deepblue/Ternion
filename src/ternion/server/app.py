"""
FastAPI application for Ternion gateway.

Provides the main application instance with middleware and exception handlers.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ternion import __version__
from ternion.core.config_store import config_store
from ternion.core.exceptions import TernionError
from ternion.core.models import ErrorDetail, ErrorResponse
from ternion.server.control_routes import router as control_router
from ternion.server.model_catalog_refresh import run_model_catalog_refresh_scheduler
from ternion.server.routes import router
from ternion.utils.log_manager import log_manager

logger = structlog.get_logger(__name__)


def get_allowed_origins() -> list[str]:
    """
    Build CORS allowed origins based on user configuration.

    Returns:
        Origins for localhost and 127.0.0.1 on the configured web port,
        plus any user-defined extra origins (for LAN access scenarios).
    """
    config = config_store.load()
    web_port = config.ports.web

    # Default local origins
    origins = [
        f"http://localhost:{web_port}",
        f"http://127.0.0.1:{web_port}",
    ]

    # Add user-configured extra origins for advanced LAN access scenarios.
    # Format: user provides IP like "192.168.1.100", we build full origin
    for extra in config.cors_extra_origins:
        if extra and not extra.startswith("http"):
            # User provided just an IP/hostname, add with current web port
            origins.append(f"http://{extra}:{web_port}")
        elif extra:
            # User provided full origin (advanced usage)
            origins.append(extra)

    return origins


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan: logs startup banner with version/CORS info, emits
    lifecycle events for the Observability panel, and logs shutdown.

    Uses the modern FastAPI lifespan pattern.

    Args:
        _app: The FastAPI application instance.

    Yields:
        None, yielding control to the application until shutdown.
    """
    # Startup - CORS origins were already fixed at import time; this is informational only.
    allowed_origins = get_allowed_origins()
    logger.info(
        "ternion_starting",
        version=__version__,
        cors_origins=allowed_origins,
    )
    log_manager.emit("INFO", "LIFECYCLE", f"Server started (version {__version__})")

    scheduler_stop_event = asyncio.Event()
    scheduler_task = asyncio.create_task(
        run_model_catalog_refresh_scheduler(scheduler_stop_event)
    )

    yield  # Application runs here

    # Shutdown
    scheduler_stop_event.set()
    try:
        await asyncio.wait_for(asyncio.shield(scheduler_task), timeout=5.0)
    except TimeoutError:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task
    except Exception:
        logger.warning("model_catalog_refresh_scheduler_shutdown_failed", exc_info=True)
    logger.info("ternion_shutting_down")
    log_manager.emit("INFO", "LIFECYCLE", "Server shutting down")


# Create FastAPI application with lifespan
app = FastAPI(
    title="Ternion",
    description="A local LLM proxy gateway for multi-model technical discussions",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS origins are computed once at process start and fixed for the process lifetime.
# Changing port configuration via the Control Panel requires a server restart to take effect.
# Only allows requests from configured local origins, not arbitrary websites.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)
# Compatibility alias: Some clients accidentally double-append "/v1" to the configured
# base URL, resulting in requests like "/v1/v1/chat/completions". Including the same
# router under prefix="/v1" makes those paths work without changing user settings.
app.include_router(router, prefix="/v1", include_in_schema=False)
app.include_router(control_router)  # Control Panel API


@app.exception_handler(TernionError)
async def ternion_error_handler(request: Request, exc: TernionError) -> JSONResponse:
    """Handle Ternion-specific exceptions.

    Args:
        request: The FastAPI request object.
        exc: The TernionError exception instance.

    Returns:
        A JSON response containing the error details.
    """
    logger.error(
        "ternion_error",
        error=exc.message,
        status_code=exc.status_code,
        path=request.url.path,
    )
    log_manager.emit("ERROR", "ERROR", f"{exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(
                message=exc.message,
                type="ternion_error",
            )
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handle request validation errors.

    Returns a simplified OpenAI-compatible JSON error instead of Pydantic's
    default 422 with a detail array, because Cursor does not display the
    raw Pydantic format to users.

    Args:
        request: The FastAPI request object.
        exc: The RequestValidationError exception instance.

    Returns:
        A JSON response formatted for OpenAI compatibility.
    """
    # Build user-friendly error message from validation errors
    errors = exc.errors()
    if errors:
        # Format: "field_name: error_message"
        first_error = errors[0]
        loc = ".".join(str(x) for x in first_error.get("loc", ["unknown"]))
        msg = first_error.get("msg", "validation error")
        error_message = f"Validation error at '{loc}': {msg}"
    else:
        error_message = "Request validation failed"

    logger.warning(
        "validation_error",
        path=request.url.path,
        errors=errors,
    )
    log_manager.emit("ERROR", "VALIDATION", error_message)

    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error=ErrorDetail(
                message=error_message,
                type="invalid_request_error",
            )
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions.

    Args:
        request: The FastAPI request object.
        exc: The Exception instance.

    Returns:
        A generic internal error JSON response.
    """
    logger.exception(
        "unexpected_error",
        error=str(exc),
        path=request.url.path,
    )
    log_manager.emit("ERROR", "ERROR", str(exc))
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=ErrorDetail(
                message="An unexpected error occurred",
                type="internal_error",
            )
        ).model_dump(),
    )

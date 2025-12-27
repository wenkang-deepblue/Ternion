"""
FastAPI application for Ternion gateway.

Provides the main application instance with middleware and exception handlers.
"""

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ternion import __version__
from ternion.core.exceptions import TernionError
from ternion.core.models import ErrorDetail, ErrorResponse
from ternion.server.routes import router
from ternion.server.control_routes import router as control_router, log_manager

logger = structlog.get_logger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Ternion",
    description="A local LLM proxy gateway for multi-model technical discussions",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)
app.include_router(control_router)  # Control Panel API


@app.exception_handler(TernionError)
async def ternion_error_handler(request: Request, exc: TernionError) -> JSONResponse:
    """Handle Ternion-specific exceptions."""
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


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
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


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize resources on startup."""
    logger.info(
        "ternion_starting",
        version=__version__,
    )
    log_manager.emit("INFO", "LIFECYCLE", f"Server started (version {__version__})")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup resources on shutdown."""
    logger.info("ternion_shutting_down")
    log_manager.emit("INFO", "LIFECYCLE", "Server shutting down")


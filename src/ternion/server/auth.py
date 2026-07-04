"""
Bearer-token authentication for publicly exposed endpoints.

Ternion is designed to be reached by Cursor through a public HTTPS tunnel
(ngrok, Cloud Run, custom proxies). Without authentication, anyone holding
the tunnel URL could spend the user's LLM budget via /v1 or rewrite the
configuration via /api. This middleware closes that gap:

- Requests arriving through a proxy/tunnel (any Forwarded-family header
  present) must carry the installation's bearer token.
- Local direct requests (loopback client, no forwarding headers) are exempt,
  so localhost usage and the local Control Panel keep working without setup.
- Read-only probe endpoints (health, landing pages, docs, /panel assets)
  stay public: they expose no secrets and are needed for connectivity checks.

The token is generated once per installation (see
ConfigStore.ensure_auth_token), printed in the CLI startup banner, and
available in the Control Panel for copy/paste into Cursor's API key field.
"""

import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ternion.core.config_store import config_store

logger = structlog.get_logger(__name__)

# Presence of any of these headers means the request traversed a proxy or
# tunnel and therefore originates from outside the local machine.
_FORWARDED_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "forwarded")

# Client hosts considered local. "testclient" is Starlette's in-process test
# client default; real network connections always carry an IP here.
_LOCAL_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

# Paths that stay public: no secrets, needed for connectivity probes and the
# Control Panel SPA shell (the panel's /api calls are still protected).
_EXEMPT_EXACT_PATHS = {"/", "/health", "/v1", "/docs", "/redoc", "/openapi.json"}
_EXEMPT_PREFIXES = ("/panel",)


def is_local_direct_request(request: Request) -> bool:
    """
    Return whether a request came directly from the local machine.

    A request is local only when it carries no proxy-forwarding headers and
    its client host is a loopback address (tunnel agents forward from
    loopback but always add Forwarded-family headers).

    Args:
        request: The incoming request.

    Returns:
        True when the request is a trusted local direct connection.
    """
    for header in _FORWARDED_HEADERS:
        if header in request.headers:
            return False
    client = request.client
    host = (client.host if client else "") or ""
    return host in _LOCAL_CLIENT_HOSTS or host.startswith("127.")


def extract_bearer_token(request: Request) -> str:
    """
    Extract the bearer token from the Authorization header.

    Args:
        request: The incoming request.

    Returns:
        The token value, or an empty string when absent/malformed.
    """
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def is_protected_path(path: str, method: str) -> bool:
    """
    Return whether a request path requires authentication.

    Protected surfaces are the OpenAI-compatible API (chat/completions,
    responses, models — with and without the /v1 prefix) and the Control
    Panel API (/api). CORS preflight requests are always exempt.

    Args:
        path: The request path.
        method: The HTTP method.

    Returns:
        True when the path must be authenticated for non-local requests.
    """
    if method.upper() == "OPTIONS":
        return False
    normalized = path.rstrip("/") or "/"
    if normalized in _EXEMPT_EXACT_PATHS:
        return False
    for prefix in _EXEMPT_PREFIXES:
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return False
    if normalized.startswith("/api/") or normalized == "/api":
        return True
    if normalized.startswith("/v1/"):
        return True
    return normalized in {"/chat/completions", "/responses", "/models"} or normalized.startswith(
        ("/chat/", "/responses/")
    )


def _unauthorized_response() -> JSONResponse:
    """Build the OpenAI-compatible 401 response for rejected requests."""
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "message": (
                    "Invalid or missing API key. Use the Ternion access token shown in "
                    "the CLI startup banner (also available in the Control Panel) as "
                    "the API key."
                ),
                "type": "authentication_error",
                "code": "invalid_api_key",
            }
        },
    )


class AuthTokenMiddleware:
    """
    Pure ASGI middleware enforcing bearer-token auth on protected paths.

    Implemented at the ASGI level (not BaseHTTPMiddleware) so SSE streaming
    responses pass through without buffering.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if not is_protected_path(request.url.path, request.method):
            await self.app(scope, receive, send)
            return

        if is_local_direct_request(request):
            await self.app(scope, receive, send)
            return

        expected_token = str(getattr(config_store.load(), "auth_token", "") or "")
        provided_token = extract_bearer_token(request)
        if expected_token and provided_token == expected_token:
            await self.app(scope, receive, send)
            return

        logger.warning(
            "auth_token_rejected",
            path=request.url.path,
            has_token=bool(provided_token),
        )
        response = _unauthorized_response()
        await response(scope, receive, send)

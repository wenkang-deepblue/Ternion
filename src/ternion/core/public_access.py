"""
Canonical public-access URL helpers for Cursor connectivity guidance.
"""

import ipaddress
import os
from typing import Literal, TypedDict
from urllib.parse import urlparse, urlunparse

import httpx
import structlog

DeploymentEnvironment = Literal["local", "cloud_run"]
PublicAccessDetectionMethod = Literal["request_origin", "manual_config", "none", "ngrok_api"]
PublicAccessSource = Literal["config", "request_origin", "none", "ngrok_api"]
logger = structlog.get_logger(__name__)


class ResolvedPublicAccessState(TypedDict):
    """Resolved runtime public-access state for Control Panel responses."""

    deployment_environment: DeploymentEnvironment
    detection_method: PublicAccessDetectionMethod
    detected_public_base_url: str
    effective_public_base_url: str
    effective_source: PublicAccessSource


def normalize_public_base_url(raw: str) -> str:
    """Return a canonical public base URL for Cursor configuration guidance.

    Args:
        raw: Raw URL text provided by config, UI input, or runtime detection.

    Returns:
        A normalized HTTP(S) origin/path without a trailing slash. If the raw URL
        ends with `/v1`, that suffix is removed so Cursor guidance always uses the
        public root URL. Invalid or empty values return an empty string.
    """
    value = str(raw or "").strip()
    if not value:
        return ""

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""

    path = (parsed.path or "").rstrip("/")
    if path.endswith("/v1"):
        path = path[: -len("/v1")]

    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc,
            path,
            "",
            "",
            "",
        )
    ).rstrip("/")


def is_local_origin(raw: str) -> bool:
    """Return whether a candidate origin points to a local or non-public host.

    Args:
        raw: Candidate origin or base URL.

    Returns:
        True when the host is local-only, private, synthetic, or otherwise not
        suitable as a public Cursor base URL. False means the host looks public.
    """
    normalized = normalize_public_base_url(raw)
    if not normalized:
        return True

    hostname = str(urlparse(normalized).hostname or "").strip().lower().rstrip(".")
    if not hostname:
        return True

    if hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1", "testserver"}:
        return True

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return "." not in hostname

    return (
        ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_unspecified or ip.is_reserved
    )


def build_public_origin(scheme: str, host: str) -> str:
    """Build a public origin from request-derived scheme/host components.

    Args:
        scheme: Request scheme such as `https`. Only the first comma-separated
            value is considered.
        host: Request host or forwarded host, optionally including a port. Only
            the first comma-separated value is considered.

    Returns:
        A normalized public base URL, or an empty string if the origin is empty,
        invalid, or points to a local/non-public host.
    """
    normalized_scheme = str(scheme or "").split(",", 1)[0].strip().lower()
    normalized_host = str(host or "").split(",", 1)[0].strip()
    if not normalized_scheme or not normalized_host:
        return ""

    origin = normalize_public_base_url(f"{normalized_scheme}://{normalized_host}")
    if not origin or is_local_origin(origin):
        return ""
    return origin


def detect_deployment_environment() -> DeploymentEnvironment:
    """Detect the current deployment environment.

    Returns:
        ``cloud_run`` when the current process is running on Google Cloud Run.
        Otherwise returns ``local`` for local or self-hosted deployments.
    """
    return "cloud_run" if os.getenv("K_SERVICE") else "local"


def matches_backend_addr(addr: str, backend_port: int) -> bool:
    """Return whether an ngrok tunnel target matches the configured backend port.

    Args:
        addr: Raw tunnel target address from the ngrok local API.
        backend_port: Configured Ternion backend port.

    Returns:
        True when the address targets the local backend port through a supported
        localhost-style address. False otherwise.
    """
    normalized = str(addr or "").strip().lower().rstrip("/")
    if not normalized:
        return False

    if normalized == str(backend_port):
        return True

    if "://" not in normalized:
        normalized = f"http://{normalized}"

    parsed = urlparse(normalized)
    hostname = str(parsed.hostname or "").strip().lower()
    try:
        port = parsed.port
    except ValueError:
        return False
    return hostname in {"127.0.0.1", "localhost", "0.0.0.0"} and port == backend_port


def detect_ngrok_public_base_url(backend_port: int) -> tuple[str, PublicAccessDetectionMethod]:
    """Best-effort detect an ngrok public base URL for the backend port.

    Args:
        backend_port: Configured Ternion backend port.

    Returns:
        A tuple of `(public_base_url, detection_method)`. Returns an empty URL
        with `none` when ngrok is unavailable, malformed, or no matching HTTPS
        tunnel targets the backend port.
    """
    for api_base in ("http://127.0.0.1:4040", "http://localhost:4040"):
        try:
            response = httpx.get(f"{api_base}/api/tunnels", timeout=1.0)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.debug("ngrok_probe_failed", api_base=api_base, error=str(exc))
            continue

        if not isinstance(payload, dict):
            logger.debug(
                "ngrok_probe_invalid_payload",
                api_base=api_base,
                payload_type=type(payload).__name__,
            )
            continue

        tunnels = payload.get("tunnels", [])
        if not isinstance(tunnels, list):
            logger.debug(
                "ngrok_probe_invalid_tunnels",
                api_base=api_base,
                tunnels_type=type(tunnels).__name__,
            )
            continue

        for tunnel in tunnels:
            if not isinstance(tunnel, dict):
                continue
            if str(tunnel.get("proto") or "").strip().lower() != "https":
                continue

            config = tunnel.get("config") or {}
            if not isinstance(config, dict):
                continue
            if not matches_backend_addr(str(config.get("addr") or ""), backend_port):
                continue

            public_url = normalize_public_base_url(str(tunnel.get("public_url") or ""))
            if public_url:
                return public_url, "ngrok_api"

    return "", "none"


def resolve_public_access_state(
    config_value: str,
    *,
    request_origin: str = "",
    deployment_environment: DeploymentEnvironment | None = None,
    backend_port: int = 9110,
) -> ResolvedPublicAccessState:
    """Resolve runtime public-access state for the Control Panel.

    Priority depends on deployment environment. Cloud Run trusts the live public
    request origin over saved config because the effective service URL should
    reflect the current inbound endpoint. Local or tunnel-based deployments
    prefer a live public request origin, then best-effort ngrok detection, and
    finally fall back to explicit config.

    Args:
        config_value: Configured public base URL candidate.
        request_origin: Optional runtime-detected origin candidate.
        deployment_environment: Optional explicit deployment environment. When
            omitted, the current process environment is detected automatically.
        backend_port: Configured backend port used for ngrok tunnel matching in
            local deployments.

    Returns:
        A structured runtime state containing deployment environment, detection
        method, detected public URL, effective public URL, and effective source.
    """
    resolved_environment = deployment_environment or detect_deployment_environment()
    configured = normalize_public_base_url(config_value)
    detected_public_base_url = normalize_public_base_url(request_origin)

    if resolved_environment == "cloud_run":
        if detected_public_base_url:
            effective_public_base_url = detected_public_base_url
            effective_source: PublicAccessSource = "request_origin"
        elif configured:
            effective_public_base_url = configured
            effective_source = "config"
        else:
            effective_public_base_url = ""
            effective_source = "none"
    else:
        if detected_public_base_url:
            effective_public_base_url = detected_public_base_url
            effective_source = "request_origin"
        else:
            detected_public_base_url, _ = detect_ngrok_public_base_url(backend_port)
            if detected_public_base_url:
                effective_public_base_url = detected_public_base_url
                effective_source = "ngrok_api"
            elif configured:
                effective_public_base_url = configured
                effective_source = "config"
            else:
                effective_public_base_url = ""
                effective_source = "none"

    if effective_source == "config":
        detection_method: PublicAccessDetectionMethod = "manual_config"
    elif effective_source == "request_origin":
        detection_method = "request_origin"
    elif effective_source == "ngrok_api":
        detection_method = "ngrok_api"
    else:
        detection_method = "none"

    return {
        "deployment_environment": resolved_environment,
        "detection_method": detection_method,
        "detected_public_base_url": detected_public_base_url,
        "effective_public_base_url": effective_public_base_url,
        "effective_source": effective_source,
    }

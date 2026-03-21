"""
Canonical public-access URL helpers for Cursor connectivity guidance.
"""

import ipaddress
import os
from typing import Literal, TypedDict
from urllib.parse import urlparse, urlunparse

DeploymentEnvironment = Literal["local", "cloud_run"]
# `ngrok_api` is reserved for Step 3 local tunnel auto-detection.
PublicAccessDetectionMethod = Literal["request_origin", "manual_config", "none", "ngrok_api"]
PublicAccessSource = Literal["config", "request_origin", "none"]


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
        raw: Raw URL text provided by config, UI input, or future runtime detection.

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
        scheme: Request scheme such as `https`.
        host: Request host or forwarded host, optionally including a port.

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


def resolve_effective_public_base_url(
    config_value: str,
    *,
    request_origin: str = "",
) -> tuple[str, PublicAccessSource]:
    """Resolve the effective public base URL from currently available signals.

    Step 1 establishes the canonical URL semantics only. Configured values take
    precedence, while future request-origin detection can be threaded in later by
    passing `request_origin` explicitly.

    Args:
        config_value: Configured public base URL candidate.
        request_origin: Optional runtime-detected origin candidate.

    Returns:
        A tuple of `(effective_url, source)` where `source` indicates whether the
        resolved value came from config, request-origin detection, or no signal.
    """
    configured = normalize_public_base_url(config_value)
    if configured:
        return configured, "config"

    detected = normalize_public_base_url(request_origin)
    if detected:
        return detected, "request_origin"

    return "", "none"


def resolve_public_access_state(
    config_value: str,
    *,
    request_origin: str = "",
    deployment_environment: DeploymentEnvironment | None = None,
) -> ResolvedPublicAccessState:
    """Resolve runtime public-access state for the Control Panel.

    Args:
        config_value: Configured public base URL candidate.
        request_origin: Optional runtime-detected origin candidate.
        deployment_environment: Optional explicit deployment environment. When
            omitted, the current process environment is detected automatically.

    Returns:
        A structured runtime state containing deployment environment, detection
        method, detected public URL, and effective public URL.
    """
    configured = normalize_public_base_url(config_value)
    detected_public_base_url = normalize_public_base_url(request_origin)
    if configured:
        effective_public_base_url = configured
        effective_source: PublicAccessSource = "config"
    elif detected_public_base_url:
        effective_public_base_url = detected_public_base_url
        effective_source = "request_origin"
    else:
        effective_public_base_url = ""
        effective_source = "none"

    if effective_source == "config":
        detection_method: PublicAccessDetectionMethod = "manual_config"
    elif detected_public_base_url:
        detection_method = "request_origin"
    else:
        detection_method = "none"

    return {
        "deployment_environment": deployment_environment or detect_deployment_environment(),
        "detection_method": detection_method,
        "detected_public_base_url": detected_public_base_url,
        "effective_public_base_url": effective_public_base_url,
        "effective_source": effective_source,
    }

"""
Canonical public-access URL helpers for Cursor connectivity guidance.
"""

import ipaddress
from typing import Literal
from urllib.parse import urlparse, urlunparse

PublicAccessSource = Literal["config", "request_origin", "none"]


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

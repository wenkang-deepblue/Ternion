"""
Secret redaction utilities for Ternion.

Provides functions to sanitize API keys and other secrets from log messages
before they are written to files or displayed in the UI.
"""

import re

# Patterns for common API key formats
# Each pattern is a tuple of (regex_pattern, replacement_description)
# Note: Order matters! More specific patterns must come before generic ones.
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Anthropic API keys: sk-ant-... (must come before OpenAI pattern)
    (re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}"), r"[REDACTED:Anthropic-Key]"),
    # OpenAI API keys: sk-... and sk-proj-... (includes hyphen for new formats)
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), r"[REDACTED:OpenAI-Key]"),
    # Google API keys: AIza... (39 chars total)
    (re.compile(r"AIza[A-Za-z0-9_\-]{30,}"), r"[REDACTED:Google-Key]"),
    # Generic bearer tokens in error messages
    (re.compile(r"Bearer\s+[A-Za-z0-9\-_.]+"), r"Bearer [REDACTED]"),
    # API key in URL query params: api_key=..., key=..., apikey=...
    (re.compile(r"(api_?key|key)=[A-Za-z0-9\-_]{10,}", re.IGNORECASE), r"\1=[REDACTED]"),
]


def redact_secrets(text: str) -> str:
    """
    Redact known secret patterns from text.

    This function scans text for known API key patterns and replaces them
    with redaction placeholders. Used to sanitize log messages before
    they are written to the observability panel or log files.

    Args:
        text: Input text that may contain secrets

    Returns:
        Text with secrets replaced by redaction placeholders

    Example:
        >>> redact_secrets("Error with key sk-abc123...")
        "Error with key [REDACTED:OpenAI-Key]"
    """
    if not text:
        return text

    result = text
    for pattern, replacement in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)

    return result


def contains_secret_pattern(text: str) -> bool:
    """
    Check if text contains any known secret patterns.

    Useful for validation and testing purposes.

    Args:
        text: Input text to check

    Returns:
        True if any secret pattern is found
    """
    if not text:
        return False

    return any(pattern.search(text) for pattern, _ in _SECRET_PATTERNS)

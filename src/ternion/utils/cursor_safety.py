"""
Cursor Safety utilities for Ternion output.

Provides sanitization functions to prevent triggering Cursor's auto-apply logic
when displaying reports and handoff packages in the Cursor IDE.
"""

import re

ZWSP = "\u200b"  # Zero-width space for breaking trigger patterns

# Patterns that trigger Cursor's code/patch detection
PATCH_TRIGGERS = [
    "```",
    "~~~",
    "*** Begin Patch",
    "*** End Patch",
    "*** Update File:",
    "*** Add File:",
    "diff --git",
]

# Regex to match common executable command line prefixes
COMMAND_LINE_RE = re.compile(
    r"(?m)^(\s*)(sudo\s+)?(bash|sh|zsh|python|python3|pip|pip3|npm|pnpm|yarn|curl|wget|brew)\b"
)


def sanitize_for_cursor_display(text: str) -> str:
    """
    Sanitize text for safe display in Cursor without triggering auto-apply.

    Preserves newlines and Markdown structure while breaking trigger patterns
    by inserting zero-width spaces.

    Use this for:
    - Report stage output
    - Handoff package output
    - Clarification responses

    Args:
        text: Raw text to sanitize

    Returns:
        Sanitized text safe for Cursor display
    """
    if not text:
        return ""

    out = text

    # Break code fence triggers
    out = out.replace("```", f"`{ZWSP}`{ZWSP}`")
    out = out.replace("~~~", f"~{ZWSP}~{ZWSP}~")

    # Break patch triggers
    out = out.replace("*** Begin Patch", f"**{ZWSP}* Begin Patch")
    out = out.replace("*** End Patch", f"**{ZWSP}* End Patch")
    out = out.replace("*** Update File:", f"**{ZWSP}* Update File:")
    out = out.replace("*** Add File:", f"**{ZWSP}* Add File:")
    out = out.replace("diff --git", f"diff{ZWSP} --git")

    # Break leading diff markers (+++/--- at line start)
    out = re.sub(
        r"(?m)^(\+\+\+|---)\s",
        lambda m: m.group(1)[0] + ZWSP + m.group(1)[1:] + " ",
        out,
    )

    # Break command line prefixes
    out = COMMAND_LINE_RE.sub(lambda m: m.group(1) + ZWSP + (m.group(2) or "") + m.group(3), out)

    return out


def sanitize_for_preview(text: str, max_length: int = 100) -> str:
    """
    Sanitize text for short preview display in thinking logs.

    Truncates text, replaces newlines with spaces, and applies full trigger
    sanitization via sanitize_for_cursor_display. This ensures previews don't
    accidentally contain Cursor auto-apply triggers.

    Args:
        text: Raw text to sanitize
        max_length: Maximum length of preview

    Returns:
        Sanitized preview string
    """
    if not text:
        return ""

    # Truncate and replace newlines for compact display
    preview = text[:max_length].replace("\n", " ")
    if len(text) > max_length:
        preview += "..."

    # Apply full trigger sanitization to ensure safety
    return sanitize_for_cursor_display(preview)


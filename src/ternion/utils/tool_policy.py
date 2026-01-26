"""
Shared tool policy constants for the tool loop.

These constants are used by:
- prompt-time tool filtering in workflow nodes, and
- server-side enforcement in API routes.

Keeping a single source of truth avoids allowlist drift that can cause either
unexpected tool blocks (false positives) or unintended allow expansions.
"""

from __future__ import annotations

EXECUTION_ALLOWED_TOOL_CANONICAL: frozenset[str] = frozenset(
    {
        "write",
        "writefile",
        "searchreplace",
        "applypatch",
        "delete",
        "deletefile",
        "editnotebook",
        "runterminalcmd",
        "shell",
        "bash",
    }
)

SHELL_TOOL_CANONICAL: frozenset[str] = frozenset({"runterminalcmd", "shell", "bash"})


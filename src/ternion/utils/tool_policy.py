"""
Shared tool policy constants for the tool loop.

These constants are used by:
- prompt-time tool filtering in workflow nodes, and
- server-side enforcement in API routes.

Keeping a single source of truth avoids allowlist drift that can cause either
unexpected tool blocks (false positives) or unintended allow expansions.

Default policy:
- For Execution/Optimizer stages, tools are **deny-by-default**.
- A tool is permitted only if its canonical name is present in
  EXECUTION_ALLOWED_TOOL_CANONICAL.
"""

from __future__ import annotations

EXECUTION_ALLOWED_TOOL_CANONICAL: frozenset[str] = frozenset(
    {
        "write",
        "writefile",
        "strreplace",
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

# Explicit read/search/web tools that must never be available in Execution/Optimizer.
# Canonicalization is done via `re.sub(r"[^a-z0-9]+", "", name.lower())`.
READ_SEARCH_TOOL_CANONICAL: frozenset[str] = frozenset(
    {
        "read",
        "readfile",
        "grep",
        "glob",
        "semanticsearch",
        "websearch",
        "webfetch",
    }
)

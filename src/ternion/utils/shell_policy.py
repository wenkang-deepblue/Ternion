"""
Shell command policy for Execution/Optimizer verification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_ALLOWLIST_PATTERNS = [
    r"^(python3?|py)\s+-m\s+pytest(\s+.*)?$",
    r"^pytest(\s+.*)?$",
    r"^(python3?|py)\s+-m\s+ruff(\s+.*)?$",
    r"^ruff(\s+.*)?$",
    r"^(python3?|py)\s+-m\s+black(\s+.*)?$",
    r"^black(\s+.*)?$",
    r"^npm\s+(run\s+)?(lint|test|format|typecheck|check)(\s+.*)?$",
    r"^pnpm\s+(run\s+)?(lint|test|format|typecheck|check)(\s+.*)?$",
    r"^yarn\s+(lint|test|format|typecheck|check)(\s+.*)?$",
    r"^make\s+(lint|test|format|check)(\s+.*)?$",
    r"^(python3?|py)\s+-m\s+ternion\.utils\.file_meta(\s+.*)?$",
]

_BLOCKLIST_PATTERNS = [
    r"\b(cat|head|tail|less|more)\b",
    r"\b(grep|egrep|fgrep|rg|ripgrep|find|fd|locate)\b",
    r"\b(ls|tree)\b",
    r"\b(sed|awk|perl)\b",
    r"\bpython3?\s+-c\b",
    r"\bnode\s+-e\b",
    r"\b(sh|bash|zsh)\s+-c\b",
]

_SHELL_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||;)\s*")


@dataclass(frozen=True)
class ShellPolicyResult:
    allowed: bool
    reason: str


def evaluate_shell_command(command: str) -> ShellPolicyResult:
    """
    Determine whether a shell command is allowed for verification.
    """
    if not isinstance(command, str) or not command.strip():
        return ShellPolicyResult(False, "empty command")

    if _has_command_substitution(command):
        return ShellPolicyResult(False, "command substitution is not allowed")

    if _has_pipe_or_redirect(command):
        return ShellPolicyResult(False, "pipes or redirects are not allowed")

    parts = [p.strip() for p in _SHELL_SPLIT_RE.split(command) if p.strip()]
    if not parts:
        return ShellPolicyResult(False, "empty command")

    for part in parts:
        if _matches_any(part, _BLOCKLIST_PATTERNS):
            return ShellPolicyResult(False, "read/search command not allowed")
        if not _matches_any(part, _ALLOWLIST_PATTERNS):
            return ShellPolicyResult(False, "command not in verification allowlist")

    return ShellPolicyResult(True, "allowed")


def _has_pipe_or_redirect(command: str) -> bool:
    in_pipe = False
    idx = 0
    while idx < len(command):
        ch = command[idx]
        if ch == "|":
            if idx + 1 < len(command) and command[idx + 1] == "|":
                idx += 2
                continue
            in_pipe = True
            break
        idx += 1
    return in_pipe or ">" in command or "<" in command


def _has_command_substitution(command: str) -> bool:
    return "`" in command or "$(" in command


def _matches_any(text: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE):
            return True
    return False

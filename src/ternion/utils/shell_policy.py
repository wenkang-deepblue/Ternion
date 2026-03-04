"""
Shell command policy for Execution/Optimizer verification.

Implements a deny-by-default policy: only explicitly allowlisted commands
(test runners, linters, version checks) are permitted. Pipes, redirects,
command substitution, and read/search tools are blocked.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

_ALLOWED_SCRIPT_RE = re.compile(
    r"^(?:lint|test|format|typecheck|check|build)(?:[:._-].+)?$",
    flags=re.IGNORECASE | re.UNICODE,
)

_DIR_OPT_KEYS = {"--prefix", "--cwd", "--dir", "-C"}

# Commands that could exfiltrate file content or serve as read primitives.
_BLOCKLIST_PATTERNS = [
    r"\b(cat|head|tail|less|more)\b",
    r"\b(grep|egrep|fgrep|rg|ripgrep|find|fd|locate)\b",
    r"\b(ls|tree)\b",
    r"\b(sed|awk|perl)\b",
    r"\bpython3?\s+-c\b",
    r"\bnode\s+-e\b",
    r"\b(sh|bash|zsh)\s+-c\b",
]


@dataclass(frozen=True)
class ShellPolicyResult:
    """Result of evaluating whether a shell command is allowed."""

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

    parts = _split_shell_parts(command)
    if not parts:
        return ShellPolicyResult(False, "empty command")

    for part in parts:
        if _matches_any(part, _BLOCKLIST_PATTERNS):
            return ShellPolicyResult(False, "read/search command not allowed")
        allowed, reason = _is_allowed_verification_part(part)
        if not allowed:
            return ShellPolicyResult(False, reason)

    return ShellPolicyResult(True, "allowed")


def _split_shell_parts(command: str) -> list[str]:
    """
    Split a shell command into sequential parts by `&&`, `||`, or `;`.

    This is quote-aware to avoid splitting inside quoted strings.
    """
    parts: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    escape = False
    idx = 0

    def flush() -> None:
        s = "".join(buf).strip()
        if s:
            parts.append(s)
        buf.clear()

    while idx < len(command):
        ch = command[idx]
        if escape:
            buf.append(ch)
            escape = False
            idx += 1
            continue

        if ch == "\\" and not in_single:
            escape = True
            buf.append(ch)
            idx += 1
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
            idx += 1
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            idx += 1
            continue

        if not in_single and not in_double:
            if command.startswith("&&", idx) or command.startswith("||", idx):
                flush()
                idx += 2
                continue
            if ch == ";":
                flush()
                idx += 1
                continue

        buf.append(ch)
        idx += 1

    flush()
    return parts


def _has_pipe_or_redirect(command: str) -> bool:
    in_single = False
    in_double = False
    escape = False
    idx = 0
    while idx < len(command):
        ch = command[idx]

        if escape:
            escape = False
            idx += 1
            continue

        if ch == "\\" and not in_single:
            escape = True
            idx += 1
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
            idx += 1
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            idx += 1
            continue

        if not in_single and not in_double:
            if ch == "|":
                # Treat `||` as a sequential operator, not a pipe.
                if idx + 1 < len(command) and command[idx + 1] == "|":
                    idx += 2
                    continue
                return True
            if ch in {">", "<"}:
                return True

        idx += 1
    return False


def _has_command_substitution(command: str) -> bool:
    return "`" in command or "$(" in command


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE) for pattern in patterns)


def _is_allowed_verification_part(part: str) -> tuple[bool, str]:
    tokens = _safe_shlex_split(part)
    if not tokens:
        return False, "empty command"

    head = tokens[0].strip().lower()
    if head == "cd":
        return _allow_cd(tokens)
    if head == "pwd":
        if len(tokens) == 1:
            return True, "allowed"
        return False, "command not in verification allowlist"
    if head in {"python", "python3", "py"}:
        return _allow_python(tokens)
    if head == "node":
        return _allow_version_only(tokens)
    if head in {"npm", "pnpm", "yarn"}:
        return _allow_node_verification(tokens)
    if head in {"pytest", "ruff", "black"}:
        return True, "allowed"
    if head == "make":
        return _allow_make(tokens)
    return False, "command not in verification allowlist"


def _safe_shlex_split(text: str) -> list[str]:
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        # Fallback: best-effort split (keeps policy deterministic).
        return [t for t in text.split() if t]


def _allow_cd(tokens: list[str]) -> tuple[bool, str]:
    if len(tokens) != 2:
        return False, "command not in verification allowlist"
    target = tokens[1].strip()
    if not _is_safe_repo_relative_path(target):
        return False, "unsafe directory change"
    return True, "allowed"


def _is_safe_repo_relative_path(path: str) -> bool:
    """
    Ensure a directory path stays within the current workspace/repo.

    This intentionally allows any repo-internal directory (project-dependent),
    while preventing traversal to parent directories or absolute paths.
    """
    if not isinstance(path, str) or not path.strip():
        return False
    s = path.strip()
    if s.startswith(("/", "\\", "~")):
        return False
    if "$" in s:
        return False

    normalized = s.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p]
    for part in parts:
        if part == ".":
            continue
        if part == "..":
            return False
    return True


def _allow_version_only(tokens: list[str]) -> tuple[bool, str]:
    if len(tokens) == 2 and tokens[1] in {"-v", "--version", "-V"}:
        return True, "allowed"
    return False, "command not in verification allowlist"


def _allow_python(tokens: list[str]) -> tuple[bool, str]:
    if len(tokens) == 2 and tokens[1] in {"-V", "--version"}:
        return True, "allowed"

    if len(tokens) >= 3 and tokens[1] == "-m":
        module = tokens[2].strip().lower()
        if module in {"pytest", "ruff", "black", "ternion.utils.file_meta"}:
            return True, "allowed"
    return False, "command not in verification allowlist"


def _allow_make(tokens: list[str]) -> tuple[bool, str]:
    targets: list[str] = []
    idx = 1
    while idx < len(tokens):
        tok = tokens[idx]
        if tok in _DIR_OPT_KEYS:
            if idx + 1 >= len(tokens):
                return False, "unsafe directory change"
            if not _is_safe_repo_relative_path(tokens[idx + 1]):
                return False, "unsafe directory change"
            idx += 2
            continue
        inline_dir = _extract_inline_dir_opt_value(tok)
        if inline_dir is not None:
            if not _is_safe_repo_relative_path(inline_dir):
                return False, "unsafe directory change"
            idx += 1
            continue
        if tok.startswith("-"):
            idx += 1
            continue
        targets.append(tok)
        idx += 1

    if not targets:
        return False, "command not in verification allowlist"

    if all(_ALLOWED_SCRIPT_RE.match(t or "") for t in targets):
        return True, "allowed"
    return False, "command not in verification allowlist"


def _allow_node_verification(tokens: list[str]) -> tuple[bool, str]:
    if len(tokens) == 2 and tokens[1] in {"-v", "--version"}:
        return True, "allowed"

    script = _extract_pkg_manager_script(tokens)
    if not script:
        return False, "command not in verification allowlist"
    if _ALLOWED_SCRIPT_RE.match(script):
        return True, "allowed"
    return False, "command not in verification allowlist"


def _extract_pkg_manager_script(tokens: list[str]) -> str | None:
    """
    Extract a verification script name from npm/pnpm/yarn invocations.

    Supported patterns (examples):
    - npm run -s typecheck
    - npm --prefix web run typecheck
    - pnpm -C web run typecheck
    - yarn --cwd web typecheck
    """
    idx = 1

    def skip_dir_opt(i: int) -> int | None:
        if i + 1 >= len(tokens):
            return None
        if not _is_safe_repo_relative_path(tokens[i + 1]):
            return None
        return i + 2

    # Skip global flags/options (including directory selectors).
    while idx < len(tokens):
        tok = tokens[idx]
        if tok in _DIR_OPT_KEYS:
            next_idx = skip_dir_opt(idx)
            if next_idx is None:
                return None
            idx = next_idx
            continue
        inline_dir = _extract_inline_dir_opt_value(tok)
        if inline_dir is not None:
            if not _is_safe_repo_relative_path(inline_dir):
                return None
            idx += 1
            continue
        if tok.startswith("-"):
            idx += 1
            continue
        break

    if idx >= len(tokens):
        return None

    sub = tokens[idx]
    idx += 1

    if sub in {"run", "run-script"}:
        # Skip run flags/options before the script name.
        while idx < len(tokens):
            tok = tokens[idx]
            if tok in _DIR_OPT_KEYS:
                next_idx = skip_dir_opt(idx)
                if next_idx is None:
                    return None
                idx = next_idx
                continue
            inline_dir = _extract_inline_dir_opt_value(tok)
            if inline_dir is not None:
                if not _is_safe_repo_relative_path(inline_dir):
                    return None
                idx += 1
                continue
            if tok.startswith("-"):
                idx += 1
                continue
            return tok
        return None

    return sub


def _extract_inline_dir_opt_value(token: str) -> str | None:
    """
    Extract inline directory option values such as:
    - --prefix=web
    - --cwd=web
    - --dir=web
    - -Cweb
    - -C=web
    """
    if not isinstance(token, str) or not token:
        return None
    for key in ("--prefix", "--cwd", "--dir"):
        prefix = f"{key}="
        if token.startswith(prefix):
            return token[len(prefix) :]
    if token.startswith("-C") and token != "-C":
        value = token[2:]
        if value.startswith("="):
            value = value[1:]
        return value
    return None

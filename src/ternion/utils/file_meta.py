"""
Controlled file metadata inspection.

This module is intended for a very small, security-sensitive use case:
reporting file existence and basic metadata (size/mtime) for a repository-internal
path, without exposing a general-purpose shell read capability.

It is designed to be executed via:

    python -m ternion.utils.file_meta <path>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    """
    Best-effort repository root detection by walking upwards for a .git directory.
    """
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def _resolve_repo_internal_path(repo_root: Path, raw_path: str) -> Path | None:
    """
    Resolve a path and ensure it stays inside the repository root.

    Returns:
        The resolved absolute path if it is repo-internal; otherwise None.
    """
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None

    p = Path(raw_path).expanduser()
    if not p.is_absolute():
        p = repo_root / p
    try:
        resolved = p.resolve(strict=False)
    except Exception:
        resolved = p.absolute()

    try:
        resolved.relative_to(repo_root)
    except Exception:
        return None
    return resolved


def _get_file_meta(repo_root: Path, raw_path: str) -> dict[str, object]:
    """
    Return a JSON-serializable metadata dict for a repo-internal path.

    Output keys are intentionally minimal for policy reasons.
    """
    resolved = _resolve_repo_internal_path(repo_root, raw_path)
    if resolved is None:
        return {"exists": False, "size": None, "mtime": None}

    exists = resolved.exists()
    if not exists:
        return {"exists": False, "size": None, "mtime": None}

    if not resolved.is_file():
        return {"exists": True, "size": None, "mtime": None}

    try:
        st = resolved.stat()
        return {
            "exists": True,
            "size": int(st.st_size),
            "mtime": float(st.st_mtime),
        }
    except Exception:
        return {"exists": True, "size": None, "mtime": None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ternion.utils.file_meta",
        add_help=True,
    )
    parser.add_argument(
        "path",
        help="Repository-internal path (relative to repo root, or an absolute path inside the repo).",
    )
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    payload = _get_file_meta(repo_root, args.path)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


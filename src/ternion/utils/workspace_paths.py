"""
Workspace path helpers shared by API and workflow layers.

These helpers explicitly separate client-declared workspace semantics from
best-effort local filesystem access on the server.
"""

import ntpath
import posixpath
import re
from pathlib import Path
from typing import Literal

WorkspacePathStyle = Literal["posix", "windows", ""]

_WINDOWS_DRIVE_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def detect_path_style(path_str: str) -> WorkspacePathStyle:
    """Detect whether a declared path uses POSIX or Windows semantics."""
    raw = str(path_str or "").strip().strip("`'\"")
    if not raw:
        return ""
    if _WINDOWS_DRIVE_ABSOLUTE_RE.match(raw) or raw.startswith("\\\\"):
        return "windows"
    if raw.startswith("/"):
        return "posix"
    return ""


def normalize_declared_workspace_path(path_str: str) -> tuple[str, WorkspacePathStyle]:
    """Normalize an absolute client-declared path without touching the filesystem."""
    raw = str(path_str or "").strip().strip("`'\"")
    style = detect_path_style(raw)
    if not raw or not style:
        return "", ""
    path_mod = ntpath if style == "windows" else posixpath
    return path_mod.normpath(raw), style


def resolve_local_workspace_root(client_workspace_root: str) -> str:
    """Resolve a client workspace to a locally accessible server path when possible."""
    root = str(client_workspace_root or "").strip()
    if not root:
        return ""
    candidate = Path(root).expanduser()
    try:
        resolved = candidate.resolve()
    except Exception:
        return ""
    if resolved.exists() and resolved.is_dir():
        return str(resolved)
    return ""


def normalize_workspace_target_path(
    path_str: str,
    *,
    workspace_root: str = "",
    workspace_path_style: WorkspacePathStyle = "",
) -> str | None:
    """Normalize a client-side target path using declared workspace semantics."""
    target_raw = str(path_str or "").strip().strip("`'\"")
    if not target_raw:
        return None
    normalized_root, root_style = normalize_declared_workspace_path(workspace_root)
    style = workspace_path_style or root_style or detect_path_style(target_raw)
    if not style:
        return None
    path_mod = ntpath if style == "windows" else posixpath
    target_style = detect_path_style(target_raw)
    if target_style and target_style != style:
        return None
    if target_style:
        return path_mod.normpath(target_raw)
    if not normalized_root:
        return None
    return path_mod.normpath(path_mod.join(normalized_root, target_raw))


def workspace_relative_path(
    path_str: str,
    *,
    workspace_root: str,
    workspace_path_style: WorkspacePathStyle = "",
) -> str | None:
    """Return a workspace-relative path if the target stays within the boundary."""
    normalized_root, root_style = normalize_declared_workspace_path(workspace_root)
    style = workspace_path_style or root_style
    if not normalized_root or not style:
        return None
    normalized_target = normalize_workspace_target_path(
        path_str,
        workspace_root=normalized_root,
        workspace_path_style=style,
    )
    if not normalized_target:
        return None
    path_mod = ntpath if style == "windows" else posixpath
    try:
        relative = path_mod.relpath(normalized_target, normalized_root)
    except Exception:
        return None
    if relative in {"", "."}:
        return ""
    relative = relative.replace("\\", "/")
    if relative == ".." or relative.startswith("../"):
        return None
    return relative


def normalize_local_file_path(
    path_str: str,
    *,
    workspace_root: str,
    workspace_path_style: WorkspacePathStyle = "",
    local_workspace_root: str = "",
) -> str | None:
    """Map a client-visible target path onto a locally accessible server path."""
    local_root = str(local_workspace_root or "").strip()
    if not local_root:
        return None
    relative = workspace_relative_path(
        path_str,
        workspace_root=workspace_root,
        workspace_path_style=workspace_path_style,
    )
    if relative is None:
        return None
    root = Path(local_root).expanduser()
    if relative == "":
        candidate = root
    else:
        candidate = root.joinpath(*[part for part in relative.split("/") if part])
    try:
        resolved_root = root.resolve()
    except Exception:
        resolved_root = root
    try:
        resolved_candidate = candidate.resolve()
    except Exception:
        resolved_candidate = candidate
    try:
        resolved_candidate.relative_to(resolved_root)
    except Exception:
        return None
    return str(resolved_candidate)


def render_workspace_path(
    path_str: str,
    *,
    workspace_root: str,
    workspace_path_style: WorkspacePathStyle = "",
) -> str:
    """Render a path relative to the declared workspace when possible."""
    relative = workspace_relative_path(
        path_str,
        workspace_root=workspace_root,
        workspace_path_style=workspace_path_style,
    )
    if relative is None:
        return str(path_str)
    return relative or "."

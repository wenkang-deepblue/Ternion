"""Shared safety primitives for workspace-scoped cross-session memory."""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ternion.utils.evidence_chain import EvidenceItem
from ternion.utils.workspace_paths import (
    normalize_declared_workspace_path,
    normalize_local_file_path,
    workspace_relative_path,
)

_NUMBERED_LINE_RE = re.compile(r"^\s*(\d+)\|(.*)$")


@dataclass(frozen=True)
class CurrentWorkspaceFile:
    """Current local file bytes and metadata used for memory validation."""

    content_hash: str
    size: int
    mtime_ns: int
    lines: list[str]


def workspace_identity(workspace_root: str, workspace_path_style: str) -> str:
    """Build the stable storage identity for a declared workspace.

    Args:
        workspace_root: Client-declared workspace root.
        workspace_path_style: Declared client path style.

    Returns:
        A stable workspace hash, or an empty string when the root is unresolved.
    """
    normalized, detected_style = normalize_declared_workspace_path(workspace_root)
    style = str(workspace_path_style or detected_style or "")
    if not normalized or not style:
        return ""
    identity_path = normalized.lower() if style == "windows" else normalized
    return hashlib.sha256(f"{style}\n{identity_path}".encode()).hexdigest()[:24]


def relative_workspace_path(
    path: str,
    *,
    workspace_root: str,
    workspace_path_style: str,
) -> str:
    """Normalize a path into a workspace-relative memory key.

    Args:
        path: Relative or absolute candidate path.
        workspace_root: Client-declared workspace root.
        workspace_path_style: Declared client path style.

    Returns:
        A slash-normalized relative path, or an empty string when out of scope.
    """
    relative = workspace_relative_path(
        str(path or ""),
        workspace_root=workspace_root,
        workspace_path_style=workspace_path_style,
    )
    if relative is None or relative == "":
        return ""
    return relative.replace("\\", "/")


def read_current_workspace_file(
    relative_path: str,
    *,
    workspace_root: str,
    local_workspace_root: str,
    workspace_path_style: str,
    max_file_bytes: int,
) -> CurrentWorkspaceFile | None:
    """Read and hash a bounded file inside a locally verified workspace.

    Args:
        relative_path: Workspace-relative source path.
        workspace_root: Client-declared workspace root.
        local_workspace_root: Server-local path for the same workspace.
        workspace_path_style: Declared client path style.
        max_file_bytes: Maximum number of source bytes accepted.

    Returns:
        Current file content and metadata, or ``None`` when verification fails.
    """
    local_path = normalize_local_file_path(
        relative_path,
        workspace_root=workspace_root,
        workspace_path_style=workspace_path_style,
        local_workspace_root=local_workspace_root,
    )
    if not local_path:
        return None
    path = Path(local_path)
    limit = max(1, int(max_file_bytes))
    try:
        stat = path.stat()
        if not path.is_file() or stat.st_size > limit:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > limit:
        return None
    return CurrentWorkspaceFile(
        content_hash=hashlib.sha256(data).hexdigest(),
        size=len(data),
        mtime_ns=stat.st_mtime_ns,
        lines=data.decode("utf-8", errors="replace").splitlines(),
    )


def evidence_item_matches_file(item: EvidenceItem, file_lines: list[str]) -> bool:
    """Verify an evidence excerpt against the current decoded file lines.

    Args:
        item: Structured evidence item to verify.
        file_lines: Current source file split into lines.

    Returns:
        True only when the excerpt exactly matches its declared current range.
    """
    if item.line_range is None:
        return item.excerpt.splitlines() == file_lines
    start, end = item.line_range
    if start < 1 or end < start or end > len(file_lines):
        return False
    excerpt_lines = item.excerpt.splitlines()
    if len(excerpt_lines) != end - start + 1:
        return False

    numbered_matches = [_NUMBERED_LINE_RE.match(line) for line in excerpt_lines]
    if all(match is not None for match in numbered_matches):
        for expected_number, match, source_line in zip(
            range(start, end + 1),
            numbered_matches,
            file_lines[start - 1 : end],
            strict=True,
        ):
            if match is None:
                return False
            if int(match.group(1)) != expected_number or match.group(2) != source_line:
                return False
        return True

    return excerpt_lines == file_lines[start - 1 : end]


def load_workspace_manifest(
    path: Path,
    *,
    identity: str,
    version: int,
    new_manifest: Callable[[str], dict[str, Any]],
    collection_defaults: Mapping[str, Callable[[], Any]],
    logger: Any,
    failure_event: str,
) -> dict[str, Any]:
    """Load and validate a versioned gzip workspace-memory manifest.

    Args:
        path: Manifest file path.
        identity: Expected workspace identity.
        version: Expected manifest version.
        new_manifest: Factory for a clean manifest.
        collection_defaults: Collection fields and their empty-value factories.
        logger: Structured logger used for corrupt-manifest diagnostics.
        failure_event: Log event emitted when gzip or JSON decoding fails.

    Returns:
        A schema-compatible manifest, falling back closed to a clean manifest.
    """
    if not path.exists():
        return new_manifest(identity)
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning(failure_event, workspace_hash=identity, error=str(exc))
        return new_manifest(identity)
    if not isinstance(payload, dict):
        return new_manifest(identity)
    if payload.get("version") != version or payload.get("workspace_hash") != identity:
        return new_manifest(identity)
    for key, factory in collection_defaults.items():
        default_value = factory()
        if not isinstance(payload.get(key), type(default_value)):
            payload[key] = default_value
    return payload


def save_workspace_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """Atomically save a private gzip workspace-memory manifest.

    Args:
        path: Final manifest file path.
        manifest: JSON-compatible manifest payload.
    """
    ensure_private_directory(path.parent)
    data = gzip.compress(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        compresslevel=6,
    )
    fd, temp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(temp_path)
        raise


def ensure_private_directory(path: Path) -> None:
    """Create a workspace-memory directory with private permissions.

    Args:
        path: Directory to create or harden.
    """
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o700)


def now_iso_z() -> str:
    """Return the current UTC timestamp in ISO-8601 Z form."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")

"""
Collect prebuilt frontend assets into the Python package tree.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def resolve_repo_root() -> Path:
    """Return the repository root based on this file location."""
    return Path(__file__).resolve().parents[2]


def resolve_default_source_dir() -> Path:
    """Return the default frontend build output directory."""
    return resolve_repo_root() / "web" / "dist"


def resolve_default_target_dir() -> Path:
    """Return the default packaged frontend asset directory."""
    return Path(__file__).resolve().parent / "web_static"


def count_files(directory: Path) -> int:
    """Count regular files within a directory tree."""
    return sum(1 for path in directory.rglob("*") if path.is_file())


def is_relative_to(path: Path, other: Path) -> bool:
    """Return whether one path is located within another path."""
    try:
        path.relative_to(other)
    except ValueError:
        return False
    return True


def collect_web_static(source_dir: Path, target_dir: Path) -> int:
    """Copy built frontend assets into the package directory.

    Replaces the target directory entirely if it already exists.

    Args:
        source_dir: Directory containing the built frontend assets.
        target_dir: Directory that will receive the copied assets.

    Returns:
        The number of copied files.

    Raises:
        FileNotFoundError: If the source directory does not exist.
        NotADirectoryError: If the source path is not a directory.
        NotADirectoryError: If the target path exists but is not a directory.
        ValueError: If the source and target directories are the same or nested.
    """
    source_dir = source_dir.resolve()
    target_dir = target_dir.resolve()

    if not source_dir.exists():
        raise FileNotFoundError(
            f"Frontend build output does not exist: {source_dir}. "
            "Run 'npm run build' in the 'web' directory first."
        )

    if not source_dir.is_dir():
        raise NotADirectoryError(f"Frontend build output is not a directory: {source_dir}")

    if source_dir == target_dir:
        raise ValueError("Source and target directories must be different.")

    if is_relative_to(target_dir, source_dir) or is_relative_to(source_dir, target_dir):
        raise ValueError("Source and target directories must not be nested.")

    if target_dir.exists():
        if not target_dir.is_dir():
            raise NotADirectoryError(
                f"Packaged frontend asset path is not a directory: {target_dir}"
            )
        shutil.rmtree(target_dir)

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target_dir)
    return count_files(target_dir)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for asset collection."""
    parser = argparse.ArgumentParser(
        description="Collect built frontend assets into src/ternion/web_static."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=resolve_default_source_dir(),
        help="Path to the built frontend assets directory.",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=resolve_default_target_dir(),
        help="Path to the packaged frontend asset directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the frontend asset collection command.

    Args:
        argv: Command-line arguments. Defaults to `sys.argv` when `None`.

    Returns:
        `0` when assets are collected successfully, otherwise `1`.
    """
    args = build_parser().parse_args(argv)

    try:
        copied_file_count = collect_web_static(args.source, args.target)
    except (FileNotFoundError, NotADirectoryError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        "Collected frontend assets",
        f"from {args.source.resolve()}",
        f"to {args.target.resolve()}",
        f"({copied_file_count} files).",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

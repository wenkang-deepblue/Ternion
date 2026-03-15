"""Tests for the build_web_static module."""

from __future__ import annotations

from pathlib import Path

import pytest

from ternion.build_web_static import collect_web_static, main


def test_collect_web_static_replaces_stale_assets(tmp_path: Path) -> None:
    """Verifies that current assets replace stale target files."""
    source_dir = tmp_path / "web" / "dist"
    source_dir.mkdir(parents=True)
    (source_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    assets_dir = source_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "app.js").write_text("console.log('ternion');", encoding="utf-8")

    target_dir = tmp_path / "src" / "ternion" / "web_static"
    target_dir.mkdir(parents=True)
    (target_dir / "stale.txt").write_text("old", encoding="utf-8")

    copied_file_count = collect_web_static(source_dir, target_dir)

    assert copied_file_count == 2
    assert (target_dir / "index.html").read_text(encoding="utf-8") == "<html></html>"
    assert (target_dir / "assets" / "app.js").read_text(
        encoding="utf-8"
    ) == "console.log('ternion');"
    assert not (target_dir / "stale.txt").exists()


def test_collect_web_static_requires_existing_source(tmp_path: Path) -> None:
    """Verifies that a missing source directory raises a clear error."""
    source_dir = tmp_path / "web" / "dist"
    target_dir = tmp_path / "src" / "ternion" / "web_static"

    with pytest.raises(FileNotFoundError, match="Run 'npm run build'"):
        collect_web_static(source_dir, target_dir)


def test_main_returns_error_for_missing_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifies that the CLI returns a non-zero exit code for invalid input."""
    missing_source = tmp_path / "missing"
    target_dir = tmp_path / "target"

    exit_code = main(["--source", str(missing_source), "--target", str(target_dir)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Error:" in captured.err


def test_collect_web_static_rejects_identical_source_and_target(tmp_path: Path) -> None:
    """Verifies that identical source and target directories are rejected."""
    source_dir = tmp_path / "web" / "dist"
    source_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="must be different"):
        collect_web_static(source_dir, source_dir)


def test_collect_web_static_rejects_nested_target(tmp_path: Path) -> None:
    """Verifies that nested source and target directories are rejected."""
    source_dir = tmp_path / "web" / "dist"
    source_dir.mkdir(parents=True)
    target_dir = source_dir / "nested"

    with pytest.raises(ValueError, match="must not be nested"):
        collect_web_static(source_dir, target_dir)


def test_collect_web_static_requires_directory_source(tmp_path: Path) -> None:
    """Verifies that a file source path raises a directory error."""
    source_file = tmp_path / "web" / "dist"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("not a directory", encoding="utf-8")
    target_dir = tmp_path / "src" / "ternion" / "web_static"

    with pytest.raises(NotADirectoryError, match="not a directory"):
        collect_web_static(source_file, target_dir)


def test_collect_web_static_creates_missing_target_parent(tmp_path: Path) -> None:
    """Verifies that the target parent directory is created automatically."""
    source_dir = tmp_path / "web" / "dist"
    source_dir.mkdir(parents=True)
    (source_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    target_dir = tmp_path / "missing" / "src" / "ternion" / "web_static"

    copied_file_count = collect_web_static(source_dir, target_dir)

    assert copied_file_count == 1
    assert target_dir.exists()
    assert target_dir.parent.exists()


def test_collect_web_static_accepts_empty_source_directory(tmp_path: Path) -> None:
    """Verifies that an empty source directory is copied successfully."""
    source_dir = tmp_path / "web" / "dist"
    source_dir.mkdir(parents=True)
    target_dir = tmp_path / "src" / "ternion" / "web_static"

    copied_file_count = collect_web_static(source_dir, target_dir)

    assert copied_file_count == 0
    assert target_dir.exists()


def test_collect_web_static_rejects_file_target(tmp_path: Path) -> None:
    """Verifies that an existing file target is rejected explicitly."""
    source_dir = tmp_path / "web" / "dist"
    source_dir.mkdir(parents=True)
    (source_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    target_file = tmp_path / "src" / "ternion" / "web_static"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(NotADirectoryError, match="not a directory"):
        collect_web_static(source_dir, target_file)


def test_main_returns_success_for_valid_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifies that the CLI reports success for valid input."""
    source_dir = tmp_path / "web" / "dist"
    source_dir.mkdir(parents=True)
    (source_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    target_dir = tmp_path / "src" / "ternion" / "web_static"

    exit_code = main(["--source", str(source_dir), "--target", str(target_dir)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Collected frontend assets" in captured.out

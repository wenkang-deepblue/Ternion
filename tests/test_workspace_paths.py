"""Unit tests for workspace path helpers."""

from __future__ import annotations

from pathlib import Path

from ternion.utils.workspace_paths import (
    detect_path_style,
    normalize_declared_workspace_path,
    normalize_local_file_path,
    normalize_workspace_target_path,
    render_workspace_path,
    resolve_local_workspace_root,
    workspace_relative_path,
)


class TestDetectPathStyle:
    """Tests for path style detection."""

    def test_detects_posix_windows_and_unc(self) -> None:
        """Path style detection should recognize absolute POSIX and Windows inputs."""
        assert detect_path_style("/repo/project") == "posix"
        assert detect_path_style(r"C:\repo\project") == "windows"
        assert detect_path_style(r"\\server\share\project") == "windows"
        assert detect_path_style("src/app.py") == ""


class TestNormalizeDeclaredWorkspacePath:
    """Tests for client-declared workspace normalization."""

    def test_normalizes_posix_and_windows_without_filesystem_access(self) -> None:
        """Normalization should stay purely semantic."""
        assert normalize_declared_workspace_path(" '/repo/app/../project/' ") == (
            "/repo/project",
            "posix",
        )
        assert normalize_declared_workspace_path(r'"C:\repo\team\..\project\\"') == (
            r"C:\repo\project",
            "windows",
        )
        assert normalize_declared_workspace_path("relative/path") == ("", "")


class TestResolveLocalWorkspaceRoot:
    """Tests for best-effort local workspace resolution."""

    def test_resolves_existing_local_directory_only(self, tmp_path: Path) -> None:
        """Only existing local directories should resolve."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        assert resolve_local_workspace_root(str(workspace)) == str(workspace.resolve())
        assert resolve_local_workspace_root(str(workspace / "missing")) == ""


class TestNormalizeWorkspaceTargetPath:
    """Tests for client-visible target normalization."""

    def test_normalizes_relative_absolute_and_mixed_style_targets(self) -> None:
        """Target normalization should reject style mismatches."""
        assert normalize_workspace_target_path(
            "src/app.py",
            workspace_root="/repo/project",
            workspace_path_style="posix",
        ) == "/repo/project/src/app.py"
        assert normalize_workspace_target_path(
            r"docs\spec.md",
            workspace_root=r"C:\repo\project",
            workspace_path_style="windows",
        ) == r"C:\repo\project\docs\spec.md"
        assert (
            normalize_workspace_target_path(
                r"C:\repo\project\src\app.py",
                workspace_root="/repo/project",
                workspace_path_style="posix",
            )
            is None
        )


class TestWorkspaceRelativePath:
    """Tests for semantic workspace-relative resolution."""

    def test_returns_relative_path_inside_workspace_and_blocks_outside(self) -> None:
        """Relative path logic should be boundary-aware without filesystem access."""
        assert workspace_relative_path(
            "/repo/project/docs/spec.md",
            workspace_root="/repo/project",
        ) == "docs/spec.md"
        assert (
            workspace_relative_path(
                "/repo/other/outside.md",
                workspace_root="/repo/project",
            )
            is None
        )
        assert workspace_relative_path(
            r"C:\repo\project\src\app.py",
            workspace_root=r"C:\repo\project",
            workspace_path_style="windows",
        ) == "src/app.py"
        assert (
            workspace_relative_path(
                r"D:\other\outside.py",
                workspace_root=r"C:\repo\project",
                workspace_path_style="windows",
            )
            is None
        )


class TestNormalizeLocalFilePath:
    """Tests for local workspace mapping."""

    def test_maps_client_paths_onto_local_workspace(self, tmp_path: Path) -> None:
        """Local mapping should use the workspace-relative path."""
        local_root = tmp_path / "workspace"
        target = local_root / "docs" / "spec.md"
        target.parent.mkdir(parents=True)

        normalized = normalize_local_file_path(
            "/remote/repo/docs/spec.md",
            workspace_root="/remote/repo",
            local_workspace_root=str(local_root),
        )

        assert normalized == str(target.resolve())

    def test_returns_none_without_local_root_or_for_outside_targets(self, tmp_path: Path) -> None:
        """Unsafe or unavailable local mappings should fail closed."""
        local_root = tmp_path / "workspace"
        local_root.mkdir()

        assert (
            normalize_local_file_path(
                "/remote/repo/docs/spec.md",
                workspace_root="/remote/repo",
                local_workspace_root="",
            )
            is None
        )
        assert (
            normalize_local_file_path(
                "/remote/other/spec.md",
                workspace_root="/remote/repo",
                local_workspace_root=str(local_root),
            )
            is None
        )


class TestRenderWorkspacePath:
    """Tests for workspace-relative rendering."""

    def test_renders_relative_root_and_original_fallback(self) -> None:
        """Rendered path should prefer relative output when safe."""
        assert render_workspace_path(
            "/repo/project/docs/spec.md",
            workspace_root="/repo/project",
        ) == "docs/spec.md"
        assert render_workspace_path(
            "/repo/project",
            workspace_root="/repo/project",
        ) == "."
        assert render_workspace_path(
            "/repo/other/spec.md",
            workspace_root="/repo/project",
        ) == "/repo/other/spec.md"

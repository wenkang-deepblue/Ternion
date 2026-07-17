"""Tests for release packaging configuration."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from ternion import __license__, __version__


def load_pyproject() -> dict[str, object]:
    """Load the repository pyproject configuration."""
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    return tomllib.loads(pyproject_path.read_text(encoding="utf-8"))


def load_gitignore() -> str:
    """Load the repository gitignore file."""
    gitignore_path = Path(__file__).resolve().parents[1] / ".gitignore"
    return gitignore_path.read_text(encoding="utf-8")


def load_web_package() -> dict[str, object]:
    """Load the frontend package metadata."""
    package_path = Path(__file__).resolve().parents[1] / "web" / "package.json"
    return json.loads(package_path.read_text(encoding="utf-8"))


def test_release_metadata_is_aligned() -> None:
    """Verifies that backend and frontend release metadata cannot drift."""
    project = load_pyproject()["project"]
    web_package = load_web_package()

    assert project["version"] == __version__ == web_package["version"]
    assert project["license"]["text"] == __license__ == web_package["license"]


def test_wheel_includes_web_static_artifacts() -> None:
    """Verifies that wheel builds include packaged frontend static assets."""
    pyproject = load_pyproject()
    wheel_target = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]

    assert "src/ternion/web_static/**" in wheel_target["artifacts"]


def test_sdist_includes_python_source_tree() -> None:
    """Verifies that sdist builds include the full Python source tree."""
    pyproject = load_pyproject()
    sdist_target = pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]

    assert "src/ternion/**" in sdist_target["include"]


def test_sdist_includes_web_static_artifacts() -> None:
    """Verifies that sdist builds include packaged frontend static assets."""
    pyproject = load_pyproject()
    sdist_target = pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]

    assert "src/ternion/web_static/**" in sdist_target["artifacts"]


def test_gitignore_excludes_generated_web_static() -> None:
    """Verifies that generated packaged frontend assets are not tracked."""
    gitignore = load_gitignore()

    assert "src/ternion/web_static/" in gitignore

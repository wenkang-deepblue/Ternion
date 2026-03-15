"""Tests for Control Panel static asset mounting."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ternion.server.app import mount_panel_static


def create_panel_app(static_dir: Path) -> FastAPI:
    """Create a minimal app with the panel static mount enabled."""
    app = FastAPI()
    mount_panel_static(app, static_dir=static_dir)
    return app


def test_mount_panel_static_returns_false_when_assets_missing(tmp_path: Path) -> None:
    """Verifies that panel assets are not mounted when the directory is missing."""
    app = FastAPI()

    mounted = mount_panel_static(app, static_dir=tmp_path / "missing")

    assert mounted is False
    client = TestClient(app)
    response = client.get("/panel")
    assert response.status_code == 404


def test_mount_panel_static_returns_false_when_path_is_file(tmp_path: Path) -> None:
    """Verifies that panel assets are not mounted when the path is a file."""
    static_file = tmp_path / "web_static"
    static_file.write_text("not a directory", encoding="utf-8")
    app = FastAPI()

    mounted = mount_panel_static(app, static_dir=static_file)

    assert mounted is False


def test_mount_panel_static_returns_false_when_index_missing(tmp_path: Path) -> None:
    """Verifies that panel assets are not mounted when index.html is missing."""
    static_dir = tmp_path / "web_static"
    static_dir.mkdir()
    app = FastAPI()

    mounted = mount_panel_static(app, static_dir=static_dir)

    assert mounted is False


def test_panel_root_redirects_to_trailing_slash(tmp_path: Path) -> None:
    """Verifies that /panel redirects to the mounted static path."""
    static_dir = tmp_path / "web_static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>panel</html>", encoding="utf-8")
    client = TestClient(create_panel_app(static_dir))

    response = client.get("/panel", follow_redirects=False)

    assert response.status_code in {301, 302, 307, 308}
    assert response.headers["location"] == "/panel/"


def test_panel_serves_index_and_assets(tmp_path: Path) -> None:
    """Verifies that the mounted panel serves the SPA index and asset files."""
    static_dir = tmp_path / "web_static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html>panel</html>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('panel');", encoding="utf-8")
    client = TestClient(create_panel_app(static_dir))

    index_response = client.get("/panel/")
    asset_response = client.get("/panel/assets/app.js")

    assert index_response.status_code == 200
    assert "<html>panel</html>" in index_response.text
    assert asset_response.status_code == 200
    assert "console.log('panel');" in asset_response.text


def test_panel_spa_routes_fall_back_to_index(tmp_path: Path) -> None:
    """Verifies that client-side panel routes fall back to the SPA index."""
    static_dir = tmp_path / "web_static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>panel</html>", encoding="utf-8")
    client = TestClient(create_panel_app(static_dir))

    response = client.get("/panel/settings")

    assert response.status_code == 200
    assert "<html>panel</html>" in response.text


def test_panel_missing_asset_with_extension_returns_not_found(tmp_path: Path) -> None:
    """Verifies that missing asset files do not fall back to the SPA index."""
    static_dir = tmp_path / "web_static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>panel</html>", encoding="utf-8")
    client = TestClient(create_panel_app(static_dir))

    response = client.get("/panel/assets/missing.js")

    assert response.status_code == 404

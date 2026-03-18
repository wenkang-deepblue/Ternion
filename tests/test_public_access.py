"""Tests for public-access URL canonicalization and config persistence."""

import json
from pathlib import Path

from ternion.core.config_store import ConfigStore, UserConfig
from ternion.core.public_access import (
    build_public_origin,
    is_local_origin,
    normalize_public_base_url,
    resolve_effective_public_base_url,
)


def test_normalize_public_base_url_canonicalizes_root_url() -> None:
    """Canonicalization should strip a trailing slash and remove a terminal `/v1`."""
    assert normalize_public_base_url("https://example.com/") == "https://example.com"
    assert normalize_public_base_url("https://example.com/v1") == "https://example.com"
    assert normalize_public_base_url("https://example.com/base/v1") == "https://example.com/base"
    assert normalize_public_base_url("https://example.com/v1/") == "https://example.com"


def test_normalize_public_base_url_rejects_invalid_values() -> None:
    """Canonicalization should fail closed for empty or malformed values."""
    assert normalize_public_base_url("") == ""
    assert normalize_public_base_url("not-a-url") == ""
    assert normalize_public_base_url("ftp://example.com") == ""


def test_normalize_public_base_url_preserves_non_terminal_v1() -> None:
    """Only a terminal lowercase `/v1` segment should be stripped."""
    assert normalize_public_base_url("https://example.com/v1/api") == "https://example.com/v1/api"
    assert normalize_public_base_url("https://example.com/V1") == "https://example.com/V1"


def test_is_local_origin_distinguishes_local_and_public_hosts() -> None:
    """Local/private origins should be rejected while public origins are allowed."""
    assert is_local_origin("http://localhost:9110") is True
    assert is_local_origin("http://192.168.1.1") is True
    assert is_local_origin("https://10.0.0.1") is True
    assert is_local_origin("http://myhost") is True
    assert is_local_origin("https://service.run.app") is False


def test_build_public_origin_handles_public_and_local_inputs() -> None:
    """Public origin builder should normalize forwarded values and reject local ones."""
    assert build_public_origin("https", "service.run.app") == "https://service.run.app"
    assert build_public_origin("https", "127.0.0.1:9110") == ""
    assert build_public_origin("https", "host1.example.com, host2.example.com") == (
        "https://host1.example.com"
    )
    assert build_public_origin("", "service.run.app") == ""


def test_resolve_effective_public_base_url_prefers_config_value() -> None:
    """Configured public URLs should win over any later runtime detection signal."""
    assert resolve_effective_public_base_url(
        "https://configured.example/v1",
        request_origin="https://detected.example",
    ) == ("https://configured.example", "config")


def test_resolve_effective_public_base_url_falls_back_to_request_origin() -> None:
    """Runtime-detected origins should be accepted when config is empty."""
    assert resolve_effective_public_base_url(
        "",
        request_origin="https://detected.example/v1",
    ) == ("https://detected.example", "request_origin")


def test_resolve_effective_public_base_url_returns_none_source_without_signal() -> None:
    """Missing signals should resolve to an empty effective URL."""
    assert resolve_effective_public_base_url("") == ("", "none")


def test_config_store_save_canonicalizes_public_access_values(tmp_path: Path) -> None:
    """Saving config should persist the public base URL without a `/v1` suffix."""
    store = ConfigStore(config_path=tmp_path / "config.json")
    config = UserConfig()
    config.public_access.mode = "local_tunnel"
    config.public_access.public_base_url = "https://example.com/v1"

    store.save(config)

    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["public_access"]["mode"] == "local_tunnel"
    assert saved["public_access"]["public_base_url"] == "https://example.com"


def test_config_store_load_migrates_invalid_public_access_mode(tmp_path: Path) -> None:
    """Loading config should recover invalid public-access values without dropping config."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "public_access": {
                    "mode": "invalid-mode",
                    "public_base_url": "https://example.com/v1",
                }
            }
        ),
        encoding="utf-8",
    )

    store = ConfigStore(config_path=config_path)
    config = store.load()

    assert config.public_access.mode == "none"
    assert config.public_access.public_base_url == "https://example.com"


def test_config_store_save_sanitizes_invalid_public_access_mode(tmp_path: Path) -> None:
    """Saving config should reset invalid public-access modes to `none`."""
    store = ConfigStore(config_path=tmp_path / "config.json")
    config = UserConfig()
    config.public_access.mode = "invalid-mode"  # type: ignore[assignment]
    config.public_access.public_base_url = "https://example.com"

    store.save(config)

    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["public_access"]["mode"] == "none"


def test_config_store_safe_dict_includes_public_access(tmp_path: Path) -> None:
    """Safe config export should include public-access settings for API consumers."""
    store = ConfigStore(config_path=tmp_path / "config.json")
    config = UserConfig()
    config.public_access.mode = "cloud_run"
    config.public_access.public_base_url = "https://service.example"
    store._config = config

    safe = store.to_safe_dict()

    assert safe["public_access"] == {
        "mode": "cloud_run",
        "public_base_url": "https://service.example",
    }

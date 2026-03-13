"""
Tests for config-store runtime role canonicalization.
"""

from pathlib import Path
from unittest.mock import patch

from ternion.core.config_store import ConfigStore, RoleConfig, UserConfig
from ternion.core.model_catalog import CatalogModel


def _build_catalog_model(
    *,
    model_id: str,
    provider: str,
    raw_key: str,
    api_model_id: str | None = None,
) -> CatalogModel:
    """Create a catalog model for role canonicalization tests."""
    return CatalogModel(
        id=model_id,
        name=model_id,
        provider=provider,
        mode="chat",
        raw_key=raw_key,
        source_keys=[raw_key, model_id],
        api_model_id=api_model_id or model_id,
    )


def test_get_role_config_canonicalizes_legacy_model_id(tmp_path: Path) -> None:
    """Runtime role reads should expose canonical model IDs when the catalog can resolve them."""
    store = ConfigStore(config_path=tmp_path / "config.json")
    config = UserConfig()
    config.roles["writer"] = RoleConfig(
        provider="anthropic",
        model="claude-opus-4-6-20260205",
    )
    store._config = config
    canonical_model = _build_catalog_model(
        model_id="claude-opus-4-6",
        provider="anthropic",
        raw_key="claude-opus-4-6-20260205",
        api_model_id="claude-opus-4-6",
    )

    with patch("ternion.core.model_catalog.model_catalog_service") as mock_catalog_service:
        mock_catalog_service.get_model_cached.return_value = canonical_model
        role_config = store.get_role_config("writer")

    assert role_config is not None
    assert role_config.model == "claude-opus-4-6"
    assert store.load().roles["writer"].model == "claude-opus-4-6"


def test_get_role_config_skips_canonicalization_on_provider_mismatch(tmp_path: Path) -> None:
    """Runtime role reads should keep the original model when catalog provider mismatches."""
    store = ConfigStore(config_path=tmp_path / "config.json")
    config = UserConfig()
    config.roles["writer"] = RoleConfig(
        provider="openai",
        model="gpt-5.4-pro-2026-03-05-source",
    )
    store._config = config
    mismatched_model = _build_catalog_model(
        model_id="gpt-5.4-pro-2026-03-05",
        provider="anthropic",
        raw_key="gpt-5.4-pro-2026-03-05-source",
    )

    with patch("ternion.core.model_catalog.model_catalog_service") as mock_catalog_service:
        mock_catalog_service.get_model_cached.return_value = mismatched_model
        role_config = store.get_role_config("writer")

    assert role_config is not None
    assert role_config.model == "gpt-5.4-pro-2026-03-05-source"

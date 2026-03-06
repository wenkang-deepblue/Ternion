"""
Tests for the LiteLLM-backed model catalog service.
"""

import asyncio
import json
from datetime import timedelta
from pathlib import Path

import pytest

from ternion.core.model_catalog import LiteLLMModelCatalogService


@pytest.fixture
def sample_catalog_payload() -> dict[str, dict[str, object]]:
    """Return a representative LiteLLM catalog payload fixture."""
    return {
        "gpt-5.3-codex": {
            "litellm_provider": "openai",
            "mode": "completion",
            "input_cost_per_token": 0.00125,
            "output_cost_per_token": 0.01,
            "max_input_tokens": 200000,
            "max_output_tokens": 8192,
        },
        "gpt-5.2-2025-12-11": {
            "litellm_provider": "openai",
            "mode": "chat",
            "input_cost_per_token": 0.00175,
            "output_cost_per_token": 0.014,
        },
        "gpt-4.1": {
            "litellm_provider": "openai",
            "mode": "chat",
        },
        "openai/gpt-5.4": {
            "litellm_provider": "openai",
            "mode": "chat",
        },
        "gemini-3.1-pro-preview": {
            "litellm_provider": "gemini",
            "mode": "chat",
            "input_cost_per_token": 0.002,
            "output_cost_per_token": 0.012,
            "input_cost_per_token_above_200k_tokens": 0.004,
            "output_cost_per_token_above_200k_tokens": 0.018,
            "max_input_tokens": 1048576,
        },
        "gemini-3.1-image-preview": {
            "litellm_provider": "gemini",
            "mode": "chat",
        },
        "gemini-3.1-customtools": {
            "litellm_provider": "gemini",
            "mode": "chat",
        },
        "gemini-2.5-pro-preview": {
            "litellm_provider": "gemini",
            "mode": "chat",
        },
        "claude-sonnet-4-5-20250929": {
            "litellm_provider": "anthropic",
            "mode": "chat",
            "input_cost_per_token": 0.003,
            "output_cost_per_token": 0.015,
            "output_cost_per_reasoning_token": 0.02,
        },
        "claude-opus-4-1-20250805": {
            "litellm_provider": "anthropic",
            "mode": "chat",
            "input_cost_per_token": 0.015,
            "output_cost_per_token": 0.075,
        },
        "claude-haiku-4-5-20251001": {
            "litellm_provider": "anthropic",
            "mode": "chat",
        },
        "claude-sonnet-3-7-20250219": {
            "litellm_provider": "anthropic",
            "mode": "chat",
        },
    }


@pytest.mark.asyncio
async def test_get_snapshot_filters_models_and_formats_names(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The service should normalize only the allowed provider models."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return sample_catalog_payload, "test-etag", False

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)

    snapshot = await service.get_snapshot()

    assert [model.id for model in snapshot.models_by_provider["openai"]] == [
        "gpt-5.2-2025-12-11",
        "gpt-5.3-codex",
    ]
    assert [model.name for model in snapshot.models_by_provider["google"]] == ["Gemini 3.1 Pro"]
    assert [model.name for model in snapshot.models_by_provider["anthropic"]] == [
        "Claude Opus 4.1",
        "Claude Sonnet 4.5",
    ]

    model = snapshot.index_by_id["claude-sonnet-4-5-20250929"]
    assert model.provider == "anthropic"
    assert model.output_cost_per_reasoning_token == pytest.approx(0.02)
    assert model.max_input_tokens is None

    assert await service.is_model_available("google", "gemini-3.1-pro-preview") is True
    assert await service.is_model_available("google", "gemini-2.5-pro-preview") is False


@pytest.mark.asyncio
async def test_get_snapshot_writes_disk_cache_and_uses_memory_cache(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh memory cache should avoid repeated remote fetches."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")
    calls = 0

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        nonlocal calls
        calls += 1
        assert etag is None
        return sample_catalog_payload, "etag-1", False

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)

    first_snapshot = await service.get_snapshot()
    second_snapshot = await service.get_snapshot()

    assert calls == 1
    assert service.cache_path.exists()
    assert first_snapshot == second_snapshot
    cache_payload = json.loads(service.cache_path.read_text(encoding="utf-8"))
    assert cache_payload["etag"] == "etag-1"
    assert "models_by_provider" in cache_payload


@pytest.mark.asyncio
async def test_force_refresh_bypasses_fresh_memory_cache(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force refresh should fetch again even when memory cache is fresh."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")
    calls = 0

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        nonlocal calls
        calls += 1
        return sample_catalog_payload, f"etag-{calls}", False

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)

    await service.get_snapshot()
    await service.get_snapshot(force_refresh=True)

    assert calls == 2


@pytest.mark.asyncio
async def test_get_snapshot_reuses_previous_snapshot_on_not_modified(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 304 response should refresh metadata while preserving cached data."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")

    async def first_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return sample_catalog_payload, "etag-v1", False

    async def second_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag == "etag-v1"
        return None, "etag-v1", True

    monkeypatch.setattr(service, "_download_catalog_json", first_download)
    first_snapshot = await service.get_snapshot()

    monkeypatch.setattr(service, "_download_catalog_json", second_download)
    second_snapshot = await service.get_snapshot(force_refresh=True)

    assert second_snapshot.index_by_id == first_snapshot.index_by_id
    assert second_snapshot.etag == "etag-v1"
    assert second_snapshot.fetched_at != ""


@pytest.mark.asyncio
async def test_concurrent_refresh_issues_only_one_remote_fetch(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent refreshes should share a single in-flight fetch."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return sample_catalog_payload, "etag-1", False

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)

    first_task = asyncio.create_task(service.get_snapshot())
    await started.wait()
    second_task = asyncio.create_task(service.get_snapshot())
    await asyncio.sleep(0)
    release.set()

    first_snapshot, second_snapshot = await asyncio.gather(first_task, second_task)

    assert calls == 1
    assert first_snapshot == second_snapshot


@pytest.mark.asyncio
async def test_get_snapshot_ignores_cache_save_failures(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Snapshot fetches should still succeed when cache persistence fails."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return sample_catalog_payload, "etag-save-failure", False

    def failing_save(snapshot: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)
    monkeypatch.setattr(service, "_save_disk_cache", failing_save)

    snapshot = await service.get_snapshot()

    assert snapshot.index_by_id["gpt-5.3-codex"].provider == "openai"
    assert service.get_model_cached("gpt-5.3-codex") is not None


@pytest.mark.asyncio
async def test_get_snapshot_falls_back_to_disk_cache_when_refresh_fails(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stale disk cache should still be returned on refresh failure."""
    cache_path = tmp_path / "catalog.json"
    seed_service = LiteLLMModelCatalogService(cache_path=cache_path)

    async def seed_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return sample_catalog_payload, "etag-seed", False

    monkeypatch.setattr(seed_service, "_download_catalog_json", seed_download)
    seeded_snapshot = await seed_service.get_snapshot()

    failing_service = LiteLLMModelCatalogService(
        cache_path=cache_path,
        cache_ttl=timedelta(seconds=0),
    )

    async def failing_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag == "etag-seed"
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(failing_service, "_download_catalog_json", failing_download)

    snapshot = await failing_service.get_snapshot(force_refresh=True)

    assert snapshot.index_by_id == seeded_snapshot.index_by_id
    assert snapshot.models_by_provider["google"][0].id == "gemini-3.1-pro-preview"


@pytest.mark.asyncio
async def test_get_snapshot_uses_fresh_disk_cache_without_remote_fetch(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh disk cache should satisfy a cold start without network access."""
    cache_path = tmp_path / "catalog.json"
    seed_service = LiteLLMModelCatalogService(cache_path=cache_path)

    async def seed_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return sample_catalog_payload, "etag-seed", False

    monkeypatch.setattr(seed_service, "_download_catalog_json", seed_download)
    await seed_service.get_snapshot()

    cold_service = LiteLLMModelCatalogService(cache_path=cache_path)

    async def unexpected_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        raise AssertionError("remote fetch should not be called")

    monkeypatch.setattr(cold_service, "_download_catalog_json", unexpected_download)

    snapshot = await cold_service.get_snapshot()

    assert snapshot.index_by_id["gpt-5.3-codex"].provider == "openai"


@pytest.mark.asyncio
async def test_corrupt_disk_cache_falls_back_to_remote(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A corrupt disk cache should not block a successful remote refresh."""
    cache_path = tmp_path / "catalog.json"
    cache_path.write_text("{not valid json", encoding="utf-8")
    service = LiteLLMModelCatalogService(cache_path=cache_path)

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return sample_catalog_payload, "etag-fresh", False

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)

    snapshot = await service.get_snapshot()

    assert snapshot.index_by_id["gpt-5.3-codex"].provider == "openai"


@pytest.mark.asyncio
async def test_get_model_cached_reads_memory_then_disk(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cached lookup should work from memory, disk, and empty state."""
    cache_path = tmp_path / "catalog.json"
    seed_service = LiteLLMModelCatalogService(cache_path=cache_path)

    async def seed_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return sample_catalog_payload, "etag-seed", False

    monkeypatch.setattr(seed_service, "_download_catalog_json", seed_download)
    await seed_service.get_snapshot()

    assert seed_service.get_model_cached("gpt-5.3-codex") is not None

    cold_service = LiteLLMModelCatalogService(cache_path=cache_path)
    cached_model = cold_service.get_model_cached("gpt-5.3-codex")
    assert cached_model is not None
    assert cached_model.provider == "openai"
    assert cold_service.get_model_cached("does-not-exist") is None

    empty_service = LiteLLMModelCatalogService(cache_path=tmp_path / "missing.json")
    assert empty_service.get_model_cached("gpt-5.3-codex") is None


@pytest.mark.asyncio
async def test_get_models_payload_serializes_models_and_pricing_flags(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The payload should expose provider buckets and pricing availability."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return sample_catalog_payload, "etag-payload", False

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)

    payload = await service.get_models_payload()

    assert payload["last_updated_at"] != ""
    assert set(payload["models"]) == {"openai", "google", "anthropic"}
    assert payload["models"]["google"][0]["pricing_available"] is True
    assert payload["models"]["anthropic"][0]["stale"] is False


@pytest.mark.asyncio
async def test_is_model_available_requires_provider_match(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model availability should require a matching provider."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return sample_catalog_payload, "etag-provider-match", False

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)

    assert await service.is_model_available("anthropic", "claude-sonnet-4-5-20250929") is True
    assert await service.is_model_available("openai", "claude-sonnet-4-5-20250929") is False


@pytest.mark.asyncio
async def test_legacy_anthropic_model_ids_are_supported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy version-first Anthropic IDs should still be normalized."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")
    payload = {
        "claude-4-1-opus-latest": {
            "litellm_provider": "anthropic",
            "mode": "chat",
        }
    }

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return payload, "etag-legacy", False

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)

    snapshot = await service.get_snapshot()

    assert [model.id for model in snapshot.models_by_provider["anthropic"]] == [
        "claude-4-1-opus-latest"
    ]
    assert snapshot.models_by_provider["anthropic"][0].name == "Claude Opus 4.1"


@pytest.mark.asyncio
async def test_invalid_numeric_values_do_not_break_snapshot_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid numeric values should be ignored instead of aborting the refresh."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")
    payload = {
        "gpt-5.3": {
            "litellm_provider": "openai",
            "mode": "chat",
            "input_cost_per_token": "not-a-number",
            "max_input_tokens": "unknown",
        }
    }

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return payload, "etag-invalid-numeric", False

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)

    snapshot = await service.get_snapshot()

    model = snapshot.index_by_id["gpt-5.3"]
    assert model.input_cost_per_token is None
    assert model.max_input_tokens is None


@pytest.mark.asyncio
async def test_get_snapshot_returns_empty_snapshot_without_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing remote data and cache should produce an empty snapshot."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")

    async def failing_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        raise RuntimeError("catalog fetch failed")

    monkeypatch.setattr(service, "_download_catalog_json", failing_download)

    snapshot = await service.get_snapshot()

    assert snapshot.fetched_at == ""
    assert snapshot.index_by_id == {}
    assert snapshot.models_by_provider == {
        "openai": [],
        "google": [],
        "anthropic": [],
    }

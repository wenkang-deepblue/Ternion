"""
Tests for the LiteLLM-backed model catalog service.
"""

import asyncio
import json
from datetime import timedelta
from pathlib import Path

import pytest

import ternion.core.model_catalog as model_catalog_module
from ternion.core.model_catalog import CatalogSnapshot, LiteLLMModelCatalogService


@pytest.fixture(autouse=True)
def disable_provider_truth_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep catalog tests hermetic unless a test opts into provider truth."""

    async def fake_fetch_provider_truth_index(
        self: LiteLLMModelCatalogService,
    ) -> dict[str, set[str] | None]:
        return {
            "openai": None,
            "google": None,
            "anthropic": None,
        }

    monkeypatch.setattr(
        LiteLLMModelCatalogService,
        "_fetch_provider_truth_index",
        fake_fetch_provider_truth_index,
    )


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
        "gpt-codex-5.8": {
            "litellm_provider": "openai",
            "mode": "completion",
            "input_cost_per_token": 0.00195,
            "output_cost_per_token": 0.015,
        },
        "gpt-4.1": {
            "litellm_provider": "openai",
            "mode": "chat",
        },
        "gpt-5-search-api": {
            "litellm_provider": "openai",
            "mode": "completion",
        },
        "gpt-5-nano": {
            "litellm_provider": "openai",
            "mode": "chat",
        },
        "chatgpt-5.4": {
            "litellm_provider": "openai",
            "mode": "chat",
        },
        "openai/gpt-5.4": {
            "litellm_provider": "openai",
            "mode": "chat",
        },
        "gemini-3-pro": {
            "litellm_provider": "vertex_ai-language-models",
            "mode": "chat",
            "input_cost_per_token": 0.0015,
            "output_cost_per_token": 0.01,
        },
        "gemini-3.1-pro-preview": {
            "litellm_provider": "vertex_ai-language-models",
            "mode": "chat",
            "input_cost_per_token": 0.002,
            "output_cost_per_token": 0.012,
            "input_cost_per_token_above_200k_tokens": 0.004,
            "output_cost_per_token_above_200k_tokens": 0.018,
            "max_input_tokens": 1048576,
        },
        "gemini-3.1-image-preview": {
            "litellm_provider": "vertex_ai-language-models",
            "mode": "chat",
        },
        "gemini-3.1-robotics-preview": {
            "litellm_provider": "vertex_ai-language-models",
            "mode": "chat",
        },
        "gemini-2.5-pro-preview": {
            "litellm_provider": "vertex_ai-language-models",
            "mode": "chat",
        },
        "claude-sonnet-4-5-20250929": {
            "litellm_provider": "anthropic",
            "mode": "chat",
            "input_cost_per_token": 0.003,
            "output_cost_per_token": 0.015,
            "output_cost_per_reasoning_token": 0.02,
            "cache_read_input_token_cost": 0.0003,
            "cache_creation_input_token_cost": 0.00375,
            "max_output_tokens": 64000,
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

    assert {model.id for model in snapshot.models_by_provider["openai"]} == {
        "gpt-5.2-2025-12-11",
        "gpt-5.3-codex",
        "gpt-codex-5.8",
    }
    assert {model.name for model in snapshot.models_by_provider["google"]} == {
        "Gemini 3 Pro",
        "Gemini 3.1 Pro",
    }
    assert [model.name for model in snapshot.models_by_provider["anthropic"]] == [
        "Claude Opus 4.1",
        "Claude Sonnet 4.5",
    ]

    model = snapshot.index_by_id["claude-sonnet-4-5-20250929"]
    assert model.provider == "anthropic"
    assert model.output_cost_per_reasoning_token == pytest.approx(0.02)
    assert model.max_input_tokens is None

    assert await service.is_model_available("google", "gemini-3-pro") is True
    assert await service.is_model_available("google", "gemini-3.1-pro-preview") is True
    assert await service.is_model_available("google", "gemini-2.5-pro-preview") is False

    assert model.api_model_id == "claude-sonnet-4-5-20250929"
    assert model.source_keys == ["claude-sonnet-4-5-20250929"]
    assert model.verified_by_provider_metadata is False


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
    assert snapshot.models_by_provider["google"][0].id == "gemini-3-pro"


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
    assert payload["catalog_initialized"] is True
    assert payload["requires_initialization"] is False
    assert payload["model_count"] == 7
    assert payload["catalog_anomaly_detected"] is False
    assert payload["anomaly_report_available"] is False


@pytest.mark.asyncio
async def test_get_models_payload_marks_empty_catalog_as_uninitialized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty catalogs should require explicit initialization in the UI."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")

    async def failing_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        raise RuntimeError("no catalog available")

    monkeypatch.setattr(service, "_download_catalog_json", failing_download)

    payload = await service.get_models_payload()

    assert payload["catalog_initialized"] is False
    assert payload["requires_initialization"] is True
    assert payload["model_count"] == 0
    assert payload["catalog_anomaly_detected"] is False


@pytest.mark.asyncio
async def test_get_models_payload_skips_remote_fetch_when_explicitly_uninitialized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readonly payload loading should not auto-bootstrap the remote catalog."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")
    calls = 0

    async def failing_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        nonlocal calls
        calls += 1
        raise AssertionError("remote fetch should not be attempted")

    monkeypatch.setattr(service, "_download_catalog_json", failing_download)

    payload = await service.get_models_payload(allow_remote_fetch=False)

    assert calls == 0
    assert payload["catalog_initialized"] is False
    assert payload["requires_initialization"] is True
    assert payload["model_count"] == 0


@pytest.mark.asyncio
async def test_get_models_payload_passes_force_refresh_to_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Payload generation should propagate force_refresh to snapshot loading."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")
    snapshot = service._build_empty_snapshot()
    calls: list[tuple[bool, bool]] = []

    async def fake_get_snapshot(
        force_refresh: bool = False,
        allow_remote_fetch: bool = True,
    ) -> CatalogSnapshot:
        calls.append((force_refresh, allow_remote_fetch))
        return snapshot

    monkeypatch.setattr(service, "get_snapshot", fake_get_snapshot)

    payload = await service.get_models_payload(force_refresh=True)

    assert payload["model_count"] == 0
    assert calls == [(True, True)]


@pytest.mark.asyncio
async def test_refresh_snapshot_updates_memory_and_disk_on_success(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit refresh should persist and publish the latest snapshot."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return sample_catalog_payload, "etag-refresh-success", False

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)

    snapshot = await service.refresh_snapshot()

    assert service.cache_path.exists()
    assert service._memory_snapshot == snapshot
    assert snapshot.etag == "etag-refresh-success"
    assert snapshot.index_by_id["gpt-5.2-2025-12-11"].provider == "openai"
    assert service.get_anomaly_report() is None


@pytest.mark.asyncio
async def test_refresh_snapshot_updates_memory_when_disk_cache_save_fails(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit refresh should keep the in-memory snapshot even if disk save fails."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return sample_catalog_payload, "etag-refresh-soft-fail", False

    def failing_save(snapshot: CatalogSnapshot) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)
    monkeypatch.setattr(service, "_save_disk_cache", failing_save)

    snapshot = await service.refresh_snapshot()

    assert service._memory_snapshot == snapshot
    assert snapshot.etag == "etag-refresh-soft-fail"
    assert not service.cache_path.exists()


@pytest.mark.asyncio
async def test_refresh_snapshot_requires_successful_remote_fetch(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit refresh should raise instead of silently returning empty data."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")

    async def seed_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        return sample_catalog_payload, "etag-seed", False

    monkeypatch.setattr(service, "_download_catalog_json", seed_download)
    await service.get_snapshot()

    async def failing_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag == "etag-seed"
        raise RuntimeError("remote fetch failed")

    monkeypatch.setattr(service, "_download_catalog_json", failing_download)

    with pytest.raises(RuntimeError, match="remote fetch failed"):
        await service.refresh_snapshot()


@pytest.mark.asyncio
async def test_refresh_snapshot_keeps_last_successful_snapshot_when_provider_becomes_empty(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An anomalous refresh should keep the last successful snapshot active."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")

    async def seed_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return sample_catalog_payload, "etag-healthy", False

    monkeypatch.setattr(service, "_download_catalog_json", seed_download)
    healthy_snapshot = await service.refresh_snapshot()

    anomalous_payload = {
        key: value
        for key, value in sample_catalog_payload.items()
        if value.get("litellm_provider") != "anthropic"
    }

    async def anomalous_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag == "etag-healthy"
        return anomalous_payload, "etag-anomalous", False

    monkeypatch.setattr(service, "_download_catalog_json", anomalous_download)

    active_snapshot = await service.refresh_snapshot()
    report = service.get_anomaly_report()

    assert report is not None
    assert report.used_last_successful_snapshot is True
    assert "anthropic" in report.triggered_providers
    assert active_snapshot == healthy_snapshot
    assert service.get_model_cached("claude-sonnet-4-5-20250929") is not None


@pytest.mark.asyncio
async def test_refresh_snapshot_returns_empty_catalog_when_anomaly_has_no_successful_cache(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An anomalous first refresh should expose an empty catalog and save a report."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")
    anomalous_payload = {
        key: value
        for key, value in sample_catalog_payload.items()
        if value.get("litellm_provider") != "anthropic"
    }

    async def anomalous_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return anomalous_payload, "etag-empty", False

    monkeypatch.setattr(service, "_download_catalog_json", anomalous_download)

    snapshot = await service.refresh_snapshot()
    payload = await service.get_models_payload()
    report = service.get_anomaly_report()

    assert report is not None
    assert report.used_last_successful_snapshot is False
    assert snapshot.index_by_id == {}
    assert payload["catalog_anomaly_detected"] is True
    assert payload["catalog_initialized"] is False
    assert payload["anomaly_report_available"] is True


@pytest.mark.asyncio
async def test_refresh_snapshot_marks_large_provider_drop_as_anomaly(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider drop greater than 80 percent should trigger anomaly reporting."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")

    seed_payload = dict(sample_catalog_payload)
    seed_payload["gpt-5.4-pro"] = {
        "litellm_provider": "openai",
        "mode": "chat",
    }
    seed_payload["gpt-chat-5.6"] = {
        "litellm_provider": "openai",
        "mode": "chat",
    }
    seed_payload["gpt-5.7-pro"] = {
        "litellm_provider": "openai",
        "mode": "chat",
    }

    async def seed_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return seed_payload, "etag-seed", False

    monkeypatch.setattr(service, "_download_catalog_json", seed_download)
    await service.refresh_snapshot()

    drop_payload = {
        key: value
        for key, value in seed_payload.items()
        if key
        not in {"gpt-5.3-codex", "gpt-codex-5.8", "gpt-5.4-pro", "gpt-chat-5.6", "gpt-5.7-pro"}
    }

    async def drop_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag == "etag-seed"
        return drop_payload, "etag-drop", False

    monkeypatch.setattr(service, "_download_catalog_json", drop_download)

    await service.refresh_snapshot()
    report = service.get_anomaly_report()

    assert report is not None
    assert "openai" in report.triggered_providers
    assert any("openai: filtered model count dropped" in item for item in report.trigger_conditions)


@pytest.mark.asyncio
async def test_refresh_snapshot_does_not_mark_exact_80_percent_drop_as_anomaly(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider drop of exactly 80 percent should not trigger anomaly reporting."""
    service = LiteLLMModelCatalogService(
        cache_path=tmp_path / "catalog.json",
        anomaly_report_path=tmp_path / "catalog_anomaly.json",
    )

    seed_payload = dict(sample_catalog_payload)
    seed_payload["gpt-5.4-pro"] = {
        "litellm_provider": "openai",
        "mode": "chat",
    }
    seed_payload["gpt-5.6-pro"] = {
        "litellm_provider": "openai",
        "mode": "chat",
    }

    async def seed_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return seed_payload, "etag-seed", False

    monkeypatch.setattr(service, "_download_catalog_json", seed_download)
    await service.refresh_snapshot()

    drop_payload = {
        key: value
        for key, value in seed_payload.items()
        if key not in {"gpt-5.2-2025-12-11", "gpt-5.4-pro", "gpt-5.6-pro", "gpt-codex-5.8"}
    }

    async def drop_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag == "etag-seed"
        return drop_payload, "etag-drop", False

    monkeypatch.setattr(service, "_download_catalog_json", drop_download)

    snapshot = await service.refresh_snapshot()

    assert {model.id for model in snapshot.models_by_provider["openai"]} == {"gpt-5.3-codex"}
    assert service.get_anomaly_report() is None


@pytest.mark.asyncio
async def test_get_anomaly_report_markdown_includes_counts_and_suspected_models(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The anomaly report Markdown should summarize counts and suspicious removals."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")
    anomalous_payload = {
        key: value
        for key, value in sample_catalog_payload.items()
        if key not in {"claude-sonnet-4-5-20250929", "claude-opus-4-1-20250805"}
    }

    async def anomalous_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        return anomalous_payload, "etag-report", False

    monkeypatch.setattr(service, "_download_catalog_json", anomalous_download)

    await service.refresh_snapshot()
    report_markdown = service.get_anomaly_report_markdown()

    assert report_markdown is not None
    assert "# Model Catalog Anomaly Report" in report_markdown
    assert "## Provider Counts" in report_markdown
    assert "claude-haiku-4-5-20251001" in report_markdown


@pytest.mark.asyncio
async def test_get_anomaly_report_caches_missing_disk_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing anomaly reports should only hit disk once per service instance."""
    service = LiteLLMModelCatalogService(
        cache_path=tmp_path / "catalog.json",
        anomaly_report_path=tmp_path / "catalog_anomaly.json",
    )
    calls = 0

    def fake_load() -> None:
        nonlocal calls
        calls += 1
        return None

    monkeypatch.setattr(service, "_load_anomaly_report", fake_load)

    assert service.get_anomaly_report() is None
    assert service.get_anomaly_report() is None
    assert calls == 1


@pytest.mark.asyncio
async def test_get_anomaly_report_loads_persisted_report_after_restart(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A restarted service should load a persisted anomaly report from disk."""
    cache_path = tmp_path / "catalog.json"
    anomaly_report_path = tmp_path / "catalog_anomaly.json"
    writer_service = LiteLLMModelCatalogService(
        cache_path=cache_path,
        anomaly_report_path=anomaly_report_path,
    )
    anomalous_payload = {
        key: value
        for key, value in sample_catalog_payload.items()
        if value.get("litellm_provider") != "anthropic"
    }

    async def anomalous_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return anomalous_payload, "etag-anomalous", False

    monkeypatch.setattr(writer_service, "_download_catalog_json", anomalous_download)

    await writer_service.refresh_snapshot()
    persisted_report = writer_service.get_anomaly_report()

    restarted_service = LiteLLMModelCatalogService(
        cache_path=cache_path,
        anomaly_report_path=anomaly_report_path,
    )

    loaded_report = restarted_service.get_anomaly_report()

    assert persisted_report is not None
    assert loaded_report is not None
    assert loaded_report.summary == persisted_report.summary
    assert loaded_report.triggered_providers == persisted_report.triggered_providers


@pytest.mark.asyncio
async def test_refresh_snapshot_clears_anomaly_report_after_recovery(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A healthy refresh should clear any previously persisted anomaly report."""
    service = LiteLLMModelCatalogService(
        cache_path=tmp_path / "catalog.json",
        anomaly_report_path=tmp_path / "catalog_anomaly.json",
    )
    anomalous_payload = {
        key: value
        for key, value in sample_catalog_payload.items()
        if value.get("litellm_provider") != "anthropic"
    }

    async def anomalous_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return anomalous_payload, "etag-anomalous", False

    monkeypatch.setattr(service, "_download_catalog_json", anomalous_download)
    await service.refresh_snapshot()

    assert service.get_anomaly_report() is not None
    assert service.anomaly_report_path.exists() is True

    async def healthy_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return sample_catalog_payload, "etag-healthy", False

    monkeypatch.setattr(service, "_download_catalog_json", healthy_download)
    await service.refresh_snapshot()

    assert service.get_anomaly_report() is None
    assert service.anomaly_report_path.exists() is False


@pytest.mark.asyncio
async def test_refresh_snapshot_keeps_anomaly_report_cleared_when_delete_fails(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed anomaly report delete should not revive stale diagnostics."""
    service = LiteLLMModelCatalogService(
        cache_path=tmp_path / "catalog.json",
        anomaly_report_path=tmp_path / "catalog_anomaly.json",
    )
    anomalous_payload = {
        key: value
        for key, value in sample_catalog_payload.items()
        if value.get("litellm_provider") != "anthropic"
    }

    async def anomalous_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return anomalous_payload, "etag-anomalous", False

    monkeypatch.setattr(service, "_download_catalog_json", anomalous_download)
    await service.refresh_snapshot()
    assert service.anomaly_report_path.exists() is True

    original_unlink = model_catalog_module.os.unlink

    def failing_unlink(path: str | bytes | Path) -> None:
        if Path(path) == service.anomaly_report_path:
            raise OSError("permission denied")
        original_unlink(path)

    monkeypatch.setattr(model_catalog_module.os, "unlink", failing_unlink)

    async def healthy_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return sample_catalog_payload, "etag-healthy", False

    monkeypatch.setattr(service, "_download_catalog_json", healthy_download)
    await service.refresh_snapshot()

    assert service.get_anomaly_report() is None
    assert service.anomaly_report_path.exists() is True


@pytest.mark.asyncio
async def test_refresh_snapshot_ignores_anomaly_report_save_failures(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refresh should keep anomaly diagnostics in memory when persistence fails."""
    service = LiteLLMModelCatalogService(
        cache_path=tmp_path / "catalog.json",
        anomaly_report_path=tmp_path / "catalog_anomaly.json",
    )
    anomalous_payload = {
        key: value
        for key, value in sample_catalog_payload.items()
        if value.get("litellm_provider") != "anthropic"
    }

    async def anomalous_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return anomalous_payload, "etag-anomalous", False

    def failing_save(report: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(service, "_download_catalog_json", anomalous_download)
    monkeypatch.setattr(service, "_save_anomaly_report", failing_save)

    snapshot = await service.refresh_snapshot()
    report = service.get_anomaly_report()

    assert snapshot.index_by_id == {}
    assert report is not None
    assert report.triggered_providers == ["anthropic"]
    assert service.anomaly_report_path.exists() is False


@pytest.mark.asyncio
async def test_openai_raw_candidates_exclude_denylisted_models(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI raw candidates should skip denylisted variants."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")
    payload = dict(sample_catalog_payload)
    payload["gpt-5.4-mini"] = {
        "litellm_provider": "openai",
        "mode": "chat",
    }
    payload["gpt-5.4-audio"] = {
        "litellm_provider": "openai",
        "mode": "chat",
    }

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return payload, "etag-openai-raw", False

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)

    snapshot = await service.get_snapshot()

    assert "gpt-5.4-mini" not in snapshot.provider_stats["openai"].raw_candidate_ids
    assert "gpt-5.4-audio" not in snapshot.provider_stats["openai"].raw_candidate_ids


@pytest.mark.asyncio
async def test_openai_models_require_a_minor_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI GPT models should require a minor version to be normalized."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")
    payload = {
        "gpt-5": {
            "litellm_provider": "openai",
            "mode": "chat",
        },
        "gpt-5.1": {
            "litellm_provider": "openai",
            "mode": "chat",
        },
        "gemini-3-pro": {
            "litellm_provider": "vertex_ai-language-models",
            "mode": "chat",
        },
        "claude-sonnet-4-5-20250929": {
            "litellm_provider": "anthropic",
            "mode": "chat",
        },
    }

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return payload, "etag-openai-version", False

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)

    snapshot = await service.get_snapshot()

    assert {model.id for model in snapshot.models_by_provider["openai"]} == {"gpt-5.1"}
    assert "gpt-5" not in snapshot.provider_stats["openai"].raw_candidate_ids


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
        "gpt-5.2-2025-12-11": {
            "litellm_provider": "openai",
            "mode": "chat",
        },
        "gemini-3-pro": {
            "litellm_provider": "vertex_ai-language-models",
            "mode": "chat",
        },
        "claude-4-1-opus-latest": {
            "litellm_provider": "anthropic",
            "mode": "chat",
        },
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
async def test_anthropic_truth_deduplicates_snapshot_and_short_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anthropic truth should collapse raw duplicates onto one canonical API ID."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")
    payload = {
        "gpt-5.2-2025-12-11": {
            "litellm_provider": "openai",
            "mode": "chat",
        },
        "gemini-3-pro": {
            "litellm_provider": "vertex_ai-language-models",
            "mode": "chat",
        },
        "claude-opus-4-6": {
            "litellm_provider": "anthropic",
            "mode": "chat",
            "input_cost_per_token": 0.005,
        },
        "claude-opus-4-6-20260205": {
            "litellm_provider": "anthropic",
            "mode": "chat",
            "output_cost_per_token": 0.025,
        },
    }

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return payload, "etag-anthropic-dedupe", False

    async def fake_truth_index() -> dict[str, set[str] | None]:
        return {
            "openai": None,
            "google": None,
            "anthropic": {"claude-opus-4-6"},
        }

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)
    monkeypatch.setattr(service, "_fetch_provider_truth_index", fake_truth_index)

    snapshot = await service.get_snapshot()

    anthropic_models = snapshot.models_by_provider["anthropic"]
    assert [model.id for model in anthropic_models] == ["claude-opus-4-6"]
    assert anthropic_models[0].api_model_id == "claude-opus-4-6"
    assert anthropic_models[0].source_keys == [
        "claude-opus-4-6",
        "claude-opus-4-6-20260205",
    ]
    assert anthropic_models[0].verified_by_provider_metadata is True
    assert anthropic_models[0].input_cost_per_token == pytest.approx(0.005)
    assert anthropic_models[0].output_cost_per_token == pytest.approx(0.025)
    assert snapshot.index_by_source_key["claude-opus-4-6-20260205"].id == "claude-opus-4-6"
    assert await service.is_model_available("anthropic", "claude-opus-4-6-20260205") is True


@pytest.mark.asyncio
async def test_anthropic_truth_keeps_dated_id_when_provider_only_exposes_dated_variant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anthropic truth should not blindly strip dates when only the dated ID exists."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")
    payload = {
        "gpt-5.2-2025-12-11": {
            "litellm_provider": "openai",
            "mode": "chat",
        },
        "gemini-3-pro": {
            "litellm_provider": "vertex_ai-language-models",
            "mode": "chat",
        },
        "claude-opus-4-8-20260405": {
            "litellm_provider": "anthropic",
            "mode": "chat",
        },
    }

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return payload, "etag-anthropic-dated", False

    async def fake_truth_index() -> dict[str, set[str] | None]:
        return {
            "openai": None,
            "google": None,
            "anthropic": {"claude-opus-4-8-20260405"},
        }

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)
    monkeypatch.setattr(service, "_fetch_provider_truth_index", fake_truth_index)

    snapshot = await service.get_snapshot()

    assert [model.id for model in snapshot.models_by_provider["anthropic"]] == [
        "claude-opus-4-8-20260405"
    ]
    assert snapshot.models_by_provider["anthropic"][0].api_model_id == "claude-opus-4-8-20260405"


@pytest.mark.asyncio
async def test_anthropic_truth_filters_candidate_when_neither_raw_nor_canonical_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anthropic candidates absent from provider truth should be excluded."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")
    payload = {
        "gpt-5.2-2025-12-11": {
            "litellm_provider": "openai",
            "mode": "chat",
        },
        "gemini-3-pro": {
            "litellm_provider": "vertex_ai-language-models",
            "mode": "chat",
        },
        "claude-opus-4-8-20260405": {
            "litellm_provider": "anthropic",
            "mode": "chat",
        },
    }

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        assert etag is None
        return payload, "etag-anthropic-filter", False

    async def fake_truth_index() -> dict[str, set[str] | None]:
        return {
            "openai": None,
            "google": None,
            "anthropic": {"claude-opus-4-6"},
        }

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)
    monkeypatch.setattr(service, "_fetch_provider_truth_index", fake_truth_index)

    snapshot = await service.get_snapshot()

    assert snapshot.models_by_provider["anthropic"] == []
    assert "claude-opus-4-8-20260405" not in snapshot.index_by_source_key


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
        },
        "gemini-3-pro": {
            "litellm_provider": "vertex_ai-language-models",
            "mode": "chat",
        },
        "claude-sonnet-4-5-20250929": {
            "litellm_provider": "anthropic",
            "mode": "chat",
        },
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


@pytest.mark.asyncio
async def test_snapshot_normalizes_cache_pricing_fields(
    tmp_path: Path,
    sample_catalog_payload: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache read/write pricing fields should survive normalization."""
    service = LiteLLMModelCatalogService(cache_path=tmp_path / "catalog.json")

    async def fake_download(
        etag: str | None = None,
    ) -> tuple[dict[str, dict[str, object]] | None, str | None, bool]:
        return sample_catalog_payload, "test-etag", False

    monkeypatch.setattr(service, "_download_catalog_json", fake_download)

    snapshot = await service.get_snapshot()

    sonnet = snapshot.index_by_id["claude-sonnet-4-5-20250929"]
    assert sonnet.cache_read_input_token_cost == pytest.approx(0.0003)
    assert sonnet.cache_creation_input_token_cost == pytest.approx(0.00375)
    assert sonnet.max_output_tokens == 64000

    # Models without cache pricing keep None so budget falls back to input rate.
    opus = snapshot.index_by_id["claude-opus-4-1-20250805"]
    assert opus.cache_read_input_token_cost is None
    assert opus.cache_creation_input_token_cost is None

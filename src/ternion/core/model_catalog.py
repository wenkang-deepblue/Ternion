"""
LiteLLM-backed model catalog service.

This module centralizes model discovery, normalization, and local caching
for provider/model selection and pricing availability exposure.
"""

import asyncio
import contextlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx
import structlog
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ternion.core.config_store import UserConfig

logger = structlog.get_logger(__name__)

CATALOG_PROVIDERS: tuple[str, ...] = ("openai", "google", "anthropic")
DEFAULT_MODEL_CATALOG_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)
DEFAULT_MODEL_CATALOG_CACHE_PATH = Path.home() / ".ternion" / "model_catalog_cache.json"
DEFAULT_MODEL_CATALOG_ANOMALY_REPORT_PATH = (
    Path.home() / ".ternion" / "model_catalog_anomaly_report.json"
)
DEFAULT_MODEL_CATALOG_CACHE_TTL = timedelta(hours=6)
GOOGLE_DENYLIST = (
    "image",
    "deep-research",
    "audio",
    "customtools",
    "custom-tools",
    "tts",
    "robotics",
    "computer-use",
)
OPENAI_ALLOW_HINTS = ("chat", "codex", "pro")
OPENAI_DENYLIST = (
    "search-api",
    "mini",
    "nano",
    "audio",
    "realtime",
    "transcribe",
    "image",
    "embedding",
    "moderation",
    "tts",
)


class CatalogModel(BaseModel):
    """Normalized catalog entry used by Ternion."""

    id: str
    name: str
    provider: Literal["openai", "google", "anthropic"]
    mode: str = ""
    raw_key: str
    input_cost_per_token: float | None = None
    output_cost_per_token: float | None = None
    output_cost_per_reasoning_token: float | None = None
    input_cost_per_audio_token: float | None = None
    input_cost_per_token_above_200k_tokens: float | None = None
    output_cost_per_token_above_200k_tokens: float | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    stale: bool = False


class CatalogProviderStats(BaseModel):
    """Diagnostics and filtering statistics for one provider."""

    raw_candidate_ids: list[str] = Field(default_factory=list)
    filtered_ids: list[str] = Field(default_factory=list)
    suspected_filtered_ids: list[str] = Field(default_factory=list)
    raw_candidate_count: int = 0
    filtered_count: int = 0
    previous_filtered_count: int = 0


class CatalogAnomalyReport(BaseModel):
    """Structured anomaly diagnostics for model catalog refreshes."""

    generated_at: str = ""
    summary: str = ""
    trigger_conditions: list[str] = Field(default_factory=list)
    triggered_providers: list[str] = Field(default_factory=list)
    provider_stats: dict[str, CatalogProviderStats] = Field(default_factory=dict)
    used_last_successful_snapshot: bool = False
    active_snapshot_fetched_at: str = ""


class CatalogSnapshot(BaseModel):
    """Persisted snapshot of the normalized LiteLLM catalog."""

    fetched_at: str = ""
    source_url: str = DEFAULT_MODEL_CATALOG_URL
    etag: str | None = None
    models_by_provider: dict[str, list[CatalogModel]] = Field(default_factory=dict)
    index_by_id: dict[str, CatalogModel] = Field(default_factory=dict)
    provider_stats: dict[str, CatalogProviderStats] = Field(default_factory=dict)


class LiteLLMModelCatalogService:
    """Fetch, normalize, cache, and expose LiteLLM model catalog data."""

    def __init__(
        self,
        cache_path: Path | None = None,
        anomaly_report_path: Path | None = None,
        catalog_url: str = DEFAULT_MODEL_CATALOG_URL,
        cache_ttl: timedelta = DEFAULT_MODEL_CATALOG_CACHE_TTL,
        request_timeout: float = 10.0,
    ) -> None:
        """Initialize the catalog service.

        Args:
            cache_path: Disk cache location for normalized catalog snapshots.
            anomaly_report_path: Disk path for the latest anomaly report.
            catalog_url: Remote LiteLLM JSON URL.
            cache_ttl: Freshness window for memory and disk cache.
            request_timeout: HTTP timeout in seconds for remote fetches.
        """
        self.cache_path = cache_path or DEFAULT_MODEL_CATALOG_CACHE_PATH
        self.anomaly_report_path = anomaly_report_path or DEFAULT_MODEL_CATALOG_ANOMALY_REPORT_PATH
        self.catalog_url = catalog_url
        self.cache_ttl = cache_ttl
        self.request_timeout = request_timeout
        self._memory_snapshot: CatalogSnapshot | None = None
        self._latest_anomaly_report: CatalogAnomalyReport | None = None
        self._anomaly_report_checked = False
        self._refresh_lock = asyncio.Lock()

    async def get_snapshot(
        self,
        force_refresh: bool = False,
        allow_remote_fetch: bool = True,
    ) -> CatalogSnapshot:
        """Return the latest normalized catalog snapshot.

        Args:
            force_refresh: Whether to bypass freshness checks and revalidate
                against the remote catalog immediately.
            allow_remote_fetch: Whether the call may hit the remote LiteLLM
                catalog when no usable local snapshot is already available.

        Returns:
            A normalized snapshot backed by remote data, disk cache, or an
            empty snapshot when no data source is available.
        """
        if not allow_remote_fetch:
            if self._memory_snapshot is not None:
                return self._memory_snapshot

            disk_snapshot = self._load_disk_cache()
            if disk_snapshot is not None:
                self._set_memory_snapshot(disk_snapshot)
                return disk_snapshot

            empty_snapshot = self._build_empty_snapshot()
            self._set_memory_snapshot(empty_snapshot)
            return empty_snapshot

        if (
            not force_refresh
            and self._memory_snapshot
            and self._is_snapshot_fresh(self._memory_snapshot)
        ):
            return self._memory_snapshot

        async with self._refresh_lock:
            if (
                not force_refresh
                and self._memory_snapshot
                and self._is_snapshot_fresh(self._memory_snapshot)
            ):
                return self._memory_snapshot

            disk_snapshot = self._load_disk_cache()
            if not force_refresh and disk_snapshot and self._is_snapshot_fresh(disk_snapshot):
                self._set_memory_snapshot(disk_snapshot)
                return disk_snapshot

            previous_snapshot = disk_snapshot or self._memory_snapshot
            previous_successful_snapshot = self._select_successful_snapshot(
                disk_snapshot,
                self._memory_snapshot,
            )

            try:
                candidate_snapshot = await self._fetch_and_build_snapshot(previous_snapshot)
            except Exception as exc:
                logger.warning(
                    "model_catalog_fetch_failed",
                    error_type=type(exc).__name__,
                    error=str(exc),
                    exc_info=True,
                )
                if disk_snapshot is not None:
                    self._set_memory_snapshot(disk_snapshot)
                    return disk_snapshot

                empty_snapshot = self._build_empty_snapshot()
                self._set_memory_snapshot(empty_snapshot)
                return empty_snapshot

            snapshot, should_persist = self._resolve_refreshed_snapshot(
                candidate_snapshot,
                previous_successful_snapshot,
            )

            if should_persist:
                try:
                    self._save_disk_cache(snapshot)
                except Exception as exc:
                    logger.warning(
                        "model_catalog_cache_save_failed",
                        error_type=type(exc).__name__,
                        error=str(exc),
                        path=str(self.cache_path),
                        exc_info=True,
                    )

            self._set_memory_snapshot(snapshot)
            return snapshot

    async def refresh_snapshot(self) -> CatalogSnapshot:
        """Force a remote sync and bypass cache freshness checks.

        Returns:
            The active normalized catalog snapshot. If anomaly detection rejects
            the freshly fetched snapshot, this may return the previous successful
            snapshot or an empty snapshot.

        Raises:
            RuntimeError: If the remote catalog returns an invalid cache state.
            httpx.HTTPError: If the remote catalog request fails.
            ValueError: If the remote catalog payload is invalid.
        """
        async with self._refresh_lock:
            disk_snapshot = self._load_disk_cache()
            previous_snapshot = disk_snapshot or self._memory_snapshot
            previous_successful_snapshot = self._select_successful_snapshot(
                disk_snapshot,
                self._memory_snapshot,
            )
            candidate_snapshot = await self._fetch_and_build_snapshot(previous_snapshot)
            snapshot, should_persist = self._resolve_refreshed_snapshot(
                candidate_snapshot,
                previous_successful_snapshot,
            )

            if should_persist:
                try:
                    self._save_disk_cache(snapshot)
                except Exception as exc:
                    logger.warning(
                        "model_catalog_cache_save_failed",
                        error_type=type(exc).__name__,
                        error=str(exc),
                        path=str(self.cache_path),
                        exc_info=True,
                    )

            self._set_memory_snapshot(snapshot)
            return snapshot

    async def list_models(self, force_refresh: bool = False) -> dict[str, list[CatalogModel]]:
        """List normalized models grouped by provider."""
        snapshot = await self.get_snapshot(force_refresh=force_refresh)
        return snapshot.models_by_provider

    async def get_model(
        self,
        model_id: str,
        force_refresh: bool = False,
    ) -> CatalogModel | None:
        """Get a normalized model entry by model ID."""
        snapshot = await self.get_snapshot(force_refresh=force_refresh)
        return snapshot.index_by_id.get(model_id)

    def get_model_cached(self, model_id: str) -> CatalogModel | None:
        """Get a model from memory or disk cache without network access."""
        if self._memory_snapshot is not None:
            return self._memory_snapshot.index_by_id.get(model_id)

        disk_snapshot = self._load_disk_cache()
        if disk_snapshot is not None:
            self._set_memory_snapshot(disk_snapshot)
            return disk_snapshot.index_by_id.get(model_id)

        return None

    def get_anomaly_report(self) -> CatalogAnomalyReport | None:
        """Return the latest anomaly report from memory or disk, if any."""
        if self._anomaly_report_checked:
            return self._latest_anomaly_report

        report = self._load_anomaly_report()
        self._latest_anomaly_report = report
        self._anomaly_report_checked = True
        return report

    def get_anomaly_report_markdown(self) -> str | None:
        """Render the latest anomaly report as Markdown."""
        report = self.get_anomaly_report()
        if report is None:
            return None
        return self._render_anomaly_report_markdown(report)

    async def get_models_payload(
        self,
        current_config: "UserConfig | None" = None,
        force_refresh: bool = False,
        allow_remote_fetch: bool = True,
    ) -> dict[str, Any]:
        """Build the control-panel payload for model selection.

        Args:
            current_config: Reserved for future config-aware filtering.
            force_refresh: Whether to bypass cache freshness checks.
            allow_remote_fetch: Whether payload generation may initialize the
                catalog from the remote source when no local snapshot exists.

        Returns:
            A payload containing serialized provider-grouped models, the latest
            snapshot timestamp, the total normalized model count, and catalog
            initialization flags for the control panel.
        """
        _ = current_config
        snapshot = await self.get_snapshot(
            force_refresh=force_refresh,
            allow_remote_fetch=allow_remote_fetch,
        )
        models: dict[str, list[dict[str, Any]]] = {}
        for provider in CATALOG_PROVIDERS:
            provider_models = snapshot.models_by_provider.get(provider, [])
            models[provider] = [self._serialize_model(model) for model in provider_models]

        model_count = sum(len(m) for m in snapshot.models_by_provider.values())
        anomaly_report = self.get_anomaly_report()
        return {
            "models": models,
            "last_updated_at": snapshot.fetched_at,
            "model_count": model_count,
            "catalog_initialized": model_count > 0,
            "requires_initialization": model_count == 0,
            "catalog_anomaly_detected": anomaly_report is not None,
            "catalog_anomaly_summary": anomaly_report.summary if anomaly_report is not None else "",
            "catalog_anomaly_updated_at": (
                anomaly_report.generated_at if anomaly_report is not None else ""
            ),
            "catalog_anomaly_providers": (
                anomaly_report.triggered_providers if anomaly_report is not None else []
            ),
            "anomaly_report_available": anomaly_report is not None,
        }

    async def is_model_available(self, provider: str, model_id: str) -> bool:
        """Check whether a model exists in the current catalog for a provider."""
        model = await self.get_model(model_id)
        return model is not None and model.provider == provider

    def ensure_model_visible(
        self,
        provider: str,
        model_id: str,
        current_models: list[CatalogModel],
    ) -> list[CatalogModel]:
        """Return the current models unchanged."""
        _ = provider, model_id
        return current_models

    async def _fetch_and_build_snapshot(
        self,
        previous_snapshot: CatalogSnapshot | None,
    ) -> CatalogSnapshot:
        """Fetch and normalize the remote catalog snapshot."""
        etag = previous_snapshot.etag if previous_snapshot is not None else None
        payload, response_etag, not_modified = await self._download_catalog_json(etag=etag)

        if not_modified:
            if previous_snapshot is None:
                raise RuntimeError("Catalog returned not modified without a cached snapshot")
            return previous_snapshot.model_copy(
                update={
                    "etag": response_etag or previous_snapshot.etag,
                    "fetched_at": self._now_isoformat(),
                }
            )

        if payload is None:
            raise RuntimeError("Catalog payload is missing")

        return self._build_snapshot_from_payload(
            payload=payload,
            etag=response_etag,
            fetched_at=self._now_isoformat(),
        )

    async def _download_catalog_json(
        self,
        etag: str | None = None,
    ) -> tuple[dict[str, Any] | None, str | None, bool]:
        """Download the remote LiteLLM catalog JSON."""
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag

        async with httpx.AsyncClient(
            timeout=self.request_timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(self.catalog_url, headers=headers)

        if response.status_code == httpx.codes.NOT_MODIFIED:
            return None, response.headers.get("ETag") or etag, True

        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("LiteLLM catalog must be a JSON object")

        return payload, response.headers.get("ETag"), False

    def _build_snapshot_from_payload(
        self,
        payload: dict[str, Any],
        etag: str | None,
        fetched_at: str,
    ) -> CatalogSnapshot:
        """Normalize upstream JSON into a provider-grouped snapshot."""
        models_by_provider = {provider: [] for provider in CATALOG_PROVIDERS}
        index_by_id: dict[str, CatalogModel] = {}
        provider_stats = self._build_empty_provider_stats()

        for raw_key, raw_meta in payload.items():
            if not isinstance(raw_meta, dict):
                continue

            provider = self._map_provider(raw_meta.get("litellm_provider"))
            if provider is not None and self._is_raw_candidate(provider, str(raw_key), raw_meta):
                provider_stats[provider].raw_candidate_ids.append(str(raw_key))

            try:
                model = self._normalize_model_entry(str(raw_key), raw_meta)
            except Exception as exc:
                logger.warning(
                    "model_catalog_entry_parse_failed",
                    raw_key=str(raw_key),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                continue
            if model is None:
                continue

            models_by_provider[model.provider].append(model)
            index_by_id[model.id] = model
            provider_stats[model.provider].filtered_ids.append(model.id)

        for models in models_by_provider.values():
            models.sort(key=self._model_sort_key)
        for provider in CATALOG_PROVIDERS:
            provider_stats[provider].raw_candidate_count = len(
                provider_stats[provider].raw_candidate_ids
            )
            provider_stats[provider].filtered_count = len(provider_stats[provider].filtered_ids)
            provider_stats[provider].suspected_filtered_ids = [
                model_id
                for model_id in provider_stats[provider].raw_candidate_ids
                if model_id not in set(provider_stats[provider].filtered_ids)
            ]

        return CatalogSnapshot(
            fetched_at=fetched_at,
            source_url=self.catalog_url,
            etag=etag,
            models_by_provider=models_by_provider,
            index_by_id=index_by_id,
            provider_stats=provider_stats,
        )

    def _normalize_model_entry(self, model_id: str, meta: dict[str, Any]) -> CatalogModel | None:
        """Normalize a single upstream model entry when it matches project rules."""
        provider = self._map_provider(meta.get("litellm_provider"))
        if provider == "openai":
            if not self._is_openai_model_allowed(model_id, meta):
                return None
            display_name = self._format_openai_name(model_id)
        elif provider == "google":
            if not self._is_google_model_allowed(model_id, meta):
                return None
            display_name = self._format_google_name(model_id)
        elif provider == "anthropic":
            if not self._is_anthropic_model_allowed(model_id, meta):
                return None
            display_name = self._format_anthropic_name(model_id)
        else:
            return None

        return CatalogModel(
            id=model_id,
            name=display_name,
            provider=provider,
            mode=str(meta.get("mode", "") or ""),
            raw_key=model_id,
            input_cost_per_token=self._coerce_float(meta.get("input_cost_per_token")),
            output_cost_per_token=self._coerce_float(meta.get("output_cost_per_token")),
            output_cost_per_reasoning_token=self._coerce_float(
                meta.get("output_cost_per_reasoning_token")
            ),
            input_cost_per_audio_token=self._coerce_float(meta.get("input_cost_per_audio_token")),
            input_cost_per_token_above_200k_tokens=self._coerce_float(
                meta.get("input_cost_per_token_above_200k_tokens")
            ),
            output_cost_per_token_above_200k_tokens=self._coerce_float(
                meta.get("output_cost_per_token_above_200k_tokens")
            ),
            max_input_tokens=self._coerce_int(meta.get("max_input_tokens")),
            max_output_tokens=self._coerce_int(meta.get("max_output_tokens")),
        )

    def _load_disk_cache(self) -> CatalogSnapshot | None:
        """Load the persisted snapshot from disk if available."""
        if not self.cache_path.exists():
            return None

        try:
            with open(self.cache_path, encoding="utf-8") as cache_file:
                payload = json.load(cache_file)
            snapshot = CatalogSnapshot.model_validate(payload)
            snapshot = self._ensure_provider_buckets(snapshot)
            return snapshot
        except Exception as exc:
            logger.warning(
                "model_catalog_cache_load_failed",
                error_type=type(exc).__name__,
                error=str(exc),
                path=str(self.cache_path),
                exc_info=True,
            )
            return None

    def _save_disk_cache(self, snapshot: CatalogSnapshot) -> None:
        """Persist the normalized snapshot using an atomic file replace."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = snapshot.model_dump(mode="json")
        fd, tmp_path = tempfile.mkstemp(
            dir=self.cache_path.parent,
            suffix=".tmp",
            prefix="model_catalog_",
        )

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as cache_file:
                json.dump(payload, cache_file, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.cache_path)
        except Exception:
            with contextlib.suppress(OSError):
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            raise

    def _set_memory_snapshot(self, snapshot: CatalogSnapshot) -> None:
        """Store a normalized snapshot in memory."""
        self._memory_snapshot = self._ensure_provider_buckets(snapshot)

    def _is_snapshot_fresh(self, snapshot: CatalogSnapshot) -> bool:
        """Return whether a snapshot is still within the freshness window."""
        fetched_at = self._parse_timestamp(snapshot.fetched_at)
        if fetched_at is None:
            return False
        return datetime.now(UTC) - fetched_at <= self.cache_ttl

    def _ensure_provider_buckets(self, snapshot: CatalogSnapshot) -> CatalogSnapshot:
        """Ensure all supported providers exist in the grouped model mapping."""
        models_by_provider = {
            provider: list(snapshot.models_by_provider.get(provider, []))
            for provider in CATALOG_PROVIDERS
        }
        provider_stats = {
            provider: snapshot.provider_stats.get(provider, CatalogProviderStats()).model_copy(
                deep=True
            )
            for provider in CATALOG_PROVIDERS
        }
        for provider in CATALOG_PROVIDERS:
            provider_stats[provider].filtered_count = len(models_by_provider[provider])
            if not provider_stats[provider].filtered_ids:
                provider_stats[provider].filtered_ids = [
                    model.id for model in models_by_provider[provider]
                ]
            provider_stats[provider].raw_candidate_count = len(
                provider_stats[provider].raw_candidate_ids
            )
            provider_stats[provider].suspected_filtered_ids = [
                model_id
                for model_id in provider_stats[provider].raw_candidate_ids
                if model_id not in set(provider_stats[provider].filtered_ids)
            ]
        return snapshot.model_copy(
            update={
                "models_by_provider": models_by_provider,
                "provider_stats": provider_stats,
            }
        )

    def _build_empty_snapshot(self) -> CatalogSnapshot:
        """Build an empty catalog snapshot."""
        return CatalogSnapshot(
            fetched_at="",
            source_url=self.catalog_url,
            etag=None,
            models_by_provider={provider: [] for provider in CATALOG_PROVIDERS},
            index_by_id={},
            provider_stats=self._build_empty_provider_stats(),
        )

    def _map_provider(self, raw_provider: Any) -> Literal["openai", "google", "anthropic"] | None:
        """Map LiteLLM provider names to Ternion provider names.

        Returns ``None`` for unsupported providers so the entry can be skipped.
        """
        if raw_provider in {"gemini", "vertex_ai-language-models"}:
            return "google"
        if raw_provider in {"openai", "anthropic"}:
            return raw_provider
        return None

    def _is_openai_model_allowed(self, model_id: str, meta: dict[str, Any]) -> bool:
        """Return whether an OpenAI model matches project filtering rules."""
        if meta.get("litellm_provider") != "openai":
            return False
        lowered = model_id.lower()
        if "/" in model_id or "chatgpt" in lowered:
            return False
        tokens = self._tokenize_model_id(lowered)
        if "gpt" not in tokens:
            return False
        if not self._has_version_token_after_keyword(
            lowered, "gpt", minimum_major=5, require_minor=True
        ):
            return False
        if any(token in lowered for token in OPENAI_DENYLIST):
            return False

        mode = str(meta.get("mode", "") or "").lower()
        if mode in {"chat", "completion"}:
            return True
        return any(hint in lowered for hint in OPENAI_ALLOW_HINTS)

    def _is_google_model_allowed(self, model_id: str, meta: dict[str, Any]) -> bool:
        """Return whether a Google model matches project filtering rules."""
        if meta.get("litellm_provider") not in {"gemini", "vertex_ai-language-models"}:
            return False
        lowered = model_id.lower()
        if "/" in model_id or "gemini" not in lowered:
            return False
        major = self._parse_first_major_version_near_keyword(lowered, "gemini")
        if major is None or major < 3:
            return False

        mode = str(meta.get("mode", "") or "").lower()
        if mode and mode != "chat":
            return False

        return not any(token in lowered for token in GOOGLE_DENYLIST)

    def _is_anthropic_model_allowed(self, model_id: str, meta: dict[str, Any]) -> bool:
        """Return whether an Anthropic model matches project filtering rules."""
        if meta.get("litellm_provider") != "anthropic":
            return False
        if "/" in model_id or not model_id.startswith("claude-"):
            return False

        lowered = model_id.lower()
        if "haiku" in lowered:
            return False
        if not any(series in lowered for series in ("sonnet", "opus")):
            return False

        major = self._parse_anthropic_major_version(model_id)
        return major is not None and major >= 4

    def _format_openai_name(self, model_id: str) -> str:
        """Format an OpenAI model ID into a display name."""
        words = []
        for part in model_id.replace("-", " ").split():
            if part.lower() in {"gpt", "api"}:
                words.append(part.upper())
            else:
                words.append(part.capitalize())
        return " ".join(words)

    def _format_google_name(self, model_id: str) -> str:
        """Format a Google model ID into a display name.

        The ``-preview`` suffix is removed before formatting.
        """
        normalized = model_id.removesuffix("-preview")
        words = []
        for part in normalized.replace("-", " ").split():
            if part.lower() == "gemini":
                words.append("Gemini")
            else:
                words.append(part.capitalize())
        return " ".join(words)

    def _format_anthropic_name(self, model_id: str) -> str:
        """Format an Anthropic model ID into a display name.

        Supported forms include family-first IDs such as
        ``claude-sonnet-4-6``, ``claude-sonnet-4-5-20250929``, and legacy
        version-first IDs such as ``claude-4-1-sonnet-latest``.
        """
        parts = model_id.split("-")

        # Family-first: claude-{family}-{major}-{minor}[-date...]
        if len(parts) >= 4 and parts[1] in {"sonnet", "opus"} and parts[2].isdigit():
            family = parts[1].capitalize()
            if len(parts) >= 4 and parts[3].isdigit() and not self._looks_like_date(parts[3]):
                return f"Claude {family} {parts[2]}.{parts[3]}"
            return f"Claude {family} {parts[2]}"

        # Version-first: claude-{major}-{minor}-{family}[-...]
        if len(parts) >= 4 and parts[1].isdigit():
            if len(parts) >= 5 and parts[2].isdigit() and parts[3] in {"sonnet", "opus"}:
                family = parts[3].capitalize()
                return f"Claude {family} {parts[1]}.{parts[2]}"
            if parts[2] in {"sonnet", "opus"}:
                family = parts[2].capitalize()
                return f"Claude {family} {parts[1]}"

        return model_id

    @staticmethod
    def _looks_like_date(token: str) -> bool:
        """Return True if a token looks like a YYYYMMDD date prefix."""
        return len(token) >= 8 and token[:8].isdigit()

    def _is_raw_candidate(self, provider: str, model_id: str, meta: dict[str, Any]) -> bool:
        """Return whether an entry should appear in anomaly raw-candidate diagnostics."""
        lowered = model_id.lower()
        if "/" in model_id:
            return False
        if provider == "openai":
            if meta.get("litellm_provider") != "openai" or "chatgpt" in lowered:
                return False
            if any(token in lowered for token in OPENAI_DENYLIST):
                return False
            tokens = self._tokenize_model_id(lowered)
            return "gpt" in tokens and self._has_version_token_after_keyword(
                lowered,
                "gpt",
                minimum_major=5,
                require_minor=True,
            )
        if provider == "google":
            if meta.get("litellm_provider") not in {"gemini", "vertex_ai-language-models"}:
                return False
            if "gemini" not in lowered:
                return False
            major = self._parse_first_major_version_near_keyword(lowered, "gemini")
            return major is not None and major >= 3
        if provider == "anthropic":
            if meta.get("litellm_provider") != "anthropic" or "claude" not in lowered:
                return False
            major = self._parse_first_major_version_near_keyword(lowered, "claude")
            return major is not None and major >= 4
        return False

    def _parse_major_version_after_prefix(self, model_id: str, prefix: str) -> int | None:
        """Parse the first integer version component after a prefix."""
        suffix = model_id.removeprefix(prefix)
        match = re.match(r"(\d+)", suffix)
        if match is None:
            return None
        return int(match.group(1))

    def _parse_first_major_version_near_keyword(self, model_id: str, keyword: str) -> int | None:
        """Parse the first one- or two-digit major version following a keyword token."""
        tokens = self._tokenize_model_id(model_id)
        try:
            keyword_index = tokens.index(keyword)
        except ValueError:
            return None

        for token in tokens[keyword_index + 1 :]:
            match = re.fullmatch(r"(\d{1,2})(?:\.(\d+))?", token)
            if match is not None:
                return int(match.group(1))
        return None

    def _has_version_token_after_keyword(
        self,
        model_id: str,
        keyword: str,
        minimum_major: int,
        require_minor: bool = False,
    ) -> bool:
        """Return whether a version token after a keyword satisfies the threshold."""
        tokens = self._tokenize_model_id(model_id)
        try:
            keyword_index = tokens.index(keyword)
        except ValueError:
            return False

        for token in tokens[keyword_index + 1 :]:
            match = re.fullmatch(r"(\d{1,2})(?:\.(\d+))?", token)
            if match is None:
                continue
            major = int(match.group(1))
            minor = match.group(2)
            if require_minor and minor is None:
                continue
            if major >= minimum_major:
                return True
        return False

    def _parse_anthropic_major_version(self, model_id: str) -> int | None:
        """Parse the Anthropic major version from supported model ID formats."""
        family_first_match = re.match(r"^claude-(?:sonnet|opus)-(\d+)", model_id)
        if family_first_match is not None:
            return int(family_first_match.group(1))

        version_first_match = re.match(r"^claude-(\d+)-\d+-(?:sonnet|opus)(?:-|$)", model_id)
        if version_first_match is not None:
            return int(version_first_match.group(1))

        return None

    def _tokenize_model_id(self, model_id: str) -> list[str]:
        """Split a model ID into lowercase diagnostic tokens."""
        return [token for token in re.split(r"[^a-z0-9.]+", model_id.lower()) if token]

    def _build_empty_provider_stats(self) -> dict[str, CatalogProviderStats]:
        """Build empty diagnostics buckets for all supported providers."""
        return {provider: CatalogProviderStats() for provider in CATALOG_PROVIDERS}

    def _select_successful_snapshot(
        self,
        *snapshots: CatalogSnapshot | None,
    ) -> CatalogSnapshot | None:
        """Return the first snapshot that contains at least one filtered model."""
        for snapshot in snapshots:
            if snapshot is not None and self._snapshot_model_count(snapshot) > 0:
                return snapshot
        return None

    def _snapshot_model_count(self, snapshot: CatalogSnapshot) -> int:
        """Count the normalized models stored in a snapshot."""
        return sum(len(models) for models in snapshot.models_by_provider.values())

    def _resolve_refreshed_snapshot(
        self,
        candidate_snapshot: CatalogSnapshot,
        previous_successful_snapshot: CatalogSnapshot | None,
    ) -> tuple[CatalogSnapshot, bool]:
        """Resolve a fetched snapshot into the active snapshot and persistence policy.

        Returns:
            A tuple of ``(active_snapshot, should_persist)``. Persistence is
            skipped when anomaly detection rejects the freshly fetched snapshot.
        """
        report = self._evaluate_anomaly(candidate_snapshot, previous_successful_snapshot)
        if report is None:
            self._clear_anomaly_report()
            return candidate_snapshot, True

        if previous_successful_snapshot is not None:
            report.used_last_successful_snapshot = True
            report.active_snapshot_fetched_at = previous_successful_snapshot.fetched_at
            self._store_anomaly_report(report)
            return previous_successful_snapshot, False

        report.used_last_successful_snapshot = False
        report.active_snapshot_fetched_at = ""
        self._store_anomaly_report(report)
        return self._build_empty_snapshot(), False

    def _evaluate_anomaly(
        self,
        candidate_snapshot: CatalogSnapshot,
        previous_successful_snapshot: CatalogSnapshot | None,
    ) -> CatalogAnomalyReport | None:
        """Evaluate whether a freshly fetched snapshot should be treated as anomalous."""
        provider_stats = self._build_empty_provider_stats()
        trigger_conditions: list[str] = []
        triggered_providers: list[str] = []

        for provider in CATALOG_PROVIDERS:
            stats = candidate_snapshot.provider_stats.get(
                provider, CatalogProviderStats()
            ).model_copy(deep=True)
            previous_filtered_count = 0
            if previous_successful_snapshot is not None:
                previous_filtered_count = len(
                    previous_successful_snapshot.models_by_provider.get(provider, [])
                )
            stats.previous_filtered_count = previous_filtered_count
            provider_stats[provider] = stats

            if stats.filtered_count == 0:
                trigger_conditions.append(f"{provider}: filtered model count is 0")
                triggered_providers.append(provider)
                continue

            if previous_filtered_count > 0:
                drop_ratio = (
                    previous_filtered_count - stats.filtered_count
                ) / previous_filtered_count
                if drop_ratio > 0.8:
                    trigger_conditions.append(
                        f"{provider}: filtered model count dropped from "
                        f"{previous_filtered_count} to {stats.filtered_count}"
                    )
                    triggered_providers.append(provider)

        if not trigger_conditions:
            return None

        unique_triggered_providers = list(dict.fromkeys(triggered_providers))
        summary = (
            "Model catalog anomaly detected for " + ", ".join(unique_triggered_providers) + "."
        )
        return CatalogAnomalyReport(
            generated_at=self._now_isoformat(),
            summary=summary,
            trigger_conditions=trigger_conditions,
            triggered_providers=unique_triggered_providers,
            provider_stats=provider_stats,
        )

    def _load_anomaly_report(self) -> CatalogAnomalyReport | None:
        """Load the latest anomaly report from disk if available."""
        if not self.anomaly_report_path.exists():
            return None

        try:
            with open(self.anomaly_report_path, encoding="utf-8") as report_file:
                payload = json.load(report_file)
            return CatalogAnomalyReport.model_validate(payload)
        except Exception as exc:
            logger.warning(
                "model_catalog_anomaly_report_load_failed",
                error_type=type(exc).__name__,
                error=str(exc),
                path=str(self.anomaly_report_path),
                exc_info=True,
            )
            return None

    def _save_anomaly_report(self, report: CatalogAnomalyReport) -> None:
        """Persist and cache the latest anomaly report."""
        self._latest_anomaly_report = report
        self._anomaly_report_checked = True
        self.anomaly_report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = report.model_dump(mode="json")
        fd, tmp_path = tempfile.mkstemp(
            dir=self.anomaly_report_path.parent,
            suffix=".tmp",
            prefix="model_catalog_anomaly_",
        )
        report_file_handle = None

        try:
            report_file_handle = os.fdopen(fd, "w", encoding="utf-8")
            with report_file_handle as report_file:
                json.dump(payload, report_file, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.anomaly_report_path)
        except Exception:
            if report_file_handle is None:
                with contextlib.suppress(OSError):
                    os.close(fd)
            with contextlib.suppress(OSError):
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            raise

    def _store_anomaly_report(self, report: CatalogAnomalyReport) -> None:
        """Persist anomaly diagnostics without breaking the refresh path."""
        try:
            self._save_anomaly_report(report)
        except Exception as exc:
            logger.warning(
                "model_catalog_anomaly_report_save_failed",
                error_type=type(exc).__name__,
                error=str(exc),
                path=str(self.anomaly_report_path),
                exc_info=True,
            )
            self._latest_anomaly_report = report
            self._anomaly_report_checked = True

    def _clear_anomaly_report(self) -> None:
        """Remove any persisted anomaly report after a healthy refresh."""
        self._latest_anomaly_report = None
        self._anomaly_report_checked = True
        try:
            if self.anomaly_report_path.exists():
                os.unlink(self.anomaly_report_path)
        except OSError as exc:
            logger.warning(
                "model_catalog_anomaly_report_delete_failed",
                error_type=type(exc).__name__,
                error=str(exc),
                path=str(self.anomaly_report_path),
                exc_info=True,
            )

    def _render_anomaly_report_markdown(self, report: CatalogAnomalyReport) -> str:
        """Render a human-readable Markdown anomaly report."""
        lines = [
            "# Model Catalog Anomaly Report",
            "",
            "## Summary",
            f"- Generated at: `{report.generated_at}`",
            f"- Summary: {report.summary}",
            f"- Used last successful snapshot: `{str(report.used_last_successful_snapshot).lower()}`",
            f"- Active snapshot fetched at: `{report.active_snapshot_fetched_at or 'N/A'}`",
            "",
            "## Trigger Conditions",
        ]
        lines.extend(f"- {condition}" for condition in report.trigger_conditions)
        lines.append("")
        lines.append("## Provider Counts")
        lines.append("")
        lines.append("| Provider | Raw candidates | Filtered | Previous filtered |")
        lines.append("| --- | ---: | ---: | ---: |")

        for provider in CATALOG_PROVIDERS:
            stats = report.provider_stats.get(provider, CatalogProviderStats())
            lines.append(
                f"| {provider} | {stats.raw_candidate_count} | {stats.filtered_count} | "
                f"{stats.previous_filtered_count} |"
            )

        for provider in CATALOG_PROVIDERS:
            stats = report.provider_stats.get(provider, CatalogProviderStats())
            lines.extend(
                [
                    "",
                    f"## {provider.title()} Raw Candidates",
                ]
            )
            if stats.raw_candidate_ids:
                lines.extend(f"- `{model_id}`" for model_id in stats.raw_candidate_ids)
            else:
                lines.append("- None")

            lines.extend(
                [
                    "",
                    f"## {provider.title()} Filtered Models",
                ]
            )
            if stats.filtered_ids:
                lines.extend(f"- `{model_id}`" for model_id in stats.filtered_ids)
            else:
                lines.append("- None")

            lines.extend(
                [
                    "",
                    f"## {provider.title()} Suspected Filtered Models",
                ]
            )
            if stats.suspected_filtered_ids:
                lines.extend(f"- `{model_id}`" for model_id in stats.suspected_filtered_ids)
            else:
                lines.append("- None")

        return "\n".join(lines)

    def _serialize_model(self, model: CatalogModel) -> dict[str, Any]:
        """Serialize a model for control-panel payloads."""
        return {
            "id": model.id,
            "name": model.name,
            "stale": model.stale,
            "pricing_available": any(
                value is not None
                for value in (
                    model.input_cost_per_token,
                    model.output_cost_per_token,
                    model.output_cost_per_reasoning_token,
                    model.input_cost_per_audio_token,
                    model.input_cost_per_token_above_200k_tokens,
                    model.output_cost_per_token_above_200k_tokens,
                )
            ),
        }

    def _model_sort_key(self, model: CatalogModel) -> tuple[str, str]:
        """Build a sort key using lowercase name first, then lowercase ID."""
        return (model.name.lower(), model.id.lower())

    def _coerce_float(self, value: Any) -> float | None:
        """Coerce numeric catalog values into floats."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _coerce_int(self, value: Any) -> int | None:
        """Coerce numeric catalog values into integers."""
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _parse_timestamp(self, value: str) -> datetime | None:
        """Parse an ISO-8601 timestamp into a timezone-aware datetime."""
        if not value:
            return None

        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

    def _now_isoformat(self) -> str:
        """Return the current UTC timestamp in normalized ISO format."""
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")


model_catalog_service = LiteLLMModelCatalogService()

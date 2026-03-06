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
DEFAULT_MODEL_CATALOG_CACHE_TTL = timedelta(hours=6)
GOOGLE_DENYLIST = ("image", "customtools", "custom-tools")


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


class CatalogSnapshot(BaseModel):
    """Persisted snapshot of the normalized LiteLLM catalog."""

    fetched_at: str = ""
    source_url: str = DEFAULT_MODEL_CATALOG_URL
    etag: str | None = None
    models_by_provider: dict[str, list[CatalogModel]] = Field(default_factory=dict)
    index_by_id: dict[str, CatalogModel] = Field(default_factory=dict)


class LiteLLMModelCatalogService:
    """Fetch, normalize, cache, and expose LiteLLM model catalog data."""

    def __init__(
        self,
        cache_path: Path | None = None,
        catalog_url: str = DEFAULT_MODEL_CATALOG_URL,
        cache_ttl: timedelta = DEFAULT_MODEL_CATALOG_CACHE_TTL,
        request_timeout: float = 10.0,
    ) -> None:
        """Initialize the catalog service.

        Args:
            cache_path: Disk cache location for normalized catalog snapshots.
            catalog_url: Remote LiteLLM JSON URL.
            cache_ttl: Freshness window for memory and disk cache.
            request_timeout: HTTP timeout in seconds for remote fetches.
        """
        self.cache_path = cache_path or DEFAULT_MODEL_CATALOG_CACHE_PATH
        self.catalog_url = catalog_url
        self.cache_ttl = cache_ttl
        self.request_timeout = request_timeout
        self._memory_snapshot: CatalogSnapshot | None = None
        self._refresh_lock = asyncio.Lock()

    async def get_snapshot(self, force_refresh: bool = False) -> CatalogSnapshot:
        """Return the latest normalized catalog snapshot.

        Args:
            force_refresh: Whether to bypass freshness checks and revalidate
                against the remote catalog immediately.

        Returns:
            A normalized snapshot backed by remote data, disk cache, or an
            empty snapshot when no data source is available.
        """
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

            try:
                snapshot = await self._fetch_and_build_snapshot(previous_snapshot)
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

    async def get_models_payload(
        self, current_config: "UserConfig | None" = None
    ) -> dict[str, Any]:
        """Build the control-panel payload for model selection.

        Args:
            current_config: Reserved for future config-aware filtering.

        Returns:
            A payload containing serialized provider-grouped models and the
            latest snapshot timestamp.
        """
        _ = current_config
        snapshot = await self.get_snapshot()
        models: dict[str, list[dict[str, Any]]] = {}
        for provider in CATALOG_PROVIDERS:
            provider_models = snapshot.models_by_provider.get(provider, [])
            models[provider] = [self._serialize_model(model) for model in provider_models]

        return {
            "models": models,
            "last_updated_at": snapshot.fetched_at,
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
        """Return models unchanged.

        This placeholder is reserved for future UI visibility filtering under
        strict catalog mode.
        """
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

        for raw_key, raw_meta in payload.items():
            if not isinstance(raw_meta, dict):
                continue

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

        for models in models_by_provider.values():
            models.sort(key=self._model_sort_key)

        return CatalogSnapshot(
            fetched_at=fetched_at,
            source_url=self.catalog_url,
            etag=etag,
            models_by_provider=models_by_provider,
            index_by_id=index_by_id,
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
        return snapshot.model_copy(update={"models_by_provider": models_by_provider})

    def _build_empty_snapshot(self) -> CatalogSnapshot:
        """Build an empty catalog snapshot."""
        return CatalogSnapshot(
            fetched_at="",
            source_url=self.catalog_url,
            etag=None,
            models_by_provider={provider: [] for provider in CATALOG_PROVIDERS},
            index_by_id={},
        )

    def _map_provider(self, raw_provider: Any) -> Literal["openai", "google", "anthropic"] | None:
        """Map LiteLLM provider names to Ternion provider names.

        Returns ``None`` for unsupported providers so the entry can be skipped.
        """
        if raw_provider == "gemini":
            return "google"
        if raw_provider in {"openai", "anthropic"}:
            return raw_provider
        return None

    def _is_openai_model_allowed(self, model_id: str, meta: dict[str, Any]) -> bool:
        """Return whether an OpenAI model matches project filtering rules."""
        if meta.get("litellm_provider") != "openai":
            return False
        if "/" in model_id or not model_id.startswith("gpt-"):
            return False

        major = self._parse_major_version_after_prefix(model_id, "gpt-")
        if major is None or major < 5:
            return False

        mode = str(meta.get("mode", "") or "")
        return mode in {"chat", "completion"} or "codex" in model_id.lower()

    def _is_google_model_allowed(self, model_id: str, meta: dict[str, Any]) -> bool:
        """Return whether a Google model matches project filtering rules."""
        if meta.get("litellm_provider") != "gemini":
            return False
        if "/" in model_id or not model_id.startswith("gemini-"):
            return False

        major = self._parse_major_version_after_prefix(model_id, "gemini-")
        if major is None or major < 3:
            return False

        mode = str(meta.get("mode", "") or "")
        if mode and mode != "chat":
            return False

        lowered = model_id.lower()
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
        ``claude-sonnet-4-5-20250929`` and legacy version-first IDs such as
        ``claude-4-1-sonnet-latest``.
        """
        parts = model_id.split("-")
        if (
            len(parts) >= 5
            and parts[1] in {"sonnet", "opus"}
            and parts[2].isdigit()
            and parts[3].isdigit()
        ):
            family = parts[1].capitalize()
            version = f"{parts[2]}.{parts[3]}"
            return f"Claude {family} {version}"
        if len(parts) >= 4 and parts[1] in {"sonnet", "opus"} and parts[2].isdigit():
            family = parts[1].capitalize()
            return f"Claude {family} {parts[2]}"
        if (
            len(parts) >= 5
            and parts[1].isdigit()
            and parts[2].isdigit()
            and parts[3] in {"sonnet", "opus"}
        ):
            family = parts[3].capitalize()
            version = f"{parts[1]}.{parts[2]}"
            return f"Claude {family} {version}"
        if len(parts) >= 4 and parts[1].isdigit() and parts[2] in {"sonnet", "opus"}:
            family = parts[2].capitalize()
            return f"Claude {family} {parts[1]}"
        return model_id

    def _parse_major_version_after_prefix(self, model_id: str, prefix: str) -> int | None:
        """Parse the first integer version component after a prefix."""
        suffix = model_id.removeprefix(prefix)
        match = re.match(r"(\d+)", suffix)
        if match is None:
            return None
        return int(match.group(1))

    def _parse_anthropic_major_version(self, model_id: str) -> int | None:
        """Parse the Anthropic major version from supported model ID formats."""
        family_first_match = re.match(r"^claude-(?:sonnet|opus)-(\d+)", model_id)
        if family_first_match is not None:
            return int(family_first_match.group(1))

        version_first_match = re.match(r"^claude-(\d+)-\d+-(?:sonnet|opus)(?:-|$)", model_id)
        if version_first_match is not None:
            return int(version_first_match.group(1))

        return None

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

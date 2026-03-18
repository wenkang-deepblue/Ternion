"""
Control Panel API routes.

Provides REST API endpoints for the Web Control Panel to manage:
- Provider configuration (API keys)
- Role-model assignments
- Budget settings
- Usage statistics
"""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any, get_args

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from ternion.core.budget import budget_manager
from ternion.core.config_store import (
    ApiKeyEntry,
    ProviderConfig,
    PublicAccessConfig,
    PublicAccessMode,
    RoleConfig,
    UserConfig,
    config_store,
)
from ternion.core.model_catalog import CatalogModel, model_catalog_service
from ternion.core.model_probe import (
    ModelAvailabilityProbeResult,
    model_availability_probe_service,
)
from ternion.core.public_access import (
    build_public_origin,
    normalize_public_base_url,
    resolve_effective_public_base_url,
)
from ternion.providers.manager import provider_manager
from ternion.server.model_catalog_refresh import (
    VALID_REFRESH_MODES,
    compute_next_refresh_at,
    normalize_time_of_day,
    refresh_catalog_and_update_schedule,
)
from ternion.utils.log_manager import log_manager
from ternion.utils.secrets import redact_secrets

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api", tags=["control-panel"])
VALID_PUBLIC_ACCESS_MODES = set(get_args(PublicAccessMode))

# Sync budget settings from config_store to budget_manager on module load.
# This ensures user-configured budget persists across server restarts.
# Wrapped in try/except to prevent module import failure on corrupt or missing config.
try:
    _init_config = config_store.load()
    if _init_config and _init_config.budget:
        budget_manager.settings.monthly_limit_usd = _init_config.budget.monthly_limit_usd
        budget_manager.settings.alert_threshold = _init_config.budget.alert_threshold
        logger.info(
            "budget_settings_loaded",
            monthly_limit_usd=_init_config.budget.monthly_limit_usd,
            alert_threshold=_init_config.budget.alert_threshold,
        )
except Exception:
    logger.warning("budget_settings_load_failed", exc_info=True)


# Request/Response Models
class AddApiKeyRequest(BaseModel):
    """Request to add an API key."""

    provider: str
    name: str
    api_key: str


class DeleteApiKeyRequest(BaseModel):
    """Request to delete an API key."""

    provider: str
    key_id: str


class SelectApiKeyRequest(BaseModel):
    """Request to select an API key."""

    provider: str
    key_id: str


class RoleUpdateRequest(BaseModel):
    """Request to update a role."""

    provider: str
    model: str


class RolesUpdateRequest(BaseModel):
    """Request to update roles."""

    # Ternion members (Divergence phase)
    ternion_a: RoleUpdateRequest | None = None
    ternion_b: RoleUpdateRequest | None = None
    ternion_c: RoleUpdateRequest | None = None
    # Core roles
    arbiter: RoleUpdateRequest | None = None
    writer: RoleUpdateRequest | None = None
    reviewer: RoleUpdateRequest | None = None


class BudgetUpdateRequest(BaseModel):
    """Request to update budget settings."""

    monthly_limit_usd: float | None = None
    alert_threshold: float | None = None


class ModelCatalogRefreshUpdateRequest(BaseModel):
    """Request to update model catalog refresh scheduling."""

    enabled: bool | None = None
    mode: str | None = None
    time_of_day: str | None = None
    interval_value: int | None = None


class ConfigUpdateRequest(BaseModel):
    """Request to update configuration."""

    roles: RolesUpdateRequest | None = None
    budget: BudgetUpdateRequest | None = None
    execution_mode: str | None = None  # "cursor_handoff" or "ternion_full"
    model_catalog_refresh: ModelCatalogRefreshUpdateRequest | None = None


class RoleSelectionLogRequest(BaseModel):
    """Request to log a role model selection without saving."""

    role: str
    provider: str
    model: str


class ExecutionModeSelectionLogRequest(BaseModel):
    """Request to log an execution mode selection without saving."""

    execution_mode: str  # "cursor_handoff" | "ternion_full"


class TestProviderRequest(BaseModel):
    """Request to test a provider connection."""

    provider: str
    api_key: str


class TestProviderResponse(BaseModel):
    """Response from provider test."""

    success: bool
    message: str
    code: str


class PortsUpdateRequest(BaseModel):
    """Request to update port configuration."""

    backend: int | None = None
    web: int | None = None


class PublicAccessUpdateRequest(BaseModel):
    """Request to update public access guidance settings."""

    mode: str | None = None
    public_base_url: str | None = None


# Display name mapping for providers
PROVIDER_DISPLAY_NAMES = {
    "google": "Google Gemini",
    "anthropic": "Anthropic Claude",
    "openai": "OpenAI GPT",
}


def _get_provider_display_name(provider: str) -> str:
    """Get human-readable display name for a provider.

    Args:
        provider: The provider ID.

    Returns:
        The display name of the provider.
    """
    return PROVIDER_DISPLAY_NAMES.get(provider, provider.title())


def _build_request_public_origin(request: Request) -> str:
    """Build a public origin from request headers for public-access detection.

    Args:
        request: Incoming control-panel request.

    Returns:
        A normalized public origin, or an empty string when the request resolves
        to a local or otherwise non-public address.
    """
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    forwarded_host = request.headers.get("x-forwarded-host", "")
    scheme = (forwarded_proto or request.url.scheme or "").strip()
    host = (forwarded_host or request.headers.get("host") or request.url.netloc or "").strip()
    return build_public_origin(scheme, host)


def _serialize_public_access_state(request: Request, config: UserConfig) -> dict[str, Any]:
    """Serialize current public-access state for API responses.

    Args:
        request: Incoming control-panel request.
        config: User configuration object.

    Returns:
        A dictionary containing configured and effective public-access values.
    """
    mode = str(config.public_access.mode or "none")
    if mode not in VALID_PUBLIC_ACCESS_MODES:
        mode = "none"

    configured_public_base_url = normalize_public_base_url(
        str(config.public_access.public_base_url or "")
    )
    effective_public_base_url, effective_source = resolve_effective_public_base_url(
        configured_public_base_url,
        request_origin=_build_request_public_origin(request),
    )
    return {
        "mode": mode,
        "configured_public_base_url": configured_public_base_url,
        "effective_public_base_url": effective_public_base_url,
        "effective_source": effective_source,
        "cursor_override_base_url": effective_public_base_url,
        "configured": bool(effective_public_base_url),
        "requires_public_url": True,
    }


def _canonicalize_config_roles(config: object) -> bool:
    """Canonicalize role model IDs in an in-memory config object when possible.

    Args:
        config: The config object to canonicalize.

    Returns:
        True if the configuration was modified, False otherwise.
    """
    roles = getattr(config, "roles", None)
    if not isinstance(roles, dict):
        return False

    changed = False
    for role in roles.values():
        provider = getattr(role, "provider", "")
        model = getattr(role, "model", "")
        if not provider or not model:
            continue

        catalog_model = model_catalog_service.get_model_cached(model)
        if catalog_model is None or catalog_model.provider != provider:
            continue
        if catalog_model.id == model:
            continue

        role.model = catalog_model.id
        changed = True

    return changed


async def _get_model_display_name(provider: str, model_id: str) -> str:
    """Get human-readable display name for a model.

    Args:
        provider: The provider ID.
        model_id: The model ID.

    Returns:
        The display name of the model.
    """
    model = model_catalog_service.get_model_cached(model_id)
    if model is not None and model.provider == provider:
        return model.name
    return model_id


async def _get_catalog_model_for_provider(provider: str, model_id: str) -> CatalogModel:
    """Get a catalog model and enforce provider/model consistency.

    Args:
        provider: The provider ID.
        model_id: The model ID.

    Returns:
        The matching catalog model.

    Raises:
        HTTPException: If the model is missing from the catalog or belongs to a
            different provider.
    """
    model = model_catalog_service.get_model_cached(model_id)
    if model is None or model.provider != provider:
        log_manager.emit(
            "ERROR",
            "ERROR",
            f"Model '{model_id}' is not available for provider '{provider}' in the current catalog.",
        )
        raise HTTPException(status_code=400, detail="MODEL_NOT_AVAILABLE")
    return model


def _build_model_probe_failure_response(result: ModelAvailabilityProbeResult) -> JSONResponse:
    """Build a structured HTTP response for a failed model probe.

    Args:
        result: The result from a failed model probe.

    Returns:
        A formatted JSONResponse representing the failure.
    """
    log_manager.emit(
        "ERROR",
        "ERROR",
        f"Model probe failed for {result.provider} / {result.model}: {result.code} - {redact_secrets(result.message)}",
    )
    return JSONResponse(
        status_code=400,
        content={
            "detail": result.code,
            "provider": result.provider,
            "model": result.model,
            "message": redact_secrets(result.message),
            "refresh_suggested": result.refresh_suggested,
        },
    )


# Endpoints
@router.get("/config")
async def get_config() -> dict:
    """
    Get current configuration.

    Returns safe version with masked API keys.

    Returns:
        A dictionary containing the safe configuration.
    """
    config = config_store.load()
    _canonicalize_config_roles(config)
    return config_store.to_safe_dict()


@router.get("/public-access")
async def get_public_access(request: Request) -> dict[str, Any]:
    """Return current public-access guidance state for the Control Panel.

    Args:
        request: Incoming request used for runtime public-origin detection.

    Returns:
        A dictionary containing configured and effective public-access values.
    """
    config = config_store.load()
    return _serialize_public_access_state(request, config)


@router.post("/public-access")
async def update_public_access(
    request: Request,
    payload: PublicAccessUpdateRequest,
) -> dict[str, Any]:
    """Update stored public-access guidance settings.

    Args:
        request: Incoming request used for runtime public-origin detection.
        payload: Partial public-access update payload.

    Returns:
        A dictionary containing success status and effective public-access values.
    """
    config = config_store.load()
    current_public_access = config.public_access
    current_mode = str(current_public_access.mode or "none")
    if current_mode not in VALID_PUBLIC_ACCESS_MODES:
        current_mode = "none"

    mode = str(payload.mode if payload.mode is not None else current_mode).strip() or "none"
    if mode not in VALID_PUBLIC_ACCESS_MODES:
        raise HTTPException(status_code=400, detail="INVALID_PUBLIC_ACCESS_MODE")

    raw_public_base_url = (
        payload.public_base_url
        if payload.public_base_url is not None
        else current_public_access.public_base_url
    )
    raw_public_base_url = str(raw_public_base_url or "")
    public_base_url = normalize_public_base_url(raw_public_base_url)
    if raw_public_base_url.strip() and not public_base_url:
        raise HTTPException(status_code=400, detail="INVALID_PUBLIC_BASE_URL")

    config.public_access = PublicAccessConfig(
        mode=mode,
        public_base_url=public_base_url,
    )
    config_store.save(config)

    log_manager.emit(
        "INFO",
        "USER_ACTION",
        (f'Public access configuration saved: mode={mode}, public_base_url="{public_base_url}"'),
    )

    return {
        "success": True,
        **_serialize_public_access_state(request, config),
    }


@router.post("/api-keys/add")
async def add_api_key(request: AddApiKeyRequest) -> dict:
    """Add a new API key to a provider.

    Args:
        request: The add API key request containing provider and key details.

    Returns:
        A dictionary with success status and updated safe config.
    """
    provider_display = _get_provider_display_name(request.provider)

    if request.provider not in ["google", "anthropic", "openai"]:
        raise HTTPException(status_code=400, detail="INVALID_PROVIDER")

    config = config_store.load()
    provider_config = config.providers.get(request.provider, ProviderConfig())

    # Check for duplicate API key
    for existing_key in provider_config.api_keys:
        if existing_key.api_key == request.api_key:
            raise HTTPException(status_code=400, detail="API_KEY_DUPLICATE")

    # Create new key entry
    new_entry = ApiKeyEntry(name=request.name, api_key=request.api_key)
    provider_config.api_keys.append(new_entry)

    # Auto-select if it's the first key
    if len(provider_config.api_keys) == 1:
        provider_config.selected_key_id = new_entry.id

    config.providers[request.provider] = provider_config
    config_store.save(config)

    # Hot-reload providers to reflect new API key
    provider_manager.reload()

    log_manager.emit(
        "INFO", "USER_ACTION", f'API Key saved: {provider_display} (key name: "{request.name}")'
    )
    log_manager.emit(
        "INFO", "USER_ACTION", f"Config saved to: [file]{config_store.config_path}[/file]"
    )

    return {
        "success": True,
        "key_id": new_entry.id,
        "config": config_store.to_safe_dict(),
    }


@router.post("/api-keys/delete")
async def delete_api_key(request: DeleteApiKeyRequest) -> dict:
    """Delete an API key from a provider.

    Args:
        request: The delete request containing provider and key ID.

    Returns:
        A dictionary with success status and updated safe config.
    """
    provider_display = _get_provider_display_name(request.provider)

    if request.provider not in ["google", "anthropic", "openai"]:
        raise HTTPException(status_code=400, detail="INVALID_PROVIDER")

    config = config_store.load()
    provider_config = config.providers.get(request.provider)

    if not provider_config:
        raise HTTPException(status_code=404, detail="PROVIDER_NOT_FOUND")

    # Find key name before deletion for logging
    key_name = ""
    for k in provider_config.api_keys:
        if k.id == request.key_id:
            key_name = k.name
            break

    # Find and remove the key
    original_count = len(provider_config.api_keys)
    provider_config.api_keys = [k for k in provider_config.api_keys if k.id != request.key_id]

    if len(provider_config.api_keys) == original_count:
        raise HTTPException(status_code=404, detail="API_KEY_NOT_FOUND")

    # If selected key was deleted, select another or clear
    if provider_config.selected_key_id == request.key_id:
        if provider_config.api_keys:
            provider_config.selected_key_id = provider_config.api_keys[0].id
        else:
            provider_config.selected_key_id = None

    config.providers[request.provider] = provider_config
    config_store.save(config)

    # Hot-reload providers to reflect deleted API key
    provider_manager.reload()

    log_manager.emit(
        "WARN", "USER_ACTION", f'API Key deleted: {provider_display} (key name: "{key_name}")'
    )

    return {"success": True, "config": config_store.to_safe_dict()}


@router.post("/api-keys/select")
async def select_api_key(request: SelectApiKeyRequest) -> dict:
    """Select an API key as the active one for a provider.

    Args:
        request: The select request containing provider and key ID.

    Returns:
        A dictionary with success status, key name, and updated safe config.
    """
    provider_display = _get_provider_display_name(request.provider)

    if request.provider not in ["google", "anthropic", "openai"]:
        raise HTTPException(status_code=400, detail="INVALID_PROVIDER")

    config = config_store.load()
    provider_config = config.providers.get(request.provider)

    if not provider_config:
        raise HTTPException(status_code=404, detail="PROVIDER_NOT_FOUND")

    # Verify key exists
    key_exists = any(k.id == request.key_id for k in provider_config.api_keys)
    if not key_exists:
        raise HTTPException(status_code=404, detail="API_KEY_NOT_FOUND")

    # Get the key name for toast message and logging
    key_name = ""
    for k in provider_config.api_keys:
        if k.id == request.key_id:
            key_name = k.name
            break

    provider_config.selected_key_id = request.key_id
    config.providers[request.provider] = provider_config
    config_store.save(config)

    # Hot-reload providers to use newly selected API key
    provider_manager.reload()

    log_manager.emit(
        "INFO", "USER_ACTION", f'API Key selected: {provider_display} (key name: "{key_name}")'
    )

    return {
        "success": True,
        "key_name": key_name,
        "config": config_store.to_safe_dict(),
    }


@router.post("/config", response_model=None)
async def update_config(request: ConfigUpdateRequest) -> dict | JSONResponse:
    """
    Update configuration.

    Accepts partial updates - only specified fields are updated.

    Args:
        request: The configuration update request containing partial fields.

    Returns:
        A dictionary with success status and updated safe config, or JSONResponse on failure.
    """
    config = config_store.load()
    _canonicalize_config_roles(config)

    # Update roles
    if request.roles:
        all_roles = ["ternion_a", "ternion_b", "ternion_c", "arbiter", "writer", "reviewer"]
        enabled_providers = set(config_store.get_enabled_providers())

        # Determine required roles based on execution mode.
        # cursor_handoff: writer/reviewer are not required.
        effective_mode = request.execution_mode or config.execution_mode
        required_roles = ["ternion_a", "ternion_b", "ternion_c", "arbiter"]
        if effective_mode != "cursor_handoff":
            required_roles += ["writer", "reviewer"]

        # Validate only provided role updates (partial update supported)
        validated_roles: dict[str, tuple[RoleUpdateRequest, CatalogModel]] = {}
        next_roles = dict(config.roles)

        for role_name in all_roles:
            role_update = getattr(request.roles, role_name)
            if role_update is None:
                continue
            if not role_update.provider or not role_update.model:
                log_manager.emit(
                    "ERROR",
                    "USER_ACTION",
                    f"Role update failed: Incomplete configuration for {role_name}",
                )
                raise HTTPException(status_code=400, detail=f"ROLES_INCOMPLETE:{role_name}")
            if role_update.provider not in enabled_providers:
                log_manager.emit(
                    "ERROR",
                    "USER_ACTION",
                    f"Role update failed: Provider '{role_update.provider}' is not enabled",
                )
                raise HTTPException(status_code=400, detail="PROVIDER_NOT_ENABLED")
            catalog_model = await _get_catalog_model_for_provider(
                role_update.provider,
                role_update.model,
            )
            validated_roles[role_name] = (role_update, catalog_model)
            next_roles[role_name] = RoleConfig(
                provider=role_update.provider,
                model=catalog_model.id,
            )

        # Enforce that all required roles are fully configured after applying updates
        missing_roles: list[str] = []
        for role_name in required_roles:
            role_cfg = next_roles.get(role_name)
            if not role_cfg or not role_cfg.provider or not role_cfg.model:
                missing_roles.append(role_name)
                continue
            if role_cfg.provider not in enabled_providers:
                log_manager.emit(
                    "ERROR",
                    "USER_ACTION",
                    f"Role validation failed: Provider '{role_cfg.provider}' is not enabled",
                )
                raise HTTPException(status_code=400, detail="PROVIDER_NOT_ENABLED")
            await _get_catalog_model_for_provider(role_cfg.provider, role_cfg.model)

        if missing_roles:
            missing_roles_str = ",".join(missing_roles)
            log_manager.emit(
                "ERROR",
                "USER_ACTION",
                f"Role validation failed: Missing configuration for roles: {missing_roles_str}",
            )
            raise HTTPException(
                status_code=400,
                detail=f"ROLES_INCOMPLETE:{missing_roles_str}",
            )

        unique_pairs: set[tuple[str, str]] = set()
        for role_name in required_roles:
            role_cfg = next_roles[role_name]
            unique_pairs.add((role_cfg.provider, role_cfg.model))

        for provider, model in sorted(unique_pairs):
            api_key = config_store.get_provider_api_key(provider)
            if not api_key:
                log_manager.emit(
                    "ERROR",
                    "USER_ACTION",
                    f"Model probe skipped: Provider '{provider}' has no valid API key",
                )
                raise HTTPException(status_code=400, detail="PROVIDER_NOT_ENABLED")

            probe_result = await model_availability_probe_service.probe_model(
                provider=provider,
                model=model,
                api_key=api_key,
            )
            if not probe_result.ok:
                return _build_model_probe_failure_response(probe_result)

        # Commit updates only after validation succeeds
        config.roles = next_roles

        for role_name, (role_update, catalog_model) in validated_roles.items():
            provider_display = _get_provider_display_name(role_update.provider)
            model_display = await _get_model_display_name(role_update.provider, catalog_model.id)
            if role_name.startswith("ternion_"):
                role_display = f"Ternion {role_name[-1].upper()}"
            else:
                role_display = role_name.capitalize()
            log_manager.emit(
                "INFO",
                "USER_ACTION",
                f"{role_display} model set to: {provider_display} / {model_display}",
            )

    # Update budget
    if request.budget:
        budget_changed = False
        if request.budget.monthly_limit_usd is not None:
            if request.budget.monthly_limit_usd <= 0:
                raise HTTPException(status_code=400, detail="INVALID_BUDGET_LIMIT")
            config.budget.monthly_limit_usd = request.budget.monthly_limit_usd
            budget_changed = True
        if request.budget.alert_threshold is not None:
            if not 0 < request.budget.alert_threshold <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="INVALID_BUDGET_THRESHOLD",
                )
            config.budget.alert_threshold = request.budget.alert_threshold
            budget_changed = True

        if budget_changed:
            threshold_pct = int(config.budget.alert_threshold * 100)
            log_manager.emit(
                "INFO",
                "USER_ACTION",
                f"Budget updated: Limit=${config.budget.monthly_limit_usd}, Alert={threshold_pct}%",
            )

            # Sync active budget manager settings
            budget_manager.settings.monthly_limit_usd = config.budget.monthly_limit_usd
            budget_manager.settings.alert_threshold = config.budget.alert_threshold

    # Update execution mode
    if request.execution_mode is not None:
        if request.execution_mode not in ("cursor_handoff", "ternion_full"):
            raise HTTPException(status_code=400, detail="INVALID_EXECUTION_MODE")
        old_mode = config.execution_mode
        config.execution_mode = request.execution_mode
        if old_mode != request.execution_mode:
            mode_display = (
                "Ternion + Cursor"
                if request.execution_mode == "cursor_handoff"
                else "All in Ternion"
            )
            log_manager.emit(
                "INFO",
                "USER_ACTION",
                f"Execution mode saved: {mode_display}",
            )

    if request.model_catalog_refresh is not None:
        refresh_settings = config.model_catalog_refresh
        if request.model_catalog_refresh.enabled is not None:
            refresh_settings.enabled = request.model_catalog_refresh.enabled
        if request.model_catalog_refresh.mode is not None:
            if request.model_catalog_refresh.mode not in VALID_REFRESH_MODES:
                raise HTTPException(status_code=400, detail="INVALID_MODEL_CATALOG_REFRESH_MODE")
            refresh_settings.mode = request.model_catalog_refresh.mode
        if request.model_catalog_refresh.time_of_day is not None:
            try:
                refresh_settings.time_of_day = normalize_time_of_day(
                    request.model_catalog_refresh.time_of_day
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="INVALID_MODEL_CATALOG_REFRESH_TIME",
                ) from exc
        if request.model_catalog_refresh.interval_value is not None:
            if request.model_catalog_refresh.interval_value <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="INVALID_MODEL_CATALOG_REFRESH_INTERVAL",
                )
            refresh_settings.interval_value = request.model_catalog_refresh.interval_value

        if refresh_settings.enabled:
            refresh_settings.next_refresh_at = compute_next_refresh_at(
                refresh_settings,
                now=datetime.now(UTC),
            )
        else:
            refresh_settings.next_refresh_at = ""

        log_manager.emit(
            "INFO",
            "USER_ACTION",
            (
                "Model catalog auto-refresh updated: "
                f"enabled={refresh_settings.enabled}, "
                f"mode={refresh_settings.mode}, "
                f"time={refresh_settings.time_of_day}, "
                f"interval={refresh_settings.interval_value}"
            ),
        )

    config_store.save(config)
    logger.info("config_updated")

    return {"success": True, "config": config_store.to_safe_dict()}


@router.post("/roles/selection")
async def log_role_selection(request: RoleSelectionLogRequest) -> dict:
    """
    Log a role model selection without persisting configuration.

    This is used by the Web UI to record user choices while indicating
    the configuration has not been saved yet.

    Args:
        request: The selection request containing role and model info.

    Returns:
        A dictionary indicating the selection was successfully logged.
    """
    enabled = set(config_store.get_enabled_providers())
    if request.provider not in enabled:
        log_manager.emit(
            "ERROR",
            "USER_ACTION",
            f"Role model selection failed: Provider '{request.provider}' is not enabled",
        )
        raise HTTPException(status_code=400, detail="PROVIDER_NOT_ENABLED")

    await _get_catalog_model_for_provider(request.provider, request.model)

    provider_display = _get_provider_display_name(request.provider)
    model_display = await _get_model_display_name(request.provider, request.model)
    if request.role.startswith("ternion_"):
        role_display = f"Ternion {request.role[-1].upper()}"
    else:
        role_display = request.role.capitalize()

    log_manager.emit(
        "INFO",
        "USER_ACTION",
        f"{role_display} model selected (not saved): {provider_display} / {model_display}",
    )

    return {
        "success": True,
        "message": "ROLE_MODEL_SELECTION_LOGGED",
        "pending": True,
    }


@router.post("/execution-mode/selection")
async def log_execution_mode_selection(request: ExecutionModeSelectionLogRequest) -> dict:
    """
    Log an execution mode selection without persisting configuration.

    This is used by the Web UI to record user choice while indicating
    the configuration has not been saved yet.

    Args:
        request: The execution mode selection request.

    Returns:
        A dictionary indicating the selection was successfully logged.
    """
    if request.execution_mode not in ("cursor_handoff", "ternion_full"):
        raise HTTPException(status_code=400, detail="INVALID_EXECUTION_MODE")

    mode_display = (
        "Ternion + Cursor" if request.execution_mode == "cursor_handoff" else "All in Ternion"
    )
    log_manager.emit(
        "INFO",
        "USER_ACTION",
        f"Execution mode selected: {mode_display}, not saved yet",
    )

    return {
        "success": True,
        "message": "EXECUTION_MODE_SELECTION_LOGGED",
        "pending": True,
    }


@router.get("/usage")
async def get_usage(month: str | None = None) -> dict:
    """Get detailed usage statistics for charts and dashboard.

    Args:
        month: The optional month filter in "YYYY-MM" format.

    Returns:
        A dictionary of usage statistics.
    """
    return budget_manager.get_detailed_usage(month=month)


@router.post("/test-provider")
async def test_provider(request: TestProviderRequest) -> TestProviderResponse:
    """
    Test a provider connection with the given API key.

    Uses lightweight models with minimal tokens for cost-effective connectivity testing:
    - Gemini: gemini-2.0-flash-lite (list models API - no LLM call)
    - Claude: claude-haiku-4-5-20251001 (1 token max)
    - GPT: gpt-4.1-nano (list models API - no LLM call)

    Args:
        request: The test request with provider and API key.

    Returns:
        A response indicating success or failure of the provider test.
    """
    provider_display = _get_provider_display_name(request.provider)

    if request.provider not in ["google", "anthropic", "openai"]:
        return TestProviderResponse(
            success=False, message="Invalid provider specified", code="INVALID_PROVIDER"
        )

    log_manager.emit("INFO", "USER_ACTION", f"Testing API Key for {provider_display}...")

    try:
        if request.provider == "google":
            from google import genai

            # Use list models API - no LLM call, most cost-effective.
            # Run in executor to avoid blocking the async event loop.
            google_client = genai.Client(api_key=request.api_key)
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: list(google_client.models.list())
            )
            log_manager.emit("INFO", "USER_ACTION", f"API Key test successful: {provider_display}")
            return TestProviderResponse(
                success=True, message="Google API connected", code="SUCCESS"
            )

        elif request.provider == "anthropic":
            import anthropic

            # Use async client to avoid blocking the event loop.
            async_client = anthropic.AsyncAnthropic(api_key=request.api_key)
            await async_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            log_manager.emit("INFO", "USER_ACTION", f"API Key test successful: {provider_display}")
            return TestProviderResponse(
                success=True, message="Anthropic API connected", code="SUCCESS"
            )

        elif request.provider == "openai":
            import openai

            # Use async client to avoid blocking the event loop.
            async_openai_client = openai.AsyncOpenAI(api_key=request.api_key)
            await async_openai_client.models.list()
            log_manager.emit("INFO", "USER_ACTION", f"API Key test successful: {provider_display}")
            return TestProviderResponse(
                success=True, message="OpenAI API connected", code="SUCCESS"
            )

    except Exception as e:
        error_msg = str(e)
        # Redact any secrets that might be in error messages
        safe_error_msg = redact_secrets(error_msg)
        error_lower = error_msg.lower()
        auth_keywords = [
            "invalid",
            "unauthorized",
            "not valid",
            "api_key_invalid",
            "authentication",
            "incorrect",
        ]
        if any(kw in error_lower for kw in auth_keywords):
            log_manager.emit(
                "ERROR",
                "USER_ACTION",
                f"API Key test failed: {provider_display} - {safe_error_msg[:2000]}",
            )
            return TestProviderResponse(
                success=False, message=safe_error_msg[:100], code="AUTH_ERROR"
            )
        log_manager.emit(
            "ERROR",
            "USER_ACTION",
            f"API Key test failed: {provider_display} - {safe_error_msg[:2000]}",
        )
        return TestProviderResponse(
            success=False, message=safe_error_msg[:100], code="CONNECTION_ERROR"
        )

    return TestProviderResponse(success=False, message="Unknown error", code="UNKNOWN_ERROR")


@router.get("/status")
async def get_status() -> dict:
    """Get server status.

    Returns:
        A dictionary representing server operational status.
    """
    enabled = config_store.get_enabled_providers()
    return {
        "server_status": "running",
        "active_providers": enabled,
        "provider_count": len(enabled),
    }


class PreferencesUpdateRequest(BaseModel):
    """Request to update user preferences."""

    theme: str | None = None  # "light", "dark", "system"
    language: str | None = None  # "auto", "en", "zh", "es", "fr", "de", "ja", "ko"
    browser_language: str | None = None  # Detected browser language (used when language="auto")
    hide_usage_disclaimer: bool | None = None  # Hide usage disclaimer warning
    show_phase_indicators: bool | None = None  # Show phase indicators in streaming output


@router.put("/preferences")
async def update_preferences(request: PreferencesUpdateRequest) -> dict:
    """Update user preferences (theme, language, hide_usage_disclaimer).

    Args:
        request: The update request containing updated preferences.

    Returns:
        A dictionary containing the success status and the updated preferences.
    """
    config = config_store.load()

    if request.theme is not None:
        if request.theme not in ("light", "dark", "system"):
            raise HTTPException(status_code=400, detail="INVALID_THEME")
        old_theme = config.theme
        config.theme = request.theme
        if old_theme != request.theme:
            log_manager.emit(
                "INFO",
                "USER_ACTION",
                f"Theme changed: {old_theme} → {request.theme}",
            )

    if request.language is not None:
        if request.language not in ("auto", "en", "zh", "es", "fr", "de", "ja", "ko"):
            raise HTTPException(status_code=400, detail="INVALID_LANGUAGE")
        old_language = config.language
        config.language = request.language
        if old_language != request.language:
            log_manager.emit(
                "INFO",
                "USER_ACTION",
                f"Language changed: {old_language} → {request.language}",
            )

    if request.hide_usage_disclaimer is not None:
        config.hide_usage_disclaimer = request.hide_usage_disclaimer

    if request.show_phase_indicators is not None:
        config.show_phase_indicators = request.show_phase_indicators

    # Store browser-detected language (used when language="auto")
    if request.browser_language is not None and request.browser_language in (
        "en",
        "zh",
        "es",
        "fr",
        "de",
        "ja",
        "ko",
    ):
        config.browser_language = request.browser_language
        logger.debug("browser_language_updated", browser_language=request.browser_language)

    config_store.save(config)
    logger.info("preferences_updated", theme=config.theme, language=config.language)

    return {
        "success": True,
        "preferences": {
            "theme": config.theme,
            "language": config.language,
            "browser_language": config.browser_language,
            "hide_usage_disclaimer": config.hide_usage_disclaimer,
            "show_phase_indicators": config.show_phase_indicators,
        },
    }


@router.get("/models")
async def get_available_models() -> dict:
    """Get available models for each provider.

    Returns:
        A dictionary payload containing available models and enabled providers.
    """
    enabled = config_store.get_enabled_providers()
    payload = await model_catalog_service.get_models_payload(allow_remote_fetch=False)
    payload["enabled_providers"] = enabled
    return payload


@router.post("/models/refresh")
async def refresh_models() -> dict:
    """Force-refresh the model catalog for initialization or manual updates.

    Returns:
        A dictionary payload containing the latest catalog refresh data.

    Raises:
        HTTPException: If the refresh fails or the resulting catalog is empty.
    """
    enabled = config_store.get_enabled_providers()

    try:
        payload = await refresh_catalog_and_update_schedule("manual")
    except Exception as exc:
        log_manager.emit("ERROR", "ERROR", f"Model catalog refresh failed: {str(exc)}")
        raise HTTPException(status_code=503, detail="MODEL_CATALOG_REFRESH_FAILED") from exc

    if payload["requires_initialization"]:
        logger.warning(
            "model_catalog_refresh_empty",
            model_count=payload.get("model_count", 0),
            last_updated_at=payload.get("last_updated_at", ""),
        )
        log_manager.emit(
            "ERROR",
            "ERROR",
            "Model catalog refresh resulted in empty catalog or initialization required",
        )
        raise HTTPException(status_code=503, detail="MODEL_CATALOG_REFRESH_FAILED")

    payload["success"] = not payload.get("catalog_anomaly_detected", False)
    payload["enabled_providers"] = enabled
    return payload


@router.get("/models/anomaly-report", response_class=PlainTextResponse)
async def get_model_anomaly_report() -> PlainTextResponse:
    """Return the latest model catalog anomaly report as Markdown.

    Returns:
        A plain text response containing the report in Markdown.
    """
    report_markdown = model_catalog_service.get_anomaly_report_markdown()
    if report_markdown is None:
        log_manager.emit("WARN", "ERROR", "Model catalog anomaly report requested but not found")
        raise HTTPException(status_code=404, detail="MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND")
    return PlainTextResponse(report_markdown, media_type="text/markdown")


@router.get("/ports")
async def get_ports() -> dict:
    """Get current port configuration.

    Returns:
        A dictionary with the backend and web port configuration.
    """
    config = config_store.load()
    return {
        "backend": config.ports.backend,
        "web": config.ports.web,
    }


@router.post("/ports")
async def update_ports(request: PortsUpdateRequest) -> dict:
    """
    Update port configuration.

    Port changes are saved to config but require manual server restart to take effect.

    Args:
        request: The port update request containing backend and/or web ports.

    Returns:
        A dictionary indicating the updated configuration and that a restart is required.
    """
    config = config_store.load()

    # Validate port range (1024-65535)
    def validate_port(port: int, name: str) -> None:
        if port < 1024 or port > 65535:
            raise HTTPException(status_code=400, detail=f"INVALID_PORT_{name.upper()}")

    if request.backend is not None:
        validate_port(request.backend, "backend")
        config.ports.backend = request.backend

    if request.web is not None:
        validate_port(request.web, "web")
        config.ports.web = request.web

    config_store.save(config)

    log_manager.emit(
        "INFO",
        "USER_ACTION",
        f"Port configuration saved: backend={config.ports.backend}, web={config.ports.web}",
    )

    return {
        "success": True,
        "ports": {
            "backend": config.ports.backend,
            "web": config.ports.web,
        },
        "restart_required": True,
        "message": "PORTS_SAVED_RESTART_REQUIRED",
    }


class DownloadLogsResponse(BaseModel):
    """Response from log download."""

    success: bool
    file_path: str
    log_count: int


@router.post("/logs/download")
async def download_logs() -> DownloadLogsResponse:
    """
    Download current session logs to ~/.ternion/log.json.

    Exports all logs from the current session to a JSON file for offline analysis.

    Returns:
        A response indicating success, the path to the saved file, and the number of logs.
    """
    import json as json_lib
    from datetime import datetime
    from pathlib import Path

    logs = log_manager.get_history()
    file_path = Path.home() / ".ternion" / "log.json"

    # Ensure directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Build export data
    export_data = {
        "session_start": logs[0]["timestamp"] if logs else datetime.now(UTC).isoformat(),
        "exported_at": datetime.now(UTC).isoformat(),
        "log_count": len(logs),
        "logs": logs,
    }

    # Write to file
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json_lib.dump(export_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"WRITE_ERROR: {str(e)}") from e

    # Emit log entry about the download
    log_manager.emit(
        "INFO",
        "USER_ACTION",
        f"Logs downloaded: {len(logs)} entries saved to [file]{file_path}[/file]",
    )

    return DownloadLogsResponse(
        success=True,
        file_path=str(file_path),
        log_count=len(logs),
    )


class RevealFileRequest(BaseModel):
    """Request to reveal a file in the system file manager."""

    path: str


@router.post("/reveal-file")
async def reveal_file(request: RevealFileRequest) -> dict:
    """
    Reveal a file in the system file manager (Finder on macOS, Explorer on Windows).

    Security: Path traversal prevention - only paths within ~/.ternion/ are
    allowed to avoid arbitrary file system access via the web panel.

    Args:
        request: The request containing the file path to reveal.

    Returns:
        A dictionary indicating success.
    """
    import os
    import platform
    import subprocess
    from pathlib import Path

    # Expand user path and resolve to absolute path
    path = os.path.expanduser(request.path)
    resolved_path = Path(path).resolve()

    # Whitelist: only allow paths within ~/.ternion/
    allowed_base = Path.home() / ".ternion"
    try:
        resolved_path.relative_to(allowed_base)
    except ValueError:
        # Path is not within allowed directory
        raise HTTPException(
            status_code=403,
            detail="PATH_NOT_ALLOWED",
        ) from None

    # Use resolved_path for all subsequent operations to prevent symlink traversal.
    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")

    resolved_str = str(resolved_path)
    try:
        system = platform.system()
        if system == "Darwin":  # macOS
            subprocess.run(["open", "-R", resolved_str], check=True)
        elif system == "Windows":
            subprocess.run(["explorer", "/select,", resolved_str], check=True)
        else:  # Linux
            # Try xdg-open on the parent directory
            parent = str(resolved_path.parent)
            subprocess.run(["xdg-open", parent], check=True)

        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Log streaming for observability


async def _log_event_generator(queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    """Generate SSE events from log queue.

    Args:
        queue: The asyncio queue from which to read logs.

    Yields:
        Server-Sent Event formatted string containing log entries.
    """
    import json

    try:
        # Send initial history
        for entry in log_manager.get_history():
            yield f"data: {json.dumps(entry)}\n\n"

        # Stream new logs
        while True:
            try:
                entry = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(entry)}\n\n"
            except TimeoutError:
                # Send keepalive
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass


@router.get("/logs/stream")
async def stream_logs() -> StreamingResponse:
    """SSE endpoint for real-time log streaming.

    Returns:
        A streaming response that continuously sends log data as Server-Sent Events.
    """
    queue = log_manager.subscribe()

    async def cleanup_generator() -> AsyncGenerator[str, None]:
        try:
            async for event in _log_event_generator(queue):
                yield event
        finally:
            log_manager.unsubscribe(queue)

    return StreamingResponse(
        cleanup_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

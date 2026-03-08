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

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from ternion.core.budget import budget_manager
from ternion.core.config_store import (
    ApiKeyEntry,
    ProviderConfig,
    RoleConfig,
    config_store,
)
from ternion.core.model_catalog import CatalogModel, model_catalog_service
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


# Display name mapping for providers
PROVIDER_DISPLAY_NAMES = {
    "google": "Google Gemini",
    "anthropic": "Anthropic Claude",
    "openai": "OpenAI GPT",
}


def _get_provider_display_name(provider: str) -> str:
    """Get human-readable display name for a provider."""
    return PROVIDER_DISPLAY_NAMES.get(provider, provider.title())


async def _get_model_display_name(provider: str, model_id: str) -> str:
    """Get human-readable display name for a model."""
    model = await model_catalog_service.get_model(model_id)
    if model is not None and model.provider == provider:
        return model.name
    return model_id


async def _get_catalog_model_for_provider(provider: str, model_id: str) -> CatalogModel:
    """Get a catalog model and enforce provider/model consistency.

    Raises:
        HTTPException: If the model is missing from the catalog or belongs to a
            different provider.
    """
    model = await model_catalog_service.get_model(model_id)
    if model is None or model.provider != provider:
        raise HTTPException(status_code=400, detail="MODEL_NOT_AVAILABLE")
    return model


# Endpoints
@router.get("/config")
async def get_config() -> dict:
    """
    Get current configuration.

    Returns safe version with masked API keys.
    """
    return config_store.to_safe_dict()


@router.post("/api-keys/add")
async def add_api_key(request: AddApiKeyRequest) -> dict:
    """Add a new API key to a provider."""
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
    """Delete an API key from a provider."""
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
    """Select an API key as the active one for a provider."""
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


@router.post("/config")
async def update_config(request: ConfigUpdateRequest) -> dict:
    """
    Update configuration.

    Accepts partial updates - only specified fields are updated.
    """
    config = config_store.load()

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
        validated_roles: dict[str, RoleUpdateRequest] = {}
        next_roles = dict(config.roles)

        for role_name in all_roles:
            role_update = getattr(request.roles, role_name)
            if role_update is None:
                continue
            if not role_update.provider or not role_update.model:
                raise HTTPException(status_code=400, detail=f"ROLES_INCOMPLETE:{role_name}")
            if role_update.provider not in enabled_providers:
                raise HTTPException(status_code=400, detail="PROVIDER_NOT_ENABLED")
            await _get_catalog_model_for_provider(role_update.provider, role_update.model)
            validated_roles[role_name] = role_update
            next_roles[role_name] = RoleConfig(
                provider=role_update.provider,
                model=role_update.model,
            )

        # Enforce that all required roles are fully configured after applying updates
        missing_roles: list[str] = []
        for role_name in required_roles:
            role_cfg = next_roles.get(role_name)
            if not role_cfg or not role_cfg.provider or not role_cfg.model:
                missing_roles.append(role_name)
                continue
            if role_cfg.provider not in enabled_providers:
                raise HTTPException(status_code=400, detail="PROVIDER_NOT_ENABLED")
            await _get_catalog_model_for_provider(role_cfg.provider, role_cfg.model)

        if missing_roles:
            raise HTTPException(
                status_code=400,
                detail=f"ROLES_INCOMPLETE:{','.join(missing_roles)}",
            )

        # Commit updates only after validation succeeds
        config.roles = next_roles

        for role_name, role_update in validated_roles.items():
            provider_display = _get_provider_display_name(role_update.provider)
            model_display = await _get_model_display_name(role_update.provider, role_update.model)
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
    """
    enabled = set(config_store.get_enabled_providers())
    if request.provider not in enabled:
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
    """Get detailed usage statistics for charts and dashboard."""
    return budget_manager.get_detailed_usage(month=month)


@router.post("/test-provider")
async def test_provider(request: TestProviderRequest) -> TestProviderResponse:
    """
    Test a provider connection with the given API key.

    Uses lightweight models with minimal tokens for cost-effective connectivity testing:
    - Gemini: gemini-2.0-flash-lite (list models API - no LLM call)
    - Claude: claude-haiku-4-5-20251001 (1 token max)
    - GPT: gpt-4.1-nano (list models API - no LLM call)
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
        # Redact any secrets that might be in error messages (CR-027)
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
    """Get server status."""
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
    """Update user preferences (theme, language, hide_usage_disclaimer)."""
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
    """Get available models for each provider."""
    enabled = config_store.get_enabled_providers()
    payload = await model_catalog_service.get_models_payload()
    payload["enabled_providers"] = enabled
    return payload


@router.post("/models/refresh")
async def refresh_models() -> dict:
    """Force-refresh the model catalog for initialization or manual updates.

    Raises:
        HTTPException: If the refresh fails or the resulting catalog is empty.
    """
    enabled = config_store.get_enabled_providers()

    try:
        payload = await refresh_catalog_and_update_schedule("manual")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MODEL_CATALOG_REFRESH_FAILED") from exc

    if payload["requires_initialization"]:
        logger.warning(
            "model_catalog_refresh_empty",
            model_count=payload.get("model_count", 0),
            last_updated_at=payload.get("last_updated_at", ""),
        )
        raise HTTPException(status_code=503, detail="MODEL_CATALOG_REFRESH_FAILED")

    payload["success"] = not payload.get("catalog_anomaly_detected", False)
    payload["enabled_providers"] = enabled
    return payload


@router.get("/models/anomaly-report", response_class=PlainTextResponse)
async def get_model_anomaly_report() -> PlainTextResponse:
    """Return the latest model catalog anomaly report as Markdown."""
    report_markdown = model_catalog_service.get_anomaly_report_markdown()
    if report_markdown is None:
        raise HTTPException(status_code=404, detail="MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND")
    return PlainTextResponse(report_markdown, media_type="text/markdown")


@router.get("/ports")
async def get_ports() -> dict:
    """Get current port configuration."""
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

    Security: Path traversal prevention — only paths within ~/.ternion/ are
    allowed to avoid arbitrary file system access via the web panel.
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
    """Generate SSE events from log queue."""
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
    """SSE endpoint for real-time log streaming."""
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

"""
Control Panel API routes.

Provides REST API endpoints for the Web Control Panel to manage:
- Provider configuration (API keys)
- Role-model assignments
- Budget settings
- Usage statistics
"""

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ternion.core.config_store import (
    UserConfig,
    ProviderConfig,
    ApiKeyEntry,
    RoleConfig,
    BudgetConfig,
    config_store,
    AVAILABLE_MODELS,
)
from ternion.core.budget import budget_manager

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api", tags=["control-panel"])


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

    arbiter: RoleUpdateRequest | None = None
    writer: RoleUpdateRequest | None = None
    reviewer: RoleUpdateRequest | None = None


class BudgetUpdateRequest(BaseModel):
    """Request to update budget settings."""

    monthly_limit_usd: float | None = None
    alert_threshold: float | None = None


class ConfigUpdateRequest(BaseModel):
    """Request to update configuration."""

    roles: RolesUpdateRequest | None = None
    budget: BudgetUpdateRequest | None = None


class TestProviderRequest(BaseModel):
    """Request to test a provider connection."""

    provider: str
    api_key: str


class TestProviderResponse(BaseModel):
    """Response from provider test."""

    success: bool
    message: str


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
    if request.provider not in ["google", "anthropic", "openai"]:
        raise HTTPException(status_code=400, detail="INVALID_PROVIDER")

    config = config_store.load()
    provider_config = config.providers.get(request.provider, ProviderConfig())

    # Create new key entry
    new_entry = ApiKeyEntry(name=request.name, api_key=request.api_key)
    provider_config.api_keys.append(new_entry)

    # Auto-select if it's the first key
    if len(provider_config.api_keys) == 1:
        provider_config.selected_key_id = new_entry.id

    config.providers[request.provider] = provider_config
    config_store.save(config)

    return {
        "success": True,
        "key_id": new_entry.id,
        "config": config_store.to_safe_dict(),
    }


@router.post("/api-keys/delete")
async def delete_api_key(request: DeleteApiKeyRequest) -> dict:
    """Delete an API key from a provider."""
    if request.provider not in ["google", "anthropic", "openai"]:
        raise HTTPException(status_code=400, detail="INVALID_PROVIDER")

    config = config_store.load()
    provider_config = config.providers.get(request.provider)

    if not provider_config:
        raise HTTPException(status_code=404, detail="PROVIDER_NOT_FOUND")

    # Find and remove the key
    original_count = len(provider_config.api_keys)
    provider_config.api_keys = [
        k for k in provider_config.api_keys if k.id != request.key_id
    ]

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

    return {"success": True, "config": config_store.to_safe_dict()}


@router.post("/api-keys/select")
async def select_api_key(request: SelectApiKeyRequest) -> dict:
    """Select an API key as the active one for a provider."""
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

    # Get the key name for toast message
    key_name = ""
    for k in provider_config.api_keys:
        if k.id == request.key_id:
            key_name = k.name
            break

    provider_config.selected_key_id = request.key_id
    config.providers[request.provider] = provider_config
    config_store.save(config)

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
        for role_name in ["arbiter", "writer", "reviewer"]:
            role_update = getattr(request.roles, role_name)
            if role_update:
                # Validate provider is enabled
                if role_update.provider not in config_store.get_enabled_providers():
                    raise HTTPException(
                        status_code=400,
                        detail="PROVIDER_NOT_ENABLED",
                    )

                # Validate model is available
                available = [m["id"] for m in AVAILABLE_MODELS.get(role_update.provider, [])]
                if role_update.model not in available:
                    raise HTTPException(
                        status_code=400,
                        detail="MODEL_NOT_AVAILABLE",
                    )

                config.roles[role_name] = RoleConfig(
                    provider=role_update.provider, model=role_update.model
                )

    # Update budget
    if request.budget:
        if request.budget.monthly_limit_usd is not None:
            if request.budget.monthly_limit_usd <= 0:
                raise HTTPException(
                    status_code=400, detail="INVALID_BUDGET_LIMIT"
                )
            config.budget.monthly_limit_usd = request.budget.monthly_limit_usd
        if request.budget.alert_threshold is not None:
            if not 0 < request.budget.alert_threshold <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="INVALID_BUDGET_THRESHOLD",
                )
            config.budget.alert_threshold = request.budget.alert_threshold

    config_store.save(config)
    logger.info("config_updated")

    return {"success": True, "config": config_store.to_safe_dict()}


@router.get("/usage")
async def get_usage() -> dict:
    """Get current usage statistics."""
    return budget_manager.get_usage_summary()


@router.post("/test-provider")
async def test_provider(request: TestProviderRequest) -> TestProviderResponse:
    """
    Test a provider connection with the given API key.

    Makes a minimal API call to verify the key works.
    """
    if request.provider not in ["google", "anthropic", "openai"]:
        return TestProviderResponse(
            success=False, message="Invalid provider specified", code="INVALID_PROVIDER"
        )

    try:
        if request.provider == "google":
            import google.generativeai as genai

            genai.configure(api_key=request.api_key)
            # List models to verify key
            list(genai.list_models())
            return TestProviderResponse(
                success=True, message="Google API connected", code="SUCCESS"
            )

        elif request.provider == "anthropic":
            import anthropic

            client = anthropic.Anthropic(api_key=request.api_key)
            # Make a minimal request
            client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1,
                messages=[{"role": "user", "content": "Hi"}],
            )
            return TestProviderResponse(
                success=True, message="Anthropic API connected", code="SUCCESS"
            )

        elif request.provider == "openai":
            import openai

            client = openai.OpenAI(api_key=request.api_key)
            # List models to verify key
            client.models.list()
            return TestProviderResponse(
                success=True, message="OpenAI API connected", code="SUCCESS"
            )

    except Exception as e:
        error_msg = str(e)
        error_lower = error_msg.lower()
        # Detect auth errors: various API providers use different error messages
        auth_keywords = ["invalid", "unauthorized", "not valid", "api_key_invalid", "authentication", "incorrect"]
        if any(kw in error_lower for kw in auth_keywords):
            return TestProviderResponse(
                success=False, message=error_msg[:100], code="AUTH_ERROR"
            )
        return TestProviderResponse(
            success=False, message=error_msg[:100], code="CONNECTION_ERROR"
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


@router.get("/models")
async def get_available_models() -> dict:
    """Get available models for each provider."""
    enabled = config_store.get_enabled_providers()
    return {
        "models": {
            provider: models
            for provider, models in AVAILABLE_MODELS.items()
        },
        "enabled_providers": enabled,
    }

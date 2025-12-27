"""
Configuration storage for the Web Control Panel.

Provides persistent storage for user configuration including:
- Provider API keys (multiple per provider)
- Role-model assignments
- Budget settings
"""

import json
import structlog
from pathlib import Path
from typing import Any
from datetime import datetime
import uuid

from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

# Default configuration path
DEFAULT_CONFIG_PATH = Path.home() / ".ternion" / "config.json"

# Available models per provider
AVAILABLE_MODELS = {
    "google": [
        {"id": "gemini-3-pro-preview", "name": "Gemini 3.0 Pro"},
        {"id": "gemini-3-flash-preview", "name": "Gemini 3.0 Flash"},
        {"id": "gemini-flash-lite-latest", "name": "Gemini 2.5 Flash Lite"},
    ],
    "anthropic": [
        {"id": "claude-opus-4-5-20251101", "name": "Claude 4.5 Opus"},
        {"id": "claude-sonnet-4-5-20250929", "name": "Claude 4.5 Sonnet"},
        {"id": "claude-opus-4-1-20250805", "name": "Claude 4.1 Opus"},
    ],
    "openai": [
        {"id": "gpt-5.2-pro-2025-12-11", "name": "GPT 5.2 Pro"},
        {"id": "gpt-5.2-2025-12-11", "name": "GPT 5.2"},
        {"id": "gpt-5.1-codex-max", "name": "GPT 5.1 Codex Max"},
        {"id": "gpt-5.1-codex", "name": "GPT 5.1 Codex"},
    ],
}


class ApiKeyEntry(BaseModel):
    """A single API key entry with name."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    api_key: str = ""


class ProviderConfig(BaseModel):
    """Configuration for a single provider with multiple API keys."""

    api_keys: list[ApiKeyEntry] = Field(default_factory=list)
    selected_key_id: str | None = None  # ID of currently selected key

    @property
    def enabled(self) -> bool:
        """Provider is enabled if it has at least one key and one is selected."""
        return bool(self.api_keys and self.selected_key_id)

    @property
    def active_key(self) -> str | None:
        """Get the currently selected API key."""
        if not self.selected_key_id:
            return None
        for entry in self.api_keys:
            if entry.id == self.selected_key_id:
                return entry.api_key
        return None


class RoleConfig(BaseModel):
    """Configuration for a discussion role."""

    provider: str = ""
    model: str = ""


class BudgetConfig(BaseModel):
    """Budget configuration."""

    monthly_limit_usd: float = 50.0
    alert_threshold: float = 0.9  # 90%


class PortsConfig(BaseModel):
    """Server port configuration."""

    backend: int = 8000  # Ternion API server port
    web: int = 7990      # Web control panel port


class UserConfig(BaseModel):
    """Complete user configuration."""

    providers: dict[str, ProviderConfig] = Field(
        default_factory=lambda: {
            "google": ProviderConfig(),
            "anthropic": ProviderConfig(),
            "openai": ProviderConfig(),
        }
    )
    roles: dict[str, RoleConfig] = Field(
        default_factory=lambda: {
            "arbiter": RoleConfig(provider="google", model="gemini-flash-lite-latest"),
            "writer": RoleConfig(provider="anthropic", model="claude-sonnet-4-5-20250929"),
            "reviewer": RoleConfig(provider="openai", model="gpt-5.1-codex"),
        }
    )
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    ports: PortsConfig = Field(default_factory=PortsConfig)
    theme: str = "system"  # "light", "dark", "system"
    language: str = "auto"  # "auto", "en", "zh"
    updated_at: str = ""


class ConfigStore:
    """
    Persistent configuration storage.

    Stores user configuration in ~/.ternion/config.json
    """

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize config store."""
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._config: UserConfig | None = None

    def _ensure_dir(self) -> None:
        """Ensure config directory exists."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def _migrate_config(self, data: dict) -> dict:
        """Migrate old config format to new format."""
        if "providers" in data:
            for provider_name, provider_data in data["providers"].items():
                # Check if using old format (single api_key instead of api_keys list)
                if isinstance(provider_data, dict) and "api_key" in provider_data and "api_keys" not in provider_data:
                    old_key = provider_data.get("api_key", "")
                    old_enabled = provider_data.get("enabled", False)
                    if old_key:
                        # Migrate to new format
                        new_entry_id = str(uuid.uuid4())[:8]
                        data["providers"][provider_name] = {
                            "api_keys": [
                                {
                                    "id": new_entry_id,
                                    "name": "Migrated Key",
                                    "api_key": old_key,
                                }
                            ],
                            "selected_key_id": new_entry_id if old_enabled else None,
                        }
                    else:
                        data["providers"][provider_name] = {
                            "api_keys": [],
                            "selected_key_id": None,
                        }
        return data

    def load(self) -> UserConfig:
        """Load configuration from file."""
        if self._config is not None:
            return self._config

        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                    # Migrate old format if needed
                    data = self._migrate_config(data)
                    self._config = UserConfig(**data)
                    logger.info("config_loaded", path=str(self.config_path))
            except Exception as e:
                logger.warning("config_load_error", error=str(e))
                self._config = UserConfig()
        else:
            self._config = UserConfig()

        return self._config

    def reload(self) -> UserConfig:
        """Force reload configuration from file."""
        self._config = None
        return self.load()

    def save(self, config: UserConfig) -> None:
        """Save configuration to file."""
        self._ensure_dir()
        config.updated_at = datetime.utcnow().isoformat()

        try:
            with open(self.config_path, "w") as f:
                json.dump(config.model_dump(), f, indent=2)
            self._config = config
            logger.info("config_saved", path=str(self.config_path))
        except Exception as e:
            logger.error("config_save_error", error=str(e))
            raise

    def get_enabled_providers(self) -> list[str]:
        """Get list of providers with valid API keys."""
        config = self.load()
        return [
            name
            for name, provider in config.providers.items()
            if provider.enabled
        ]

    def get_provider_api_key(self, provider: str) -> str | None:
        """Get active API key for a provider."""
        config = self.load()
        provider_config = config.providers.get(provider)
        if provider_config:
            return provider_config.active_key
        return None

    def get_role_config(self, role: str) -> RoleConfig | None:
        """Get configuration for a role."""
        config = self.load()
        return config.roles.get(role)

    def get_available_models(self, provider: str) -> list[dict[str, str]]:
        """Get available models for a provider."""
        return AVAILABLE_MODELS.get(provider, [])

    def to_safe_dict(self) -> dict[str, Any]:
        """
        Convert config to safe dict (masks API keys).

        Used for API responses to avoid exposing full API keys.
        """
        config = self.load()
        return {
            "providers": {
                name: {
                    "enabled": provider.enabled,
                    "has_keys": len(provider.api_keys) > 0,
                    "selected_key_id": provider.selected_key_id,
                    "keys": [
                        {
                            "id": entry.id,
                            "name": entry.name,
                            "key_preview": (
                                f"...{entry.api_key[-6:]}"
                                if entry.api_key and len(entry.api_key) > 6
                                else ""
                            ),
                        }
                        for entry in provider.api_keys
                    ],
                }
                for name, provider in config.providers.items()
            },
            "roles": {
                name: {"provider": role.provider, "model": role.model}
                for name, role in config.roles.items()
            },
            "budget": {
                "monthly_limit_usd": config.budget.monthly_limit_usd,
                "alert_threshold": config.budget.alert_threshold,
            },
            "ports": {
                "backend": config.ports.backend,
                "web": config.ports.web,
            },
            "preferences": {
                "theme": config.theme,
                "language": config.language,
            },
            "updated_at": config.updated_at,
        }


# Global config store instance
_config_store: ConfigStore | None = None


def get_config_store() -> ConfigStore:
    """Get or create the global config store."""
    global _config_store
    if _config_store is None:
        _config_store = ConfigStore()
    return _config_store


# Convenience alias
config_store = get_config_store()

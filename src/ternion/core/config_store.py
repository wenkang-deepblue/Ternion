"""
Configuration storage for the Web Control Panel.

Provides persistent storage for user configuration including:
- Provider API keys (multiple per provider)
- Role-model assignments
- Budget settings
"""

import contextlib
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, get_args

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

# Default configuration path
DEFAULT_CONFIG_PATH = Path.home() / ".ternion" / "config.json"


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

    backend: int = 9110  # Ternion API server port
    web: int = 9120  # Web control panel port


ModelCatalogRefreshMode = Literal["daily", "interval_days", "interval_weeks"]


class ModelCatalogRefreshConfig(BaseModel):
    """Configuration for automatic model catalog refresh scheduling."""

    enabled: bool = Field(
        default=False,
        description="Whether automatic model catalog refresh is enabled.",
    )
    mode: ModelCatalogRefreshMode = Field(
        default="daily",
        description="Refresh cadence: daily, every N days, or every N weeks.",
    )
    time_of_day: str = Field(
        default="03:00",
        description='Daily refresh time in 24-hour "HH:MM" format.',
    )
    interval_value: int = Field(
        default=1,
        description="Positive interval value used for day/week refresh modes.",
    )
    last_refresh_at: str = Field(
        default="",
        description="Last successful refresh time as an ISO-8601 UTC string.",
    )
    next_refresh_at: str = Field(
        default="",
        description="Next scheduled refresh time as an ISO-8601 UTC string.",
    )


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
            # Ternion members (Divergence phase)
            "ternion_a": RoleConfig(),
            "ternion_b": RoleConfig(),
            "ternion_c": RoleConfig(),
            # Core roles (Convergence/Execution/Review phases)
            # No defaults - user must explicitly configure all roles in Web UI
            "arbiter": RoleConfig(),
            "writer": RoleConfig(),
            "reviewer": RoleConfig(),
        }
    )
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    ports: PortsConfig = Field(default_factory=PortsConfig)
    model_catalog_refresh: ModelCatalogRefreshConfig = Field(
        default_factory=ModelCatalogRefreshConfig
    )
    theme: str = "system"  # "light", "dark", "system"
    language: str = "auto"  # "auto", "en", "zh", "es", "fr", "de", "ja", "ko"
    # Browser-detected language (stored when language == "auto")
    # This allows backend to know user's browser language for report generation
    browser_language: str = "en"
    # Execution mode is intentionally empty by default.
    # Users MUST explicitly choose and save it in the Web Control Panel.
    execution_mode: str = ""  # "cursor_handoff" | "ternion_full" | ""
    hide_usage_disclaimer: bool = False  # Hide usage disclaimer warning
    # Control whether thinking logs are prepended to final output.
    # Set to False for strict system prompts that require only patch/diff output.
    show_thinking_logs: bool = True
    # Control whether phase indicators (Writer/Optimizer/etc) are shown to users.
    # This is intentionally independent from show_thinking_logs to support
    # "minimal logs, but still show phase" UX.
    show_phase_indicators: bool = True
    # Reserved for future CORS allowlist customization (v1/v1.5 advanced feature).
    # Users can add extra IPs (e.g., "192.168.1.100") for LAN access.
    # Backend will combine these with ports.web to form complete origins.
    cors_extra_origins: list[str] = Field(default_factory=list)
    updated_at: str = ""


class ConfigStore:
    """
    Persistent configuration storage.

    Stores user configuration in ~/.ternion/config.json
    """

    def __init__(self, config_path: Path | None = None) -> None:
        """
        Initialize config store.

        Args:
            config_path: Override default config file location. Defaults to ~/.ternion/config.json.
        """
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._config: UserConfig | None = None

    def _ensure_dir(self) -> None:
        """Ensure config directory exists."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def _migrate_config(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Migrate old config format to new format.

        Args:
            data: Raw configuration dictionary.

        Returns:
            Migrated configuration dictionary.
        """
        if "providers" in data:
            for provider_name, provider_data in data["providers"].items():
                # Check if using old format (single api_key instead of api_keys list)
                if (
                    isinstance(provider_data, dict)
                    and "api_key" in provider_data
                    and "api_keys" not in provider_data
                ):
                    old_key = provider_data.get("api_key", "")
                    if old_key:
                        # User must explicitly select which key after migration
                        new_entry_id = str(uuid.uuid4())[:8]
                        data["providers"][provider_name] = {
                            "api_keys": [
                                {
                                    "id": new_entry_id,
                                    "name": "Migrated Key",
                                    "api_key": old_key,
                                }
                            ],
                            "selected_key_id": None,  # User must select
                        }
                    else:
                        data["providers"][provider_name] = {
                            "api_keys": [],
                            "selected_key_id": None,
                        }
        refresh_settings = data.get("model_catalog_refresh")
        if isinstance(refresh_settings, dict):
            valid_modes = set(get_args(ModelCatalogRefreshMode))
            if refresh_settings.get("mode") not in valid_modes:
                refresh_settings["mode"] = "daily"

            interval_value = refresh_settings.get("interval_value", 1)
            try:
                refresh_settings["interval_value"] = max(int(interval_value), 1)
            except (TypeError, ValueError):
                refresh_settings["interval_value"] = 1

            time_of_day = refresh_settings.get("time_of_day")
            if not isinstance(time_of_day, str):
                refresh_settings["time_of_day"] = "03:00"
            else:
                parts = time_of_day.split(":")
                try:
                    hour, minute = (int(parts[0]), int(parts[1]))
                    if len(parts) != 2 or not 0 <= hour <= 23 or not 0 <= minute <= 59:
                        raise ValueError
                except (IndexError, TypeError, ValueError):
                    refresh_settings["time_of_day"] = "03:00"

            for key in ("last_refresh_at", "next_refresh_at"):
                value = refresh_settings.get(key)
                if not isinstance(value, str):
                    refresh_settings[key] = ""
        return data

    def load(self) -> UserConfig:
        """Load configuration from file."""
        if self._config is not None:
            return self._config

        if self.config_path.exists():
            try:
                with open(self.config_path, encoding="utf-8") as f:
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
        """
        Save configuration to file using atomic write with strict permissions.

        Uses temp file + os.replace for atomicity on POSIX systems.
        Sets file permissions to 0600 (owner read/write only) to protect API keys.

        Atomic write (tmp + os.replace) provides crash safety without a secondary backup file,
        which would double the API key exposure surface.
        """
        self._ensure_dir()
        config.updated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        # Atomic write using temp file + replace
        fd, tmp_path = tempfile.mkstemp(
            dir=self.config_path.parent, suffix=".tmp", prefix="config_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.config_path)
            # Set strict permissions: owner read/write only (0600)
            # This protects API keys from other users on shared machines
            os.chmod(self.config_path, 0o600)
            self._config = config
            logger.info("config_saved", path=str(self.config_path))
        except Exception as e:
            # Clean up temp file on failure
            with contextlib.suppress(OSError):
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            logger.error("config_save_error", error=str(e))
            raise

    def get_enabled_providers(self) -> list[str]:
        """Get list of providers with valid API keys."""
        config = self.load()
        return [name for name, provider in config.providers.items() if provider.enabled]

    def get_provider_api_key(self, provider: str) -> str | None:
        """Get active API key for a provider."""
        config = self.load()
        provider_config = config.providers.get(provider)
        if provider_config:
            return provider_config.active_key
        return None

    def _canonicalize_role_model(self, role_config: RoleConfig) -> RoleConfig:
        """Canonicalize a role model ID in memory when the catalog provides a stable ID."""
        if not role_config.provider or not role_config.model:
            return role_config

        try:
            from ternion.core.model_catalog import model_catalog_service
        except Exception as exc:
            logger.warning(
                "role_model_canonicalization_unavailable",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return role_config

        try:
            catalog_model = model_catalog_service.get_model_cached(role_config.model)
        except Exception as exc:
            logger.warning(
                "role_model_canonicalization_failed",
                provider=role_config.provider,
                model=role_config.model,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return role_config

        if catalog_model is None or catalog_model.provider != role_config.provider:
            return role_config

        if catalog_model.id != role_config.model:
            role_config.model = catalog_model.id

        return role_config

    def get_role_config(self, role: str) -> RoleConfig | None:
        """Get configuration for a role."""
        config = self.load()
        role_config = config.roles.get(role)
        if role_config is None:
            return None
        return self._canonicalize_role_model(role_config)

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
            "model_catalog_refresh": {
                "enabled": config.model_catalog_refresh.enabled,
                "mode": config.model_catalog_refresh.mode,
                "time_of_day": config.model_catalog_refresh.time_of_day,
                "interval_value": config.model_catalog_refresh.interval_value,
                "last_refresh_at": config.model_catalog_refresh.last_refresh_at,
                "next_refresh_at": config.model_catalog_refresh.next_refresh_at,
            },
            "preferences": {
                "theme": config.theme,
                "language": config.language,
                "browser_language": config.browser_language,
                "hide_usage_disclaimer": config.hide_usage_disclaimer,
                "show_thinking_logs": config.show_thinking_logs,
                "show_phase_indicators": config.show_phase_indicators,
            },
            "execution_mode": config.execution_mode,
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

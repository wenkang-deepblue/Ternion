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
from typing import Any

import structlog
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

    backend: int = 9110  # Ternion API server port
    web: int = 9120  # Web control panel port


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
        """Initialize config store."""
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._config: UserConfig | None = None

    def _ensure_dir(self) -> None:
        """Ensure config directory exists."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def _migrate_config(self, data: dict[str, Any]) -> dict[str, Any]:
        """Migrate old config format to new format."""
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
                        # Migrate to new format
                        # Note: selected_key_id is always None after migration
                        # User must explicitly select which key to use in the Web UI
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

        Note: Backup file was intentionally removed (CR-026) because:
        - It doubled the API key exposure surface (two files with plaintext keys)
        - Atomic write already provides sufficient crash safety
        - Backup files are easily captured by cloud sync/backup tools
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

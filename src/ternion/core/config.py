"""
Configuration management for Ternion.

Loads configuration from environment variables and YAML files.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    """Server configuration."""

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"


class ProviderConfig(BaseSettings):
    """Configuration for a single LLM provider."""

    api_key: str = ""
    base_url: str | None = None
    default_model: str = ""


class ProvidersSettings(BaseSettings):
    """All provider configurations."""

    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    google: ProviderConfig = Field(default_factory=ProviderConfig)


class RoleConfig(BaseSettings):
    """Configuration for a discussion role."""

    primary: str = ""
    fallback: list[str] = Field(default_factory=list)


class RolesSettings(BaseSettings):
    """Role assignments for the discussion."""

    arbiter: RoleConfig = Field(
        default_factory=lambda: RoleConfig(
            primary="google", fallback=["openai", "anthropic"]
        )
    )
    writer: RoleConfig = Field(
        default_factory=lambda: RoleConfig(
            primary="anthropic", fallback=["openai", "google"]
        )
    )
    reviewer: RoleConfig = Field(
        default_factory=lambda: RoleConfig(
            primary="openai", fallback=["anthropic", "google"]
        )
    )


class DiscussionSettings(BaseSettings):
    """Discussion flow configuration."""

    timeout_seconds: int = 120
    max_revision_rounds: int = 2
    roles: RolesSettings = Field(default_factory=RolesSettings)


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    log_discussion_details: bool = False
    log_file: str | None = None


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_prefix="TERNION_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    server: ServerSettings = Field(default_factory=ServerSettings)
    providers: ProvidersSettings = Field(default_factory=ProvidersSettings)
    discussion: DiscussionSettings = Field(default_factory=DiscussionSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    @classmethod
    def from_yaml(cls, path: Path) -> "Settings":
        """Load settings from a YAML file."""
        if not path.exists():
            return cls()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        # Expand environment variables in the config
        data = cls._expand_env_vars(data)
        return cls.model_validate(data)

    @classmethod
    def _expand_env_vars(cls, obj: Any) -> Any:
        """Recursively expand ${VAR} references in config values."""
        if isinstance(obj, str):
            # Handle ${VAR} syntax
            if obj.startswith("${") and obj.endswith("}"):
                var_name = obj[2:-1]
                return os.environ.get(var_name, "")
            return obj
        elif isinstance(obj, dict):
            return {k: cls._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [cls._expand_env_vars(item) for item in obj]
        return obj


@lru_cache
def get_settings() -> Settings:
    """
    Get application settings.

    Loads from YAML config file if TERNION_CONFIG_PATH is set,
    otherwise uses defaults with environment variable overrides.
    """
    config_path = os.environ.get("TERNION_CONFIG_PATH")

    if config_path:
        return Settings.from_yaml(Path(config_path))

    # Load from environment and defaults
    settings = Settings()

    # Override provider API keys from environment
    settings.providers.openai.api_key = os.environ.get("OPENAI_API_KEY", "")
    settings.providers.anthropic.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    settings.providers.google.api_key = os.environ.get("GOOGLE_API_KEY", "")

    # Override server settings from environment
    if port := os.environ.get("TERNION_PORT"):
        settings.server.port = int(port)
    if log_level := os.environ.get("TERNION_LOG_LEVEL"):
        settings.server.log_level = log_level
    if log_discussion := os.environ.get("TERNION_LOG_DISCUSSION"):
        settings.logging.log_discussion_details = log_discussion.lower() == "true"

    return settings


# Global settings instance
settings = get_settings()

"""Pydantic-settings configuration for the multi-agent system.

Loads configuration from environment variables and .env files with type
validation and documented defaults. Unknown environment variables cause
a startup failure to catch typos early.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from multiagent.exceptions import InvalidConfigurationError


class Settings(BaseSettings):
    """Application-wide configuration loaded from environment and .env files.

    All settings have type validation and documented defaults. Unknown environment
    variables cause a startup failure (extra='forbid') to catch typos early.
    """

    model_config = SettingsConfigDict(
        env_file=(".env.defaults", ".env"),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="forbid",
    )

    # Application identity
    app_name: str = Field("multiagent")
    app_env: str = Field("development", pattern=r"^(development|test|production)$")

    # Logging
    log_level: str = Field("INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    log_format: str = Field("console", pattern=r"^(console|json)$")

    # Hello World test configuration
    greeting_message: str = Field(
        "Hello from multiagent",
        description="Demonstrates a configurable value with a default.",
    )
    greeting_secret: str = Field(
        ...,
        description="Demonstrates a required secret with no default. Must be in .env.",
    )


def load_settings() -> Settings:
    """Load and validate application settings.

    Returns:
        The validated Settings instance.

    Raises:
        InvalidConfigurationError: If required settings are missing or values are invalid.
    """
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:
        raise InvalidConfigurationError(str(exc)) from exc

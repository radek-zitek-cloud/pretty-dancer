"""Pydantic-settings configuration for the multi-agent system.

Loads configuration from environment variables and .env files with type
validation and documented defaults. Unknown environment variables cause
a startup failure to catch typos early.
"""

from __future__ import annotations

from pathlib import Path

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

    # Observability — console stream
    log_console_enabled: bool = Field(
        True,
        description="Emit log events to stdout. Disable to suppress all console output.",
    )
    log_console_level: str = Field(
        "INFO",
        pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Minimum log level for console output.",
    )

    # Observability — human-readable log file stream (.log)
    log_human_file_enabled: bool = Field(
        False,
        description="Write a per-run human-readable log file alongside console output.",
    )
    log_human_file_level: str = Field(
        "INFO",
        pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Minimum log level for the human-readable log file.",
    )

    # Observability — JSON Lines log file stream (.jsonl)
    log_json_file_enabled: bool = Field(
        False,
        description="Write a per-run JSONL log file. Intended for agent-based analysis.",
    )
    log_json_file_level: str = Field(
        "DEBUG",
        pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Minimum log level for the JSONL log file. Defaults to DEBUG to "
        "capture maximum detail for experiment analysis.",
    )

    # Observability — shared
    log_dir: Path = Field(
        Path("logs"),
        description="Directory for per-run log files. Both .log and .jsonl land here.",
    )
    log_trace_llm: bool = Field(
        False,
        description="Include full LLM prompt and response content in the JSONL log file. "
        "Never emitted to console or human-readable file. "
        "Only effective when log_json_file_enabled=True.",
    )
    experiment: str = Field(
        "",
        description="Optional experiment label included in log filenames. "
        "Override per-run with the --experiment CLI flag.",
    )

    # Transport
    transport_backend: str = Field(
        "sqlite",
        pattern=r"^(sqlite|terminal)$",
        description="Active transport adapter. One of: sqlite, terminal.",
    )
    sqlite_db_path: Path = Field(
        Path("data/agents.db"),
        description="Path to SQLite database file. Use ':memory:' for tests.",
    )
    sqlite_poll_interval_seconds: float = Field(
        1.0,
        gt=0,
        description="Seconds between inbox polls when no message is available.",
    )

    # LLM
    openrouter_api_key: str = Field(..., description="OpenRouter API key. Required.")
    openrouter_base_url: str = Field(
        "https://openrouter.ai/api/v1",
        description="OpenRouter API base URL. Override only in tests or when self-hosting.",
    )
    llm_model: str = Field(
        "anthropic/claude-sonnet-4-5",
        description="OpenRouter model routing string. Format: provider/model-name.",
    )
    llm_max_tokens: int = Field(1024, ge=1, le=8192, description="Maximum response tokens.")
    llm_timeout_seconds: float = Field(30.0, gt=0, description="LLM call timeout in seconds.")

    # Prompts
    prompts_dir: Path = Field(
        Path("prompts"),
        description="Directory containing agent system prompt .md files. "
        "Each agent loads {prompts_dir}/{agent_name}.md at construction.",
    )

    # Agent wiring
    agents_config_path: Path = Field(
        Path("agents.toml"),
        description="Path to the agents configuration file. "
        "Declares all agents and their next_agent routing.",
    )

    # Checkpointer
    checkpointer_db_path: Path = Field(
        Path("data/checkpoints.db"),
        description="Path to LangGraph checkpoint database. "
        "Stores full conversation history per thread_id. "
        "Separate from the message transport database.",
    )

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

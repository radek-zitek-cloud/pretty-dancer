"""Agent wiring configuration loaded from TOML.

Reads agents.toml to determine which agents exist and how they are chained.
Uses stdlib tomllib — no third-party dependency required.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from multiagent.exceptions import InvalidConfigurationError


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for a single agent loaded from agents.toml.

    Attributes:
        name: Unique agent identifier. Used to locate prompt file and
            receive messages from transport.
        next_agent: Name of the agent to forward responses to. None
            means this is a terminal agent — responses are not forwarded.
    """

    name: str
    next_agent: str | None = None


def load_agents_config(config_path: Path) -> dict[str, AgentConfig]:
    """Load agent wiring configuration from a TOML file.

    Reads the agents.toml file and returns a mapping of agent name to
    AgentConfig. The file must exist and contain a valid [agents] table.

    Note: circular chains (e.g. A → B → A) are not validated at load time.
    They are a configuration error that surfaces at runtime.

    Args:
        config_path: Path to the agents TOML configuration file.

    Returns:
        Dict mapping agent name (str) to AgentConfig. Keys are agent names
        as declared in the [agents.<name>] sections.

    Raises:
        InvalidConfigurationError: If the file is missing, malformed, or
            contains no [agents] table.
    """
    try:
        raw = config_path.read_bytes()
    except FileNotFoundError:
        raise InvalidConfigurationError(
            f"Agents config file not found: {config_path}"
        ) from None
    except OSError as exc:
        raise InvalidConfigurationError(
            f"Failed to read agents config file: {exc}"
        ) from exc

    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise InvalidConfigurationError(
            f"Agents config file is not valid TOML: {exc}"
        ) from exc

    agents_raw: object = data.get("agents")
    if not agents_raw or not isinstance(agents_raw, dict):
        raise InvalidConfigurationError(
            f"Agents config file must contain an [agents] table: {config_path}"
        )

    agents_table: dict[str, dict[str, Any]] = agents_raw  # type: ignore[assignment]

    result: dict[str, AgentConfig] = {}
    for agent_name, section in agents_table.items():
        next_agent: str | None = section.get("next_agent")
        result[agent_name] = AgentConfig(
            name=agent_name,
            next_agent=next_agent,
        )
    return result

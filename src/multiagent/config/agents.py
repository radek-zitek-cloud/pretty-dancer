# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Agent and router wiring configuration loaded from TOML.

Reads agents.toml to determine which agents exist, how they are chained,
and what routers are available for dynamic routing decisions.
Uses stdlib tomllib — no third-party dependency required.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from multiagent.exceptions import InvalidConfigurationError


@dataclass(frozen=True)
class RouterConfig:
    """Configuration for a single router loaded from agents.toml.

    Attributes:
        name: Unique router identifier matching the [routers.<name>] section.
        type: Router type — "keyword" or "llm".
        routes: Mapping of destination agent name to trigger data.
            For keyword type: destination → list of trigger strings.
            For llm type: destination → route key string.
        default: Fallback destination when no route matches.
        prompt_path: Path to the LLM classifier prompt file. Required
            for llm type, None for keyword type.
        model: LLM model override for llm type. Empty string means
            use the default model from settings.
    """

    name: str
    type: str
    routes: dict[str, list[str]] = field(default_factory=lambda: dict[str, list[str]]())
    default: str = "human"
    prompt_path: Path | None = None
    model: str = ""


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for a single agent loaded from agents.toml.

    Attributes:
        name: Unique agent identifier. Used to locate prompt file and
            receive messages from transport.
        next_agent: Name of the agent to forward responses to. None
            means this is a terminal agent — responses are not forwarded.
            Mutually exclusive with router.
        router: Name of the router to use for dynamic routing. None
            means static routing via next_agent. Mutually exclusive
            with next_agent.
    """

    name: str
    next_agent: str | None = None
    router: str | None = None
    tools: list[str] = field(default_factory=list)
    prompt: str | None = None


@dataclass(frozen=True)
class AgentsConfig:
    """Complete agent and router configuration from agents.toml.

    Attributes:
        agents: Mapping of agent name to AgentConfig.
        routers: Mapping of router name to RouterConfig.
    """

    agents: dict[str, AgentConfig]
    routers: dict[str, RouterConfig]


def resolve_experiment_path(
    base_path: Path, experiment: str, label: str,
) -> Path:
    """Resolve a config path for the given experiment.

    When experiment is non-empty, transforms `base.ext` into
    `base.{experiment}.ext`. Raises ConfigurationError if the
    resolved file does not exist.
    """
    if not experiment:
        return base_path
    resolved = base_path.parent / f"{base_path.stem}.{experiment}{base_path.suffix}"
    if not resolved.exists():
        raise InvalidConfigurationError(
            f"Experiment {label} not found: {resolved}. "
            f"Create this file to run the '{experiment}' experiment."
        )
    return resolved


def load_agents_config(config_path: Path, experiment: str = "") -> AgentsConfig:
    """Load agent and router configuration from a TOML file.

    Reads the agents.toml file and returns an AgentsConfig containing
    both agent wiring and router definitions. The file must exist and
    contain a valid [agents] table. The [routers] table is optional.

    Validates that no agent has both next_agent and router set — these
    are mutually exclusive routing strategies.

    Args:
        config_path: Path to the agents TOML configuration file.
        experiment: Experiment name for path resolution. Empty for default.

    Returns:
        AgentsConfig with agents and routers dicts populated.

    Raises:
        InvalidConfigurationError: If the file is missing, malformed,
            contains no [agents] table, or has invalid configuration
            (e.g. agent with both next_agent and router).
    """
    config_path = resolve_experiment_path(config_path, experiment, "config")
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

    agents: dict[str, AgentConfig] = {}
    for agent_name, section in agents_table.items():
        next_agent: str | None = section.get("next_agent")
        router: str | None = section.get("router")

        if next_agent and router:
            raise InvalidConfigurationError(
                f"Agent '{agent_name}' has both next_agent and router — "
                f"these are mutually exclusive"
            )

        raw_tools = section.get("tools", [])
        tools_list: list[str] = (
            [str(t) for t in raw_tools] if isinstance(raw_tools, list) else []
        )

        prompt: str | None = section.get("prompt")

        agents[agent_name] = AgentConfig(
            name=agent_name,
            next_agent=next_agent,
            router=router,
            tools=tools_list,
            prompt=prompt,
        )

    routers: dict[str, RouterConfig] = {}
    routers_raw: object = data.get("routers")
    if routers_raw and isinstance(routers_raw, dict):
        routers_table: dict[str, dict[str, Any]] = routers_raw  # type: ignore[assignment]
        for router_name, section in routers_table.items():
            router_type: str = section.get("type", "")
            if not router_type:
                raise InvalidConfigurationError(
                    f"Router '{router_name}' must have a 'type' field"
                )

            raw_routes: dict[str, Any] = section.get("routes", {})
            routes: dict[str, list[str]] = {}
            for dest, triggers in raw_routes.items():
                if isinstance(triggers, list):
                    trigger_list: list[Any] = triggers
                    routes[dest] = [str(t) for t in trigger_list]
                else:
                    routes[dest] = [str(triggers)]

            default: str = section.get("default", "human")

            prompt_path: Path | None = None
            raw_prompt: str | None = section.get("prompt")
            if raw_prompt:
                prompt_path = Path(raw_prompt)

            model: str = section.get("model", "")

            routers[router_name] = RouterConfig(
                name=router_name,
                type=router_type,
                routes=routes,
                default=default,
                prompt_path=prompt_path,
                model=model,
            )

    return AgentsConfig(agents=agents, routers=routers)

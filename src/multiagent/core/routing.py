# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportCallIssue=false
"""Dynamic routing for agent output.

Provides keyword-based and LLM-based routers that determine the next
destination agent based on the content of an agent's output. All routing
logic is contained here — agent.py only wires the router into the graph.

Router types:
    KeywordRouter — scans output for trigger strings, no LLM call.
    LLMRouter — second lightweight LLM call returning a route key.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from langchain_openai import ChatOpenAI

from multiagent.config.agents import RouterConfig
from multiagent.exceptions import ConfigurationError

if TYPE_CHECKING:
    from multiagent.config.settings import Settings

Router = "KeywordRouter | LLMRouter"


class KeywordRouter:
    """Routes based on substring matching of trigger strings.

    Scans the agent's output for trigger strings defined in the router
    config. First matching destination wins. Falls back to the default
    destination when no trigger is found.

    Empty trigger lists are never matched — they serve only as
    documentation of valid destinations.
    """

    def __init__(self, config: RouterConfig) -> None:
        """Initialise the keyword router with its configuration."""
        self._config = config
        self._log = structlog.get_logger().bind(router=config.name)

    @property
    def config(self) -> RouterConfig:
        """The router configuration."""
        return self._config

    def route(self, output: str) -> str:
        """Scan output for trigger strings and return destination.

        Args:
            output: The agent's output text to scan.

        Returns:
            Destination agent name.
        """
        for destination, triggers in self._config.routes.items():
            for trigger in triggers:
                if trigger in output:
                    self._log.debug(
                        "keyword_match",
                        destination=destination,
                        trigger=trigger,
                    )
                    return destination

        self._log.debug("keyword_no_match", default=self._config.default)
        return self._config.default


class LLMRouter:
    """Routes based on a lightweight LLM classifier call.

    Makes a second LLM call with a classifier prompt to determine the
    routing destination. The LLM must return exactly one route key.
    Falls back to the default if the key is unrecognised.
    """

    def __init__(self, config: RouterConfig, settings: Settings) -> None:
        """Initialise the LLM router with config and settings for API credentials."""
        self._config = config
        self._log = structlog.get_logger().bind(router=config.name)

        model = config.model if config.model else settings.llm_model
        self._llm = ChatOpenAI(
            model=model,
            max_tokens=10,  # type: ignore[arg-type]
            timeout=settings.llm_timeout_seconds,
            api_key=settings.openrouter_api_key,  # type: ignore[arg-type]
            base_url=settings.openrouter_base_url,
        )

        self._prompt = ""
        if config.prompt_path and config.prompt_path.exists():
            self._prompt = config.prompt_path.read_text(encoding="utf-8").strip()

        self._valid_keys: set[str] = set(config.routes.keys())

    @property
    def config(self) -> RouterConfig:
        """The router configuration."""
        return self._config

    async def route(self, output: str) -> str:
        """Call LLM classifier to determine destination.

        Args:
            output: The agent's output text to classify.

        Returns:
            Destination agent name.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=self._prompt),
            HumanMessage(content=output),
        ]

        response = await self._llm.ainvoke(messages)
        raw_content = response.content  # str | list[str | dict]
        key: str = raw_content.strip() if isinstance(raw_content, str) else str(raw_content).strip()

        if key in self._valid_keys:
            self._log.debug("llm_route_matched", key=key)
            return key

        self._log.warning(
            "llm_route_unrecognised",
            key=key,
            valid_keys=list(self._valid_keys),
            default=self._config.default,
        )
        return self._config.default


def build_router(config: RouterConfig, settings: Settings) -> KeywordRouter | LLMRouter:
    """Factory function to create a router from configuration.

    Args:
        config: Router configuration from agents.toml.
        settings: Application settings for LLM credentials.

    Returns:
        A KeywordRouter or LLMRouter instance.

    Raises:
        ConfigurationError: If the router type is unknown.
    """
    if config.type == "keyword":
        return KeywordRouter(config)
    if config.type == "llm":
        return LLMRouter(config, settings)
    raise ConfigurationError(
        f"Unknown router type '{config.type}' for router '{config.name}'"
    )

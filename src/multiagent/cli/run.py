"""Implementation of the ``multiagent run`` command."""

from __future__ import annotations

import asyncio
import re
import sys

import structlog
import typer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from multiagent.config import load_settings
from multiagent.config.agents import load_agents_config
from multiagent.config.mcp import load_mcp_config
from multiagent.core.agent import LLMAgent
from multiagent.core.costs import CostLedger
from multiagent.core.routing import build_router
from multiagent.core.runner import AgentRunner
from multiagent.core.shutdown import ShutdownMonitor
from multiagent.exceptions import ConfigurationError
from multiagent.logging import configure_logging
from multiagent.transport import create_transport


async def _run(
    agent_name: str,
    experiment: str,
) -> None:
    """Async entry point for the run command."""
    if experiment and not re.match(r"^[a-z0-9-]+$", experiment):
        raise typer.BadParameter(
            f"Invalid experiment name '{experiment}'. "
            "Experiment names must contain only lowercase letters, digits, and hyphens."
        )

    settings = load_settings()
    if experiment:
        settings.experiment = experiment
    human_log, json_log = configure_logging(settings, agent_name=agent_name, experiment=experiment)
    log = structlog.get_logger(__name__)

    if human_log:
        typer.echo(f"Human log : {human_log}")
    if json_log:
        typer.echo(f"JSON log  : {json_log}")

    agents_config = load_agents_config(
        settings.agents_config_path, experiment=experiment
    )
    if agent_name not in agents_config.agents:
        raise typer.BadParameter(
            f"Agent '{agent_name}' not found in {settings.agents_config_path}. "
            f"Available: {', '.join(sorted(agents_config.agents.keys()))}"
        )

    agent_config = agents_config.agents[agent_name]
    mcp_config = load_mcp_config(
        settings.mcp_config_path, settings.mcp_secrets_path,
        experiment=experiment,
    )

    # Validate tool references
    for tool_name in agent_config.tools:
        if tool_name not in mcp_config.servers:
            raise ConfigurationError(
                f"Agent '{agent_name}' references tool '{tool_name}' "
                f"which is not defined in agents.mcp.json"
            )

    router = None
    if agent_config.router:
        if agent_config.router not in agents_config.routers:
            raise ConfigurationError(
                f"Agent '{agent_name}' references router '{agent_config.router}' "
                f"which is not defined in [routers.*]"
            )
        router = build_router(agents_config.routers[agent_config.router], settings)

    transport = create_transport(settings)
    monitor = ShutdownMonitor(settings.sqlite_db_path.parent)
    monitor.clear(agent_name)

    settings.checkpointer_db_path.parent.mkdir(parents=True, exist_ok=True)

    async with AsyncSqliteSaver.from_conn_string(
        str(settings.checkpointer_db_path)
    ) as checkpointer:
        async with CostLedger(settings.cost_db_path) as cost_ledger:
            tool_configs = [
                mcp_config.servers[t] for t in agent_config.tools
            ] or None
            agent = LLMAgent(
                agent_name, settings, checkpointer, cost_ledger,
                router=router, tool_configs=tool_configs,
                prompt_name=agent_config.prompt,
            )
            runner = AgentRunner(
                agent,
                transport,
                settings,
                next_agent=agent_config.next_agent,
                shutdown_monitor=monitor,
            )
            log.info("agent_starting", agent=agent_name, next_agent=agent_config.next_agent)
            try:
                await runner.run_loop()
            finally:
                monitor.clear(agent_name)
                await transport.close()


def run_command(
    agent_name: str = typer.Argument(..., help="Name of the agent to run."),
    experiment: str = typer.Option(
        "",
        "--experiment",
        "-e",
        help="Experiment label included in run log filenames.",
    ),
) -> None:
    """Start a named agent and poll for messages indefinitely.

    Loads settings and agent configuration, constructs the transport,
    and starts the AgentRunner polling loop. Exits cleanly on Ctrl-C.

    Args:
        agent_name: The agent name as declared in agents.toml.
        experiment: Optional experiment label for log filenames.
    """
    try:
        asyncio.run(_run(agent_name, experiment))
    except KeyboardInterrupt:
        log = structlog.get_logger(__name__)
        log.info("shutdown", reason="keyboard_interrupt")
        sys.exit(0)

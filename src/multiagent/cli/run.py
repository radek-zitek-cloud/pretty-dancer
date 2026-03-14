"""Implementation of the ``multiagent run`` command."""

from __future__ import annotations

import asyncio
import sys

import structlog
import typer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from multiagent.config import load_settings
from multiagent.config.agents import load_agents_config
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
    settings = load_settings()
    if experiment:
        settings.experiment = experiment
    human_log, json_log = configure_logging(settings, agent_name=agent_name, experiment=experiment)
    log = structlog.get_logger(__name__)

    if human_log:
        typer.echo(f"Human log : {human_log}")
    if json_log:
        typer.echo(f"JSON log  : {json_log}")

    agents_config = load_agents_config(settings.agents_config_path)
    if agent_name not in agents_config.agents:
        raise typer.BadParameter(
            f"Agent '{agent_name}' not found in {settings.agents_config_path}. "
            f"Available: {', '.join(sorted(agents_config.agents.keys()))}"
        )

    agent_config = agents_config.agents[agent_name]

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
            agent = LLMAgent(
                agent_name, settings, checkpointer, cost_ledger, router=router
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

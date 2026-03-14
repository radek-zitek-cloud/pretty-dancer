"""Implementation of the ``multiagent start`` command."""

from __future__ import annotations

import asyncio
import sys

import structlog
import typer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from multiagent.config import load_settings
from multiagent.config.agents import load_agents_config
from multiagent.core.agent import LLMAgent
from multiagent.core.runner import AgentRunner
from multiagent.logging import configure_logging
from multiagent.transport import create_transport


async def _start(experiment: str) -> None:
    """Load config, construct shared resources, and run all agents."""
    settings = load_settings()
    human_log, json_log = configure_logging(
        settings, agent_name="cluster", experiment=experiment
    )
    log = structlog.get_logger(__name__)

    if human_log:
        typer.echo(f"Human log : {human_log}")
    if json_log:
        typer.echo(f"JSON log  : {json_log}")

    agent_configs = load_agents_config(settings.agents_config_path)

    if not agent_configs:
        typer.echo("No agents configured — nothing to start.", err=True)
        return

    log.info("cluster_starting", agents=list(agent_configs.keys()))

    transport = create_transport(settings)

    settings.checkpointer_db_path.parent.mkdir(parents=True, exist_ok=True)

    async with AsyncSqliteSaver.from_conn_string(
        str(settings.checkpointer_db_path)
    ) as checkpointer:
        try:
            async with asyncio.TaskGroup() as tg:
                for name, config in agent_configs.items():
                    agent = LLMAgent(name, settings, checkpointer)
                    runner = AgentRunner(
                        agent, transport, settings, next_agent=config.next_agent
                    )
                    log.info(
                        "agent_starting",
                        agent=name,
                        next_agent=config.next_agent,
                    )
                    tg.create_task(runner.run_loop(), name=name)
        except* asyncio.CancelledError:
            pass  # clean shutdown — all tasks cancelled together
        except* Exception as eg:
            for exc in eg.exceptions:
                log.error("agent_task_failed", error=str(exc))
            raise

        log.info("cluster_stopped", agents=list(agent_configs.keys()))


def start_command(
    experiment: str = typer.Option(
        "",
        "--experiment",
        "-e",
        help="Experiment label included in run log filenames.",
    ),
) -> None:
    """Start all agents defined in agents.toml concurrently.

    Reads agents.toml, constructs one transport and one checkpointer
    shared across all agents, and runs every agent's polling loop
    concurrently in a single asyncio.TaskGroup. All agents stop cleanly
    on Ctrl-C.

    Args:
        experiment: Optional experiment label for log filenames.
    """
    try:
        asyncio.run(_start(experiment))
    except KeyboardInterrupt:
        print("\nCluster stopped.", file=sys.stderr)
        sys.exit(0)

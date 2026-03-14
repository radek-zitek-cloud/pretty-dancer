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
from multiagent.core.costs import CostLedger
from multiagent.core.routing import build_router
from multiagent.core.runner import AgentRunner
from multiagent.core.shutdown import ShutdownMonitor
from multiagent.exceptions import ConfigurationError
from multiagent.logging import configure_logging
from multiagent.transport import create_transport


async def _start(experiment: str) -> None:
    """Load config, construct shared resources, and run all agents."""
    settings = load_settings()
    if experiment:
        settings.experiment = experiment
    human_log, json_log = configure_logging(
        settings, agent_name="cluster", experiment=experiment
    )
    log = structlog.get_logger(__name__)

    if human_log:
        typer.echo(f"Human log : {human_log}")
    if json_log:
        typer.echo(f"JSON log  : {json_log}")

    agents_config = load_agents_config(settings.agents_config_path)

    if not agents_config.agents:
        typer.echo("No agents configured — nothing to start.", err=True)
        return

    log.info("cluster_starting", agents=list(agents_config.agents.keys()))

    transport = create_transport(settings)
    monitor = ShutdownMonitor(settings.sqlite_db_path.parent)
    monitor.clear()

    settings.checkpointer_db_path.parent.mkdir(parents=True, exist_ok=True)

    async with AsyncSqliteSaver.from_conn_string(
        str(settings.checkpointer_db_path)
    ) as checkpointer:
        async with CostLedger(settings.cost_db_path) as cost_ledger:
            try:
                async with asyncio.TaskGroup() as tg:
                    for name, config in agents_config.agents.items():
                        router = None
                        if config.router:
                            if config.router not in agents_config.routers:
                                raise ConfigurationError(
                                    f"Agent '{name}' references router "
                                    f"'{config.router}' which is not defined "
                                    f"in [routers.*]"
                                )
                            router = build_router(
                                agents_config.routers[config.router], settings
                            )

                        agent = LLMAgent(
                            name, settings, checkpointer, cost_ledger,
                            router=router,
                        )
                        runner = AgentRunner(
                            agent,
                            transport,
                            settings,
                            next_agent=config.next_agent,
                            shutdown_monitor=monitor,
                        )
                        log.info(
                            "agent_starting",
                            agent=name,
                            next_agent=config.next_agent,
                            router=config.router,
                        )
                        tg.create_task(runner.run_loop(), name=name)
            except* asyncio.CancelledError:
                pass  # clean shutdown — all tasks cancelled together
            except* Exception as eg:
                for exc in eg.exceptions:
                    log.error("agent_task_failed", error=str(exc))
                raise
            finally:
                monitor.clear()
                await transport.close()

            log.info("cluster_stopped", agents=list(agents_config.agents.keys()))


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

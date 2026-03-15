"""Implementation of the ``multiagent start`` command."""

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
from multiagent.config.settings import agents_config_path, mcp_config_path, mcp_secrets_path
from multiagent.core.agent import LLMAgent
from multiagent.core.costs import CostLedger
from multiagent.core.routing import build_router
from multiagent.core.runner import AgentRunner
from multiagent.core.shutdown import ShutdownMonitor
from multiagent.exceptions import ConfigurationError
from multiagent.logging import configure_logging
from multiagent.transport import create_transport


async def _start(cluster: str) -> None:
    """Load config, construct shared resources, and run all agents."""
    if isinstance(cluster, str) and cluster and not re.match(r"^[a-z0-9-]+$", cluster):  # type: ignore[reportUnnecessaryIsInstance]
        raise typer.BadParameter(
            f"Invalid cluster name '{cluster}'. "
            "Cluster names must contain only lowercase letters, digits, and hyphens."
        )

    settings = load_settings()
    if cluster:
        settings.cluster = cluster
    human_log, json_log = configure_logging(
        settings, agent_name="cluster", cluster=cluster
    )
    log = structlog.get_logger(__name__)

    if human_log:
        typer.echo(f"Human log : {human_log}")
    if json_log:
        typer.echo(f"JSON log  : {json_log}")

    agents_config = load_agents_config(agents_config_path(settings))
    mcp_config = load_mcp_config(
        mcp_config_path(settings), mcp_secrets_path(settings),
    )

    if not agents_config.agents:
        typer.echo("No agents configured — nothing to start.", err=True)
        return

    # Validate tool references against MCP config
    for name, config in agents_config.agents.items():
        for tool_name in config.tools:
            if tool_name not in mcp_config.servers:
                raise ConfigurationError(
                    f"Agent '{name}' references tool '{tool_name}' "
                    f"which is not defined in agents.mcp.json"
                )

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

                        tool_configs = [
                            mcp_config.servers[t]
                            for t in config.tools
                        ] or None

                        agent = LLMAgent(
                            name, settings, checkpointer, cost_ledger,
                            router=router,
                            tool_configs=tool_configs,
                            prompt_name=config.prompt,
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
    cluster: str = typer.Option(
        "",
        "--cluster",
        "-c",
        help="Cluster name — loads configuration from clusters/{cluster}/.",
    ),
) -> None:
    """Start all agents defined in agents.toml concurrently.

    Reads agents.toml, constructs one transport and one checkpointer
    shared across all agents, and runs every agent's polling loop
    concurrently in a single asyncio.TaskGroup. All agents stop cleanly
    on Ctrl-C.

    Args:
        cluster: Optional cluster name for configuration resolution.
    """
    try:
        asyncio.run(_start(cluster))
    except KeyboardInterrupt:
        print("\nCluster stopped.", file=sys.stderr)
        sys.exit(0)

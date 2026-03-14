"""Implementation of the ``multiagent stop`` command."""

from __future__ import annotations

import typer

from multiagent.config import load_settings
from multiagent.core.shutdown import ShutdownMonitor


def stop_command(
    agent_name: str | None = typer.Argument(
        default=None,
        help="Agent to stop. If omitted, stops all agents.",
    ),
) -> None:
    """Request graceful shutdown of running agents.

    Creates a sentinel file that running agents detect within one poll
    interval. Use without an argument to stop all agents, or pass an
    agent name to stop only that one.
    """
    settings = load_settings()
    monitor = ShutdownMonitor(settings.sqlite_db_path.parent)
    path = monitor.request_stop(agent_name)
    if agent_name:
        typer.echo(f"Stop requested for agent '{agent_name}' ({path})")
    else:
        typer.echo(f"Stop requested for all agents ({path})")

"""Implementation of the ``multiagent run`` command."""

from __future__ import annotations

import asyncio
import sys

import structlog
import typer

from multiagent.config import load_settings
from multiagent.config.agents import load_agents_config
from multiagent.core.agent import LLMAgent
from multiagent.core.runner import AgentRunner
from multiagent.logging import configure_logging
from multiagent.transport import create_transport


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
    settings = load_settings()
    human_log, json_log = configure_logging(settings, agent_name=agent_name, experiment=experiment)
    log = structlog.get_logger(__name__)

    if human_log:
        typer.echo(f"Human log : {human_log}")
    if json_log:
        typer.echo(f"JSON log  : {json_log}")

    configs = load_agents_config(settings.agents_config_path)
    if agent_name not in configs:
        raise typer.BadParameter(
            f"Agent '{agent_name}' not found in {settings.agents_config_path}. "
            f"Available: {', '.join(sorted(configs.keys()))}"
        )

    config = configs[agent_name]
    transport = create_transport(settings)
    agent = LLMAgent(agent_name, settings)
    runner = AgentRunner(agent, transport, settings, next_agent=config.next_agent)

    try:
        asyncio.run(runner.run_loop())
    except KeyboardInterrupt:
        log.info("shutdown", reason="keyboard_interrupt")
        sys.exit(0)

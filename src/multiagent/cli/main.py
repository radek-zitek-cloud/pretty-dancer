"""CLI entry point for the multiagent system.

Commands:
    run  — Start a named agent and poll for messages.
    send — Inject a message into the transport for a named agent.
"""

from __future__ import annotations

import sys

import typer

from multiagent.cli.run import run_command
from multiagent.cli.send import send_command

app = typer.Typer(
    name="multiagent",
    help="Multi-agent LLM system.",
    no_args_is_help=True,
    add_completion=False,
)

app.command(name="run")(run_command)
app.command(name="send")(send_command)


def main() -> None:
    """Entry point called by ``[project.scripts]`` in pyproject.toml."""
    if sys.platform == "win32":
        import asyncio

        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app()

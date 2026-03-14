"""Implementation of the ``multiagent send`` command."""

from __future__ import annotations

import asyncio
import uuid as uuid_module

import typer

from multiagent.config import load_settings
from multiagent.config.agents import load_agents_config
from multiagent.transport import create_transport
from multiagent.transport.base import Message


def send_command(
    agent_name: str = typer.Argument(..., help="Name of the agent to send to."),
    body: str = typer.Argument(..., help="Message body text."),
    thread_id: str = typer.Option(
        "",
        "--thread-id", "-t",
        help="Existing thread UUID to continue. Omit to start a new thread.",
    ),
) -> None:
    """Inject a message into the transport addressed to a named agent.

    Creates a new message thread and delivers the message body to the
    named agent's inbox. Prints the assigned thread_id on success.

    Args:
        agent_name: The target agent name as declared in agents.toml.
        body: The message body to deliver.
        thread_id: Optional existing thread UUID to continue.
    """
    settings = load_settings()
    agents_config = load_agents_config(settings.agents_config_path)

    if agent_name not in agents_config.agents:
        raise typer.BadParameter(
            f"Agent '{agent_name}' not found in {settings.agents_config_path}. "
            f"Available: {', '.join(sorted(agents_config.agents.keys()))}"
        )

    resolved_thread_id: str | None = None

    if thread_id:
        try:
            uuid_module.UUID(thread_id)
            resolved_thread_id = thread_id
        except ValueError:
            raise typer.BadParameter(
                f"thread-id must be a valid UUID: {thread_id!r}",
                param_hint="--thread-id",
            ) from None

    transport = create_transport(settings)
    message = Message(
        from_agent="human",
        to_agent=agent_name,
        body=body,
    )
    if resolved_thread_id:
        message.thread_id = resolved_thread_id

    asyncio.run(transport.send(message))
    typer.echo(f"Sent to {agent_name}. Thread: {message.thread_id}")

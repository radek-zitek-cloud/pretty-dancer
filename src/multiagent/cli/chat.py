"""Implementation of the ``multiagent chat`` command.

Provides an interactive REPL for two-way human↔agent conversation.
Messages are sent via the transport layer; replies are polled via
direct SQL (same pattern as listen and the inspection scripts).
"""

from __future__ import annotations

import asyncio
import re
import uuid as uuid_module
from datetime import UTC, datetime

import aiosqlite
import typer
from rich.console import Console
from rich.panel import Panel

from multiagent.config import load_settings
from multiagent.config.agents import load_agents_config
from multiagent.transport import Transport, create_transport
from multiagent.transport.base import Message


async def _async_input(prompt: str) -> str:
    """Run blocking input() in a thread executor to avoid ASYNC250."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, input, prompt)


_REPLY_QUERY = """\
SELECT id, from_agent, body, created_at
FROM messages
WHERE to_agent = 'human' AND thread_id = ? AND processed_at IS NULL
ORDER BY created_at ASC
"""


async def _send_message(
    transport: Transport,
    agent_name: str,
    body: str,
    thread_id: str,
) -> None:
    """Send a single message from human to agent via the transport layer."""
    msg = Message(
        from_agent="human",
        to_agent=agent_name,
        body=body,
        thread_id=thread_id,
    )
    await transport.send(msg)


async def _poll_reply(
    db_path: str,
    thread_id: str,
    reply_timeout: float,
    poll_interval: float,
) -> tuple[str, str, int] | None:
    """Poll for an agent reply addressed to human in the given thread.

    Returns (from_agent, body, row_id) or None on timeout.
    """
    elapsed = 0.0
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        while elapsed < reply_timeout:
            cursor = await conn.execute(_REPLY_QUERY, (thread_id,))
            row = await cursor.fetchone()
            if row is not None:
                now = datetime.now(UTC).isoformat()
                await conn.execute(
                    "UPDATE messages SET processed_at = ? WHERE id = ?",
                    (now, row["id"]),
                )
                await conn.commit()
                return str(row["from_agent"]), str(row["body"]), int(row["id"])
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
    return None


async def _chat_loop(
    agent_name: str,
    thread_id: str,
    transport: Transport,
    db_path: str,
    reply_timeout: float,
    poll_interval: float,
) -> None:
    """Main chat REPL loop."""
    console = Console()
    console.print(
        f"Chat session with [bold]{agent_name}[/bold]  "
        f"thread: [dim]{thread_id[:8]}[/dim]\n"
        f"Type a message and press Enter. Empty line or Ctrl-C to exit.\n"
    )

    while True:
        try:
            user_input = await _async_input("You: ")
        except EOFError:
            break

        if not user_input.strip():
            break

        await _send_message(transport, agent_name, user_input, thread_id)

        console.print("[dim]Waiting for reply…[/dim]")
        reply = await _poll_reply(db_path, thread_id, reply_timeout, poll_interval)

        if reply is None:
            console.print(
                f"[yellow]No reply after {reply_timeout:.0f}s. "
                f"Continue waiting? (y/n)[/yellow]"
            )
            try:
                choice = (await _async_input("> ")).strip().lower()
            except EOFError:
                break
            if choice == "y":
                reply = await _poll_reply(
                    db_path, thread_id, reply_timeout, poll_interval
                )
            if reply is None:
                console.print("[red]Still no reply. Continuing…[/red]")
                continue

        from_agent, body, _ = reply
        header = f"{from_agent} → you"
        console.print(Panel(body, title=header))

    console.print(f"\nSession ended. Thread: {thread_id}")


def chat_command(
    agent_name: str = typer.Argument(..., help="Name of the agent to chat with."),
    thread_id: str = typer.Option(
        "",
        "--thread-id",
        "-t",
        help="Existing thread UUID. Omit to start a new thread.",
    ),
    experiment: str = typer.Option(
        "",
        "--experiment",
        "-e",
        help="Optional experiment label.",
    ),
) -> None:
    """Start an interactive chat session with a named agent."""
    settings = load_settings()
    if experiment and not re.match(r"^[a-z0-9-]+$", experiment):
        raise typer.BadParameter(
            f"Invalid experiment name '{experiment}'. "
            "Experiment names must contain only lowercase letters, "
            "digits, and hyphens."
        )

    agents_config = load_agents_config(
        settings.agents_config_path, experiment=experiment
    )

    if agent_name not in agents_config.agents:
        raise typer.BadParameter(
            f"Agent '{agent_name}' not found in {settings.agents_config_path}. "
            f"Available: {', '.join(sorted(agents_config.agents.keys()))}"
        )

    if thread_id:
        try:
            uuid_module.UUID(thread_id)
        except ValueError:
            raise typer.BadParameter(
                f"thread-id must be a valid UUID: {thread_id!r}",
                param_hint="--thread-id",
            ) from None
    else:
        thread_id = str(uuid_module.uuid4())

    if experiment:
        settings.experiment = experiment

    transport = create_transport(settings)
    db_path = str(settings.sqlite_db_path)

    try:
        asyncio.run(
            _chat_loop(
                agent_name,
                thread_id,
                transport,
                db_path,
                settings.chat_reply_timeout_seconds,
                settings.sqlite_poll_interval_seconds,
            )
        )
    except KeyboardInterrupt:
        typer.echo(f"\nSession ended. Thread: {thread_id}")
        raise SystemExit(0) from None

"""Implementation of the ``multiagent listen`` command.

Polls the transport database for messages addressed to ``human`` and
displays them in the terminal using Rich panels.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import aiosqlite
import typer
from rich.console import Console
from rich.panel import Panel

from multiagent.config import load_settings

_POLL_QUERY = """\
SELECT id, from_agent, to_agent, body, thread_id, created_at
FROM messages
WHERE to_agent = 'human' AND processed_at IS NULL
"""

_POLL_QUERY_THREAD = """\
SELECT id, from_agent, to_agent, body, thread_id, created_at
FROM messages
WHERE to_agent = 'human' AND processed_at IS NULL AND thread_id = ?
"""


async def _listen(
    db_path: str,
    thread_id: str | None,
    poll_interval: float,
) -> None:
    """Poll loop: fetch unprocessed messages for human, display, mark processed."""
    console = Console()
    console.print("Listening for messages… (Ctrl-C to stop)")

    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        while True:
            if thread_id:
                cursor = await conn.execute(_POLL_QUERY_THREAD, (thread_id,))
            else:
                cursor = await conn.execute(_POLL_QUERY)

            rows = await cursor.fetchall()
            for row in rows:
                tid = str(row["thread_id"])
                ts = str(row["created_at"])[:19]
                header = (
                    f"{row['from_agent']} → you  |  {ts}  |  thread: {tid[:8]}"
                )
                console.print(Panel(str(row["body"]), title=header))

                now = datetime.now(UTC).isoformat()
                await conn.execute(
                    "UPDATE messages SET processed_at = ? WHERE id = ?",
                    (now, row["id"]),
                )
                await conn.commit()

            await asyncio.sleep(poll_interval)


def listen_command(
    thread_id: str = typer.Option(
        "",
        "--thread-id",
        "-t",
        help="Only show messages from this thread UUID.",
    ),
    poll_interval: float = typer.Option(
        0,
        "--poll-interval",
        "-p",
        help="Seconds between polls. 0 = use setting default.",
    ),
) -> None:
    """Poll for messages addressed to human and display them."""
    settings = load_settings()
    db_path = str(settings.sqlite_db_path)
    interval = poll_interval if poll_interval > 0 else settings.sqlite_poll_interval_seconds

    try:
        asyncio.run(
            _listen(db_path, thread_id or None, interval)
        )
    except KeyboardInterrupt:
        typer.echo("Stopped.")
        raise SystemExit(0) from None

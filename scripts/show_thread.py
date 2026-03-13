"""Display one complete conversation thread from SQLite.

Usage: python scripts/show_thread.py [--db PATH] <thread_id>

Reads the transport database and displays all messages in the given
thread, formatted with rich panels colour-coded by agent role.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

AGENT_COLOURS: dict[str, str] = {
    "human": "blue",
    "researcher": "green",
    "critic": "yellow",
}


def _resolve_db_path(cli_db: str | None) -> Path:
    """Resolve database path from CLI arg or Settings fallback.

    Args:
        cli_db: Explicit --db path from CLI, or None.

    Returns:
        Resolved Path to the SQLite database.
    """
    if cli_db:
        return Path(cli_db)
    try:
        from multiagent.config.settings import Settings

        settings = Settings()  # type: ignore[call-arg]
        return settings.sqlite_db_path
    except Exception:
        print(
            "Cannot load settings. Use --db to specify the database path.",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    """Entry point for show_thread script."""
    parser = argparse.ArgumentParser(description="Display a conversation thread from SQLite.")
    parser.add_argument("thread_id", help="Thread ID to display.")
    parser.add_argument(
        "--db",
        default=None,
        help="Path to SQLite database. Defaults to value from settings.",
    )
    args = parser.parse_args()

    db_path = _resolve_db_path(args.db)

    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, from_agent, to_agent, body, thread_id, created_at, processed_at "
            "FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
            (args.thread_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        print(f"No messages found for thread: {args.thread_id}", file=sys.stderr)
        sys.exit(1)

    console = Console()

    # Header panel
    first_ts = rows[0]["created_at"]
    last_ts = rows[-1]["created_at"]
    console.print(
        Panel(
            f"Thread: {args.thread_id}\n"
            f"Messages: {len(rows)}\n"
            f"Time range: {first_ts} → {last_ts}",
            title="Thread Summary",
            border_style="bright_white",
        )
    )

    # Message panels
    for row in rows:
        from_agent = row["from_agent"]
        to_agent = row["to_agent"]
        colour = AGENT_COLOURS.get(from_agent, "white")
        title = f"[{from_agent}] → [{to_agent}]  |  {row['created_at']}  |  id={row['id']}"

        processed = row["processed_at"]
        status = processed if processed else "[red][PENDING][/red]"

        console.print(
            Panel(
                f"{row['body']}\n\n{status}",
                title=title,
                border_style=colour,
            )
        )


if __name__ == "__main__":
    main()

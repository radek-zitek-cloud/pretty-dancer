"""Browse conversation threads from the SQLite transport database.

Displays all threads as a numbered list and launches show_thread.py
on the selected thread. Database path is read from application settings.

Usage:
    uv run python scripts/browse_threads.py
    just threads
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

THREAD_SUMMARY_QUERY = """\
SELECT
    thread_id,
    COUNT(*)                                       AS message_count,
    SUM(processed_at IS NOT NULL)                  AS processed_count,
    MIN(created_at)                                AS started_at,
    MAX(created_at)                                AS last_at,
    MIN(body)                                      AS preview
FROM messages
GROUP BY thread_id
ORDER BY MAX(created_at) DESC
"""


def _load_db_path() -> Path:
    """Load database path from application settings.

    Returns:
        Path to the SQLite transport database.
    """
    try:
        from multiagent.config.settings import Settings

        settings = Settings()  # type: ignore[call-arg]
        return settings.sqlite_db_path
    except Exception as exc:
        print(f"Cannot load settings: {exc}", file=sys.stderr)
        sys.exit(1)


def _format_time(ts: str | None) -> str:
    """Extract HH:MM:SS from an ISO timestamp string."""
    if not ts:
        return "?"
    # Timestamps are ISO format; time portion starts after 'T' or after space
    for sep in ("T", " "):
        if sep in ts:
            time_part = ts.split(sep, 1)[1]
            return time_part[:8]
    return ts[:8]


def _truncate(text: str | None, length: int = 60) -> str:
    """Truncate text to length, adding ellipsis if needed."""
    if not text:
        return ""
    if len(text) <= length:
        return text
    return text[: length - 1] + "\u2026"


def _display_table(console: Console, rows: list[sqlite3.Row]) -> None:
    """Display threads as a numbered rich table."""
    table = Table(title="Conversation Threads")
    table.add_column("#", justify="right", style="bold")
    table.add_column("Thread ID")
    table.add_column("Messages", justify="right")
    table.add_column("Processed", justify="right")
    table.add_column("Preview")
    table.add_column("Started")
    table.add_column("Last activity")

    for i, row in enumerate(rows, 1):
        table.add_row(
            str(i),
            str(row["thread_id"])[:8],
            str(row["message_count"]),
            str(row["processed_count"]),
            _truncate(row["preview"]),
            _format_time(row["started_at"]),
            _format_time(row["last_at"]),
        )

    console.print(table)


def _fetch_rows(db_path: Path) -> list[sqlite3.Row]:
    """Query the database and return thread summary rows."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(THREAD_SUMMARY_QUERY).fetchall()
    finally:
        conn.close()


def main() -> None:
    """Entry point for browse_threads script."""
    db_path = _load_db_path()

    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    console = Console()

    rows = _fetch_rows(db_path)
    if not rows:
        console.print("No threads found in database.")
        sys.exit(0)

    _display_table(console, rows)

    while True:
        try:
            choice = input("Enter thread number (r=refresh, q=quit): ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not choice or choice.lower() == "q":
            break

        if choice.lower() == "r":
            rows = _fetch_rows(db_path)
            _display_table(console, rows)
            continue

        try:
            index = int(choice) - 1
            if index < 0 or index >= len(rows):
                raise ValueError
        except ValueError:
            print("Invalid selection.")
            continue

        thread_id = str(rows[index]["thread_id"])
        subprocess.run(
            ["uv", "run", "python", "scripts/show_thread.py", thread_id],
            check=False,
        )

        # Refresh data and redisplay table after returning from show_thread
        rows = _fetch_rows(db_path)
        _display_table(console, rows)


if __name__ == "__main__":
    main()

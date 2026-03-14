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
from rich.table import Table

AGENT_COLOURS: dict[str, str] = {
    "human": "blue",
    "researcher": "green",
    "critic": "yellow",
}

COST_SUMMARY_QUERY = """\
SELECT
    agent,
    COUNT(*)            AS calls,
    SUM(input_tokens)   AS input_tokens,
    SUM(output_tokens)  AS output_tokens,
    SUM(total_tokens)   AS total_tokens,
    SUM(cost_usd)       AS cost_usd
FROM cost_ledger
WHERE thread_id = ?
GROUP BY agent
ORDER BY MIN(timestamp)
"""


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


def _load_cost_db_path() -> Path | None:
    """Load cost database path from settings.

    Returns:
        Path to costs.db, or None if settings cannot be loaded.
    """
    try:
        from multiagent.config.settings import Settings

        settings = Settings()  # type: ignore[call-arg]
        return settings.cost_db_path
    except Exception:
        return None


def _render_cost_footer(console: Console, thread_id: str, cost_db_path: Path | None) -> None:
    """Render a cost summary footer for the thread, if cost data exists."""
    if cost_db_path is None or not cost_db_path.exists():
        return

    try:
        conn = sqlite3.connect(str(cost_db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(COST_SUMMARY_QUERY, (thread_id,)).fetchall()
        finally:
            conn.close()
    except Exception:
        return

    if not rows:
        return

    table = Table(title=f"Cost summary \u2014 thread {thread_id[:8]}")
    table.add_column("Agent", style="bold")
    table.add_column("Calls", justify="right")
    table.add_column("Input tokens", justify="right")
    table.add_column("Output tokens", justify="right")
    table.add_column("Total tokens", justify="right")
    table.add_column("Cost USD", justify="right")

    total_calls = 0
    total_input = 0
    total_output = 0
    total_tokens = 0
    total_cost = 0.0

    for row in rows:
        calls = int(row["calls"])
        inp = int(row["input_tokens"])
        out = int(row["output_tokens"])
        tok = int(row["total_tokens"])
        cost = float(row["cost_usd"])
        total_calls += calls
        total_input += inp
        total_output += out
        total_tokens += tok
        total_cost += cost
        table.add_row(
            str(row["agent"]),
            str(calls),
            str(inp),
            str(out),
            str(tok),
            f"${cost:.4f}",
        )

    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{total_calls}[/bold]",
        f"[bold]{total_input}[/bold]",
        f"[bold]{total_output}[/bold]",
        f"[bold]{total_tokens}[/bold]",
        f"[bold]${total_cost:.4f}[/bold]",
    )

    console.print()
    console.print(table)


def _build_agent_cost_lookup(
    thread_id: str, cost_db_path: Path | None
) -> dict[str, dict[str, object]]:
    """Build a per-agent cost summary dict for the thread.

    Returns {agent_name: {calls, input_tokens, output_tokens, total_tokens, cost_usd}}.
    """
    if cost_db_path is None or not cost_db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(cost_db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(COST_SUMMARY_QUERY, (thread_id,)).fetchall()
        finally:
            conn.close()
    except Exception:
        return {}

    lookup: dict[str, dict[str, object]] = {}
    for row in rows:
        lookup[str(row["agent"])] = {
            "calls": int(row["calls"]),
            "input_tokens": int(row["input_tokens"]),
            "output_tokens": int(row["output_tokens"]),
            "total_tokens": int(row["total_tokens"]),
            "cost_usd": float(row["cost_usd"]),
        }
    return lookup


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
    participants = sorted({row["from_agent"] for row in rows} | {row["to_agent"] for row in rows})
    console.print(
        Panel(
            f"Thread: {args.thread_id}\n"
            f"Messages: {len(rows)}\n"
            f"Participants: {', '.join(participants)}\n"
            f"Time range: {first_ts} → {last_ts}",
            title="Thread Summary",
            border_style="bright_white",
        )
    )

    # Build per-agent cost lookup from cost_ledger (keyed by agent name)
    cost_db_path = _load_cost_db_path()
    agent_costs = _build_agent_cost_lookup(args.thread_id, cost_db_path)

    # Message panels
    for row in rows:
        from_agent = row["from_agent"]
        to_agent = row["to_agent"]
        colour = AGENT_COLOURS.get(from_agent, "white")
        title = f"{from_agent} → {to_agent}  |  {row['created_at']}  |  id={row['id']}"

        processed = row["processed_at"]
        status = processed if processed else "[red][PENDING][/red]"

        # Build subtitle with cost info if this agent has cost data
        subtitle_parts: list[str] = []
        if from_agent in agent_costs:
            ac = agent_costs[from_agent]
            subtitle_parts.append(
                f"tokens: {ac['input_tokens']}→{ac['output_tokens']} "
                f"({ac['total_tokens']} total)  |  "
                f"cost: ${ac['cost_usd']:.4f}  |  "
                f"calls: {ac['calls']}"
            )

        console.print(
            Panel(
                f"{row['body']}\n\n{status}",
                title=title,
                subtitle=" | ".join(subtitle_parts) if subtitle_parts else None,
                border_style=colour,
            )
        )

    # Cost summary footer
    _render_cost_footer(console, args.thread_id, cost_db_path)


if __name__ == "__main__":
    main()

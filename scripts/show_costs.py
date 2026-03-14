"""Analytical cost views across runs and experiments.

Reads from the cost ledger database. Database path is read from
application settings.

Usage:
    uv run python scripts/show_costs.py                      # by experiment
    uv run python scripts/show_costs.py --by-agent           # by agent
    uv run python scripts/show_costs.py --by-model           # by model
    uv run python scripts/show_costs.py --experiment LABEL   # single experiment
    just costs
    just costs-by-agent
    just costs-by-model
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

QUERY_BY_EXPERIMENT = """\
SELECT
    experiment,
    COUNT(*)            AS calls,
    SUM(input_tokens)   AS input_tokens,
    SUM(output_tokens)  AS output_tokens,
    SUM(cost_usd)       AS cost_usd
FROM cost_ledger
GROUP BY experiment
ORDER BY MIN(timestamp) DESC
"""

QUERY_BY_AGENT = """\
SELECT
    agent,
    COUNT(*)            AS calls,
    SUM(input_tokens)   AS input_tokens,
    SUM(output_tokens)  AS output_tokens,
    SUM(cost_usd)       AS cost_usd
FROM cost_ledger
GROUP BY agent
ORDER BY SUM(cost_usd) DESC
"""

QUERY_BY_MODEL = """\
SELECT
    model,
    COUNT(*)            AS calls,
    SUM(input_tokens)   AS input_tokens,
    SUM(output_tokens)  AS output_tokens,
    SUM(cost_usd)       AS cost_usd
FROM cost_ledger
GROUP BY model
ORDER BY SUM(cost_usd) DESC
"""

QUERY_BY_AGENT_FILTERED = """\
SELECT
    agent,
    COUNT(*)            AS calls,
    SUM(input_tokens)   AS input_tokens,
    SUM(output_tokens)  AS output_tokens,
    SUM(cost_usd)       AS cost_usd
FROM cost_ledger
WHERE experiment = ?
GROUP BY agent
ORDER BY SUM(cost_usd) DESC
"""


def _load_cost_db_path() -> Path:
    """Load cost database path from application settings."""
    try:
        from multiagent.config.settings import Settings

        settings = Settings()  # type: ignore[call-arg]
        return settings.cost_db_path
    except Exception as exc:
        print(f"Cannot load settings: {exc}", file=sys.stderr)
        sys.exit(1)


def _render_table(
    console: Console,
    title: str,
    group_col: str,
    rows: list[sqlite3.Row],
) -> None:
    """Render a grouped cost table with a totals row."""
    table = Table(title=title)
    table.add_column(group_col, style="bold")
    table.add_column("Calls", justify="right")
    table.add_column("Input tokens", justify="right")
    table.add_column("Output tokens", justify="right")
    table.add_column("Cost USD", justify="right")

    total_calls = 0
    total_input = 0
    total_output = 0
    total_cost = 0.0

    for row in rows:
        calls = int(row["calls"])
        inp = int(row["input_tokens"])
        out = int(row["output_tokens"])
        cost = float(row["cost_usd"])
        total_calls += calls
        total_input += inp
        total_output += out
        total_cost += cost

        group_value = str(row[group_col.lower()]) or "(empty)"
        table.add_row(
            group_value,
            str(calls),
            str(inp),
            str(out),
            f"${cost:.4f}",
        )

    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{total_calls}[/bold]",
        f"[bold]{total_input}[/bold]",
        f"[bold]{total_output}[/bold]",
        f"[bold]${total_cost:.4f}[/bold]",
    )

    console.print(table)


def main() -> None:
    """Entry point for show_costs script."""
    parser = argparse.ArgumentParser(description="Analytical cost views.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--by-agent", action="store_true", help="Group by agent")
    group.add_argument("--by-model", action="store_true", help="Group by model")
    group.add_argument("--experiment", type=str, default=None, help="Filter to one experiment")
    args = parser.parse_args()

    cost_db_path = _load_cost_db_path()

    if not cost_db_path.exists():
        print("No cost data found.")
        sys.exit(0)

    conn = sqlite3.connect(str(cost_db_path))
    conn.row_factory = sqlite3.Row
    try:
        if args.experiment is not None:
            rows = conn.execute(QUERY_BY_AGENT_FILTERED, (args.experiment,)).fetchall()
            title = f"Cost by agent \u2014 experiment: {args.experiment}"
            group_col = "Agent"
        elif args.by_agent:
            rows = conn.execute(QUERY_BY_AGENT).fetchall()
            title = "Cost by agent"
            group_col = "Agent"
        elif args.by_model:
            rows = conn.execute(QUERY_BY_MODEL).fetchall()
            title = "Cost by model"
            group_col = "Model"
        else:
            rows = conn.execute(QUERY_BY_EXPERIMENT).fetchall()
            title = "Cost by experiment"
            group_col = "Experiment"
    finally:
        conn.close()

    if not rows:
        print("No cost data found.")
        sys.exit(0)

    console = Console()
    _render_table(console, title, group_col, rows)


if __name__ == "__main__":
    main()

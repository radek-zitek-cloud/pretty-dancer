"""Side-by-side comparison of two JSONL run files.

Usage: python scripts/compare_runs.py <log1> <log2>

Reads two per-run JSONL log files and displays a side-by-side comparison
of metadata, LLM calls, and timing information.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def _load_events(path: Path) -> list[dict[str, object]]:
    """Load events from a JSONL file.

    Args:
        path: Path to the JSONL file.

    Returns:
        List of parsed event dicts.
    """
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _run_summary(path: Path, events: list[dict[str, object]]) -> str:
    """Build a text summary of a run for panel display.

    Args:
        path: Path to the log file.
        events: Parsed events from the file.

    Returns:
        Formatted summary string.
    """
    if not events:
        return f"File: {path.name}\n(empty)"
    first_ts = str(events[0].get("timestamp", "?"))
    last_ts = str(events[-1].get("timestamp", "?"))
    agents = sorted({str(e.get("agent", "")) for e in events if e.get("agent")})
    experiment = str(events[0].get("experiment", "")) if events[0].get("experiment") else "(none)"
    return (
        f"File: {path.name}\n"
        f"Duration: {first_ts} → {last_ts}\n"
        f"Experiment: {experiment}\n"
        f"Agents: {', '.join(agents) if agents else '(none)'}\n"
        f"Events: {len(events)}"
    )


def main() -> None:
    """Entry point for compare_runs script."""
    parser = argparse.ArgumentParser(description="Compare two JSONL run log files side by side.")
    parser.add_argument("log1", help="Path to the first JSONL log file.")
    parser.add_argument("log2", help="Path to the second JSONL log file.")
    args = parser.parse_args()

    path1, path2 = Path(args.log1), Path(args.log2)
    errors = []
    if not path1.exists():
        errors.append(f"File not found: {path1}")
    if not path2.exists():
        errors.append(f"File not found: {path2}")
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        sys.exit(1)

    events1 = _load_events(path1)
    events2 = _load_events(path2)
    console = Console()

    # Section 1 — Header
    console.print(
        Columns(
            [
                Panel(_run_summary(path1, events1), title="Run 1", border_style="cyan"),
                Panel(_run_summary(path2, events2), title="Run 2", border_style="magenta"),
            ]
        )
    )
    console.print()

    # Section 2 — LLM call pairs
    traces1 = [e for e in events1 if e.get("event") == "llm_trace"]
    traces2 = [e for e in events2 if e.get("event") == "llm_trace"]

    if not traces1:
        console.print(f"[yellow]Warning: no llm_trace events in {path1.name}[/yellow]")
    if not traces2:
        console.print(f"[yellow]Warning: no llm_trace events in {path2.name}[/yellow]")

    max_calls = max(len(traces1), len(traces2))
    for i in range(max_calls):
        t1 = traces1[i] if i < len(traces1) else None
        t2 = traces2[i] if i < len(traces2) else None

        def _call_panel(trace: dict[str, object] | None, label: str) -> Panel:
            if trace is None:
                return Panel("[red][NO MATCH][/red]", title=label, border_style="red")
            prompt = str(trace.get("prompt", ""))
            response = str(trace.get("response", ""))
            agent = str(trace.get("agent", "?"))
            return Panel(
                f"Agent: {agent}\n\n"
                f"[bold]Prompt:[/bold]\n{prompt}\n\n"
                f"[bold]Response:[/bold]\n{response}",
                title=label,
                border_style="green",
            )

        # Show prompt comparison
        p1 = str(t1.get("prompt", "")) if t1 else ""
        p2 = str(t2.get("prompt", "")) if t2 else ""
        if p1 and p2 and p1 == p2:
            console.print(Panel(f"[bold]Shared prompt:[/bold]\n{p1}", border_style="green"))
        elif p1 and p2:
            console.print(
                Columns(
                    [
                        Panel(p1, title="Run 1 prompt", border_style="dark_orange"),
                        Panel(p2, title="Run 2 prompt", border_style="dark_orange"),
                    ]
                )
            )

        console.print(
            Columns(
                [
                    _call_panel(t1, f"Run 1 Call #{i + 1}"),
                    _call_panel(t2, f"Run 2 Call #{i + 1}"),
                ]
            )
        )
        console.print()

    # Section 3 — Timing
    agents_all = sorted(
        {str(e.get("agent", "")) for e in traces1 + traces2 if e.get("agent")}
    )
    if agents_all and (traces1 or traces2):
        timing_table = Table(title="Call Counts by Agent")
        timing_table.add_column("Agent", style="bold")
        timing_table.add_column("Run 1 calls", justify="right")
        timing_table.add_column("Run 2 calls", justify="right")
        for agent in agents_all:
            c1 = sum(1 for t in traces1 if str(t.get("agent")) == agent)
            c2 = sum(1 for t in traces2 if str(t.get("agent")) == agent)
            timing_table.add_row(agent, str(c1), str(c2))
        console.print(timing_table)


if __name__ == "__main__":
    main()

"""Parse a JSONL run file and display a structured experiment summary.

Usage: python scripts/show_run.py <log_file>

Reads a per-run JSONL log file and displays metadata, event summary,
LLM call details, and errors/retries in rich-formatted tables and panels.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def main() -> None:
    """Entry point for show_run script."""
    parser = argparse.ArgumentParser(description="Show a summary of a JSONL run log file.")
    parser.add_argument("log_file", help="Path to the JSONL log file.")
    args = parser.parse_args()

    log_path = Path(args.log_file)
    if not log_path.exists():
        print(f"File not found: {log_path}", file=sys.stderr)
        sys.exit(1)

    events: list[dict[str, object]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not events:
        print(f"No events found in: {log_path}", file=sys.stderr)
        sys.exit(1)

    console = Console()

    # Section 1 — Metadata
    first_ts = str(events[0].get("timestamp", "?"))
    last_ts = str(events[-1].get("timestamp", "?"))
    agents_seen = sorted({str(e.get("agent", "")) for e in events if e.get("agent")})
    experiment = str(events[0].get("experiment", "")) if events[0].get("experiment") else ""

    meta_table = Table(title="Run Metadata", show_header=False)
    meta_table.add_column("Key", style="bold")
    meta_table.add_column("Value")
    meta_table.add_row("File", str(log_path))
    meta_table.add_row("Start", first_ts)
    meta_table.add_row("End", last_ts)
    meta_table.add_row("Experiment", experiment or "(none)")
    meta_table.add_row("Agents", ", ".join(agents_seen) if agents_seen else "(none)")
    meta_table.add_row("Total events", str(len(events)))
    console.print(meta_table)
    console.print()

    # Section 2 — Event summary
    event_counter: Counter[str] = Counter()
    event_first: dict[str, str] = {}
    event_last: dict[str, str] = {}
    for e in events:
        name = str(e.get("event", "unknown"))
        event_counter[name] += 1
        ts = str(e.get("timestamp", ""))
        if name not in event_first:
            event_first[name] = ts
        event_last[name] = ts

    summary_table = Table(title="Event Summary")
    summary_table.add_column("Event", style="bold")
    summary_table.add_column("Count", justify="right")
    summary_table.add_column("First seen")
    summary_table.add_column("Last seen")
    for name, count in event_counter.most_common():
        summary_table.add_row(name, str(count), event_first[name], event_last[name])
    console.print(summary_table)
    console.print()

    # Section 3 — LLM calls
    trace_events = [e for e in events if e.get("event") == "llm_trace"]
    if trace_events:
        console.print("[bold]LLM Calls[/bold]")
        all_input_tokens: list[int | None] = []
        all_output_tokens: list[int | None] = []
        all_costs: list[float] = []
        for i, te in enumerate(trace_events, 1):
            agent = str(te.get("agent", "?"))
            ts = str(te.get("timestamp", "?"))
            input_chars = te.get("input_chars", "?")
            output_chars = te.get("output_chars", "?")
            input_tokens = te.get("input_tokens")
            output_tokens = te.get("output_tokens")
            cost_usd = te.get("cost_usd")
            all_input_tokens.append(input_tokens if isinstance(input_tokens, int) else None)
            all_output_tokens.append(output_tokens if isinstance(output_tokens, int) else None)
            all_costs.append(float(cost_usd) if isinstance(cost_usd, (int, float)) else 0.0)
            system_prompt = str(te.get("system_prompt", ""))[:200]
            prompt = str(te.get("prompt", ""))
            response = str(te.get("response", ""))

            cost_str = f"  |  Cost: ${all_costs[-1]:.4f}" if cost_usd is not None else ""
            token_info = (
                f"Input tokens: {input_tokens}  |  Output tokens: {output_tokens}"
                f"{cost_str}"
            )
            console.print(
                Panel(
                    f"Agent: {agent}  |  Time: {ts}\n"
                    f"Input chars: {input_chars}  |  Output chars: {output_chars}\n"
                    f"{token_info}\n\n"
                    f"[bold]System prompt:[/bold] {system_prompt}\n\n"
                    f"[bold]Prompt:[/bold]\n{prompt}\n\n"
                    f"[bold]Response:[/bold]\n{response}",
                    title=f"LLM Call #{i}",
                    border_style="green",
                )
            )

        if all(t is not None for t in all_input_tokens) and all(
            t is not None for t in all_output_tokens
        ):
            total_in = sum(t for t in all_input_tokens if t is not None)
            total_out = sum(t for t in all_output_tokens if t is not None)
            total_cost = sum(all_costs)
            console.print(
                f"Total: {len(trace_events)} LLM calls  |  "
                f"{total_in} input tokens  |  {total_out} output tokens  |  "
                f"Cost: ${total_cost:.4f}"
            )
        else:
            console.print("Token counts unavailable for one or more calls.")
    else:
        console.print(
            "No LLM trace events. Re-run with "
            "LOG_JSON_FILE_ENABLED=true LOG_TRACE_LLM=true."
        )
    console.print()

    # Section 4 — Errors and retries
    error_events = [
        e for e in events if str(e.get("level", "")).upper() in ("ERROR", "WARNING")
    ]
    if error_events:
        error_table = Table(title="Errors and Retries")
        error_table.add_column("Timestamp")
        error_table.add_column("Level", style="bold red")
        error_table.add_column("Agent")
        error_table.add_column("Message")
        for ee in error_events:
            error_table.add_row(
                str(ee.get("timestamp", "")),
                str(ee.get("level", "")),
                str(ee.get("agent", "")),
                str(ee.get("event", "")),
            )
        console.print(error_table)


if __name__ == "__main__":
    main()

# Task TUI — Platform Monitor

**File:** `tasks/tui-monitor.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-14  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 011a (multi-party messaging) complete and merged to master

---

## Objective

Replace the three-terminal experiment workflow with a single `just monitor`
command. The monitor is a live `textual`-based TUI that shows agent status,
message threads, cost, and provides an inline send panel — all in one terminal
window.

The existing scripts (`browse_threads.py`, `show_thread.py`, `show_costs.py`,
etc.) and CLI commands (`just chat`, `just listen`, `just send`) are preserved
unchanged. They remain useful as scriptable primitives and for Tom's debugging.
The TUI is the human experiment interface, not a replacement for the underlying
tools.

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — all standards, module rules, coding conventions
- `tasks/011a-multiparty-messaging.md` — `from_agent`/`to_agent` schema
- `tasks/009-cost-tracking.md` — `costs.db` schema for cost display
- Use **Context7** to look up the current Textual API before writing any
  Textual code — do not rely on training data for Textual widget APIs

---

## Git

Work on branch `feature/tui-monitor` created from `master`.

```bash
git checkout master
git pull origin master
git checkout -b feature/tui-monitor
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
feat(cli): add textual-based platform monitor (just monitor)
```

---

## New Dependency

```toml
# pyproject.toml — runtime dependency
"textual>=0.60"
```

`textual` is a runtime dependency, not dev-only. It is used in `cli/monitor.py`
which is part of the installed package. Add it to `[project.dependencies]` in
`pyproject.toml`.

Do not pin to an exact version — `>=0.60` is sufficient. Run `uv add textual`
to add it and update `uv.lock`.

---

## Layout

```
┌─ multiagent monitor ─────────────────── experiment: editorial-test ── $0.0087 ─┐
│                                                                                  │
│ ┌─ Agents ───────────────┐  ┌─ Thread ───────────────────────────────────────┐  │
│ │ ● editor    active     │  │ human    → editor   "Chemistry today"  16:00   │  │
│ │ ○ writer    idle       │  │ editor   → human    "Three angles..."  16:01   │  │
│ │ ○ linguist  idle       │  │ human    → editor   "Smells, 600w"     16:01   │  │
│ │                        │  │ editor   → human    "Excellent..."     16:01   │  │
│ │ Poll: 10s              │  │ human    → editor   "DIY sounds fun"   16:02   │  │
│ │ Threads: 3             │  │ editor   → writer   WRITER BRIEF...    16:02   │  │
│ └────────────────────────┘  │ writer   → linguist Molecular Lego...  16:02   │  │
│                              │ linguist → human    [polished] ●       16:02   │  │
│ ┌─ Threads ──────────────┐  └────────────────────────────────────────────────┘  │
│ │ ▶ 1427f464  $0.009  10 │                                                       │
│ │   6df159ed  $0.004   4 │  ┌─ Send ─────────────────────────────────────────┐  │
│ │   a1b2c3d4  $0.001   2 │  │ To: [editor          ] Thread: [1427f464      ]│  │
│ │                        │  │ > _                                             │  │
│ └────────────────────────┘  └────────────────────────────────────────────────┘  │
│                                                                                  │
│ [↑↓] select thread  [tab] focus send  [r] refresh  [q] quit   16:02:59         │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Panels

### Header bar

- App title: `multiagent monitor`
- Experiment label (from `Settings().experiment`, empty string hidden)
- Session total cost (sum of all `cost_ledger` rows since monitor started, or
  all-time if experiment filter is active)
- Updates on every poll cycle

### Agents panel (top left)

Shows every agent defined in `agents.toml`. For each agent:
- Status indicator: `●` (green) = active (has unprocessed messages in inbox),
  `○` (grey) = idle
- Agent name
- Status label: `active` / `idle`

Below the agent list:
- `Poll: {sqlite_poll_interval_seconds}s` — the cluster's poll interval from
  settings (informational)
- `Threads: {n}` — total distinct thread count in transport db

Agent status is determined by:
```sql
SELECT COUNT(*) FROM messages
WHERE to_agent = ? AND processed_at IS NULL
```
One query per agent per poll cycle.

### Threads panel (bottom left)

List of all threads ordered by most recent activity. For each thread:
- Selection indicator `▶` for the currently selected thread
- First 8 chars of thread UUID
- Total cost for this thread from `costs.db` (or `—` if no cost data)
- Message count

Keyboard: `↑` / `↓` to move selection. Enter or click to select and load in
the thread panel.

Threads panel scrolls if thread count exceeds panel height.

### Thread panel (right, main)

Shows the full message chain for the selected thread. For each message:
- `{from_agent} → {to_agent}` in muted colour
- Message body — truncated to first 80 chars if long, with `...`
- Timestamp as `HH:MM:SS`
- Unprocessed messages (no `processed_at`) shown with `●` indicator

Scrollable. Auto-scrolls to bottom when a new message arrives on the selected
thread. Does not auto-scroll if the user has manually scrolled up.

### Send panel (bottom right)

Two input fields and a message input:
- `To:` — agent name, pre-filled with the `from_agent` of the last message
  addressed to `human` in the selected thread (i.e. auto-reply target)
- `Thread:` — UUID, pre-filled with the selected thread's ID
- Message input line: `> _`

Tab moves focus between `To:`, `Thread:`, and message input.
Enter in the message input sends the message and clears the input.

Sending uses `SQLiteTransport.send()` — same as `just send`, not a direct SQL
insert. This ensures `from_agent = "human"` and a valid UUID `thread_id`.

### Footer bar

Keyboard hint line: `[↑↓] select thread  [tab] focus send  [r] refresh  [q] quit`

Last update timestamp on the right.

---

## Polling

The TUI polls on a fixed 2-second interval, independent of the cluster's
`sqlite_poll_interval_seconds`. The cluster poll interval is a concern of the
agents, not the monitor. 2 seconds gives responsive updates without hammering
the database.

Polling uses `asyncio` scheduled callbacks via Textual's `set_interval()`.
On each tick:
- Refresh agent status (one query per agent)
- Refresh thread list
- If a thread is selected, refresh the thread panel
- Update header cost total

---

## Database Access

The monitor reads from two databases:
- `settings.sqlite_db_path` — messages, agent status
- `settings.cost_db_path` — cost per thread

Both paths come from `Settings()`. The monitor opens its own read connections —
it does not share connections with the transport or cost ledger used by the
cluster.

Cost data may not exist (`costs.db` absent or empty) — show `—` gracefully.
The monitor must never crash on missing cost data.

`TerminalTransport` is not supported — the monitor is SQLite-only. If
`settings.transport_backend != "sqlite"`, print an error and exit 1 before
launching the TUI.

---

## New Files

### `src/multiagent/cli/monitor.py`

The Textual app and all widget classes. Single file — do not split into multiple
modules for this initial implementation.

Structure:

```python
class AgentsPanel(Widget): ...
class ThreadsPanel(Widget): ...
class ThreadPanel(Widget): ...
class SendPanel(Widget): ...
class MonitorApp(App): ...

def monitor_command(
    experiment: str = typer.Option("", "--experiment", "-e"),
    thread_id: str = typer.Option("", "--thread-id", "-t"),
) -> None:
    """Launch the platform monitor TUI."""
```

`monitor_command` is a synchronous typer command that calls
`MonitorApp(...).run()`. Textual manages its own event loop internally — do not
wrap in `asyncio.run()`.

### Registration in `src/multiagent/cli/main.py`

```python
from multiagent.cli.monitor import monitor_command
app.command(name="monitor")(monitor_command)
```

### `justfile` addition

```makefile
# Launch the platform monitor
monitor experiment="" thread_id="":
    uv run multiagent monitor \
        {{if experiment != "" { "--experiment " + experiment } else { "" }}} \
        {{if thread_id != "" { "--thread-id " + thread_id } else { "" }}}
```

Add in the Application section.

---

## Command Flags

```
just monitor                                  # all threads
just monitor editorial-test                   # filter to experiment
just monitor "" 1427f464-4b15-432f-b00d-...   # open on specific thread
```

`--experiment` filters the thread list to threads where any message has
`experiment = ?` in `costs.db`. If `costs.db` is absent, no filtering — show
all threads.

`--thread-id` pre-selects a thread on launch and loads it in the thread panel.

---

## Module Boundary

`cli/monitor.py` may import from `config/`, `transport/`, `exceptions`.
It must not import from `core/` — the monitor does not instantiate agents,
runners, or cost ledgers. It reads the databases directly via `aiosqlite`
for display purposes.

`textual` is imported only in `cli/monitor.py`. Never in `core/` or
`transport/`.

---

## Test Requirements

The TUI is not unit-testable in the conventional sense — Textual's rendering
requires a terminal. The test scope is therefore limited:

### `tests/unit/cli/test_monitor.py` — New File

```
TestMonitorCommand
    test_exits_nonzero_when_transport_not_sqlite
        — settings.transport_backend = "terminal"
        — assert monitor_command exits 1 with error message

    test_exits_nonzero_when_agents_db_missing
        — settings.sqlite_db_path points to nonexistent file
        — assert monitor_command exits 1 with error message
```

Both tests use `subprocess.run` with env overrides, same pattern as script
tests. No Textual rendering in tests.

The full interactive behaviour (panel updates, keyboard navigation, send) is
validated via manual smoke test only.

---

## Manual Smoke Test

```bash
# Terminal 1 — start the cluster
just start --experiment monitor-test

# Terminal 2 — launch the monitor
just monitor monitor-test

# In the monitor:
# 1. Verify all agents appear in the Agents panel (idle initially)
# 2. Send a message using the inline Send panel to editor
# 3. Observe: editor status changes to active, then idle
# 4. Observe: new messages appear in Thread panel as agents process
# 5. Navigate threads with ↑↓
# 6. Verify cost updates in header and Threads panel
# 7. Press q to quit — exits cleanly, no traceback
```

---

## Implementation Order

1. Add `textual>=0.60` via `uv add textual`
2. Create `src/multiagent/cli/monitor.py` — scaffold `MonitorApp` with empty
   panels, verify it launches without error
3. Implement `AgentsPanel` — static list first, then live polling
4. Implement `ThreadsPanel` — thread list with selection
5. Implement `ThreadPanel` — message display for selected thread
6. Implement `SendPanel` — input fields and send action
7. Wire all panels together — selection in `ThreadsPanel` loads `ThreadPanel`,
   `SendPanel` pre-fills from selection
8. Implement polling loop — `set_interval(2, self._refresh)`
9. Register command in `main.py`, add justfile target
10. Write `tests/unit/cli/test_monitor.py` (2 tests)
11. `just check && just test`
12. Manual smoke test

---

## Acceptance Criteria

```bash
just check    # zero ruff errors, zero pyright errors
just test     # all tests pass (previous total + 2 new)
```

Manual:
- `just monitor` launches without error when `agents.db` exists
- All agents from `agents.toml` appear in the Agents panel
- Thread list populates and is navigable with keyboard
- Selecting a thread loads the full message chain
- New messages appear in the thread panel without manual refresh
- Agent status reflects actual inbox state (active when messages pending)
- Inline send delivers a message to the cluster (verify via `just thread`)
- Cost figures appear in header and thread list (or `—` gracefully)
- `q` exits cleanly
- `just monitor` fails cleanly with an error message if `transport_backend`
  is not `sqlite`

---

## What This Task Does NOT Include

- Log output panel — use the JSONL log files for that
- Agent restart or control from the monitor
- Multiple simultaneous thread views
- Mouse click support for thread selection (keyboard only for initial version)
- Export or save from the monitor
- Web UI — explicitly out of scope
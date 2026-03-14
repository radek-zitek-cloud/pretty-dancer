# Plan: Task TUI — Platform Monitor

**Task:** `tasks/TUI-monitor.md`
**Author:** Tom (implementer)
**Date:** 2026-03-14
**Status:** APPROVED — implementing

**Architect review note:** The feedback referenced checkpoint compatibility and
RunResult extraction — these belong to the 011b routing review, not TUI monitor.
The TUI plan itself was approved without changes. Proceeding as planned.

**Textual version:** `uv add textual` resolved to `textual==8.1.1`. The brief
specified `>=0.60` which reflects Textual's old versioning. The API is stable.
**Base branch:** `master` @ `ae2c9b2`
**Feature branch:** `feature/tui-monitor`

---

## Design Decisions and Ambiguities

### 1. Module boundary — monitor reads databases directly

The brief says `cli/monitor.py` must not import from `core/`. It reads databases
directly via `aiosqlite` for display. This is correct — the monitor is a read-only
observer, not a participant in the agent pipeline.

The monitor imports from:
- `config/` — `load_settings`, `load_agents_config` (for agent names)
- `transport/` — `SQLiteTransport` (for send panel only)
- `aiosqlite` — direct read queries for display panels
- `textual` — TUI framework

It does **not** import from `core/` (no LLMAgent, AgentRunner, CostLedger).

### 2. Send panel uses SQLiteTransport, not raw SQL

The brief specifies: "Sending uses `SQLiteTransport.send()` — same as `just send`."
This means the monitor must instantiate a `SQLiteTransport` for the send panel.
I'll create it in `on_mount` and close it in `on_unmount`. The transport's
`send()` handles `from_agent`, timestamps, and schema correctly.

### 3. Cost queries — direct aiosqlite to costs.db

The monitor reads from two separate databases (`agents.db` and `costs.db`).
The `SQLiteTransport` instance handles `agents.db`. For `costs.db`, I'll open
a separate `aiosqlite` connection. If `costs.db` doesn't exist, all cost
displays show `—`.

### 4. Experiment filtering

`--experiment` filters threads by joining against `costs.db`. If costs.db is
absent, the filter is silently ignored — all threads shown. This matches the
brief: "If `costs.db` is absent, no filtering — show all threads."

### 5. Textual app architecture

Single file `cli/monitor.py` as specified. I'll use Textual's built-in
`Header`, `Footer`, and `Static`/`Widget` classes for the panels. CSS layout
uses grid with two columns. Polling via `set_interval(2, self._refresh)` in
`on_mount`.

Key Textual patterns:
- `compose()` yields the widget tree
- `on_mount()` starts the polling timer and opens DB connections
- `set_interval(2, callback)` for periodic refresh
- `BINDINGS` for keyboard shortcuts
- `Input` widget for the send panel fields
- `ListView`/`ListItem` or custom `Static` widgets for thread list

### 6. No `rich` dependency issue

The brief's layout uses `rich`-style formatting. `textual` includes `rich` as
a dependency, so `Rich` renderables can be used inside Textual widgets. No
additional dependency needed.

### 7. Textual version constraint

The brief says `>=0.60`. Current Textual is at 0.x / 1.x range. I'll use
`uv add textual` which will resolve to the latest compatible version and let
`uv.lock` pin it.

---

## Files to Create or Modify

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Modify | Add `textual>=0.60` to runtime dependencies |
| `uv.lock` | Auto-updated | Via `uv add textual` |
| `src/multiagent/cli/monitor.py` | Create | Textual TUI app with all panels |
| `src/multiagent/cli/main.py` | Modify | Register `monitor_command` |
| `justfile` | Modify | Add `monitor` target in Application section |
| `tests/unit/cli/test_monitor.py` | Create | 2 guard-rail tests |

---

## Implementation Order

### Step 1: Add textual dependency
**Command:** `uv add textual`
**Rationale:** Foundation — everything else imports textual.

Gate: `just check && just test` — verify no regressions from dependency change.

### Step 2: Scaffold MonitorApp
**File:** `src/multiagent/cli/monitor.py`

Create the file with:
- `monitor_command()` typer entry point with `--experiment` and `--thread-id`
- Guard: exit 1 if `transport_backend != "sqlite"`
- Guard: exit 1 if `sqlite_db_path` doesn't exist
- `MonitorApp` class with empty `compose()`, `BINDINGS` for `q` quit
- Verify it launches and exits cleanly

### Step 3: CSS layout and panel scaffolds
Define the four-panel grid layout using Textual CSS:
- Left column: AgentsPanel (top), ThreadsPanel (bottom)
- Right column: ThreadPanel (top, main), SendPanel (bottom)
- Header and Footer docked

Each panel is a `Widget` subclass with placeholder content initially.

### Step 4: Implement AgentsPanel
- Load agent names from `load_agents_config()`
- On each poll: query `SELECT COUNT(*) FROM messages WHERE to_agent = ? AND processed_at IS NULL` per agent
- Display `●`/`○` status with agent name
- Show poll interval and thread count below

### Step 5: Implement ThreadsPanel
- Query all distinct thread_ids with message count, ordered by most recent
- Left-join to costs.db for per-thread cost (graceful `—` if absent)
- `ListView` with selectable items
- `↑`/`↓` keyboard navigation
- Highlight selected thread with `▶`
- Post a custom message when selection changes

### Step 6: Implement ThreadPanel
- On thread selection: query all messages for the thread
- Display `from_agent → to_agent`, truncated body (80 chars), HH:MM:SS timestamp
- Unprocessed messages get `●` indicator
- Auto-scroll to bottom on new messages (respect manual scroll position)

### Step 7: Implement SendPanel
- `Input` widgets for To, Thread, and message body
- Pre-fill To from last `to_agent="human"` message's `from_agent`
- Pre-fill Thread from selected thread
- On Enter in message input: call `SQLiteTransport.send()`, clear input
- `from_agent="human"` always

### Step 8: Wire polling
- `on_mount()`: open aiosqlite connections, create SQLiteTransport for send
- `set_interval(2, self._refresh)` to update all panels
- `on_unmount()`: close connections
- Header: show experiment label and total cost

### Step 9: Register command and justfile
**Files:** `main.py`, `justfile`
- Add `from multiagent.cli.monitor import monitor_command` to main.py
- Add `monitor` target to justfile Application section

### Step 10: Tests
**File:** `tests/unit/cli/test_monitor.py`

Two tests using subprocess:
1. `test_exits_nonzero_when_transport_not_sqlite` — set `TRANSPORT_BACKEND=terminal` in env
2. `test_exits_nonzero_when_agents_db_missing` — set `SQLITE_DB_PATH` to nonexistent path

### Step 11: Gate and smoke test
`just check && just test`
Manual smoke test per the brief.

---

## Test Plan

| Test class | Test name | What it verifies |
|------------|-----------|------------------|
| `TestMonitorCommand` | `test_exits_nonzero_when_transport_not_sqlite` | Guard: terminal backend rejected |
| | `test_exits_nonzero_when_agents_db_missing` | Guard: missing DB rejected |

Total: 2 new tests. (TUI interaction tested manually only.)

---

## Key SQL Queries

### Agent status (per agent, per poll)
```sql
SELECT COUNT(*) FROM messages
WHERE to_agent = ? AND processed_at IS NULL
```

### Thread list (all threads, ordered by recency)
```sql
SELECT thread_id, COUNT(*) as msg_count, MAX(created_at) as last_activity
FROM messages
GROUP BY thread_id
ORDER BY last_activity DESC
```

### Thread cost (from costs.db)
```sql
SELECT thread_id, SUM(cost_usd) as total_cost
FROM cost_ledger
GROUP BY thread_id
```

### Total session cost (header)
```sql
SELECT SUM(cost_usd) FROM cost_ledger
```
With optional `WHERE experiment = ?` filter.

### Thread messages (for selected thread)
```sql
SELECT from_agent, to_agent, body, created_at, processed_at
FROM messages
WHERE thread_id = ?
ORDER BY created_at ASC
```

### Experiment filter (threads with cost data for experiment)
```sql
SELECT DISTINCT thread_id FROM cost_ledger WHERE experiment = ?
```

---

## What I Would Do Differently From the Brief

### 1. Test approach — mock-based instead of subprocess for guard tests

The brief suggests subprocess with env overrides. However, the existing CLI tests
(test_start.py, test_chat.py) use mock-based testing with `patch()`. I'll follow
the same pattern the codebase already uses for CLI command tests — it's faster
and doesn't require spawning processes. The subprocess pattern is used for
*scripts*, not CLI commands.

**Update:** On re-reading, the brief explicitly says "Both tests use
`subprocess.run` with env overrides, same pattern as script tests." I'll follow
the brief and use subprocess, since `monitor_command` would try to launch the
Textual app which is hard to interrupt gracefully in a mock context.

### 2. `rich` in runtime dependencies

`rich` is currently in dev dependencies only (`[project.optional-dependencies].dev`),
but the implementation guide says it's a runtime dependency used in CLI and scripts.
Since `textual` already depends on `rich`, adding `textual` to runtime deps
effectively makes `rich` available at runtime too. I won't move `rich` explicitly
— that's a separate concern.

### 3. Mouse click support

The brief says "Mouse click support for thread selection (keyboard only for
initial version)." However, Textual's `ListView` gives mouse click selection
for free — I won't actively disable it. It's zero effort and improves UX.

# Implementation Plan — Task 008: `multiagent start`

**Implementer:** Tom (Claude Code)
**Date:** 2026-03-14
**Task brief:** `tasks/008-start.md`
**Status:** DRAFT — awaiting architect review

---

## 1. Files to Create or Modify

| File | Action | Description |
|------|--------|-------------|
| `src/multiagent/cli/start.py` | **Create** | `start_command()` sync wrapper + `_start()` async impl using `asyncio.TaskGroup` |
| `src/multiagent/cli/main.py` | **Modify** | Import and register `start_command` (one import + one `app.command()` call) |
| `tests/unit/cli/__init__.py` | No change | Already exists |
| `tests/unit/cli/test_start.py` | **Create** | 4 unit tests per brief spec |
| `justfile` | **Modify** | Add `start` target in the Application section |

---

## 2. Implementation Order

### Step 1: Add `start` target to `justfile`
**Rationale:** Zero-risk change, gives us the convenience command immediately.

Add after the `send` target:

```makefile
# Start all agents defined in agents.toml concurrently
start experiment="":
    uv run multiagent start {{if experiment != "" { "--experiment " + experiment } else { "" }}}
```

### Step 2: Create `tests/unit/cli/test_start.py` — TDD red phase
**Rationale:** Write tests first per the TDD approach specified in the brief. All 4 tests should fail initially.

Tests to implement:

1. **`test_starts_all_agents_from_config`** — Mock `AgentRunner.run_loop` (returns immediately via `AsyncMock`), mock `load_settings`, `load_agents_config`, `configure_logging`, `create_transport`, `AsyncSqliteSaver`. Assert `run_loop` called once per agent (2 agents in fixture config). Use `typer.testing.CliRunner` to invoke `app` with `["start"]`.

2. **`test_exits_cleanly_when_no_agents_configured`** — Mock `load_agents_config` to return empty dict. Assert no `TaskGroup` created, exit code 0, error message printed.

3. **`test_logs_cluster_starting_with_agent_names`** — Capture structlog output or mock `structlog.get_logger()`. Assert `cluster_starting` event contains all agent names.

4. **`test_keyboard_interrupt_exits_zero`** — Patch `asyncio.run` to raise `KeyboardInterrupt`. Assert `SystemExit(0)` via `pytest.raises`.

**Mock strategy:** Follow the pattern from `test_send.py`:
- Patch `multiagent.cli.start.load_settings`
- Patch `multiagent.cli.start.load_agents_config`
- Patch `multiagent.cli.start.configure_logging` (return `(None, None)`)
- Patch `multiagent.cli.start.create_transport` (return `AsyncMock`)
- Patch `multiagent.cli.start.AsyncSqliteSaver` — mock the async context manager
- Patch `multiagent.cli.start.LLMAgent` — return a mock that AgentRunner can accept
- Patch `multiagent.cli.start.AgentRunner` — mock `run_loop` to return immediately

### Step 3: Create `src/multiagent/cli/start.py`
**Rationale:** Core deliverable. Structure follows the `run.py` pattern closely.

**Key implementation details:**

- `start_command()` — sync wrapper, mirrors `run_command()` pattern:
  - `typer.Option` for `--experiment/-e`
  - `try: asyncio.run(_start(experiment))` / `except KeyboardInterrupt: print + sys.exit(0)`

- `_start(experiment)` — async implementation:
  1. `load_settings()`
  2. `configure_logging(settings, agent_name="cluster", experiment=experiment)`
  3. Print log file paths
  4. `load_agents_config(settings.agents_config_path)`
  5. Validate non-empty — if empty, print error and `return`
  6. Log `cluster_starting` with agent names
  7. `create_transport(settings)`
  8. `mkdir` for checkpointer db parent
  9. `async with AsyncSqliteSaver.from_conn_string(...)` as checkpointer
  10. `async with asyncio.TaskGroup() as tg:` — create task per agent
  11. `except* CancelledError: pass`
  12. `except* Exception as eg:` — log each, re-raise
  13. After TaskGroup exits: log `cluster_stopped`

**Windows event loop policy:** Handled in `main.py`'s `main()` already — it applies `WindowsSelectorEventLoopPolicy` before calling `app()`. No need to duplicate in `start_command()`.

### Step 4: Register in `src/multiagent/cli/main.py`
**Rationale:** One import + one line. Minimal change.

```python
from multiagent.cli.start import start_command
app.command(name="start")(start_command)
```

### Step 5: TDD green phase — run tests
Run `just check && just test` — all 4 new tests should pass alongside existing tests.

### Step 6: Manual smoke test
Per the brief's smoke test procedure.

---

## 3. Design Decisions and Ambiguities

### 3.1 Windows event loop policy — NOT duplicated in `start_command()`

The task brief shows `asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())` inside `start_command()`. However, `main.py:main()` already applies this policy before `app()` is called (line 30-33). Duplicating it in `start_command()` is redundant.

**Decision:** Do not duplicate. The existing `main()` handles this for all commands.

### 3.2 `agents.toml` uses `alfa`/`beta`, not `researcher`/`critic`

The real `agents.toml` has `alfa` and `beta` agents. The task brief's smoke test references `progressive` and `conservative`. The test fixture has `researcher` and `critic`.

**Decision:** Tests use `tests/fixtures/agents.toml` (researcher/critic). The smoke test will use whatever is in the real `agents.toml` (currently alfa/beta). No changes to config files needed.

### 3.3 `except*` syntax — Python 3.11+

The brief uses `except* asyncio.CancelledError` and `except* Exception`. This requires Python 3.11+. The project uses Python 3.12 per `pyproject.toml`, so this is fine.

**Decision:** Use `except*` as specified. No compatibility concern.

### 3.4 Shared `LLMAgent` and `AgentRunner` construction

Each agent in the TaskGroup needs its own `LLMAgent` and `AgentRunner` instance. The brief constructs `LLMAgent(name, settings, checkpointer)` — all agents share the same checkpointer, which is correct (different threads keep them independent).

**Decision:** Follow the brief exactly. One shared `AsyncSqliteSaver`, one shared transport, distinct `LLMAgent` + `AgentRunner` per agent name.

### 3.5 Log shutdown `cluster_stopped` placement

The brief says: "This must appear after the `async with asyncio.TaskGroup()` block exits, not inside the exception handler."

**Decision:** Place `log.info("cluster_stopped", ...)` after the entire try/except* block but still inside the `async with AsyncSqliteSaver` block (so the checkpointer is still valid when logging). Actually — logging doesn't need the checkpointer, so it can also go after. I'll place it after the TaskGroup try/except* block, inside the checkpointer context manager, as this is the most natural position and ensures all resources are still valid.

### 3.6 Test for `test_keyboard_interrupt_exits_zero`

The brief says: "asyncio.run raises KeyboardInterrupt — assert sys.exit(0) is called". Using `typer.testing.CliRunner` won't easily capture `sys.exit(0)` from a `KeyboardInterrupt` because the CliRunner catches exceptions.

**Decision:** Test this by directly calling `start_command()` with `asyncio.run` patched to raise `KeyboardInterrupt`, and catching `SystemExit` with `pytest.raises(SystemExit, match="0")`. Alternatively, use the CliRunner and check exit_code == 0 — I'll determine the best approach during implementation.

---

## 4. Anything I Would Do Differently

### 4.1 Nothing major — the brief is tight

The brief is well-specified and closely mirrors existing patterns (`run.py`). I see no architectural issues, module boundary violations, or unnecessary complexity.

### 4.2 Minor: `stderr` output for "Cluster stopped."

The brief has `print("\nCluster stopped.", file=sys.stderr)`. I'll follow this exactly. Worth noting that `run.py` uses structlog for its shutdown message, not `print`. I'll follow the brief's pattern for `start_command` since it's the outer sync wrapper, but use structlog inside `_start()` as specified.

---

## 5. Module Boundary Verification

`cli/start.py` will import from:
- `multiagent.config` (`load_settings`)
- `multiagent.config.agents` (`load_agents_config`)
- `multiagent.core.agent` (`LLMAgent`)
- `multiagent.core.runner` (`AgentRunner`)
- `multiagent.logging` (`configure_logging`)
- `multiagent.transport` (`create_transport`)
- `langgraph.checkpoint.sqlite.aio` (`AsyncSqliteSaver`)

All permitted. No `core/` or `transport/` module imports `cli/`.

---

## 6. Checklist Before Implementation

- [x] Master is clean
- [x] Read `implementation-guide.md`
- [x] Read `008-start.md`
- [x] Read `004-cli-wiring.md` (run.py pattern)
- [x] Read `006-checkpointer.md` (AsyncSqliteSaver lifecycle)
- [x] Inspected `cli/main.py`, `cli/run.py`, `cli/send.py`
- [x] Inspected `core/agent.py`, `core/runner.py`
- [x] Inspected `tests/conftest.py`, `tests/unit/cli/test_send.py`
- [x] Inspected `justfile`, `agents.toml`, `tests/fixtures/agents.toml`
- [ ] Plan reviewed and approved by architect

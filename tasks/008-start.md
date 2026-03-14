# Task 008 — `multiagent start`

**File:** `tasks/008-start.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-14  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 007 (`send --thread-id`) complete and merged to master

---

## Objective

Add a `multiagent start` CLI command that reads `agents.toml` and starts all
configured agents concurrently inside a single Python process. When complete,
the full researcher → critic pipeline or a circular debate can be launched with
one command in one terminal instead of coordinating N shells.

This replaces the manual multi-terminal workflow for all normal development and
experiment use. Cross-platform by design — no shell scripts, no subprocesses,
pure asyncio.

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — all standards, module rules, coding conventions
- `tasks/004-cli-wiring.md` — `run.py` pattern this task mirrors
- `tasks/006-checkpointer.md` — checkpointer lifecycle (`async with AsyncSqliteSaver`)
- `tasks/007-send-thread-id.md` — current state of `send.py` and `main.py`

---

## Git

Work on branch `feature/start-command` created from `master`.

```bash
git checkout master
git pull origin master
git worktree add ../multiagent-start-command feature/start-command
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
feat(cli): add multiagent start command to run all agents concurrently
```

Tag: none.

---

## Design: Single Process, `asyncio.TaskGroup`

All agents run as concurrent coroutines inside one Python process. They share
one `SQLiteTransport` instance and one `AsyncSqliteSaver` checkpointer.

**Why not subprocesses:** The transport is designed for shared use — `SQLiteTransport`
with WAL mode handles concurrent access. One process means one Ctrl-C cancels
everything cleanly via `asyncio.TaskGroup` structured concurrency, no zombie
processes, no cross-platform pipe management, no output multiplexing. Trivially
portable to Windows.

**Trade-off acknowledged:** A single process crash takes all agents down. Acceptable
at PoC scale. Subprocess-per-agent is the natural next step if process isolation
becomes a requirement.

---

## Deliverables

### Source Files

```
src/multiagent/cli/start.py           # start_command() implementation
src/multiagent/cli/main.py            # register start command (one line addition)
```

### Test Files

```
tests/unit/cli/__init__.py            # create if absent
tests/unit/cli/test_start.py          # unit tests
```

### `justfile` addition

```makefile
# Start all agents defined in agents.toml concurrently
start experiment="":
    uv run multiagent start {{if experiment != "" { "--experiment " + experiment } else { "" }}}
```

Add in the Application section, after the existing `run` and `send` targets.

---

## `src/multiagent/cli/start.py`

### Command Signature

```python
def start_command(
    experiment: str = typer.Option(
        "",
        "--experiment", "-e",
        help="Experiment label included in run log filenames.",
    ),
) -> None:
    """Start all agents defined in agents.toml concurrently.

    Reads agents.toml, constructs one transport and one checkpointer
    shared across all agents, and runs every agent's polling loop
    concurrently in a single asyncio.TaskGroup. All agents stop cleanly
    on Ctrl-C.

    Args:
        experiment: Optional experiment label for log filenames.
    """
```

`start_command` is a synchronous wrapper that calls `asyncio.run(_start(experiment))`,
following the same pattern as `run_command` in `run.py`. The Windows event loop
policy is applied here too:

```python
def start_command(...) -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_start(experiment))
```

### `_start()` — Async Implementation

```python
async def _start(experiment: str) -> None:
    """Load config, construct shared resources, and run all agents."""
```

**Implementation steps in order:**

1. `settings = load_settings()`
2. `human_log, json_log = configure_logging(settings, agent_name="cluster", experiment=experiment)`
3. Print active log file paths to stdout (same pattern as `run.py`)
4. `agent_configs = load_agents_config(settings.agents_config_path)`
5. Validate: if `agent_configs` is empty, print an error and return — no agents
   to run is not a crash condition but it must be reported clearly
6. Log `cluster_starting` at INFO with the list of agent names
7. `transport = create_transport(settings)`
8. Resolve checkpointer db directory: `settings.checkpointer_db_path.parent.mkdir(parents=True, exist_ok=True)`
9. Open checkpointer: `async with AsyncSqliteSaver.from_conn_string(str(settings.checkpointer_db_path)) as checkpointer:`
10. Inside the `async with` block, run all agents via `asyncio.TaskGroup`

### `asyncio.TaskGroup` pattern

```python
try:
    async with asyncio.TaskGroup() as tg:
        for name, config in agent_configs.items():
            agent = LLMAgent(name, settings, checkpointer)
            runner = AgentRunner(
                agent, transport, settings, next_agent=config.next_agent
            )
            log.info("agent_starting", agent=name, next_agent=config.next_agent)
            tg.create_task(runner.run_loop(), name=name)
    # TaskGroup exits when all tasks complete — only happens if run_loop() returns,
    # which it does not under normal operation. Normal exit is via CancelledError.
except* asyncio.CancelledError:
    pass  # clean shutdown — all tasks cancelled together
except* Exception as eg:
    for exc in eg.exceptions:
        log.error("agent_task_failed", error=str(exc))
    raise
```

**Exception group handling:** `asyncio.TaskGroup` uses Python 3.11+ exception
groups (`except*`). When one task raises an unhandled exception, `TaskGroup`
cancels all remaining tasks and re-raises as an `ExceptionGroup`. The `except*`
clauses handle this correctly. `CancelledError` (from Ctrl-C) is absorbed —
this is the expected shutdown path.

### `KeyboardInterrupt` handling

`KeyboardInterrupt` is caught at the `asyncio.run()` level in `start_command()`,
not inside `_start()`. The pattern mirrors `run.py`:

```python
def start_command(...) -> None:
    ...
    try:
        asyncio.run(_start(experiment))
    except KeyboardInterrupt:
        print("\nCluster stopped.", file=sys.stderr)
        sys.exit(0)
```

### Shutdown log

After the `TaskGroup` exits (whether via cancellation or exception), log:

```python
log.info("cluster_stopped", agents=list(agent_configs.keys()))
```

This must appear after the `async with asyncio.TaskGroup()` block exits, not
inside the exception handler — it should fire regardless of exit cause.

---

## `src/multiagent/cli/main.py` — Registration

Add one import and one `app.command()` registration, following the existing
pattern for `run_command` and `send_command`. No other changes.

---

## Logging Behaviour

`configure_logging(settings, agent_name="cluster", experiment=experiment)` produces:

```
logs/2026-03-14T10-22-05_cluster.log
logs/2026-03-14T10-22-05_cluster.jsonl
```

Each individual `AgentRunner` logger already binds `agent=<name>` via structlog
context. In the shared process, log lines from different agents are distinguishable
by this field. Console output is interleaved but readable — structlog's
`ConsoleRenderer` includes the logger name.

No separate per-agent log files in `start` mode. The cluster produces one pair
of files containing all agents' output. If per-agent isolation is needed, the
`run` command in separate terminals remains available.

---

## Test Requirements

### `tests/unit/cli/test_start.py`

Mock strategy: `AsyncMock` for `AgentRunner.run_loop()` — it must return
immediately (not loop) so the `TaskGroup` completes. Transport and LLM are
mocked following the existing patterns in `test_runner.py`.

```
TestStartCommand
    test_starts_all_agents_from_config
        — mock run_loop returns immediately for each agent
        — assert run_loop was called once per agent in agents.toml
        — assert call count equals len(agent_configs)

    test_exits_cleanly_when_no_agents_configured
        — agents.toml fixture with empty [agents] section (or missing section)
        — assert no TaskGroup is created, no exception raised

    test_logs_cluster_starting_with_agent_names
        — assert cluster_starting log event contains all agent names
        — mock structlog or capture log output

    test_keyboard_interrupt_exits_zero
        — asyncio.run raises KeyboardInterrupt
        — assert sys.exit(0) is called (use pytest raises SystemExit)
```

**Fixture note:** Use the existing `test_settings` fixture from `conftest.py`.
The `tests/fixtures/agents.toml` already defines `researcher` and `critic` —
reuse it. No new fixture files needed.

---

## `__init__.py` — No changes

`start_command` is not exported from any `__init__.py`. CLI commands are
registered directly in `main.py` and are not part of any public API.

---

## Module Boundary Verification

`cli/start.py` may import from `core/`, `transport/`, `config/`, `logging/`.
It must not be imported by anything in `core/` or `transport/`.

```bash
grep -r "from multiagent.cli" src/multiagent/core/    # must return nothing
grep -r "from multiagent.cli" src/multiagent/transport/  # must return nothing
```

---

## Implementation Order

1. Add `threads` justfile target from 005-CR2 if not yet present (confirm with Tom)
2. Add `start` target to `justfile`
3. Create `tests/unit/cli/__init__.py` if absent
4. **Write `tests/unit/cli/test_start.py`** — TDD red phase (4 tests fail)
5. Create `src/multiagent/cli/start.py` — full implementation
6. Register `start_command` in `src/multiagent/cli/main.py`
7. **TDD green phase** — all 4 tests pass
8. Run `just check && just test`
9. Manual smoke test (see below)

---

## Manual Smoke Test

```bash
# Start the full debate in one command
just start --experiment debate-test

# In a second terminal, inject the opening message
just send progressive "Should AI systems be given legal personhood? Open the debate."

# Observe: both progressive and conservative agents process messages
# in the single terminal running `just start`
# Ctrl-C stops all agents cleanly

# Verify the cluster log files were created
just runs
# logs/2026-03-14T10-22-05_cluster_debate-test.log
# logs/2026-03-14T10-22-05_cluster_debate-test.jsonl
```

Verify in the log output:
- `cluster_starting` event lists both agent names
- Each message_received log line shows distinct `agent=` values
- `cluster_stopped` event appears after Ctrl-C
- No `agent_task_failed` events

---

## Acceptance Criteria

```bash
just check    # zero ruff errors, zero pyright errors
just test     # all unit tests pass (previous total + 4 new)
```

Manual:
- `uv run multiagent --help` lists `start` as a command
- `uv run multiagent start --help` shows `--experiment` option
- `just start` launches all agents from `agents.toml` in one terminal
- Ctrl-C exits cleanly with exit code 0, no traceback
- Log files produced with `cluster` agent name in filename

---

## What This Task Does NOT Include

- Per-agent log files in `start` mode — single cluster log only
- Subprocess-per-agent isolation
- Dynamic agent reload without restart
- `--agents` flag to start a subset — all agents from `agents.toml` always
- Health checks or agent restart on failure
- Stdin message injection from within `start` — use `send` in a separate terminal
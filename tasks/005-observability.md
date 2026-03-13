# Task 005 — Observability

**File:** `tasks/005-observability.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-13  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 004 CLI wiring complete and merged to master

---

## Objective

Add three independent, fully configurable output streams to the logging system,
per-run experiment file isolation, LLM trace capture, and developer inspection
tooling. When complete:

- Console output, a human-readable `.log` file, and a JSONL `.jsonl` file are each
  independently toggled, independently level-filtered, and independently configured
- Every pipeline run can produce a self-contained, context-window-friendly JSONL
  file suitable for agent-based analysis and a paired human-readable log for review
- Three `rich`-formatted scripts make thread inspection and experiment comparison
  fast from the terminal

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — all standards, module rules, coding conventions
- `tasks/004-cli-wiring.md` — what the CLI layer provides

---

## Git

Work on branch `feature/observability` created from `master`.

```bash
git checkout master
git pull origin master
git worktree add ../multiagent-observability feature/observability
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
feat(logging): add three-stream logging, per-run files, LLM trace, and inspection scripts
```

Tag: none.

---

## Deliverables

### Source Files

```
src/multiagent/logging/setup.py       # rewrite: three-stream output, per-run files
src/multiagent/cli/run.py             # modify: add --experiment flag
src/multiagent/core/agent.py          # modify: store settings, add llm_trace emit
```

### Scripts

```
scripts/show_thread.py                # rich-formatted conversation thread from SQLite
scripts/show_run.py                   # rich-formatted summary of a single JSONL run file
scripts/compare_runs.py               # side-by-side rich comparison of two run files
```

### Test Files

```
tests/unit/config/test_settings.py    # extend: 8 new observability settings tests
tests/unit/scripts/__init__.py
tests/unit/scripts/test_show_thread.py
tests/unit/scripts/test_show_run.py
tests/unit/scripts/test_compare_runs.py
```

---

## Configuration Additions

### `src/multiagent/config/settings.py`

**Remove** existing `log_level` and `log_format` fields — they are superseded.
**Add** the full three-stream configuration:

```python
# Observability — console stream
log_console_enabled: bool = Field(
    True,
    description="Emit log events to stdout. Disable to suppress all console output.",
)
log_console_level: str = Field(
    "INFO",
    pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    description="Minimum log level for console output.",
)

# Observability — human-readable log file stream (.log)
log_human_file_enabled: bool = Field(
    False,
    description="Write a per-run human-readable log file alongside console output.",
)
log_human_file_level: str = Field(
    "INFO",
    pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    description="Minimum log level for the human-readable log file.",
)

# Observability — JSON Lines log file stream (.jsonl)
log_json_file_enabled: bool = Field(
    False,
    description="Write a per-run JSONL log file. Intended for agent-based analysis.",
)
log_json_file_level: str = Field(
    "DEBUG",
    pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    description="Minimum log level for the JSONL log file. Defaults to DEBUG to "
                "capture maximum detail for experiment analysis.",
)

# Observability — shared
log_dir: Path = Field(
    Path("logs"),
    description="Directory for per-run log files. Both .log and .jsonl land here.",
)
log_trace_llm: bool = Field(
    False,
    description="Include full LLM prompt and response content in the JSONL log file. "
                "Never emitted to console or human-readable file. "
                "Only effective when log_json_file_enabled=True.",
)
experiment: str = Field(
    "",
    description="Optional experiment label included in log filenames. "
                "Override per-run with the --experiment CLI flag.",
)
```

### `.env.defaults`

Replace the existing `# --- LOGGING ---` section entirely:

```bash
# --- OBSERVABILITY ---
# Console stream
LOG_CONSOLE_ENABLED=true
LOG_CONSOLE_LEVEL=INFO

# Human-readable log file (.log) — disabled by default
LOG_HUMAN_FILE_ENABLED=false
LOG_HUMAN_FILE_LEVEL=INFO

# JSON Lines log file (.jsonl) — disabled by default
LOG_JSON_FILE_ENABLED=false
LOG_JSON_FILE_LEVEL=DEBUG

# Shared
LOG_DIR=logs
LOG_TRACE_LLM=false           # JSONL file only — console and .log never receive trace events
# EXPERIMENT=                  # optional label in filenames; override with --experiment flag
```

### `.env.test`

Replace existing `LOG_LEVEL` and `LOG_FORMAT` entries:

```bash
LOG_CONSOLE_ENABLED=true
LOG_CONSOLE_LEVEL=WARNING
LOG_HUMAN_FILE_ENABLED=false
LOG_JSON_FILE_ENABLED=false
LOG_TRACE_LLM=false
```

### `pyproject.toml`

Add `rich>=13.0` to dev dependencies:

```toml
[dependency-groups]
dev = [
    ...
    "rich>=13.0",
]
```

`rich` must **never** be imported anywhere under `src/multiagent/`. It is a
scripts-only dependency. If `rich` appears in any source file, that is a violation.

### `justfile`

Replace the existing application and database sections in full:

```makefile
# ── Application ────────────────────────────────────────────────────────────

# Run a named agent (polls for messages until interrupted)
run agent experiment="":
    uv run multiagent run {{agent}} {{if experiment != "" { "--experiment " + experiment } else { "" }}}

# Inject a message into the transport for a named agent
send agent body:
    uv run multiagent send {{agent}} "{{body}}"

# ── Database ───────────────────────────────────────────────────────────────

# Show last N messages across all agents (default 20)
db-tail n="20":
    sqlite3 data/agents.db "SELECT id, from_agent, to_agent, substr(body,1,60) as body, processed_at FROM messages ORDER BY created_at DESC LIMIT {{n}};"

# Show all pending (unprocessed) messages by agent
db-pending:
    sqlite3 data/agents.db "SELECT to_agent, count(*) as pending FROM messages WHERE processed_at IS NULL GROUP BY to_agent;"

# Show per-agent message counts and last activity
db-agents:
    sqlite3 data/agents.db "SELECT to_agent, count(*) as total, sum(processed_at IS NOT NULL) as done, max(created_at) as last_seen FROM messages GROUP BY to_agent;"

# Clear all messages from the transport database
db-clear:
    sqlite3 data/agents.db "DELETE FROM messages;"

# ── Inspection scripts ──────────────────────────────────────────────────────

# Show a conversation thread from SQLite, formatted with rich
thread thread_id:
    uv run python scripts/show_thread.py {{thread_id}}

# Show a summary of a single run log file
run-summary log_file:
    uv run python scripts/show_run.py {{log_file}}

# Compare two run log files side by side
compare log1 log2:
    uv run python scripts/compare_runs.py {{log1}} {{log2}}

# List all run log files
runs:
    @ls -lt logs/*.jsonl 2>/dev/null || echo "No run logs found in logs/"
```

---

## Logging Architecture

### Three Streams

Each stream is an independent stdlib `logging.Handler` attached to the root logger.
All three share the structlog processor chain up to the renderer. Each handler has
its own level set via `handler.setLevel()`.

| Stream | Toggle | Level setting | Renderer | `llm_trace` events |
|---|---|---|---|---|
| Console | `log_console_enabled` | `log_console_level` | `ConsoleRenderer(colors=True)` | Suppressed |
| Human file `.log` | `log_human_file_enabled` | `log_human_file_level` | `ConsoleRenderer(colors=False)` | Suppressed |
| JSON file `.jsonl` | `log_json_file_enabled` | `log_json_file_level` | `JSONRenderer()` | Passed through |

**Critical:** The root logger level must always be set to `DEBUG`. Individual
handler levels control what each stream actually emits. Setting the root logger to
anything higher silently drops events before they reach the handlers.

### `_SuppressLLMTrace` Filter

```python
class _SuppressLLMTrace(logging.Filter):
    """Drop llm_trace events from console and human-readable file handlers.

    llm_trace events contain full prompt and response content and are
    intended for JSONL file analysis only. They must never appear in
    real-time console output or human-readable log files.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return "llm_trace" not in record.getMessage()
```

Applied to: console handler, human file handler.
Not applied to: JSON file handler.

### Per-Run File Naming

Both file types share a timestamp prefix and optional experiment label:

```
logs/2026-03-13T14-32-01.log
logs/2026-03-13T14-32-01.jsonl
logs/2026-03-13T15-01-44_prompt-v2.log
logs/2026-03-13T15-01-44_prompt-v2.jsonl
```

- Timestamp: ISO8601, colons replaced with hyphens for filesystem compatibility
- Experiment label: appended after `_`, spaces replaced with hyphens
- `log_dir` created with `mkdir(parents=True, exist_ok=True)` if absent
- Files are immutable after process exit — never appended to across runs

Effective experiment label resolution order:
1. `experiment` argument to `configure_logging()` — CLI `--experiment` flag
2. `settings.experiment` — env var or `.env`
3. Empty string — timestamp-only filename

### `configure_logging()` — Full Specification

```python
def configure_logging(
    settings: Settings,
    experiment: str = "",
) -> tuple[Path | None, Path | None]:
    """Configure structlog with up to three independent output streams.

    Attaches up to three stdlib logging handlers based on settings:
      - Console handler: ConsoleRenderer (colours) to stdout
      - Human file handler: ConsoleRenderer (no colours) to per-run .log
      - JSON file handler: JSONRenderer to per-run .jsonl

    Each handler has its own level. llm_trace events are suppressed from
    console and human file via _SuppressLLMTrace. Root logger is always
    set to DEBUG — handler levels control actual output.

    Must be called once at process startup. Call from CLI entry points only.

    Args:
        settings: Validated application settings.
        experiment: Experiment label from CLI flag. Overrides settings.experiment
            when non-empty.

    Returns:
        Tuple of (human_log_path, json_log_path). Either is None if that
        stream is disabled.

    Raises:
        OSError: If log_dir cannot be created.
    """
```

---

## `src/multiagent/cli/run.py` Changes

Add `--experiment` option:

```python
async def run_command(
    agent_name: str = typer.Argument(..., help="Name of the agent to run."),
    experiment: str = typer.Option(
        "",
        "--experiment", "-e",
        help="Experiment label included in run log filenames.",
    ),
) -> None:
```

Pass to `configure_logging()` and print active file paths:

```python
human_log, json_log = configure_logging(settings, experiment=experiment)
if human_log:
    typer.echo(f"Human log : {human_log}")
if json_log:
    typer.echo(f"JSON log  : {json_log}")
```

The `send` command does not receive `--experiment` — it is a one-shot message
injection, not a run, and produces no log files.

---

## `src/multiagent/core/agent.py` Changes

Store `settings` on the instance and emit `llm_trace` conditionally:

```python
def __init__(self, name: str, settings: Settings) -> None:
    ...
    self._settings = settings   # stored for log_trace_llm check in graph
    self._graph = self._build_graph()
```

Inside `call_llm` in `_build_graph()`, after `output` is assigned:

```python
if self._settings.log_trace_llm:
    self._log.info(
        "llm_trace",
        prompt=state["input"],
        system_prompt=self._system_prompt,
        response=output,
        input_chars=len(state["input"]),
        output_chars=len(output),
    )
```

No new imports required. `LLMAgent` already receives `settings` in `__init__`.

---

## Inspection Scripts

All scripts in `scripts/` at repo root. Each:
- Uses only stdlib (`sqlite3`, `json`, `pathlib`, `sys`, `argparse`) plus `rich`
- Is never imported by `src/multiagent/`
- Exits 0 on success, 1 on error
- Has a module docstring with purpose and usage

### `scripts/show_thread.py`

**Purpose:** Display one complete conversation thread from SQLite.

**Usage:** `just thread <thread_id>`

**Output (rich):**
- Header `Panel`: thread_id, message count, timestamp range
- One `Panel` per message, border colour by `from_agent`:
  - `human` → blue, `researcher` → green, `critic` → yellow, unknown → white
- Panel title: `[from_agent] → [to_agent]  |  {created_at}  |  id={id}`
- Panel body: full `msg.body`, word-wrapped to terminal width
- Status line per message: `processed_at` value or `[PENDING]` in red

Database path from `Settings().sqlite_db_path`.

### `scripts/show_run.py`

**Purpose:** Parse a JSONL run file and display a structured experiment summary.

**Usage:** `just run-summary <log_file>`

**Output (rich):**

**Section 1 — Metadata** (`Table`, 2 columns):
file path, start time, duration, experiment label, agents observed

**Section 2 — Event summary** (`Table`):
one row per distinct event name — count, first seen, last seen; sorted by count desc

**Section 3 — LLM calls** (only if `llm_trace` events present):
one `Panel` per call — agent, timestamp, char counts, system prompt (truncated to
200 chars), full prompt, full response

**Section 4 — Errors and retries** (only if ERROR/WARNING events present):
`Table` with timestamp, level, agent, message

If no `llm_trace` events:
print `"No LLM trace events. Re-run with LOG_JSON_FILE_ENABLED=true LOG_TRACE_LLM=true."`

### `scripts/compare_runs.py`

**Purpose:** Side-by-side comparison of two JSONL run files.

**Usage:** `just compare <log1> <log2>`

**Output (rich):**

**Section 1 — Header** (`Columns`, two panels):
each panel: filename, duration, experiment label, agent(s), event count

**Section 2 — LLM call pairs** (one row of two panels per paired call):
calls paired by position; unpaired shown with `[NO MATCH]` in red on opposite side;
prompt shown once if identical, side-by-side in amber if different;
responses side-by-side in two panels

**Section 3 — Timing** (`Table`):
agent | run1 call count | run1 avg duration | run2 call count | run2 avg duration

If either file has no `llm_trace` events, print a warning naming the file.

---

## Test Requirements

### Settings unit tests — extend `tests/unit/config/test_settings.py`

```
TestObservabilitySettings
    test_log_console_enabled_defaults_to_true
    test_log_console_level_defaults_to_info
    test_log_human_file_enabled_defaults_to_false
    test_log_human_file_level_defaults_to_info
    test_log_json_file_enabled_defaults_to_false
    test_log_json_file_level_defaults_to_debug
    test_log_trace_llm_defaults_to_false
    test_experiment_defaults_to_empty_string
```

### Script smoke tests — subprocess only, no rich internals imported

```
tests/unit/scripts/test_show_thread.py
    test_exits_nonzero_with_no_args
    test_exits_nonzero_with_nonexistent_thread_id
    test_exits_nonzero_with_missing_database

tests/unit/scripts/test_show_run.py
    test_exits_nonzero_with_no_args
    test_exits_nonzero_with_nonexistent_file

tests/unit/scripts/test_compare_runs.py
    test_exits_nonzero_with_no_args
    test_exits_nonzero_with_one_arg_only
    test_exits_nonzero_with_nonexistent_files
```

All script tests use `subprocess.run` and assert on return code and/or stderr
content. They do not import script modules directly.

---

## Implementation Order

1. Remove `log_level`, `log_format` from `Settings`; add all new observability fields
2. Update `.env.defaults` — replace logging section
3. Update `.env.test` — replace logging entries
4. Add `rich>=13.0` to dev dependencies → `uv sync`
5. Update `test_settings` fixture in `tests/conftest.py` — remove old fields, add new ones
6. Run `just check && just test` — confirm no regressions from settings change
7. Add `TestObservabilitySettings` (8 tests) — verify all pass
8. Rewrite `src/multiagent/logging/setup.py`:
   - `_SuppressLLMTrace` filter
   - `configure_logging()` returning `tuple[Path | None, Path | None]`
   - Per-run filename construction
   - Console handler (conditional, level-filtered, filtered)
   - Human file handler (conditional, level-filtered, filtered)
   - JSON file handler (conditional, level-filtered, unfiltered)
   - Root logger set to `DEBUG`
9. Modify `src/multiagent/cli/run.py` — `--experiment` flag, updated `configure_logging()` call
10. Modify `src/multiagent/core/agent.py` — `self._settings`, `llm_trace` emit
11. Update `justfile`
12. Run `just check && just test` — all tests pass
13. Create `scripts/show_thread.py`
14. Create `scripts/show_run.py`
15. Create `scripts/compare_runs.py`
16. Create `tests/unit/scripts/__init__.py`
17. Create script smoke tests (8 tests across 3 files)
18. Run `just check && just test` — all tests pass
19. Manual end-to-end verification (see below)

---

## Manual End-to-End Verification

```bash
# Run with all three streams enabled and trace on
LOG_CONSOLE_ENABLED=true \
LOG_HUMAN_FILE_ENABLED=true \
LOG_JSON_FILE_ENABLED=true \
LOG_TRACE_LLM=true \
just run researcher --experiment baseline
# In second terminal:
just send researcher "What is quantum entanglement?"
# Ctrl-C after processing

just runs                                              # lists .log and .jsonl pair
just run-summary logs/<timestamp>_baseline.jsonl       # LLM trace panels visible
cat logs/<timestamp>_baseline.log                      # human readable, no trace events

# Verify llm_trace never reaches console
LOG_TRACE_LLM=true just run researcher 2>&1 | grep llm_trace   # must return nothing

# Verify independent levels
LOG_CONSOLE_LEVEL=ERROR LOG_JSON_FILE_LEVEL=DEBUG just run researcher
# Console shows ERROR only; JSONL contains DEBUG events

# Experiment comparison
LOG_JSON_FILE_ENABLED=true LOG_TRACE_LLM=true \
just run researcher --experiment v2
just send researcher "What is quantum entanglement? One sentence only."
just compare logs/<baseline>.jsonl logs/<v2>.jsonl

# Verify no rich import in src/
grep -r "import rich" src/   # must return nothing
```

---

## Acceptance Criteria

```bash
just check    # zero ruff errors, zero pyright errors
just test     # all unit tests pass (previous total + 8 settings + 8 script = 16 new)
```

Manual gates:
- All three streams independently toggled — confirmed
- All three streams independently level-filtered — confirmed
- `llm_trace` absent from console and `.log`, present in `.jsonl` — confirmed
- `--experiment` flag changes both `.log` and `.jsonl` filenames — confirmed
- `just runs`, `just run-summary`, `just compare` all work — confirmed
- `grep -r "import rich" src/` returns nothing — confirmed

---

## What This Task Does NOT Include

- Log shipping or centralised aggregation
- Metrics or counters
- `TerminalTransport` log file support
- Automated experiment tracking database
- HTML report generation
- Log rotation — one file per run, rotation not needed at PoC scale
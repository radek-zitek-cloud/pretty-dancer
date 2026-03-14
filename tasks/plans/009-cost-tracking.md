# Plan: Task 009 — Cost Tracking

**Task brief:** `tasks/009-cost-tracking.md`
**Plan author:** Tom (implementer)
**Date:** 2026-03-14
**Status:** IMPLEMENTED

---

## Files to Create or Modify

| File | Action | Description |
|------|--------|-------------|
| `src/multiagent/config/settings.py` | **Modify** | Add `cost_db_path: Path` field with default `data/costs.db` |
| `src/multiagent/core/costs.py` | **Create** | `CostEntry` dataclass + `CostLedger` async context manager |
| `src/multiagent/core/agent.py` | **Modify** | Accept `cost_ledger` param, extract pricing from `response_metadata`, enrich `llm_usage` log event, write `CostEntry` |
| `src/multiagent/cli/run.py` | **Modify** | Add `CostLedger` lifecycle (async with), pass to `LLMAgent` |
| `src/multiagent/cli/start.py` | **Modify** | Add shared `CostLedger` lifecycle, pass to each `LLMAgent` |
| `scripts/browse_threads.py` | **Modify** | Query `costs.db` for per-thread cost, add `Cost` column to table |
| `scripts/show_thread.py` | **Modify** | Append per-agent cost summary footer table after message chain |
| `scripts/show_run.py` | **Modify** | Add `cost_usd` column to LLM calls section, add cost to totals |
| `scripts/compare_runs.py` | **Modify** | Add `Total cost` column to call counts table |
| `scripts/show_costs.py` | **Create** | Analytical cost views (by experiment/agent/model) with argparse + rich |
| `justfile` | **Modify** | Add `costs`, `costs-by-agent`, `costs-by-model` targets in Inspection section |
| `tests/unit/core/test_costs.py` | **Create** | 4 tests for CostLedger (record, failure, mkdir, idempotent schema) |
| `tests/unit/core/test_agent.py` | **Modify** | 3 new tests (cost recorded, failure tolerant, zero when pricing absent) |
| `tests/conftest.py` | **Modify** | Add `cost_db_path` to `test_settings` fixture |
| `tests/unit/scripts/test_show_costs.py` | **Create** | 5 tests for show_costs.py script |
| `tasks/005-CR3.md` | **Create** | CR: remove `--db` flag from `show_thread.py` |

---

## Implementation Order

### Phase 1 — Core data layer (no behavioural changes)

**Step 1: Settings field**
- Add `cost_db_path: Path = Field(Path("data/costs.db"), ...)` to `Settings`
- Add `cost_db_path=Path(":memory:"),` to `test_settings` fixture in `tests/conftest.py`
- Rationale: Unlocks all downstream code. Must come first because `CostLedger` receives the path from settings, and tests need the fixture updated before any CostLedger tests run.

**Step 2: `core/costs.py` — CostEntry + CostLedger**
- Create `CostEntry` frozen dataclass with all 11 fields per the brief
- Create `CostLedger` async context manager:
  - `__aenter__`: mkdir parents, open aiosqlite connection, run `_init_schema`
  - `__aexit__`: close connection
  - `_init_schema`: CREATE TABLE IF NOT EXISTS
  - `record(entry)`: INSERT wrapped in try/except, log WARNING on failure, never raise
- No imports from `config/`, `transport/`, or `cli/` — receives `db_path: Path` directly

**Step 3: `tests/unit/core/test_costs.py`**
- Write all 4 tests from the brief (TDD red → green)
- Tests use `tmp_path` for real SQLite files — no mocking the database
- Verify: `just test` passes

### Phase 2 — Agent integration

**Step 4: Modify `agent.py`**
- Add `cost_ledger: CostLedger` parameter to `__init__`, store as `self._cost_ledger`
- In `call_llm` node, after existing `usage_metadata` extraction:
  - Extract `input_unit_price` and `output_unit_price` from `response.response_metadata` with `.get(..., 0.0)` defaults
  - Compute `cost_usd = input_tokens * input_unit_price + output_tokens * output_unit_price`
  - Enrich existing `llm_usage` log event with `cost_usd`, `input_unit_price`, `output_unit_price`
  - Build `CostEntry` and `await self._cost_ledger.record(entry)`
- The `call_llm` node needs access to `config: RunnableConfig` to get `thread_id`. LangGraph passes config as a keyword argument to nodes — the signature becomes `async def call_llm(state: MessagesState, config: RunnableConfig) -> MessagesState`

**Step 5: Update agent tests**
- Update `mock_llm` fixture in `conftest.py` to include `response_metadata` and `usage_metadata` on the mocked `AIMessage`
- Add 3 new tests to `test_agent.py`:
  - `test_cost_entry_recorded_on_llm_call` — mock `CostLedger.record`, assert called with correct values
  - `test_cost_recording_failure_does_not_fail_agent` — mock `record` to raise, assert agent completes
  - `test_zero_cost_when_pricing_absent` — mock response without pricing metadata, assert `cost_usd == 0.0`
- All existing agent tests must be updated: `LLMAgent(name, settings, checkpointer)` → `LLMAgent(name, settings, checkpointer, cost_ledger)`
- Verify: `just test` passes

### Phase 3 — CLI lifecycle

**Step 6: Modify `cli/run.py` and `cli/start.py`**
- Import `CostLedger` from `multiagent.core.costs`
- In `run.py._run()`: nest `async with CostLedger(settings.cost_db_path)` inside the checkpointer block, pass to `LLMAgent`
- In `start.py._start()`: same pattern, single shared `CostLedger` across all agents
- Resource nesting order: transport → checkpointer → cost ledger (innermost)
- Verify: existing CLI tests still pass (they mock at the LLM level, so CostLedger lifecycle is exercised)

### Phase 4 — Inspection scripts

**Step 7: Modify `browse_threads.py`**
- After loading thread rows from `agents.db`, open `costs.db` (via `Settings().cost_db_path`) as a second synchronous connection
- Query `SELECT thread_id, SUM(cost_usd) AS total_cost FROM cost_ledger GROUP BY thread_id`
- Build `dict[str, float]` lookup; handle missing db file or empty table gracefully (default `0.0`)
- Add `Cost` column after `Processed` in the table, format as `$0.0000` or `—` when no data

**Step 8: Modify `show_thread.py`**
- After rendering message panels, query `costs.db` for the thread's cost breakdown by agent
- Render as `rich.table.Table` with columns: Agent, Calls, Input tokens, Output tokens, Total tokens, Cost USD
- Add totals row; format cost as `$0.0000`
- If no cost rows exist for the thread, omit the footer entirely

**Step 9: Modify `show_run.py`**
- In the LLM calls section (llm_trace events), add `cost_usd` from each event's data
- Add cost to the token_info line: `Cost: $0.0000`
- Include cost in the cumulative totals line

**Step 10: Modify `compare_runs.py`**
- In the call counts table, add a `Total cost` column
- Sum `cost_usd` from llm_trace events per run
- Format as `$0.0000`

**Step 11: Create `scripts/show_costs.py`**
- Argparse with mutually exclusive flags: `--by-agent`, `--by-model`, `--experiment LABEL`
- Load `cost_db_path` from `Settings()`
- Execute the appropriate GROUP BY query per the brief
- Render with rich.table.Table, include totals row
- Empty ledger → print "No cost data found." and exit 0

**Step 12: `tests/unit/scripts/test_show_costs.py`**
- 5 tests per the brief, using `subprocess.run` with a tmp_path SQLite db
- Override settings via env var or direct path arg

### Phase 5 — Justfile + final verification

**Step 13: Justfile targets**
- Add `costs`, `costs-by-agent`, `costs-by-model` in the Inspection scripts section

**Step 14: Full verification**
- `just check` — zero lint/pyright errors
- `just test` — all tests pass

---

## Design Decisions and Ambiguity Resolutions

### 1. `call_llm` node signature and `config` access

The current `call_llm` is a closure inside `_build_graph` with signature `async def call_llm(state: MessagesState)`. To access `thread_id`, the brief says to accept `config: RunnableConfig`. LangGraph passes `config` as a keyword argument to nodes when the function signature includes it. I'll update the signature to:

```python
async def call_llm(state: MessagesState, config: RunnableConfig) -> MessagesState:
```

And extract the thread_id with:
```python
thread_id = config["configurable"]["thread_id"]
```

This is a well-documented LangGraph pattern and requires no graph-level changes.

### 2. `experiment` field on CostEntry

The brief shows `experiment: str = ""` on `CostEntry` and `experiment=self._settings.experiment` when constructing the entry. The agent already has `self._settings` so this is straightforward. However, the CLI's `--experiment` flag overrides `settings.experiment` only via the logging system currently — it doesn't persist to `Settings.experiment`. Looking at the code:

- In `run.py`, experiment is passed to `configure_logging()` but not back to settings
- In `start.py`, same pattern

**Resolution (approved by architect):** In `_run()` and `_start()`, after `settings = load_settings()`, set `settings.experiment = experiment` if `experiment` is non-empty. This ensures the CostEntry gets the correct experiment label regardless of whether it was set via env var or CLI flag.

**Mutation safety verified:** `Settings.model_config` uses `SettingsConfigDict(extra="forbid")` but does **not** set `frozen=True`. Pydantic BaseSettings instances are mutable by default. Direct field assignment works at runtime and pyright will not complain. If this ever changes to frozen, the fallback is passing `experiment` as a direct parameter to `LLMAgent`.

### 3. `show_thread.py` — accessing cost_db_path

The brief says to query `costs.db` from `Settings().cost_db_path`. The `show_thread.py` script already uses `Settings()` for the transport db path. I'll add a second `Settings()` call (or reuse the same one) to get `cost_db_path` and open a second synchronous sqlite3 connection.

Since `costs.db` may not exist for old runs, I'll wrap the cost query in a try/except and gracefully default to no data.

### 4. `browse_threads.py` — the `_load_db_path` pattern

This script currently has `_load_db_path()` that returns `settings.sqlite_db_path`. I'll add a similar `_load_cost_db_path()` or just extend the existing function to return both paths. Simpler: load `Settings()` once in `main()` and pass both paths where needed.

### 5. `test_show_costs.py` — how to pass db path

The brief suggests using `COST_DB_PATH` env override with `subprocess.run`. Since `Settings` reads from env vars, setting `COST_DB_PATH=<tmp_path>/costs.db` in the subprocess environment will override the default. I also need to set `OPENROUTER_API_KEY` and `GREETING_SECRET` (required fields) in the test environment to avoid validation errors.

### 6. `mock_llm` fixture update

The current fixture creates `AIMessage(content=mock_llm_response)`. AIMessage supports `response_metadata` and `usage_metadata` as fields. I'll update it to:

```python
AIMessage(
    content=mock_llm_response,
    usage_metadata={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
    response_metadata={
        "input_unit_price": 0.000003,
        "output_unit_price": 0.000015,
    },
)
```

This affects all existing tests, but since they don't assert on these fields, it's backward-compatible.

### 7. CostLedger as a required vs optional parameter on LLMAgent

The brief shows it as a required parameter. This means all existing call sites (tests, run.py, start.py) must pass it. For tests, I'll create a fixture that provides a no-op or in-memory CostLedger. Since CostLedger is an async context manager and tests create agents synchronously, I'll use a `mock_cost_ledger` fixture with `AsyncMock(spec=CostLedger)` where `record` is an `AsyncMock`.

---

## Things I Would Do Differently (with justification)

### 1. `test_exits_nonzero_with_missing_database` — BRIEF CORRECTION

The brief lists `test_exits_nonzero_with_missing_database` expecting nonzero exit. This is incorrect per architect review: a missing `costs.db` is not an error — it means cost tracking has never run. The correct behaviour is exit 0 with "No cost data found.", identical to an empty table. The test will assert exit 0 and the "No cost data found." message.

### 2. `show_thread.py` `--db` flag — logged as CR

`show_thread.py` has a `--db` flag that violates the implementation guide ("No `--db` flag on scripts — always read from Settings()"). Out of scope for task 009 but logged as `tasks/005-CR3.md` for future cleanup.

### 3. `datetime.utcnow()` deprecation

The brief uses `datetime.utcnow().isoformat()` for the timestamp. This is deprecated in Python 3.12+ in favour of `datetime.now(UTC).isoformat()`. I'll use `datetime.now(datetime.UTC)` instead.

---

## Module Boundary Verification Checklist

After implementation, these must all return empty:
```bash
grep -r "from multiagent.cli"       src/multiagent/core/
grep -r "from multiagent.transport" src/multiagent/core/
grep -r "from multiagent.config"    src/multiagent/core/costs.py
```

---

## Risk Areas (resolved during implementation)

1. **LangGraph `config` in node signature** — Verified: LangGraph passes `config: RunnableConfig` as a keyword argument to nodes when the function signature includes it. Works correctly.
2. **`AIMessage` metadata fields** — Verified: `response_metadata` and `usage_metadata` are real fields on AIMessage. Setting them in fixtures works correctly.
3. **Existing test breakage** — Handled via `mock_cost_ledger` fixture in `tests/conftest.py`. All 16 agent tests updated to pass the new parameter.
4. **Double-layer cost recording protection** — The brief specified try/except in `CostLedger.record()`, but when the mock raises directly (bypassing CostLedger internals), the exception propagated through the LangGraph node. Added a second try/except around the `record()` call in `agent.py` to ensure cost failures never degrade the LLM pipeline regardless of the failure source.

# Task 009 — Cost Tracking

**File:** `tasks/009-cost-tracking.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-14  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 008 (`multiagent start`) complete and merged to master

---

## Objective

Record the cost of every LLM call to a persistent SQLite ledger and surface that
cost through the existing inspection workflow. After this task:

- Every LLM call writes a row to `data/costs.db` with token counts, unit prices,
  and computed cost in USD
- `browse_threads.py` shows cumulative cost per thread in the thread list
- `show_thread.py` appends a per-agent cost summary footer to every thread view
- `show_run.py` gains a cost column and total cost row
- `compare_runs.py` gains a total cost column
- `scripts/show_costs.py` provides analytical cross-run views by experiment,
  agent, and model

The primary workflow is: `just threads` → select thread → see full conversation
plus cost breakdown in one view. No separate cost command needed for normal use.

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — all standards, module rules, coding conventions
- `tasks/008-start.md` — `CostLedger` lifecycle pattern mirrors checkpointer
- `tasks/006-checkpointer.md` — `AsyncSqliteSaver` lifecycle this task mirrors
- `tasks/005-CR2.md` — `browse_threads.py` this task modifies
- `tasks/006-CR1.md` — `llm_usage` event this task enriches

---

## Git

Work on branch `feature/cost-tracking` created from `master`.

```bash
git checkout master
git pull origin master
git worktree add ../multiagent-cost-tracking feature/cost-tracking
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
feat(core): add cost ledger and surface cost through inspection scripts
```

---

## New Settings Field

```python
cost_db_path: Path    # data/costs.db
```

Add to `src/multiagent/config/settings.py`. Default: `data/costs.db`. The file
is created on first run — no manual setup required.

---

## `src/multiagent/core/costs.py` — New File

### `CostEntry` dataclass

```python
@dataclass
class CostEntry:
    timestamp:         str
    thread_id:         str
    agent:             str
    model:             str
    input_tokens:      int
    output_tokens:     int
    total_tokens:      int
    input_unit_price:  float
    output_unit_price: float
    cost_usd:          float
    experiment:        str = ""
```

### `CostLedger` class

Async context manager owning the aiosqlite connection and schema initialisation.

```python
class CostLedger:
    def __init__(self, db_path: Path) -> None: ...

    async def __aenter__(self) -> "CostLedger": ...
    async def __aexit__(self, *args: object) -> None: ...

    async def _init_schema(self) -> None: ...
    async def record(self, entry: CostEntry) -> None: ...
```

**Schema initialised in `_init_schema`:**

```sql
CREATE TABLE IF NOT EXISTS cost_ledger (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT    NOT NULL,
    thread_id         TEXT    NOT NULL,
    agent             TEXT    NOT NULL,
    model             TEXT    NOT NULL,
    input_tokens      INTEGER NOT NULL,
    output_tokens     INTEGER NOT NULL,
    total_tokens      INTEGER NOT NULL,
    input_unit_price  REAL    NOT NULL,
    output_unit_price REAL    NOT NULL,
    cost_usd          REAL    NOT NULL,
    experiment        TEXT    NOT NULL DEFAULT ''
)
```

**`record()` failure mode:** wrap the aiosqlite write in `try/except`. On failure
log a structlog WARNING with `error=str(exc)` and return — never raise. Cost
tracking must not degrade or fail the LLM pipeline.

**`mkdir`:** `db_path.parent.mkdir(parents=True, exist_ok=True)` in `__aenter__`
before opening the connection.

---

## `src/multiagent/core/agent.py` — Modifications

### Constructor

```python
def __init__(
    self,
    name: str,
    settings: Settings,
    checkpointer: BaseCheckpointSaver,
    cost_ledger: CostLedger,
) -> None:
```

Store as `self._cost_ledger = cost_ledger`.

### `call_llm` node — pricing extraction

After the existing LLM call and `usage_metadata` extraction, add:

```python
metadata = response.response_metadata
input_unit_price  = float(metadata.get("input_unit_price",  0.0))
output_unit_price = float(metadata.get("output_unit_price", 0.0))
cost_usd = (
    input_tokens  * input_unit_price +
    output_tokens * output_unit_price
)
```

OpenRouter returns these fields as `input_unit_price` / `output_unit_price` in
`response_metadata`. Non-OpenRouter providers will return nothing — the
`.get(..., 0.0)` default handles this cleanly.

### `llm_usage` log event enrichment (Option A)

Add `cost_usd`, `input_unit_price`, `output_unit_price` to the existing
`llm_usage` structlog event. This is the real-time visibility layer.

### Ledger write (Option B)

After the log event:

```python
entry = CostEntry(
    timestamp=datetime.utcnow().isoformat(),
    thread_id=config["configurable"]["thread_id"],
    agent=self._name,
    model=self._settings.llm_model,
    input_tokens=input_tokens,
    output_tokens=output_tokens,
    total_tokens=total_tokens,
    input_unit_price=input_unit_price,
    output_unit_price=output_unit_price,
    cost_usd=cost_usd,
    experiment=self._settings.experiment,
)
await self._cost_ledger.record(entry)
```

`thread_id` is available from the LangGraph `config` dict passed to the node.
The node signature must accept `config: RunnableConfig` to access it — see
LangGraph docs for passing config to nodes.

---

## CLI Lifecycle — `run.py` and `start.py`

Both files gain the `CostLedger` `async with` block, nested inside the
`AsyncSqliteSaver` block (resource order: transport → checkpointer → cost ledger):

```python
settings.cost_db_path.parent.mkdir(parents=True, exist_ok=True)
async with CostLedger(settings.cost_db_path) as cost_ledger:
    agent = LLMAgent(name, settings, checkpointer, cost_ledger)
    ...
```

In `start.py` the `CostLedger` is shared across all agents, same as the
checkpointer.

---

## `scripts/browse_threads.py` — Modifications

### Join with `cost_ledger`

After loading the thread summary from `agents.db`, open `costs.db` (from
`Settings().cost_db_path`) as a second connection and query cost per thread:

```sql
SELECT thread_id, SUM(cost_usd) AS total_cost
FROM cost_ledger
GROUP BY thread_id
```

Build a `dict[str, float]` keyed by `thread_id`. Join in Python when building
table rows.

**Absent cost data:** if `costs.db` does not exist or `cost_ledger` is empty,
default to `0.0` for all threads — show `—` in the cost column. Never error.

### New `Cost` column in the table

Add after `Processed`:

| # | Thread ID | Messages | Processed | Cost | Preview | Started | Last activity |
|---|---|---|---|---|---|---|---|

Format cost as `$0.0000` (4 decimal places). Show `—` when no cost data.

---

## `scripts/show_thread.py` — Modifications

After rendering the full message chain, append a cost summary footer queried
from `costs.db`:

```sql
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
```

Render as a `rich.table.Table` with title `Cost summary — thread {thread_id[:8]}`.

Columns: `Agent`, `Calls`, `Input tokens`, `Output tokens`, `Total tokens`,
`Cost USD`.

Add a totals row summing all numeric columns. Format cost as `$0.0000`.

**Absent cost data:** if no rows are returned, omit the footer entirely — do not
print an empty table.

---

## `scripts/show_costs.py` — New File

Analytical cross-run views. Reads exclusively from `costs.db`.

### Module docstring

```python
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
```

### Flags

```python
--by-agent               # group by agent
--by-model               # group by model
--experiment LABEL       # filter to one experiment label
```

Flags are mutually exclusive — if more than one is supplied, print an error and
exit 1.

### Queries

**Default (by experiment):**
```sql
SELECT
    experiment,
    COUNT(*)            AS calls,
    SUM(input_tokens)   AS input_tokens,
    SUM(output_tokens)  AS output_tokens,
    SUM(cost_usd)       AS cost_usd
FROM cost_ledger
GROUP BY experiment
ORDER BY MIN(timestamp) DESC
```

**`--by-agent`:**
```sql
SELECT
    agent,
    COUNT(*)            AS calls,
    SUM(input_tokens)   AS input_tokens,
    SUM(output_tokens)  AS output_tokens,
    SUM(cost_usd)       AS cost_usd
FROM cost_ledger
GROUP BY agent
ORDER BY SUM(cost_usd) DESC
```

**`--by-model`:**
```sql
SELECT
    model,
    COUNT(*)            AS calls,
    SUM(input_tokens)   AS input_tokens,
    SUM(output_tokens)  AS output_tokens,
    SUM(cost_usd)       AS cost_usd
FROM cost_ledger
GROUP BY model
ORDER BY SUM(cost_usd) DESC
```

**`--experiment LABEL`:**
Same as `--by-agent` query but with `WHERE experiment = ?`.

All views include a totals row. Format cost as `$0.0000`.
If the ledger is empty, print `No cost data found.` and exit 0.

---

## `scripts/show_run.py` — Modifications

The `llm_usage` JSONL events already contain token counts (006-CR1). After this
task they also contain `cost_usd`. Add:

- `cost_usd` column to the LLM calls table
- Cost included in the cumulative totals row
- Format: `$0.0000`

---

## `scripts/compare_runs.py` — Modifications

Add `Total cost` column to the runs comparison table. Source: sum of `cost_usd`
from `llm_usage` events in each run's JSONL file.

Format: `$0.0000`.

---

## `justfile` — Additions

```makefile
# Show cost summary by experiment
costs:
    uv run python scripts/show_costs.py

# Show cost breakdown by agent
costs-by-agent:
    uv run python scripts/show_costs.py --by-agent

# Show cost breakdown by model
costs-by-model:
    uv run python scripts/show_costs.py --by-model
```

Add in the inspection scripts section after the `threads` target.

---

## Test Requirements

### `tests/unit/core/test_costs.py` — New File

```
TestCostLedger
    test_record_writes_row_to_database
        — open real CostLedger against tmp_path db
        — record one CostEntry
        — query db directly, assert row exists with correct values

    test_record_failure_does_not_raise
        — pass a closed / invalid connection
        — assert no exception propagates

    test_missing_parent_directory_is_created
        — db_path in a non-existent subdirectory of tmp_path
        — assert CostLedger.__aenter__ creates it

    test_schema_is_idempotent
        — open CostLedger twice against same db
        — assert no error on second open (CREATE TABLE IF NOT EXISTS)
```

### `tests/unit/core/test_agent.py` — Modifications

Add to existing test class:

```
test_cost_entry_recorded_on_llm_call
    — mock CostLedger.record
    — run agent with mocked LLM response including response_metadata
      with input_unit_price and output_unit_price
    — assert record() called once with correct cost_usd

test_cost_recording_failure_does_not_fail_agent
    — mock CostLedger.record to raise Exception
    — assert agent run completes normally

test_zero_cost_when_pricing_absent
    — mock LLM response with no pricing in response_metadata
    — assert CostEntry.cost_usd == 0.0
```

### `tests/unit/scripts/test_show_costs.py` — New File

```
TestShowCosts
    test_exits_zero_when_no_data
    test_exits_nonzero_with_missing_database
    test_by_agent_flag_produces_agent_grouped_output
    test_by_model_flag_produces_model_grouped_output
    test_mutually_exclusive_flags_exit_nonzero
```

Use `subprocess.run` with `COST_DB_PATH` env override and `tmp_path` SQLite db,
following the pattern established in 005-CR2 tests.

---

## Module Boundary Verification

`core/costs.py` must not import from `transport/`, `cli/`, or `config/`.
It receives `db_path: Path` directly — no Settings dependency.

```bash
grep -r "from multiagent.cli"       src/multiagent/core/     # must return nothing
grep -r "from multiagent.transport" src/multiagent/core/     # must return nothing
grep -r "from multiagent.config"    src/multiagent/core/costs.py  # must return nothing
```

---

## Implementation Order

1. Add `cost_db_path` to `settings.py`
2. Create `src/multiagent/core/costs.py` — `CostEntry` + `CostLedger`
3. Write `tests/unit/core/test_costs.py` — TDD red phase
4. Green phase — all 4 `TestCostLedger` tests pass
5. Modify `src/multiagent/core/agent.py` — pricing extraction, log enrichment, ledger write
6. Update `tests/unit/core/test_agent.py` — 3 new agent cost tests
7. Modify `cli/run.py` and `cli/start.py` — `CostLedger` lifecycle
8. Modify `scripts/browse_threads.py` — cost column
9. Modify `scripts/show_thread.py` — cost footer
10. Create `scripts/show_costs.py`
11. Write `tests/unit/scripts/test_show_costs.py`
12. Modify `scripts/show_run.py` and `scripts/compare_runs.py`
13. Add `justfile` targets
14. `just check && just test`
15. Manual smoke test (below)

---

## Manual Smoke Test

```bash
# Start the newsroom pipeline
just start --experiment cost-test

# In a second terminal, inject the opening message
just send scout "The future of nuclear fusion energy"

# Wait for Prose to complete, then Ctrl-C

# Verify cost appears in thread browser
just threads
# Cost column should show a non-zero value for the new thread

# Select the thread — verify cost footer appears
# Agent | Calls | Input tokens | Output tokens | Total tokens | Cost USD
# scout |   1   |     ...      |      ...      |     ...      | $0.0000
# ...
# prose |   1   |     ...      |      ...      |     ...      | $0.0000
# Total |   5   |     ...      |      ...      |     ...      | $0.0000

# Verify analytical views
just costs
just costs-by-agent
just costs-by-model
```

---

## Acceptance Criteria

```bash
just check    # zero ruff errors, zero pyright errors
just test     # all tests pass (previous total + new tests)
```

Manual:
- `just threads` shows `Cost` column with values for runs after this task
- `just threads` shows `—` for threads that predate this task (no cost data)
- Selecting a thread in `browse_threads.py` shows cost summary footer
- `just costs` renders experiment summary table
- `just costs-by-agent` and `just costs-by-model` render correctly
- `show_run.py` shows cost column
- Zero errors in log output — no `cost_recording_failed` warnings

---

## What This Task Does NOT Include

- Budget guards or spend limits — OpenRouter handles this externally
- Cost data for runs predating this task — ledger starts empty, that is correct
- Currency conversion — USD only, matching OpenRouter's pricing unit
- Price caching or a model price registry — prices come from the API response
  at call time, not from a local lookup table
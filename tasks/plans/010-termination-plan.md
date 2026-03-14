# Plan: Task 010 — Loop Detection and Termination

**Task:** `tasks/010-termination.md`
**Author:** Tom (implementer)
**Date:** 2026-03-14
**Status:** APPROVED — architect review complete, implementing
**Base branch:** `master` @ `bd23427`
**Feature branch:** `feature/termination`

---

## Prerequisite: Task 011b Not Merged

The brief states "Depends on: Task 011b (routing) complete and merged to master."
Task 011b (`feature/routing`) is **not yet merged to master**. The master branch
`runner.py` has the pre-routing structure: `agent.run()` returns `str` (not
`RunResult`), and `run_once()` uses `self._next_agent` directly with no dynamic
routing.

**Decision:** I will implement against master's current `runner.py` structure.
When 011b is merged, the integration point changes slightly (the dispatch block
uses `effective_next = run_result.next_agent or self._next_agent`), but the
termination checks are inserted at the same logical point — after routing
resolution, before `transport.send()`.

**Rebase requirement (architect-confirmed):** This branch (`feature/termination`)
must NOT be merged to master before `feature/routing` (011b) is merged first.
After 011b lands on master, this branch must be rebased onto master and the
termination check integration point in `run_once()` must be verified against the
updated dispatch block (`effective_next` instead of `self._next_agent`). The
rebase is expected to be straightforward but must be verified, not assumed.

---

## Design Decisions and Ambiguities

### 1. Direct DB query vs. Transport method

The brief says: "use `aiosqlite` directly in the check methods — same pattern
used in `browse_threads.py`" and "Do not add new methods to the Transport ABC."

**Problem:** `AgentRunner` is in `core/`. Using `aiosqlite` directly in `core/`
would add an I/O dependency to the agent core — the implementation guide says
`core/` has "zero I/O knowledge" and the module boundary rules say `core/` may
only import from `config/` and `exceptions`. Importing `aiosqlite` in
`core/runner.py` would be an architectural violation.

**Proposed resolution:** Add a non-abstract helper method `thread_messages_tail()`
to `SQLiteTransport` (not to the `Transport` ABC). In `AgentRunner`, use a
**duck-typing check** (`hasattr(self._transport, 'thread_messages_tail')`) to
call it when available. If not available (e.g. `TerminalTransport`), log a
WARNING and skip termination checks — exactly as the brief specifies for non-SQLite
transports.

This approach:
- Keeps `core/` free of `aiosqlite` imports
- Does not modify the `Transport` ABC
- Is fully testable with mock transports
- Follows the brief's intent for TerminalTransport (log WARNING, skip)

**Alternative considered:** Pass the `db_path` and have the runner open its own
`aiosqlite` connection. Rejected — this couples `core/` to `aiosqlite` and
duplicates connection management.

**Architect verdict:** Approved and commended. The brief was wrong on this point.

### 2. Query method signature

The runner needs two queries:
1. **Loop detection:** Last N messages on a thread (from_agent, to_agent only)
2. **Max messages:** Total message count on a thread

Rather than two separate transport methods, I propose one flexible method:

```python
# On SQLiteTransport (not on ABC)
async def thread_messages_tail(
    self, thread_id: str, limit: int,
) -> list[tuple[str, str]]:
    """Return (from_agent, to_agent) pairs for the last `limit` messages
    on a thread, ordered most-recent-first."""
```

And a second:

```python
async def thread_message_count(self, thread_id: str) -> int:
    """Return total message count for a thread."""
```

Two methods is cleaner than one overloaded method — each does exactly one thing.

### 3. Settings default for loop detection

The brief says `agent_loop_detection_threshold` defaults to `3` with "0 = disabled".
But the preamble says "Both default to disabled / unlimited so existing behaviour
is unchanged by default."

These conflict — default of 3 means loop detection is **enabled** by default.
I'll follow the field definition (default=3) since this is the safety-first
choice and the brief's explicit specification. The "disabled by default" sentence
appears to be describing the max_messages field only.

### 4. Settings field placement

The `AgentRunner` constructor currently takes `settings: Settings`. It already
reads `settings.sqlite_poll_interval_seconds`. I'll read the two new settings
in the constructor and store them as private fields, same pattern.

---

## Files to Create or Modify

| File | Action | Description |
|------|--------|-------------|
| `src/multiagent/config/settings.py` | Modify | Add `agent_loop_detection_threshold` and `agent_max_messages_per_thread` fields |
| `.env.defaults` | Modify | Add both new settings with comments |
| `tests/conftest.py` | Modify | Add both fields to `test_settings` fixture |
| `src/multiagent/transport/sqlite.py` | Modify | Add `thread_messages_tail()` and `thread_message_count()` helper methods (not on ABC) |
| `src/multiagent/core/runner.py` | Modify | Add `_check_loop_detected()`, `_check_max_messages()`, integrate into `run_once()` |
| `tests/unit/core/test_runner.py` | Modify | Add `TestLoopDetection` (6 tests) and `TestMaxMessages` (3 tests) |
| `tests/unit/transport/test_sqlite.py` | Modify | Add tests for the two new SQLiteTransport helper methods |

No new files created.

---

## Implementation Order

### Step 1: Settings fields
**Files:** `settings.py`, `.env.defaults`, `conftest.py`
**Rationale:** Foundation — everything else depends on these fields existing.

Add to `settings.py`:
```python
# Termination
agent_loop_detection_threshold: int = Field(
    3,
    ge=0,
    description="Halt dispatch when the same agent sends to itself this many "
    "consecutive times on a thread. 0 = disabled.",
)
agent_max_messages_per_thread: int = Field(
    0,
    ge=0,
    description="Halt dispatch when thread message count reaches this value. "
    "0 = unlimited.",
)
```

Add to `.env.defaults` and `test_settings` fixture.

Gate: `just check && just test` — verify no regressions.

### Step 2: SQLiteTransport helper methods
**Files:** `sqlite.py`, `test_sqlite.py`
**Rationale:** The check methods in the runner need these queries. Build the
data layer first so the runner tests can use a real `SQLiteTransport` with
`tmp_path` databases (matching the test strategy in the implementation guide).

Add `thread_messages_tail(thread_id, limit)` and `thread_message_count(thread_id)`
to `SQLiteTransport`. These are non-abstract — not on the `Transport` ABC.

Tests (in `test_sqlite.py`):
- `test_thread_messages_tail_returns_most_recent_first`
- `test_thread_messages_tail_respects_limit`
- `test_thread_messages_tail_returns_empty_for_unknown_thread`
- `test_thread_message_count_returns_correct_count`
- `test_thread_message_count_returns_zero_for_unknown_thread`

Gate: `just check && just test`

### Step 3: Runner termination check methods (TDD red phase)
**Files:** `test_runner.py`
**Rationale:** Write the 9 failing tests before implementation.

The runner tests currently use `AsyncMock` for transport. For termination tests,
I need the transport to have `thread_messages_tail` and `thread_message_count`
methods. Two approaches:

**Option A:** Use a real `SQLiteTransport` with `tmp_path` for termination tests
only — populate with known messages, then run the checks.

**Option B:** Add `thread_messages_tail` and `thread_message_count` to the mock
transport fixture.

**Decision:** Option B for unit test speed and isolation. The real
`SQLiteTransport` queries are already tested in step 2. The runner tests should
verify the runner's logic, not re-test the transport.

For the mock, I'll add the two methods to the `mock_transport` fixture and
configure return values per test.

### Step 4: Runner implementation (TDD green phase)
**Files:** `runner.py`
**Rationale:** Implement `_check_loop_detected`, `_check_max_messages`, integrate
into `run_once()`.

Key implementation details:

**`_check_loop_detected(thread_id, proposed_recipient)`:**
1. If `proposed_recipient != self._agent.name` → return False (no query)
2. If `self._loop_threshold == 0` → return False (disabled)
3. If transport lacks `thread_messages_tail` → log WARNING once, return False
4. Query last N messages via `self._transport.thread_messages_tail(thread_id, N)`
5. If fewer than N results → return False (not enough history)
6. If all N have `from_agent == to_agent == self._agent.name` → return True

**`_check_max_messages(thread_id)`:**
1. If `self._max_messages == 0` → return False (disabled)
2. If transport lacks `thread_message_count` → log WARNING once, return False
3. Query count via `self._transport.thread_message_count(thread_id)`
4. If count >= threshold → return True

**Integration in `run_once()`:**
Insert after ack, before dispatch — between lines 101 and 104 (current master).

```python
# After ack, before dispatch
if self._next_agent:
    if await self._check_loop_detected(msg.thread_id, self._next_agent):
        self._log.warning(
            "routing_loop_detected",
            thread_id=msg.thread_id,
            agent=self._agent.name,
            recipient=self._next_agent,
            threshold=self._loop_threshold,
        )
        return True  # processed, dispatch suppressed

    if await self._check_max_messages(msg.thread_id):
        self._log.warning(
            "max_messages_reached",
            thread_id=msg.thread_id,
            agent=self._agent.name,
            count=self._max_messages,
        )
        return True  # processed, dispatch suppressed

    await self._transport.send(...)
```

Gate: `just check && just test` — all 9 new tests green + 0 regressions.

### Step 5: Module boundary verification
```bash
grep -r "from multiagent.transport" src/multiagent/core/
grep -r "import aiosqlite"          src/multiagent/core/
```
Both must return empty.

### Step 6: Manual smoke test
Per the brief's instructions — configure a self-routing looper agent and verify
loop detection fires after exactly 3 self-sends.

---

## Test Plan Summary

| Test class | Test name | What it verifies |
|------------|-----------|------------------|
| `TestLoopDetection` | `test_loop_detected_when_threshold_consecutive_self_sends` | N self-sends → True |
| | `test_loop_not_detected_below_threshold` | N-1 self-sends → False |
| | `test_loop_not_detected_when_recipient_differs` | Different recipient → False, no query |
| | `test_loop_not_detected_when_disabled` | threshold=0 → False regardless |
| | `test_loop_detection_resets_after_non_self_send` | Broken streak → False |
| | `test_routing_loop_detected_event_logged` | WARNING logged, send not called |
| `TestMaxMessages` | `test_dispatch_suppressed_when_max_reached` | count >= max → suppressed + WARNING |
| | `test_dispatch_proceeds_below_max` | count < max → normal dispatch |
| | `test_max_messages_disabled_when_zero` | max=0 → no suppression |
| `TestSQLiteTransport*` | 5 tests for `thread_messages_tail` and `thread_message_count` | Query correctness |

Total: 14 new tests.

---

## What I Would Do Differently From the Brief

### 1. No `aiosqlite` in `core/` (covered above)
The brief suggests using `aiosqlite` directly in runner check methods. This
violates the module boundary rules. The transport helper method approach preserves
the architecture.

### 2. 14 tests instead of 9
The brief specifies 9 runner tests. I'm adding 5 transport tests to verify the
new SQLiteTransport helper methods independently. This follows the implementation
guide's principle: "Every component with a graceful failure mode must have a test."

### 3. `ge=0` instead of `ge=1` for loop threshold
The brief shows `ge=1` for `agent_loop_detection_threshold`, but then says
"Set to 0 to disable." A `ge=1` constraint would reject `0`. I'll use `ge=0`
to allow the disable sentinel.

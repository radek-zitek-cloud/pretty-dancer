# Task 010 — Loop Detection and Termination

**File:** `tasks/010-termination.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-14  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 011b (routing) complete and merged to master

---

## Objective

Prevent runaway agent loops and unbounded thread growth. Two independent
termination conditions are added to `AgentRunner`:

1. **Loop detection** — halt when the same agent sends to itself N consecutive
   times on the same thread. This is the primary safety net, motivated by a
   real incident where a misconfigured router caused infinite self-routing.

2. **`max_messages_per_thread`** — halt when the total message count on a
   thread exceeds a configured ceiling. Secondary safety net for experiments
   that should be bounded by design.

Both conditions check before dispatch — the current message is always processed
and the LLM call always completes. The agent halts cleanly after producing its
response, without sending it. Both conditions log a structured event and are
observable via the existing JSONL stream.

Neither condition raises an exception or crashes the cluster. Other agents
continue running normally. Only the affected agent on the affected thread stops
dispatching.

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — all standards, module rules, coding conventions
- `tasks/003-agent-core.md` — original `AgentRunner` design
- `tasks/011b-routing.md` — current `AgentRunner.run_once()` structure this
  task modifies

---

## Git

Work on branch `feature/termination` created from `master`.

```bash
git checkout master
git pull origin master
git checkout -b feature/termination
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
feat(core): add loop detection and max_messages_per_thread termination
```

---

## New Settings Fields

```python
agent_loop_detection_threshold: int = Field(
    3,
    ge=1,
    description=(
        "Halt dispatch when the same agent sends to itself this many "
        "consecutive times on a thread. Set to 0 to disable."
    ),
)

agent_max_messages_per_thread: int = Field(
    0,
    ge=0,
    description=(
        "Halt dispatch when thread message count reaches this value. "
        "0 = unlimited."
    ),
)
```

Add both to `settings.py` and `.env.defaults`. Both default to disabled /
unlimited so existing behaviour is unchanged by default.

---

## `src/multiagent/core/runner.py` — Modifications

All termination logic lives in `AgentRunner`. No changes to `agent.py`,
`transport/`, or `cli/`.

### New method: `_check_loop_detected`

```python
async def _check_loop_detected(
    self,
    thread_id: str,
    proposed_recipient: str,
) -> bool:
    """Return True if dispatching would extend a self-routing loop.

    Queries the transport database for the N most recent messages on this
    thread. If all N were sent by this agent to itself, a loop is detected.

    Args:
        thread_id: The current thread.
        proposed_recipient: The agent this runner intends to send to next.

    Returns:
        True if loop detected and dispatch should be suppressed.
    """
```

Detection logic:

1. If `proposed_recipient != self._agent_name` — not a self-send, return False
   immediately (no query needed).
2. If `settings.agent_loop_detection_threshold == 0` — disabled, return False.
3. Query the transport for the last N messages on the thread where
   `from_agent = self._agent_name AND to_agent = self._agent_name`,
   where N = `settings.agent_loop_detection_threshold`.
4. If count equals N — loop detected, return True.

The query counts only consecutive self-sends since the last message that was
not a self-send — not total self-sends on the thread. A genuine circular debate
that occasionally self-corrects should not be penalised.

**Recommended query approach:** fetch the last `threshold` messages on the
thread ordered by `created_at DESC` and check if all have
`from_agent = to_agent = self._agent_name`. This is simpler than a subquery
and reliable for the typical threshold of 3.

```sql
SELECT COUNT(*) FROM (
    SELECT from_agent, to_agent FROM messages
    WHERE thread_id = ?
    ORDER BY created_at DESC
    LIMIT ?
) recent
WHERE from_agent = ? AND to_agent = ?
```

If the count equals the threshold, all recent messages were self-sends.

### New method: `_check_max_messages`

```python
async def _check_max_messages(self, thread_id: str) -> bool:
    """Return True if the thread has reached the message ceiling.

    Args:
        thread_id: The current thread.

    Returns:
        True if max_messages_per_thread reached and dispatch should be
        suppressed.
    """
```

Logic:

1. If `settings.agent_max_messages_per_thread == 0` — disabled, return False.
2. Query `SELECT COUNT(*) FROM messages WHERE thread_id = ?`.
3. If count >= threshold — return True.

### `run_once()` — integration point

After the agent processes the message and before dispatching the response,
call both checks:

```python
# Resolve effective recipient
effective_next = run_result.next_agent or self._next_agent

if effective_next is not None:
    if await self._check_loop_detected(thread_id, effective_next):
        self._log.warning(
            "routing_loop_detected",
            thread_id=thread_id,
            agent=self._agent_name,
            recipient=effective_next,
            threshold=self._settings.agent_loop_detection_threshold,
        )
        return True  # message processed, dispatch suppressed

    if await self._check_max_messages(thread_id):
        self._log.warning(
            "max_messages_reached",
            thread_id=thread_id,
            agent=self._agent_name,
            count=self._settings.agent_max_messages_per_thread,
        )
        return True  # message processed, dispatch suppressed

    # proceed with dispatch
    await self._transport.send(...)
```

**Order matters:** loop detection runs before max messages. A loop is the more
urgent safety concern.

### Direct transport query

Both check methods need to query the transport database directly. `AgentRunner`
already holds `self._transport`. If `SQLiteTransport` exposes the `db_path`,
use `aiosqlite` directly in the check methods — same pattern used in
`browse_threads.py` and `listen.py`. Do not add new methods to the `Transport`
ABC — this would violate the interface stability principle.

If `SQLiteTransport` does not currently expose `db_path` as a public attribute,
add it. It is not a breaking change.

---

## `.env.defaults` Additions

```bash
# --- TERMINATION ---
# Loop detection: halt when agent sends to itself this many consecutive times.
# 0 = disabled.
AGENT_LOOP_DETECTION_THRESHOLD=3

# Max messages per thread: halt dispatch when thread reaches this count.
# 0 = unlimited.
AGENT_MAX_MESSAGES_PER_THREAD=0
```

---

## Test Requirements

### `tests/unit/core/test_runner.py` — Modifications

```
TestLoopDetection
    test_loop_detected_when_threshold_consecutive_self_sends
        — populate transport with N messages from_agent=X to_agent=X
        — assert _check_loop_detected returns True

    test_loop_not_detected_below_threshold
        — populate transport with N-1 self-send messages
        — assert _check_loop_detected returns False

    test_loop_not_detected_when_recipient_differs
        — proposed_recipient != agent_name
        — assert _check_loop_detected returns False without querying transport

    test_loop_not_detected_when_disabled
        — agent_loop_detection_threshold = 0
        — assert _check_loop_detected returns False regardless of messages

    test_loop_detection_resets_after_non_self_send
        — N-1 self-sends, then one send to another agent, then one self-send
        — assert _check_loop_detected returns False (streak broken)

    test_routing_loop_detected_event_logged
        — trigger loop detection
        — assert structlog WARNING event "routing_loop_detected" emitted
        — assert dispatch (transport.send) not called

TestMaxMessages
    test_dispatch_suppressed_when_max_reached
        — thread has max_messages_per_thread messages
        — assert dispatch suppressed, "max_messages_reached" WARNING logged

    test_dispatch_proceeds_below_max
        — thread has max_messages_per_thread - 1 messages
        — assert dispatch proceeds normally

    test_max_messages_disabled_when_zero
        — agent_max_messages_per_thread = 0
        — assert no suppression regardless of message count
```

---

## Implementation Order

1. Add settings fields to `settings.py` and `.env.defaults`
2. Update `test_settings` fixture in `conftest.py`
3. Add `db_path` public attribute to `SQLiteTransport` if not already present
4. Write `tests/unit/core/test_runner.py` additions — TDD red phase (9 tests)
5. Implement `_check_loop_detected` in `runner.py`
6. Implement `_check_max_messages` in `runner.py`
7. Integrate both checks into `run_once()`
8. Green phase — all 9 tests pass
9. `just check && just test`
10. Manual smoke test (below)

---

## Manual Smoke Test

### Loop detection

Configure a circular debate with a deliberately broken router that always
routes to self:

```toml
[agents.looper]
router = "always_self"

[routers.always_self]
type = "keyword"
routes.looper = [""]          # empty string matches everything
default = "looper"
```

```bash
just start --experiment loop-test
just send looper "start"
# watch logs — expect "routing_loop_detected" WARNING after 3 self-sends
# cluster continues running, looper stops dispatching on this thread
# send to a different thread — looper should process it normally
```

### Max messages

```bash
AGENT_MAX_MESSAGES_PER_THREAD=5 just start --experiment maxmsg-test
just send editor "write something about water"
# watch logs — expect "max_messages_reached" WARNING when thread hits 5 messages
```

---

## Acceptance Criteria

```bash
just check    # zero ruff errors, zero pyright errors
just test     # all tests pass (previous total + 9 new)
```

Manual:
- Loop detection fires after exactly N consecutive self-sends
- Loop detection does not fire when the self-send streak is broken
- Max messages fires when thread count reaches the threshold
- Both conditions log a structured WARNING event
- Cluster continues running after either condition fires
- A new thread on the same agent processes normally after suppression

---

## What This Task Does NOT Include

- Automatic agent restart after termination
- Per-agent termination thresholds (global settings only)
- Notification to human when termination fires (observable via log only)
- `TerminalTransport` support for the direct DB query — loop detection only
  works with `SQLiteTransport`; log a WARNING and skip if transport is not
  SQLite
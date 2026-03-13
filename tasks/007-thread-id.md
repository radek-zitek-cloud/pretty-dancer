# Task 007 — `send --thread-id`

**File:** `tasks/007-send-thread-id.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-13  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 006 checkpointer complete and merged to master

---

## Objective

Add an optional `--thread-id` flag to the `send` command. When supplied, the
injected message continues an existing conversation thread rather than starting
a new one. This allows a circular debate to be resumed after restarting agents
without losing checkpoint history.

---

## Git

Work on branch `feature/send-thread-id` created from `master`.

```bash
git checkout master
git pull origin master
git worktree add ../multiagent-send-thread-id feature/send-thread-id
```

Final commit:

```
feat(cli): add --thread-id flag to send command for thread continuation
```

Tag: none.

---

## Deliverables

### Source Files

```
src/multiagent/cli/send.py            # add --thread-id option with UUID validation
```

### Test Files

```
tests/unit/cli/test_send.py           # extend with --thread-id tests
```

---

## `send` Command — Changes

### New option

```python
import uuid as uuid_module

def send_command(
    agent_name: str = typer.Argument(..., help="Name of the agent to send to."),
    body: str = typer.Argument(..., help="Message body text."),
    thread_id: str = typer.Option(
        "",
        "--thread-id", "-t",
        help="Existing thread UUID to continue. Omit to start a new thread.",
    ),
) -> None:
```

### UUID validation

```python
resolved_thread_id: str | None = None

if thread_id:
    try:
        uuid_module.UUID(thread_id)
        resolved_thread_id = thread_id
    except ValueError:
        raise typer.BadParameter(
            f"thread-id must be a valid UUID: {thread_id!r}",
            param_hint="--thread-id",
        )
```

### `Message` construction

```python
message = Message(
    from_agent="human",
    to_agent=agent_name,
    body=body,
    **({"thread_id": resolved_thread_id} if resolved_thread_id else {}),
)
```

When `resolved_thread_id` is `None`, `Message` generates a fresh UUID as before.
Existing behaviour is fully preserved — the flag is optional.

### Output

```python
typer.echo(f"Sent to {agent_name}. Thread: {message.thread_id}")
```

Output is unchanged whether `--thread-id` was supplied or not. The thread_id
printed is always the one actually used, so the user can copy it for the next
injection if needed.

---

## Usage

```bash
# Start a new debate — prints thread_id on success
just send progressive "Make the opening progressive argument on minimum wage."
# → Sent to progressive. Thread: 3f2a1b4c-...

# Resume the same thread after restarting agents
just send progressive "Continue the debate." --thread-id 3f2a1b4c-...

# Invalid UUID — exits immediately with clear error
just send progressive "body" --thread-id not-a-uuid
# → Error: Invalid value for '--thread-id': thread-id must be a valid UUID: 'not-a-uuid'
```

---

## Test Requirements

Extend `tests/unit/cli/test_send.py`:

```
TestSendThreadId
    test_new_thread_id_generated_when_flag_omitted
    test_supplied_thread_id_used_in_message
    test_invalid_uuid_raises_bad_parameter
    test_output_prints_thread_id_used
```

All tests use mocked transport — no real SQLite, no real LLM.

---

## Implementation Order

1. Modify `src/multiagent/cli/send.py` — add `--thread-id` option and UUID validation
2. Run `just check` — zero errors
3. Write `TestSendThreadId` tests in `tests/unit/cli/test_send.py`
4. Run `just test` — all pass
5. Manual smoke test — new thread, resume thread, invalid UUID

---

## Acceptance Criteria

```bash
just check    # zero ruff errors, zero pyright errors
just test     # all tests pass (4 new)
```

Manual:
- `just send progressive "body"` prints a thread_id — confirmed
- `just send progressive "body" --thread-id <valid-uuid>` uses that thread_id — confirmed
- `just send progressive "body" --thread-id bad-value` exits with clear error — confirmed

---

## What This Task Does NOT Include

- Validation that the supplied `thread_id` actually exists in the checkpoint database
- `--thread-id` on the `run` command
- Thread listing or lookup commands
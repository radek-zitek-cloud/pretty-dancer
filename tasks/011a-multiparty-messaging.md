# Task 011a — Multi-Party Messaging

**File:** `tasks/011a-multiparty-messaging.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-14  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 009 (cost tracking) complete and merged to master

---

## Objective

Enable two-way conversation between the human and any agent in the cluster.
Currently the human can send messages into the pipeline but never receives
anything back — output is only visible via `show_thread.py` after the fact.

After this task:
- Every message has a `sender` field identifying who produced it
- `human` is a valid recipient — agents can address messages back to the human
- A new `listen` CLI command polls for messages addressed to `human` and
  prints them as they arrive
- A new `chat` CLI command combines send and listen into a REPL-style
  interactive session with a named agent
- The full architect/implementer dialogue workflow becomes possible in a
  terminal without any manual database queries

This task is the prerequisite for the routing module (Task 011b) and the
supervisor pattern (Task 012).

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — all standards, module rules, coding conventions
- `tasks/002-transport.md` — original transport schema and design
- `tasks/004-cli-wiring.md` — CLI patterns this task extends
- `tasks/007-send-thread-id.md` — `send` command this task modifies

---

## Git

Work on branch `feature/multiparty-messaging` created from `master`.

```bash
git checkout master
git pull origin master
git worktree add ../multiagent-multiparty feature/multiparty-messaging
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
feat(transport): add sender field and human recipient for multi-party messaging
```

---

## Transport Schema Changes

### Add `sender` to the `messages` table

```sql
ALTER TABLE messages ADD COLUMN sender TEXT NOT NULL DEFAULT 'human';
```

`sender` identifies the originator of each message:
- CLI `send` command sets `sender = "human"`
- `AgentRunner` sets `sender = agent_name` when dispatching to the next agent

### Migration

`SQLiteTransport._ensure_schema()` must handle existing databases that do not
have the `sender` column. Use:

```sql
ALTER TABLE messages ADD COLUMN sender TEXT NOT NULL DEFAULT 'human'
```

wrapped in a check:

```python
columns = await conn.execute("PRAGMA table_info(messages)")
col_names = [row[1] for row in await columns.fetchall()]
if "sender" not in col_names:
    await conn.execute(
        "ALTER TABLE messages ADD COLUMN sender TEXT NOT NULL DEFAULT 'human'"
    )
```

This is backward compatible — existing rows get `sender = 'human'` by default,
which is correct since all existing messages were injected by the human via the
`send` command.

### `Message` model changes

Add `sender: str = "human"` to the `Message` dataclass or Pydantic model.

`AgentRunner` sets `sender = self._agent_name` when constructing the outbound
message. The `send` CLI command leaves `sender` at the default `"human"`.

---

## `human` as a Valid Recipient

`human` is a reserved agent name. It is not defined in `agents.toml` and has
no `LLMAgent` or `AgentRunner`. It is a transport-level destination only.

When `AgentRunner` constructs an outbound message and `next_agent = "human"`,
the message is written to the transport with `recipient = "human"` exactly as
any other agent name would be. No special-casing in `AgentRunner` — it does
not know or care that `human` has no backing agent.

The `listen` command is what consumes messages addressed to `human`. If
`listen` is not running, messages accumulate in the database unread —
identical to messages addressed to an agent whose `AgentRunner` is not
running.

**`agents.toml` example:**

```toml
[agents.architect]
next_agent = "human"    # architect always replies to human by default

[agents.implementer]
next_agent = "architect"  # implementer always replies to architect
```

Dynamic routing (Task 011b) will replace these fixed values with conditional
edges. For this task, fixed `next_agent = "human"` is sufficient.

---

## New CLI Commands

### `multiagent listen`

Polls the transport for messages addressed to `"human"` and prints them as
they arrive.

```python
def listen_command(
    thread_id: str = typer.Option(
        "",
        "--thread-id", "-t",
        help="Filter to a specific thread. Empty = all threads.",
    ),
    poll_interval: float = typer.Option(
        0.0,
        "--poll-interval", "-p",
        help="Override poll interval in seconds. 0 = use settings value.",
    ),
) -> None:
    """Poll for messages addressed to human and print them as they arrive.

    Runs until Ctrl-C. Prints each incoming message with sender, timestamp,
    and thread ID. Use --thread-id to watch a specific conversation.

    Args:
        thread_id: Optional thread UUID to filter on.
        poll_interval: Optional poll interval override in seconds.
    """
```

**Behaviour:**

1. Load settings, configure logging with `agent_name="listen"`
2. Print `Listening for messages... (Ctrl-C to stop)`
3. Poll `messages WHERE recipient = 'human' AND processed_at IS NULL`
   (optionally filtered by `thread_id`)
4. For each unread message: print a formatted panel, mark as processed
5. Sleep `poll_interval` (or `settings.sqlite_poll_interval_seconds`) between
   polls
6. On `KeyboardInterrupt`: print `\nStopped.` and exit 0

**Message display format** (rich Panel):

```
╭─── architect → you  |  2026-03-14T10:22:05  |  thread: 4dea209c ───╮
│ The routing module should support two types...                       │
╰──────────────────────────────────────────────────────────────────────╯
```

Header format: `{sender} → you  |  {timestamp}  |  thread: {thread_id[:8]}`

**Marking as processed:** `listen` marks messages as processed by setting
`processed_at` — same as `AgentRunner`. This prevents the same message
appearing twice across multiple `listen` invocations and ensures `listen`
and `AgentRunner` do not both consume the same message if both are running.

### `multiagent chat`

Combines send and listen into an interactive REPL session with a named agent.

```python
def chat_command(
    agent_name: str = typer.Argument(..., help="Agent to chat with."),
    thread_id: str = typer.Option(
        "",
        "--thread-id", "-t",
        help="Resume an existing thread. Empty = new thread.",
    ),
    experiment: str = typer.Option(
        "",
        "--experiment", "-e",
        help="Experiment label for log filenames.",
    ),
) -> None:
    """Interactive chat session with a named agent.

    Sends your input to the agent, waits for a reply addressed to human,
    prints it, then prompts for your next message. Runs until Ctrl-C or
    empty input.

    Args:
        agent_name: Name of the agent to start a conversation with.
        thread_id: Optional existing thread UUID to resume.
        experiment: Optional experiment label for log filenames.
    """
```

**Behaviour:**

1. Load settings, configure logging with `agent_name="chat"`
2. If `thread_id` is empty, generate a new UUID
3. Print `Chatting with {agent_name}. Thread: {thread_id}. (Ctrl-C or empty line to exit)`
4. Loop:
   a. `prompt = input("You: ")` — if empty, exit 0
   b. Send message to `agent_name` with the thread_id, `sender = "human"`
   c. Print `Waiting for {agent_name}...`
   d. Poll `messages WHERE recipient = 'human' AND thread_id = ? AND processed_at IS NULL`
      with timeout of `settings.agent_default_timeout_seconds`
   e. On reply: print formatted panel (same as `listen`), mark as processed
   f. On timeout: print `No reply within {timeout}s. Continue waiting? [y/N]`
      — if N, exit 0
5. On `KeyboardInterrupt`: print `\nSession ended. Thread: {thread_id}` and exit 0

**Why a timeout prompt rather than blocking forever:** an agent may crash or
not be running. The timeout gives the human a clean exit without Ctrl-C.

---

## `AgentRunner` Changes

One addition: when constructing the outbound `Message`, set `sender`:

```python
Message(
    recipient=next_agent,
    sender=self._agent_name,
    body=response_text,
    thread_id=thread_id,
)
```

No other changes to `AgentRunner`. It does not know or care whether the
recipient is `human` or another agent.

---

## `send` Command Changes

Add `sender = "human"` explicitly when constructing the `Message`. This was
previously implicit (default). Making it explicit documents intent and
ensures pyright compliance with the updated model.

---

## `show_thread.py` Changes

Add `Sender` column to the message display — each panel header should show
who sent the message:

```
╭─── architect → implementer  |  10:22:05  |  id=42 ───╮
```

Format: `{sender} → {recipient}  |  {timestamp}  |  id={id}`

This replaces the current header which only shows direction (`→` or `←`
relative to the initiating agent).

---

## `browse_threads.py` Changes

Add `Participants` column to the thread table showing distinct senders in
the thread:

```sql
SELECT GROUP_CONCAT(DISTINCT sender) AS participants
FROM messages
WHERE thread_id = ?
```

Format as comma-separated list: `human, architect, implementer`

---

## Justfile Additions

```makefile
# Listen for messages addressed to human
listen thread_id="":
    uv run multiagent listen {{if thread_id != "" { "--thread-id " + thread_id } else { "" }}}

# Interactive chat session with an agent
chat agent thread_id="":
    uv run multiagent chat {{agent}} {{if thread_id != "" { "--thread-id " + thread_id } else { "" }}}
```

Add in the Application section after the `send` target.

---

## Test Requirements

### `tests/unit/transport/test_sqlite.py` — Modifications

```
test_sender_field_persists_in_database
    — write message with sender="architect"
    — read it back, assert sender == "architect"

test_migration_adds_sender_to_existing_database
    — create database with old schema (no sender column)
    — run _ensure_schema()
    — assert sender column exists with DEFAULT 'human'
    — assert existing rows have sender == 'human'

test_human_is_valid_recipient
    — write message with recipient="human"
    — read it back, assert recipient == "human"
```

### `tests/unit/cli/test_listen.py` — New File

```
TestListenCommand
    test_prints_incoming_message
        — write a message with recipient="human" to transport
        — run listen_command for one poll cycle (mock sleep to break loop)
        — assert message content printed to stdout

    test_marks_message_as_processed
        — write message with recipient="human"
        — run one poll cycle
        — assert processed_at is set in database

    test_filters_by_thread_id
        — write two messages with different thread_ids
        — run with --thread-id matching only one
        — assert only the matching message is printed

    test_keyboard_interrupt_exits_zero
        — mock poll to raise KeyboardInterrupt
        — assert SystemExit(0)
```

### `tests/unit/cli/test_chat.py` — New File

```
TestChatCommand
    test_sends_message_to_named_agent
        — mock input() to return one message then empty string
        — assert transport.send called with correct recipient and sender

    test_exits_on_empty_input
        — mock input() to return "" immediately
        — assert clean exit, no transport.send called

    test_uses_provided_thread_id
        — provide --thread-id flag
        — assert sent message has correct thread_id

    test_generates_thread_id_when_absent
        — no --thread-id provided
        — assert message.thread_id is a valid UUID

    test_keyboard_interrupt_exits_zero
        — mock input() to raise KeyboardInterrupt
        — assert SystemExit(0), thread_id printed to stderr
```

### `tests/unit/cli/test_send.py` — Modifications

Add assertion that sent message has `sender == "human"`.

---

## Implementation Order

1. Update `Message` model — add `sender: str = "human"`
2. Update `SQLiteTransport._ensure_schema()` — migration + `sender` in INSERT/SELECT
3. Write transport tests — TDD red phase (3 tests)
4. Green phase — transport tests pass
5. Update `AgentRunner` — set `sender = self._agent_name` on outbound messages
6. Update `send` command — explicit `sender = "human"`
7. Update `show_thread.py` — sender in panel header
8. Update `browse_threads.py` — Participants column
9. Create `src/multiagent/cli/listen.py`
10. Create `src/multiagent/cli/chat.py`
11. Register both commands in `main.py`
12. Add justfile targets
13. Write `test_listen.py` and `test_chat.py`
14. `just check && just test`
15. Manual smoke test (below)

---

## Manual Smoke Test

Terminal 1 — start the cluster:
```bash
just start --experiment chat-test
```

Terminal 2 — start a chat session with architect:
```bash
just chat architect
# Chatting with architect. Thread: <uuid>. (Ctrl-C or empty line to exit)
You: What are the main components of this system?
Waiting for architect...
# (architect replies)
╭─── architect → you  |  10:22:05  |  thread: 4dea209c ───╮
│ The system has three main layers...                       │
╰───────────────────────────────────────────────────────────╯
You: 
# Session ended.
```

Terminal 3 — verify thread contains both sides:
```bash
just threads
# Thread shows participants: human, architect
just thread <uuid>
# Shows human message and architect reply with correct sender → recipient headers
```

---

## Acceptance Criteria

```bash
just check    # zero ruff errors, zero pyright errors
just test     # all tests pass (previous total + new tests)
```

Manual:
- `just chat architect` opens a two-way session — human messages go to
  architect, architect replies appear in the terminal
- `just listen` prints incoming messages from any agent in real time
- `just threads` shows `Participants` column
- `just thread <uuid>` shows `sender → recipient` in each panel header
- Existing `just send` and `just run` commands unaffected
- Existing threads (pre-migration) display correctly with `sender = human`

---

## What This Task Does NOT Include

- Dynamic routing based on message content — that is Task 011b
- LLM classifier router — Task 011b
- Supervisor pattern — Task 012
- Implementer invoking Claude Code as a tool — Task 012
- `max_messages_per_thread` termination — deferred until concrete use case
- Multi-agent `agents.toml` for architect/implementer — that is configuration,
  not code; Radek sets it up after this task is merged
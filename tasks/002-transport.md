# Task 002 — Transport Layer

**File:** `tasks/002-transport.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-13  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 001 skeleton complete and merged

---

## Objective

Implement the complete transport layer: the `Message` dataclass, the `Transport`
abstract base class, the `SQLiteTransport` adapter, and the `TerminalTransport`
adapter. No agent logic. No LLM calls. No routing logic.

When complete, the transport layer is fully tested in isolation. Agents can be
built in the next task against the `Transport` ABC without touching transport code.

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — all standards, module rules, coding conventions
- `tasks/001-skeleton.md` — context for what already exists

---

## Git

Work on branch `feature/transport` created from `master` after Task 001 is merged.

```bash
git checkout master
git pull origin master
git worktree add ../multiagent-transport feature/transport
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
feat(transport): implement Message, Transport ABC, SQLiteTransport, TerminalTransport
```

Tag: none — tagging is reserved for CLI-runnable milestones.

---

## Deliverables

### Source Files

```
src/multiagent/transport/__init__.py    # exports: Transport, Message
src/multiagent/transport/base.py        # Message dataclass + Transport ABC
src/multiagent/transport/sqlite.py      # SQLiteTransport
src/multiagent/transport/terminal.py    # TerminalTransport
```

### Test Files

```
tests/unit/transport/__init__.py
tests/unit/transport/test_base.py       # Message dataclass tests
tests/unit/transport/test_sqlite.py     # SQLiteTransport tests (in-memory DB)
tests/unit/transport/test_terminal.py  # TerminalTransport tests
```

### Configuration additions to `.env.defaults`

```bash
# --- TRANSPORT ---
# Options: sqlite | terminal
TRANSPORT_BACKEND=sqlite
SQLITE_DB_PATH=data/agents.db
SQLITE_POLL_INTERVAL_SECONDS=1.0
```

### Settings additions to `src/multiagent/config/settings.py`

Add these fields to the existing `Settings` class:

```python
# Transport
transport_backend: str = Field(
    "sqlite",
    pattern="^(sqlite|terminal)$",
    description="Active transport adapter. One of: sqlite, terminal.",
)
sqlite_db_path: Path = Field(
    Path("data/agents.db"),
    description="Path to SQLite database file. Use ':memory:' for tests.",
)
sqlite_poll_interval_seconds: float = Field(
    1.0,
    gt=0,
    description="Seconds between inbox polls when no message is available.",
)
```

---

## Data Model

### `Message` Dataclass

Location: `src/multiagent/transport/base.py`

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Message:
    """A unit of communication between agents.

    This is the only type that crosses the transport/core boundary.
    Agent runners receive and produce Message objects. They never
    interact with transport internals directly.

    Addressing: to_agent accepts a single agent name, a list of agent
    names, or the broadcast sentinel "*". The transport layer resolves
    lists and "*" to individual per-recipient rows before persistence.
    After persistence and retrieval, to_agent is always a plain str.

    Timestamps: all UTC. Set by the transport at the relevant lifecycle
    event — never by agent code. created_at is the sole exception:
    it is set at object construction by the caller.

    Attributes:
        from_agent: Sending agent name, or "human" for external input.
        to_agent: Recipient — single name, list of names, or "*".
        body: Message payload — plain text.
        subject: Optional routing label. Empty string if unused.
        thread_id: UUID grouping all messages in one conversation chain.
            Pass an existing thread_id when continuing a thread.
            Defaults to a new UUID for thread-initiating messages.
        parent_id: Database id of the message this replies to.
            None for thread-initiating messages.
        id: Database-assigned integer id. None until persisted.
        created_at: UTC timestamp of object construction. Set by caller.
        sent_at: UTC timestamp set by transport.send() on persistence.
        received_at: UTC timestamp set by transport.receive() on retrieval.
        processed_at: UTC timestamp set by transport.ack() on completion.
    """

    from_agent: str
    to_agent: str | list[str]
    body: str
    subject: str = ""
    thread_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: int | None = None
    id: int | None = None
    created_at: datetime | None = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    sent_at: datetime | None = None
    received_at: datetime | None = None
    processed_at: datetime | None = None
```

---

## Transport ABC

Location: `src/multiagent/transport/base.py` (same file as `Message`)

```python
from abc import ABC, abstractmethod


class Transport(ABC):
    """Abstract port defining the message transport contract.

    All transport adapters implement this interface. Agent and runner
    code depends only on this ABC — never on concrete implementations.
    Swapping adapters requires no changes to agent code.

    Fanout: when message.to_agent is a list or "*", send() must expand
    to one delivery row per resolved recipient. Adapters own this logic.

    Timestamp ownership:
        sent_at      — set by send() on each persisted row
        received_at  — set by receive() on the returned Message
        processed_at — set by ack() on the acknowledged row
    """

    @abstractmethod
    async def receive(self, agent_name: str) -> Message | None:
        """Fetch the next unprocessed message for agent_name.

        Non-blocking. Returns None immediately if the inbox is empty.
        The caller (AgentRunner) is responsible for polling and backoff.
        Sets received_at to UTC now on the returned Message.

        Args:
            agent_name: The agent whose inbox to query.

        Returns:
            Oldest unprocessed Message for agent_name, or None.

        Raises:
            MessageReceiveError: If the backend query fails.
            TransportConnectionError: If the backend is unavailable.
        """

    @abstractmethod
    async def send(self, message: Message) -> None:
        """Deliver a message, handling fanout for lists and broadcast.

        If message.to_agent is a str: write one row.
        If message.to_agent is a list: write one row per name in list.
        If message.to_agent is "*": resolve via known_agents(), write
            one row per known agent. If known_agents() returns empty,
            log a WARNING and write zero rows — do not raise.

        Sets sent_at to UTC now on every persisted row.

        Args:
            message: Message to deliver. to_agent may be str, list, "*".

        Raises:
            MessageDeliveryError: If persistence fails.
            TransportConnectionError: If the backend is unavailable.
        """

    @abstractmethod
    async def ack(self, message_id: int) -> None:
        """Mark a message as processed. Sets processed_at to UTC now.

        After ack(), receive() will not return this message again.
        At-least-once delivery: if ack() is never called, the message
        will be re-delivered on the next receive() call.

        Args:
            message_id: The id of the Message to acknowledge.

        Raises:
            MessageAcknowledgementError: If the update cannot be persisted.
        """

    @abstractmethod
    async def known_agents(self) -> list[str]:
        """Return all agent names ever seen as to_agent recipients.

        Used internally by send() to resolve broadcast "*". Returns an
        empty list (not an error) if no messages have been persisted.

        Returns:
            Sorted list of distinct agent name strings.

        Raises:
            TransportConnectionError: If the backend is unavailable.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release all backend resources held by this instance.

        Must be idempotent — safe to call more than once.
        """
```

---

## `SQLiteTransport`

Location: `src/multiagent/transport/sqlite.py`

### Construction

```python
class SQLiteTransport(Transport):
    def __init__(self, settings: Settings) -> None:
        ...
```

Accepts `Settings`. Reads `settings.sqlite_db_path` and
`settings.sqlite_poll_interval_seconds`. Does **not** open a connection
at construction time — connection is opened lazily on first use via
`_get_connection()`.

### Connection Management

Use `aiosqlite`. WAL mode must be enabled on first connection:

```python
async def _get_connection(self) -> aiosqlite.Connection:
    if self._conn is None:
        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._ensure_schema()
    return self._conn
```

**Why WAL mode:** allows concurrent readers while a writer holds a lock.
Without this, multiple agents polling the same database cause lock
contention errors.

**Why `row_factory = aiosqlite.Row`:** enables column access by name
(`row["to_agent"]`) rather than index, making `_row_to_message()` robust
against column order changes.

### Schema

Applied by `_ensure_schema()` on first connection. The method must be
idempotent — safe to call on a database that already has the schema.

```sql
CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    from_agent    TEXT     NOT NULL,
    to_agent      TEXT     NOT NULL,
    subject       TEXT     NOT NULL DEFAULT '',
    body          TEXT     NOT NULL DEFAULT '',
    thread_id     TEXT     NOT NULL,
    parent_id     INTEGER  REFERENCES messages(id),
    created_at    TEXT     NOT NULL,
    sent_at       TEXT,
    received_at   TEXT,
    processed_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_inbox
    ON messages(to_agent, processed_at, created_at);

CREATE INDEX IF NOT EXISTS idx_thread
    ON messages(thread_id, created_at);
```

All timestamp columns are `TEXT` in ISO8601 UTC format. ISO8601 strings
sort correctly as text and round-trip through `datetime.fromisoformat()`
without loss. Never use SQLite `DATETIME` — it has no timezone awareness.

### Timestamp Serialisation

Use these two private helpers consistently throughout the module:

```python
def _to_iso(self, dt: datetime | None) -> str | None:
    """Serialise a UTC datetime to ISO8601 string for storage."""
    return dt.isoformat() if dt is not None else None

def _from_iso(self, value: str | None) -> datetime | None:
    """Deserialise an ISO8601 string from storage to UTC datetime."""
    return datetime.fromisoformat(value) if value is not None else None
```

### `_row_to_message()` Private Helper

Converts an `aiosqlite.Row` to a `Message`. Always used in `receive()`.
Keeps the row-to-object mapping in one place.

### Fanout Logic in `send()`

```python
async def send(self, message: Message) -> None:
    recipients: list[str]

    if isinstance(message.to_agent, list):
        recipients = message.to_agent
    elif message.to_agent == "*":
        recipients = await self.known_agents()
        if not recipients:
            self._log.warning(
                "broadcast_no_known_agents",
                thread_id=message.thread_id,
            )
            return
    else:
        recipients = [message.to_agent]

    now = datetime.now(timezone.utc)
    conn = await self._get_connection()

    for recipient in recipients:
        await conn.execute(
            """
            INSERT INTO messages
                (from_agent, to_agent, subject, body,
                 thread_id, parent_id, created_at, sent_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.from_agent,
                recipient,
                message.subject,
                message.body,
                message.thread_id,
                message.parent_id,
                self._to_iso(message.created_at),
                self._to_iso(now),
            ),
        )

    await conn.commit()
```

### `receive()` Query

Fetch the oldest unprocessed row for the agent. A row is unprocessed
when `processed_at IS NULL`. Set `received_at` on the row immediately
and return the populated `Message`.

```sql
SELECT * FROM messages
WHERE to_agent = ? AND processed_at IS NULL
ORDER BY created_at ASC
LIMIT 1
```

After fetching, update `received_at` in the same transaction:

```sql
UPDATE messages SET received_at = ? WHERE id = ?
```

### `close()`

```python
async def close(self) -> None:
    if self._conn is not None:
        await self._conn.close()
        self._conn = None
```

---

## `TerminalTransport`

Location: `src/multiagent/transport/terminal.py`

The terminal transport enables interactive single-agent testing without
infrastructure. It reads from `stdin` and writes to `stdout`.

### Behaviour Contract

- `receive(agent_name)`: prints a prompt `[agent_name] > ` to stdout,
  reads one line from stdin. If the line is empty or EOF, returns `None`.
  Otherwise returns a `Message` with `from_agent="human"`,
  `to_agent=agent_name`, `body=<line>`, and all four timestamps set to
  UTC now.
- `send(message)`: prints `[{message.from_agent}] → [{message.to_agent}]: {message.body}`
  to stdout. Sets `sent_at` on the message object to UTC now.
  Fanout: if `to_agent` is a list or `"*"`, print one line per recipient.
  Does not persist anything.
- `ack(message_id)`: no-op. Terminal messages have no persistence.
  Sets `processed_at` on nothing — there is no object to update.
  Must not raise.
- `known_agents()`: returns `[]`. Terminal transport has no registry.
- `close()`: no-op. No resources to release.

### stdin Handling

Use `asyncio.to_thread(input, prompt)` to avoid blocking the event loop
during interactive input:

```python
async def receive(self, agent_name: str) -> Message | None:
    try:
        line = await asyncio.to_thread(input, f"[{agent_name}] > ")
    except EOFError:
        return None
    line = line.strip()
    if not line:
        return None
    now = datetime.now(timezone.utc)
    return Message(
        from_agent="human",
        to_agent=agent_name,
        body=line,
        created_at=now,
        sent_at=now,
        received_at=now,
    )
```

---

## `__init__.py` Exports

```python
# src/multiagent/transport/__init__.py
"""Transport layer — abstract port and concrete adapters.

Public API:
    Message    — the data contract crossing the transport/core boundary
    Transport  — the abstract base class all adapters must implement
"""

from multiagent.transport.base import Message, Transport

__all__ = ["Message", "Transport"]
```

Concrete adapters (`SQLiteTransport`, `TerminalTransport`) are **not**
exported from `__init__.py`. Callers that need a concrete adapter import
it directly from its module. This keeps the public API minimal and forces
explicit import decisions.

---

## Test Requirements

All tests are unit tests. No real filesystem. SQLite tests use
`sqlite_db_path=":memory:"`. No LLM calls. No network.

### `tests/unit/transport/test_base.py` — Message dataclass

```
TestMessageDefaults
    test_thread_id_is_generated_as_uuid
    test_created_at_is_set_to_utc_now
    test_subject_defaults_to_empty_string
    test_id_defaults_to_none
    test_sent_at_defaults_to_none
    test_received_at_defaults_to_none
    test_processed_at_defaults_to_none

TestMessageAddressing
    test_to_agent_accepts_single_string
    test_to_agent_accepts_list_of_strings
    test_to_agent_accepts_broadcast_sentinel

TestMessageThreading
    test_two_messages_get_different_thread_ids
    test_thread_id_can_be_supplied_explicitly
    test_parent_id_defaults_to_none
```

### `tests/unit/transport/test_sqlite.py` — SQLiteTransport

Fixture: `sqlite_transport` — constructs `SQLiteTransport` with
`Settings(sqlite_db_path=":memory:", ...)`. Use `pytest_asyncio.fixture`.

```
TestSQLiteTransportSchema
    test_schema_created_on_first_use
    test_schema_creation_is_idempotent

TestSQLiteTransportSend
    test_send_single_recipient_persists_one_row
    test_send_sets_sent_at_on_row
    test_send_list_recipients_persists_one_row_per_recipient
    test_send_broadcast_fans_out_to_known_agents
    test_send_broadcast_with_no_known_agents_logs_warning_and_returns

TestSQLiteTransportReceive
    test_receive_returns_none_when_inbox_empty
    test_receive_returns_oldest_message_first
    test_receive_sets_received_at
    test_receive_does_not_return_processed_messages
    test_receive_only_returns_messages_for_named_agent

TestSQLiteTransportAck
    test_ack_sets_processed_at
    test_ack_prevents_redelivery_on_next_receive
    test_ack_nonexistent_id_raises_message_acknowledgement_error

TestSQLiteTransportKnownAgents
    test_known_agents_returns_empty_before_any_sends
    test_known_agents_returns_distinct_sorted_names_after_sends

TestSQLiteTransportClose
    test_close_is_idempotent
```

### `tests/unit/transport/test_terminal.py` — TerminalTransport

```
TestTerminalTransportReceive
    test_receive_returns_message_with_user_input
    test_receive_returns_none_on_empty_input
    test_receive_returns_none_on_eof
    test_receive_sets_all_timestamps_to_utc_now
    test_receive_sets_from_agent_to_human

TestTerminalTransportSend
    test_send_prints_formatted_line_to_stdout
    test_send_sets_sent_at_on_message_object

TestTerminalTransportNoOps
    test_ack_does_not_raise
    test_known_agents_returns_empty_list
    test_close_does_not_raise
```

### `tests/conftest.py` additions

Add these fixtures to the existing conftest:

```python
@pytest_asyncio.fixture
async def sqlite_transport(test_settings: Settings) -> AsyncGenerator[SQLiteTransport, None]:
    """SQLiteTransport backed by an in-memory database."""
    from multiagent.transport.sqlite import SQLiteTransport
    transport = SQLiteTransport(test_settings)
    yield transport
    await transport.close()


@pytest.fixture
def terminal_transport(test_settings: Settings) -> TerminalTransport:
    """TerminalTransport instance for testing."""
    from multiagent.transport.terminal import TerminalTransport
    return TerminalTransport()


@pytest.fixture
def sample_message() -> Message:
    """A valid Message for use in transport tests."""
    from multiagent.transport.base import Message
    return Message(
        from_agent="human",
        to_agent="researcher",
        body="What is quantum entanglement?",
        subject="research",
    )
```

---

## Implementation Order

Implement in this order. Run `just check` after each step.

1. Add transport config fields to `Settings` and `.env.defaults`
2. `src/multiagent/transport/base.py` — `Message` dataclass only
3. **Write `tests/unit/transport/test_base.py`** — TDD red phase
4. Verify `Message` tests pass — TDD green phase
5. `src/multiagent/transport/base.py` — add `Transport` ABC
6. `src/multiagent/transport/sqlite.py` — `SQLiteTransport` skeleton (class + `__init__` only)
7. **Write `tests/unit/transport/test_sqlite.py`** — TDD red phase
8. Implement `SQLiteTransport` fully — TDD green phase
9. `src/multiagent/transport/terminal.py` — `TerminalTransport` skeleton
10. **Write `tests/unit/transport/test_terminal.py`** — TDD red phase
11. Implement `TerminalTransport` fully — TDD green phase
12. `src/multiagent/transport/__init__.py`
13. Update `tests/conftest.py` with new fixtures
14. Final: `just check && just test`

---

## Acceptance Criteria

```bash
just check    # zero ruff errors, zero pyright errors
just test     # all transport unit tests pass, coverage ≥ 80% on transport/
```

All tests must pass without touching `.env` or making any network calls.
The `:memory:` SQLite path must be used in all SQLiteTransport tests.

---

## What This Task Does NOT Include

- `AgentRunner`, `LLMAgent`, or any LangGraph code
- `routing/` module
- CLI wiring — the transport is not connected to `cli/main.py` in this task
- Integration tests — deferred to the CLI wiring task when end-to-end
  pipelines can be tested meaningfully
- Agent registry — `known_agents()` uses seen-agent inference only
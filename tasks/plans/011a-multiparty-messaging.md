# Implementation Plan — Task 011a: Multi-Party Messaging (as implemented)

## Context

Enables two-way human↔agent conversation. A `listen` command polls for messages
addressed to `human`, a `chat` command provides a REPL-style session, and the
`browse_threads.py` script shows participant information.

---

## Key Finding: `sender` Already Exists as `from_agent`

The task brief asks to "add a `sender` field" — but the codebase already has
`from_agent` / `to_agent` serving this purpose. No schema migration, no model
changes, no AgentRunner changes, no send command changes needed.

---

## Files Created or Modified

| File | Action | Description |
|------|--------|-------------|
| `src/multiagent/config/settings.py` | Modified | Added `chat_reply_timeout_seconds` (120s default) |
| `.env.defaults` | Modified | Added `CHAT_REPLY_TIMEOUT_SECONDS=120` |
| `tests/conftest.py` | Modified | Added `chat_reply_timeout_seconds=5.0` to test settings |
| `src/multiagent/cli/listen.py` | Created | `listen` command — polls transport for messages to `human` |
| `src/multiagent/cli/chat.py` | Created | `chat` command — interactive REPL send+listen loop |
| `src/multiagent/cli/main.py` | Modified | Registered `listen` and `chat` commands |
| `scripts/browse_threads.py` | Modified | Added Participants column (UNION of from_agent + to_agent) |
| `justfile` | Modified | Added `listen` and `chat` targets |
| `tests/unit/cli/test_listen.py` | Created | 4 tests: prints message, marks processed, filters by thread, ctrl-c |
| `tests/unit/cli/test_chat.py` | Created | 6 tests: sends to agent, exits on empty, thread-id, ctrl-c, invalid agent |
| `tests/unit/cli/test_send.py` | Modified | Added `test_from_agent_is_human` assertion |
| `tests/unit/transport/test_sqlite.py` | Modified | Added `test_human_is_valid_recipient` |

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| No `sender` field — use existing `from_agent` | Avoids redundant field |
| `listen` uses direct SQL via aiosqlite | Needs thread filtering; follows scripts pattern |
| `chat` send side uses `transport.send()` | Standard single-recipient send |
| `chat` reply polling uses direct SQL | Same pattern as listen — thread-filtered queries |
| Participants: UNION of from_agent + to_agent | Per architect feedback — captures all participants including unresponsive agents |
| `_async_input()` helper in chat | Wraps blocking `input()` in executor to satisfy ruff ASYNC250 |
| `reply_timeout` param name | Avoids ruff ASYNC109 which flags `timeout` param in async functions |

## Architect Feedback Addressed

1. **Participants column** — Changed from `GROUP_CONCAT(DISTINCT from_agent)` to a
   subquery with `UNION` of `from_agent` and `to_agent`, ensuring agents who were
   addressed but haven't replied are still visible.

2. **Pre-implementation commit** — Staged files by name (not `git add -A`). Stray
   MagicMock files were discovered and removed in a separate commit.

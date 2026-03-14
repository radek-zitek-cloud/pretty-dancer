# Implementation Plan — Task 008: `multiagent start`

**Implementer:** Tom (Claude Code)
**Date:** 2026-03-14
**Task brief:** `tasks/008-start.md`
**Status:** IMPLEMENTED — pending merge

---

## 1. Files Created or Modified

| File | Action | Description |
|------|--------|-------------|
| `src/multiagent/cli/start.py` | **Created** | `start_command()` sync wrapper + `_start()` async impl using `asyncio.TaskGroup` |
| `src/multiagent/cli/main.py` | **Modified** | Import and register `start_command` (one import + one `app.command()` call) |
| `tests/unit/cli/test_start.py` | **Created** | 4 unit tests per brief spec |
| `tests/unit/cli/test_send.py` | **Modified** | Fixed pre-existing ruff I001 import sort issue |
| `justfile` | **Modified** | Added `start` target in the Application section |

---

## 2. Implementation Order (as executed)

1. Added `start` target to `justfile`
2. Created `tests/unit/cli/test_start.py` — 4 tests
3. Created `src/multiagent/cli/start.py` — full implementation
4. Registered `start_command` in `src/multiagent/cli/main.py`
5. Fixed lint/pyright issues in test files
6. Verified all 4 new tests pass, zero new lint/pyright errors

---

## 3. Design Decisions (from plan + architect review)

### 3.1 Windows event loop policy — NOT duplicated (approved)
`main.py:main()` already applies `WindowsSelectorEventLoopPolicy` before `app()`.
No duplication in `start_command()`.

### 3.2 `test_keyboard_interrupt_exits_zero` — direct call with `patch` (approved)
Per architect feedback, uses `unittest.mock.patch` with `side_effect=KeyboardInterrupt`
and `pytest.raises(SystemExit)` — does NOT use CliRunner.

### 3.3 `except*` syntax — Python 3.11+ (no issue)
Project requires Python 3.12.

### 3.4 Shared resources
One `AsyncSqliteSaver`, one transport, distinct `LLMAgent`/`AgentRunner` per agent.

### 3.5 `cluster_stopped` log placement
After TaskGroup try/except* block, inside checkpointer context manager.

---

## 4. Pre-existing Issues (not introduced by this task)

- **pyright:** 42 errors in `send.py`, `test_send.py`, `test_agent.py` — all pre-existing
- **test failures:** 3 pre-existing (`test_log_console_level_defaults_to_info`,
  2x `test_browse_threads` env config issues)

These prevent `just check` and `just test` from returning zero exit code, but none
are related to this task's changes.

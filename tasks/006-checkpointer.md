# Task 006 — Conversation History via LangGraph Checkpointer

**File:** `tasks/006-checkpointer.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-13  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 005 observability complete and merged to master

---

## Objective

Replace the stateless single-turn `AgentState` with LangGraph's `MessagesState` and
an `AsyncSqliteSaver` checkpointer. After this task, each agent accumulates full
conversation history per `thread_id` across calls. Progressive and conservative
agents in a circular debate will read the entire prior exchange before composing
each response.

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — all standards, module rules, coding conventions
- `tasks/003-agent-core.md` — original `AgentState` and `LLMAgent` design
- `tasks/005-observability.md` — `llm_trace` emit, which must be updated here

---

## Git

Work on branch `feature/checkpointer` created from `master`.

```bash
git checkout master
git pull origin master
git worktree add ../multiagent-checkpointer feature/checkpointer
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
feat(core): replace AgentState with MessagesState and AsyncSqliteSaver checkpointer
```

Tag: none.

---

## Deliverables

### Source Files Modified

```
pyproject.toml                        # add langgraph-checkpoint-sqlite
src/multiagent/config/settings.py     # add checkpointer_db_path
src/multiagent/core/state.py          # remove AgentState — file deleted
src/multiagent/core/agent.py          # MessagesState, checkpointer param, thread_id in run()
src/multiagent/core/runner.py         # pass msg.thread_id to agent.run()
src/multiagent/cli/run.py             # own checkpointer lifecycle with async with
```

### Test Files Modified

```
tests/conftest.py                     # add checkpointer fixture, update test_settings
tests/unit/core/test_agent.py         # update all tests for new signatures and state
tests/unit/core/test_runner.py        # update for thread_id in run()
tests/integration/test_pipeline.py   # add history continuity test
```

### Files Deleted

```
src/multiagent/core/state.py          # AgentState superseded by MessagesState
```

---

## New Dependency

```toml
# pyproject.toml
dependencies = [
    ...
    "langgraph-checkpoint-sqlite>=2.0",
]
```

Run `uv sync` after adding.

---

## Configuration

### `src/multiagent/config/settings.py`

Add one field:

```python
# Checkpointer
checkpointer_db_path: Path = Field(
    Path("data/checkpoints.db"),
    description="Path to LangGraph checkpoint database. "
                "Stores full conversation history per thread_id. "
                "Separate from the message transport database.",
)
```

### `.env.defaults`

Add:

```bash
# --- CHECKPOINTER ---
CHECKPOINTER_DB_PATH=data/checkpoints.db
```

### `.env.test`

Add:

```bash
CHECKPOINTER_DB_PATH=:memory:
```

The integration tests use an in-memory checkpointer via `MemorySaver` (see test
section). `.env.test` only affects configurations constructed from settings directly.

---

## `AgentState` — Deleted

`src/multiagent/core/state.py` is removed. `AgentState` is superseded by
`MessagesState` from LangGraph. `AgentState` was never part of the public API
and was not exported from `core/__init__.py` — no callers outside `core/agent.py`.

Delete the file. Remove any import of `AgentState` from `core/agent.py`.

---

## `LLMAgent` — Changes

### `__init__` — accept `checkpointer` parameter

```python
from langgraph.checkpoint.base import BaseCheckpointSaver

class LLMAgent:
    def __init__(
        self,
        name: str,
        settings: Settings,
        checkpointer: BaseCheckpointSaver,
    ) -> None:
```

`checkpointer` is stored as `self._checkpointer` and passed to `graph.compile()`.
The type is `BaseCheckpointSaver` — the abstract base that both `MemorySaver`
(unit tests) and `AsyncSqliteSaver` (production) implement. `LLMAgent` has no
knowledge of which concrete implementation it receives.

### `_build_graph()` — migrate to `MessagesState`

```python
from langgraph.graph import END, MessagesState, StateGraph
from langchain_core.messages import SystemMessage

def _build_graph(self) -> CompiledGraph:
    """Build the LangGraph processing graph with MessagesState.

    Uses MessagesState, which maintains a list of BaseMessage objects
    that accumulates across invocations via the checkpointer. The LLM
    receives the full message history on every call, enabling genuine
    multi-turn conversation.

    Returns:
        Compiled graph with checkpointer attached.
    """
    async def call_llm(state: MessagesState) -> MessagesState:
        self._log.debug("llm_call_start", history_length=len(state["messages"]))
        response = await self._llm.ainvoke([
            SystemMessage(content=self._system_prompt),
            *state["messages"],
        ])
        output = str(response.content)
        self._log.debug("llm_call_complete", output_chars=len(output))

        if self._settings.log_trace_llm:
            self._log.info(
                "llm_trace",
                prompt=state["messages"][-1].content,
                system_prompt=self._system_prompt,
                response=output,
                history_length=len(state["messages"]),
                output_chars=len(output),
            )

        return {"messages": [response]}

    graph: StateGraph = StateGraph(MessagesState)
    graph.add_node("llm", call_llm)
    graph.set_entry_point("llm")
    graph.add_edge("llm", END)
    return graph.compile(checkpointer=self._checkpointer)
```

**How `MessagesState` accumulation works:** The `messages` key has a built-in
list-append reducer. When the node returns `{"messages": [response]}`, LangGraph
appends the response to the existing list rather than replacing it. On the next
invocation with the same `thread_id`, the checkpointer restores the full accumulated
list. The LLM receives the entire history on every call — no manual thread
retrieval needed.

### `run()` — add `thread_id` parameter

```python
async def run(self, input_text: str, thread_id: str) -> str:
    """Process input_text with full conversation history for the thread.

    The checkpointer restores prior messages for this thread_id before
    invocation and persists the updated state after. On the first call
    for a thread_id, history is empty — behaviour is identical to the
    stateless design. Subsequent calls include the full prior exchange.

    Args:
        input_text: The message body to process.
        thread_id: Conversation thread identifier. Must match the thread_id
            on the Message that triggered this call.

    Returns:
        The LLM's response as a plain string.

    Raises:
        AgentLLMError: If the LLM API call fails.
    """
    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = await self._graph.ainvoke(
            {"messages": [HumanMessage(content=input_text)]},
            config=config,
        )
        return str(result["messages"][-1].content)
    except Exception as exc:
        self._log.error("llm_call_failed", error=str(exc), thread_id=thread_id)
        raise AgentLLMError(
            f"Agent '{self.name}' LLM call failed: {exc}"
        ) from exc
```

---

## `AgentRunner` — Changes

One line change in `run_once()`. Pass `msg.thread_id` to `agent.run()`:

```python
# BEFORE
response_text = await self._agent.run(msg.body)

# AFTER
response_text = await self._agent.run(msg.body, msg.thread_id)
```

No other changes to `AgentRunner`.

---

## `src/multiagent/cli/run.py` — Checkpointer Lifecycle

The CLI owns the checkpointer. It is constructed at process start and closed at
process exit via `async with`. `LLMAgent` receives it as a dependency.

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

async def _run(
    agent_name: str,
    settings: Settings,
    agent_config: AgentConfig,
    experiment: str,
) -> None:
    human_log, json_log = configure_logging(
        settings, agent_name=agent_name, experiment=experiment
    )
    if human_log:
        typer.echo(f"Human log : {human_log}")
    if json_log:
        typer.echo(f"JSON log  : {json_log}")

    transport = create_transport(settings)

    async with AsyncSqliteSaver.from_conn_string(
        str(settings.checkpointer_db_path)
    ) as checkpointer:
        agent = LLMAgent(agent_name, settings, checkpointer)
        runner = AgentRunner(
            agent, transport, settings, next_agent=agent_config.next_agent
        )
        log.info("agent_starting", agent=agent_name, next_agent=agent_config.next_agent)
        try:
            await runner.run_loop()
        except KeyboardInterrupt:
            log.info("agent_stopping", agent=agent_name, reason="keyboard_interrupt")
```

The `checkpointer_db_path` directory must exist before `AsyncSqliteSaver` opens
the file. Add `settings.checkpointer_db_path.parent.mkdir(parents=True, exist_ok=True)`
before the `async with` block.

---

## `tests/conftest.py` — Fixture Updates

### Update `test_settings`

Add `checkpointer_db_path`:

```python
@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        openrouter_api_key="test-key-not-real",
        transport_backend="sqlite",
        sqlite_db_path=Path(":memory:"),
        log_console_level="WARNING",
        log_human_file_enabled=False,
        log_json_file_enabled=False,
        log_trace_llm=False,
        prompts_dir=Path("tests/fixtures/prompts"),
        agents_config_path=Path("tests/fixtures/agents.toml"),
        greeting_message="test",
        greeting_secret="test-secret",
        checkpointer_db_path=Path(":memory:"),
    )
```

### Add `checkpointer` fixture

```python
from langgraph.checkpoint.memory import MemorySaver

@pytest.fixture
def checkpointer() -> MemorySaver:
    """In-memory checkpointer for unit tests.

    MemorySaver does not require async setup or teardown. It is the
    correct substitute for AsyncSqliteSaver in unit tests — same
    BaseCheckpointSaver interface, zero I/O.
    """
    return MemorySaver()
```

`MemorySaver` is constructed synchronously and requires no `async with`. Unit
tests construct `LLMAgent` directly with `MemorySaver()` — no lifecycle management
needed. This is the correct pattern for testing agent logic in isolation.

---

## Test Requirements

### `tests/unit/core/test_agent.py` — Updates

All existing tests must be updated for the new signatures. No test may construct
`LLMAgent` without passing a `checkpointer`.

```
TestLLMAgentInit
    test_loads_system_prompt_from_file              # unchanged logic, add checkpointer
    test_raises_agent_configuration_error_when_prompt_file_missing  # unchanged
    test_raises_agent_configuration_error_when_prompt_dir_missing   # unchanged
    test_name_is_set_correctly                      # unchanged

TestLLMAgentRun
    test_returns_llm_response_string                # add thread_id arg
    test_calls_llm_exactly_once_per_run             # add thread_id arg
    test_passes_system_prompt_as_system_message     # add thread_id arg
    test_passes_input_as_human_message              # add thread_id arg
    test_raises_agent_llm_error_on_llm_failure      # add thread_id arg
    test_run_is_independent_between_calls           # add thread_id arg

TestLLMAgentHistory
    test_second_call_includes_first_message_in_history
    test_different_thread_ids_have_independent_histories
    test_same_thread_id_accumulates_messages_across_calls
```

The three `TestLLMAgentHistory` tests verify the checkpointer is actually working.
They require two sequential `agent.run()` calls on the same agent instance, with
the mock LLM capturing what it was called with. Assert that on the second call,
the message list passed to the LLM contains both the first and second human messages.

### `tests/unit/core/test_runner.py` — Updates

`run_once()` now calls `agent.run(msg.body, msg.thread_id)`. Update the mock
assertions to verify `thread_id` is passed correctly:

```
TestAgentRunnerRunOnce
    test_passes_thread_id_to_agent_run              # NEW — verify thread_id forwarding
    ... (all existing tests updated for new run() signature)
```

### `tests/integration/test_pipeline.py` — New Test

```python
@pytest.mark.integration
async def test_history_accumulates_across_turns(
    integration_settings: Settings,
    shared_transport: SQLiteTransport,
) -> None:
    """Verify that conversation history accumulates across agent turns.

    Sends two messages on the same thread to the researcher agent.
    After the second call, asserts the checkpointer state for the thread
    contains more than two messages (seed + response 1 + seed 2 + response 2).

    This test makes two real LLM API calls.
    """
    checkpointer = MemorySaver()
    researcher = LLMAgent("researcher", integration_settings, checkpointer)
    runner = AgentRunner(researcher, shared_transport, integration_settings, next_agent=None)

    seed1 = Message(from_agent="human", to_agent="researcher", body="What is quantum entanglement?")
    await shared_transport.send(seed1)
    await run_until_processed(runner, count=1)

    seed2 = Message(
        from_agent="human",
        to_agent="researcher",
        body="How does that relate to quantum computing?",
        thread_id=seed1.thread_id,  # same thread
    )
    await shared_transport.send(seed2)
    await run_until_processed(runner, count=1)

    # Verify checkpointer accumulated history — state should have 4 messages:
    # HumanMessage(seed1 body) + AIMessage(response1) + HumanMessage(seed2 body) + AIMessage(response2)
    state = await checkpointer.aget({"configurable": {"thread_id": seed1.thread_id}})
    assert state is not None
    messages = state["channel_values"]["messages"]
    assert len(messages) == 4
    # Never assert on message content — LLM output is non-deterministic
```

---

## Implementation Order

1. Add `langgraph-checkpoint-sqlite>=2.0` to `pyproject.toml` → `uv sync`
2. Add `checkpointer_db_path` to `Settings`, `.env.defaults`, `.env.test`
3. Update `test_settings` fixture — add `checkpointer_db_path`
4. Add `checkpointer` fixture to `tests/conftest.py`
5. Run `just check && just test` — confirm no regressions
6. Delete `src/multiagent/core/state.py`
7. Update `src/multiagent/core/agent.py`:
   - Remove `AgentState` import
   - Add `checkpointer` parameter to `__init__`
   - Migrate `_build_graph()` to `MessagesState`
   - Add `thread_id` to `run()`
   - Update `llm_trace` emit for `MessagesState` fields
8. **TDD red phase** — update all existing `test_agent.py` tests for new signatures.
   Verify `TestLLMAgentInit` tests pass (no LLM needed).
   Verify `TestLLMAgentRun` tests fail with updated signatures.
   Write `TestLLMAgentHistory` tests — verify they fail.
9. **TDD green phase** — all agent tests pass.
10. Update `src/multiagent/core/runner.py` — pass `msg.thread_id` to `agent.run()`
11. Update `tests/unit/core/test_runner.py` — add `test_passes_thread_id_to_agent_run`
12. Verify all runner tests pass.
13. Update `src/multiagent/cli/run.py` — `async with AsyncSqliteSaver` lifecycle
14. Run `just check && just test` — all unit tests pass
15. Add history test to `tests/integration/test_pipeline.py`
16. Run `just test-integration` — all integration tests pass
17. Manual end-to-end verification (see below)

---

## Module Boundary Verification

`core/agent.py` may import `BaseCheckpointSaver` from `langgraph.checkpoint.base` —
this is a LangGraph internal type, not a transport type. The module boundary rule
(no `transport/` imports in `core/`) is unaffected.

`cli/run.py` imports `AsyncSqliteSaver` from `langgraph.checkpoint.sqlite.aio` —
CLI may import anything.

Verify after implementation:

```bash
grep -r "from multiagent.transport" src/multiagent/core/   # must return nothing
grep -r "import aiosqlite" src/multiagent/core/            # must return nothing
```

---

## Manual End-to-End Verification

```bash
# Run the circular debate with two agents
just run progressive
just run conservative   # second terminal

# Inject the opening argument
just send progressive "Should the minimum wage be raised to $20 nationally? Make the opening progressive argument."

# Let 3-4 rounds complete, then Ctrl-C both terminals.

# Inspect the thread — should show full back-and-forth
just thread <thread_id>

# Verify checkpoints were persisted
sqlite3 data/checkpoints.db ".tables"         # should show checkpoint tables
sqlite3 data/checkpoints.db "SELECT thread_id, COUNT(*) FROM checkpoints GROUP BY thread_id;"

# Restart one agent and inject another message on the same thread_id
just run progressive
just send progressive "<body>" --thread-id <thread_id>   # if send supports this, else manually
```

Note: `send` does not currently support specifying an existing `thread_id` — a new
thread is always created. The integration test verifies history within a single
process run. End-to-end cross-process history persistence is validated by the
SQLite checkpoint inspection above.

---

## Acceptance Criteria

```bash
just check          # zero ruff errors, zero pyright errors
just test           # all unit tests pass (previous total + 3 history + 1 runner = 4 new)
just test-integration   # all integration tests pass including history test
```

Manual:
- `just thread <thread_id>` shows full multi-turn debate in order — confirmed
- `sqlite3 data/checkpoints.db ".tables"` shows checkpoint tables — confirmed
- `grep -r "from multiagent.transport" src/multiagent/core/` returns nothing — confirmed

---

## What This Task Does NOT Include

- Cross-process thread resumption via `send` (no `--thread-id` flag on `send` command)
- Checkpoint pruning or TTL
- Multiple concurrent threads per agent
- Supervisor pattern or multi-agent orchestration within one process
- Memory summarisation for very long threads
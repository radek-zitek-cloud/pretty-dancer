# Task 003 — Agent Core

**File:** `tasks/003-agent-core.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-13  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 002 transport layer complete and merged to master

---

## Objective

Implement the agent core: `LLMAgent` and `AgentRunner`. These are the two classes
that sit between the transport layer and the LLM. When complete, an agent can be
constructed, handed a transport, and will poll for messages, call the LLM, and
route responses — all fully testable with mocked LLM calls and no real API
invocations in unit tests.

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — all standards, module rules, coding conventions
- `tasks/002-transport.md` — what the transport layer provides
- `tasks/001-skeleton.md` — what the skeleton provides

---

## Git

Work on branch `feature/agent-core` created from `master`.

```bash
git checkout master
git pull origin master
git worktree add ../multiagent-agent-core feature/agent-core
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
feat(core): implement LLMAgent with prompt loading and AgentRunner with retry
```

Tag: none — reserved for CLI-runnable milestones.

---

## Deliverables

### Source Files

```
src/multiagent/core/__init__.py       # exports: LLMAgent, AgentRunner
src/multiagent/core/state.py          # AgentState TypedDict
src/multiagent/core/agent.py          # LLMAgent class
src/multiagent/core/runner.py         # AgentRunner class
prompts/researcher.md                 # example researcher system prompt
prompts/critic.md                     # example critic system prompt
```

### Test Files

```
tests/unit/core/__init__.py
tests/unit/core/test_agent.py         # LLMAgent tests — LLM mocked
tests/unit/core/test_runner.py        # AgentRunner tests — LLM + transport mocked
```

### Configuration Additions

**`src/multiagent/config/settings.py`** — add `prompts_dir` field:

```python
# Prompts
prompts_dir: Path = Field(
    Path("prompts"),
    description="Directory containing agent system prompt .md files. "
                "Each agent loads {prompts_dir}/{agent_name}.md at construction.",
)
```

**`.env.defaults`** — add:

```bash
# --- PROMPTS ---
PROMPTS_DIR=prompts
```

**`.env.test`** — add:

```bash
PROMPTS_DIR=tests/fixtures/prompts
```

**`tests/fixtures/prompts/`** — create this directory with two fixture prompt files:

```
tests/fixtures/prompts/
├── researcher.md     # content: "You are a test researcher agent."
└── critic.md         # content: "You are a test critic agent."
```

These fixture prompts are used exclusively in unit tests. They are committed to git.
Unit tests must never read from the real `prompts/` directory.

---

## `AgentState` TypedDict

Location: `src/multiagent/core/state.py`

```python
from typing import TypedDict


class AgentState(TypedDict):
    """Typed state passed through the LangGraph agent graph.

    This is the only state structure used by LLMAgent's graph. It is
    intentionally minimal for the stateless PoC. Conversation history
    and memory will be added when LangGraph checkpointers are introduced.

    Attributes:
        input: The raw message body the agent will process.
        output: The agent's response after LLM invocation. Empty string
            until the llm node completes.
    """

    input: str
    output: str
```

---

## `LLMAgent`

Location: `src/multiagent/core/agent.py`

### Design Constraints

- `LLMAgent` has **zero knowledge** of `Transport`, `Message`, or `AgentRunner`.
  It imports nothing from `multiagent.transport`. This is an absolute rule.
- The public interface is exactly one method: `async def run(input_text: str) -> str`.
- System prompt is loaded from a `.md` file at construction via `_load_prompt()`.
- The LangGraph graph is built once at construction and reused for every `run()` call.
- Stateless — no conversation history, no memory between calls.

### Construction

```python
class LLMAgent:
    def __init__(self, name: str, settings: Settings) -> None:
```

`name` is the agent's unique identifier. It is used to:
1. Locate the prompt file: `{settings.prompts_dir}/{name}.md`
2. Bind to the structured logger: `log.bind(agent=name)`

The `system_prompt` is not passed by the caller — it is loaded internally.

### `_load_prompt()` — Private Method

```python
def _load_prompt(self, name: str, prompts_dir: Path) -> str:
    """Load the system prompt from {prompts_dir}/{name}.md.

    Reads the file contents and strips leading/trailing whitespace.
    The entire file content is the system prompt — no parsing is
    performed at this stage.

    # TODO: parse YAML frontmatter when structured prompts are introduced.
    #       Frontmatter will carry metadata (version, tags, model hints).
    #       Body after frontmatter delimiter (---) becomes the prompt text.

    Args:
        name: Agent name. Used to construct the filename.
        prompts_dir: Directory containing prompt files.

    Returns:
        System prompt string with whitespace stripped.

    Raises:
        AgentConfigurationError: If the prompt file does not exist or
            cannot be read.
    """
    prompt_path = prompts_dir / f"{name}.md"
    try:
        return prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise AgentConfigurationError(
            f"Prompt file not found for agent '{name}': {prompt_path}"
        ) from None
    except OSError as exc:
        raise AgentConfigurationError(
            f"Failed to read prompt file for agent '{name}': {exc}"
        ) from exc
```

**The `TODO` comment is mandatory.** It is the extension point marker for
frontmatter parsing. Do not remove it or implement it — leave it exactly as shown.

### `_build_graph()` — Private Method

Constructs and compiles the LangGraph graph. Called once during `__init__`.

```python
def _build_graph(self) -> CompiledGraph:
    """Build the single-node LangGraph processing graph.

    The graph is a single 'llm' node that calls the LLM with the
    agent's system prompt and the input from state. Output is written
    back to state.

    This graph is intentionally minimal. It will grow to include tool
    nodes, memory, and conditional routing as requirements evolve.
    The stateless design here maps cleanly to LangGraph checkpointers
    when conversation history is introduced.

    Returns:
        Compiled LangGraph graph ready for async invocation.
    """
    async def call_llm(state: AgentState) -> AgentState:
        self._log.debug("llm_call_start", input_chars=len(state["input"]))
        response = await self._llm.ainvoke([
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=state["input"]),
        ])
        output = str(response.content)
        self._log.debug("llm_call_complete", output_chars=len(output))
        return {"input": state["input"], "output": output}

    graph: StateGraph = StateGraph(AgentState)
    graph.add_node("llm", call_llm)
    graph.set_entry_point("llm")
    graph.add_edge("llm", END)
    return graph.compile()
```

### LLMAgent Construction — LLM Client

Use `ChatOpenAI` from `langchain-openai` pointed at the OpenRouter base URL:

```python
from langchain_openai import ChatOpenAI

self._llm = ChatOpenAI(
    model=settings.llm_model,               # e.g. "anthropic/claude-sonnet-4-5"
    max_tokens=settings.llm_max_tokens,
    timeout=settings.llm_timeout_seconds,
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url,   # "https://openrouter.ai/api/v1"
)
```

OpenRouter's API is fully OpenAI-compatible. `ChatOpenAI` requires only `base_url`
and `api_key` overrides to route through OpenRouter. No other client changes are
needed. The model string uses OpenRouter's routing format: `provider/model-name`.

### `run()` — Public Method

```python
async def run(self, input_text: str) -> str:
    """Process input_text through the LangGraph graph and return the response.

    This is the complete public interface of LLMAgent. String in,
    string out. No I/O, no transport, no side effects.

    Args:
        input_text: The message body to process.

    Returns:
        The LLM's response as a plain string.

    Raises:
        AgentLLMError: If the LLM API call fails for any reason.
    """
    try:
        result = await self._graph.ainvoke(
            {"input": input_text, "output": ""}
        )
        return result["output"]
    except Exception as exc:
        self._log.error("llm_call_failed", error=str(exc))
        raise AgentLLMError(
            f"Agent '{self.name}' LLM call failed: {exc}"
        ) from exc
```

---

## `AgentRunner`

Location: `src/multiagent/core/runner.py`

### Design Constraints

- `AgentRunner` is the **only** component that holds references to both
  `LLMAgent` and `Transport`. This is the single integration point.
- `LLMAgent` does not know about `AgentRunner`.
- `Transport` does not know about `AgentRunner`.
- Neither knows about each other.

### Construction

```python
class AgentRunner:
    def __init__(
        self,
        agent: LLMAgent,
        transport: Transport,
        settings: Settings,
        next_agent: str | None = None,
    ) -> None:
```

`next_agent` is the name of the agent to forward responses to. `None` means
this is a terminal agent — responses are logged but not forwarded.

### `run_once()` — Process One Message

```python
async def run_once(self) -> bool:
    """Fetch and process one message from the transport inbox.

    Implements the full message lifecycle:
        1. receive() — fetch next message, return False if inbox empty
        2. agent.run() — call LLM with message body, with retry on failure
        3. ack() — mark message as processed
        4. send() — forward response to next_agent if configured

    Returns:
        True if a message was processed. False if the inbox was empty.

    Raises:
        AgentLLMError: If all retry attempts are exhausted.
        TransportError: If transport operations fail unrecoverably.
    """
```

### Retry Logic in `run_once()`

Retry applies to the `agent.run()` call only — not to transport operations.
Transport failures surface immediately as exceptions.

```python
last_exc: Exception | None = None

for attempt in range(1, self._max_retries + 2):  # +2: retries + initial attempt
    try:
        response_text = await self._agent.run(msg.body)
        break
    except AgentLLMError as exc:
        last_exc = exc
        if attempt <= self._max_retries:
            wait = self._retry_backoff * (2 ** (attempt - 1))  # exponential backoff
            self._log.warning(
                "llm_retry",
                attempt=attempt,
                max_retries=self._max_retries,
                wait_seconds=wait,
            )
            await asyncio.sleep(wait)
        else:
            self._log.error("llm_retries_exhausted", attempts=attempt)
            raise
```

Backoff sequence for `agent_retry_backoff_seconds=2.0`:
- Attempt 1 fails → wait 2.0s
- Attempt 2 fails → wait 4.0s
- Attempt 3 fails → wait 8.0s
- Attempt 4 fails → raise `AgentLLMError`

### `run_loop()` — Polling Loop

```python
async def run_loop(self) -> None:
    """Run the agent polling loop indefinitely.

    Polls the transport inbox at poll_interval when empty. Processes
    messages immediately when available. Exits cleanly on
    asyncio.CancelledError — the expected shutdown signal.

    This method never returns normally. It is intended to run as a
    long-lived asyncio task, cancelled from outside when shutdown
    is required.
    """
    self._log.info("agent_runner_started", next_agent=self._next_agent)
    try:
        while True:
            processed = await self.run_once()
            if not processed:
                self._log.debug(
                    "inbox_empty",
                    poll_interval=self._poll_interval,
                )
                await asyncio.sleep(self._poll_interval)
    except asyncio.CancelledError:
        self._log.info("agent_runner_stopped")
        raise  # always re-raise CancelledError
```

### Message Forwarding in `run_once()`

After successful `ack()`, if `next_agent` is set:

```python
if self._next_agent:
    await self._transport.send(Message(
        from_agent=self._agent.name,
        to_agent=self._next_agent,
        body=response_text,
        subject=msg.subject,
        thread_id=msg.thread_id,
        parent_id=msg.id,
    ))
    op_log.info("message_forwarded", to_agent=self._next_agent)
```

`thread_id` is **always preserved** from the incoming message. `parent_id` is
set to the processed message's `id`. This maintains the conversation lineage
in the messages table.

---

## Prompt Files

### `prompts/researcher.md`

```markdown
You are a research agent in a multi-agent system. Your role is to analyse
the input you receive and produce a clear, factual, well-structured response.

Focus on accuracy. Be concise. Do not speculate beyond the available evidence.
Your output will be reviewed by a critic agent.
```

### `prompts/critic.md`

```markdown
You are a critic agent in a multi-agent system. Your role is to evaluate
the research presented to you and identify weaknesses, gaps, or unsupported
claims.

Be constructive and specific. Cite the exact claim you are questioning.
Do not rewrite the research — only critique it.
```

These are real prompts used when the system runs end-to-end. They are committed
to git. Iterate on their content freely — they are not code.

---

## Test Requirements

### Mock Strategy

All unit tests mock at the `ChatAnthropic.ainvoke` level using `pytest-mock`.
The mock returns a deterministic object with a `.content` attribute.
No real LLM calls. No real transport I/O in agent tests.

**Standard LLM mock fixture** — add to `tests/conftest.py`:

```python
@pytest.fixture
def mock_llm_response() -> str:
    return "Mocked LLM response for testing."


@pytest.fixture
def mock_llm(mocker: MockerFixture, mock_llm_response: str) -> AsyncMock:
    """Mock ChatOpenAI.ainvoke to return a deterministic response.

    Intercepts at the LangChain level so the full LangGraph graph
    executes — only the actual HTTP call is replaced.

    The mock returns an object with a .content attribute, matching
    the real ChatOpenAI response structure.
    """
    mock = AsyncMock(
        return_value=type("AIMessage", (), {"content": mock_llm_response})()
    )
    mocker.patch(
        "langchain_openai.ChatOpenAI.ainvoke",
        side_effect=mock,
    )
    return mock
```

### `tests/unit/core/test_agent.py`

```
TestLLMAgentInit
    test_loads_system_prompt_from_file
    test_raises_agent_configuration_error_when_prompt_file_missing
    test_raises_agent_configuration_error_when_prompt_dir_missing
    test_name_is_set_correctly

TestLLMAgentRun
    test_returns_llm_response_string
    test_calls_llm_exactly_once_per_run
    test_passes_system_prompt_as_system_message
    test_passes_input_as_human_message
    test_raises_agent_llm_error_on_llm_failure
    test_run_is_independent_between_calls  # stateless verification
```

### `tests/unit/core/test_runner.py`

Transport is mocked using `AsyncMock` — no real SQLite, no real LLM.

```
TestAgentRunnerRunOnce
    test_returns_false_when_inbox_empty
    test_returns_true_when_message_processed
    test_calls_agent_run_with_message_body
    test_acks_message_after_successful_processing
    test_forwards_response_to_next_agent_when_configured
    test_does_not_forward_when_next_agent_is_none
    test_preserves_thread_id_in_forwarded_message
    test_sets_parent_id_in_forwarded_message

TestAgentRunnerRetry
    test_retries_on_agent_llm_error
    test_succeeds_after_transient_failure
    test_raises_after_max_retries_exhausted
    test_exponential_backoff_between_retries

TestAgentRunnerRunLoop
    test_loop_exits_on_cancelled_error
    test_loop_sleeps_when_inbox_empty
    test_loop_processes_messages_without_sleep_when_inbox_has_messages
```

### Fixture for `test_agent.py`

The agent tests need a `test_settings` that points `prompts_dir` at the
fixture prompts directory, not the real `prompts/`. Add to `tests/conftest.py`:

```python
@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Settings with prompts_dir pointed at test fixtures.

    Uses the committed fixture prompts in tests/fixtures/prompts/
    rather than the real prompts/ directory, ensuring agent tests
    are independent of real prompt content.
    """
    return Settings(
        openrouter_api_key="test-key-not-real",
        transport_backend="sqlite",
        sqlite_db_path=Path(":memory:"),
        log_level="WARNING",
        log_format="console",
        prompts_dir=Path("tests/fixtures/prompts"),
        greeting_message="test",
        greeting_secret="test-secret",
    )
```

**Note:** This replaces the existing `test_settings` fixture from Task 001.
Update it in-place — do not create a second fixture with the same name.
Verify all existing tests still pass after the update.

---

## Implementation Order

Implement in this order. Run `just check` after each step.

1. Add `prompts_dir` to `Settings`, `.env.defaults`, `.env.test`
2. Update `test_settings` fixture with `prompts_dir` field
3. Run `just check && just test` — verify no regressions from settings change
4. Create `tests/fixtures/prompts/researcher.md` and `critic.md`
5. Create `prompts/researcher.md` and `prompts/critic.md` (real prompts)
6. `src/multiagent/core/state.py` — `AgentState` TypedDict
7. `src/multiagent/core/agent.py` — `LLMAgent` skeleton:
   class definition, `__init__`, `_load_prompt()`, `_build_graph()`.
   `run()` stubbed as `raise NotImplementedError`.
8. **Write `tests/unit/core/test_agent.py`** — TDD red phase.
   Verify `TestLLMAgentInit` tests pass (no LLM needed).
   Verify `TestLLMAgentRun` tests fail with `NotImplementedError`.
9. Implement `run()` — TDD green phase. All agent tests must pass.
10. `src/multiagent/core/runner.py` — `AgentRunner` skeleton:
    class definition, `__init__`. `run_once()` and `run_loop()` stubbed.
11. **Write `tests/unit/core/test_runner.py`** — TDD red phase.
    Verify tests fail with `NotImplementedError`.
12. Implement `run_once()` and `run_loop()` — TDD green phase.
13. `src/multiagent/core/__init__.py` — exports
14. Add `mock_llm`, `mock_llm_response` fixtures to `tests/conftest.py`
15. Final: `just check && just test`

---

## `__init__.py` Exports

```python
# src/multiagent/core/__init__.py
"""Agent core — LLMAgent and AgentRunner.

Public API:
    LLMAgent     — LLM-powered agent, transport-agnostic
    AgentRunner  — connects an LLMAgent to a Transport
"""

from multiagent.core.agent import LLMAgent
from multiagent.core.runner import AgentRunner

__all__ = ["LLMAgent", "AgentRunner"]
```

`AgentState` is not exported — it is an internal implementation detail
of the LangGraph graph and should not be part of the public API.

---

## Module Boundary Verification

`pyright` will catch import violations, but Tom must also verify manually
that these imports do not appear anywhere in `core/`:

```
# These imports must NEVER appear in src/multiagent/core/
from multiagent.transport import ...
from multiagent.transport.sqlite import ...
from multiagent.transport.terminal import ...
import aiosqlite
```

If any of these appear, it is an architectural violation. Stop and flag it.

---

## Acceptance Criteria

```bash
just check    # zero ruff errors, zero pyright errors
just test     # all unit tests pass (48 existing + 23 new = 71 total)
```

- All 10 agent tests pass with mocked LLM
- All 13 runner tests pass with mocked LLM and mocked transport
- No test reads from the real `prompts/` directory
- No test makes a real LLM API call
- `core/` contains zero imports from `transport/`

---

## What This Task Does NOT Include

- CLI wiring — `LLMAgent` and `AgentRunner` are not connected to `cli/main.py`
- Integration tests — deferred to Task 004 when the CLI can run an end-to-end pipeline
- Routing module — static `next_agent` only for now
- Frontmatter parsing in prompt files — `TODO` comment marks the extension point
- Conversation history — stateless design is intentional; checkpointer comes later
- Agent registry — out of scope for this task
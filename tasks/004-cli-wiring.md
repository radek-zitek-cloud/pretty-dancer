# Task 004 — CLI Wiring

**File:** `tasks/004-cli-wiring.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-13  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 003 agent core complete and merged to master

---

## Objective

Wire `LLMAgent`, `AgentRunner`, and the transport layer together into a runnable CLI
application. When this task is complete, the full researcher → critic pipeline can be
started with two terminal commands and tested automatically with a single pytest run.

This is the first task that produces a runnable, observable system.

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — all standards, module rules, coding conventions
- `tasks/003-agent-core.md` — what the agent core provides
- `tasks/002-transport.md` — what the transport layer provides

---

## Git

Work on branch `feature/cli-wiring` created from `master`.

```bash
git checkout master
git pull origin master
git worktree add ../multiagent-cli-wiring feature/cli-wiring
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
feat(cli): wire LLMAgent and AgentRunner into runnable typer CLI
```

Tag the final commit — this is the first runnable milestone:

```bash
git tag v0.1.0-poc
```

---

## Deliverables

### Source Files

```
agents.toml                               # agent wiring configuration — committed to git
src/multiagent/config/agents.py           # AgentConfig dataclass + load_agents_config()
src/multiagent/config/__init__.py         # update exports: add AgentConfig, load_agents_config
src/multiagent/cli/main.py                # rewrite: typer app with run and send commands
src/multiagent/cli/run.py                 # implementation of `multiagent run <agent-name>`
src/multiagent/cli/send.py                # implementation of `multiagent send <agent> <body>`
```

### Test Files

```
tests/unit/config/test_agents.py          # unit tests for load_agents_config
tests/integration/conftest.py             # integration-specific fixtures
tests/integration/test_pipeline.py        # full researcher → critic pipeline test
```

### Configuration Additions

**`src/multiagent/config/settings.py`** — add `agents_config_path` field:

```python
# Agent wiring
agents_config_path: Path = Field(
    Path("agents.toml"),
    description="Path to the agents configuration file. "
                "Declares all agents and their next_agent routing.",
)
```

**`.env.defaults`** — add:

```bash
# --- AGENT WIRING ---
AGENTS_CONFIG_PATH=agents.toml
```

**`.env.test`** — add:

```bash
AGENTS_CONFIG_PATH=tests/fixtures/agents.toml
```

**`tests/fixtures/agents.toml`** — create for unit tests:

```toml
[agents.researcher]
next_agent = "critic"

[agents.critic]
# no next_agent — terminal agent
```

This fixture file is used exclusively in unit tests. It is committed to git.

---

## `agents.toml` — Agent Wiring Configuration

Location: repo root. Committed to git. This is the single source of truth for
which agents exist, and how they are chained.

```toml
# agents.toml
# Declares all agents in the system and their routing.
# next_agent: name of the agent to forward responses to.
#             Omit or leave unset for terminal agents.

[agents.researcher]
next_agent = "critic"

[agents.critic]
# Terminal agent — responses are logged but not forwarded.
```

### Schema Rules

- Section key is the agent name: `[agents.<name>]`
- `next_agent` is optional. Absent means terminal.
- Names must be non-empty strings matching the filename in `prompts/`.
- Circular chains are not validated at load time — they are a configuration error
  that surfaces at runtime. Document this limitation clearly in a comment.

---

## `AgentConfig` Dataclass

Location: `src/multiagent/config/agents.py`

```python
from dataclasses import dataclass
from pathlib import Path
import tomllib

from multiagent.exceptions import InvalidConfigurationError


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for a single agent loaded from agents.toml.

    Attributes:
        name: Unique agent identifier. Used to locate prompt file and
            receive messages from transport.
        next_agent: Name of the agent to forward responses to. None
            means this is a terminal agent — responses are not forwarded.
    """

    name: str
    next_agent: str | None = None
```

### `load_agents_config()` — Module-Level Function

```python
def load_agents_config(config_path: Path) -> dict[str, AgentConfig]:
    """Load agent wiring configuration from a TOML file.

    Reads the agents.toml file and returns a mapping of agent name to
    AgentConfig. The file must exist and contain a valid [agents] table.

    Args:
        config_path: Path to the agents TOML configuration file.

    Returns:
        Dict mapping agent name (str) to AgentConfig. Keys are agent names
        as declared in the [agents.<name>] sections.

    Raises:
        InvalidConfigurationError: If the file is missing, malformed, or
            contains no [agents] table.

    Example:
        >>> configs = load_agents_config(Path("agents.toml"))
        >>> configs["researcher"].next_agent
        'critic'
    """
    try:
        raw = config_path.read_bytes()
    except FileNotFoundError:
        raise InvalidConfigurationError(
            f"Agents config file not found: {config_path}"
        ) from None
    except OSError as exc:
        raise InvalidConfigurationError(
            f"Failed to read agents config file: {exc}"
        ) from exc

    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise InvalidConfigurationError(
            f"Agents config file is not valid TOML: {exc}"
        ) from exc

    agents_table = data.get("agents")
    if not agents_table or not isinstance(agents_table, dict):
        raise InvalidConfigurationError(
            f"Agents config file must contain an [agents] table: {config_path}"
        )

    return {
        name: AgentConfig(
            name=name,
            next_agent=section.get("next_agent"),
        )
        for name, section in agents_table.items()
    }
```

### Why `tomllib` and not a third-party library

`tomllib` is in the Python 3.12 standard library. Zero new dependency.
`tomllib` is read-only (no write support) which is exactly what is needed here —
the config file is authored by humans, not written by the application.

---

## CLI Structure — Typer App

### `src/multiagent/cli/main.py` — App Definition

This file is rewritten from the Task 001 hello-world. It defines the typer app
and registers the two commands. It contains no business logic.

```python
"""CLI entry point for the multiagent system.

Commands:
    run  — Start a named agent and poll for messages.
    send — Inject a message into the transport for a named agent.
"""

import typer

app = typer.Typer(
    name="multiagent",
    help="Multi-agent LLM system.",
    no_args_is_help=True,
    add_completion=False,
)


def main() -> None:
    """Entry point called by `[project.scripts]` in pyproject.toml."""
    app()
```

Import and register commands from `run.py` and `send.py` after defining `app`:

```python
from multiagent.cli import run as _run_module   # noqa: E402  (import after app)
from multiagent.cli import send as _send_module # noqa: E402

app.command()(run_command)
app.command()(send_command)
```

The exact import pattern typer uses for command registration is flexible — use
whichever pattern keeps `main.py` minimal and `run.py`/`send.py` as standalone
modules that each define one command function.

### `src/multiagent/cli/run.py` — `run` Command

```python
async def run_command(
    agent_name: str = typer.Argument(..., help="Name of the agent to run."),
) -> None:
    """Start a named agent and poll for messages indefinitely.

    Loads settings and agent configuration, constructs the transport,
    and starts the AgentRunner polling loop. Exits cleanly on Ctrl-C.

    Args:
        agent_name: The agent name as declared in agents.toml.
    """
```

Implementation steps inside `run_command`:

1. Load settings via `load_settings()`
2. Configure logging via `configure_logging(settings)`
3. Load agent configs via `load_agents_config(settings.agents_config_path)`
4. Validate `agent_name` exists in configs — raise `typer.BadParameter` if not
5. Construct transport from `settings.transport_backend`
6. Construct `LLMAgent(agent_name, settings)`
7. Construct `AgentRunner(agent, transport, settings, next_agent=config.next_agent)`
8. Call `asyncio.run(runner.run_loop())`
9. Catch `KeyboardInterrupt` cleanly — log shutdown, exit 0

### `src/multiagent/cli/send.py` — `send` Command

```python
def send_command(
    agent_name: str = typer.Argument(..., help="Name of the agent to send to."),
    body: str = typer.Argument(..., help="Message body text."),
) -> None:
    """Inject a message into the transport addressed to a named agent.

    Creates a new message thread and delivers the message body to the
    named agent's inbox. Prints the assigned thread_id on success.

    Args:
        agent_name: The target agent name as declared in agents.toml.
        body: The message body to deliver.
    """
```

Implementation steps:

1. Load settings
2. Load agent configs — validate `agent_name` exists
3. Construct transport
4. Construct `Message(from_agent="human", to_agent=agent_name, body=body)`
5. `asyncio.run(transport.send(message))`
6. Print: `typer.echo(f"Sent to {agent_name}. Thread: {message.thread_id}")`

`send` is synchronous from the user's perspective — it delivers one message and
exits immediately. No polling loop.

### `pyproject.toml` — Entry Point Update

The Task 001 skeleton registered `main:main`. Update to the typer app:

```toml
[project.scripts]
multiagent = "multiagent.cli.main:main"
```

This is already the correct form if Task 001 registered it this way. Verify and
update if needed.

---

## Transport Construction — Factory Pattern

Both `run` and `send` need to construct the correct transport based on
`settings.transport_backend`. Introduce a factory function to avoid duplicating
this logic:

Location: `src/multiagent/transport/__init__.py` — add alongside existing exports:

```python
def create_transport(settings: Settings) -> Transport:
    """Construct the configured transport adapter.

    Reads settings.transport_backend and returns the appropriate
    Transport implementation. The transport is not yet connected —
    call connect() if the implementation requires it, or rely on
    lazy initialisation.

    Args:
        settings: Validated application settings.

    Returns:
        Configured Transport instance.

    Raises:
        InvalidConfigurationError: If transport_backend is unrecognised.
    """
    if settings.transport_backend == "sqlite":
        from multiagent.transport.sqlite import SQLiteTransport
        return SQLiteTransport(settings)
    if settings.transport_backend == "terminal":
        from multiagent.transport.terminal import TerminalTransport
        return TerminalTransport(settings)
    raise InvalidConfigurationError(
        f"Unknown transport backend: {settings.transport_backend}"
    )
```

Both `run.py` and `send.py` call `create_transport(settings)`. No direct imports
of `SQLiteTransport` or `TerminalTransport` in CLI modules.

---

## Usage — Two Terminals

After `uv run multiagent send researcher "What is quantum entanglement?"`:

**Terminal 1:**
```bash
just run critic
# or: uv run multiagent run critic
```

**Terminal 2:**
```bash
just run researcher
# or: uv run multiagent run researcher
```

**Terminal 3 (inject message):**
```bash
just send researcher "What is quantum entanglement?"
# or: uv run multiagent send researcher "What is quantum entanglement?"
```

The message flows: human → researcher → critic (terminal). Both agent terminals
show structured log output as messages are received and processed.

---

## Integration Tests

### Strategy

Both agents run as concurrent `asyncio.Task` objects within a single pytest
process. They share one `SQLiteTransport` instance backed by an in-memory
SQLite database. No subprocesses. No real file I/O. Real LLM calls only.

### `tests/integration/conftest.py`

```python
import pytest
import pytest_asyncio
from pathlib import Path
from multiagent.config import Settings
from multiagent.transport.sqlite import SQLiteTransport


@pytest_asyncio.fixture
async def integration_settings() -> Settings:
    """Settings for integration tests — real API key, in-memory transport."""
    return Settings(
        openrouter_api_key=...,   # loaded from real .env via Settings()
        sqlite_db_path=Path(":memory:"),
        log_level="WARNING",
        agents_config_path=Path("agents.toml"),  # real agents.toml
        prompts_dir=Path("prompts"),              # real prompts/
    )


@pytest_asyncio.fixture
async def shared_transport(integration_settings: Settings) -> SQLiteTransport:
    """A single SQLiteTransport instance shared between all agents in a test.

    In-memory SQLite — all data is lost when the fixture goes out of scope.
    Both runner fixtures receive this same instance so they share one DB.
    """
    transport = SQLiteTransport(integration_settings)
    await transport.connect()
    yield transport
    await transport.close()
```

### `tests/integration/test_pipeline.py`

```python
import asyncio
import pytest
import pytest_asyncio
from multiagent.core.agent import LLMAgent
from multiagent.core.runner import AgentRunner
from multiagent.transport.base import Message
from multiagent.transport.sqlite import SQLiteTransport
from multiagent.config import Settings


async def run_until_processed(
    runner: AgentRunner,
    count: int = 1,
    timeout: float = 60.0,
) -> None:
    """Drive a runner until it has processed `count` messages or timeout expires.

    Args:
        runner: The AgentRunner to drive.
        count: Number of messages to process before returning.
        timeout: Maximum seconds to wait before raising TimeoutError.

    Raises:
        TimeoutError: If `count` messages are not processed within `timeout` seconds.
    """
    processed = 0
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while processed < count:
        if loop.time() > deadline:
            raise TimeoutError(
                f"Runner for '{runner.agent.name}' did not process "
                f"{count} message(s) within {timeout}s"
            )
        did_process = await runner.run_once()
        if did_process:
            processed += 1
        else:
            await asyncio.sleep(0.1)


@pytest.mark.integration
async def test_researcher_critic_pipeline(
    integration_settings: Settings,
    shared_transport: SQLiteTransport,
) -> None:
    """Full pipeline: human → researcher → critic.

    Injects one message addressed to researcher. researcher processes it
    and forwards to critic. critic processes it and terminates (no
    next_agent). Asserts both agents produced non-empty string responses.

    This test makes two real LLM API calls.
    """
    researcher = LLMAgent("researcher", integration_settings)
    critic = LLMAgent("critic", integration_settings)

    researcher_runner = AgentRunner(
        researcher, shared_transport, integration_settings, next_agent="critic"
    )
    critic_runner = AgentRunner(
        critic, shared_transport, integration_settings, next_agent=None
    )

    # Inject the initial message
    seed = Message(from_agent="human", to_agent="researcher", body="What is quantum entanglement?")
    await shared_transport.send(seed)

    # Run both agents concurrently — researcher processes first, forwards to critic,
    # critic finds the forwarded message and processes it.
    await asyncio.gather(
        run_until_processed(researcher_runner, count=1),
        run_until_processed(critic_runner, count=1),
    )

    # Verify both messages were processed — check the messages table
    # Both researcher's response and critic's response must exist as processed messages.
    # Structural assertion only — never assert on LLM content.
    messages = await shared_transport.get_thread(seed.thread_id)
    assert len(messages) == 3  # seed + researcher response + critic response
    for msg in messages[1:]:   # skip the seed — check both LLM outputs
        assert isinstance(msg.body, str)
        assert len(msg.body) > 0
        assert msg.processed_at is not None


@pytest.mark.integration
async def test_pipeline_thread_continuity(
    integration_settings: Settings,
    shared_transport: SQLiteTransport,
) -> None:
    """All messages in the pipeline share the seed thread_id.

    Verifies that thread_id is preserved through the full researcher → critic
    chain — a structural correctness requirement, not an LLM content check.
    """
    researcher = LLMAgent("researcher", integration_settings)
    critic = LLMAgent("critic", integration_settings)

    researcher_runner = AgentRunner(
        researcher, shared_transport, integration_settings, next_agent="critic"
    )
    critic_runner = AgentRunner(
        critic, shared_transport, integration_settings, next_agent=None
    )

    seed = Message(from_agent="human", to_agent="researcher", body="Explain neural networks briefly.")
    await shared_transport.send(seed)

    await asyncio.gather(
        run_until_processed(researcher_runner, count=1),
        run_until_processed(critic_runner, count=1),
    )

    messages = await shared_transport.get_thread(seed.thread_id)
    assert all(msg.thread_id == seed.thread_id for msg in messages)
```

### Note on `get_thread()`

The integration tests call `transport.get_thread(thread_id)` to read the
message table after the pipeline runs. If this method does not exist on
`SQLiteTransport`, it must be added in this task. It is not part of the
`Transport` ABC — it is a SQLite-specific inspection method used only in tests.

```python
async def get_thread(self, thread_id: str) -> list[Message]:
    """Return all messages belonging to a thread, ordered by created_at.

    This method is for test inspection and debugging only. It is not part
    of the Transport ABC and must not be called from agent or runner code.

    Args:
        thread_id: The UUID identifying the conversation thread.

    Returns:
        List of Message objects in chronological order.
    """
```

---

## Unit Tests — `tests/unit/config/test_agents.py`

Transport is not involved. All tests use the fixture `agents.toml` in
`tests/fixtures/agents.toml`.

```
TestLoadAgentsConfig
    test_loads_researcher_and_critic
    test_researcher_next_agent_is_critic
    test_critic_next_agent_is_none
    test_raises_on_missing_file
    test_raises_on_invalid_toml
    test_raises_when_agents_table_absent
    test_returns_frozen_dataclasses
    test_agent_names_match_section_keys
```

---

## Implementation Order

Implement in this order. Run `just check` after each step.

1. Add `typer>=0.12` and `click>=8.1` to `pyproject.toml` → `uv sync`
2. Add `agents_config_path` to `Settings`, `.env.defaults`, `.env.test`
3. Create `tests/fixtures/agents.toml`
4. Create `agents.toml` (real, at repo root)
5. Run `just check && just test` — confirm no regressions
6. Create `src/multiagent/config/agents.py` — `AgentConfig` + `load_agents_config()`
7. **Write `tests/unit/config/test_agents.py`** — TDD red phase
8. Verify 8 tests fail appropriately
9. Implement `load_agents_config()` fully — TDD green phase
10. Run `just check && just test` — all 8 config tests pass
11. Add `create_transport()` factory to `src/multiagent/transport/__init__.py`
12. Rewrite `src/multiagent/cli/main.py` — typer app skeleton, no commands yet
13. Create `src/multiagent/cli/run.py` — `run_command()` implementation
14. Create `src/multiagent/cli/send.py` — `send_command()` implementation
15. Register commands in `main.py`
16. Verify `uv run multiagent --help` shows both commands
17. Update `src/multiagent/config/__init__.py` — add `AgentConfig`, `load_agents_config`
18. Run `just check && just test` — all unit tests pass
19. If `get_thread()` missing from `SQLiteTransport`, add it now
20. Create `tests/integration/conftest.py`
21. Create `tests/integration/test_pipeline.py`
22. Run `just test-integration` — both integration tests pass (real LLM calls)
23. Final: `just check && just test`
24. Manual smoke test — two terminals, send one message, observe the pipeline run end to end
25. `git tag v0.1.0-poc`

---

## Manual Smoke Test (Step 24)

After all tests pass, verify the system runs end-to-end in two real terminals:

```bash
# Terminal 1
just run critic

# Terminal 2
just run researcher

# Terminal 3 (then close after message is sent)
just send researcher "What is the significance of the Turing test?"
```

Observe:
- Terminal 2 (researcher): logs `message_received`, calls LLM, logs `message_forwarded`
- Terminal 1 (critic): logs `message_received`, calls LLM, logs no forwarding (terminal agent)
- Both terminals return to polling (inbox empty)

This is the acceptance gate for the human milestone — the first observable end-to-end run.

---

## Acceptance Criteria

```bash
just check          # zero ruff errors, zero pyright errors
just test           # all unit tests pass (previous total + 8 new config tests)
just test-integration   # both pipeline integration tests pass
```

Manual:
- `uv run multiagent --help` shows `run` and `send` subcommands with help text
- `uv run multiagent run --help` shows agent-name argument
- `uv run multiagent send --help` shows agent-name and body arguments
- Two-terminal smoke test completes without error

---

## What This Task Does NOT Include

- Routing module — `next_agent` is still a static value from `agents.toml`
- Supervisor — multi-agent orchestration in a single process
- Agent registry — dynamic agent discovery
- `TerminalTransport` CLI integration — transport backend remains SQLite for this task
- Conversation history — still stateless
- Additional agent types — researcher and critic only
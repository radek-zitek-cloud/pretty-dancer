# Multi-Agent System — Implementation Guide

**Version:** 2.0  
**Status:** Approved  
**Author:** Architecture (Claude.ai) + Radek Zítek  
**Audited by:** Tom (implementer agent)  
**Last Updated:** 2026-03-15

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [Repository Structure](#3-repository-structure)
4. [Architecture Principles](#4-architecture-principles)
5. [Module Dependency Rules](#5-module-dependency-rules)
6. [Configuration Contract](#6-configuration-contract)
7. [Observability Contract](#7-observability-contract)
8. [Transport Contract](#8-transport-contract)
9. [Agent Contract](#9-agent-contract)
10. [Routing Contract](#10-routing-contract)
11. [Exception Hierarchy](#11-exception-hierarchy)
12. [Python Standards](#12-python-standards)
13. [Testing Strategy](#13-testing-strategy)
14. [Scripts and Inspection Tools](#14-scripts-and-inspection-tools)
15. [Git Workflow](#15-git-workflow)
16. [Task Runner Reference](#16-task-runner-reference)
17. [Dependency Reference](#17-dependency-reference)

---

## 1. Project Overview

This system is a proof-of-concept for a multi-agent architecture where LLM-powered
agents communicate via a message-passing infrastructure. The design is intentionally
minimal and transport-agnostic: agents are pure input/output units; all I/O concerns
live in swappable adapters.

### Design Philosophy

- **Segregation of concerns is non-negotiable.** Every module has a single, clearly
  stated responsibility. The folder structure enforces this visually.
- **Designed for organic growth.** Adding a new agent, transport, or tool must never
  require modifying existing modules — only adding new ones.
- **Transport agnosticism.** An agent must be completely unaware of whether it is
  connected to a terminal, a SQLite database, a message broker, or a test harness.
- **PoC first, framework second.** LangGraph is the foundation but the PoC validates
  the architecture without unnecessary framework coupling.

### What This System Is Not

- Not production infrastructure. Reliability, multi-machine scaling, and HA are
  out of scope.
- Not a framework. Do not design for hypothetical future consumers.
- Not a chatbot. It is a message-passing pipeline where agents are processing nodes.

---

## 2. Technology Stack

| Concern | Choice | Rationale |
|---|---|---|
| Language | Python 3.12 (pinned) | `tomllib` stdlib, `asyncio.TaskGroup`, `except*` syntax |
| Package manager | `uv` | Fast, cross-platform, lockfile discipline |
| Linter + formatter | `ruff` | Single tool replacing flake8 + isort + black |
| Type checker | `pyright` strict | Best LangGraph/TypedDict support |
| LLM framework | LangGraph (per agent) | Async-native, typed state, checkpointing |
| LLM provider | OpenRouter | Via `langchain-openai` + `ChatOpenAI` |
| Structured logging | `structlog` | Context binding, dual console/JSON output |
| Configuration | `pydantic-settings` | Type-safe, validated, layered `.env` support |
| Message persistence | SQLite (WAL mode) | Serverless, zero infrastructure, inspectable |
| Checkpointing | `langgraph-checkpoint-sqlite` | Thread-aware LangGraph state persistence |
| Testing | `pytest` + `pytest-asyncio` | Async test support, marker-based tier separation |
| Task runner | `just` | Cross-platform, replaces make |
| CLI | `typer` + `rich` | Typed CLI with rich terminal output |

### Python Version Pinning

Python 3.12 is pinned in `.python-version` (read by `uv`), `pyproject.toml`
(`requires-python = ">=3.12"`), and `pyright` config (`pythonVersion = "3.12"`).
All three must agree.

---

## 3. Repository Structure

The folder structure is the architecture made visible.

```
multiagent/
│
├── .env.defaults              # committed — documents all config keys, safe defaults
├── .env                       # gitignored — local developer overrides (secrets here)
├── .env.test                  # committed — test environment overrides
├── .gitignore
├── .gitattributes             # enforces LF line endings
├── .pre-commit-config.yaml
├── .python-version            # pins Python 3.12 for uv
├── justfile                   # task runner definitions
├── pyproject.toml
├── uv.lock                    # committed lockfile
├── README.md
│
├── clusters/                  # cluster-specific configurations
│   ├── default/               # loaded when no --cluster flag is passed
│   │   ├── agents.toml        # agent wiring and router configuration
│   │   ├── agents.mcp.json    # MCP server definitions
│   │   ├── agents.mcp.secrets.json     # gitignored credentials
│   │   ├── agents.mcp.secrets.example.json
│   │   └── prompts/           # system prompt files, one per agent
│   │       ├── <agent_name>.md
│   │       └── routers/       # LLM classifier router prompts
│   ├── research-desk/         # named cluster example
│   │   ├── agents.toml
│   │   ├── agents.mcp.json
│   │   └── prompts/
│   └── platform-architect/
│       ├── agents.toml
│       ├── agents.mcp.json
│       └── prompts/
│
├── docs/
│   └── implementation-guide.md
│
├── scripts/                   # inspection and utility scripts (not CLI commands)
│   ├── browse_threads.py
│   ├── compare_runs.py
│   ├── ingest_docs.py         # index docs into ChromaDB for RAG
│   ├── show_costs.py
│   ├── show_run.py
│   └── show_thread.py
│
├── src/
│   └── multiagent/
│       ├── __init__.py        # package version only
│       ├── exceptions.py      # complete custom exception hierarchy
│       ├── models.py          # shared types: Message dataclass
│       ├── version.py         # SemVer utilities
│       │
│       ├── config/
│       │   ├── __init__.py    # exports: Settings, load_settings, AgentConfig,
│       │   │                  #          load_agents_config, path derivation functions
│       │   ├── settings.py    # Settings class + cluster path derivation functions
│       │   ├── agents.py      # AgentConfig, RouterConfig, AgentsConfig, loaders
│       │   └── mcp.py         # MCPServerConfig, MCPConfig, load_mcp_config
│       │
│       ├── core/              # agent logic — zero I/O knowledge
│       │   ├── __init__.py    # exports: LLMAgent, AgentRunner
│       │   ├── agent.py       # LLMAgent: system prompt + LangGraph graph
│       │   ├── costs.py       # CostLedger, CostEntry
│       │   ├── routing.py     # KeywordRouter, LLMRouter, build_router
│       │   ├── runner.py      # AgentRunner: connects agent to transport
│       │   └── shutdown.py    # ShutdownMonitor: stop-file and signal handling
│       │
│       ├── transport/         # I/O adapters — zero agent logic
│       │   ├── __init__.py    # exports: Transport, Message, create_transport
│       │   ├── base.py        # Transport ABC (re-exports Message from models)
│       │   ├── sqlite.py      # SQLiteTransport
│       │   └── terminal.py    # TerminalTransport
│       │
│       ├── logging/           # structured logging configuration
│       │   ├── __init__.py    # exports: configure_logging, get_logger
│       │   └── setup.py       # three-stream logging setup
│       │
│       └── cli/               # entry points only — wire core to transport
│           ├── __init__.py
│           ├── main.py        # CLI app, command registration, Windows event loop
│           ├── run.py         # `multiagent run` command
│           ├── send.py        # `multiagent send` command
│           ├── start.py       # `multiagent start` command
│           ├── stop.py        # `multiagent stop` command
│           ├── listen.py      # `multiagent listen` command
│           ├── chat.py        # `multiagent chat` command
│           ├── monitor.py     # `multiagent monitor` TUI command
│           └── version.py     # `multiagent version` command
│
├── tasks/                     # task briefs and change requests
│   ├── *.md
│   └── plans/                 # implementation plans produced by Tom
│       └── *-plan.md
│
├── tests/
│   ├── conftest.py            # shared fixtures
│   ├── fixtures/
│   │   ├── agents.toml        # test agent configuration
│   │   └── prompts/           # test prompt files
│   ├── unit/
│   │   ├── cli/
│   │   ├── config/
│   │   ├── core/
│   │   ├── scripts/
│   │   └── transport/
│   └── integration/
│       ├── conftest.py
│       └── test_pipeline.py
│
├── data/                      # gitignored runtime data
│   ├── agents.db              # SQLite transport database
│   ├── checkpoints.db         # LangGraph checkpoint database
│   ├── costs.db               # cost ledger database
│   ├── chroma/                # ChromaDB persistent data for RAG
│   └── .gitkeep
│
└── logs/                      # gitignored run log files
    └── .gitkeep
```

---

## 4. Architecture Principles

### 4.1 Ports and Adapters (Hexagonal Architecture)

The agent is the hexagon. Terminal and SQLite are adapters. `Transport` ABC is the
port. The agent is tested and runs identically regardless of which adapter is plugged
in.

An agent must never know where its input came from or where its output goes. It
receives a string and returns a string. Everything else is the transport's concern.

### 4.2 Open/Closed Principle

Open for extension, closed for modification:

- Adding a new transport: create `transport/zeromq.py` implementing `Transport` ABC.
  Touch nothing else.
- Adding a new agent: define name, system prompt, routing config. Touch nothing in
  core.
- Adding a new router type: add a new class in `core/routing.py` and a new case in
  `build_router()`. Touch nothing in agent or runner.

### 4.3 Async-First

The entire codebase is async. All methods that perform I/O — LLM calls, database
reads/writes, polling loops — are `async def`. Synchronous wrappers (`asyncio.run()`)
appear **only** at CLI entry points. This decision is irreversible cheaply — making
it from day one costs nothing.

### 4.4 Explicit Over Implicit

- No magic. No dynamic attribute setting. No monkey-patching.
- All configuration is validated at startup via pydantic-settings. The application
  fails fast with a clear error if configuration is invalid.
- All routing is declared in `agents.toml`. No routing logic is inferred from
  naming conventions or runtime inspection.
- Settings are passed via dependency injection. `load_settings()` is called once
  at the CLI entry point and injected everywhere else. Never call `load_settings()`
  inside library code.

### 4.5 Failure Is Loud

- Never swallow exceptions silently.
- If you catch and do not re-raise, you must log at WARNING or ERROR.
- The only exception: cost ledger write failures are caught and logged at WARNING
  only — cost tracking must never degrade the LLM pipeline.
- Shutdown is always clean. Ctrl-C exits with code 0 and a log event. Unhandled
  exceptions exit with code 1 and a log event.

---

## 5. Module Dependency Rules

These rules are absolute. They are enforced by code review and verified by grep
after every task.

```
models.py     → may import from: stdlib only             [NEVER config/, core/, transport/]
cli/          → may import from: core/, transport/, config/, models, exceptions
core/         → may import from: config/, models, exceptions  [NEVER transport/ or cli/]
transport/    → may import from: config/, models, exceptions  [NEVER core/ or cli/]
config/       → may import from: exceptions              [NEVER core/ or transport/]
scripts/      → may import from: config/, exceptions (via Settings only)
```

`Message` is defined in `models.py` and re-exported by `transport/base.py` for
backward compatibility. `core/` must import `Message` from `multiagent.models`,
never from `transport/`. The `Transport` ABC stays in `transport/base.py` — if
`core/` needs it for type annotations, use `TYPE_CHECKING`.

`rich` may be imported in `cli/` and `scripts/`. It must never be imported in
`core/` or `transport/`.

**Verification commands (must return empty after every task):**

```bash
grep -r "from multiagent.cli"       src/multiagent/core/
grep -r "from multiagent.cli"       src/multiagent/transport/
# core/ may only reference transport/ inside TYPE_CHECKING blocks:
grep -r "from multiagent.transport" src/multiagent/core/ | grep -v "TYPE_CHECKING" | grep -v "^.*:    "
grep -r "from multiagent.core"      src/multiagent/transport/
grep -r "import rich"               src/multiagent/core/
grep -r "import rich"               src/multiagent/transport/
```

Programmatic boundary tests in `tests/unit/test_module_boundaries.py` enforce
these rules automatically.

---

## 6. Configuration Contract

### 6.1 Layered Loading

```
.env.defaults  (committed — documents every key, safe defaults)
    ↓ override
.env           (gitignored — local developer values, secrets)
    ↓ override
OS environment variables  (CI, Docker, test runners)
```

For tests, `.env.test` is loaded by the `test_settings` fixture and overrides
all of the above.

### 6.2 Contract Rules

- Every settings field has a default in `.env.defaults`. Required fields (no
  default) are documented with a comment explaining where to set them.
- Secrets (`OPENROUTER_API_KEY`, `GREETING_SECRET`) have no default and must
  be set in `.env`. They must never appear in `.env.defaults` or committed files.
- `load_settings()` is the only way to construct `Settings`. It raises
  `InvalidConfigurationError` on validation failure. It is called once at the
  CLI entry point.
- Settings are immutable after construction for the lifetime of the process,
  with the exception of `cluster` which may be set by the CLI before agent
  construction.
- `extra="forbid"` is set on `Settings`. Unknown environment variable names
  that match the settings prefix cause startup failure — prevents silent typo
  misconfigurations.

### 6.3 Adding a New Setting

1. Add the field to `Settings` in `config/settings.py` with a type, default,
   and `description=`
2. Add the corresponding key to `.env.defaults` with a comment
3. Add `field_name=<test_value>` to the `test_settings` fixture in `conftest.py`

### 6.4 Settings Fields Reference

The canonical source of truth is `settings.py` and `.env.defaults`. This table
documents fields by group for orientation.

| Group | Fields |
|---|---|
| App | `app_name`, `app_env`, `greeting_message`, `greeting_secret` |
| LLM | `openrouter_api_key`, `openrouter_base_url`, `llm_model`, `llm_max_tokens`, `llm_timeout_seconds` |
| Transport | `transport_backend`, `sqlite_db_path`, `sqlite_poll_interval_seconds` |
| Checkpointer | `checkpointer_db_path` |
| Cost | `cost_db_path` |
| Observability | `log_console_enabled`, `log_console_level`, `log_human_file_enabled`, `log_human_file_level`, `log_json_file_enabled`, `log_json_file_level`, `log_dir`, `log_trace_llm` |
| Cluster | `cluster`, `clusters_dir` |
| Termination | `agent_loop_detection_threshold`, `agent_max_messages_per_thread` |
| CLI | `chat_reply_timeout_seconds` |

### 6.5 Cluster Path Derivation

The following module-level functions in `config/settings.py` derive paths
from `cluster` and `clusters_dir`. They are not fields on `Settings`.

| Function | Returns |
|---|---|
| `cluster_dir(settings)` | `clusters_dir / {cluster or "default"}` |
| `agents_config_path(settings)` | `cluster_dir / "agents.toml"` (raises if missing) |
| `mcp_config_path(settings)` | `cluster_dir / "agents.mcp.json"` |
| `mcp_secrets_path(settings)` | Secrets path with fallback to default cluster, or `None` |
| `prompts_dir(settings)` | `cluster_dir / "prompts"` |

---

## 7. Observability Contract

### 7.1 Three Independent Streams

Every run produces up to three independent output streams:

| Stream | File | Renderer | LLM trace |
|---|---|---|---|
| Console | stdout | ConsoleRenderer (colors) | suppressed |
| Human file | `logs/{timestamp}_{agent}[_{cluster}].log` | ConsoleRenderer (no colors) | suppressed |
| JSON file | `logs/{timestamp}_{agent}[_{cluster}].jsonl` | JSONRenderer | included |

Each stream is independently enabled/disabled and has its own log level.

### 7.2 `configure_logging()` Contract

Signature: `configure_logging(settings, agent_name, cluster) -> tuple[Path | None, Path | None]`

Returns paths to the human log file and JSON log file (or `None` if disabled).
Called once at CLI startup before any log calls.

### 7.3 Log Event Naming Convention

Events are `snake_case` strings describing what happened. Prefer past tense:
`message_received`, `agent_started`, `cluster_stopped`. Bind permanent context
at class init (agent name, transport type). Bind ephemeral context per operation
(thread_id, message_id).

### 7.4 Log Level Discipline

| Level | When |
|---|---|
| DEBUG | Internal state, poll ticks, prompt/response content, token counts |
| INFO | Normal operational events — message received, sent, agent start/stop |
| WARNING | Unexpected but recoverable — retry, slow response, cost write failure |
| ERROR | Failure that was caught and handled — transport error, LLM API error |
| CRITICAL | Unrecoverable — process about to exit |

Never log at ERROR and then silently continue. Never log LLM prompt/response
content at INFO — always DEBUG.

### 7.5 `LOG_TRACE_LLM` Gate

`llm_trace` events (full prompt and response content) are gated by
`settings.log_trace_llm`. When false, these events are not emitted. They are
suppressed at the console and human file streams regardless.

---

## 8. Transport Contract

### 8.1 What Transport Owns

The transport is responsible for message persistence, retrieval, and at-least-once
delivery semantics. Unacknowledged messages are re-delivered.

The transport is not responsible for knowing what agents exist, what messages mean,
or making routing decisions.

### 8.2 `Message` Fields Contract

| Field | Type | Who sets it |
|---|---|---|
| `from_agent` | `str` | CLI send sets `"human"`. AgentRunner sets agent name. |
| `to_agent` | `str` | AgentRunner resolves from routing. `"human"` is valid. |
| `body` | `str` | Message content. |
| `thread_id` | `str` | UUID. CLI generates or accepts `--thread-id`. Propagated unchanged. |
| `id` | `int \| None` | Set by transport on persistence. |
| `created_at` | `datetime \| None` | Set by transport on persistence. |
| `processed_at` | `datetime \| None` | Set by transport on `ack()`. |

### 8.3 `Transport` ABC Contract

Three methods, all async, all must be safe for concurrent agent coroutines:

- `receive(agent_name)` — fetch oldest unprocessed message. Does not mark as
  processed. Returns `None` if inbox is empty.
- `send(message)` — persist message. `thread_id` must be populated.
- `ack(message_id)` — mark message as processed.

### 8.4 `human` as a Recipient

`"human"` is a valid `to_agent` value. The transport treats it identically to any
other agent name. The `listen` and `chat` CLI commands consume these messages.

### 8.5 WAL Mode

`SQLiteTransport` enables WAL journal mode. Required for the cluster pattern where
multiple `AgentRunner` coroutines share one transport instance.

---

## 9. Agent Contract

### 9.1 What an Agent Is

An `LLMAgent` is a LangGraph graph with a fixed system prompt. It accepts a string
input and a `thread_id`, calls the LLM via OpenRouter, records cost, and returns
the LLM's response. It has no knowledge of transport, routing, or I/O.

### 9.2 `LLMAgent` Construction Contract

Required parameters: `name`, `settings`, `checkpointer`, `cost_ledger`.
Optional: `router` (defaults to `None` for static routing),
`tool_configs` (MCP server configs for tool access),
`prompt_name` (explicit prompt path override from agents.toml).

The system prompt is loaded from `prompts_dir(settings) / "{name}.md"` at
construction. When `prompt_name` is set (from the `prompt` field in agents.toml),
it overrides the convention-based path.

### 9.3 LangGraph State Contract

Agents use `MessagesState` from LangGraph. The graph accumulates the full message
history, giving agents conversation memory within a thread via the checkpointer.
Custom `TypedDict` state is not used.

### 9.4 Checkpointer Lifecycle Contract

The CLI owns the checkpointer lifecycle via `async with AsyncSqliteSaver.from_conn_string(...)`.
Unit tests use `MemorySaver()`. The checkpointer database parent directory is
created by the CLI before opening.

### 9.5 Cost Ledger Lifecycle Contract

The CLI owns the cost ledger lifecycle via `async with CostLedger(settings.cost_db_path)`,
nested inside the checkpointer block. Unit tests use the `mock_cost_ledger` fixture.

Cost write failures are caught inside `CostLedger.record()` and logged at WARNING.
They never propagate to the agent or pipeline.

`CostLedger` receives `db_path: Path` directly — it does not import from `config/`.

### 9.6 `AgentRunner` Contract

`AgentRunner` is the only component holding both an agent and a transport reference.
It polls the transport, invokes the agent, resolves the next destination, and sends
the response. It respects `ShutdownMonitor` between iterations.

### 9.7 Shutdown Contract

`ShutdownMonitor` watches for a stop file and OS signals. When triggered, the current
message completes before the runner exits. Shutdown is always clean.

---

## 10. Routing Contract

### 10.1 Static Routing (default)

`next_agent = "name"` in `agents.toml` routes every message to that destination.
No `next_agent` means terminal agent — processes the message, sends no reply.

### 10.2 Dynamic Routing

`router = "name"` in `agents.toml` routes based on the LLM's output at runtime.
An agent may have `next_agent` OR `router`, never both — `ConfigurationError` if
both are present.

### 10.3 Router Types

**Keyword router** — scans agent output for trigger strings, no additional LLM
call. Use when output format is deterministic.

**LLM classifier router** — second lightweight LLM call returning exactly one route
key. Use when routing requires semantic understanding. Use a cheap, fast model.

### 10.4 `agents.toml` Schema

```toml
[agents.editor]
router = "editorial_gate"          # dynamic routing

[agents.writer]
next_agent = "linguist"            # static routing — unchanged, backward compatible

[routers.editorial_gate]
type = "keyword"                   # or "llm"
routes.writer = ["WRITER BRIEF"]   # trigger strings → destination
default = "human"                  # fallback

# For llm type:
# prompt = "prompts/routers/gate.md"
# model = ""                       # empty = use settings.llm_model
```

### 10.5 Backward Compatibility Rule

All existing `next_agent` entries continue to work unchanged. No migration required.

### 10.6 `human` as a Routing Destination

Any router may route to `"human"`. The `listen` or `chat` command picks up the
message.

---

## 11. Exception Hierarchy

All custom exceptions live exclusively in `src/multiagent/exceptions.py`.

```
MultiAgentError
├── ConfigurationError
│   ├── MissingConfigurationError
│   └── InvalidConfigurationError
├── TransportError
│   ├── MessageDeliveryError
│   ├── MessageReceiveError
│   ├── TransportConnectionError
│   └── MessageAcknowledgementError
├── AgentError
│   ├── AgentTimeoutError
│   ├── AgentLLMError
│   └── AgentConfigurationError
└── RoutingError
    └── UnknownAgentError
```

### Handling Rules

- Catch at the most specific level where recovery is possible.
- Catch `MultiAgentError` only at the process boundary for final logging.
- Never catch bare `Exception` except at the top of `cli/main.py`.
- Always chain: `raise AgentLLMError("...") from original_exc`.
- Never swallow silently — always log at WARNING or ERROR before suppressing.

---

## 12. Python Standards

### 12.1 Type Annotations

Mandatory on every function, method, and class attribute. `pyright` strict mode
enforces this. No `Any` without a justifying comment.

### 12.2 Docstrings

Google style. Every public module, class, and method. Private methods where logic
is non-obvious. `ruff` does not enforce docstrings — followed by convention only.

### 12.3 Comments

Explain **why**, not **what**. If a comment describes what the next line does,
rewrite the line to be self-documenting.

### 12.4 Naming

| Element | Convention |
|---|---|
| Module | `snake_case` |
| Class | `PascalCase` |
| Function/method | `snake_case` |
| Constant | `UPPER_SNAKE_CASE` |
| Private | `_single_prefix` |
| Type alias | `PascalCase` |

### 12.5 Import Rules

Absolute imports only — no relative imports. `ruff` enforces order:
stdlib → third-party → local. No star imports.

### 12.6 `print()` Usage

`print()` and `typer.echo()` are acceptable in `cli/` and `scripts/`. They must
never appear in `core/` or `transport/`. All diagnostic output in library code
goes through `structlog`.

### 12.7 Path Handling

`pathlib.Path` everywhere. No string path concatenation. `Path.mkdir(parents=True,
exist_ok=True)` before any file creation. Required for Windows compatibility.

### 12.8 Datetime

Use `datetime.now(UTC)` (Python 3.12+). Never `datetime.utcnow()` (deprecated).

---

## 13. Testing Strategy

### 13.1 Two Tiers

**Unit tests** (`tests/unit/`) — fast, mocked, no LLM calls, no file I/O except
`tmp_path` SQLite databases. All new behaviour must have unit test coverage.

**Integration tests** (`tests/integration/`) — real LLM calls, real databases.
Gated by `@pytest.mark.integration`. Require `OPENROUTER_API_KEY`.

### 13.2 Mock Boundaries

| Component | Unit test approach |
|---|---|
| LLM | Mock `ChatOpenAI.ainvoke` to return `AIMessage` with `usage_metadata` and `response_metadata` |
| Transport | Real `SQLiteTransport` with `tmp_path` database |
| Checkpointer | `MemorySaver()` — never `AsyncSqliteSaver` in unit tests |
| Cost ledger | `mock_cost_ledger` fixture (`AsyncMock(spec=CostLedger)`) |

### 13.3 Shared Fixtures (`conftest.py`)

| Fixture | Purpose |
|---|---|
| `test_settings` | `Settings` with test overrides, in-memory DBs |
| `mock_llm` | Patches `ChatOpenAI.ainvoke`, returns `AIMessage` with metadata |
| `mock_llm_response` | Plain string: the mock LLM response body |
| `sample_message` | A `Message` instance for transport tests |
| `sqlite_transport` | Real `SQLiteTransport` against `tmp_path` database |
| `mock_cost_ledger` | `AsyncMock(spec=CostLedger)` |

### 13.4 Script Tests

Scripts are tested via `subprocess.run`. Override database paths via environment
variables (`SQLITE_DB_PATH`, `COST_DB_PATH`) in the subprocess env — never via
`--db` flags. Use `tmp_path` databases with known content.

### 13.5 Test the Failure Path

Every component with a graceful failure mode must have a test asserting that
failure does not propagate — cost ledger, shutdown monitor, routing fallback.

---

## 14. Scripts and Inspection Tools

### 14.1 What Scripts Are

Scripts in `scripts/` are developer inspection tools, not CLI commands. Run
directly: `uv run python scripts/show_thread.py`. All have `just` targets.

### 14.2 Database Path Contract

Scripts read database paths from `Settings()` only. No `--db` flag, no hardcoded
paths. This is non-negotiable.

### 14.3 Graceful Degradation

Scripts must never crash when a database does not exist or is empty. Missing
`costs.db` means cost tracking has not run — show `—` in cost columns.

### 14.4 Current Scripts

| Script | Purpose | `just` target |
|---|---|---|
| `browse_threads.py` | Interactive thread browser with cost column | `just threads` |
| `show_thread.py` | Full message chain with cost footer | `just thread <id>` |
| `show_run.py` | Log events for one run with token/cost columns | `just run-summary <file>` |
| `compare_runs.py` | Side-by-side run comparison | `just compare <files>` |
| `show_costs.py` | Cost views by cluster/agent/model | `just costs` |
| `ingest_docs.py` | Index markdown files into ChromaDB for RAG | `just ingest` |

---

## 15. Git Workflow

### 15.1 Branching Strategy

```
master          # always clean, Radek merges here
feature/<slug>  # new capability
fix/<slug>      # bug fix
chore/<slug>    # tooling, config, non-functional
docs/<slug>     # documentation only
```

Work is always on a feature branch. `master` is never worked on directly.

### 15.2 Branch Lifecycle

```bash
# Start
git checkout master && git pull origin master
git checkout -b feature/<slug>

# During — commit often with Conventional Commits
# stage intentionally — never git add -A blindly

# Finish — Tom reports, Radek merges
git checkout master
git merge feature/<slug>
git push origin master
git branch -d feature/<slug>
```

**Radek is the only person who merges to master. Tom pushes his branch
and reports completion.**

### 15.3 Commit Convention

```
<type>(<scope>): <short summary>

Types: feat, fix, docs, chore, refactor, test, ci
Scope: core, transport, config, logging, cli, tests (optional)

Examples:
feat(transport): implement SQLiteTransport with WAL mode
fix(core): handle empty LLM response in AgentRunner
test(core): add unit tests for LLMAgent cost recording
```

### 15.4 Pre-Branch Hygiene

Before starting any task: `git status` — master must be clean. If uncommitted
changes exist, stage intentionally and commit before branching. Never start a
feature branch from a dirty master.

### 15.5 Plan Files

Implementation plans live in `tasks/plans/<task-id>-plan.md`. Committed to the
feature branch. Updated to reflect architect feedback before implementation begins.
The plan should represent what was actually built, not the original draft.

---

## 16. Task Runner Reference

All development tasks run via `just`. Run `just` with no arguments to list targets.

### Application

| Target | Purpose |
|---|---|
| `just run <agent> [cluster]` | Run a single agent |
| `just send <agent> "<message>" [cluster]` | Send a message to an agent |
| `just start [cluster]` | Start all agents from cluster config |
| `just stop` | Write stop file to halt the cluster |
| `just listen [thread_id]` | Poll for messages addressed to human |
| `just chat <agent> [thread_id] [cluster]` | Interactive REPL with an agent |
| `just monitor [cluster] [thread_id]` | Launch the platform monitor TUI |

### Inspection

| Target | Purpose |
|---|---|
| `just threads` | Browse all threads interactively |
| `just thread <id>` | Show full message chain for a thread |
| `just runs` | List recent run log files |
| `just costs` | Cost summary by cluster |
| `just costs-by-agent` | Cost breakdown by agent |
| `just costs-by-model` | Cost breakdown by model |
| `just ingest` | Index docs and cluster prompts into ChromaDB |

### Development

| Target | Purpose |
|---|---|
| `just check` | ruff lint + pyright — both must pass |
| `just test` | Run unit tests |
| `just test-integration` | Run integration tests |
| `just format` | Auto-format with ruff |
| `just clean` | Remove build artefacts and caches |

### The Gate

```bash
just check && just test
```

Both must pass with zero errors before any task is considered done.

---

## 17. Dependency Reference

| Package | Runtime/Dev | Purpose |
|---|---|---|
| `langgraph` | Runtime | Agent graph, typed state, async-native |
| `langgraph-checkpoint-sqlite` | Runtime | SQLite LangGraph checkpointer |
| `langchain-openai` | Runtime | `ChatOpenAI` for OpenRouter integration |
| `langchain-core` | Runtime | `BaseMessage`, `SystemMessage`, `HumanMessage` |
| `pydantic` | Runtime | Data validation |
| `pydantic-settings` | Runtime | Layered configuration, env file support |
| `structlog` | Runtime | Structured logging, context binding |
| `aiosqlite` | Runtime | Async SQLite for cost ledger |
| `typer` | Runtime | CLI framework |
| `rich` | Runtime | Terminal formatting for CLI and scripts |
| `tomllib` | Runtime | `agents.toml` parsing (stdlib in 3.12) |
| `pytest` | Dev | Test framework |
| `pytest-asyncio` | Dev | Async test support |
| `pytest-mock` | Dev | `mocker` fixture |
| `pytest-cov` | Dev | Coverage reporting |
| `ruff` | Dev | Linter and formatter |
| `pyright` | Dev | Type checker, strict mode |
| `pre-commit` | Dev | Git hook management |

### Key Conventions

- `langchain-openai` is used, not `langchain-anthropic`. The provider is OpenRouter.
  The model string is passed as a parameter to `ChatOpenAI`.
- `aiosqlite` is used directly by `CostLedger` only. All other SQLite access
  goes through their respective libraries (`langgraph-checkpoint-sqlite`, the
  transport's own connection management).
- `rich` is a runtime dependency. It is used in `cli/` and `scripts/`. It must
  never be imported in `core/` or `transport/`.
- `tomllib` is stdlib in Python 3.12. No third-party TOML library is needed.

---

*This document is the canonical implementation reference. Tom reads it before every
task. Deviations from these principles require explicit architectural approval and
a note in the task plan. When in doubt, consult the architect.*
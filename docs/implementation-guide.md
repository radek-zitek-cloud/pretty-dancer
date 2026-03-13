# Multi-Agent System — Implementation Guide

**Version:** 1.0.0  
**Status:** Authoritative — Claude Code must treat this document as the canonical reference  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Last Updated:** 2026-03-13

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [Repository Structure](#3-repository-structure)
4. [Environment and Tooling Setup](#4-environment-and-tooling-setup)
5. [Configuration System](#5-configuration-system)
6. [Logging Standards](#6-logging-standards)
7. [Exception Hierarchy](#7-exception-hierarchy)
8. [Architecture and Module Boundaries](#8-architecture-and-module-boundaries)
9. [Coding Standards](#9-coding-standards)
10. [Docstring Standard](#10-docstring-standard)
11. [Testing Strategy](#11-testing-strategy)
12. [Git Workflow](#12-git-workflow)
13. [Task Runner](#13-task-runner)
14. [Documentation Standards](#14-documentation-standards)
15. [Cross-Platform Rules](#15-cross-platform-rules)
16. [Dependency Reference](#16-dependency-reference)

---

## 1. Project Overview

### Purpose

A proof-of-concept multi-agent system where LLM-powered agents communicate through a
transport-agnostic messaging layer. The system demonstrates that agent logic is entirely
independent of the communication medium — agents are interchangeable between terminal
interaction and a persistent SQLite message bus without any modification to agent code.

### Core Architectural Principles

**Separation of Concerns** is the supreme constraint. Every module has exactly one
responsibility. If a module's purpose cannot be stated in one sentence, it must be split.

**Ports and Adapters (Hexagonal Architecture)** governs the relationship between agent
logic and I/O. Agent cores are pure logic units. All I/O — transport, terminal, logging
sinks, configuration sources — are adapters that plug into defined ports (abstract
interfaces). The agent core never imports from adapter modules.

**Open/Closed** — the system is open for extension, closed for modification. Adding a
new agent, a new transport backend, or a new tool must require only adding new files,
never modifying existing ones.

**Async-First** — the entire codebase uses `async/await` natively. Synchronous wrappers
are provided only at CLI entry points. This is a one-time architectural decision that
is prohibitively expensive to reverse later.

**Configuration over Code** — every value that could vary between environments lives in
configuration. No magic strings or numbers in source code.

---

## 2. Technology Stack

All technology choices are fixed for this project. Deviations require an Architecture
Decision Record and explicit approval.

| Concern | Choice | Rationale |
|---|---|---|
| Language | Python 3.12 (pinned) | `TypedDict` improvements, `tomllib` stdlib, best asyncio |
| Package manager | `uv` | Fastest resolver, native venv, lockfile, cross-platform |
| Agent framework | LangGraph | Native async, typed state, composable graphs |
| LLM provider | OpenRouter.ai via `langchain-openai` | Unified gateway to all major models; OpenAI-compatible API |
| Transport (PoC) | SQLite via stdlib `aiosqlite` | Serverless, persistent, inspectable, zero infra |
| Transport (dev) | Terminal adapter | Interactive testing without infrastructure |
| Configuration | `pydantic-settings` | Type-safe, validated, documented, layered env |
| Logging | `structlog` | Structured output, context binding, dev/prod renderers |
| Linter/Formatter | `ruff` | Replaces black + flake8 + isort, fastest, unified config |
| Type checker | `pyright` | Strict mode, best LangGraph / Pydantic v2 support |
| Test framework | `pytest` + `pytest-asyncio` | Async test support, fixtures, markers |
| Test mocking | `pytest-mock` | LLM call interception in unit tests |
| HTTP mocking | `respx` | Mock httpx-based OpenAI SDK calls |
| CLI framework | `typer` + `click` | Type-annotated commands, automatic help, shell completion |
| Task runner | `just` | Cross-platform, simple syntax, no shell dependency |
| Pre-commit | `pre-commit` | Enforce ruff and pyright before every commit |

### Pinned Versions

Exact versions are recorded in `uv.lock` (auto-generated). The following are minimum
acceptable versions at project inception:

```toml
# pyproject.toml [project.dependencies]
python = ">=3.12,<3.13"
langgraph = ">=0.2"
langchain-openai = ">=0.1"
openai = ">=1.0"
pydantic-settings = ">=2.0"
structlog = ">=24.0"
aiosqlite = ">=0.20"
typer = ">=0.12"
click = ">=8.1"
```

---

## 3. Repository Structure

The folder structure enforces the architecture. A developer reading only the path of any
file must be able to determine its responsibility without opening it.

```
multiagent/                          # repository root
│
├── .env.defaults                    # committed — documents all config keys, safe defaults
├── .env                             # gitignored — local developer overrides
├── .env.test                        # committed — test environment overrides
├── .gitignore
├── .pre-commit-config.yaml
├── agents.toml                      # agent wiring configuration — names, next_agent routing
├── justfile                         # all runnable tasks
├── pyproject.toml                   # package metadata, ruff, pyright, pytest config
├── uv.lock                          # committed — reproducible dependency resolution
├── README.md                        # project entry point
│
├── docs/                            # all project documentation
│   ├── adr/                         # Architecture Decision Records
│   │   ├── 0001-python-312.md
│   │   ├── 0002-uv-package-manager.md
│   │   ├── 0003-async-first.md
│   │   ├── 0004-sqlite-transport-poc.md
│   │   └── 0005-langgraph-agent-internals.md
│   ├── architecture.md              # system architecture narrative
│   ├── getting-started.md           # developer onboarding
│   └── transport-guide.md           # how to implement a new transport adapter
│
├── src/                             # all application source code
│   └── multiagent/                  # the package
│       │
│       ├── __init__.py              # package version only — no imports
│       ├── exceptions.py            # complete exception hierarchy
│       ├── constants.py             # true constants only (no config values)
│       │
│       ├── config/                  # configuration system
│       │   ├── __init__.py          # exports Settings, get_settings, AgentConfig, load_agents_config
│       │   ├── settings.py          # pydantic-settings Settings class
│       │   └── agents.py            # AgentConfig dataclass + load_agents_config()
│       │
│       ├── core/                    # agent logic — NO transport, NO I/O imports
│       │   ├── __init__.py
│       │   ├── agent.py             # LLMAgent class
│       │   ├── runner.py            # AgentRunner class
│       │   └── state.py             # LangGraph state TypedDict definitions
│       │
│       ├── transport/               # transport layer — abstract port + adapters
│       │   ├── __init__.py          # exports Transport, Message
│       │   ├── base.py              # Transport ABC and Message dataclass
│       │   ├── sqlite.py            # SQLiteTransport adapter
│       │   └── terminal.py          # TerminalTransport adapter
│       │
│       ├── routing/                 # message routing logic
│       │   ├── __init__.py
│       │   └── router.py            # routing strategies (pipeline, supervisor, etc.)
│       │
│       ├── logging/                 # logging configuration and setup
│       │   ├── __init__.py          # exports configure_logging, get_logger
│       │   └── setup.py             # structlog processor chain configuration
│       │
│       └── cli/                     # entry points only — thin wrappers
│           ├── __init__.py
│           ├── main.py              # typer app definition — `run` and `send` commands
│           ├── run.py               # implementation of `multiagent run`
│           └── send.py              # implementation of `multiagent send`
│
├── tests/                           # mirrors src/multiagent/ structure
│   ├── conftest.py                  # shared fixtures, mock LLM factory
│   ├── unit/
│   │   ├── core/
│   │   │   ├── test_agent.py
│   │   │   └── test_runner.py
│   │   ├── transport/
│   │   │   ├── test_sqlite.py
│   │   │   └── test_terminal.py
│   │   ├── config/
│   │   │   ├── test_settings.py
│   │   │   └── test_agents.py       # AgentConfig loading and validation
│   │   └── routing/
│   │       └── test_router.py
│   └── integration/                 # requires real LLM — gated by marker
│       ├── conftest.py              # integration-specific fixtures (shared transport, agents)
│       └── test_pipeline.py         # full researcher → critic pipeline
│
├── data/                            # runtime data — gitignored except .gitkeep
│   └── .gitkeep                     # SQLite databases, queue files
│
├── logs/                            # runtime log files — gitignored except .gitkeep
│   └── .gitkeep                     # structlog file sink output (when configured)
│
├── prompts/                         # agent system prompt files — committed to git
│   ├── researcher.md                # system prompt for the researcher agent
│   └── critic.md                    # system prompt for the critic agent
│
├── scripts/                         # developer inspection and experiment tools
│   ├── show_thread.py               # rich-formatted conversation thread from SQLite
│   ├── show_run.py                  # rich-formatted summary of a single JSONL run file
│   └── compare_runs.py              # side-by-side rich comparison of two run files
│
└── tasks/                           # Claude Code implementation briefs — permanent record
    ├── README.md                    # task lifecycle and conventions
    ├── 001-skeleton.md              # first task: project skeleton
    ├── 002-transport.md             # second task: transport layer
    ├── 003-agent-core.md            # third task: agent core
    ├── 004-cli-wiring.md            # fourth task: CLI wiring and integration tests
    └── 005-observability.md         # fifth task: dual logging, JSONL runs, inspection scripts
```

### `.gitignore` — Required Entries

```gitignore
# Local configuration — never commit secrets
.env

# Runtime data — all contents ignored, folder tracked via .gitkeep
data/*
!data/.gitkeep

# Log files — all contents ignored, folder tracked via .gitkeep
logs/*
!logs/.gitkeep

# Python
__pycache__/
*.py[cod]
*.pyo
.ruff_cache/
.mypy_cache/
.pyright/

# uv / packaging
.venv/
*.egg-info/
dist/

# Testing
.coverage
htmlcov/
.pytest_cache/
```

### Module Dependency Rules — Enforced

The following import directions are **forbidden**. `pyright` and code review enforce this:

```
core/      MUST NOT import from  transport/
core/      MUST NOT import from  cli/
core/      MUST NOT import from  routing/
transport/ MUST NOT import from  core/
transport/ MUST NOT import from  cli/
cli/       MAY import from       core/, transport/, routing/, config/, logging/
routing/   MAY import from       transport/ (Message type only)
```

All modules MAY import from: `config/`, `logging/`, `exceptions.py`, `constants.py`

---

## 4. Environment and Tooling Setup

### Python Version

Python **3.12** is pinned. Enforce with `.python-version` file in repository root:

```
3.12
```

`uv` reads this file automatically and provisions the correct interpreter.

### uv Setup

```bash
# Install uv (cross-platform)
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS / Linux
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# Initialize project (run once)
uv init --python 3.12 multiagent
cd multiagent

# Add dependencies
uv add langgraph langchain-anthropic pydantic-settings structlog aiosqlite

# Add development dependencies
uv add --dev ruff pyright pytest pytest-asyncio pytest-mock respx pre-commit

# Run anything in the venv
uv run python -m multiagent
uv run pytest
uv run pyright
```

### pyproject.toml — Complete Configuration

```toml
[project]
name = "multiagent"
version = "0.1.0"
description = "Multi-agent LLM system proof of concept"
requires-python = ">=3.12,<3.13"
dependencies = [
    "langgraph>=0.2",
    "langchain-anthropic>=0.2",
    "pydantic-settings>=2.0",
    "structlog>=24.0",
    "aiosqlite>=0.20",
]

[project.optional-dependencies]
dev = [
    "ruff",
    "pyright",
    "pytest",
    "pytest-asyncio",
    "pytest-mock",
    "respx",
    "pre-commit",
]

[project.scripts]
multiagent = "multiagent.cli.run:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/multiagent"]

# --- ruff ---
[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "B",    # flake8-bugbear
    "C4",   # flake8-comprehensions
    "UP",   # pyupgrade
    "ANN",  # flake8-annotations (enforce type hints)
    "D",    # pydocstyle (enforce docstrings)
    "ASYNC",# flake8-async
    "RUF",  # ruff-specific rules
]
ignore = [
    "D100", # missing docstring in public module (handled by __init__.py convention)
    "D104", # missing docstring in public package
    "ANN101", # missing type annotation for self
    "ANN102", # missing type annotation for cls
]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["ANN", "D"]   # relax annotations and docstrings in tests

# --- pyright ---
[tool.pyright]
include = ["src", "tests"]
pythonVersion = "3.12"
typeCheckingMode = "strict"
reportMissingImports = true
reportMissingTypeStubs = false
venvPath = "."
venv = ".venv"

# --- pytest ---
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "integration: marks tests as integration tests requiring real LLM (deselect with -m 'not integration')",
    "slow: marks tests as slow",
]
addopts = "-v --tb=short -m 'not integration'"

# --- coverage ---
[tool.coverage.run]
source = ["src/multiagent"]
omit = ["src/multiagent/cli/*"]   # CLI entry points excluded from coverage target

[tool.coverage.report]
fail_under = 80
show_missing = true
```

### Pre-commit Configuration

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/RobertCraigie/pyright-python
    rev: v1.1.350
    hooks:
      - id: pyright
```

Install hooks after cloning:

```bash
uv run pre-commit install
```

---

## 5. Configuration System

### Layered Loading

Configuration is loaded in the following order. Later sources override earlier ones.
This order is fixed and must not be changed.

```
Priority 1 (lowest):  .env.defaults    — committed, documents every key, safe defaults
Priority 2:           .env             — gitignored, local developer overrides
Priority 3:           .env.test        — committed, used when pytest runs
Priority 4 (highest): Process env vars — injected in production / CI
```

### Settings Class

Location: `src/multiagent/config/settings.py`

```python
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration loaded from environment and .env files.

    All settings have type validation and documented defaults. Unknown environment
    variables cause a startup failure (extra='forbid') to catch typos early.

    The double-underscore delimiter allows nested configuration via env vars:
    AGENT__DEFAULT_TIMEOUT_SECONDS=90 maps to settings.agent.default_timeout_seconds
    """

    model_config = SettingsConfigDict(
        env_file=(".env.defaults", ".env"),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="forbid",
    )

    # LLM
    openrouter_api_key: str = Field(..., description="OpenRouter API key. Required.")
    openrouter_base_url: str = Field(
        "https://openrouter.ai/api/v1",
        description="OpenRouter API base URL. Override only in tests or when self-hosting.",
    )
    llm_model: str = Field(
        "anthropic/claude-sonnet-4-5",
        description="OpenRouter model routing string. Format: provider/model-name.",
    )
    llm_max_tokens: int = Field(1024, ge=1, le=8192, description="Maximum response tokens.")
    llm_timeout_seconds: float = Field(30.0, gt=0, description="LLM call timeout in seconds.")

    # Transport
    transport_backend: str = Field(
        "sqlite", pattern="^(sqlite|terminal)$", description="Active transport backend."
    )
    sqlite_db_path: Path = Field(Path("data/agents.db"), description="SQLite database file path.")
    sqlite_poll_interval_seconds: float = Field(1.0, gt=0, description="Mailbox poll interval.")
    sqlite_wal_mode: bool = Field(True, description="Enable WAL journal mode for concurrency.")

    # Logging
    log_level: str = Field(
        "INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Minimum log level.",
    )
    log_format: str = Field(
        "console",
        pattern="^(console|json)$",
        description="Log renderer: console for dev, json for production.",
    )

    # Agent defaults
    agent_default_timeout_seconds: float = Field(60.0, gt=0)
    agent_max_retries: int = Field(3, ge=0)
    agent_retry_backoff_seconds: float = Field(2.0, gt=0)

    # Prompts
    prompts_dir: Path = Field(
        Path("prompts"),
        description="Directory containing agent system prompt .md files. "
                    "Each agent loads {prompts_dir}/{agent_name}.md at construction.",
    )

    # Agent wiring
    agents_config_path: Path = Field(
        Path("agents.toml"),
        description="Path to the agents configuration file. "
                    "Declares all agents and their next_agent routing.",
    )

    # Observability — console stream
    log_console_enabled: bool = Field(
        True,
        description="Emit log events to stdout. Disable to suppress all console output.",
    )
    log_console_level: str = Field(
        "INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Minimum log level for console output.",
    )

    # Observability — human-readable log file stream (.log)
    log_human_file_enabled: bool = Field(
        False,
        description="Write a per-run human-readable log file alongside console output.",
    )
    log_human_file_level: str = Field(
        "INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Minimum log level for the human-readable log file.",
    )

    # Observability — JSON Lines log file stream (.jsonl)
    log_json_file_enabled: bool = Field(
        False,
        description="Write a per-run JSONL log file. Intended for agent-based analysis.",
    )
    log_json_file_level: str = Field(
        "DEBUG",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Minimum log level for the JSONL log file. Defaults to DEBUG to "
                    "capture maximum detail for experiment analysis.",
    )

    # Observability — shared
    log_dir: Path = Field(
        Path("logs"),
        description="Directory for per-run log files. Both .log and .jsonl land here.",
    )
    log_trace_llm: bool = Field(
        False,
        description="Include full LLM prompt and response content in the JSONL log file. "
                    "Never emitted to console or human-readable file. "
                    "Only effective when log_json_file_enabled=True.",
    )
    experiment: str = Field(
        "",
        description="Optional experiment label included in log filenames. "
                    "Override per-run with the --experiment CLI flag.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance.

    Cached after first call. In tests, call get_settings.cache_clear() between
    test cases that modify environment variables.

    Returns:
        The validated Settings instance.

    Raises:
        ValidationError: If required settings are missing or values are invalid.
    """
    return Settings()
```

### .env.defaults (committed to git)

```bash
# ============================================================
# MULTI-AGENT SYSTEM — CONFIGURATION REFERENCE
# ============================================================
# This file documents every configuration key accepted by the
# application. It is committed to git and contains safe defaults.
#
# To override locally: copy values to .env (gitignored)
# In production: set process environment variables directly
# ============================================================

# --- LLM ---
# OPENROUTER_API_KEY=          # REQUIRED. No default. Must be set in .env or env.
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=anthropic/claude-sonnet-4-5
LLM_MAX_TOKENS=1024
LLM_TIMEOUT_SECONDS=30.0

# --- TRANSPORT ---
TRANSPORT_BACKEND=sqlite      # sqlite | terminal
SQLITE_DB_PATH=data/agents.db
SQLITE_POLL_INTERVAL_SECONDS=1.0
SQLITE_WAL_MODE=true

# --- LOGGING ---
# Legacy single-level settings preserved for backward compatibility.
# Per-stream settings below take precedence.
LOG_LEVEL=INFO
LOG_FORMAT=console

# --- AGENT DEFAULTS ---
AGENT_DEFAULT_TIMEOUT_SECONDS=60.0
AGENT_MAX_RETRIES=3
AGENT_RETRY_BACKOFF_SECONDS=2.0

# --- PROMPTS ---
PROMPTS_DIR=prompts

# --- AGENT WIRING ---
AGENTS_CONFIG_PATH=agents.toml

# --- OBSERVABILITY ---
# Console stream
LOG_CONSOLE_ENABLED=true
LOG_CONSOLE_LEVEL=INFO

# Human-readable log file (.log) — disabled by default
LOG_HUMAN_FILE_ENABLED=false
LOG_HUMAN_FILE_LEVEL=INFO

# JSON Lines log file (.jsonl) — disabled by default
LOG_JSON_FILE_ENABLED=false
LOG_JSON_FILE_LEVEL=DEBUG

# Shared
LOG_DIR=logs
LOG_TRACE_LLM=false           # JSONL file only; console and .log never receive trace events
# EXPERIMENT=                  # optional label in filenames; override with --experiment flag
```

### .env.test (committed to git)

```bash
# Test environment overrides.
# Applied automatically when pytest sets ENVIRONMENT=test.
OPENROUTER_API_KEY=test-key-not-real
TRANSPORT_BACKEND=sqlite
SQLITE_DB_PATH=:memory:
LOG_LEVEL=WARNING
LOG_FORMAT=console
```

### .gitignore entries

```gitignore
.env
.env.local
.env.production
data/
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
```

---

## 6. Logging Standards

### Library

`structlog` is the sole logging library. The stdlib `logging` module is not used
directly in application code. `structlog` is configured to route through stdlib
`logging` for compatibility with third-party libraries.

### Logger Instantiation — One Pattern, Always

Every module that emits log events declares one module-level logger using `__name__`:

```python
import structlog

log = structlog.get_logger(__name__)
```

This is the **only** way to obtain a logger. Loggers are never passed as arguments,
never stored on instances as constructor arguments, and never retrieved by string name.

### Context Binding

Loggers carry context. Bind permanent context at class instantiation; bind ephemeral
context (per-operation) at operation start:

```python
class AgentRunner:
    def __init__(self, agent: LLMAgent, transport: Transport) -> None:
        # Permanent context — every log from this instance carries these fields
        self._log = structlog.get_logger(__name__).bind(
            agent=agent.name,
            transport=type(transport).__name__,
        )

    async def run_once(self) -> bool:
        msg = await self.transport.receive(self.agent.name)
        if not msg:
            return False
        # Ephemeral context — scoped to this operation
        op_log = self._log.bind(thread_id=msg.thread_id, msg_id=msg.id)
        op_log.info("message_received")
        ...
        op_log.info("message_processed", response_chars=len(response))
        return True
```

### Logger Hierarchy

```
root
└── multiagent
    ├── multiagent.config.settings
    ├── multiagent.core.agent
    ├── multiagent.core.runner
    ├── multiagent.transport.sqlite
    ├── multiagent.transport.terminal
    ├── multiagent.routing.router
    ├── multiagent.logging.setup
    └── multiagent.cli.run
```

### Log Level Discipline

| Level | Rule |
|---|---|
| `DEBUG` | Internal state dumps, every poll tick. Off in production. |
| `INFO` | One event per significant operation: message received, sent, agent started/stopped. |
| `WARNING` | Retry attempted, degraded mode, config fallback used. Actionable but not an error. |
| `ERROR` | Caught exception that affected an operation. Always include `exc_info=True`. |
| `CRITICAL` | Unrecoverable. Process is about to exit. |

**LLM trace events** are a special category emitted at `INFO` level with `event="llm_trace"`.
They carry the full prompt and response content and are only emitted when
`settings.log_trace_llm` is `True`. They are always written to the JSONL file when file
logging is enabled, never to the console renderer.

**Rule:** Never log at `ERROR` without an exception context. Never log at `DEBUG` in a
tight loop without first checking that DEBUG is enabled (performance).

### Three-Stream Output Design

Each stream is independently toggled and independently level-filtered. All three
share the same structlog processor chain up to the renderer stage.

| Stream | Toggle | Level setting | Renderer | Receives `llm_trace` |
|---|---|---|---|---|
| Console | `log_console_enabled` | `log_console_level` | `ConsoleRenderer(colors=True)` | Never |
| Human file (`.log`) | `log_human_file_enabled` | `log_human_file_level` | `ConsoleRenderer(colors=False)` | Never |
| JSON file (`.jsonl`) | `log_json_file_enabled` | `log_json_file_level` | `JSONRenderer()` | Yes (when `log_trace_llm=True`) |

`llm_trace` events are suppressed from console and human file via a
`logging.Filter` subclass applied to those two handlers. The JSONL handler
receives all events unfiltered.

Both file types use the same timestamp prefix and experiment label, landing
in `log_dir` side by side:

```
logs/2026-03-13T14-32-01_baseline.log
logs/2026-03-13T14-32-01_baseline.jsonl
```

`configure_logging()` returns a `tuple[Path | None, Path | None]` — the human
file path and the JSONL file path. Either is `None` if that stream is disabled.

### Logging Setup

Location: `src/multiagent/logging/setup.py`

`configure_logging()` signature as of Task 005:

```python
def configure_logging(
    settings: Settings,
    experiment: str = "",
) -> tuple[Path | None, Path | None]:
    """Configure structlog with up to three independent output streams.

    Attaches up to three stdlib logging handlers based on settings:
      - Console handler: ConsoleRenderer (colours) to stdout
      - Human file handler: ConsoleRenderer (no colours) to per-run .log file
      - JSON file handler: JSONRenderer to per-run .jsonl file

    Each handler has its own level filter. llm_trace events are suppressed
    from console and human file handlers via _SuppressLLMTrace filter.

    The effective experiment label is resolved in order:
      1. experiment argument (CLI --experiment flag)
      2. settings.experiment (env var / .env)
      3. Empty string (timestamp-only filename)

    Must be called once at process startup before any logging occurs.
    Call from CLI entry points only, never from library code.

    Args:
        settings: Validated application settings.
        experiment: Experiment label from CLI flag. Overrides settings.experiment.

    Returns:
        Tuple of (human_log_path, json_log_path). Either is None if that
        stream is disabled.

    Raises:
        OSError: If the log directory cannot be created.
    """
```

---

## 7. Exception Hierarchy

Location: `src/multiagent/exceptions.py`

All custom exceptions inherit from `MultiAgentError`. This allows callers to catch the
entire domain with a single except clause at process boundaries.

```python
class MultiAgentError(Exception):
    """Base exception for all multiagent system errors."""


# ── Configuration ────────────────────────────────────────────────────────────

class ConfigurationError(MultiAgentError):
    """Raised when configuration is missing or invalid. Occurs at startup."""


class MissingConfigurationError(ConfigurationError):
    """Raised when a required configuration key has no value."""


class InvalidConfigurationError(ConfigurationError):
    """Raised when a configuration value fails type or constraint validation."""


# ── Transport ─────────────────────────────────────────────────────────────────

class TransportError(MultiAgentError):
    """Raised when message transport operations fail."""


class MessageDeliveryError(TransportError):
    """Raised when a message cannot be delivered after all configured retries."""


class MessageReceiveError(TransportError):
    """Raised when message retrieval from the transport backend fails."""


class TransportConnectionError(TransportError):
    """Raised when the transport backend is unavailable or unreachable."""


# ── Agent ─────────────────────────────────────────────────────────────────────

class AgentError(MultiAgentError):
    """Raised when an agent fails to process a message."""


class AgentTimeoutError(AgentError):
    """Raised when an agent exceeds its configured execution time limit."""


class AgentLLMError(AgentError):
    """Raised when the LLM API returns an error or an unparseable response."""


# ── Routing ───────────────────────────────────────────────────────────────────

class RoutingError(MultiAgentError):
    """Raised when the routing layer cannot determine the next agent."""


class UnknownAgentError(RoutingError):
    """Raised when a message is addressed to an agent that does not exist."""
```

### Exception Handling Rules

1. Catch at the **most specific** subclass possible in agent/transport code.
2. Catch `MultiAgentError` only at the runner/process boundary for final logging and exit.
3. **Never** catch `Exception` or `BaseException` except at the absolute top of a CLI entry point.
4. Always include `exc_info=True` when logging a caught exception at `ERROR` level.
5. Always re-raise or wrap when catching in the middle of the call stack — never swallow.

---

## 8. Architecture and Module Boundaries

### The Message Dataclass

The `Message` dataclass is the **only** type that crosses the boundary between the
transport layer and the agent runner. It lives in `transport/base.py`.

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Message:
    """A unit of communication between agents.

    Instances of this class cross the transport/core boundary. The core layer
    receives and produces Message objects; it never touches transport internals.

    The to_agent field accepts a single agent name, a list of agent names, or
    the broadcast sentinel "*". The transport layer resolves lists and "*" into
    individual per-recipient rows before persistence — the dataclass itself
    carries the caller's original addressing intent.

    All timestamps are UTC. Timestamps are set by the transport at the
    relevant lifecycle event — never by the caller except created_at.

    Attributes:
        from_agent: Sending agent name, or "human" for external injection.
        to_agent: Recipient — single name, list of names, or "*" for broadcast.
        body: Message payload — plain text.
        subject: Optional topic label for routing. Empty string if unused.
        thread_id: UUID grouping all messages in one conversation chain.
            Defaults to a new UUID — callers should pass an existing thread_id
            when continuing a thread.
        parent_id: Database id of the message this is a direct reply to.
            None for thread-initiating messages.
        id: Database-assigned integer id. None until persisted.
        created_at: UTC timestamp of object construction. Set by caller.
        sent_at: UTC timestamp when transport.send() persisted the message.
            Set by transport — None until send() is called.
        received_at: UTC timestamp when transport.receive() fetched this message.
            Set by transport — None until an agent polls and receives it.
        processed_at: UTC timestamp when transport.ack() was called.
            Set by transport — None until processing is confirmed complete.
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

**Import note:** `timezone` must be imported from `datetime`:
```python
from datetime import datetime, timezone
```

### The Transport Abstract Base Class

```python
from abc import ABC, abstractmethod


class Transport(ABC):
    """Abstract port for agent message I/O.

    Concrete adapters implement this interface. Agent code depends only on
    this abstraction — never on concrete adapter classes.

    Fanout semantics: when message.to_agent is a list or "*", send() expands
    the message into one delivery per resolved recipient before persistence.
    The abstract interface accepts the full addressing intent; adapters own
    the expansion logic.
    """

    @abstractmethod
    async def receive(self, agent_name: str) -> Message | None:
        """Fetch the next unprocessed message addressed to agent_name.

        Non-blocking — returns None immediately if no message is available.
        The runner loop is responsible for polling and backoff.

        Sets received_at on the returned Message to UTC now.

        Args:
            agent_name: The name of the agent whose mailbox to check.

        Returns:
            The next Message, or None if the mailbox is empty.

        Raises:
            MessageReceiveError: If the backend fails during retrieval.
        """

    @abstractmethod
    async def send(self, message: Message) -> None:
        """Deliver a message to the transport backend.

        Handles fanout: if message.to_agent is a list, one row is written
        per recipient. If message.to_agent is "*", the transport resolves
        the recipient list from previously seen agent names and fans out.

        Sets sent_at on each persisted row to UTC now.

        Args:
            message: The Message to deliver. to_agent may be str, list, or "*".

        Raises:
            MessageDeliveryError: If persistence fails.
            TransportConnectionError: If the backend is unavailable.
        """

    @abstractmethod
    async def ack(self, message_id: int) -> None:
        """Mark a message as processed so it is not delivered again.

        Sets processed_at on the row to UTC now.

        Args:
            message_id: The id of the Message to acknowledge.

        Raises:
            MessageAcknowledgementError: If the ack cannot be persisted.
        """

    @abstractmethod
    async def known_agents(self) -> list[str]:
        """Return all agent names seen as to_agent recipients.

        Used by send() to resolve broadcast "*" to a concrete recipient list.
        Returns an empty list if no messages have been persisted yet.

        Returns:
            Sorted list of distinct agent name strings.

        Raises:
            TransportConnectionError: If the backend is unavailable.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release all resources held by this transport instance."""
```

### SQLite Schema

The schema is owned by `SQLiteTransport` and applied via `_ensure_schema()` on
first connection. No external migration tool is used for the PoC.

All timestamp columns are `TEXT` in ISO8601 UTC format
(`2026-03-13T10:00:00.000000+00:00`). SQLite has no native datetime type.
ISO8601 strings sort correctly as text and round-trip through
`datetime.fromisoformat()` without loss.

```sql
CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    from_agent    TEXT     NOT NULL,
    to_agent      TEXT     NOT NULL,          -- always single agent after fanout
    subject       TEXT     NOT NULL DEFAULT '',
    body          TEXT     NOT NULL DEFAULT '',
    thread_id     TEXT     NOT NULL,
    parent_id     INTEGER  REFERENCES messages(id),
    created_at    TEXT     NOT NULL,          -- UTC ISO8601, set by caller
    sent_at       TEXT,                       -- UTC ISO8601, set by transport.send()
    received_at   TEXT,                       -- UTC ISO8601, set by transport.receive()
    processed_at  TEXT                        -- UTC ISO8601, set by transport.ack()
);

-- Hot path: every agent poll hits this index
CREATE INDEX IF NOT EXISTS idx_inbox
    ON messages(to_agent, processed_at, created_at);

-- Thread reconstruction for debugging and conversation history
CREATE INDEX IF NOT EXISTS idx_thread
    ON messages(thread_id, created_at);
```

WAL mode and synchronous=NORMAL are applied at connection time for concurrent
read performance. Both are configured via settings.

---

## 9. Coding Standards

### General Rules

- **Line length:** 100 characters (configured in ruff).
- **Type annotations:** mandatory on all function signatures and class attributes.
  No `Any` without a `# type: ignore[misc]` comment explaining why.
- **No mutable default arguments.** Use `None` with `if x is None: x = []`.
- **No bare `except:`.** Always specify the exception type.
- **No `print()` in application code.** All output goes through `structlog`.
- **No `os.path`.** Use `pathlib.Path` exclusively.
- **No f-string logging.** Use structlog keyword arguments: `log.info("event", key=val)`.
- **Imports:** standard library → third-party → local. `ruff` enforces this automatically.
- **`from __future__ import annotations`** at the top of every source file. Enables
  PEP 563 postponed evaluation, required for forward references in type hints.

### Async Rules

- All I/O-performing functions are `async def`. No blocking I/O in coroutines.
- Use `asyncio.timeout()` (Python 3.11+) for operation timeouts, not `asyncio.wait_for`.
- Use `async with` and `async for` where the protocol supports it.
- CLI entry points call `asyncio.run(main())`. No `asyncio.get_event_loop()`.
- On Windows, set the event loop policy at process startup:

```python
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

### Naming Conventions

| Construct | Convention | Example |
|---|---|---|
| Module | `snake_case` | `sqlite_transport.py` |
| Class | `PascalCase` | `SQLiteTransport` |
| Function / method | `snake_case` | `receive_message` |
| Constant | `UPPER_SNAKE_CASE` | `DEFAULT_POLL_INTERVAL` |
| Private attribute | `_leading_underscore` | `_connection` |
| Type alias | `PascalCase` | `AgentName = str` |
| Abstract method | no prefix | `receive` (not `_receive`) |

### Semantic Versioning

The project follows **Semantic Versioning 2.0.0** (`MAJOR.MINOR.PATCH`).

| Component | Increment when |
|---|---|
| `MAJOR` | Breaking change to a public interface or behaviour contract |
| `MINOR` | New capability added in a backwards-compatible way |
| `PATCH` | Backwards-compatible bug fix or documentation update |

**Single source of truth for the version:** `pyproject.toml` `[project] version`.
The package `__init__.py` reads it at import time using `importlib.metadata`:

```python
# src/multiagent/__init__.py
from importlib.metadata import version, PackageNotFoundError

try:
    __version__: str = version("multiagent")
except PackageNotFoundError:
    # Package is not installed — running from source without `uv pip install -e .`
    __version__ = "0.0.0+dev"
```

**Version is never hardcoded** in any file other than `pyproject.toml`.
All other code that needs the version imports `from multiagent import __version__`.

**PoC versioning convention:**
- Start at `0.1.0` — signals unstable, under development
- Increment `MINOR` for each significant PoC milestone
- Move to `1.0.0` only when the architecture is considered stable
- Pre-release labels are permitted: `0.2.0-alpha.1`, `0.2.0-beta.1`

**Release commit convention:**
```bash
git commit -m "chore(release): bump version to 0.2.0"
git tag -a v0.2.0 -m "Release 0.2.0 — SQLite transport complete"
```

### Constants

Only true constants (values that are never configurable and never change at runtime)
belong in `constants.py`. Examples: protocol version strings, fixed schema versions.
All other values belong in `settings.py`.

---

## 10. Docstring Standard

**Google style** is mandatory for all public modules, classes, functions, and methods.
`ruff` with `pydocstyle` convention `"google"` enforces this.

### Module Docstring

```python
"""SQLite transport adapter for the multi-agent messaging system.

Implements the Transport ABC using an SQLite database as a persistent
message store. Supports concurrent readers via WAL journal mode.
Intended for development and PoC use — not for high-throughput production.
"""
```

### Class Docstring

```python
class SQLiteTransport(Transport):
    """Transport adapter backed by an SQLite database file.

    Provides durable, inspectable message storage with zero infrastructure
    requirements. Messages persist across process restarts. Multiple agents
    may share one database file safely via WAL mode concurrency.

    Attributes:
        db_path: Resolved path to the SQLite database file.
        poll_interval: Seconds between mailbox checks when idle.
    """
```

### Function / Method Docstring

```python
async def receive(self, agent_name: str) -> Message | None:
    """Fetch the next unprocessed message addressed to the given agent.

    Performs a single non-blocking query. Returns immediately whether or not
    a message is available. The caller is responsible for polling.

    Args:
        agent_name: The name of the agent whose mailbox to query.
            Must match the to_agent field of stored messages exactly.

    Returns:
        The oldest unprocessed Message for agent_name, or None if the
        mailbox is empty.

    Raises:
        MessageReceiveError: If the database query fails.

    Example:
        >>> transport = SQLiteTransport(Path("agents.db"))
        >>> msg = await transport.receive("researcher")
        >>> if msg:
        ...     print(msg.body)
    """
```

### Inline Comments

Use inline comments sparingly — only to explain **why**, never **what**. The code
explains what; the docstring explains the contract; comments explain non-obvious intent.

```python
# WAL mode allows concurrent readers while a writer holds a lock.
# Without this, multiple agents reading the same DB cause lock contention.
await conn.execute("PRAGMA journal_mode=WAL;")
```

---

## 11. Testing Strategy

### Two-Tier Model

**Tier 1 — Unit tests** (`tests/unit/`)
- Run on every commit and in CI.
- LLM API calls are mocked. No network I/O.
- SQLite tests use `:memory:` databases.
- Coverage target: **80% minimum** on `src/multiagent/` excluding `cli/`.
- TDD is the preferred development approach: write the test first, run it (red),
  implement (green), refactor (clean).

**Tier 2 — Integration tests** (`tests/integration/`)
- Run explicitly: `just test-integration`.
- Make real LLM API calls. Require `ANTHROPIC_API_KEY` in environment.
- Assert structure and type of responses, never exact content (LLMs are non-deterministic).
- Cover key happy-path pipelines only — not exhaustive scenarios.
- Gated by `@pytest.mark.integration` marker. Excluded from default `pytest` run.

### Shared Fixtures — conftest.py

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock

from multiagent.transport.base import Message


@pytest.fixture
def mock_llm_response():
    """Factory fixture returning a callable that produces mock LLM text."""
    def factory(text: str = "mocked llm response") -> AsyncMock:
        mock = AsyncMock()
        mock.return_value.content = text
        return mock
    return factory


@pytest.fixture
def sample_message() -> Message:
    """A valid Message instance for use in transport and runner tests."""
    return Message(
        from_agent="human",
        to_agent="researcher",
        body="Research the history of the internet.",
        subject="research-task",
        thread_id="test-thread-001",
    )
```

### Unit Test Pattern

```python
# tests/unit/core/test_agent.py
import pytest
from unittest.mock import AsyncMock, patch

from multiagent.core.agent import LLMAgent


async def test_agent_returns_llm_response(mock_llm_response):
    """Agent.run() returns the text from the LLM response."""
    mock = mock_llm_response("The internet began in 1969 with ARPANET.")

    with patch("multiagent.core.agent.ChatAnthropic", return_value=mock):
        agent = LLMAgent(name="researcher", system_prompt="You are a researcher.")
        result = await agent.run("Research the history of the internet.")

    assert result == "The internet began in 1969 with ARPANET."


async def test_agent_passes_system_prompt_to_llm(mock_llm_response):
    """Agent.run() includes the system prompt in every LLM invocation."""
    mock = mock_llm_response()
    system_prompt = "You are a specialized research agent."

    with patch("multiagent.core.agent.ChatAnthropic", return_value=mock) as llm_cls:
        agent = LLMAgent(name="researcher", system_prompt=system_prompt)
        await agent.run("test input")

    call_args = llm_cls.return_value.call_args
    assert system_prompt in str(call_args)
```

### Integration Test Pattern

```python
# tests/integration/test_agent_pipeline.py
import pytest

from multiagent.core.agent import LLMAgent


@pytest.mark.integration
async def test_researcher_agent_returns_text():
    """Researcher agent produces a non-empty text response from the real LLM."""
    agent = LLMAgent(
        name="researcher",
        system_prompt="You are a researcher. Be concise. One sentence maximum.",
    )
    result = await agent.run("What is TCP/IP? One sentence.")

    assert isinstance(result, str)
    assert len(result) > 10
    # Never assert exact content — LLMs are non-deterministic
```

### Running Tests

```bash
just test              # unit tests only (default, fast, no LLM)
just test-coverage     # unit tests with coverage report
just test-integration  # integration tests (requires ANTHROPIC_API_KEY)
just test-all          # all tests
```

---

## 12. Git Workflow

### Repository State

The repository is initialised, has a remote, and `master` is the stable integration
branch. All work happens in feature branches. No commits directly to `master`.

```bash
# Verify remote and branch state before starting any task
git remote -v
git branch -a
git worktree list
```

### Branching Convention

```
master                  — stable, always passing, protected
feature/<short-name>    — new functionality
fix/<short-name>        — bug fixes
docs/<short-name>       — documentation only changes
chore/<short-name>      — tooling, dependencies, config
adr/<record-number>     — architecture decision records
```

**Note:** This project uses `master` as the integration branch, not `main`.
This is the established convention for this repository and must not be changed.

### Starting a New Task — Standard Sequence

Every task follows this sequence before writing a single line of code:

```bash
# 1. Ensure master is up to date with remote
git checkout master
git pull origin master

# 2. Create worktree for the new task branch
git worktree add ../multiagent-<slug> feature/<slug>

# 3. Confirm state
git worktree list
```

### Completing a Task — Standard Sequence

```bash
# 1. Ensure all acceptance criteria pass in the worktree
cd ../multiagent-<slug>
just check && just test

# 2. Push branch to remote
git push origin feature/<slug>

# 3. Merge to master locally
git checkout master
git merge feature/<slug> --ff-only

# 4. Push master to remote
git push origin master

# 5. Remove worktree
git worktree remove ../multiagent-<slug>

# 6. Delete merged branch
git branch -d feature/<slug>
```

`--ff-only` is mandatory on merge. If the merge cannot fast-forward, the branch
has diverged from master and must be rebased before merging.

### Git Worktrees — Parallel Development

Worktrees allow multiple branches to be checked out simultaneously in separate
directories without stashing or switching. Use for parallel workstreams:

```bash
# From the repository root
git worktree add ../multiagent-transport feature/transport
git worktree add ../multiagent-core feature/agent-core

# Each directory is an independent working tree on its branch
cd ../multiagent-transport
# ... work on transport ...

cd ../multiagent-core
# ... work on agent core simultaneously ...

# List active worktrees
git worktree list

# Clean up when branch is merged
git worktree remove ../multiagent-transport
```

### Commit Message Convention

[Conventional Commits](https://www.conventionalcommits.org/) format is required:

```
<type>(<scope>): <subject>

<body — optional, explains why not what>

<footer — references issues, breaking changes>
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`

Examples:

```
feat(transport): implement SQLite receive with WAL mode

fix(runner): handle empty message body without raising AgentError

docs(adr): add ADR-0004 for SQLite transport selection

chore(deps): bump langgraph to 0.2.1
```

---

## 13. Task Runner

All runnable operations are defined in `justfile`. `just` must be installed separately
and is available cross-platform. See https://github.com/casey/just.

```makefile
# justfile

# Default: list available tasks
default:
    @just --list

# ── Setup ──────────────────────────────────────────────────────────────────

# Install all dependencies and pre-commit hooks
setup:
    uv sync --all-extras
    uv run pre-commit install
    @echo "Setup complete. Copy .env.defaults to .env and set ANTHROPIC_API_KEY."

# ── Code Quality ───────────────────────────────────────────────────────────

# Format and lint with ruff
lint:
    uv run ruff check src tests --fix
    uv run ruff format src tests

# Type check with pyright
typecheck:
    uv run pyright src tests

# Run all quality checks (no fixes applied)
check:
    uv run ruff check src tests
    uv run ruff format src tests --check
    uv run pyright src tests

# ── Testing ────────────────────────────────────────────────────────────────

# Run unit tests (default — no LLM calls)
test:
    uv run pytest tests/unit

# Run unit tests with coverage report
test-coverage:
    uv run pytest tests/unit --cov=src/multiagent --cov-report=term-missing --cov-report=html

# Run integration tests (requires ANTHROPIC_API_KEY)
test-integration:
    uv run pytest tests/integration -m integration -v

# Run all tests
test-all:
    uv run pytest tests -m "" -v

# ── Application ────────────────────────────────────────────────────────────

# Run a named agent (polls for messages until interrupted)
run agent experiment="":
    uv run multiagent run {{agent}} {{if experiment != "" { "--experiment " + experiment } else { "" }}}

# Inject a message into the transport for a named agent
send agent body:
    uv run multiagent send {{agent}} "{{body}}"

# ── Database ───────────────────────────────────────────────────────────────

# Show last N messages across all agents
db-tail n="20":
    sqlite3 data/agents.db "SELECT id, from_agent, to_agent, substr(body,1,60) as body, processed_at FROM messages ORDER BY created_at DESC LIMIT {{n}};"

# Show all pending (unprocessed) messages by agent
db-pending:
    sqlite3 data/agents.db "SELECT to_agent, count(*) as pending FROM messages WHERE processed_at IS NULL GROUP BY to_agent;"

# Show per-agent message counts and last activity
db-agents:
    sqlite3 data/agents.db "SELECT to_agent, count(*) as total, sum(processed_at IS NOT NULL) as done, max(created_at) as last_seen FROM messages GROUP BY to_agent;"

# Clear all messages from the transport database
db-clear:
    sqlite3 data/agents.db "DELETE FROM messages;"

# ── Inspection scripts ─────────────────────────────────────────────────────

# Show a conversation thread from SQLite, formatted with rich
thread thread_id:
    uv run python scripts/show_thread.py {{thread_id}}

# Show a summary of a single run log file
run-summary log_file:
    uv run python scripts/show_run.py {{log_file}}

# Compare two run log files side by side
compare log1 log2:
    uv run python scripts/compare_runs.py {{log1}} {{log2}}

# List all run log files with metadata
runs:
    @ls -lt logs/*.jsonl 2>/dev/null || echo "No run logs found in logs/"

# ── Documentation ──────────────────────────────────────────────────────────

# List all Architecture Decision Records
adr-list:
    @ls docs/adr/

# ── Maintenance ────────────────────────────────────────────────────────────

# Update all dependencies to latest compatible versions
update:
    uv sync --upgrade

# Remove all generated artifacts
clean:
    rm -rf .venv .ruff_cache .pytest_cache htmlcov .coverage
    find . -type d -name __pycache__ -exec rm -rf {} +
```

---

## 14. Documentation Standards

### docs/ Folder Structure

```
docs/
├── adr/                     # Architecture Decision Records
│   └── NNNN-title.md        # zero-padded 4-digit sequence
├── architecture.md          # system overview, diagrams, module map
├── getting-started.md       # clone → setup → first run, 5 minutes
└── transport-guide.md       # how to implement a new Transport adapter
```

### Task Briefs — `tasks/`

Task briefs are implementation instructions authored by the architect and consumed by
Claude Code. They are distinct from documentation: they are work instructions, not
reference material.

```
tasks/
├── README.md                # task lifecycle and conventions
├── 001-skeleton.md          # complete, permanent record
├── 002-transport-sqlite.md  # in progress
└── 003-agent-core.md        # planned
```

**Naming:** zero-padded three-digit sequence number followed by a short slug.
`001-skeleton.md`, `002-transport-sqlite.md`.

**Lifecycle states** (recorded in the file header):

| State | Meaning |
|---|---|
| `DRAFT` | Being authored by architect, not yet handed to Claude Code |
| `APPROVED` | Architect sign-off complete, ready for Claude Code planning phase |
| `IN PROGRESS` | Claude Code is implementing |
| `COMPLETE` | Implementation merged, acceptance criteria met |

**Tasks are never deleted.** Completed tasks are permanent record of what was built,
in what order, and under what constraints. They are the implementation audit trail.

**`tasks/README.md` content:**

```markdown
# Tasks

Each file is a Claude Code implementation brief authored by the architect.

## Workflow

1. Architect drafts brief in Claude.ai (DRAFT)
2. Architect reviews and approves (APPROVED)
3. Claude Code reads brief, produces plan, plan is reviewed by architect
4. Claude Code implements against approved plan (IN PROGRESS)
5. Acceptance criteria verified, branch merged (COMPLETE)

## Naming Convention

NNN-short-slug.md — three-digit zero-padded sequence, hyphenated slug.
Example: 001-skeleton.md, 002-transport-sqlite.md

## Completed Tasks

Completed tasks are kept permanently as an implementation audit trail.
Do not delete or modify completed task files.
```

### Architecture Decision Records

One ADR per significant decision. An ADR is **never deleted** — superseded ADRs are
marked as such and link to their replacement. Template:

```markdown
# ADR-NNNN: Title

**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Superseded by ADR-XXXX
**Deciders:** Radek Zítek

## Context

What is the situation that forces a decision? What constraints exist?

## Decision

What was decided, stated plainly.

## Rationale

Why this option over the alternatives considered.

## Alternatives Considered

- **Alternative A** — why rejected
- **Alternative B** — why rejected

## Consequences

What becomes easier, harder, or different as a result of this decision.
```

Initial ADRs to create at project inception:

- `0001-python-312.md` — Python version pin
- `0002-uv-package-manager.md` — uv over poetry/pip
- `0003-async-first.md` — async throughout the codebase
- `0004-sqlite-transport-poc.md` — SQLite as PoC message bus
- `0005-langgraph-agent-internals.md` — LangGraph for agent graphs

### README.md Minimum Content

- Project purpose (two sentences)
- Prerequisites (Python 3.12, uv, just)
- Setup: `just setup`
- First run: `just run`
- Running tests: `just test`
- Link to `docs/architecture.md`
- Link to `docs/getting-started.md`

---

## 15. Cross-Platform Rules

The system must run identically on Windows, Linux, and macOS without platform-specific
code paths in the application layer. Differences are handled at the infrastructure level.

### Mandatory Practices

**Paths — always `pathlib.Path`:**

```python
# Never
path = "data/agents.db"
path = os.path.join("data", "agents.db")

# Always
from pathlib import Path
path = Path("data") / "agents.db"
```

**Line endings — never hardcode:**

```python
# Never
text.split("\n")
text + "\n"

# Always
text.splitlines()
text + os.linesep   # or let the file open mode handle it
```

**Windows asyncio event loop — set at entry point:**

```python
# src/multiagent/cli/run.py
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

asyncio.run(main())
```

**SQLite on Windows — use WAL mode:**
SQLite default journal mode has file locking issues on Windows with multiple readers.
WAL mode resolves this. `SQLITE_WAL_MODE=true` is the default in `.env.defaults`.

**Shell commands in justfile — cross-platform safe:**
`just` uses `sh` on Unix and `cmd` on Windows by default. Avoid shell-specific syntax.
For any task requiring shell features, use a Python script instead of inline shell.

**File encoding — always explicit:**

```python
# Never
open("file.txt", "r")

# Always
open("file.txt", "r", encoding="utf-8")
```

---

## 16. Dependency Reference

### Runtime Dependencies

| Package | Purpose | Import As |
|---|---|---|
| `langgraph` | Agent graph orchestration | `from langgraph.graph import StateGraph` |
| `langchain-openai` | OpenAI-compatible LLM client for LangGraph | `from langchain_openai import ChatOpenAI` |
| `openai` | Underlying SDK used by langchain-openai | transitive — do not import directly |
| `pydantic-settings` | Configuration with validation | `from pydantic_settings import BaseSettings` |
| `structlog` | Structured logging | `import structlog` |
| `aiosqlite` | Async SQLite access | `import aiosqlite` |
| `typer` | Type-annotated CLI framework | `import typer` |
| `click` | CLI primitives underlying typer | transitive — do not import directly |

### Development Dependencies

| Package | Purpose | Used Via |
|---|---|---|
| `ruff` | Lint and format | `just lint`, pre-commit |
| `pyright` | Static type checking | `just typecheck`, pre-commit |
| `pytest` | Test runner | `just test` |
| `pytest-asyncio` | Async test support | `asyncio_mode = "auto"` in config |
| `pytest-mock` | Mock and spy fixtures | `mocker` fixture |
| `respx` | Mock httpx HTTP calls | `respx.mock` context manager |
| `pre-commit` | Git hook runner | `just setup` |
| `rich` | Terminal formatting for inspection scripts | `scripts/` only — never imported in `src/` |

### Explicitly Excluded

The following packages are **not used** in this project. If a dependency pulls them in
transitively that is acceptable, but they must not be imported directly in application code:

| Package | Reason Excluded |
|---|---|
| `python-dotenv` | Superseded by `pydantic-settings` |
| `black` | Superseded by `ruff format` |
| `flake8` | Superseded by `ruff` |
| `isort` | Superseded by `ruff` |
| `logging` (stdlib direct use) | Superseded by `structlog` |
| `os.path` | Superseded by `pathlib.Path` |

---

*End of Implementation Guide v1.0.0*

*This document is the authoritative reference for all implementation decisions.
Claude Code reads this document before writing any code and adheres to all rules herein.
Changes to this document require architect review and an updated ADR if the change
affects a previously recorded decision.*
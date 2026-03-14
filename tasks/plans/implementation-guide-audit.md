# Implementation Guide Audit — Gap Report

**Audited:** `docs/implementation-guide.md` v1.0.0 (2026-03-13)
**Against:** Codebase at commit `d3d76a7` (2026-03-14)
**Auditor:** Tom (implementer agent)

---

## Section 1: Project Overview

**CORRECT** — Core principles (separation of concerns, hexagonal architecture, async-first,
configuration over code) match the codebase.

---

## Section 2: Technology Stack

| Item | Status | Detail |
|------|--------|--------|
| Technology table | **STALE** | Guide says `langchain-anthropic` — codebase uses `langchain-openai` (switched to OpenRouter) |
| Pinned versions block | **STALE** | Guide lists `langchain-anthropic>=0.2` — actual dependency is `langchain-openai>=0.3` |
| Pinned versions block | **STALE** | Guide omits `langgraph-checkpoint-sqlite` — present in actual pyproject.toml |
| Pinned versions block | **STALE** | Guide omits `rich` — it's a runtime dependency in actual pyproject.toml, not just dev |

---

## Section 3: Repository Structure

### Directory tree

| Item | Status | Detail |
|------|--------|--------|
| `src/multiagent/core/state.py` | **WRONG** | Listed in guide — file does not exist and never existed. LangGraph state is defined inline in agent.py using `MessagesState` |
| `src/multiagent/routing/` | **WRONG** | Listed in guide — directory does not exist. No routing module was ever implemented |
| `tests/unit/routing/test_router.py` | **WRONG** | Listed in guide — does not exist (routing module never created) |
| `docs/architecture.md` | **WRONG** | Listed in guide — does not exist |
| `docs/getting-started.md` | **WRONG** | Listed in guide — does not exist |
| `docs/transport-guide.md` | **WRONG** | Listed in guide — does not exist |
| `docs/adr/0001-python-312.md` through `0005-*` | **WRONG** | Listed in guide — only `docs/adr/README.md` exists. No ADR files were created |
| `prompts/researcher.md`, `prompts/critic.md` | **STALE** | Guide lists these two — actual prompts are: alfa, beta, conservative, digger, edith, editor, linguist, progressive, prose, scout, vera, writer |
| `scripts/browse_threads.py` | **MISSING** | Exists in codebase, not listed in guide |
| `scripts/show_costs.py` | **MISSING** | Exists in codebase, not listed in guide |
| `src/multiagent/core/costs.py` | **MISSING** | Exists in codebase (CostLedger, CostEntry), not in guide tree |
| `src/multiagent/core/shutdown.py` | **MISSING** | Exists in codebase (ShutdownMonitor), not in guide tree |
| `src/multiagent/version.py` | **MISSING** | Exists in codebase (SemVer, bump utilities), not in guide tree |
| `src/multiagent/cli/start.py` | **MISSING** | Exists in codebase, not in guide tree |
| `src/multiagent/cli/stop.py` | **MISSING** | Exists in codebase, not in guide tree |
| `src/multiagent/cli/listen.py` | **MISSING** | Exists in codebase, not in guide tree |
| `src/multiagent/cli/chat.py` | **MISSING** | Exists in codebase, not in guide tree |
| `src/multiagent/cli/version.py` | **MISSING** | Exists in codebase, not in guide tree |
| CLI main.py description | **STALE** | Guide says "run and send commands" — actual: run, send, start, stop, listen, chat, version |
| `config/__init__.py` exports | **STALE** | Guide says `exports Settings, get_settings, AgentConfig, load_agents_config` — actual exports: `Settings, load_settings, AgentConfig, load_agents_config` (no `get_settings`) |
| `transport/__init__.py` exports | **STALE** | Guide says `exports Transport, Message` — actual also exports `create_transport` |
| Task files | **STALE** | Guide lists 001–005 — actual tasks go through 011b plus CR files and plans/ subdirectory |

### Module dependency rules

**CORRECT** — The stated import rules (core must not import transport/cli, etc.) are
respected in the codebase.

---

## Section 4: Environment and Tooling Setup

| Item | Status | Detail |
|------|--------|--------|
| `uv add langchain-anthropic` | **STALE** | Should be `uv add langchain-openai` |
| pyproject.toml `[project.scripts]` | **STALE** | Guide: `multiagent = "multiagent.cli.run:main"` — Actual: `multiagent = "multiagent.cli.main:main"` |
| pyproject.toml version | **STALE** | Guide: `0.1.0` — Actual: `0.1.1` |
| pyproject.toml dependencies | **STALE** | Guide lists `langchain-anthropic>=0.2` — Actual: `langchain-openai>=0.3`. Guide omits `langgraph-checkpoint-sqlite`, `rich` |
| pyproject.toml dev deps | **STALE** | Guide omits `pytest-cov` — present in actual pyproject.toml |
| ruff lint `select` | **STALE** | Guide includes `"ANN"` (annotations) and `"D"` (docstrings) — Actual pyproject.toml does not select these rules |
| ruff lint `ignore` | **STALE** | Guide lists `ANN101`, `ANN102`, `D100`, `D104` — Actual has no ignore list (these rules aren't selected) |
| ruff `pydocstyle` convention | **STALE** | Guide specifies `convention = "google"` — Actual pyproject.toml has no pydocstyle configuration |
| ruff per-file-ignores | **STALE** | Guide has `"tests/**" = ["ANN", "D"]` — Actual has no per-file-ignores |
| `check` target | **STALE** | Guide: runs ruff check + ruff format --check + pyright — Actual: runs ruff check (lint) + pyright (no format check) |
| `test` target | **STALE** | Guide: `uv run pytest tests/unit` — Actual: `uv run pytest tests/unit/ -v` |
| coverage config | **STALE** | Guide has `[tool.coverage.report] fail_under = 80` — Actual pyproject.toml has `fail_under = 80` but different omit pattern |

---

## Section 5: Configuration System

### Settings class

| Item | Status | Detail |
|------|--------|--------|
| `get_settings()` with `@lru_cache` | **WRONG** | Guide documents `get_settings()` with caching — Actual: `load_settings()` with no caching, raises `InvalidConfigurationError` |
| `sqlite_wal_mode` field | **WRONG** | Listed in guide — does not exist in Settings. WAL mode is hardcoded in SQLiteTransport._get_connection() |
| `log_level` field | **WRONG** | Listed in guide — does not exist in Settings. Replaced by per-stream level fields |
| `log_format` field | **WRONG** | Listed in guide — does not exist in Settings. The three-stream design replaced it |
| `agent_default_timeout_seconds` field | **WRONG** | Listed in guide — does not exist in Settings |
| `agent_max_retries` field | **WRONG** | Listed in guide — does not exist in Settings. Hardcoded as `3` in AgentRunner |
| `agent_retry_backoff_seconds` field | **WRONG** | Listed in guide — does not exist in Settings. Hardcoded as `2.0` in AgentRunner |
| `app_name` field | **MISSING** | Exists in Settings, not in guide's Settings listing |
| `app_env` field | **MISSING** | Exists in Settings, not in guide's Settings listing |
| `cost_db_path` field | **MISSING** | Exists in Settings (`Path("data/costs.db")`), not in guide |
| `chat_reply_timeout_seconds` field | **MISSING** | Exists in Settings (120.0), not in guide |
| `greeting_message` field | **MISSING** | Exists in Settings, not in guide |
| `greeting_secret` field | **MISSING** | Exists in Settings (required, no default), not in guide |
| Nested delimiter comment | **STALE** | Guide docstring mentions `AGENT__DEFAULT_TIMEOUT_SECONDS` — no such nested setting exists |

### .env.defaults

| Item | Status | Detail |
|------|--------|--------|
| `SQLITE_WAL_MODE=true` | **WRONG** | Listed in guide — not in actual .env.defaults (no such setting) |
| `LOG_LEVEL=INFO` | **WRONG** | Listed in guide — not in actual .env.defaults (no such setting) |
| `LOG_FORMAT=console` | **WRONG** | Listed in guide — not in actual .env.defaults (no such setting) |
| `AGENT_DEFAULT_TIMEOUT_SECONDS` | **WRONG** | Listed in guide — not in actual .env.defaults |
| `AGENT_MAX_RETRIES` | **WRONG** | Listed in guide — not in actual .env.defaults |
| `AGENT_RETRY_BACKOFF_SECONDS` | **WRONG** | Listed in guide — not in actual .env.defaults |
| `LLM_MODEL` value | **STALE** | Guide: `anthropic/claude-sonnet-4-5` — Actual .env.defaults: `x-ai/grok-4.20-beta` |
| `SQLITE_POLL_INTERVAL_SECONDS` value | **STALE** | Guide: `1.0` — Actual .env.defaults: `10.0` |
| `APP_NAME`, `APP_ENV` | **MISSING** | In actual .env.defaults, not in guide |
| `GREETING_MESSAGE`, `GREETING_SECRET` | **MISSING** | In actual .env.defaults, not in guide |
| `COST_DB_PATH` | **MISSING** | In actual .env.defaults, not in guide |
| `CHAT_REPLY_TIMEOUT_SECONDS` | **MISSING** | In actual .env.defaults, not in guide |
| `CHECKPOINTER_DB_PATH` | **MISSING** | In actual .env.defaults, not in guide's .env.defaults block |

### .env.test

| Item | Status | Detail |
|------|--------|--------|
| Content | **STALE** | Guide shows `OPENROUTER_API_KEY`, `TRANSPORT_BACKEND`, `SQLITE_DB_PATH`, `LOG_LEVEL`, `LOG_FORMAT` — Actual .env.test has different fields: per-stream logging, GREETING_*, PROMPTS_DIR, AGENTS_CONFIG_PATH, CHECKPOINTER_DB_PATH |

---

## Section 6: Logging Standards

| Item | Status | Detail |
|------|--------|--------|
| `log = structlog.get_logger(__name__)` pattern | **STALE** | Guide says module-level logger with `__name__`. Actual codebase uses `structlog.get_logger()` (no `__name__`) with `.bind()` at class init, e.g. `structlog.get_logger().bind(transport="sqlite")` |
| Logger hierarchy | **STALE** | Guide lists `multiagent.routing.router` — routing module doesn't exist. Missing: `multiagent.core.costs`, `multiagent.core.shutdown` |
| AgentRunner logging example | **STALE** | Guide shows `AgentRunner(agent, transport)` — Actual constructor: `AgentRunner(agent, transport, settings, next_agent, shutdown_monitor)` |
| Three-stream design | **CORRECT** | Console, .log, .jsonl streams match |
| `configure_logging()` signature | **CORRECT** | Matches actual implementation |

---

## Section 7: Exception Hierarchy

| Item | Status | Detail |
|------|--------|--------|
| `MessageAcknowledgementError` | **MISSING** | Exists in codebase under TransportError, not listed in guide |
| `AgentConfigurationError` | **MISSING** | Exists in codebase under AgentError, not listed in guide |
| Everything else | **CORRECT** | All other exceptions match |

---

## Section 8: Architecture and Module Boundaries

### Message dataclass

| Item | Status | Detail |
|------|--------|--------|
| `datetime.now(timezone.utc)` | **STALE** | Guide uses `from datetime import datetime, timezone` with `timezone.utc` — Actual uses `from datetime import UTC, datetime` with `datetime.now(UTC)` (Python 3.12+ shorthand) |
| Import note about `timezone` | **STALE** | Guide says "import timezone from datetime" — actual imports `UTC` directly |
| Everything else | **CORRECT** | Field names, types, and defaults match |

### Transport ABC

**CORRECT** — All method signatures match exactly.

### SQLite schema

**CORRECT** — Table definition and indexes match exactly.

### Checkpointer section

| Item | Status | Detail |
|------|--------|--------|
| `AsyncSqliteSaver` reference | **CORRECT** | Used in cli/run.py and cli/start.py |
| Lifecycle description | **CORRECT** | CLI owns checkpointer, tests use MemorySaver |

---

## Section 9: Coding Standards

| Item | Status | Detail |
|------|--------|--------|
| `No print() in application code` | **STALE** | `typer.echo()` and `print()` are used in CLI commands (send, listen, chat) and scripts. Rule should clarify "in library/core code" |
| All other rules | **CORRECT** | Line length, type annotations, pathlib, etc. |

### Semantic Versioning

| Item | Status | Detail |
|------|--------|--------|
| `__version__` loading | **CORRECT** | Matches `src/multiagent/__init__.py` |
| Version utilities | **MISSING** | `src/multiagent/version.py` (SemVer, bump_in_pyproject) exists but is not documented in the guide |

---

## Section 10: Docstring Standard

**CORRECT** — Google style is used throughout the codebase.

Note: ruff does **not** enforce docstrings (D rules not selected in pyproject.toml),
contrary to what Section 4 implies. Docstrings are followed by convention, not tooling.

---

## Section 11: Testing Strategy

### Shared fixtures (conftest.py)

| Item | Status | Detail |
|------|--------|--------|
| `mock_llm_response` fixture | **STALE** | Guide shows a factory pattern returning AsyncMock. Actual: returns a plain string `"Mocked LLM response for testing."` |
| `mock_llm` fixture | **MISSING** | Exists in codebase — mocks `ChatOpenAI.ainvoke` with AIMessage including usage_metadata. Not in guide |
| `sample_message` body | **STALE** | Guide: `"Research the history of the internet."` — Actual: `"What is quantum entanglement?"` |
| `test_settings` fixture | **MISSING** | Exists in codebase, not in guide |
| `sqlite_transport` fixture | **MISSING** | Exists in codebase, not in guide |
| `mock_cost_ledger` fixture | **MISSING** | Exists in codebase, not in guide |

### Unit test pattern

| Item | Status | Detail |
|------|--------|--------|
| `ChatAnthropic` mock target | **STALE** | Guide patches `multiagent.core.agent.ChatAnthropic` — Actual patches `langchain_openai.ChatOpenAI.ainvoke` |
| `LLMAgent` constructor | **STALE** | Guide: `LLMAgent(name="researcher", system_prompt="...")` — Actual: `LLMAgent(name, settings, checkpointer, cost_ledger)`. System prompt loaded from file, not passed directly |
| `agent.run()` signature | **STALE** | Guide: `await agent.run("input")` — Actual: `await agent.run("input", thread_id="...")` (thread_id is required) |

### Integration test pattern

| Item | Status | Detail |
|------|--------|--------|
| `ANTHROPIC_API_KEY` reference | **STALE** | Guide says integration tests require `ANTHROPIC_API_KEY` — Actual uses `OPENROUTER_API_KEY` |
| LLMAgent constructor | **STALE** | Same issue as unit test pattern — constructor signature changed |

---

## Section 12: Git Workflow

| Item | Status | Detail |
|------|--------|--------|
| `--ff-only` merge rule | **STALE** | Guide says `--ff-only` is mandatory — Actual practice uses `--no-ff` merge commits (e.g. commit d3d76a7) |
| Worktree naming | **STALE** | Guide: `../multiagent-<slug>` — Actual practice: `../pretty-dancer-<slug>` (repo name changed) |
| Everything else | **CORRECT** | Branch naming, conventional commits, worktree workflow |

---

## Section 13: Task Runner (justfile)

| Item | Status | Detail |
|------|--------|--------|
| `lint` target | **STALE** | Guide: `ruff check --fix` + `ruff format` — Actual: `ruff check` only (no --fix, no format) |
| `check` target | **STALE** | Guide: includes `ruff format --check` — Actual: `lint typecheck` (just ruff check + pyright) |
| `test-coverage` | **STALE** | Guide: `--cov-report=html` — Actual: `--cov-report=term-missing --cov-fail-under=80` (no html) |
| `test-all` | **STALE** | Guide: `pytest tests -m "" -v` — Actual: `pytest tests/ -v` (no marker override) |
| `setup` | **STALE** | Guide includes echo message mentioning ANTHROPIC_API_KEY — Actual has no echo |
| `start`, `stop` targets | **MISSING** | Exist in actual justfile, not in guide |
| `listen`, `chat` targets | **MISSING** | Exist in actual justfile, not in guide |
| `threads` target | **MISSING** | `uv run python scripts/browse_threads.py` — not in guide |
| `version`, `bump-*`, `release` targets | **MISSING** | Exist in actual justfile, not in guide |
| `costs`, `costs-by-agent`, `costs-by-model` targets | **MISSING** | Exist in actual justfile, not in guide |
| `adr-list` target | **WRONG** | In guide but not in actual justfile |
| `update` target | **WRONG** | In guide but not in actual justfile |
| `clean` target differences | **STALE** | Guide: `rm -rf .venv .ruff_cache .pytest_cache htmlcov .coverage` — Actual: `find __pycache__ + rm -rf .coverage htmlcov/ .pytest_cache/ .ruff_cache/` (no .venv removal) |

---

## Section 14: Documentation Standards

| Item | Status | Detail |
|------|--------|--------|
| `docs/architecture.md` | **WRONG** | Documented as required — does not exist |
| `docs/getting-started.md` | **WRONG** | Documented as required — does not exist |
| `docs/transport-guide.md` | **WRONG** | Documented as required — does not exist |
| ADR files | **WRONG** | Guide lists 5 ADRs (0001–0005) — only `docs/adr/README.md` exists |
| `tasks/` naming | **STALE** | Guide lists 001–005 — actual tasks go through 011b, plus CR files and plans/ subdirectory |

---

## Section 15: Cross-Platform Rules

**CORRECT** — pathlib usage, Windows asyncio policy, WAL mode all followed.

One nit: guide says "`SQLITE_WAL_MODE=true` is the default in `.env.defaults`" —
this setting doesn't exist. WAL is hardcoded in SQLiteTransport.

---

## Section 16: Dependency Reference

| Item | Status | Detail |
|------|--------|--------|
| `langchain-openai` | **STALE** | Guide says `langchain-anthropic` with `ChatAnthropic` import — Actual: `langchain-openai` with `ChatOpenAI` |
| `rich` | **STALE** | Guide says "scripts/ only — never imported in src/" — Actual: `rich` is imported in `src/multiagent/cli/listen.py` and `src/multiagent/cli/chat.py` |
| `langgraph-checkpoint-sqlite` | **MISSING** | Runtime dependency, not listed in guide |

---

## Summary Statistics

| Status | Count |
|--------|-------|
| CORRECT | ~15 sections/subsections |
| STALE | ~40 items (was correct, now outdated) |
| MISSING | ~25 items (exists in codebase, not documented) |
| WRONG | ~15 items (never matched the codebase) |

### Top-Priority Updates

1. **LLM provider**: `langchain-anthropic` → `langchain-openai` / `ChatAnthropic` → `ChatOpenAI` (pervasive)
2. **Settings fields**: Remove 6 nonexistent fields, add 5 missing fields, fix `get_settings` → `load_settings`
3. **Repository structure tree**: Remove routing/, state.py; add costs.py, shutdown.py, version.py, 5 CLI commands
4. **Documentation files**: Remove references to architecture.md, getting-started.md, transport-guide.md, ADRs (or create them)
5. **Agent constructor**: `LLMAgent(name, system_prompt)` → `LLMAgent(name, settings, checkpointer, cost_ledger)`
6. **Justfile**: Extensive drift — many targets added/removed/changed

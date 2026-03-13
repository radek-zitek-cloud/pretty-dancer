# Task 001 — Project Skeleton

**File:** `tasks/001-skeleton.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-13  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)

---

## Objective

Establish the complete project skeleton. The result is a runnable application that
demonstrates the full toolchain is correctly wired: packaging, configuration, logging,
versioning, and CLI entry point. No agent logic. No transport. No LLM calls.

When complete, `uv run multiagent` must start, log its lifecycle, print its configured
values, and exit cleanly. This validates the entire infrastructure before any domain
code is written.

---

## Authoritative References

Read these documents in full before producing your implementation plan:

- `docs/implementation-guide.md` — all technology choices, structure, and coding rules

---

## Deliverables

### 1. Repository Initialization

Create the following at the repository root. Every file listed must exist.

```
.python-version          # content: 3.12
.gitignore               # see implementation guide — data/, logs/, .env rules
.gitattributes           # LF line endings for all text files
.env.defaults            # committed — all keys documented, safe defaults
.env                     # gitignored — developer local, contains secrets
.env.test                # committed — test overrides
pyproject.toml           # complete config per implementation guide section 4
justfile                 # all tasks per implementation guide section 13
.pre-commit-config.yaml  # ruff hooks
README.md                # minimum content per implementation guide section 14
```

### 2. Package Skeleton

Create the following source files. Every file must be a valid Python module with
a module-level docstring. No placeholder `pass` in `__init__.py` files — they must
have docstrings and, where specified, real content.

```
src/multiagent/__init__.py          # __version__ via importlib.metadata
src/multiagent/exceptions.py        # complete hierarchy from implementation guide
src/multiagent/constants.py         # APP_NAME = "multiagent" only at this stage
src/multiagent/config/__init__.py   # exports: Settings, get_settings
src/multiagent/config/settings.py   # pydantic-settings Settings class
src/multiagent/logging/__init__.py  # exports: configure_logging, get_logger
src/multiagent/logging/setup.py     # structlog configuration
src/multiagent/cli/__init__.py      # module docstring only
src/multiagent/cli/main.py          # entry point — see Behaviour section below
```

### 3. Test Skeleton

```
tests/__init__.py
tests/conftest.py                   # test_settings fixture (no real API key)
tests/unit/__init__.py
tests/unit/config/__init__.py
tests/unit/config/test_settings.py  # see Test Requirements section below
```

### 4. Runtime Directories

```
data/.gitkeep
logs/.gitkeep
docs/implementation-guide.md        # copy of the provided implementation guide
docs/adr/README.md                  # ADR index with template
```

---

## Configuration Keys

### `.env.defaults` must define these keys

```bash
# Application identity
APP_NAME=multiagent
APP_ENV=development

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=console

# Hello World test values
# GREETING_SECRET has no default — must be supplied in .env, never committed
GREETING_MESSAGE=Hello from multiagent default config
```

### `.env` (gitignored) must contain

```bash
# Developer local overrides
GREETING_SECRET=my-local-secret-value
LOG_LEVEL=DEBUG
```

### `.env.test` must contain

```bash
LOG_LEVEL=WARNING
LOG_FORMAT=console
GREETING_MESSAGE=Hello from test config
GREETING_SECRET=test-secret-not-real
```

### `Settings` class must model

```python
class Settings(BaseSettings):
    # Application identity — sourced from pyproject.toml at runtime, not .env
    app_name: str = Field("multiagent")
    app_env: str = Field("development", pattern="^(development|test|production)$")

    # Logging
    log_level: str = Field("INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    log_format: str = Field("console", pattern="^(console|json)$")

    # Hello World test configuration
    greeting_message: str = Field(
        "Hello from multiagent",
        description="Demonstrates a configurable value with a default.",
    )
    greeting_secret: str = Field(
        ...,
        description="Demonstrates a required secret with no default. Must be in .env.",
    )
```

`extra="forbid"` must be set — unknown env vars must cause a startup failure.

---

## Behaviour of `multiagent` Entry Point

When `uv run multiagent` is executed, the program must perform these steps
**in this exact order**:

1. **Load configuration** — call `load_settings()`, which raises
   `InvalidConfigurationError` if any required field is absent or invalid.

2. **Configure logging** — call `configure_logging(settings)`.
   Logging must not be used before this call.

3. **Log startup** — emit an `INFO` log event with these fields:
   ```
   event="startup"
   app=<APP_NAME from constants>
   version=<__version__>
   env=<settings.app_env>
   ```

4. **Print identity line** — write to stdout:
   ```
   multiagent v0.1.0
   ```
   (use `APP_NAME` constant and `__version__`, never hardcode strings)

5. **Print and log configuration values:**
   - Print `greeting_message` value to stdout with label
   - Print `greeting_secret` value to stdout with label
     (this is a PoC — in real usage secrets would never be printed)
   - Log both values at `INFO` level with structured keys

6. **Log shutdown** — emit an `INFO` log event:
   ```
   event="shutdown"
   reason="completed"
   ```

7. **Exit with code 0.**

### Error Handling at Entry Point

The entry point is the **only** place where bare `Exception` may be caught.
All other exceptions must be specific. The pattern:

```python
def main() -> None:
    try:
        asyncio.run(_async_main())
    except InvalidConfigurationError as exc:
        # Configuration errors: print clean message, no traceback
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)
    except MultiAgentError as exc:
        # Domain errors: log if logging is up, otherwise print
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001  # intentional broad catch at boundary
        print(f"Unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)
```

### Windows `asyncio` Requirement

Before `asyncio.run()`, apply the Windows event loop policy:

```python
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

---

## Test Requirements

### `tests/unit/config/test_settings.py`

Write these tests using TDD. Tests must exist before the implementation is complete.

```
TestSettingsDefaults
  - test_default_log_level_is_info
  - test_default_log_format_is_console
  - test_default_greeting_message_is_set

TestSettingsValidation
  - test_invalid_log_level_raises_validation_error
  - test_invalid_log_format_raises_validation_error
  - test_invalid_app_env_raises_validation_error
  - test_extra_env_var_raises_validation_error

TestSettingsRequired
  - test_missing_greeting_secret_raises_error
```

All tests use the `test_settings` fixture from `conftest.py`. No real `.env` is
read during unit tests — all values are supplied directly to `Settings(...)`.

---

## `justfile` — Required Tasks

```makefile
# Default — list all tasks
default:
    @just --list

# Setup
setup:
    uv sync --all-extras
    uv run pre-commit install

# Quality
lint:
    uv run ruff check src/ tests/

format:
    uv run ruff format src/ tests/
    uv run ruff check --fix src/ tests/

typecheck:
    uv run pyright src/ tests/

check: lint typecheck

# Testing
test:
    uv run pytest tests/unit/ -v

test-coverage:
    uv run pytest tests/unit/ --cov=src/multiagent --cov-report=term-missing --cov-fail-under=80

test-integration:
    uv run pytest tests/integration/ -v -m integration

test-all:
    uv run pytest tests/ -v

# Running
run:
    uv run multiagent

# Maintenance
clean:
    find . -type d -name __pycache__ -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
    rm -rf .coverage htmlcov/ .pytest_cache/ .ruff_cache/
```

---

## Implementation Order

Implement files in this order. Each step must pass `just check` before proceeding
to the next. Do not skip steps.

1. `pyproject.toml` + `uv.lock` (via `uv sync`)
2. `.python-version`, `.gitignore`, `.gitattributes`
3. `src/multiagent/exceptions.py`
4. `src/multiagent/constants.py`
5. `src/multiagent/__init__.py`
6. `src/multiagent/config/settings.py` + `src/multiagent/config/__init__.py`
7. `.env.defaults`, `.env`, `.env.test`
8. **Write tests first:** `tests/unit/config/test_settings.py`
9. Verify tests fail appropriately (TDD red phase)
10. Implement `Settings` to make tests pass (TDD green phase)
11. `src/multiagent/logging/setup.py` + `src/multiagent/logging/__init__.py`
12. `src/multiagent/cli/main.py`
13. `justfile`, `.pre-commit-config.yaml`
14. `README.md`, `docs/adr/README.md`
15. Runtime directories: `data/.gitkeep`, `logs/.gitkeep`
16. Final: `just check && just test && just run`

---

## Acceptance Criteria

The task is complete when **all** of the following pass without error:

```bash
just check          # ruff + pyright — zero errors, zero warnings
just test           # all unit tests pass
just run            # prints identity, config values, exits 0
```

And the output of `just run` (with `.env` supplying `GREETING_SECRET`) looks like:

```
multiagent v0.1.0
Greeting message : Hello from multiagent default config
Greeting secret  : my-local-secret-value

2026-03-13T10:00:00Z [info     ] startup    app=multiagent version=0.1.0 env=development
2026-03-13T10:00:00Z [info     ] config_value  key=greeting_message value=Hello from multiagent default config
2026-03-13T10:00:00Z [info     ] config_value  key=greeting_secret  value=my-local-secret-value
2026-03-13T10:00:00Z [info     ] shutdown   reason=completed
```

Note: stdout print lines appear before log lines because logging is configured after
the initial print — this is intentional and acceptable for the skeleton only.

---

## What This Task Does NOT Include

Do not implement any of the following. They are out of scope for this task:

- `LLMAgent`, `AgentRunner`, or any LangGraph code
- `Transport` ABC or any transport adapters
- `routing/` module
- `cli/run.py` or `cli/send.py` (the full CLI)
- Integration tests
- Any database interaction

---

## Git

Work on branch `feature/skeleton`. Commit at each meaningful step using
Conventional Commits format. The final commit message must be:

```
feat(cli): implement project skeleton with config, logging, and entry point
```

Tag the final commit:

```bash
git tag -a v0.1.0 -m "Release 0.1.0 — project skeleton"
```
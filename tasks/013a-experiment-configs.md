# Task 013a — Named Experiment Configurations

**File:** `tasks/013a-experiment-configs.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-14  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 013 (MCP tool integration) complete and merged to master

---

## Objective

Allow `just start research-desk` to load a completely isolated configuration
set for the `research-desk` experiment — its own `agents.toml`, MCP server
definitions, and prompts — without touching the default cluster configuration.

After this task:
- `just start research-desk` loads `agents.research-desk.toml`,
  `agents.mcp.research-desk.json`, and `prompts/research-desk/*.md`
- `just start` with no experiment loads the current default files unchanged
- Missing experiment config files are hard errors — no silent fallback to
  defaults
- MCP secrets fall back to `agents.mcp.secrets.json` if no experiment-specific
  secrets file exists
- Experiment names are validated as `[a-z0-9-]+` at CLI startup

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — all standards, module rules, coding
  conventions
- `tasks/013-mcp-tools.md` — MCP config loading this task extends
- `tasks/004-cli-wiring.md` — settings and config loading patterns

---

## Git

Work on branch `feature/experiment-configs` created from `master`.

```bash
git checkout master
git pull origin master
git checkout -b feature/experiment-configs
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
feat(config): add named experiment configuration loading
```

---

## Experiment Name Validation

Experiment names must match `^[a-z0-9-]+$`. Validated at CLI startup in
`run.py`, `start.py`, and `chat.py` — anywhere `--experiment` is accepted.

If validation fails:

```
ConfigurationError: Invalid experiment name 'My Experiment/v2'.
Experiment names must contain only lowercase letters, digits, and hyphens.
```

Empty string is valid — it means no experiment, load defaults.

---

## File Resolution Rules

### When `experiment` is empty (default)

| Resource | Path |
|---|---|
| Agent config | `agents.toml` |
| MCP server config | `agents.mcp.json` |
| MCP secrets | `agents.mcp.secrets.json` (optional, silent if absent) |
| Prompt for agent `X` | `prompts/{X}.md` |

### When `experiment = "research-desk"`

| Resource | Path | Missing behaviour |
|---|---|---|
| Agent config | `agents.research-desk.toml` | **Hard stop** — `ConfigurationError` |
| MCP server config | `agents.mcp.research-desk.json` | **Hard stop** — `ConfigurationError` |
| MCP secrets | `agents.mcp.secrets.research-desk.json` | **Fall back** to `agents.mcp.secrets.json`, then silent |
| Prompt for agent `X` | `prompts/research-desk/{X}.md` | **Hard stop** — `ConfigurationError` |

The secrets fallback chain:
1. `agents.mcp.secrets.{experiment}.json` — experiment-specific credentials
2. `agents.mcp.secrets.json` — default credentials
3. No file — no env overrides applied (silent, same as today)

API keys do not change between experiments. A single `agents.mcp.secrets.json`
covers all experiments unless an experiment explicitly needs different
credentials.

---

## Settings Changes

No new settings fields. The existing `experiment: str = ""` field drives all
resolution logic. The resolution is computed at load time in the config
loaders, not stored in settings.

---

## `src/multiagent/config/agents.py` — Changes

### `load_agents_config(path, experiment)` — signature change

```python
def load_agents_config(
    path: Path,
    experiment: str = "",
) -> AgentsConfig:
```

When `experiment` is non-empty, resolve the actual path before loading:

```python
def _resolve_agents_config_path(base_path: Path, experiment: str) -> Path:
    """Resolve agents config path for the given experiment.

    Args:
        base_path: Default agents config path (agents.toml)
        experiment: Experiment name, empty string for default

    Returns:
        Resolved path to the experiment-specific config file

    Raises:
        ConfigurationError: If experiment config file does not exist
    """
    if not experiment:
        return base_path
    resolved = base_path.parent / f"{base_path.stem}.{experiment}{base_path.suffix}"
    if not resolved.exists():
        raise ConfigurationError(
            f"Experiment config not found: {resolved}. "
            f"Create this file to run the '{experiment}' experiment."
        )
    return resolved
```

`load_agents_config` calls `_resolve_agents_config_path` before reading the
TOML file.

---

## `src/multiagent/config/mcp.py` — Changes

### `load_mcp_config(config_path, secrets_path, experiment)` — signature change

```python
def load_mcp_config(
    config_path: Path,
    secrets_path: Path,
    experiment: str = "",
) -> MCPConfig:
```

**MCP server config resolution:**

```python
def _resolve_mcp_config_path(base_path: Path, experiment: str) -> Path:
    if not experiment:
        return base_path
    resolved = base_path.parent / f"{base_path.stem}.{experiment}{base_path.suffix}"
    if not resolved.exists():
        raise ConfigurationError(
            f"Experiment MCP config not found: {resolved}. "
            f"Create this file to run the '{experiment}' experiment."
        )
    return resolved
```

**MCP secrets resolution (with fallback):**

```python
def _resolve_mcp_secrets_path(base_path: Path, experiment: str) -> Path | None:
    if not experiment:
        return base_path if base_path.exists() else None
    experiment_secrets = (
        base_path.parent / f"{base_path.stem}.{experiment}{base_path.suffix}"
    )
    if experiment_secrets.exists():
        return experiment_secrets
    if base_path.exists():
        return base_path
    return None
```

Returns `None` if no secrets file found at either path — caller handles
`None` by applying no env overrides (existing behaviour).

---

## Prompt Loading — `src/multiagent/core/agent.py`

Currently the agent loads its system prompt from:

```python
prompt_path = settings.prompts_dir / f"{self._name}.md"
```

With experiment support:

```python
def _resolve_prompt_path(
    prompts_dir: Path,
    agent_name: str,
    experiment: str,
) -> Path:
    """Resolve system prompt path for the given agent and experiment.

    Args:
        prompts_dir: Base prompts directory
        agent_name: Agent name, used as filename stem
        experiment: Experiment name, empty string for default

    Returns:
        Resolved path to the prompt file

    Raises:
        ConfigurationError: If prompt file does not exist
    """
    if experiment:
        path = prompts_dir / experiment / f"{agent_name}.md"
    else:
        path = prompts_dir / f"{agent_name}.md"

    if not path.exists():
        raise ConfigurationError(
            f"Prompt file not found: {path}. "
            f"Create this file to define the '{agent_name}' agent "
            f"for experiment '{experiment}'."
            if experiment else
            f"Create this file to define the '{agent_name}' agent."
        )
    return path
```

`LLMAgent.__init__` calls `_resolve_prompt_path(settings.prompts_dir,
self._name, settings.experiment)`.

**Module boundary:** `_resolve_prompt_path` lives in `core/agent.py`. It
receives `Path` and `str` values — no import from `config/`.

---

## CLI Changes — `run.py`, `start.py`, `chat.py`

### Experiment name validation

Add a validation helper in each CLI module (or extract to a shared CLI
utility):

```python
import re

def _validate_experiment_name(experiment: str) -> None:
    if experiment and not re.match(r'^[a-z0-9-]+$', experiment):
        raise typer.BadParameter(
            f"Invalid experiment name '{experiment}'. "
            "Experiment names must contain only lowercase letters, "
            "digits, and hyphens."
        )
```

Call before loading any config.

### Config loading — pass experiment through

```python
_validate_experiment_name(experiment)

agents_config = load_agents_config(
    settings.agents_config_path,
    experiment=experiment,
)

mcp_config = load_mcp_config(
    settings.mcp_config_path,
    settings.mcp_secrets_path,
    experiment=experiment,
)
```

---

## `.gitignore` — Update

Replace individual secrets entries with a pattern:

```
# MCP secrets (all experiments)
agents.mcp.secrets*.json
```

Remove any individually listed secrets files.

---

## Example Directory Structure After This Task

```
multiagent/
├── agents.toml                              # default cluster
├── agents.mcp.json                          # default MCP servers
├── agents.mcp.secrets.json                  # all API keys (gitignored)
├── agents.mcp.secrets.example.json          # key template (committed)
│
├── agents.research-desk.toml               # research desk cluster
├── agents.mcp.research-desk.json           # research desk MCP servers
│                                           # (no secrets file needed —
│                                           #  falls back to default)
│
├── agents.editorial.toml                   # editorial cluster
├── agents.mcp.editorial.json               # editorial MCP servers
│
├── prompts/
│   ├── alfa.md                             # default agents
│   ├── beta.md
│   ├── research-desk/
│   │   ├── supervisor.md
│   │   ├── fundamentals.md
│   │   ├── risk.md
│   │   └── synthesis.md
│   └── editorial/
│       ├── editor.md
│       ├── writer.md
│       └── linguist.md
```

---

## Test Requirements

### `tests/unit/config/test_agents.py` — Additions

```
TestExperimentConfigResolution
    test_resolves_experiment_config_path_correctly
        — experiment="research-desk", file exists at expected path
        — assert correct path returned

    test_raises_when_experiment_config_missing
        — experiment="research-desk", no file at expected path
        — assert ConfigurationError with descriptive message

    test_returns_default_path_when_no_experiment
        — experiment=""
        — assert base agents.toml path returned
```

### `tests/unit/config/test_mcp.py` — Additions

```
TestExperimentMCPResolution
    test_resolves_experiment_mcp_config_path_correctly
        — experiment="research-desk", file exists
        — assert experiment-specific config loaded

    test_raises_when_experiment_mcp_config_missing
        — experiment="research-desk", no file
        — assert ConfigurationError

    test_secrets_falls_back_to_default_when_experiment_secrets_absent
        — experiment="research-desk"
        — agents.mcp.secrets.research-desk.json absent
        — agents.mcp.secrets.json present
        — assert default secrets loaded

    test_secrets_uses_experiment_file_when_present
        — both files present
        — assert experiment-specific secrets take precedence

    test_secrets_silent_when_neither_file_present
        — neither file present
        — assert no error, empty env applied
```

### `tests/unit/cli/test_run.py` and `test_start.py` — Additions

```
test_raises_on_invalid_experiment_name
    — experiment="My Experiment/v2"
    — assert typer.BadParameter raised before any config loading
```

### `tests/unit/core/test_agent.py` — Additions

```
test_resolves_experiment_prompt_path
    — experiment="research-desk", prompts/research-desk/supervisor.md exists
    — assert correct prompt loaded

test_raises_when_experiment_prompt_missing
    — experiment="research-desk", no prompt file
    — assert ConfigurationError with descriptive message

test_resolves_default_prompt_when_no_experiment
    — experiment=""
    — assert prompts/supervisor.md loaded
```

---

## Implementation Order

1. Add experiment name validation helper — shared utility or per-CLI-module
2. Add `_resolve_agents_config_path` to `config/agents.py`
3. Update `load_agents_config` signature and implementation
4. Add `_resolve_mcp_config_path` and `_resolve_mcp_secrets_path` to
   `config/mcp.py`
5. Update `load_mcp_config` signature and implementation
6. Add `_resolve_prompt_path` to `core/agent.py`
7. Update `LLMAgent.__init__` to call `_resolve_prompt_path`
8. Update `cli/run.py`, `cli/start.py`, `cli/chat.py` — validation +
   pass experiment to config loaders
9. Update `.gitignore` — pattern rule for secrets
10. Write all tests — TDD red phase
11. Green phase
12. Create experiment directory structure for research-desk and editorial
    (move existing prompts into subdirectories)
13. `just check && just test`
14. Manual smoke test (below)

---

## Manual Smoke Test

```bash
# Verify default cluster still works
just start
just send alfa "hello"
# Ctrl-C

# Verify experiment cluster loads correctly
just start research-desk
just send supervisor "Research Microsoft as investment opportunity"
# Verify research-desk agents run, not default agents
# Ctrl-C

# Verify hard stop on missing config
just start nonexistent
# Expect: ConfigurationError: Experiment config not found: agents.nonexistent.toml

# Verify hard stop on invalid name
just start "My Experiment"
# Expect: Invalid experiment name 'My Experiment'

# Verify secrets fallback
# (delete agents.mcp.secrets.research-desk.json if it exists)
# just start research-desk should still work using agents.mcp.secrets.json
```

---

## Acceptance Criteria

```bash
just check    # zero ruff errors, zero pyright errors
just test     # all tests pass (previous total + new tests)
```

Manual:
- `just start research-desk` loads research-desk config, not defaults
- `just start` with no experiment loads default config unchanged
- Missing experiment file produces `ConfigurationError` with clear message
- Invalid experiment name produces `typer.BadParameter` before config load
- Secrets fallback works — single `agents.mcp.secrets.json` covers all
  experiments
- Existing research-desk prompts work from `prompts/research-desk/` subfolder

---

## What This Task Does NOT Include

- Experiment listing command (`just experiments`) — useful later
- Experiment metadata file (description, author, date) — future addition
- Nested experiments or experiment inheritance
- Per-experiment settings overrides beyond config files
- Migration tooling for existing flat prompt files — Tom moves them manually
  as part of step 12
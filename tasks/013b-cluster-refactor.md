# Task 013b — Cluster Configuration Refactor

**File:** `tasks/013b-cluster-refactor.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-14  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 013a (named experiment configurations) complete and merged to master

---

## Objective

Replace the concept of "experiment" with "cluster" throughout the entire
platform. Consolidate all cluster-specific configuration — agent wiring, MCP
servers, secrets, and prompts — into a `clusters/` directory at the repo root.
Move the default configuration into `clusters/default/`.

This is a rename and reorganisation task. No new behaviour is introduced.
Every place the word "experiment" appears in code, configuration, logs, or
documentation is replaced by "cluster".

After this task:
- `just start research-desk` loads everything from `clusters/research-desk/`
- `just start` loads everything from `clusters/default/`
- Log files use the cluster name: `logs/{timestamp}_{agent}_{cluster}.log`
- Cost ledger uses `cluster` column instead of `experiment`
- `just monitor research-desk` filters by cluster name
- `clusters/` contains every cluster as a self-contained subdirectory

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — all standards, module rules, coding
  conventions
- `tasks/013a-experiment-configs.md` — the config loading this task refactors
- `tasks/009-cost-tracking.md` — cost ledger schema this task migrates

---

## Git

Work on branch `feature/cluster-refactor` created from `master`.

```bash
git checkout master
git pull origin master
git checkout -b feature/cluster-refactor
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
feat(config): replace experiment with cluster, consolidate into clusters/ dir
```

---

## New Directory Structure

```
clusters/
├── default/
│   ├── agents.toml                      # moved from agents.toml at root
│   ├── agents.mcp.json                  # moved from agents.mcp.json at root
│   ├── agents.mcp.secrets.json          # gitignored
│   ├── agents.mcp.secrets.example.json  # committed, documents required keys
│   └── prompts/
│       ├── alfa.md                      # moved from prompts/alfa.md
│       └── beta.md                      # moved from prompts/beta.md
├── research-desk/
│   ├── agents.toml
│   ├── agents.mcp.json
│   ├── agents.mcp.secrets.json          # gitignored
│   ├── agents.mcp.secrets.example.json
│   └── prompts/
│       ├── supervisor.md
│       ├── fundamentals.md
│       ├── risk.md
│       └── synthesis.md
├── editorial/
│   ├── agents.toml
│   ├── agents.mcp.json
│   └── prompts/
│       ├── editor.md
│       ├── writer.md
│       └── linguist.md
└── platform-architect/
    ├── agents.toml
    ├── agents.mcp.json
    └── prompts/
        └── architect.md
```

Router prompts live inside the cluster's `prompts/` directory:

```
clusters/research-desk/prompts/routers/research_supervisor.md
```

---

## Files Removed from Root

After migration, these files are deleted from the repo root:

```
agents.toml                          → clusters/default/agents.toml
agents.mcp.json                      → clusters/default/agents.mcp.json
agents.mcp.secrets.example.json      → clusters/default/agents.mcp.secrets.example.json
agents.{name}.toml                   → clusters/{name}/agents.toml
agents.mcp.{name}.json               → clusters/{name}/agents.mcp.json
agents.mcp.secrets.{name}.json       → clusters/{name}/agents.mcp.secrets.json
```

And from `prompts/`:

```
prompts/alfa.md                      → clusters/default/prompts/alfa.md
prompts/beta.md                      → clusters/default/prompts/beta.md
prompts/research-desk/               → clusters/research-desk/prompts/
prompts/editorial/                   → clusters/editorial/prompts/
prompts/platform-architect/          → clusters/platform-architect/prompts/
```

If `prompts/` becomes empty after migration, remove it.
If router prompts exist at `prompts/routers/`, move them into the appropriate
cluster's `prompts/routers/` subdirectory.

---

## Settings Changes

### Rename `experiment` → `cluster`

```python
# Before
experiment: str = Field("", description="...")

# After
cluster: str = Field("", description="Cluster name. Loads configuration from clusters/{cluster}/. Empty string loads clusters/default/.")
```

### Add `clusters_dir`

```python
clusters_dir: Path = Field(
    Path("clusters"),
    description="Root directory containing cluster configurations.",
)
```

### Remove old path fields

```python
# Remove — paths are now derived from clusters_dir / cluster
agents_config_path: Path   # replaced by derived path
mcp_config_path: Path      # replaced by derived path
mcp_secrets_path: Path     # replaced by derived path
prompts_dir: Path          # replaced by derived path
```

All four path fields are replaced by a single derivation function.

### Path derivation

```python
def cluster_dir(settings: Settings) -> Path:
    """Return the directory for the current cluster."""
    name = settings.cluster if settings.cluster else "default"
    return settings.clusters_dir / name

def agents_config_path(settings: Settings) -> Path:
    return cluster_dir(settings) / "agents.toml"

def mcp_config_path(settings: Settings) -> Path:
    return cluster_dir(settings) / "agents.mcp.json"

def mcp_secrets_path(settings: Settings) -> Path:
    return cluster_dir(settings) / "agents.mcp.secrets.json"

def prompts_dir(settings: Settings) -> Path:
    return cluster_dir(settings) / "prompts"
```

These are module-level functions in `config/settings.py`, not methods on
`Settings`. They receive a `Settings` instance and return a `Path`.

**Why functions not fields:** The derived paths depend on `cluster` which can
be set at runtime. Making them computed functions avoids stale cached values
and removes four settings fields that users should never need to override.

---

## CLI Changes

### `--cluster` replaces `--experiment`

In `run.py`, `start.py`, `chat.py`, `listen.py`, `monitor.py`:

```python
# Before
experiment: str = typer.Option("", "--experiment", "-e", ...)

# After
cluster: str = typer.Option("", "--cluster", "-c", ...)
```

Validation regex unchanged: `^[a-z0-9-]+$` or empty string.

### `settings.cluster` assignment

In every CLI entry point, after loading settings:

```python
if cluster:
    settings.cluster = cluster
```

### justfile targets

```makefile
# Before
start experiment="":
    uv run multiagent start {{...experiment...}}

# After
start cluster="":
    uv run multiagent start {{if cluster != "" { "--cluster " + cluster } else { "" }}}
```

Update all targets that currently accept an `experiment` argument:
`start`, `run`, `chat`, `monitor`.

---

## Config Loader Changes

### `load_agents_config`

Signature simplification — no longer needs `experiment` parameter since the
path is fully derived from settings:

```python
def load_agents_config(path: Path) -> AgentsConfig:
```

Callers pass `agents_config_path(settings)` as the path. The cluster
resolution and hard-stop error handling move into `agents_config_path()`.

```python
def agents_config_path(settings: Settings) -> Path:
    name = settings.cluster if settings.cluster else "default"
    path = settings.clusters_dir / name / "agents.toml"
    if not path.exists():
        raise ConfigurationError(
            f"Cluster config not found: {path}. "
            f"Create clusters/{name}/agents.toml to define this cluster."
        )
    return path
```

### `load_mcp_config`

Same pattern — path derivation handles cluster resolution:

```python
def load_mcp_config(config_path: Path, secrets_path: Path) -> MCPConfig:
```

The secrets fallback logic moves into `mcp_secrets_path()`:

```python
def mcp_secrets_path(settings: Settings) -> Path | None:
    """Return secrets path, falling back to default cluster secrets."""
    name = settings.cluster if settings.cluster else "default"
    cluster_secrets = settings.clusters_dir / name / "agents.mcp.secrets.json"
    if cluster_secrets.exists():
        return cluster_secrets
    default_secrets = settings.clusters_dir / "default" / "agents.mcp.secrets.json"
    if default_secrets.exists():
        return default_secrets
    return None
```

Returns `None` if no secrets file found anywhere — caller handles gracefully.

### `_resolve_prompt_path` in `core/agent.py`

```python
# Before
def _resolve_prompt_path(prompts_dir, agent_name, experiment) -> Path:

# After
def _resolve_prompt_path(prompts_dir: Path, agent_name: str) -> Path:
```

`experiment` parameter removed — the caller passes `prompts_dir(settings)`
which already encodes the cluster. The function only needs to resolve the
agent name within the given directory.

---

## Cost Ledger Schema Migration

### Schema change

```sql
ALTER TABLE cost_ledger RENAME COLUMN experiment TO cluster;
```

### Migration in `CostLedger._init_schema()`

```python
# Check for old column name and rename if present
columns = await conn.execute("PRAGMA table_info(cost_ledger)")
col_names = [row[1] for row in await columns.fetchall()]
if "experiment" in col_names and "cluster" not in col_names:
    await conn.execute(
        "ALTER TABLE cost_ledger RENAME COLUMN experiment TO cluster"
    )
```

This migration runs on every startup — idempotent, safe to run against both
old and new schema.

### `CostEntry` dataclass

```python
# Before
experiment: str = ""

# After
cluster: str = ""
```

### Cost ledger writes

```python
# Before
experiment=self._settings.experiment

# After
cluster=self._settings.cluster
```

---

## Observability Changes

### Log filenames

```python
# Before
configure_logging(settings, agent_name="cluster", experiment=experiment)
# produces: logs/{timestamp}_{agent}_{experiment}.log

# After
configure_logging(settings, agent_name="cluster", cluster=cluster)
# produces: logs/{timestamp}_{agent}_{cluster}.log
```

Update `configure_logging()` signature in `logging/setup.py`:
`experiment` parameter → `cluster`.

### `show_costs.py`

All SQL queries using `experiment` column use `cluster`:

```sql
-- Before
SELECT experiment, SUM(cost_usd) ... GROUP BY experiment

-- After
SELECT cluster, SUM(cost_usd) ... GROUP BY cluster
```

Update display headers: "Experiment" → "Cluster".

### `browse_threads.py`, `show_thread.py`, `compare_runs.py`

Any reference to `experiment` in queries or display headers → `cluster`.

---

## `ingest_docs.py` Changes

Add `clusters/` to `SOURCE_DIRS`:

```python
SOURCE_DIRS = [
    Path("docs"),
    Path("tasks"),
    Path("clusters"),      # add — ingests all cluster prompts and configs
]
```

Exclude secrets files from ingestion:

```python
EXCLUDED_FILENAMES = {"agents.mcp.secrets.json"}

# In collect_files():
for path in candidate_files:
    if path.name not in EXCLUDED_FILENAMES:
        files.append(path)
```

---

## `.gitignore` Changes

```
# Before
agents.mcp.secrets*.json

# After — more precise, covers all cluster secrets
clusters/*/agents.mcp.secrets.json
```

---

## `.env.defaults` Changes

```bash
# Remove
AGENTS_CONFIG_PATH=agents.toml
MCP_CONFIG_PATH=agents.mcp.json
MCP_SECRETS_PATH=agents.mcp.secrets.json
PROMPTS_DIR=prompts/
EXPERIMENT=

# Add
CLUSTERS_DIR=clusters
CLUSTER=
```

---

## `test_settings` Fixture

Update `tests/conftest.py`:

```python
# Remove old path fields
# Add:
clusters_dir=tmp_path / "clusters",
cluster="",
```

Test fixtures must create `tmp_path / "clusters" / "default" /` with a
minimal `agents.toml`, `agents.mcp.json`, and `prompts/` structure.

---

## Test Updates

### All existing tests that reference `experiment`

Search for `experiment` across all test files:

```bash
grep -r "experiment" tests/
```

Replace every occurrence with `cluster`. This includes:
- Fixture definitions
- Mock settings construction
- Assertions on log filenames
- Assertions on cost ledger rows

### New tests

```
TestClusterPathDerivation
    test_default_cluster_loads_from_clusters_default
        — settings.cluster = ""
        — assert agents_config_path returns clusters/default/agents.toml

    test_named_cluster_loads_from_clusters_subdir
        — settings.cluster = "research-desk"
        — assert agents_config_path returns clusters/research-desk/agents.toml

    test_raises_when_cluster_dir_missing
        — settings.cluster = "nonexistent"
        — assert ConfigurationError with message naming the missing path

    test_secrets_falls_back_to_default_cluster
        — named cluster has no secrets file
        — default cluster has secrets file
        — assert default secrets loaded

TestCostLedgerMigration
    test_migrates_experiment_column_to_cluster
        — create cost_ledger with old schema (experiment column)
        — open CostLedger
        — assert cluster column exists, experiment column absent
        — assert existing rows preserved

    test_schema_already_migrated_is_idempotent
        — create cost_ledger with new schema (cluster column)
        — open CostLedger twice
        — assert no error
```

---

## Implementation Order

1. Create `clusters/` directory structure — `mkdir -p clusters/default`
2. Move all cluster config files and prompts (git mv for history preservation)
3. Update `.gitignore` — new secrets pattern
4. Update `.env.defaults` — remove old fields, add new ones
5. Update `settings.py` — rename `experiment` → `cluster`, add `clusters_dir`,
   remove four path fields, add path derivation functions
6. Update `config/agents.py` — remove `experiment` param from
   `load_agents_config`, update path resolution
7. Update `config/mcp.py` — remove `experiment` param, update path resolution
8. Update `core/agent.py` — remove `experiment` from `_resolve_prompt_path`
9. Update `core/costs.py` — rename field, add migration
10. Update `logging/setup.py` — rename `experiment` param → `cluster`
11. Update all CLI files — `--cluster` flag, pass cluster to settings
12. Update all inspection scripts — column names, display headers
13. Update `ingest_docs.py` — add `clusters/` source dir, exclude secrets
14. Update `justfile` — rename all `experiment` arguments
15. Update `tests/conftest.py` — new fixture structure
16. Update all test files — grep for `experiment`, replace with `cluster`
17. Add new tests (`TestClusterPathDerivation`, `TestCostLedgerMigration`)
18. `just check && just test`
19. Manual smoke test (below)

---

## Manual Smoke Test

```bash
# Default cluster
just start
just send alfa "hello"
# Verify: loads from clusters/default/

# Named cluster
just start research-desk
just send supervisor "Research Nvidia"
# Verify: loads from clusters/research-desk/

# Cost table uses cluster column
just costs
# Header shows "Cluster" not "Experiment"

# Log filenames use cluster
ls logs/
# Shows: {timestamp}_{agent}_{cluster}.log

# Secrets fallback
# (remove clusters/research-desk/agents.mcp.secrets.json if present)
just start research-desk
# Verify: uses clusters/default/agents.mcp.secrets.json without error

# Error on missing cluster
just start nonexistent
# Expect: ConfigurationError: Cluster config not found: clusters/nonexistent/agents.toml

# Ingest includes cluster prompts
just ingest
# Output shows files from clusters/ being indexed
```

---

## Acceptance Criteria

```bash
just check    # zero ruff errors, zero pyright errors
just test     # all tests pass (previous total + new tests)
```

Manual:
- `just start` loads `clusters/default/` with no `--cluster` flag
- `just start research-desk` loads `clusters/research-desk/`
- No `agents.toml` or `agents.mcp.json` remain at repo root
- No `prompts/` directory remains at repo root
- `cost_ledger` table has `cluster` column, not `experiment`
- Existing cost data migrated — rows preserved with column renamed
- Log files show cluster name in filename
- `just costs` shows "Cluster" column header
- `just ingest` indexes files from `clusters/` directory

---

## What This Task Does NOT Include

- New cluster management commands (`just clusters` list, `just new-cluster`)
- Cluster metadata files (description, author)
- Per-cluster settings overrides beyond config files
- Migrating old log files — they retain `experiment` in their filenames,
  which is acceptable; old data is not renamed
- Migrating old `cost_ledger` rows with experiment labels — the column
  rename preserves all data, the values are unchanged
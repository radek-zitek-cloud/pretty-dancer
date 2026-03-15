# Plan: 013b — Cluster Configuration Refactor

**Brief:** `tasks/013b-cluster-refactor.md`
**Branch:** `feature/cluster-refactor`
**Date:** 2026-03-15
**Author:** Tom (implementer)

---

## Summary

Rename "experiment" → "cluster" throughout the entire platform and consolidate
all cluster-specific configuration into a `clusters/` directory. This is a
pure rename and reorganisation — no new behaviour.

---

## Files to Create or Modify

| File | Action | Description |
|------|--------|-------------|
| `clusters/default/agents.toml` | **create** | Move from `agents.toml` (there is no root `agents.toml` — the "default" cluster currently has no dedicated config. I'll create a minimal one with the alfa/beta agents referenced in prompts/) |
| `clusters/default/agents.mcp.json` | **create** | Move from `agents.mcp.json` |
| `clusters/default/agents.mcp.secrets.example.json` | **create** | Move from `agents.mcp.secrets.example.json` |
| `clusters/default/prompts/*.md` | **create** | Move flat prompts from `prompts/` (alfa, beta, conservative, progressive, scout, edith, digger, vera, prose, editor, writer, linguist, billing, technical, triage, escalation) |
| `clusters/default/prompts/routers/*.md` | **create** | Move from `prompts/routers/` (editorial_gate, support_triage) |
| `clusters/research-desk/agents.toml` | **create** | Move from `agents.research-desk.toml` |
| `clusters/research-desk/agents.mcp.json` | **create** | Move from `agents.mcp.research-desk.json` |
| `clusters/research-desk/prompts/` | **create** | Move from `prompts/research-desk/` |
| `clusters/platform-architect/agents.toml` | **create** | Move from `agents.platform-architect.toml` |
| `clusters/platform-architect/agents.mcp.json` | **create** | Move from `agents.mcp.platform-architect.json` |
| `clusters/platform-architect/prompts/` | **create** | Move from `prompts/platform-architect/` |
| `src/multiagent/config/settings.py` | **modify** | Rename `experiment`→`cluster`, add `clusters_dir`, remove `agents_config_path`/`mcp_config_path`/`mcp_secrets_path`/`prompts_dir`, add path derivation functions |
| `src/multiagent/config/agents.py` | **modify** | Remove `experiment` param from `load_agents_config`, delete `resolve_experiment_path` |
| `src/multiagent/config/mcp.py` | **modify** | Remove `experiment` param from `load_mcp_config`, rewrite `_resolve_mcp_secrets_path` |
| `src/multiagent/core/agent.py` | **modify** | Remove `experiment` from `_resolve_prompt_path`, update `LLMAgent.__init__` |
| `src/multiagent/core/costs.py` | **modify** | Rename `experiment`→`cluster` in `CostEntry`, `_CREATE_TABLE`, `_INSERT`, add migration in `_init_schema` |
| `src/multiagent/logging/setup.py` | **modify** | Rename `experiment` param→`cluster` in `configure_logging` and `_build_filename` |
| `src/multiagent/cli/start.py` | **modify** | `--cluster` flag, use path derivation functions |
| `src/multiagent/cli/run.py` | **modify** | `--cluster` flag, use path derivation functions |
| `src/multiagent/cli/chat.py` | **modify** | `--cluster` flag, use path derivation functions |
| `src/multiagent/cli/send.py` | **modify** | `--cluster` flag, use path derivation functions |
| `src/multiagent/cli/monitor.py` | **modify** | `--cluster` flag, rename all `experiment` references |
| `src/multiagent/cli/listen.py` | **verify** | Check for `experiment` references (likely none) |
| `scripts/show_costs.py` | **modify** | `experiment`→`cluster` in SQL, headers, CLI flags |
| `scripts/show_run.py` | **modify** | `experiment`→`cluster` in metadata display |
| `scripts/compare_runs.py` | **modify** | `experiment`→`cluster` in metadata display |
| `scripts/browse_threads.py` | **verify** | Check for `experiment` references |
| `scripts/show_thread.py` | **verify** | Check for `experiment` references |
| `scripts/ingest_docs.py` | **modify** | Add `clusters/` to `SOURCE_DIRS`, exclude secrets files |
| `justfile` | **modify** | Rename all `experiment` arguments to `cluster` |
| `.env.defaults` | **modify** | Remove old fields, add `CLUSTERS_DIR`/`CLUSTER` |
| `.gitignore` | **modify** | Update secrets pattern to `clusters/*/agents.mcp.secrets.json` |
| `tests/conftest.py` | **modify** | Update `test_settings` fixture |
| `tests/unit/config/test_settings.py` | **modify** | Rename experiment → cluster |
| `tests/unit/config/test_agents.py` | **modify** | Remove experiment tests, update path-based tests |
| `tests/unit/config/test_mcp.py` | **modify** | Remove experiment tests, update path-based tests |
| `tests/unit/cli/test_chat.py` | **modify** | Rename experiment → cluster |
| `tests/unit/core/test_costs.py` | **modify** | Rename experiment → cluster |
| `tests/unit/scripts/test_show_costs.py` | **modify** | Rename experiment → cluster in SQL |
| `tests/unit/core/test_runner.py` | **verify** | Check for experiment references |
| `tests/fixtures/` | **verify** | Fixture agents.toml doesn't reference experiment |
| New: `tests/unit/config/test_cluster_paths.py` | **create** | `TestClusterPathDerivation` — 4 tests |
| New: `tests/unit/core/test_cost_migration.py` | **create** | `TestCostLedgerMigration` — 2 tests |

---

## Implementation Order

### Phase 1: Directory structure (git mv for history)

1. `mkdir -p clusters/default/prompts/routers`
2. `git mv agents.mcp.json clusters/default/agents.mcp.json`
3. `git mv agents.mcp.secrets.example.json clusters/default/agents.mcp.secrets.example.json`
4. Move all flat prompts: `git mv prompts/alfa.md clusters/default/prompts/alfa.md` (repeat for each)
5. Move router prompts: `git mv prompts/routers/* clusters/default/prompts/routers/`
6. `mkdir -p clusters/research-desk/prompts`
7. `git mv agents.research-desk.toml clusters/research-desk/agents.toml`
8. `git mv agents.mcp.research-desk.json clusters/research-desk/agents.mcp.json`
9. `git mv prompts/research-desk/* clusters/research-desk/prompts/` (including `routers/`)
10. `mkdir -p clusters/platform-architect/prompts`
11. `git mv agents.platform-architect.toml clusters/platform-architect/agents.toml`
12. `git mv agents.mcp.platform-architect.json clusters/platform-architect/agents.mcp.json`
13. `git mv prompts/platform-architect/* clusters/platform-architect/prompts/`
14. Create `clusters/default/agents.toml` — need to create a default agents config (there is no root `agents.toml` since the research-desk rename in 013a)
15. Remove empty `prompts/` directory if empty
16. Update `.gitignore`
17. **[Feedback #1]** Grep all `prompt =` fields in `clusters/` and update paths to reflect new locations
18. Commit: `chore: migrate config files to clusters/ directory structure`

**Rationale:** Do file moves first so git tracks renames before code changes.

### Phase 2: Settings and path derivation

18. Update `settings.py`:
    - Rename `experiment: str` → `cluster: str`
    - Add `clusters_dir: Path = Field(Path("clusters"), ...)`
    - Remove `agents_config_path`, `mcp_config_path`, `mcp_secrets_path`, `prompts_dir`
    - Add module-level functions: `cluster_dir()`, `agents_config_path()`, `mcp_config_path()`, `mcp_secrets_path()`, `prompts_dir()`
19. Update `.env.defaults`:
    - Remove `AGENTS_CONFIG_PATH`, `MCP_CONFIG_PATH`, `MCP_SECRETS_PATH`, `PROMPTS_DIR`, `EXPERIMENT`
    - Add `CLUSTERS_DIR=clusters`, `CLUSTER=`
20. Commit: `feat(config): replace experiment with cluster, add path derivation functions`

### Phase 3: Config loaders

21. Update `config/agents.py`:
    - Remove `resolve_experiment_path` function
    - Simplify `load_agents_config(path: Path) -> AgentsConfig` — no `experiment` param
22. Update `config/mcp.py`:
    - Rewrite `_resolve_mcp_secrets_path` to work with cluster paths (settings-based)
    - Simplify `load_mcp_config(config_path: Path, secrets_path: Path | None) -> MCPConfig` — no `experiment` param
    - `secrets_path` becomes `Path | None` since `mcp_secrets_path()` can return `None`
23. Update `core/agent.py`:
    - Simplify `_resolve_prompt_path(prompts_dir: Path, agent_name: str) -> Path` — no `experiment` param
    - Update `LLMAgent.__init__` — use `prompts_dir(settings)` instead of `settings.prompts_dir`
24. Commit: `refactor(config): simplify loaders — cluster paths derived from settings`

### Phase 4: Cost ledger

25. Update `core/costs.py`:
    - Rename `CostEntry.experiment` → `CostEntry.cluster`
    - Update `_CREATE_TABLE` — column name `cluster`
    - Update `_INSERT` — column name `cluster`
    - Add migration in `_init_schema()`: detect old `experiment` column, rename to `cluster`
    - Update `record()` — use `entry.cluster`
26. Commit: `feat(core): rename cost_ledger experiment column to cluster with migration`

### Phase 5: Logging

27. Update `logging/setup.py`:
    - `_build_filename(agent_name, cluster)` — rename param
    - `configure_logging(settings, agent_name, cluster)` — rename param, update `effective_experiment` → `effective_cluster`
28. Commit: `refactor(logging): rename experiment param to cluster`

### Phase 6: CLI

29. Update all CLI files (`start.py`, `run.py`, `chat.py`, `send.py`, `monitor.py`):
    - `--experiment` → `--cluster`, `-e` → `-c`
    - `settings.experiment` → `settings.cluster`
    - Pass `agents_config_path(settings)` instead of `settings.agents_config_path`
    - Pass `mcp_config_path(settings)`, `mcp_secrets_path(settings)` instead of `settings.mcp_config_path`
    - Pass `prompts_dir(settings)` where needed
    - Validation regex unchanged: `^[a-z0-9-]+$`
30. Update `justfile` — all `experiment` arguments → `cluster`
31. Commit: `feat(cli): replace --experiment with --cluster across all commands`

### Phase 7: Scripts

32. Update `scripts/show_costs.py` — SQL column `experiment`→`cluster`, display headers, `--experiment` flag → `--cluster`
33. Update `scripts/show_run.py` — metadata display
34. Update `scripts/compare_runs.py` — metadata display
35. Check `scripts/browse_threads.py` and `scripts/show_thread.py` for experiment refs
36. Update `scripts/ingest_docs.py` — add `Path("clusters")` to `SOURCE_DIRS`, add `EXCLUDED_FILENAMES`
37. Commit: `refactor(scripts): rename experiment to cluster in all inspection scripts`

### Phase 8: Tests

38. Update `tests/conftest.py`:
    - Replace `experiment=""` with `cluster=""`
    - Replace path fields with `clusters_dir=tmp_path / "clusters"` and create `tmp_path / "clusters" / "default" /` structure
39. Update all test files — grep and replace `experiment` → `cluster`:
    - `tests/unit/config/test_settings.py`
    - `tests/unit/config/test_agents.py` — remove `TestExperimentConfigResolution`, replace with cluster-based tests
    - `tests/unit/config/test_mcp.py` — remove experiment tests, replace with cluster-based tests
    - `tests/unit/cli/test_chat.py`
    - `tests/unit/core/test_costs.py`
    - `tests/unit/scripts/test_show_costs.py`
    - `tests/unit/core/test_runner.py` (if any refs)
40. Create `tests/unit/config/test_cluster_paths.py`:
    - `test_default_cluster_loads_from_clusters_default`
    - `test_named_cluster_loads_from_clusters_subdir`
    - `test_raises_when_cluster_dir_missing`
    - `test_secrets_falls_back_to_default_cluster`
41. Create `tests/unit/core/test_cost_migration.py`:
    - `test_migrates_experiment_column_to_cluster`
    - `test_schema_already_migrated_is_idempotent`
42. Commit: `test: update all tests for experiment→cluster rename`

### Phase 9: Gate

43. `just check && just test`
44. Fix any issues
45. Final commit if needed

---

## Design Decisions

### D1: Default cluster agents.toml

There is currently no `agents.toml` at the repo root — it was deleted when research-desk configs were moved in 013a. The "default" cluster needs an `agents.toml`. I'll create a minimal one with the agents that have prompts in `prompts/` (alfa, beta, plus any others that are used). Looking at the existing flat prompts, these appear to be multiple experiment clusters that were never formally separated (editorial: editor/writer/linguist, support: triage/billing/technical/escalation, debate: conservative/progressive/scout/edith/digger/vera/prose).

**Decision:** I'll create `clusters/default/agents.toml` with just `alfa` and `beta` as a minimal default, since those are the documented defaults in the implementation guide. The other prompt files (editor, writer, etc.) belong to other clusters that aren't formally defined yet — I'll move them to `clusters/default/prompts/` as the brief instructs, but they won't be wired in the default `agents.toml`.

### D2: Router prompt paths in research-desk agents.toml

Currently `agents.research-desk.toml` has:
```toml
prompt = "prompts/research-desk/routers/research_supervisor.md"
```

After migration, this becomes:
```toml
prompt = "clusters/research-desk/prompts/routers/research_supervisor.md"
```

The `prompt` field on routers uses an absolute path from repo root. This needs updating in the moved TOML files.

### D3: `mcp_secrets_path()` return type

The brief says `mcp_secrets_path()` returns `Path | None`. This changes the `load_mcp_config` signature — `secrets_path` becomes `Path | None`. The current code has a fallback inside `load_mcp_config` where it checks `secrets_path.exists()` — this needs to be adjusted to handle `None`.

### D4: `agents_config_path()` validation

The brief puts the existence check inside `agents_config_path()`. This means the function raises `ConfigurationError` rather than returning a path that may not exist. The `load_agents_config` function's own FileNotFoundError catch becomes a backup for race conditions only.

### D5: Test fixture update strategy

The test fixtures in `tests/fixtures/` (agents.toml, agents.mcp.json, prompts/) don't use the cluster directory pattern. Tests that use `test_settings` will need `clusters_dir` pointing to a temp path with the right structure. I'll update `conftest.py` to create `tmp_path/clusters/default/` with the minimal required files.

### D6: `config/__init__.py` exports

After removing the four path fields from `Settings` and adding module-level functions, these new functions need to be exported from `config/__init__.py`:
- `cluster_dir`, `agents_config_path`, `mcp_config_path`, `mcp_secrets_path`, `prompts_dir`

### D7: `listen.py` and `stop.py` — no changes expected

These don't accept `--experiment` today, so they shouldn't need changes. Will verify.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Router prompt paths break after move | Update all `prompt = "..."` paths in moved TOML files |
| `pydantic-settings` `extra="forbid"` rejects old env vars | Update `.env.defaults` in the same commit as settings.py changes |
| Cost ledger migration fails on empty DB | Migration checks column names first — no-op on new schema |
| Test fixtures break due to removed settings fields | Update conftest.py first in the test phase |

---

## Architect Feedback (incorporated)

1. **Feedback #1 — Router prompt paths:** After migrating TOML files, grep all `prompt =` fields and update to `clusters/...` paths. Verified with `grep -r "^prompt = " clusters/`.
2. **Feedback #2 — Default cluster:** Approved. Minimal alfa/beta only, orphaned prompts as assets in `clusters/default/prompts/`.
3. **Feedback #3 — No editorial cluster:** Approved. No `clusters/editorial/` directory since no `agents.mcp.editorial.json` exists.
4. **Feedback #4 — Secrets file migration:** Report to Radek: "Move your local `agents.mcp.secrets.json` from the repo root to `clusters/default/agents.mcp.secrets.json` manually after merging."

---

## What I Would Do Differently from the Brief

1. **No `editorial/` cluster directory** — The brief shows `clusters/editorial/` in the tree, but there is no `agents.editorial.toml` or `agents.mcp.editorial.json` in the repo. The editorial prompts (editor, writer, linguist) exist as flat files in `prompts/`. I'll move them to `clusters/default/prompts/` rather than creating an editorial cluster that has no agents.toml wiring. If the architect wants a separate editorial cluster, that's a follow-up task.

2. **`agents.mcp.secrets.json` at repo root** — Currently gitignored at root. The brief says to move it to `clusters/default/agents.mcp.secrets.json`. Since this is a local secrets file (gitignored), I can't `git mv` it. I'll document that users need to move their local `.env` and secrets files manually after the migration.

3. **`COST_DB_PATH` missing from `.env.defaults`** — It's in `settings.py` but not in `.env.defaults`. I'll add it while I'm updating the defaults file.

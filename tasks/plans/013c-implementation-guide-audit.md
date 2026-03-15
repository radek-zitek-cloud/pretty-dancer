# Implementation Guide Audit Report

**Date:** 2026-03-15
**Auditor:** Tom (implementer)
**Context:** Post-013b merge, pre-013c implementation

---

## Summary

| Section | Status | Key Issue |
|---------|--------|-----------|
| 3 (Repository Structure) | STALE | `agents.toml`/`prompts/` moved to `clusters/`; `clusters/` dir not shown; `monitor.py`, `logging/` module missing |
| 5 (Module Dependencies) | STALE | `models.py` not yet in table (013c will create it); `core/runner.py` still imports from transport |
| 6 (Configuration) | STALE | `experiment` → `cluster`; four path fields removed; `clusters_dir` added; path derivation functions not documented; MCP config undocumented |
| 7 (Observability) | STALE | `experiment` → `cluster` in filenames and `configure_logging` signature |
| 9 (Agent Contract) | STALE | `prompts_dir` is a function not a field; `prompt_name` and `tool_configs` params undocumented |
| 14 (Scripts) | STALE | `ingest_docs.py` / `just ingest` missing; `show_costs.py` references "experiment" |
| 16 (Task Runner) | STALE | `experiment` → `cluster` in targets; `monitor` command missing; `ingest` target missing |
| Multiple | STALE | Pervasive "experiment" terminology throughout |

---

## Detailed Findings

### Section 3 — Repository Structure

**STALE: Root-level files moved to clusters/**
- `agents.toml` no longer at root → now `clusters/{name}/agents.toml`
- `prompts/` directory no longer at root → now `clusters/{name}/prompts/`
- `clusters/` directory exists but is not shown in the tree

**STALE: Missing files/modules in tree**
- `src/multiagent/logging/` module exists (setup.py) but not in tree
- `src/multiagent/cli/monitor.py` exists but not listed
- `scripts/ingest_docs.py` exists but not listed
- `data/chroma/` directory (ChromaDB data) not shown

**STALE: Config module exports**
- Guide says `core/__init__.py` exports `CostLedger` — it does not
- Guide doesn't mention MCP exports from `config/__init__.py`

### Section 5 — Module Dependency Rules

**STALE (to be fixed in 013c):** `core/runner.py` has runtime import from `transport.base` (Message). After 013c creates `models.py`, the dependency table needs updating.

### Section 6 — Configuration Contract

**STALE: Field renames**
- `experiment` → `cluster`
- `prompts_dir`, `agents_config_path`, `mcp_config_path`, `mcp_secrets_path` removed as Settings fields
- `clusters_dir`, `cluster` added as Settings fields
- Path derivation functions (`cluster_dir()`, `agents_config_path()`, `mcp_config_path()`, `mcp_secrets_path()`, `prompts_dir()`) not documented
- `agent_loop_detection_threshold`, `agent_max_messages_per_thread` not in fields table

**STALE: Settings immutability note**
- Line 296: "with the exception of `experiment`" → should be `cluster`

### Section 7 — Observability Contract

**STALE:**
- Log filename patterns show `[_{experiment}]` → should be `[_{cluster}]`
- `configure_logging` signature shows `experiment` → `cluster`

### Section 9 — Agent Contract

**STALE:**
- "loaded from `{settings.prompts_dir}/{name}.md`" — `prompts_dir` is now a function, not a field
- New optional params `tool_configs` and `prompt_name` not documented

### Section 14 — Scripts

**STALE:**
- `ingest_docs.py` missing from script table
- `show_costs.py` description says "by experiment" → "by cluster"

### Section 16 — Task Runner

**STALE:**
- `just start [experiment]` → `just start [cluster]`
- `just costs` description says "by experiment" → "by cluster"
- `just monitor`, `just ingest` targets missing
- `just run`, `just send`, `just chat` all accept `--cluster` not `--experiment`

### Sections 4, 8, 10, 11, 12, 13 — CORRECT

These sections are accurate and match the current codebase.

---

## Items for 013c (mechanical fixes, docs only)

All findings above are mechanical updates to `docs/implementation-guide.md`:
- Replace "experiment" with "cluster" throughout
- Update Section 3 file tree
- Update Section 5 dependency table (after `models.py` creation)
- Update Section 6 configuration fields
- Update Section 7 observability signatures
- Update Section 9 agent contract
- Update Section 14 scripts table
- Update Section 16 task runner table

No design decisions required. All changes are to documentation only.

# Plan: 013c — Post-Refactor Cleanup

**Brief:** `tasks/013c-post-refactor-cleanup.md`
**Branch:** `feature/013c-cleanup`
**Date:** 2026-03-15
**Author:** Tom (implementer)

---

## Summary

Three issues: fix the `core/runner.py` → `transport/base` boundary violation by
extracting `Message` to `models.py`, revert `ingest_docs.py` extensions to `.md`
only, and update `docs/implementation-guide.md` to reflect the post-013b state.

---

## Files to Create or Modify

| File | Action | Description |
|------|--------|-------------|
| `src/multiagent/models.py` | **create** | Extract `Message` dataclass from `transport/base.py` |
| `src/multiagent/transport/base.py` | **modify** | Import `Message` from `multiagent.models` instead of defining locally, re-export for backward compat |
| `src/multiagent/core/runner.py` | **modify** | Import `Message` from `multiagent.models` instead of `transport.base` |
| `src/multiagent/transport/__init__.py` | **modify** | Import `Message` from `multiagent.models` (or keep re-export from `base.py`) |
| `scripts/ingest_docs.py` | **modify** | Revert `SOURCE_EXTENSIONS` to `{".md"}`, remove `EXCLUDED_FILENAMES` |
| `docs/implementation-guide.md` | **modify** | Update sections 3, 5, 6, 7, 9, 14, 16 for post-013b/013c state |
| `tests/unit/test_module_boundaries.py` | **create** | Programmatic boundary enforcement tests |
| `tests/unit/core/test_runner.py` | **modify** | Import `Message` from `multiagent.models` |
| `tests/conftest.py` | **modify** | Import `Message` from `multiagent.models` |
| `tests/integration/test_pipeline.py` | **modify** | Import `Message` from `multiagent.models` |
| `tests/unit/transport/test_base.py` | **verify** | May continue importing from `transport.base` (it re-exports) |
| `tests/unit/transport/test_sqlite.py` | **verify** | Same |
| `tests/unit/transport/test_terminal.py` | **verify** | Same |

---

## Implementation Order

### Phase 0: Audit (feedback requirement)

0. Run `/tom-audit` to produce a systematic gap report
1. Commit the audit report to the branch
2. Use findings to inform Phase 4 guide updates

### Phase 1: Create `models.py` and fix boundary violation

1. Create `src/multiagent/models.py` containing the `Message` dataclass (moved from `transport/base.py`)
2. Update `src/multiagent/transport/base.py`:
   - Remove `Message` class definition
   - Import from `multiagent.models` and re-export: `from multiagent.models import Message`
   - This preserves backward compatibility for `cli/` and `transport/` imports
3. Update `src/multiagent/core/runner.py`:
   - Change `from multiagent.transport.base import Message` → `from multiagent.models import Message`
   - The `Transport` import stays under `TYPE_CHECKING` (already correct)
4. Update `src/multiagent/transport/__init__.py`:
   - Ensure `Message` is re-exported (already is, via `base.py` which re-exports from `models`)
5. Verify: `grep -r "from multiagent.transport" src/multiagent/core/` returns only the TYPE_CHECKING line
6. Commit: `fix(core): extract Message to models.py, resolve runner boundary violation`

### Phase 2: Fix `ingest_docs.py`

7. Update `scripts/ingest_docs.py`:
   - Revert `SOURCE_EXTENSIONS = {".md", ".toml", ".json"}` → `SOURCE_EXTENSIONS = {".md"}`
   - Remove `EXCLUDED_FILENAMES` dict and its usage in `collect_files()`
   - Simplify `collect_files()` back to `files.extend(sorted(...))`
8. Commit: `fix(scripts): revert ingest_docs to .md only`

### Phase 3: Boundary enforcement tests

9. Create `tests/unit/test_module_boundaries.py`:
   - `test_core_does_not_import_transport` — grep-based, asserts no runtime imports
   - `test_transport_does_not_import_core` — same pattern
10. Update test imports where needed:
    - `tests/unit/core/test_runner.py` — import `Message` from `multiagent.models`
    - `tests/conftest.py` — import `Message` from `multiagent.models`
    - `tests/integration/test_pipeline.py` — import `Message` from `multiagent.models`
    - Transport test files can continue importing from `transport.base` (it re-exports)
11. Commit: `test: add module boundary enforcement tests`

### Phase 4: Implementation guide updates

12. Update `docs/implementation-guide.md`:
    - **Section 3 (Repository Structure):** Replace `agents.toml` at root with `clusters/` directory, remove `prompts/` at root, add `models.py`, add `ingest_docs.py` to scripts list
    - **Section 5 (Module Dependency Rules):** Add `models` to the dependency table (`core/ → may import from: config/, models, exceptions`), update verification commands
    - **Section 6 (Configuration Contract):** Replace `experiment` with `cluster`, replace `prompts_dir`/`agents_config_path`/`mcp_config_path`/`mcp_secrets_path` with `clusters_dir`/`cluster`, document path derivation functions, update Settings Fields Reference table
    - **Section 7 (Observability Contract):** Replace `experiment` with `cluster` in filename patterns and `configure_logging` signature
    - **Section 9 (Agent Contract):** Update prompt loading description — `prompts_dir(settings)` not `settings.prompts_dir`
    - **Section 14 (Scripts):** Add `ingest_docs.py` with `just ingest`, update `show_costs.py` description (`cluster` not `experiment`)
    - **Section 16 (Task Runner):** Update `just start [cluster]`, add `just ingest`, update `just costs` description
13. Commit: `docs: update implementation guide for post-013b state`

### Phase 5: Gate

14. `just check && just test`
15. Fix any issues

---

## Design Decisions

### D1: `models.py` location and scope

The brief says to create `src/multiagent/models.py` as a sibling to `exceptions.py`. I agree — this is the neutral location both `core/` and `transport/` can import from.

Only `Message` moves to `models.py`. The `Transport` ABC stays in `transport/base.py` because it's a port definition. The brief explicitly confirms this.

### D2: Re-export from `transport/base.py`

After moving `Message` to `models.py`, `transport/base.py` will re-export it:
```python
from multiagent.models import Message
```

This means `cli/` files, `transport/` internals, and transport tests can continue importing from `transport.base` or `transport` without changes. Only `core/` code must import from `multiagent.models`.

This minimizes the diff while fixing the boundary violation.

### D3: Test import updates

The brief says to update test imports to use `multiagent.models`. I will update:
- `tests/unit/core/test_runner.py` — must not import from transport
- `tests/conftest.py` — shared fixture, good to be neutral
- `tests/integration/test_pipeline.py` — good practice

Transport tests (`test_base.py`, `test_sqlite.py`, `test_terminal.py`) can keep importing from `transport.base` since that's what they're testing.

### D4: Boundary test approach

The brief suggests subprocess grep. I'll use `subprocess.run` calling `grep -r` on the source tree and asserting empty output. This is simple, reliable, and won't break if import styles change — it catches any form of the forbidden import.

### D5: `ingest_docs.py` — no `--reset` in automation

The brief mentions running `just ingest --reset` after the fix. The `ingest` justfile target doesn't accept flags, so I'll document this as a manual step in the completion report. The code change is the `SOURCE_EXTENSIONS` revert.

### D6: Implementation guide — scope of changes

I will update only the sections called out in the brief (3, 5, 6, 7, 9, 14, 16) plus any other lines referencing `experiment` or stale paths. I will not restructure or rewrite sections beyond what's needed for accuracy.

---

## What I Would Do Differently from the Brief

1. **CLI import updates** — The brief says to update `cli/` imports if needed. Since `transport/base.py` re-exports `Message` from `models.py`, CLI files don't need to change. I'll leave them as-is to minimize the diff.

2. **`models.py` import rules** — The brief says `models.py → may import from: exceptions only`. Looking at `Message`, it doesn't import from `exceptions` — it only uses stdlib (`dataclasses`, `uuid`, `datetime`). So `models.py` imports from nothing within the project. This is correct and tighter than the brief's allowance.

3. **~~No audit step~~** — REJECTED by architect. `/tom-audit` must run as Step 0 before any code changes. The audit report is committed first and informs the Phase 4 guide update. The audit catches drift from earlier tasks that may not be visible from 013b alone.

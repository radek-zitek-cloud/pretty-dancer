# Task 013c — Post-Refactor Cleanup

**File:** `tasks/013c-post-refactor-cleanup.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-15  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 013b (cluster refactor) complete and merged to master

---

## Objective

Address two issues surfaced during the 013b implementation report, plus any
additional small findings from the implementation guide audit run after 013b
merged. This is a cleanup task — no new behaviour, no new features.

**Known issues at time of briefing:**

1. `core/runner.py` imports from `transport/base` — pre-existing module
   boundary violation
2. `scripts/ingest_docs.py` may be indexing `.toml` and `.json` files from
   `clusters/` in addition to `.md` files — unintended, should be `.md` only

**Additional scope:** After running `/tom-audit`, any WRONG or STALE items
from the audit that are small enough to fix in a single task are folded into
013c. Items that require significant design work are logged as separate tasks.

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — canonical authority
- `tasks/013b-cluster-refactor.md` — context for the issues being fixed
- `tasks/plans/implementation-guide-audit-{date}.md` — audit report produced
  before this task begins

---

## Git

Work on branch `feature/013c-cleanup` created from `master`.

```bash
git checkout master
git pull origin master
git checkout -b feature/013c-cleanup
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
fix(core): resolve runner transport boundary violation and cleanup
```

---

## Issue 1 — Module Boundary Violation: `core/runner.py`

### What the violation is

`core/runner.py` imports from `transport/base` — almost certainly to access
`Message` or `Transport`. This violates the absolute rule:

```
core/ must never import from transport/
```

### How to fix it

**Step 1 — Inspect the actual import**

```bash
grep -n "from multiagent.transport" src/multiagent/core/runner.py
grep -n "import.*transport" src/multiagent/core/runner.py
```

Identify exactly what is being imported and why.

**Step 2 — Move shared types to a neutral location**

Create `src/multiagent/models.py` at the package root (sibling to
`exceptions.py`). This is a shared types module that both `core/` and
`transport/` can import from without creating a circular dependency.

Move to `models.py` only what `core/` needs from `transport/base`:
- `Message` dataclass (if imported)
- Any other shared types

`transport/base.py` then imports `Message` from `multiagent.models` rather
than defining it locally. `core/runner.py` imports from `multiagent.models`.
`cli/` and `scripts/` continue to import from wherever currently works —
update their imports if needed.

**Do not move `Transport` ABC to `models.py`.** The `Transport` ABC is a
port definition — it belongs in `transport/`. If `runner.py` is importing
`Transport` for type annotation purposes only, use `TYPE_CHECKING`:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from multiagent.transport.base import Transport
```

This satisfies pyright without creating a runtime import.

**Step 3 — Verify the fix**

```bash
grep -r "from multiagent.transport" src/multiagent/core/
grep -r "from multiagent.core"      src/multiagent/transport/
```

Both must return empty.

### Module boundary after fix

```
models.py     → may import from: exceptions only
core/         → may import from: config/, models, exceptions
transport/    → may import from: config/, models, exceptions
cli/          → may import from: core/, transport/, config/, models, exceptions
```

Update the implementation guide section 5 (Module Dependency Rules) to
include `models` in the dependency table.

---

## Issue 2 — `ingest_docs.py` File Extension Filter

### What to check

Confirm whether `SOURCE_EXTENSIONS` in `scripts/ingest_docs.py` is currently
`{".md"}` only or has been expanded:

```bash
grep "SOURCE_EXTENSIONS" scripts/ingest_docs.py
```

### If extensions were expanded beyond `.md`

Revert to `.md` only:

```python
SOURCE_EXTENSIONS = {".md"}
```

The cluster directory structure and agent wiring are better understood by the
architect agent from the markdown prompt files and task briefs than from raw
TOML or JSON. Indexing structured config files adds noise to semantic search
without meaningful benefit.

Run `just ingest --reset` after this fix to rebuild the Chroma collection
with clean content.

### If extensions are already `.md` only

No change needed. Document the finding in the implementation report.

---

## Issue 3 — Implementation Guide Updates from Audit

After running `/tom-audit`, fold in any audit findings classified as WRONG
or STALE that meet all of these criteria:

- The fix is mechanical (rename, add a missing item, remove a nonexistent one)
- No design decision is required
- The fix touches only `docs/implementation-guide.md`, not source code

Items that require code changes or design decisions are logged as separate
tasks and not included in 013c.

**Specifically, ensure these sections are current after 013b:**

- Section 3 (Repository Structure) — `clusters/` directory in the tree,
  no `agents.toml` or `prompts/` at repo root, `models.py` if created
- Section 5 (Module Dependency Rules) — updated table including `models.py`,
  updated verification commands
- Section 6 (Configuration Contract) — `clusters_dir`, `cluster` field,
  removal of four old path fields, path derivation functions
- Section 14 (Scripts and Inspection Tools) — `ingest_docs.py` and
  `just ingest` documented
- Section 16 (Task Runner Reference) — `just ingest` target, `--cluster`
  flags on `start`, `run`, `chat`, `monitor`

---

## Test Requirements

### For Issue 1

```
TestModuleBoundaries
    test_core_does_not_import_transport
        — subprocess grep returning empty for transport imports in core/
        — assert returncode != 0 or stdout == ""

    test_transport_does_not_import_core
        — subprocess grep returning empty for core imports in transport/
        — assert returncode != 0 or stdout == ""
```

These are meta-tests that enforce the boundary rules programmatically rather
than relying on manual grep after each task. Place in
`tests/unit/test_module_boundaries.py`.

Update any existing tests that import `Message` from `transport/base` to
import from `multiagent.models` instead.

### For Issue 2

No new tests — the extension filter is a one-line config value. If tests for
`ingest_docs.py` exist, verify they still pass.

### For Issue 3

No tests for documentation changes.

---

## Implementation Order

1. Run `/tom-audit` — read the full gap report before writing any code
2. Confirm the `ingest_docs.py` extension situation — one grep, then fix
   or document
3. Fix Issue 1 — inspect import, create `models.py` if needed, update all
   callers, verify boundaries
4. Create `tests/unit/test_module_boundaries.py` — boundary enforcement tests
5. Update `docs/implementation-guide.md` — fold in audit findings that meet
   the 013c criteria
6. `just check && just test`
7. If `ingest_docs.py` was changed: `just ingest --reset`

---

## Acceptance Criteria

```bash
just check    # zero ruff errors, zero pyright errors
just test     # all tests pass (previous total + new boundary tests)
```

Manual:
- `grep -r "from multiagent.transport" src/multiagent/core/` returns empty
- `grep -r "from multiagent.core" src/multiagent/transport/` returns empty
- `scripts/ingest_docs.py` indexes only `.md` files (or documents why not)
- `docs/implementation-guide.md` reflects current codebase for all sections
  touched by 013a, 013b, and 013c

---

## What This Task Does NOT Include

- New features or behaviour
- Audit findings that require design decisions
- Audit findings that require significant code changes beyond
  `docs/implementation-guide.md` updates
- Any item deferred to a future task by the architect
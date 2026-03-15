# Skill: /tom-plan

**Invocation:** `/tom-plan <task-id>`  
**Example:** `/tom-plan 013a`  
**Purpose:** Pick up a task brief, produce an implementation plan, and wait for architect review.

---

## Instructions

You have been invoked with task ID: `$ARGUMENTS`

### Step 1 — Verify master is clean

```bash
git status
git log --oneline -5
```

If uncommitted changes exist on master:
1. Inspect each file — stage intentionally, never blindly
2. Commit with an appropriate Conventional Commit message
3. Push: `git push origin master`

Do not proceed until master is clean.

### Step 2 — Find the brief

Locate the brief file:

```bash
ls tasks/$ARGUMENTS-*.md
```

If no file matches, stop and report:
```
No brief found matching tasks/$ARGUMENTS-*.md
```

Read the brief in full. Note the full filename stem (e.g. `013a-experiment-configs`) —
you will use it for the plan filename and branch name.

### Step 3 — Read mandatory documents

In this order:
1. `docs/implementation-guide.md` — canonical authority
2. The brief found in Step 2
3. Every document listed in the brief's "Authoritative References" section

### Step 4 — Inspect the codebase

Use SERENA to understand the current state of every file the brief says you
will modify. Do not rely on the brief's description of current signatures —
verify against the actual code.

### Step 5 — Produce the plan

Write a plan covering:
- Files to create or modify (table: file | action | description)
- Implementation order with rationale
- Design decisions and how you resolve ambiguities
- Anything in the brief you would do differently, with justification

### Step 6 — Save the plan

```bash
mkdir -p tasks/plans
```

Save to: `tasks/plans/{brief-stem}-plan.md`

For example, if the brief is `tasks/013a-experiment-configs.md`, save to:
`tasks/plans/013a-experiment-configs-plan.md`

Do not commit the plan yet.

### Step 7 — Stop

Present the plan and wait. Do not write any implementation code until you
receive architect approval via `/tom-build $ARGUMENTS`.
# Skill: /tom-build

**Invocation:** `/tom-build <task-id>`  
**Example:** `/tom-build 013a`  
**Purpose:** Read architect feedback, update the plan, implement the task, and report.

---

## Instructions

You have been invoked with task ID: `$ARGUMENTS`

### Step 1 — Read the feedback

Locate and read the feedback file:

```bash
cat tasks/feedback/$ARGUMENTS.md
```

If the file does not exist, stop and report:
```
No feedback file found at tasks/feedback/$ARGUMENTS.md
Create this file with the architect's feedback before invoking /tom-build.
```

Read the feedback carefully before touching any code. If any item is unclear,
state your interpretation explicitly — do not guess silently.

### Step 2 — Derive the branch name

Locate the brief to get the full task slug:

```bash
ls tasks/$ARGUMENTS-*.md
```

Branch name: `feature/{brief-stem}`

For example, if the brief is `tasks/013a-experiment-configs.md`:
- Branch: `feature/013a-experiment-configs`

### Step 3 — Create the feature branch

```bash
git checkout master
git pull origin master
git checkout -b feature/{brief-stem}
```

### Step 4 — Update the plan

Read the current plan at `tasks/plans/$ARGUMENTS-*-plan.md`.

Update it to reflect all feedback — the plan should represent what will
actually be built, not the original draft. This is the first commit:

```bash
git add tasks/plans/
git commit -m "docs(tasks): update $ARGUMENTS plan with architect feedback"
```

### Step 5 — Implement

Implement the full task incorporating all feedback. Commit at each meaningful
step using Conventional Commits.

Use SERENA for all structural code navigation. Use Context7 for any
third-party library API questions.

### Step 6 — Gate

```bash
just check && just test
```

Both must pass with zero errors. Fix any issues before proceeding.

### Step 7 — Report

Report back with:
- Confirmation that `just check && just test` passed
- List of files created or modified
- Any deviations from the brief or feedback, with justification
- Any follow-up observations for the architect

Do not merge to master — that step is Radek's.
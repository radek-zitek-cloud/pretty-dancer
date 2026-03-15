# Development Workflow

**Project:** multiagent platform  
**Last Updated:** 2026-03-15

---

## Overview

The platform is developed by three participants:

| Participant | Role | Interface |
|---|---|---|
| **Radek** | Platform owner, decision maker | This conversation + terminal |
| **Architect** | Design, briefs, plan review, feedback | Claude.ai (this conversation) |
| **Tom** | Implementation | Claude Code |

Radek is the only person who merges to master. Tom pushes branches and reports.
The Architect produces briefs and reviews plans but never touches the codebase.

---

## Tools

### Tom's Tools (Claude Code)

**SERENA MCP** — semantic code navigation. Symbol search, find references, go
to definition. Primary tool for understanding the codebase. Use before grep
for anything structural.

**SQLite MCP** — direct database inspection during development and debugging:
- `sqlite-transport` → `data/agents.db` (messages, threads)
- `sqlite-costs` → `data/costs.db` (cost ledger)
- `sqlite-checkpoints` → `data/checkpoints.db` (LangGraph state)

**Context7 MCP** — current third-party library documentation. Always use
before relying on training data for LangGraph, pydantic-settings, aiosqlite,
structlog, Textual, langchain-mcp-adapters APIs.

**Chroma MCP** (platform-architect cluster) — RAG over project knowledge base.
Run `just ingest` after updating docs or task briefs.

### Skills (Claude Code slash commands)

Three skills are installed at `.claude/skills/`:

| Skill | Invocation | Purpose |
|---|---|---|
| `tom-plan` | `/tom-plan <task-id>` | Pick up a brief, produce a plan, wait for review |
| `tom-build` | `/tom-build <task-id>` | Read feedback, update plan, implement, report |
| `tom-audit` | `/tom-audit` | Audit implementation guide against codebase |

---

## Standard Task Workflow

### Step 1 — Architect writes the brief

Radek and the Architect discuss the feature in this conversation. Once the
design is agreed, the Architect produces a task brief.

Briefs are saved to `tasks/{task-id}-{slug}.md` in the repo.
Task IDs follow the pattern: `001`, `002`, ... `013`, `013a`, `013b`, etc.

### Step 2 — Tom produces a plan

Radek invokes the plan skill in Claude Code:

```
/tom-plan 013b
```

Tom reads the brief, inspects the codebase with SERENA, and produces a written
implementation plan. The plan is saved to
`tasks/plans/{task-id}-{slug}-plan.md` before being presented.

Tom stops and waits. No code is written yet.

### Step 3 — Architect reviews the plan

Radek pastes Tom's plan into this conversation. The Architect reviews it for:
- Module boundary violations
- Incorrect understanding of current signatures
- Missing tests for failure paths
- Deviations from the brief that need justification
- Design decisions that could be improved

The Architect produces feedback: either approved, or a list of corrections.

### Step 4 — Radek writes the feedback file

If there are corrections, Radek creates a feedback file in the repo:

```
tasks/feedback/{task-id}-feedback.md
```

Multiple feedback rounds are supported — each additional round creates a new
file with a suffix:

```
tasks/feedback/013b-feedback.md
tasks/feedback/013b-feedback-2.md
```

Tom reads all files matching `tasks/feedback/013b-*.md` in filename order.

If the plan is approved with no changes, Radek skips the feedback file and
tells Tom directly.

### Step 5 — Tom implements

Radek invokes the build skill in Claude Code:

```
/tom-build 013b
```

Tom reads all feedback files, updates the plan to reflect what will actually
be built, creates a feature branch, implements, and runs `just check && just test`.

Tom reports completion with:
- Confirmation that `just check && just test` passed
- List of files created or modified
- Any deviations from the brief or feedback, with justification
- Any follow-up observations for the Architect

### Step 6 — Radek tests and merges

Radek tests the implementation manually. If it passes:

```bash
git checkout master
git merge feature/{slug}
git push origin master
git branch -d feature/{slug}
```

Tom never merges to master.

---

## Implementation Guide Audit Workflow

The implementation guide (`docs/implementation-guide.md`) documents platform
architecture principles and contracts. It drifts over time as tasks land.

### When to audit

After a cluster of related tasks merge — typically every 3-5 tasks or when a
significant new capability lands (tools integration, routing module, etc.).

### How to audit

Radek invokes the audit skill in Claude Code:

```
/tom-audit
```

Tom audits every section of the guide against the actual codebase, classifying
each item as CORRECT / STALE / MISSING / WRONG. The gap report is saved to:

```
tasks/plans/implementation-guide-audit-{date}.md
```

Tom commits the report directly to master — no feature branch needed.

### How to update the guide

Radek pastes Tom's audit report into this conversation. The Architect produces
an updated guide from the audit report plus any additional gaps identified
from task brief knowledge. The updated guide replaces `docs/implementation-guide.md`.

Tom commits it directly to master.

---

## Cluster Configuration

Each cluster is a self-contained experiment configuration in `clusters/`:

```
clusters/
├── default/          # loaded when no --cluster flag
├── research-desk/    # investment research pipeline
├── editorial/        # editorial pipeline
└── platform-architect/  # architect agent with RAG
```

Each cluster directory contains:

```
clusters/{name}/
├── agents.toml                      # agent wiring and routers
├── agents.mcp.json                  # MCP server definitions (committed)
├── agents.mcp.secrets.json          # API keys (gitignored)
├── agents.mcp.secrets.example.json  # key template (committed)
└── prompts/
    ├── {agent}.md                   # one file per agent
    └── routers/
        └── {router}.md              # one file per LLM router
```

### Starting a cluster

```bash
just start                    # default cluster
just start research-desk      # named cluster
```

### Creating a new cluster

```bash
mkdir -p clusters/my-cluster/prompts
# Create clusters/my-cluster/agents.toml
# Create clusters/my-cluster/agents.mcp.json
# Create clusters/my-cluster/prompts/{agent}.md for each agent
just start my-cluster
```

### Cluster name rules

Lowercase letters, digits, and hyphens only: `[a-z0-9-]+`

---

## File Locations Reference

| Artifact | Location |
|---|---|
| Task briefs | `tasks/{id}-{slug}.md` |
| Implementation plans | `tasks/plans/{id}-{slug}-plan.md` |
| Architect feedback | `tasks/feedback/{id}-*.md` |
| Implementation guide | `docs/implementation-guide.md` |
| Audit reports | `tasks/plans/implementation-guide-audit-{date}.md` |
| Cluster configs | `clusters/{name}/agents.toml` |
| Cluster prompts | `clusters/{name}/prompts/{agent}.md` |
| MCP secrets | `clusters/{name}/agents.mcp.secrets.json` (gitignored) |
| Skills | `.claude/skills/{skill}.md` |
| Log files | `logs/{timestamp}_{agent}_{cluster}.log` |
| Databases | `data/agents.db`, `data/costs.db`, `data/checkpoints.db` |
| Chroma knowledge base | `data/chroma/` |

---

## Key Commands

### Development

```bash
just check          # ruff lint + pyright — must pass before reporting done
just test           # unit tests — must pass before reporting done
just format         # auto-format with ruff
just clean          # remove build artefacts
```

### Running experiments

```bash
just start [cluster]              # start cluster
just stop                         # stop cluster
just send <agent> "<message>"     # send message to agent
just monitor [cluster]            # open TUI monitor
just chat <agent>                 # interactive chat with agent
just listen                       # poll for messages to human
```

### Inspection

```bash
just threads                      # browse all threads
just thread <id>                  # show full thread
just costs                        # cost summary by cluster
just costs-by-agent               # cost breakdown by agent
just costs-by-model               # cost breakdown by model
just runs                         # list recent log files
```

### Knowledge base

```bash
just ingest                       # index docs/ tasks/ clusters/ into Chroma
just ingest --reset               # wipe and rebuild Chroma collection
```

---

## Non-Negotiable Standards

These apply to every task, every commit, every file Tom touches:

- `core/` never imports from `transport/` or `cli/`
- `transport/` never imports from `core/` or `cli/`
- `rich` only in `cli/` and `scripts/` — never in `core/` or `transport/`
- No `aiosqlite` imports in `core/` — all DB access through transport methods
- No `--db` flag on scripts — always read DB path from `Settings()`
- `pyright` strict — no type errors, no untyped functions
- All new behaviour covered by unit tests
- `datetime.now(UTC)` — never `datetime.utcnow()`
- `pathlib.Path` everywhere — no string path concatenation
- Absolute imports only — no relative imports
- `git mv` for file moves — never `mv` + `git add`

### Verification after every task

```bash
grep -r "from multiagent.cli"       src/multiagent/core/
grep -r "from multiagent.cli"       src/multiagent/transport/
grep -r "from multiagent.transport" src/multiagent/core/
grep -r "from multiagent.core"      src/multiagent/transport/
grep -r "import rich"               src/multiagent/core/
grep -r "import rich"               src/multiagent/transport/
```

All must return empty.

---

## Roadmap

The current roadmap lives at `ROADMAP.md` in the repo root. Major milestones:

- ✅ Transport, agent core, CLI wiring
- ✅ Observability, checkpointing, cost tracking
- ✅ Multi-party messaging, routing module
- ✅ Terminal UI monitor
- ✅ Loop detection / termination
- ✅ MCP tool integration
- ✅ Named cluster configurations (013a)
- ✅ Cluster refactor — experiment → cluster (013b)
- 🔄 RAG via Chroma (platform-architect cluster running)
- ⬜ Fan-out routing (014)
- ⬜ Supervisor automation (017)
- ⬜ Context window management (015)
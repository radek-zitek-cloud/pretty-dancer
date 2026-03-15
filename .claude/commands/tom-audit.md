# Skill: /tom-audit

**Invocation:** `/tom-audit`  
**Purpose:** Audit `docs/implementation-guide.md` against the actual codebase
and produce a gap report for the architect to use when updating the guide.

---

## Instructions

### Step 1 — Verify master is clean

```bash
git status
git log --oneline -5
```

If uncommitted changes exist, commit and push them before auditing. The audit
should reflect the current merged state of the codebase, not work in progress.

### Step 2 — Read the current guide

Read `docs/implementation-guide.md` in full. Note the version number and
last updated date at the top.

### Step 3 — Audit each section

For every section in the guide, verify its accuracy against the actual
codebase. Use SERENA for symbol lookups, actual file contents for signatures
and schemas, and `git log --oneline -20` for recent changes.

For each item found, classify it as one of:

- **CORRECT** — matches the codebase exactly
- **STALE** — was correct at some point, now outdated (describe what changed)
- **MISSING** — exists in the codebase but not documented in the guide
- **WRONG** — never matched the codebase, or references something that does
  not exist

### Step 4 — Check these areas specifically

These are the most likely sources of drift based on recent tasks:

**Technology stack**
- LLM provider and library names
- All runtime and dev dependencies in `pyproject.toml`
- Any new dependencies added since the last guide update

**Repository structure**
- Every file and directory listed in the tree — does it actually exist?
- Every file and directory that exists — is it in the tree?
- New CLI commands, scripts, config files, data directories

**Configuration**
- Every `Settings` field in `settings.py` — name, type, default
- Every key in `.env.defaults`
- Fields documented in the guide that do not exist in the code
- Fields in the code not documented in the guide

**Module dependency rules**
- Run the verification commands from the guide — do they all return empty?

```bash
grep -r "from multiagent.cli"       src/multiagent/core/
grep -r "from multiagent.cli"       src/multiagent/transport/
grep -r "from multiagent.transport" src/multiagent/core/
grep -r "from multiagent.core"      src/multiagent/transport/
grep -r "import rich"               src/multiagent/core/
grep -r "import rich"               src/multiagent/transport/
```

**Agent contract**
- `LLMAgent.__init__` — exact current signature
- `LLMAgent.run()` — return type, parameters
- Graph node names
- Checkpointer and cost ledger lifecycle patterns
- Thread ID namespacing approach (checkpoint isolation)

**Routing contract**
- `AgentConfig` fields — including `tools`
- `RouterConfig` fields
- `agents.toml` schema — all supported keys
- Router types and their configuration

**Transport contract**
- `Message` dataclass — all fields, types, who sets each
- `Transport` ABC — method signatures
- `human` as a valid recipient

**Testing strategy**
- Shared fixtures in `conftest.py` — names and what they provide
- Mock patterns — what is mocked and how
- Test file structure under `tests/`

**Task runner**
- Every `just` target in the actual `justfile`
- Targets documented in the guide that do not exist
- Targets in the justfile not documented in the guide

**Git workflow**
- Current merge practice (ff-only vs merge commits)
- Branch naming in practice
- Worktree usage — current practice vs what guide says

**Dependency reference**
- Cross-check every package in the guide against actual `pyproject.toml`
- Runtime vs dev classification — is it correct?

**New sections needed**
- MCP tool integration (`agents.mcp.json`, `agents.mcp.secrets.json`,
  `tool_configs` on `LLMAgent`, ReAct graph pattern)
- Named experiment configurations (`agents.{experiment}.toml`,
  prompt subfolders, secrets fallback)
- Anything added since the last guide update with no corresponding
  documentation

### Step 5 — Produce the gap report

Save the report to:

```
tasks/plans/implementation-guide-audit-{date}.md
```

where `{date}` is today's date as `YYYY-MM-DD`.

Format the report as:

```markdown
# Implementation Guide Audit — Gap Report

**Audited:** docs/implementation-guide.md v{version}
**Against:** Codebase at commit {git-sha}
**Date:** {date}
**Auditor:** Tom (implementer)

---

## Section: {Section Name}

| Item | Status | Detail |
|------|--------|--------|
| ... | CORRECT / STALE / MISSING / WRONG | ... |

---

## Summary Statistics

| Status | Count |
|--------|-------|
| CORRECT | n |
| STALE | n |
| MISSING | n |
| WRONG | n |

## Top Priority Updates

[List the 5-10 most important items for the architect to address first]
```

Be specific. "Constructor signature changed" is not useful.
"Guide shows `LLMAgent(name, system_prompt, settings)` — actual is
`LLMAgent(name, settings, checkpointer, cost_ledger, router, tool_configs)`"
is useful.

### Step 6 — Commit the report

```bash
git add tasks/plans/
git commit -m "docs(tasks): add implementation guide audit {date}"
git push origin master
```

Commit directly to master — this is a read-only audit, no feature branch
needed.

### Step 7 — Report

Tell the architect:
- The audit is complete and committed
- The file path of the report
- Your top 3 most critical findings

Do not update `docs/implementation-guide.md` yourself. The architect produces
the updated guide from the audit report.
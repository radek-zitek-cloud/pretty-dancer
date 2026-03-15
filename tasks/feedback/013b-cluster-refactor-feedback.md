The plan is thorough and Tom has done good codebase inspection — several deviations from the brief are correct. Four points before he proceeds:

---

**1. D2 — Router prompt paths: approved, but needs explicit handling**

Tom correctly identified that `prompt = "prompts/research-desk/routers/research_supervisor.md"` in the TOML files uses repo-root-relative paths. After migration these must become `clusters/research-desk/prompts/routers/research_supervisor.md`. Tom should add a explicit step to his implementation order: after moving the TOML files, grep for all `prompt =` fields and update them. Easy to miss in a large refactor.

```bash
grep -r "^prompt = " clusters/
```

All results must point to paths that exist after the migration.

---

**2. D1 — Default cluster agents.toml: approved**

Creating a minimal alfa/beta default and moving the other prompts to `clusters/default/prompts/` without wiring them is correct. The editorial, support, and debate prompts are orphaned configuration that was never properly clustered — they belong in `clusters/default/prompts/` as assets but should not be wired into `agents.toml` without deliberate configuration. Tom's instinct is right.

---

**3. D3 — Editorial cluster omission: approved**

No `agents.mcp.editorial.json` exists, so creating a half-formed cluster directory would be worse than leaving it as prompts-only assets in default. Approved.

---

**4. Local secrets file migration — add a note to the report**

Tom correctly notes he cannot `git mv` a gitignored file. When reporting completion, he should explicitly tell Radek: "Move your local `agents.mcp.secrets.json` from the repo root to `clusters/default/agents.mcp.secrets.json` manually after merging." This is the one manual step the user must perform that the code change cannot handle.

---

**Everything else approved.** Phase ordering is correct — file moves first before code changes, which is essential for git history. The `COST_DB_PATH` addition to `.env.defaults` is a good catch. The test fixture update strategy is sound. Tom can proceed.
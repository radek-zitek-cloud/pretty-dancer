The plan is clean and the design decisions are sound. One point to address before Tom proceeds:

---

**D3 — Skipping the audit is not approved**

The brief explicitly sequences `/tom-audit` before implementation because 013c's scope is intentionally open — the audit may surface additional small findings to fold in. Tom's reasoning ("I already know the codebase state from implementing 013b") is understandable but misses the point. The audit is not just about what Tom knows — it is a systematic cross-check that catches things that slip through during implementation, and it produces a committed record for the architect to use when updating the guide.

The implementation guide update in Phase 4 is particularly at risk without the audit. Tom is planning to update sections 3, 5, 6, 7, 9, 14, 16 based on what he knows changed in 013a/013b. But there may be drift from earlier tasks (013, 011b, 010, TUI) that has not been captured yet. The audit catches that. Updating the guide without it means we are still partially stale.

**Instruction to Tom:** Run `/tom-audit` as Step 0 before writing any code. Commit the audit report to master first, then proceed with the plan. The Phase 4 guide update should be informed by the full audit report, not just the known 013a/013b changes. This adds perhaps two hours but produces a guide that is genuinely current rather than partially updated.

---

**Everything else approved.** D2 (re-export from `transport/base.py`) is the right call — minimal diff, backward compatible. D4 (subprocess grep for boundary tests) is correct. The `models.py` importing nothing internally is tighter than the brief required and that is fine.

Send Tom back with the single correction: run the audit first, commit the report, then implement.
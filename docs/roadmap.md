# Multiagent Platform — Roadmap

**Status:** Living document  
**Framing:** Personal LLM experimentation platform  
**Last Updated:** 2026-03-14

---

## Completed

|Task|Description|
|---|---|
|~~007~~|`send --thread-id` — thread continuity for debate use case|
|~~008~~|`multiagent start` — launch full cluster from `agents.toml` in one command|
|~~009~~|Cost tracking — per-call token/cost ledger, surfaced in all inspection tools|
|~~010~~|Loop detection / termination — halt on consecutive self-sends; `max_messages_per_thread`|
|~~011a~~|Multi-party messaging — `from_agent`/`to_agent`, `human` as recipient, `listen` and `chat` CLI|
|~~011b~~|Routing module — keyword and LLM classifier routers, `[routers.*]` in `agents.toml`|
|~~TUI~~|Terminal UI — `just monitor` live dashboard: agents, threads, cost, inline send|
|~~Guide v2.0~~|Implementation guide rewrite — principles and contracts only|

---

## Active

| Task | Description                                                                         | Status           |
| ---- | ----------------------------------------------------------------------------------- | ---------------- |
| 013  | MCP tool integration — any agent can use MCP servers as tools via `agents.mcp.json` | Tom implementing |

---

## Roadmap

### Tier 1 — Capability Expansion

| Task          | Description                                                                                                                                                         | Rationale                                                                                                                           |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| ~~013~~       | ~~**MCP tool integration** — per-agent tools via `agents.mcp.json` + `agents.mcp.secrets.json`; any MCP server usable as a LangGraph tool node~~                    | ~~Transforms agents from talkers to actors; investment research desk with Exa web search is the validation scenario~~               |
| ~~RAG~~       | ~~**Chroma RAG** — `scripts/ingest_docs.py` indexes project docs into local Chroma; architect agent searches via `chroma-mcp` tool; `just ingest` justfile target~~ | ~~Folds into 013 as configuration once tool layer exists; no new architecture needed~~                                              |
| ~~013a and 013b~~ | ~~**Cluster Config**<br>named clusters, remove experiments notion~~                                                                                                     | ~~Multiple test scenarios, cleanup~~                                                                                                    |
| Guide v2.1    | Implementation guide update — tool layer, MCP config, ReAct graph pattern                                                                                           | After 013 + RAG merge                                                                                                               |
| 014           | **Fan-out routing** — `to_agents: list[str]` in transport; agent output produces multiple simultaneous messages                                                     | Enables acknowledge-human AND route-to-next in same step; enables parallel worker invocations; currently requires prompt workaround |

### Tier 2 — Orchestration

| Task | Description                                                                                                                                                      | Rationale                                                                                                                                                                           |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 012  | **Supervisor pattern** — transport-native hub-and-spoke; supervisor agent with LLM router orchestrating specialist workers; all workers route back to supervisor | Validated conceptually via investment research desk experiment; requires no new code — configuration and prompting exercise; defer formal task until a concrete scenario demands it |
| 017  | **Architect/implementer automation** — supervisor orchestrating the full design→plan→implement→review loop with Claude Code tool integration                     | Long-term vision; requires 012 validated + 013 (tools) + filesystem/shell tool access                                                                                               |
**After 017 (architect/implementer automation)** — if that ever lands, the platform will have transformed enough to warrant a full v3.0 rewrite rather than an incremental update.
### Tier 3 — Platform Maturity

|Task|Description|Rationale|
|---|---|---|
|015|**Context window management** — summarisation node for long threads; automatic when approaching model context limit|Not hitting limits yet; supervisor token accumulation will eventually make this necessary|
|016|**System prompt enrichment RAG** — runner injects retrieved context into every agent invocation before the agent sees the message; agent-agnostic|More powerful than tool-based RAG for always-on context; requires retriever component in AgentRunner; distinct from tool-based RAG|
|018|**Web UI** — thread browser, live message stream, chat interface in browser|Only if TUI proves insufficient; UI building is painful, defer until need is unambiguous|

---

## Deferred / Under Discussion

|Item|Note|
|---|---|
|Per-agent log files in `start` mode|Currently one cluster log; revisit if debugging multi-agent runs becomes painful|
|Hot reload of `agents.toml`|Nice to have; not blocking anything|
|Router chaining|Router output feeds another router; not needed yet|
|`system_prompt_override` on Message|Supervisor sends different personas to same worker per invocation; achievable via message body today; revisit when prompt engineering proves insufficient|
|Named cluster configurations|Multiple `agents.toml` + `agents.mcp.json` sets for different experiment topologies; natural next step after MCP tools are validated|
|Deployment infrastructure|Out of scope until there are users other than Radek|
|Auth / security boundaries|Same — platform framing means single-user for now|

---

## Principles

- **Every task should increase experimental capability.** If a feature does not make it easier to run, observe, or understand an experiment, it is not ready for the roadmap.
- **Observability before complexity.** Do not add architectural layers without first having the visibility to understand what is happening.
- **Terminal-first.** The platform lives in the terminal. Browser UI is a last resort, not a first instinct.
- **Validate before formalising.** The supervisor pattern was validated via experiment before a task brief was written. Prefer running experiments over writing briefs for uncertain capabilities.
- **Tom merges nothing.** Radek owns master. Every task ends with a branch and a report.
You are Tom, the implementer for the multiagent PoC project. Your plan for Task v013a-experiment-configs has been reviewed by the architect. Address the feedback below and proceed with full implementation.

## Tools

### SERENA MCP — semantic code navigation
Use SERENA for all code understanding tasks: symbol search, find references,
go to definition, list symbols in a file. This is your primary tool for
navigating the codebase. Prefer SERENA over grep for anything structural.
Use grep only for string literals and config file content SERENA cannot reach.

### SQLite MCP — database inspection
Three servers are available for direct database inspection during development
and debugging:

| Server | Database | Contents |
|---|---|---|
| `sqlite-transport` | `data/agents.db` | Messages, threads, from/to routing |
| `sqlite-costs` | `data/costs.db` | Per-call token counts and cost |
| `sqlite-checkpoints` | `data/checkpoints.db` | LangGraph checkpoint state |

Use these to inspect actual message flow, verify routing decisions, and debug
thread behaviour without writing throwaway scripts. Do not use them as a
substitute for writing proper tests.

### Context7 MCP — third-party library documentation
Use Context7 to look up current API documentation for any third-party library
before relying on training data. Training data may be stale — especially for
LangGraph, pydantic-settings, aiosqlite, and structlog APIs. When in doubt,
look it up.

Priority order for any library question:
1. Context7 (current docs)
2. Codebase (how it is already used here)
3. Training data (last resort)

## Architect feedback

Strong plan. Tom's Context7 research surfaced two things the brief missed — the transport: "stdio" requirement and the correct tools_condition pattern from langgraph.prebuilt. Both are real corrections. Four points before he proceeds:

1. Tool test coverage — push back on the hedge
Tom says full tool execution tests are "complex and brittle" and he'll rely on the smoke test. This is not acceptable for a feature this architecturally significant. The mock pattern is:
pythonwith patch("multiagent.core.agent.MultiServerMCPClient") as mock_client:
    mock_client.return_value.__aenter__.return_value.get_tools.return_value = [mock_tool]
    # run agent, assert tool was called
```

It is not as complex as Tom implies. Require him to write at minimum:
- `test_tool_call_invoked_when_llm_requests_tool` — LLM returns tool call, tool executes, LLM incorporates result
- `test_tools_and_routing_compose_correctly` — both active, tool loop runs before routing

These are the two tests in the brief he dropped. They must be in the implementation.

---

**2. The `should_continue` function — clarify the routing composition**

Tom's graph diagram for tools + router is correct:
```
call_llm → should_continue?
             tool_calls → tools → call_llm
             no tools   → route → END
But tools_condition from langgraph.prebuilt returns "tools" or "__end__" — it does not know about the "route" node. Tom needs a custom should_continue function when both are active. His plan acknowledges this implicitly but does not state the implementation explicitly. Require him to be specific: custom function replaces tools_condition when router is present, calls tools_condition logic internally but returns "route" instead of "__end__".

3. Decision 4 — server names as keys: approved
Using actual server names ("exa", "filesystem") over f"server_{i}" is correct. Better debuggability, cleaner tool names surfaced to the LLM.

4. Decision 1, 3, 4 on conditional config and validation placement: all approved
Conditional ConfigurationError only when tools are actually needed is the right call. Validation in CLI where both configs are available is architecturally correct. Default transport: "stdio" for command-based servers is the right default.

Send Tom back with two corrections: add the two dropped agent tests, and be explicit about the custom should_continue function when tools and router are both active. Everything else is approved.

## Instructions

1. Read the feedback carefully before touching any code
2. If any feedback item is unclear, state your interpretation explicitly before
   proceeding — do not guess silently
3. Create a feature branch:

```bash
git checkout master
git pull origin master
git checkout -b feature/<<<BRANCH_SLUG>>>
```

4. Update `tasks/plans/013a-experiment-configs-plan.md` to reflect any changes introduced
   by the feedback — the file should represent the plan as actually implemented,
   not the original draft
5. Implement the full task, incorporating all feedback
6. Commit at each meaningful step using Conventional Commits — include the
   updated plan file in the first commit
7. When complete, run:

```bash
just check && just test
```

Both must pass with zero errors before you consider the task done.

8. Report back with:
   - Confirmation that `just check && just test` passed
   - List of files created or modified
   - Any deviations from the brief or feedback, with justification
   - Any follow-up observations for the architect

Do not merge to master — that step is Radek's.
# Plan: Task 013 — MCP Tool Integration

**Task:** `tasks/013-mcp-tools.md`
**Author:** Tom (implementer)
**Date:** 2026-03-14
**Status:** APPROVED — implementing

**Architect feedback incorporated:**
1. Two dropped tool execution tests restored: `test_tool_call_invoked_when_llm_requests_tool`
   and `test_tools_and_routing_compose_correctly`. Mock pattern via
   `patch("multiagent.core.agent.MultiServerMCPClient")`.
2. Custom `should_continue` function explicit: when tools + router are both
   active, returns `"tools"` if tool_calls pending, `"route"` (not `END`) when
   done. Replaces `tools_condition` from prebuilt.
**Base branch:** `master` @ `4ffccb6`
**Feature branch:** `feature/mcp-tools`

---

## Design Decisions and Ambiguities

### 1. Graph rebuild on every tool-using run() call

The brief correctly identifies that `MultiServerMCPClient` is an async context
manager — tools are only available while the client is alive. This means for
tool-using agents, the graph must be built fresh on each `run()` call (inside
the `async with` block). For agents without tools, the pre-built graph from
`__init__` is reused (current behaviour, unchanged).

**Cost:** Graph compilation per call. Acceptable for a PoC — the MCP server
startup and LLM API calls dominate latency.

### 2. tools_condition from langgraph.prebuilt

Context7 confirms the pattern:
```python
from langgraph.prebuilt import ToolNode, tools_condition

builder.add_conditional_edges("call_llm", tools_condition)
builder.add_edge("tools", "call_llm")
```

`tools_condition` checks `state["messages"][-1].tool_calls` and returns either
`"tools"` or `"__end__"`. When a router is also present, I need a custom
`should_continue` function that routes to `"tools"` if tool calls are pending,
or to `"route"` (if router exists) / `END` (if no router) when done.

### 3. Routing + tools composition

Both can be active on the same agent. The graph structure:

**Tools only (no router):**
```
START → call_llm → should_continue?
                     tool_calls → tools → call_llm (loop)
                     no tools   → END
```

**Tools + router:**
```
START → call_llm → should_continue?
                     tool_calls → tools → call_llm (loop)
                     no tools   → route → END
```

**Router only (no tools):** unchanged from current:
```
START → llm → route → END
```

**Neither:** unchanged:
```
START → llm → END
```

The `should_continue` function is the decision point. When tools are present,
it replaces the direct edge from `llm` to `route`/`END`.

### 4. MCP server naming in MultiServerMCPClient

The brief uses `f"server_{i}"` as keys. I'll use the actual server names from
`agents.mcp.json` (e.g. `"exa"`, `"filesystem"`) since that's what the user
configured and it produces more readable tool names.

### 5. Validation: tool names vs MCP config

The brief says validate at startup that agent tool names exist in MCP config.
This validation belongs in the CLI layer (`run.py`, `start.py`) where both
`AgentsConfig` and `MCPConfig` are available — not in `load_agents_config()`
which doesn't have access to the MCP config.

### 6. MCP config loading when no agents use tools

If no agent references tools, `agents.mcp.json` absence should be silent.
`load_mcp_config` will return empty `MCPConfig` when the base config file
doesn't exist. The CLI only raises if an agent references a tool that doesn't
exist in the (possibly empty) MCP config.

**Correction to brief:** The brief says "`ConfigurationError` if absent" for
`agents.mcp.json`. I'll make it conditional — only error if an agent actually
needs tools and the config is missing. An empty file or absent file with no
tool-using agents is fine.

### 7. `transport` field in MultiServerMCPClient

Context7 shows the server config dict requires a `transport` field. For stdio
servers (our use case), this is `"stdio"`. The brief's `agents.mcp.json`
doesn't include it. I'll add `transport: "stdio"` as a default when `command`
is present, and allow explicit override in the config file for future HTTP
transport support.

### 8. Cost tracking for tool round-trips

Each `call_llm` node invocation (including tool round-trip calls) goes through
the same `call_llm` function which already records costs. So tool round-trips
are automatically cost-tracked. No additional cost logic needed.

### 9. AgentState compatibility

The current `AgentState` extends `MessagesState` and adds `next_agent: str | None`.
`ToolNode` from `langgraph.prebuilt` works with `MessagesState` — it reads
tool calls from the last message and appends `ToolMessage` results. This is
compatible with `AgentState` since it inherits `messages`.

---

## Files to Create or Modify

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Modify | Add `langchain-mcp-adapters` dependency |
| `uv.lock` | Auto-updated | Via `uv add langchain-mcp-adapters` |
| `agents.mcp.json` | Create | MCP server definitions (committed) |
| `agents.mcp.secrets.example.json` | Create | Credential template (committed) |
| `.gitignore` | Modify | Add `agents.mcp.secrets.json` |
| `.env.defaults` | Modify | Add `MCP_CONFIG_PATH` and `MCP_SECRETS_PATH` |
| `src/multiagent/config/settings.py` | Modify | Add `mcp_config_path` and `mcp_secrets_path` fields |
| `tests/conftest.py` | Modify | Add both fields to `test_settings` fixture |
| `src/multiagent/config/mcp.py` | Create | `MCPServerConfig`, `MCPConfig`, `load_mcp_config()` |
| `src/multiagent/config/__init__.py` | Modify | Export new MCP config symbols |
| `src/multiagent/config/agents.py` | Modify | Add `tools` field to `AgentConfig` |
| `src/multiagent/core/agent.py` | Modify | Add `tool_configs` param, tool-aware `_build_graph()`, MCP lifecycle in `run()` |
| `src/multiagent/cli/run.py` | Modify | Load MCPConfig, resolve tool configs, pass to LLMAgent |
| `src/multiagent/cli/start.py` | Modify | Load MCPConfig, resolve tool configs, pass to LLMAgent |
| `tests/unit/config/test_mcp.py` | Create | 6 tests for MCP config loading |
| `tests/unit/config/test_agents.py` | Modify | 2 tests for tools field parsing |
| `tests/unit/core/test_agent.py` | Modify | 2-4 tests for tool-aware graph building |
| `tests/fixtures/agents.mcp.json` | Create | Test MCP config fixture |
| `tests/fixtures/agents.mcp.secrets.json` | Create | Test MCP secrets fixture |

---

## Implementation Order

### Step 1: Dependency and config files
- `uv add langchain-mcp-adapters`
- Create `agents.mcp.json`, `agents.mcp.secrets.example.json`
- Add to `.gitignore`
- Add settings fields, `.env.defaults`, `test_settings` fixture

Gate: `just check && just test`

### Step 2: MCP config loader (`config/mcp.py`)
- Create `MCPServerConfig`, `MCPConfig` dataclasses
- Implement `load_mcp_config()` with merge logic
- Create test fixtures
- Write 6 tests in `test_mcp.py`
- Export from `config/__init__.py`

Gate: `just check && just test`

### Step 3: AgentConfig extension
- Add `tools: list[str]` field to `AgentConfig`
- Update `load_agents_config()` to parse `tools`
- Write 2 tests in `test_agents.py`
- Update test fixture `agents.toml` if needed

Gate: `just check && just test`

### Step 4: LLMAgent tool integration
- Add `tool_configs` parameter to constructor
- Implement tool-aware `_build_graph(tools=...)` with ReAct pattern
- Modify `run()` to manage MCP client lifecycle for tool-using agents
- Extract `_invoke_graph()` helper for shared invocation logic
- Write tests (mock `MultiServerMCPClient` and tool execution)

Gate: `just check && just test`

### Step 5: CLI wiring
- Modify `run.py` and `start.py` to load MCPConfig
- Resolve per-agent tool configs
- Validate tool names against MCP config
- Pass `tool_configs` to LLMAgent constructor

Gate: `just check && just test`

### Step 6: Module boundary verification
```bash
grep -r "from multiagent.core" src/multiagent/config/mcp.py
grep -r "from multiagent.transport" src/multiagent/config/mcp.py
```

### Step 7: Manual smoke test with Exa

---

## Test Plan

| Test file | Test name | Verifies |
|-----------|-----------|----------|
| `test_mcp.py` | `test_loads_base_config_without_secrets` | Base-only loading works |
| | `test_merges_secrets_into_base_config` | Env merge logic |
| | `test_secrets_file_absent_is_not_an_error` | Graceful absent secrets |
| | `test_raises_when_base_config_absent_and_tools_needed` | Fail-fast on missing config |
| | `test_secrets_override_base_env_keys` | Override precedence |
| | `test_unknown_server_in_secrets_is_ignored` | Robustness |
| `test_agents.py` | `test_loads_tools_field_from_toml` | Field parsing |
| | `test_tools_defaults_to_empty_list_when_absent` | Default value |
| `test_agent.py` | `test_graph_without_tools_unchanged` | Backward compat |
| | `test_tool_configs_stored_on_agent` | Constructor wiring |
| | `test_tool_call_invoked_when_llm_requests_tool` | Full tool round-trip |
| | `test_tools_and_routing_compose_correctly` | Tool loop before routing |

Total: 12+ new tests.

---

## What I Would Do Differently From the Brief

### 1. Conditional MCP config requirement
The brief says `agents.mcp.json` is required and raises `ConfigurationError` if
absent. I'll make it conditional — only error when an agent actually uses tools.
A cluster with no tool-using agents shouldn't need an MCP config file.

### 2. Server names as MultiServerMCPClient keys
The brief uses `f"server_{i}"`. I'll use the actual server names from
`agents.mcp.json` for readability and debuggability.

### 3. Default `transport: "stdio"` for command-based servers
The brief's JSON doesn't include `transport`. Context7 shows it's required.
I'll default to `"stdio"` when `command` is present in the server config.

### 4. Tool name validation in CLI, not config loader
The brief places validation in `load_agents_config()`, but that function doesn't
have access to `MCPConfig`. Validation happens in `run.py`/`start.py` where
both configs are available.

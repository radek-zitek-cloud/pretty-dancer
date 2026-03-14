# Task 013 — MCP Tool Integration

**File:** `tasks/013-mcp-tools.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-14  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 011b (routing) complete and merged to master

---

## Objective

Give any agent the ability to use MCP servers as tools. An agent with tools
configured can search the web, read files, query databases, or call any other
MCP-compatible service during its LangGraph graph execution before producing
its final response.

After this task:
- `agents.mcp.json` at the repo root defines available MCP servers
- `agents.mcp.secrets.json` (gitignored) provides server credentials
- `agents.toml` per-agent `tools = [...]` field lists which servers each agent
  may use
- Agents with tools configured use the ReAct pattern — they can invoke tools
  in a loop until satisfied, then produce their final response
- Agents without tools are completely unchanged — full backward compatibility

The investment research desk with Exa web search is the primary validation
scenario.

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — all standards, module rules, coding
  conventions
- `tasks/003-agent-core.md` — original `LLMAgent._build_graph()` this task
  extends
- `tasks/011b-routing.md` — current graph structure (routing node) this task
  must compose with
- **Context7: `langchain-mcp-adapters`** — look up `MultiServerMCPClient`
  current API before writing any tool integration code. Do not rely on training
  data for this library.
- **Context7: LangGraph `ToolNode`** — look up current `create_react_agent`
  or manual `ToolNode` + conditional edge patterns.

---

## Git

Work on branch `feature/mcp-tools` created from `master`.

```bash
git checkout master
git pull origin master
git checkout -b feature/mcp-tools
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
feat(core): add MCP tool integration via agents.mcp.json configuration
```

---

## New Dependencies

```toml
# pyproject.toml — runtime dependencies
"langchain-mcp-adapters>=0.1"
```

Run `uv add langchain-mcp-adapters` to add and update `uv.lock`.

Verify with Context7 that this is the correct package name and minimum version
before adding.

---

## New Configuration Files

### `agents.mcp.json` (committed)

Defines MCP server commands and arguments. No secrets. Committed to git.

```json
{
  "mcpServers": {
    "exa": {
      "command": "npx",
      "args": ["-y", "exa-mcp-server"]
    },
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "./data"
      ]
    }
  }
}
```

### `agents.mcp.secrets.json` (gitignored)

Provides environment variables for MCP servers that require credentials.

```json
{
  "mcpServers": {
    "exa": {
      "env": {
        "EXA_API_KEY": "your-key-here"
      }
    }
  }
}
```

### `agents.mcp.secrets.example.json` (committed)

Documents required keys with empty values. Serves as onboarding reference.

```json
{
  "mcpServers": {
    "exa": {
      "env": {
        "EXA_API_KEY": ""
      }
    },
    "filesystem": {
      "env": {}
    }
  }
}
```

### `.gitignore` addition

```
# MCP secrets
agents.mcp.secrets.json
```

---

## New Settings Field

```python
mcp_config_path: Path = Field(
    Path("agents.mcp.json"),
    description="Path to MCP server configuration file.",
)

mcp_secrets_path: Path = Field(
    Path("agents.mcp.secrets.json"),
    description="Path to MCP server secrets file (gitignored).",
)
```

Add both to `settings.py` and `.env.defaults`.

---

## `agents.toml` Extension

Add optional `tools` field to agent sections:

```toml
[agents.researcher]
next_agent = "supervisor"
tools = ["exa"]             # list of server names from agents.mcp.json

[agents.supervisor]
router = "research_supervisor"
# no tools field = no tools, graph unchanged

[agents.fundamentals]
next_agent = "supervisor"
tools = ["exa", "filesystem"]
```

`tools` is optional. Absent or empty list means no tools. Agent graph is
unchanged from current behaviour.

---

## `src/multiagent/config/agents.py` — Extension

`AgentConfig` gains a new field:

```python
@dataclass(frozen=True)
class AgentConfig:
    next_agent: str | None = None
    router: str | None = None
    tools: list[str] = field(default_factory=list)
```

`load_agents_config()` parses `tools` from each `[agents.*]` section.

Validation: if any tool name in `tools` is not a key in `agents.mcp.json`,
raise `ConfigurationError` at startup. Fail fast — do not discover missing
tool configs at runtime.

---

## `src/multiagent/config/mcp.py` — New File

Responsible for loading and merging `agents.mcp.json` and
`agents.mcp.secrets.json`.

```python
@dataclass(frozen=True)
class MCPServerConfig:
    """Configuration for a single MCP server."""
    command: str
    args: list[str]
    env: dict[str, str]      # merged from base + secrets

@dataclass(frozen=True)  
class MCPConfig:
    """Complete MCP configuration for the cluster."""
    servers: dict[str, MCPServerConfig]

def load_mcp_config(
    config_path: Path,
    secrets_path: Path,
) -> MCPConfig:
    """Load and merge MCP server config and secrets.

    Loads agents.mcp.json for server definitions and merges
    agents.mcp.secrets.json for credentials. Secrets file is
    optional — if absent, servers are loaded without env overrides.

    Args:
        config_path: Path to agents.mcp.json
        secrets_path: Path to agents.mcp.secrets.json (may not exist)

    Returns:
        Merged MCPConfig with all server definitions and credentials.

    Raises:
        ConfigurationError: If agents.mcp.json is missing or malformed.
    """
```

**Merge logic:**
1. Load `agents.mcp.json` — required, `ConfigurationError` if absent
2. Load `agents.mcp.secrets.json` — optional, silently skip if absent
3. For each server in secrets, merge `env` dict into the base config
4. Base `env` keys are preserved; secrets `env` keys override/extend

`MCPConfig` is not a `Settings` subclass — it is loaded separately and passed
to `LLMAgent` alongside `Settings`. This keeps tool configuration orthogonal
to application configuration.

**Module boundary:** `config/mcp.py` may not import from `core/` or
`transport/`. It receives paths as parameters.

---

## `src/multiagent/core/agent.py` — Modifications

### Constructor

```python
def __init__(
    self,
    name: str,
    settings: Settings,
    checkpointer: BaseCheckpointSaver,
    cost_ledger: CostLedger,
    router: Router | None = None,
    tool_configs: list[MCPServerConfig] | None = None,
) -> None:
```

`tool_configs` is the list of `MCPServerConfig` instances for the servers this
agent is allowed to use. `None` or empty list means no tools.

### `run()` — async context manager for MCP client

`MultiServerMCPClient` is an async context manager — it must be entered before
tools are available. This means `run()` must open the MCP client, build the
tool-aware graph, invoke it, and close the client.

**Key design constraint:** The graph cannot be built once in `__init__` when
tools are involved — `MultiServerMCPClient` must be active when tools are
fetched and bound. The graph is built fresh on each `run()` call when tools
are configured, or once in `__init__` and reused when no tools are configured.

```python
async def run(self, input_text: str, thread_id: str) -> RunResult:
    if self._tool_configs:
        # Build graph fresh each call with active MCP client
        mcp_server_map = {
            f"server_{i}": {
                "command": cfg.command,
                "args": cfg.args,
                "env": cfg.env,
            }
            for i, cfg in enumerate(self._tool_configs)
        }
        async with MultiServerMCPClient(mcp_server_map) as client:
            tools = await client.get_tools()
            graph = self._build_graph(tools=tools)
            return await self._invoke_graph(graph, input_text, thread_id)
    else:
        # Use pre-built graph (current behaviour, unchanged)
        return await self._invoke_graph(self._graph, input_text, thread_id)
```

### `_build_graph()` — tool-aware variant

When `tools` is provided, the graph uses the ReAct pattern:

```
call_llm → should_continue?
               tools pending → tool_node → call_llm (loop)
               no tools      → route_node (if router) → END
                              → END (if no router)
```

```python
def _build_graph(
    self,
    tools: list | None = None,
) -> CompiledGraph:
```

When `tools` is not None:
- Bind tools to the LLM: `llm_with_tools = self._llm.bind_tools(tools)`
- Add `ToolNode` to the graph
- Add conditional edge from `call_llm`: if tool calls present → `tools`,
  else → `route` (if router exists) or `END`
- Add edge from `tools` back to `call_llm`

When `tools` is None: existing behaviour unchanged.

**Verify with Context7:** the exact `ToolNode` import path, `bind_tools()`
signature, and conditional edge pattern for tool use in LangGraph. The
`should_continue` function pattern may differ from what is in training data.

### Routing + tools composition

Both routing and tools can be active on the same agent. The graph handles
tools first (ReAct loop), then routing after the final LLM response. This
is the correct order — tools gather information, routing decides destination.

---

## CLI Lifecycle — `run.py` and `start.py`

Both files must load `MCPConfig` and resolve per-agent tool configs before
constructing `LLMAgent`:

```python
from multiagent.config.mcp import load_mcp_config, MCPConfig

mcp_config = load_mcp_config(
    settings.mcp_config_path,
    settings.mcp_secrets_path,
)

# Per agent:
tool_configs = [
    mcp_config.servers[tool_name]
    for tool_name in agent_config.tools
]

agent = LLMAgent(
    name,
    settings,
    checkpointer,
    cost_ledger,
    router=router,
    tool_configs=tool_configs or None,
)
```

If `agents.mcp.json` does not exist and no agent uses tools, this is fine —
`load_mcp_config` returns an empty `MCPConfig`. If any agent uses tools but
`agents.mcp.json` is absent, raise `ConfigurationError` at startup.

---

## `src/multiagent/config/__init__.py` — Exports

Add `MCPServerConfig`, `MCPConfig`, `load_mcp_config` to exports.

---

## Test Requirements

### `tests/unit/config/test_mcp.py` — New File

```
TestLoadMCPConfig
    test_loads_base_config_without_secrets
        — agents.mcp.json present, no secrets file
        — assert servers loaded with empty env

    test_merges_secrets_into_base_config
        — both files present
        — assert env from secrets merged into server config

    test_secrets_file_absent_is_not_an_error
        — only agents.mcp.json present
        — assert loads successfully

    test_raises_when_base_config_absent
        — neither file present
        — assert ConfigurationError

    test_secrets_override_base_env_keys
        — base has env key, secrets has same key with different value
        — assert secrets value wins

    test_unknown_server_in_secrets_is_ignored
        — secrets references server not in base config
        — assert no error, unknown server silently ignored
```

### `tests/unit/config/test_agents.py` — Modifications

```
test_loads_tools_field_from_toml
    — agent with tools = ["exa", "filesystem"]
    — assert AgentConfig.tools == ["exa", "filesystem"]

test_tools_defaults_to_empty_list_when_absent
    — agent with no tools field
    — assert AgentConfig.tools == []
```

### `tests/unit/core/test_agent.py` — Modifications

```
test_graph_built_without_tools_when_tool_configs_none
    — LLMAgent with tool_configs=None
    — assert graph does not contain ToolNode
    — assert pre-built graph is reused across run() calls

test_graph_built_with_tools_when_tool_configs_provided
    — LLMAgent with mock tool_configs
    — mock MultiServerMCPClient to return mock tools
    — assert LLM is called with bind_tools()
    — assert ToolNode present in graph

test_tool_call_invoked_when_llm_requests_tool
    — mock LLM first response: tool call request
    — mock tool execution: returns result
    — mock LLM second response: final answer using tool result
    — assert final RunResult.response contains tool-informed answer

test_tools_and_routing_compose_correctly
    — agent with both tool_configs and router
    — assert tool loop runs before routing decision
```

### `tests/unit/config/test_agents.py` — validation test

```
test_raises_configuration_error_when_tool_name_not_in_mcp_config
    — agent references tool "unknown_server"
    — MCPConfig has no such server
    — assert ConfigurationError at load time
```

---

## `.env.defaults` Additions

```bash
# --- MCP TOOLS ---
MCP_CONFIG_PATH=agents.mcp.json
MCP_SECRETS_PATH=agents.mcp.secrets.json
```

---

## Implementation Order

1. Add `langchain-mcp-adapters` via `uv add langchain-mcp-adapters`
2. Create `agents.mcp.json`, `agents.mcp.secrets.example.json`
3. Add `agents.mcp.secrets.json` to `.gitignore`
4. Add settings fields to `settings.py` and `.env.defaults`
5. Create `src/multiagent/config/mcp.py` — `MCPServerConfig`, `MCPConfig`,
   `load_mcp_config()`
6. Write `tests/unit/config/test_mcp.py` — TDD red phase (6 tests)
7. Green phase — config tests pass
8. Extend `AgentConfig` in `config/agents.py` — add `tools` field
9. Add validation in `load_agents_config()` — unknown tool names raise error
10. Update `tests/unit/config/test_agents.py` — 3 new tests
11. Modify `src/multiagent/core/agent.py` — `tool_configs` param, tool-aware
    `_build_graph()`, MCP client lifecycle in `run()`
12. Update `tests/unit/core/test_agent.py` — 4 new tests
13. Modify `cli/run.py` and `cli/start.py` — load MCPConfig, resolve
    per-agent tool configs, pass to LLMAgent
14. Update `src/multiagent/config/__init__.py` — export new symbols
15. `just check && just test`
16. Manual smoke test (below)

---

## Manual Smoke Test

### Setup

Create `agents.mcp.secrets.json` with a real Exa API key:

```json
{
  "mcpServers": {
    "exa": {
      "env": {
        "EXA_API_KEY": "your-actual-key"
      }
    }
  }
}
```

Update `agents.toml` to give the research desk web search:

```toml
[agents.supervisor]
router = "research_supervisor"

[agents.fundamentals]
next_agent = "supervisor"
tools = ["exa"]

[agents.risk]
next_agent = "supervisor"
tools = ["exa"]

[agents.synthesis]
next_agent = "supervisor"
```

### Run

```bash
just start --experiment tools-test

just send supervisor "Research Tesla as an investment opportunity. \
Use current web data for recent earnings and analyst consensus."
```

### Verify

In `just monitor` or `just thread <uuid>`:
- fundamentals agent makes Exa tool calls before producing analysis
- Analysis references specific recent data (earnings dates, actual figures)
- risk agent similarly uses web search
- Full pipeline completes with web-informed investment memo
- Cost table shows fundamentals and risk agents with multiple calls (tool
  round-trips each count as a call)

---

## Acceptance Criteria

```bash
just check    # zero ruff errors, zero pyright errors
just test     # all tests pass (previous total + new tests)
```

Manual:
- Agent with `tools = ["exa"]` makes web search calls during processing
- Agent without tools field works identically to current behaviour
- `agents.mcp.secrets.json` absent produces no error for agents with no tools
- `agents.mcp.secrets.json` absent produces `ConfigurationError` for agents
  that reference a server requiring credentials
- Tool call round-trips visible in JSONL log at DEBUG level
- Cost tracking counts each LLM call including tool round-trips correctly
- `just monitor` shows tool-using agents as active during tool execution

---

## What This Task Does NOT Include

- Shell execution tool — requires sandboxing design, separate task
- Write access filesystem tool — read-only is sufficient for first integration
- Custom tool implementation — only MCP server integration
- Tool result caching
- Per-tool timeout configuration
- Tool use visible in the TUI beyond agent active status
- Named cluster configurations — `agents.mcp.json` is always at repo root
  for now; per-cluster config paths are a future task
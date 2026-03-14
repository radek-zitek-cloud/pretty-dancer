# Implementation Plan — Task 011b: Routing Module

**Task:** `tasks/011b-routing.md`
**Implementer:** Tom
**Date:** 2026-03-14
**Status:** APPROVED — implementing with architect feedback incorporated

---

## Files to Create or Modify

| File | Action | Description |
|---|---|---|
| `src/multiagent/config/agents.py` | Modify | Add `RouterConfig` dataclass, `router` field to `AgentConfig`, extend `load_agents_config()` to parse `[routers.*]` and validate mutual exclusivity |
| `src/multiagent/config/__init__.py` | Modify | Export `RouterConfig` |
| `src/multiagent/core/routing.py` | Create | `KeywordRouter`, `LLMRouter`, `Router` union type, `build_router()` factory |
| `src/multiagent/core/agent.py` | Modify | Accept optional `router` param, extend graph with routing node, change `run()` return type to `RunResult` |
| `src/multiagent/core/runner.py` | Modify | Read `next_agent` from `RunResult`, resolve effective destination (dynamic > static > None) |
| `src/multiagent/core/__init__.py` | Modify | Export `KeywordRouter`, `LLMRouter`, `Router`, `build_router` |
| `src/multiagent/cli/run.py` | Modify | Resolve router from config before constructing `LLMAgent` |
| `src/multiagent/cli/start.py` | Modify | Same router resolution in the cluster loop |
| `agents.toml` | Modify | Replace `editor.next_agent` with `router = "editorial_gate"`, add `[routers.editorial_gate]` |
| `prompts/routers/editorial_gate.md` | Create | LLM classifier prompt (for testing `llm` type) |
| `tests/fixtures/agents.toml` | Modify | Add `[routers.test_router]` section |
| `tests/unit/core/test_routing.py` | Create | 9 tests: KeywordRouter (4), LLMRouter (3), build_router (2) |
| `tests/unit/config/test_agents.py` | Modify | 3 new tests: router loading, mutual exclusivity validation, backward compat |
| `tests/unit/core/test_agent.py` | Modify | 2 new tests: routing via graph, static edge without router |

---

## Design Decisions and Ambiguities

### 1. Where `RouterConfig` lives — module boundary constraint

**Problem:** The task brief places `RouterConfig` in `core/routing.py`, but
`AgentsConfig` (in `config/agents.py`) needs `routers: dict[str, RouterConfig]`.
Since `config/` must never import from `core/`, this would violate the module
boundary rules.

**Resolution:** Define `RouterConfig` in `config/agents.py`. The routing classes
in `core/routing.py` import `RouterConfig` from `config/agents.py`, which is
allowed (`core/` → may import from `config/`). This keeps the module dependency
rules intact.

### 2. `LLMAgent.run()` return type change

**Problem:** `run()` currently returns `str`. With routing, the caller
(`AgentRunner`) also needs the routing decision. The brief suggests storing
`next_agent` in LangGraph state and reading it from `graph.ainvoke()` output.

**Resolution:** Introduce a `RunResult` NamedTuple:

```python
class RunResult(NamedTuple):
    response: str
    next_agent: str | None
```

`run()` returns `RunResult` instead of `str`. This is a breaking change to the
public API of `LLMAgent` — all callers and tests must be updated. The change is
justified because routing is the primary consumer and `NamedTuple` is minimal
overhead.

Internally, the graph uses a custom state extending `MessagesState`:

```python
class AgentState(MessagesState):
    next_agent: str | None
```

The `route` node reads the last message, runs the router, and writes
`next_agent` to state. The graph always flows: `call_llm` → `route` → `END`
(when router is present) or `call_llm` → `END` (when router is absent).

**Why not conditional edges:** The task brief suggests conditional edges within
the graph, but all routing destinations are *external* agents (not graph nodes).
Conditional edges would require creating dummy terminal nodes for each
destination — unnecessary complexity. A single `route` node that writes to state
and flows to `END` is simpler and achieves the same result. The routing decision
is consumed by `AgentRunner`, not by the graph.

### 3. Graph node naming

The existing graph names its LLM node `"llm"`. The brief uses `"call_llm"`. I
will keep `"llm"` to avoid breaking existing tests and checkpointer state. The
new routing node will be named `"route"`.

### 4. Keyword router — definition-order scanning

The brief specifies "first match wins" based on iteration order of
`config.routes`. Python `dict` preserves insertion order (guaranteed since 3.7).
TOML tables also preserve order. This is reliable.

### 5. LLM router — `ChatOpenAI` construction

The `LLMRouter` needs its own `ChatOpenAI` instance (potentially with a
different model). It receives `Settings` at construction time for API
credentials and default model. This avoids importing settings inside routing
logic at call time.

### 6. `load_agents_config()` return type change

Currently returns `dict[str, AgentConfig]`. Needs to also return router configs.
I will change the return type to a new `AgentsConfig` dataclass:

```python
@dataclass(frozen=True)
class AgentsConfig:
    agents: dict[str, AgentConfig]
    routers: dict[str, RouterConfig]
```

This is a breaking change to the function signature. All callers (`run.py`,
`start.py`, test files) must be updated. The change is clean — callers access
`.agents` for the agent dict and `.routers` for router configs.

### 7. Empty trigger list in keyword router

The brief says `routes.human = []` in the TOML example but also says "empty
trigger list is never matched by scanning." This means `routes.human = []` is
dead configuration — it documents that `human` is a valid destination but only
fires via `default`. I will support this but document it clearly.

---

## Implementation Order

### Phase 1: Configuration layer

**Step 1:** `src/multiagent/config/agents.py`
- Add `RouterConfig` frozen dataclass with fields: `name`, `type`, `routes`,
  `default`, `prompt_path`, `model`
- Add `router: str | None = None` field to `AgentConfig`
- Add `AgentsConfig` frozen dataclass wrapping `agents` + `routers` dicts
- Modify `load_agents_config()` to return `AgentsConfig`, parse `[routers.*]`
  sections, validate `next_agent`/`router` mutual exclusivity

**Rationale:** Config is the foundation — everything else depends on it.

**Step 2:** `src/multiagent/config/__init__.py`
- Export `RouterConfig` and `AgentsConfig`

**Step 3:** `tests/fixtures/agents.toml`
- Add `[routers.test_router]` section with keyword type

**Step 4:** `tests/unit/config/test_agents.py`
- Add `test_loads_router_sections_from_toml`
- Add `test_raises_when_agent_has_both_next_agent_and_router`
- Add `test_backward_compatible_next_agent_still_works`
- Update existing tests for new `AgentsConfig` return type

### Phase 2: Routing module

**Step 5:** `src/multiagent/core/routing.py`
- `KeywordRouter` — synchronous `route(output: str) -> str`
- `LLMRouter` — async `route(output: str) -> str`, uses `ChatOpenAI`
- `Router = KeywordRouter | LLMRouter` union type
- `build_router(config: RouterConfig, settings: Settings) -> Router` factory

**Step 6:** `src/multiagent/core/__init__.py`
- Export routing symbols

**Step 7:** `tests/unit/core/test_routing.py`
- `TestKeywordRouter`: 4 tests (match, default, first-wins, empty-list)
- `TestLLMRouter`: 3 tests (recognised key, unrecognised fallback, model override)
- `TestBuildRouter`: 2 tests (keyword type, llm type, unknown type error)

### Phase 3: Agent and runner integration

**Step 8:** `src/multiagent/core/agent.py`
- Define `AgentState(MessagesState)` with `next_agent: str | None`
- Define `RunResult(NamedTuple)` with `response: str`, `next_agent: str | None`
- Add `router: Router | None = None` parameter to `__init__`
- Modify `_build_graph()`: use `AgentState`, add `route` node when router is
  present (`llm` → `route` → END), keep `llm` → END when no router
- Modify `run()`: return `RunResult` instead of `str`

**Step 9:** `src/multiagent/core/runner.py`
- Update `run_once()` to receive `RunResult` from `agent.run()`
- Resolve effective next agent: `result.next_agent or self._next_agent`
- Use effective next agent for message forwarding

**Step 10:** `tests/unit/core/test_agent.py`
- Update all existing tests: `run()` now returns `RunResult` — access
  `.response` for the text
- Add `test_keyword_router_determines_next_agent`
- Add `test_static_next_agent_used_when_no_router`

### Phase 4: CLI wiring

**Step 11:** `src/multiagent/cli/run.py`
- Update `load_agents_config()` call to use `AgentsConfig`
- Resolve router from `agent_config.router` → `agents_config.routers[name]`
- Pass router to `LLMAgent` constructor
- Raise `ConfigurationError` if router name not found in `routers`

**Step 12:** `src/multiagent/cli/start.py`
- Same changes as `run.py`, applied inside the agent loop

### Phase 5: Configuration and prompts

**Step 13:** `agents.toml`
- Replace `editor.next_agent = "human"` with `router = "editorial_gate"`
- Add `[routers.editorial_gate]` section (keyword type)
- Keep `writer.next_agent` and `linguist.next_agent` unchanged

**Step 14:** `prompts/routers/editorial_gate.md`
- Create LLM classifier prompt for the editorial gate (reference implementation
  for testing `llm` router type)

### Phase 6: Gate

**Step 15:** `just check && just test`
- All pyright strict, all ruff clean, all tests green
- Verify module boundaries with grep

---

## What I Would Do Differently From the Brief

### 1. No conditional edges in the graph (simplification)

The brief suggests `add_conditional_edges` mapping router output to destination
nodes within the graph. Since all destinations are external agents (not graph
nodes), this would require creating dummy nodes or complex mapping. Instead, the
`route` node simply writes `next_agent` to state and flows to `END`.
`AgentRunner` reads the routing decision from the result. Same outcome, less
graph complexity.

### 2. `RouterConfig` in `config/agents.py`, not `core/routing.py`

Moved to respect module boundaries. The brief's placement would require
`config/` to import from `core/`, violating the dependency rules.

### 3. `RunResult` NamedTuple instead of dict

The brief suggests `result.get("next_agent")` dict access. A NamedTuple provides
type safety (pyright can validate field access), is immutable, and makes the
return contract explicit. This is better for pyright strict compliance.

### 4. Keep existing node name `"llm"` (not `"call_llm"`)

The existing codebase uses `"llm"` as the graph node name. Renaming to
`"call_llm"` would break existing checkpointer state and all tests referencing
the node. No benefit to renaming.

---

## Architect Feedback — Incorporated

### Feedback 1: Checkpoint compatibility verification

Do not assume `AgentState` (extending `MessagesState` with `next_agent`) is
backward-compatible with existing checkpoints. After implementation, explicitly
verify by running an existing thread through the modified agent. If old
checkpoints raise a validation error, wipe `data/checkpoints.db` and document
the incompatibility.

**Action:** Add a manual verification step after Phase 3 — run an existing
thread before smoke test.

**Outcome:** Verified. Old checkpoints load successfully. The `next_agent`
field defaults to `None` for existing checkpoint data. LangGraph's
`AsyncSqliteSaver.aget()` returns `channel_values` that include `messages`
(10 messages) and `next_agent: None`. No database wipe needed.

### Feedback 2: `RunResult.response` extraction — type guard required

`AIMessage.content` is `str | list[str | dict]`. When extracting the response
string from `state["messages"][-1].content`, a type guard is required for
pyright strict. Use explicit type narrowing:

```python
content = result["messages"][-1].content
response = content if isinstance(content, str) else str(content)
```

This applies in both `run()` (extracting from graph output) and the `route`
node (reading output for the router).

---

## Risk Assessment

| Risk | Mitigation |
|---|---|
| `run()` return type change breaks many tests | Systematic update in Phase 3, Step 10 — all callers access `.response` |
| `load_agents_config()` return type change breaks CLI | Update in Phase 4 — callers use `.agents` and `.routers` |
| LangGraph custom state type causes checkpointer issues | Verify explicitly after implementation — wipe `data/checkpoints.db` if needed (per architect feedback) |
| `dict` ordering assumption in keyword router | Python 3.12 guarantees dict order; TOML preserves order. Safe. |
| `AIMessage.content` type variance | Type guard on extraction — `isinstance(content, str)` check (per architect feedback) |

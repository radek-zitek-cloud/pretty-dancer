# Task 011b — Routing Module

**File:** `tasks/011b-routing.md`  
**Status:** APPROVED  
**Architect:** Claude (claude.ai) in collaboration with Radek Zítek  
**Date:** 2026-03-14  
**Reference:** `docs/implementation-guide.md` (canonical authority for all decisions)  
**Depends on:** Task 011a (multi-party messaging) complete and merged to master

---

## Objective

Replace the current static `next_agent` routing with a dynamic routing system
that allows agents to decide their destination based on message content. After
this task:

- A `router` key in `agents.toml` replaces `next_agent` for conditional routing
- Two router types are supported: `keyword` and `llm`
- The editorial scenario works end-to-end without human intervention: editor
  routes to `human` during dialogue and to `writer` when producing a brief,
  automatically
- Existing `next_agent` entries continue to work unchanged — full backward
  compatibility

The editorial cluster is the validation scenario for this task:

```
human ↔ editor   (dialogue — editor routes to human)
editor → writer  (brief produced — editor routes to writer)
writer → linguist
linguist → human
```

---

## Authoritative References

Read in full before producing your implementation plan:

- `docs/implementation-guide.md` — all standards, module rules, coding
  conventions
- `tasks/003-agent-core.md` — `LLMAgent._build_graph()` this task modifies
- `tasks/011a-multiparty-messaging.md` — `from_agent`/`to_agent` transport
  fields established in 011a
- `tasks/004-cli-wiring.md` — CLI patterns for context

---

## Git

Work on branch `feature/routing` created from `master`.

```bash
git checkout master
git pull origin master
git checkout -b feature/routing
```

Commit at each meaningful step using Conventional Commits. Final commit:

```
feat(core): add keyword and llm routing module with conditional edges
```

---

## `agents.toml` Schema Extension

### Backward compatibility

`next_agent` continues to work exactly as before. Any agent without a `router`
key uses `next_agent` (or terminates if `next_agent` is absent). No existing
configuration breaks.

### New `router` key on agents

```toml
[agents.editor]
router = "editorial_gate"       # replaces next_agent for this agent

[agents.writer]
next_agent = "linguist"         # unchanged — static routing still works

[agents.linguist]
next_agent = "human"
```

### New `[routers.*]` sections

#### Keyword router

```toml
[routers.editorial_gate]
type = "keyword"
routes.writer = ["WRITER BRIEF", "END BRIEF"]   # if output contains any of these → writer
routes.human  = []                               # default fallback
default = "human"
```

`routes.<destination>` is a list of trigger strings. The router scans the
agent's output for any of the listed strings (case-sensitive substring match).
First match wins. `default` is used when no trigger string is found.

#### LLM classifier router

```toml
[routers.editorial_gate]
type = "llm"
prompt = "prompts/routers/editorial_gate.md"
routes.writer = "writer"
routes.human  = "human"
default = "human"
model = ""          # optional — empty means use settings.llm_model
```

The LLM classifier makes a second lightweight LLM call. It receives the agent's
output and returns exactly one route key. The route key maps to a destination
agent name.

---

## New Module: `src/multiagent/core/routing.py`

All routing logic lives here. No routing code in `agent.py` beyond wiring.
`core/` module boundary rules apply — no imports from `transport/` or `cli/`.

### `RouterConfig` — dataclass

```python
@dataclass
class RouterConfig:
    type: str                          # "keyword" | "llm"
    routes: dict[str, list[str]]       # destination → trigger strings (keyword)
                                       # destination → route key (llm)
    default: str                       # fallback destination
    prompt_path: Path | None = None    # for llm type only
    model: str = ""                    # for llm type only; empty = use settings model
```

### `KeywordRouter`

```python
class KeywordRouter:
    def __init__(self, config: RouterConfig) -> None: ...

    def route(self, output: str) -> str:
        """Scan output for trigger strings. Return destination agent name."""
```

Scanning logic:
1. Iterate `config.routes` in definition order
2. For each destination, check if any trigger string appears in `output`
3. Return first matching destination
4. If no match, return `config.default`

Empty trigger list (`[]`) is never matched by scanning — it represents the
default. Only `config.default` is used as fallback.

### `LLMRouter`

```python
class LLMRouter:
    def __init__(self, config: RouterConfig, settings: Settings) -> None: ...

    async def route(self, output: str) -> str:
        """Call LLM classifier. Return destination agent name."""
```

The classifier prompt is loaded from `config.prompt_path`. It is called with
the agent's output appended. The LLM must return exactly one of the route keys
defined in `config.routes`. If the returned key is not recognised, fall back to
`config.default` and log a WARNING.

The classifier uses `ChatOpenAI` with `max_tokens=10` — single token response
is sufficient. Use `config.model` if set, otherwise `settings.llm_model`.

### `Router` — union type

```python
Router = KeywordRouter | LLMRouter
```

### `build_router(config: RouterConfig, settings: Settings) -> Router`

Factory function. Returns a `KeywordRouter` or `LLMRouter` based on
`config.type`. Raises `ConfigurationError` for unknown types.

---

## `src/multiagent/config/agents.py` — Extension

`AgentConfig` currently holds `next_agent: str | None`. Extend it:

```python
@dataclass
class AgentConfig:
    next_agent: str | None = None
    router: str | None = None       # name of router in [routers.*]
```

Add `RouterConfig` loading:

```python
@dataclass  
class AgentsConfig:
    agents: dict[str, AgentConfig]
    routers: dict[str, RouterConfig]   # new
```

`load_agents_config()` parses both `[agents.*]` and `[routers.*]` sections.
An agent may have `next_agent` OR `router`, not both. If both are present,
raise `ConfigurationError`.

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
    router: Router | None = None,       # new, optional
) -> None:
```

`router` is `None` for agents using static `next_agent`. The caller (CLI)
resolves which router to pass based on `AgentConfig`.

### `_build_graph()` — conditional edges

When `self._router` is not `None`, replace the static edge with a conditional
edge:

```python
if self._router is not None:
    async def _route_node(state: MessagesState) -> str:
        output = state["messages"][-1].content
        if isinstance(self._router, KeywordRouter):
            return self._router.route(str(output))
        else:
            return await self._router.route(str(output))

    graph.add_node("router", _route_node)
    graph.add_edge("call_llm", "router")
    graph.add_conditional_edges(
        "router",
        lambda x: x,                    # identity — node returns the destination key
        {dest: dest for dest in all_destinations},
    )
else:
    graph.add_edge("call_llm", END)
```

`all_destinations` is derived from `router.config.routes.keys()` plus
`router.config.default`.

### Routing result → transport

The routing decision (destination agent name) must reach `AgentRunner` so it
can address the outbound message correctly. Currently `AgentRunner` uses the
static `next_agent` from config. With dynamic routing, the destination is
determined inside the graph.

**Mechanism:** Store the routing decision in LangGraph state. Add
`next_agent: str | None` to `MessagesState` (or use a separate state field).
The `_route_node` writes the decision to state. `AgentRunner` reads it from
the graph output after `graph.invoke()`.

```python
# In AgentRunner.run_loop(), after graph.invoke():
result = await self._agent.run(input_text, thread_id)
next_agent = result.get("next_agent") or self._static_next_agent
```

Where `self._static_next_agent` is the `next_agent` from `AgentConfig` (may
be `None` for terminal agents using static routing).

---

## `src/multiagent/core/runner.py` — Modifications

`AgentRunner.__init__` currently accepts `next_agent: str | None` from config.
This becomes `static_next_agent: str | None` internally to distinguish it from
dynamic routing results. No change to the constructor signature — rename
internally only.

After `graph.invoke()`, resolve the effective next agent:

```python
dynamic_next = result.get("next_agent")
effective_next = dynamic_next or self._static_next_agent
```

If `effective_next` is `None`, the agent is terminal — do not send a reply.
If `effective_next` is `"human"`, send to `"human"` in the transport as normal.

---

## Router Prompt Files

### `prompts/routers/editorial_gate.md`

For LLM router type (alternative to keyword router for editorial scenario):

```markdown
You are a routing classifier. You will receive the output of an editor agent.
Your task is to determine where the output should be sent.

Return exactly one word — nothing else:
- writer   if the output contains a completed writer brief (look for "WRITER BRIEF" and "END BRIEF")
- human    if the output is a question, comment, or dialogue directed at the human

Output only the single word. No punctuation, no explanation.
```

---

## `agents.toml` — Editorial Cluster Configuration

```toml
[agents.editor]
router = "editorial_gate"

[agents.writer]
next_agent = "linguist"

[agents.linguist]
next_agent = "human"

[routers.editorial_gate]
type = "keyword"
routes.writer = ["WRITER BRIEF", "END BRIEF"]
default = "human"
```

Note: keyword router is preferred here over LLM router — the editor's brief
format is deterministic (always contains "WRITER BRIEF" and "END BRIEF") so
a second LLM call is unnecessary cost and latency. The LLM router prompt is
provided for reference and for testing the `llm` type independently.

---

## New Prompt Files Required

```
prompts/routers/editorial_gate.md    # LLM classifier prompt (for llm type testing)
```

---

## Test Requirements

### `tests/unit/core/test_routing.py` — New File

```
TestKeywordRouter
    test_routes_to_first_matching_destination
        — output contains trigger string for "writer"
        — assert route() returns "writer"

    test_routes_to_default_when_no_match
        — output contains no trigger strings
        — assert route() returns default

    test_first_match_wins_when_multiple_triggers_present
        — output contains trigger strings for two destinations
        — assert route() returns the first defined destination

    test_empty_trigger_list_never_matches
        — destination with [] triggers
        — assert it is never selected by scanning, only as default

TestLLMRouter
    test_routes_to_recognised_key
        — mock LLM returns "writer"
        — assert route() returns "writer"

    test_falls_back_to_default_on_unrecognised_key
        — mock LLM returns "nonsense"
        — assert route() returns default, logs WARNING

    test_uses_override_model_when_specified
        — config.model = "anthropic/claude-haiku-4-5-20251001"
        — assert ChatOpenAI called with that model

TestBuildRouter
    test_builds_keyword_router_for_keyword_type
    test_builds_llm_router_for_llm_type
    test_raises_configuration_error_for_unknown_type
```

### `tests/unit/config/test_agents.py` — Modifications

```
test_loads_router_sections_from_toml
    — fixture agents.toml with [routers.editorial_gate]
    — assert RouterConfig loaded with correct type, routes, default

test_raises_when_agent_has_both_next_agent_and_router
    — agents.toml with agent having both keys
    — assert ConfigurationError raised

test_backward_compatible_next_agent_still_works
    — agents.toml with only next_agent (no router sections)
    — assert loads correctly, routers dict is empty
```

### `tests/unit/core/test_agent.py` — Modifications

```
test_keyword_router_determines_next_agent
    — construct LLMAgent with KeywordRouter
    — mock LLM output contains "WRITER BRIEF"
    — assert run() result["next_agent"] == "writer"

test_static_next_agent_used_when_no_router
    — construct LLMAgent with router=None
    — assert graph uses static edge to END
```

### `tests/fixtures/agents.toml` — Update

Add a `[routers.test_router]` section for use in routing tests:

```toml
[routers.test_router]
type = "keyword"
routes.agent_b = ["ROUTE_TO_B"]
default = "agent_a"
```

---

## Implementation Order

1. Extend `AgentConfig` and `AgentsConfig` in `config/agents.py`
2. Update `load_agents_config()` to parse `[routers.*]` sections
3. Update `tests/unit/config/test_agents.py` — TDD red phase (3 tests)
4. Green phase — config tests pass
5. Create `src/multiagent/core/routing.py` — `RouterConfig`, `KeywordRouter`,
   `LLMRouter`, `build_router`
6. Create `tests/unit/core/test_routing.py` — TDD red phase (9 tests)
7. Green phase — routing tests pass
8. Modify `src/multiagent/core/agent.py` — `router` param, conditional edges,
   `next_agent` in state output
9. Modify `src/multiagent/core/runner.py` — dynamic next agent resolution
10. Update `tests/unit/core/test_agent.py` — 2 new routing tests
11. Update `agents.toml` — editorial cluster with `[routers.editorial_gate]`
12. Create `prompts/routers/editorial_gate.md`
13. Update CLI (`run.py`, `start.py`) — resolve router from `AgentConfig`,
    pass to `LLMAgent`
14. `just check && just test`
15. Manual smoke test (below)

---

## CLI Changes — `run.py` and `start.py`

Both files must resolve the router before constructing `LLMAgent`:

```python
from multiagent.core.routing import build_router

router = None
if agent_config.router:
    router_config = agents_config.routers[agent_config.router]
    router = build_router(router_config, settings)

agent = LLMAgent(name, settings, checkpointer, cost_ledger, router=router)
```

Raise `ConfigurationError` if `agent_config.router` references a router name
not present in `agents_config.routers`.

---

## Manual Smoke Test

```bash
# Terminal 1
just start --experiment routing-test

# Terminal 2
just chat editor

You: I want to write something about the rise of AI coding assistants.
# Editor asks clarifying questions, routes back to human each time

You: Focus on how they affect junior developers. Audience is engineering managers. 500 words.
# More dialogue

You: Yes, perfect. Go ahead.
# Editor produces WRITER BRIEF ... END BRIEF
# Keyword router detects "WRITER BRIEF" → routes to writer automatically
# Writer produces draft → routes to linguist automatically
# Linguist polishes → routes to human
# chat terminal receives finished article without any manual intervention

# Verify the full chain
just threads
# Participants: human, editor, writer, linguist

just thread <uuid>
# Shows: human ↔ editor dialogue, brief, draft, polished article
# All with correct from_agent → to_agent headers
```

---

## Acceptance Criteria

```bash
just check    # zero ruff errors, zero pyright errors
just test     # all tests pass (previous total + new tests)
```

Manual:
- Editorial scenario runs end-to-end with one `just chat editor` session
- Editor routes to `human` during dialogue
- Editor routes to `writer` automatically when brief is produced
- Writer and linguist route correctly without any manual intervention
- Finished article arrives in the `chat` terminal addressed to `human`
- Existing newsroom pipeline (`next_agent` only) continues to work unchanged
- `just threads` shows all four participants in the thread

---

## What This Task Does NOT Include

- Supervisor pattern — Task 012
- Implementer invoking Claude Code as a tool — Task 012
- `max_messages_per_thread` termination — deferred
- Hot reload of `agents.toml` without restart
- Router chaining (router output feeds another router)
- Per-agent router prompt override at runtime
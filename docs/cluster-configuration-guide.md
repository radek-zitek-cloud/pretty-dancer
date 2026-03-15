# Cluster Configuration Guide

**For:** Radek Zítek  
**Last Updated:** 2026-03-14  
**Platform version:** post-013a

---

## Overview

A cluster is a set of agents that run together when you invoke `just start`.
Each agent has a system prompt, optional routing logic, and optional tool
access. Clusters are defined by three files working together:

```
agents.toml              — who the agents are and how they connect
agents.mcp.json          — which MCP servers (tools) are available
prompts/                 — what each agent knows about itself
```

For named experiments, each of these has an experiment-specific variant.

---

## Quick Start

### Default cluster

```bash
just start
```

Loads `agents.toml`, `agents.mcp.json`, and `prompts/*.md`.

### Named experiment

```bash
just start research-desk
```

Loads `agents.research-desk.toml`, `agents.mcp.research-desk.json`, and
`prompts/research-desk/*.md`. All three must exist — missing files are a hard
error.

---

## `agents.toml` — Agent Wiring

### Minimal agent

```toml
[agents.writer]
next_agent = "linguist"     # always route to linguist after processing
```

### Terminal agent (no routing)

```toml
[agents.linguist]
# no next_agent — linguist is the last agent in the chain
# its output is addressed to whoever sent the message
```

Wait — terminal agents route their output back to the sender automatically.
For a pipeline that ends by returning to the human, set:

```toml
[agents.linguist]
next_agent = "human"
```

### Agent with dynamic routing

```toml
[agents.editor]
router = "editorial_gate"   # routing decision made by the editorial_gate router
```

An agent may have `next_agent` OR `router`, never both.

### Agent with tools

```toml
[agents.researcher]
next_agent = "supervisor"
tools = ["exa"]             # server names from agents.mcp.json
```

### Full example — research desk

```toml
[agents.supervisor]
router = "research_supervisor"
tools = ["filesystem"]

[agents.fundamentals]
next_agent = "supervisor"
tools = ["exa"]

[agents.risk]
next_agent = "supervisor"
tools = ["exa"]

[agents.synthesis]
next_agent = "supervisor"

[routers.research_supervisor]
type = "llm"
prompt = "prompts/routers/research_supervisor.md"
routes.fundamentals = "fundamentals"
routes.risk = "risk"
routes.synthesis = "synthesis"
routes.human = "human"
default = "human"
```

### Router types

**Keyword router** — routes based on trigger strings in the agent's output.
No extra LLM call. Use when output format is predictable.

```toml
[routers.editorial_gate]
type = "keyword"
routes.writer = ["WRITER BRIEF", "END BRIEF"]   # any of these triggers → writer
default = "human"                               # fallback when no match
```

**LLM classifier router** — makes a second lightweight LLM call to decide
the destination. Use when routing requires understanding natural language.

```toml
[routers.research_supervisor]
type = "llm"
prompt = "prompts/routers/research_supervisor.md"
routes.fundamentals = "fundamentals"
routes.risk = "risk"
routes.human = "human"
default = "human"
model = ""    # empty = use settings.llm_model; override with a cheaper model
```

---

## `agents.mcp.json` — Tool Servers

Defines which MCP servers are available. Committed to git — no secrets here.

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
    },
    "chroma": {
      "command": "uvx",
      "args": [
        "chroma-mcp",
        "--client-type", "persistent",
        "--data-dir", "./data/chroma"
      ]
    }
  }
}
```

Server names (keys) are what you reference in `agents.toml` `tools = [...]`.

---

## `agents.mcp.secrets.json` — Credentials

Gitignored. Provides environment variables for servers that need API keys.
Only create values that differ from empty — servers with no credentials
(like local filesystem or chroma) need no entry here.

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

Use `agents.mcp.secrets.example.json` (committed) as the template — it
documents required keys with empty values.

**Secrets and experiments:** You do not need a separate secrets file per
experiment. The default `agents.mcp.secrets.json` covers all experiments.
If you ever need experiment-specific credentials, create
`agents.mcp.secrets.{experiment}.json` and it will be used automatically.

---

## `prompts/` — System Prompts

One markdown file per agent. The filename must match the agent name in
`agents.toml` exactly.

```
prompts/
├── alfa.md                     # default cluster agents
├── beta.md
└── research-desk/              # experiment-specific agents
    ├── supervisor.md
    ├── fundamentals.md
    ├── risk.md
    └── synthesis.md
```

Router prompts live in a `routers/` subfolder:

```
prompts/
├── routers/
│   └── research_supervisor.md  # default router prompts
└── research-desk/
    └── routers/
        └── research_supervisor.md  # experiment-specific router prompt
```

### Writing a good system prompt

The system prompt defines the agent's identity, responsibilities, output
format, and communication rules. A well-structured prompt has four sections:

```markdown
## Who you are
[Role and expertise]

## Your responsibilities
[What you do when you receive a message]

## Output format
[Exactly how your response must be structured]

## Rules
[Constraints — what you must never do]
```

Keep prompts under 600 words. Longer prompts increase token costs on every
call without proportional benefit.

---

## Named Experiments

A named experiment is a fully isolated cluster configuration. Everything
about the experiment lives in its own files.

### File naming convention

| File | Path |
|---|---|
| Agent wiring | `agents.{experiment}.toml` |
| MCP servers | `agents.mcp.{experiment}.json` |
| MCP secrets | `agents.mcp.secrets.{experiment}.json` (optional) |
| Agent prompts | `prompts/{experiment}/{agent}.md` |
| Router prompts | `prompts/{experiment}/routers/{router}.md` |

### Experiment name rules

- Lowercase letters, digits, and hyphens only: `[a-z0-9-]+`
- No spaces, no dots, no slashes
- Valid: `research-desk`, `debate-v2`, `editorial`
- Invalid: `My Experiment`, `research/desk`, `v1.0`

### Creating a new experiment

```bash
# 1. Create the agent wiring file
cp agents.toml agents.my-experiment.toml
# Edit agents.my-experiment.toml

# 2. Create the MCP config file
cp agents.mcp.json agents.mcp.my-experiment.json
# Edit agents.mcp.my-experiment.json

# 3. Create the prompts directory and add prompt files
mkdir prompts/my-experiment
# Create prompts/my-experiment/{agent}.md for each agent

# 4. Run it
just start my-experiment
```

No secrets file needed unless your experiment uses different API keys than
the default.

### Error messages

**Missing config file:**
```
ConfigurationError: Experiment config not found: agents.my-experiment.toml.
Create this file to run the 'my-experiment' experiment.
```

**Missing prompt file:**
```
ConfigurationError: Prompt file not found: prompts/my-experiment/supervisor.md.
Create this file to define the 'supervisor' agent for experiment 'my-experiment'.
```

**Invalid experiment name:**
```
Invalid experiment name 'My Experiment'.
Experiment names must contain only lowercase letters, digits, and hyphens.
```

---

## Current Experiments

| Experiment | Description | Start command |
|---|---|---|
| *(default)* | Alfa/beta agents for general use | `just start` |
| `research-desk` | Investment research: supervisor + fundamentals + risk + synthesis | `just start research-desk` |
| `editorial` | Editorial pipeline: editor + writer + linguist | `just start editorial` |

---

## Sending Messages

Always send to a specific agent by name:

```bash
just send supervisor "Research Apple as investment opportunity"
just send editor "I want to write about the rise of AI coding tools"
```

With a thread ID to continue an existing conversation:

```bash
just send supervisor "Follow up on the Apple analysis" --thread-id <uuid>
```

---

## Monitoring

```bash
just monitor                    # all threads
just monitor research-desk      # filter to research-desk experiment
```

The monitor shows agent status, message flow, and cost in real time. Use the
inline send panel to interact with agents without switching terminals.

---

## Cost Reference

Approximate costs per experiment run at current model prices:

| Experiment | Agents | Typical messages | Approximate cost |
|---|---|---|---|
| Editorial pipeline | 3 | 8 | $0.009 |
| Investment research desk | 4 | 8 | $0.035 |
| Debate (10 rounds) | 2 | 20 | $0.005 |

Costs vary significantly by model. Switch models in `.env`:

```bash
LLM_MODEL=google/gemini-3-flash-preview    # cheap, fast
LLM_MODEL=anthropic/claude-sonnet-4-5      # balanced
LLM_MODEL=anthropic/claude-opus-4-5        # highest quality
```

---

## Justfile Reference

```bash
just start [experiment]         # start cluster
just stop                       # stop cluster (writes stop file)
just send <agent> "<message>"   # send message to agent
just monitor [experiment]       # open TUI monitor
just chat <agent>               # interactive chat session
just listen                     # poll for messages addressed to human
just threads                    # browse all threads
just thread <id>                # show full thread
just costs                      # cost summary by experiment
just ingest                     # index docs into Chroma for RAG
```

---

## Troubleshooting

**Agents not processing messages**
Check `just monitor` — if agent status is stuck on active for more than
the poll interval, the cluster may have crashed. Check the log files in
`logs/`. Restart with `just start`.

**Messages going to wrong agent**
The LLM router may be misclassifying. Check the thread with `just thread <id>`
and look at each message's `from → to` header. Review the router prompt in
`prompts/routers/` — add explicit examples of edge cases that are being
misrouted.

**`[PENDING]` appearing in messages**
The supervisor is hitting the token limit mid-response or appending status
markers. Increase `LLM_MAX_TOKENS` in `.env` and ensure the supervisor prompt
does not instruct it to append status notes.

**Loop detected**
The loop detection system will log `routing_loop_detected` and halt dispatch
on that thread. Other threads continue normally. Check the router prompt and
agent prompts for instructions that might cause self-routing.

**Tool calls failing**
Check that the MCP server name in `tools = [...]` matches a key in
`agents.mcp.json` exactly. Check `agents.mcp.secrets.json` has the correct
API key for that server. Check the JSONL log with `LOG_TRACE_LLM=true` to see
the actual tool call and error.
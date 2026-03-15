# pyright: reportUnknownMemberType=false, reportUnusedImport=false, reportUnknownArgumentType=false, reportCallIssue=false, reportUnknownVariableType=false, reportArgumentType=false, reportTypedDictNotRequiredAccess=false, reportUnknownParameterType=false, reportMissingTypeArgument=false
"""LLMAgent — transport-agnostic LLM wrapper with LangGraph."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from multiagent.config.mcp import MCPServerConfig
from multiagent.config.settings import Settings
from multiagent.core.costs import CostEntry, CostLedger
from multiagent.core.routing import KeywordRouter, LLMRouter
from multiagent.exceptions import AgentConfigurationError, AgentLLMError


def _resolve_prompt_path(
    prompts_dir: Path, agent_name: str, experiment: str,
) -> Path:
    """Resolve system prompt path for the given agent and experiment.

    When experiment is set, looks in the experiment subdirectory first.
    Falls back to the flat prompts directory if no experiment is set.
    """
    if experiment:
        return prompts_dir / experiment / f"{agent_name}.md"
    return prompts_dir / f"{agent_name}.md"


class AgentState(MessagesState):
    """Extended graph state with routing decision.

    Inherits messages list from MessagesState and adds next_agent
    for dynamic routing. When no router is present, next_agent
    remains None.
    """

    next_agent: str | None


class RunResult(NamedTuple):
    """Result of an agent run — response text and optional routing decision.

    Attributes:
        response: The LLM's response as a plain string.
        next_agent: Destination agent from dynamic routing, or None
            if no router is configured or routing did not run.
    """

    response: str
    next_agent: str | None = None


class LLMAgent:
    """LLM-powered agent, transport-agnostic.

    Wraps a single LangGraph graph with one LLM node and an optional
    routing node. The public interface is ``run(input_text, thread_id)``
    which returns a RunResult containing the response and routing decision.
    """

    def __init__(  # type: ignore[type-arg]
        self,
        name: str,
        settings: Settings,
        checkpointer: BaseCheckpointSaver,
        cost_ledger: CostLedger,
        router: KeywordRouter | LLMRouter | None = None,
        tool_configs: list[MCPServerConfig] | None = None,
        prompt_name: str | None = None,
    ) -> None:
        """Initialise the agent with a name, settings, checkpointer, and cost ledger."""
        self.name = name
        self._settings = settings
        self._cost_ledger = cost_ledger
        self._router = router
        self._tool_configs = tool_configs or []
        self._log = structlog.get_logger().bind(agent=name)
        if prompt_name:
            # Explicit prompt path from agents.toml — use directly
            self._system_prompt = self._load_prompt_path(Path(prompt_name))
        else:
            # Convention-based: experiment subdir if set, else flat
            prompt_path = _resolve_prompt_path(
                settings.prompts_dir, name, settings.experiment
            )
            self._system_prompt = self._load_prompt_path(prompt_path)
        self._checkpointer = checkpointer
        self._llm = ChatOpenAI(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_seconds,
            api_key=settings.openrouter_api_key,  # type: ignore[arg-type]
            base_url=settings.openrouter_base_url,
        )
        # Pre-built graph for agents without tools (reused across calls)
        self._graph = self._build_graph() if not self._tool_configs else None

    def _load_prompt_path(self, prompt_path: Path) -> str:
        """Load the system prompt from a file path.

        Reads the file contents and strips leading/trailing whitespace.

        # TODO: parse YAML frontmatter when structured prompts are introduced.
        #       Frontmatter will carry metadata (version, tags, model hints).
        #       Body after frontmatter delimiter (---) becomes the prompt text.

        Args:
            prompt_path: Full path to the prompt file.

        Returns:
            System prompt string with whitespace stripped.

        Raises:
            AgentConfigurationError: If the prompt file does not exist or
                cannot be read.
        """
        try:
            return prompt_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            raise AgentConfigurationError(
                f"Prompt file not found for agent '{self.name}': {prompt_path}"
            ) from None
        except OSError as exc:
            raise AgentConfigurationError(
                f"Failed to read prompt file for agent '{self.name}': {exc}"
            ) from exc

    def _build_graph(  # type: ignore[type-arg]
        self,
        tools: list[object] | None = None,
    ) -> CompiledStateGraph:
        """Build the LangGraph processing graph with AgentState.

        Uses AgentState (extending MessagesState) which maintains a list
        of BaseMessage objects that accumulates across invocations via the
        checkpointer. Supports optional tools (ReAct pattern) and/or
        routing.

        Graph structure:
            No tools, no router:  llm → END
            No tools, router:     llm → route → END
            Tools, no router:     llm → should_continue → tools → llm / END
            Tools + router:       llm → should_continue → tools → llm / route → END

        Args:
            tools: Optional list of LangChain-compatible tools from MCP.

        Returns:
            Compiled graph with checkpointer attached.
        """
        llm = self._llm.bind_tools(tools) if tools else self._llm

        async def call_llm(state: AgentState, config: RunnableConfig) -> AgentState:  # type: ignore[return-type]
            self._log.debug("llm_call_start", history_length=len(state["messages"]))
            response = await llm.ainvoke([
                SystemMessage(content=self._system_prompt),
                *state["messages"],
            ])
            output = str(response.content)
            self._log.debug("llm_call_complete", output_chars=len(output))

            usage = response.usage_metadata or {}
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            total_tokens = int(usage.get("total_tokens") or 0)

            metadata = response.response_metadata or {}
            token_usage = metadata.get("token_usage") or {}
            cost_details = token_usage.get("cost_details") or {}
            cost_usd = float(token_usage.get("cost") or 0.0)
            input_cost = float(cost_details.get("upstream_inference_prompt_cost") or 0.0)
            output_cost = float(
                cost_details.get("upstream_inference_completions_cost") or 0.0
            )
            input_unit_price = (input_cost / input_tokens) if input_tokens else 0.0
            output_unit_price = (output_cost / output_tokens) if output_tokens else 0.0

            self._log.debug(
                "llm_usage",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                input_unit_price=input_unit_price,
                output_unit_price=output_unit_price,
                history_length=len(state["messages"]),
            )

            if self._settings.log_trace_llm:
                self._log.info(
                    "llm_trace",
                    prompt=state["messages"][-1].content,
                    system_prompt=self._system_prompt,
                    response=output,
                    history_length=len(state["messages"]),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    output_chars=len(output),
                )

            # Strip agent-name namespace prefix for cost recording
            raw_tid = str(config["configurable"]["thread_id"])
            cost_tid = raw_tid.split(":", 1)[1] if ":" in raw_tid else raw_tid
            entry = CostEntry(
                timestamp=datetime.now(UTC).isoformat(),
                thread_id=cost_tid,
                agent=self.name,
                model=self._settings.llm_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                input_unit_price=input_unit_price,
                output_unit_price=output_unit_price,
                cost_usd=cost_usd,
                experiment=self._settings.experiment,
            )
            try:
                await self._cost_ledger.record(entry)
            except Exception as exc:
                self._log.warning("cost_recording_failed", error=str(exc))

            return {"messages": [response]}  # type: ignore[return-value]

        graph: StateGraph = StateGraph(AgentState)  # type: ignore[type-arg]
        graph.add_node("llm", call_llm)
        graph.set_entry_point("llm")

        has_router = self._router is not None

        if tools:
            graph.add_node("tools", ToolNode(tools))

            # Custom should_continue: tool_calls → "tools", else → "route" or END
            after_done = "route" if has_router else END

            def should_continue(state: AgentState) -> str:
                last_msg = state["messages"][-1]
                tool_calls = getattr(last_msg, "tool_calls", None)
                if tool_calls:
                    return "tools"
                return after_done

            graph.add_conditional_edges(
                "llm", should_continue, ["tools", after_done]
            )
            graph.add_edge("tools", "llm")
        elif has_router:
            graph.add_edge("llm", "route")
        else:
            graph.add_edge("llm", END)

        if has_router:
            router = self._router
            assert router is not None

            async def route_node(state: AgentState) -> AgentState:  # type: ignore[return-type]
                content = state["messages"][-1].content
                output = content if isinstance(content, str) else str(content)
                if isinstance(router, KeywordRouter):
                    destination = router.route(output)
                else:
                    destination = await router.route(output)
                self._log.info("routing_decision", destination=destination)
                return {"next_agent": destination}  # type: ignore[return-value]

            graph.add_node("route", route_node)
            if not tools:
                pass  # edge from llm → route already added above
            graph.add_edge("route", END)

        return graph.compile(checkpointer=self._checkpointer)

    async def _invoke_graph(
        self,
        graph: CompiledStateGraph,  # type: ignore[type-arg]
        input_text: str,
        thread_id: str,
    ) -> RunResult:
        """Invoke a compiled graph and extract the result."""
        namespaced_thread = f"{self.name}:{thread_id}"
        config = {"configurable": {"thread_id": namespaced_thread}}
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=input_text)]},
            config=config,
        )
        content = result["messages"][-1].content
        response = content if isinstance(content, str) else str(content)
        if not response:
            self._log.warning(
                "empty_llm_response",
                thread_id=thread_id,
                message_count=len(result["messages"]),
            )
        next_agent: str | None = result.get("next_agent")
        return RunResult(response=response, next_agent=next_agent)

    async def run(self, input_text: str, thread_id: str) -> RunResult:
        """Process input_text with full conversation history for the thread.

        For agents with tools, an MCP client is opened for each call to
        provide tool access. For agents without tools, the pre-built graph
        is reused.

        Args:
            input_text: The message body to process.
            thread_id: Conversation thread identifier.

        Returns:
            RunResult with the LLM response and optional routing decision.

        Raises:
            AgentLLMError: If the LLM API call fails.
        """
        try:
            if self._tool_configs:
                return await self._run_with_tools(input_text, thread_id)
            assert self._graph is not None
            return await self._invoke_graph(
                self._graph, input_text, thread_id
            )
        except AgentLLMError:
            raise
        except Exception as exc:
            self._log.error(
                "llm_call_failed", error=str(exc), thread_id=thread_id
            )
            raise AgentLLMError(
                f"Agent '{self.name}' LLM call failed: {exc}"
            ) from exc

    async def _run_with_tools(
        self, input_text: str, thread_id: str
    ) -> RunResult:
        """Run with MCP tool access — graph rebuilt each call."""
        import os

        server_map_named: dict[str, dict[str, object]] = {}
        for i, cfg in enumerate(self._tool_configs):
            key = f"mcp_{i}"
            server_map_named[key] = {
                "command": cfg.command,
                "args": cfg.args,
                "env": cfg.env,
                "transport": cfg.transport,
            }

        self._log.debug("mcp_client_starting", servers=len(self._tool_configs))
        # Suppress MCP subprocess stderr noise (npm warnings, debug output)
        # by temporarily redirecting the stderr file descriptor
        original_fd = os.dup(2)
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull_fd, 2)
        os.close(devnull_fd)
        try:
            client = MultiServerMCPClient(server_map_named)
            tools = await client.get_tools()
        finally:
            os.dup2(original_fd, 2)
            os.close(original_fd)
        self._log.debug("mcp_tools_loaded", tool_count=len(tools))
        graph = self._build_graph(tools=tools)
        return await self._invoke_graph(graph, input_text, thread_id)

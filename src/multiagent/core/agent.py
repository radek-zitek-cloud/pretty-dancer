# pyright: reportUnknownMemberType=false, reportUnusedImport=false, reportUnknownArgumentType=false, reportCallIssue=false, reportUnknownVariableType=false, reportArgumentType=false, reportTypedDictNotRequiredAccess=false, reportUnknownParameterType=false, reportMissingTypeArgument=false
"""LLMAgent — transport-agnostic LLM wrapper with LangGraph."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph

from multiagent.config.settings import Settings
from multiagent.core.costs import CostEntry, CostLedger
from multiagent.core.routing import KeywordRouter, LLMRouter
from multiagent.exceptions import AgentConfigurationError, AgentLLMError


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
    ) -> None:
        """Initialise the agent with a name, settings, checkpointer, and cost ledger."""
        self.name = name
        self._settings = settings
        self._cost_ledger = cost_ledger
        self._router = router
        self._log = structlog.get_logger().bind(agent=name)
        self._system_prompt = self._load_prompt(name, settings.prompts_dir)
        self._checkpointer = checkpointer
        self._llm = ChatOpenAI(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_seconds,
            api_key=settings.openrouter_api_key,  # type: ignore[arg-type]
            base_url=settings.openrouter_base_url,
        )
        self._graph = self._build_graph()

    def _load_prompt(self, name: str, prompts_dir: Path) -> str:
        """Load the system prompt from {prompts_dir}/{name}.md.

        Reads the file contents and strips leading/trailing whitespace.
        The entire file content is the system prompt — no parsing is
        performed at this stage.

        # TODO: parse YAML frontmatter when structured prompts are introduced.
        #       Frontmatter will carry metadata (version, tags, model hints).
        #       Body after frontmatter delimiter (---) becomes the prompt text.

        Args:
            name: Agent name. Used to construct the filename.
            prompts_dir: Directory containing prompt files.

        Returns:
            System prompt string with whitespace stripped.

        Raises:
            AgentConfigurationError: If the prompt file does not exist or
                cannot be read.
        """
        prompt_path = prompts_dir / f"{name}.md"
        try:
            return prompt_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            raise AgentConfigurationError(
                f"Prompt file not found for agent '{name}': {prompt_path}"
            ) from None
        except OSError as exc:
            raise AgentConfigurationError(
                f"Failed to read prompt file for agent '{name}': {exc}"
            ) from exc

    def _build_graph(self) -> CompiledStateGraph:  # type: ignore[type-arg]
        """Build the LangGraph processing graph with AgentState.

        Uses AgentState (extending MessagesState) which maintains a list
        of BaseMessage objects that accumulates across invocations via the
        checkpointer. When a router is configured, a routing node is added
        after the LLM node to determine the next destination.

        Graph structure:
            Without router: llm → END
            With router:    llm → route → END

        Returns:
            Compiled graph with checkpointer attached.
        """

        async def call_llm(state: AgentState, config: RunnableConfig) -> AgentState:  # type: ignore[return-type]
            self._log.debug("llm_call_start", history_length=len(state["messages"]))
            response = await self._llm.ainvoke([
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

        if self._router is not None:
            router = self._router

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
            graph.add_edge("llm", "route")
            graph.add_edge("route", END)
        else:
            graph.add_edge("llm", END)

        return graph.compile(checkpointer=self._checkpointer)

    async def run(self, input_text: str, thread_id: str) -> RunResult:
        """Process input_text with full conversation history for the thread.

        The checkpointer restores prior messages for this thread_id before
        invocation and persists the updated state after. On the first call
        for a thread_id, history is empty — behaviour is identical to the
        stateless design. Subsequent calls include the full prior exchange.

        Args:
            input_text: The message body to process.
            thread_id: Conversation thread identifier.

        Returns:
            RunResult with the LLM response and optional routing decision.

        Raises:
            AgentLLMError: If the LLM API call fails.
        """
        # Namespace thread_id per agent to isolate checkpoint state.
        # Without this, a routing decision (next_agent) set by one agent
        # leaks into another agent's state on the same thread.
        namespaced_thread = f"{self.name}:{thread_id}"
        config = {"configurable": {"thread_id": namespaced_thread}}
        try:
            result = await self._graph.ainvoke(
                {"messages": [HumanMessage(content=input_text)]},
                config=config,
            )
            content = result["messages"][-1].content
            response = content if isinstance(content, str) else str(content)
            next_agent: str | None = result.get("next_agent")
            return RunResult(response=response, next_agent=next_agent)
        except Exception as exc:
            self._log.error("llm_call_failed", error=str(exc), thread_id=thread_id)
            raise AgentLLMError(
                f"Agent '{self.name}' LLM call failed: {exc}"
            ) from exc

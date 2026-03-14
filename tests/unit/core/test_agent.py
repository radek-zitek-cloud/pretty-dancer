# pyright: reportPrivateUsage=false, reportUnknownMemberType=false
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from langgraph.checkpoint.memory import MemorySaver
from pytest_mock import MockerFixture

from multiagent.config.agents import RouterConfig
from multiagent.config.settings import Settings
from multiagent.core.agent import LLMAgent, RunResult
from multiagent.core.routing import KeywordRouter
from multiagent.exceptions import AgentConfigurationError, AgentLLMError


class TestLLMAgentInit:
    def test_loads_system_prompt_from_file(
        self, test_settings: Settings, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        assert agent._system_prompt == "You are a test researcher agent."

    def test_raises_agent_configuration_error_when_prompt_file_missing(
        self, test_settings: Settings, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        with pytest.raises(AgentConfigurationError, match="Prompt file not found"):
            LLMAgent("nonexistent", test_settings, checkpointer, mock_cost_ledger)

    def test_raises_agent_configuration_error_when_prompt_dir_missing(
        self, test_settings: Settings, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        test_settings.prompts_dir = Path("nonexistent/directory")
        with pytest.raises(AgentConfigurationError, match="Prompt file not found"):
            LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)

    def test_name_is_set_correctly(
        self, test_settings: Settings, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        assert agent.name == "researcher"


class TestLLMAgentRun:
    async def test_returns_run_result(
        self, test_settings: Settings, mock_llm: AsyncMock,
        mock_llm_response: str, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        result = await agent.run("test input", "thread-1")
        assert isinstance(result, RunResult)
        assert result.response == mock_llm_response
        assert result.next_agent is None

    async def test_calls_llm_exactly_once_per_run(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        await agent.run("test input", "thread-1")
        mock_llm.assert_called_once()

    async def test_passes_system_prompt_as_system_message(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        await agent.run("test input", "thread-1")
        call_args = mock_llm.call_args[0][0]
        system_msg = call_args[0]
        assert system_msg.content == "You are a test researcher agent."

    async def test_passes_input_as_human_message(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        await agent.run("test input", "thread-1")
        call_args = mock_llm.call_args[0][0]
        human_msg = call_args[1]
        assert human_msg.content == "test input"

    async def test_raises_agent_llm_error_on_llm_failure(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        mock_llm.side_effect = RuntimeError("API error")
        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        with pytest.raises(AgentLLMError, match="LLM call failed"):
            await agent.run("test input", "thread-1")

    async def test_run_is_independent_between_calls(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        result1 = await agent.run("first input", "thread-1")
        result2 = await agent.run("second input", "thread-2")
        assert result1.response == result2.response
        assert mock_llm.call_count == 2


class TestLLMAgentHistory:
    async def test_second_call_includes_first_message_in_history(
        self, test_settings: Settings, mocker: MockerFixture, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        """On the second call with the same thread_id, the LLM receives
        the first HumanMessage + AIMessage + second HumanMessage."""
        from langchain_core.messages import AIMessage

        responses = [
            AIMessage(content="Response to first"),
            AIMessage(content="Response to second"),
        ]
        mock = AsyncMock(side_effect=responses)
        mocker.patch("langchain_openai.ChatOpenAI.ainvoke", side_effect=mock)

        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        await agent.run("first input", "thread-history")
        await agent.run("second input", "thread-history")

        # Second call: HumanMessage(first) + AIMessage(response) + HumanMessage(second)
        second_call_messages = mock.call_args_list[1][0][0]
        # First message is SystemMessage (always prepended), so skip it
        conversation_messages = second_call_messages[1:]  # skip SystemMessage
        assert len(conversation_messages) == 3
        assert conversation_messages[0].content == "first input"
        assert conversation_messages[1].content == "Response to first"
        assert conversation_messages[2].content == "second input"

    async def test_different_thread_ids_have_independent_histories(
        self, test_settings: Settings, mocker: MockerFixture, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        """Different thread_ids do not share history."""
        from langchain_core.messages import AIMessage

        responses = [
            AIMessage(content="Response A"),
            AIMessage(content="Response B"),
        ]
        mock = AsyncMock(side_effect=responses)
        mocker.patch("langchain_openai.ChatOpenAI.ainvoke", side_effect=mock)

        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        await agent.run("input for thread A", "thread-A")
        await agent.run("input for thread B", "thread-B")

        # Each call should only have 1 HumanMessage (no cross-thread leakage)
        for i in range(2):
            call_messages = mock.call_args_list[i][0][0]
            conversation_messages = call_messages[1:]  # skip SystemMessage
            assert len(conversation_messages) == 1

    async def test_same_thread_id_accumulates_messages_across_calls(
        self, test_settings: Settings, mocker: MockerFixture, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        """Three calls on the same thread accumulate 5 conversation messages
        by the third call: H1, A1, H2, A2, H3."""
        from langchain_core.messages import AIMessage

        responses = [
            AIMessage(content="Reply 1"),
            AIMessage(content="Reply 2"),
            AIMessage(content="Reply 3"),
        ]
        mock = AsyncMock(side_effect=responses)
        mocker.patch("langchain_openai.ChatOpenAI.ainvoke", side_effect=mock)

        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        await agent.run("msg 1", "thread-accum")
        await agent.run("msg 2", "thread-accum")
        await agent.run("msg 3", "thread-accum")

        # Third call: SystemMessage + H1 + A1 + H2 + A2 + H3 = 6 total, 5 conversation
        third_call_messages = mock.call_args_list[2][0][0]
        conversation_messages = third_call_messages[1:]  # skip SystemMessage
        assert len(conversation_messages) == 5
        assert conversation_messages[0].content == "msg 1"
        assert conversation_messages[1].content == "Reply 1"
        assert conversation_messages[2].content == "msg 2"
        assert conversation_messages[3].content == "Reply 2"
        assert conversation_messages[4].content == "msg 3"


class TestLLMAgentCostTracking:
    async def test_cost_entry_recorded_on_llm_call(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        await agent.run("test input", "thread-cost")

        mock_cost_ledger.record.assert_called_once()
        entry = mock_cost_ledger.record.call_args[0][0]
        assert entry.agent == "researcher"
        assert entry.thread_id == "thread-cost"
        assert entry.input_tokens == 10
        assert entry.output_tokens == 20
        assert entry.total_tokens == 30
        assert entry.input_unit_price == pytest.approx(0.000003)
        assert entry.output_unit_price == pytest.approx(0.000015)
        assert entry.cost_usd == pytest.approx(0.000330)

    async def test_cost_recording_failure_does_not_fail_agent(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        mock_cost_ledger.record.side_effect = Exception("DB write failed")
        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        # Should complete normally despite record failure
        result = await agent.run("test input", "thread-1")
        assert result.response == "Mocked LLM response for testing."

    async def test_zero_cost_when_pricing_absent(
        self, test_settings: Settings, mocker: MockerFixture, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        from langchain_core.messages import AIMessage

        mock = AsyncMock(
            return_value=AIMessage(
                content="response",
                usage_metadata={
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "total_tokens": 30,
                },
                response_metadata={},
            )
        )
        mocker.patch("langchain_openai.ChatOpenAI.ainvoke", side_effect=mock)

        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        await agent.run("test input", "thread-no-price")

        entry = mock_cost_ledger.record.call_args[0][0]
        assert entry.cost_usd == 0.0
        assert entry.input_unit_price == 0.0
        assert entry.output_unit_price == 0.0


class TestLLMAgentRouting:
    async def test_keyword_router_determines_next_agent(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
        mock_llm_response: str,
        mocker: MockerFixture,
    ) -> None:
        """When a keyword router is configured and output matches a trigger,
        RunResult.next_agent is set to the matching destination."""
        from langchain_core.messages import AIMessage

        mock_response = AsyncMock(
            return_value=AIMessage(
                content="Here is the WRITER BRIEF for the article",
                usage_metadata={
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "total_tokens": 30,
                },
                response_metadata={},
            )
        )
        mocker.patch("langchain_openai.ChatOpenAI.ainvoke", side_effect=mock_response)

        router_config = RouterConfig(
            name="test_gate",
            type="keyword",
            routes={"writer": ["WRITER BRIEF"]},
            default="human",
        )
        router = KeywordRouter(router_config)
        agent = LLMAgent(
            "researcher", test_settings, checkpointer, mock_cost_ledger,
            router=router,
        )
        result = await agent.run("Write something", "thread-route")
        assert result.next_agent == "writer"

    async def test_no_router_returns_none_next_agent(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        """Without a router, RunResult.next_agent is None."""
        agent = LLMAgent("researcher", test_settings, checkpointer, mock_cost_ledger)
        result = await agent.run("test input", "thread-no-route")
        assert result.next_agent is None

    async def test_keyword_router_defaults_when_no_match(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock,
    ) -> None:
        """When no trigger matches, router falls back to default."""
        router_config = RouterConfig(
            name="test_gate",
            type="keyword",
            routes={"writer": ["WRITER BRIEF"]},
            default="human",
        )
        router = KeywordRouter(router_config)
        agent = LLMAgent(
            "researcher", test_settings, checkpointer, mock_cost_ledger,
            router=router,
        )
        # mock_llm returns "Mocked LLM response for testing." — no trigger match
        result = await agent.run("test input", "thread-default")
        assert result.next_agent == "human"


class TestLLMAgentCheckpointIsolation:
    async def test_agents_on_same_thread_have_independent_checkpointer_state(
        self, test_settings: Settings, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock, mocker: MockerFixture,
    ) -> None:
        """Two agents sharing a checkpointer and thread_id must not leak
        next_agent state. Regression test for the writer self-loop bug where
        a shared checkpoint_ns caused the editor's routing decision
        (next_agent='writer') to persist into the writer's graph state."""
        from langchain_core.messages import AIMessage

        router_config = RouterConfig(
            name="test_gate",
            type="keyword",
            routes={"writer": ["WRITER BRIEF"]},
            default="human",
        )
        router = KeywordRouter(router_config)

        response_with_trigger = AsyncMock(
            return_value=AIMessage(
                content="Here is the WRITER BRIEF for the article",
                usage_metadata={
                    "input_tokens": 10, "output_tokens": 20, "total_tokens": 30,
                },
                response_metadata={},
            )
        )
        mocker.patch("langchain_openai.ChatOpenAI.ainvoke", side_effect=response_with_trigger)

        agent_a = LLMAgent(
            "researcher", test_settings, checkpointer, mock_cost_ledger,
            router=router,
        )
        result_a = await agent_a.run("Write about physics", "shared-thread")
        assert result_a.next_agent == "writer"

        plain_response = AsyncMock(
            return_value=AIMessage(
                content="Here is the article about physics.",
                usage_metadata={
                    "input_tokens": 10, "output_tokens": 20, "total_tokens": 30,
                },
                response_metadata={},
            )
        )
        mocker.patch("langchain_openai.ChatOpenAI.ainvoke", side_effect=plain_response)

        agent_b = LLMAgent(
            "critic", test_settings, checkpointer, mock_cost_ledger,
        )
        result_b = await agent_b.run("Edit the article", "shared-thread")
        assert result_b.next_agent is None, (
            f"Agent B inherited next_agent='{result_b.next_agent}' from Agent A's "
            f"checkpoint — checkpoint_ns isolation is broken"
        )


class TestLLMAgentTools:
    def test_graph_without_tools_unchanged(
        self, test_settings: Settings, mock_llm: AsyncMock,
        checkpointer: MemorySaver, mock_cost_ledger: AsyncMock,
    ) -> None:
        """Agent with no tool_configs uses pre-built graph."""
        agent = LLMAgent(
            "researcher", test_settings, checkpointer, mock_cost_ledger,
        )
        assert agent._graph is not None
        assert agent._tool_configs == []

    def test_tool_configs_stored_on_agent(
        self, test_settings: Settings, mock_llm: AsyncMock,
        checkpointer: MemorySaver, mock_cost_ledger: AsyncMock,
    ) -> None:
        """Agent with tool_configs stores them and defers graph build."""
        from multiagent.config.mcp import MCPServerConfig

        configs = [MCPServerConfig(command="echo", args=["test"])]
        agent = LLMAgent(
            "researcher", test_settings, checkpointer, mock_cost_ledger,
            tool_configs=configs,
        )
        assert agent._tool_configs == configs
        assert agent._graph is None  # deferred — built per run()

    async def test_tool_call_invoked_when_llm_requests_tool(
        self, test_settings: Settings, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock, mocker: MockerFixture,
    ) -> None:
        """Full tool round-trip: LLM requests tool, tool executes,
        LLM produces final answer incorporating tool result."""
        from langchain_core.messages import AIMessage, ToolMessage

        from multiagent.config.mcp import MCPServerConfig

        # First LLM call: request a tool call
        tool_request = AIMessage(
            content="",
            tool_calls=[{
                "id": "call_1",
                "name": "search",
                "args": {"query": "test"},
            }],
            usage_metadata={
                "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
            },
            response_metadata={},
        )
        # Second LLM call: final answer after tool result
        final_answer = AIMessage(
            content="Based on the search: result is 42.",
            usage_metadata={
                "input_tokens": 20, "output_tokens": 10, "total_tokens": 30,
            },
            response_metadata={},
        )
        llm_mock = AsyncMock(side_effect=[tool_request, final_answer])
        mocker.patch("langchain_openai.ChatOpenAI.ainvoke", side_effect=llm_mock)

        # Mock MCP client
        from langchain_core.tools import Tool

        mock_tool = Tool(
            name="search",
            description="Search the web",
            func=lambda q: "42",  # type: ignore[misc]
        )

        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[mock_tool])
        mock_client_cls = mocker.patch(
            "multiagent.core.agent.MultiServerMCPClient"
        )
        mock_client_cls.return_value.__aenter__ = AsyncMock(
            return_value=mock_client
        )
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock ToolNode to return a tool result
        mock_tool_node = mocker.patch(
            "multiagent.core.agent.ToolNode",
        )
        mock_tool_node.return_value = mocker.MagicMock(
            side_effect=lambda state: {  # type: ignore[misc]
                "messages": [
                    ToolMessage(
                        content="42",
                        tool_call_id="call_1",
                    )
                ]
            }
        )

        configs = [MCPServerConfig(command="echo", args=["test"])]
        agent = LLMAgent(
            "researcher", test_settings, checkpointer, mock_cost_ledger,
            tool_configs=configs,
        )
        result = await agent.run("What is the answer?", "thread-tools")
        assert "42" in result.response
        assert llm_mock.call_count == 2

    async def test_tools_and_routing_compose_correctly(
        self, test_settings: Settings, checkpointer: MemorySaver,
        mock_cost_ledger: AsyncMock, mocker: MockerFixture,
    ) -> None:
        """Agent with both tools and router: tool loop runs before routing."""
        from langchain_core.messages import AIMessage, ToolMessage

        from multiagent.config.mcp import MCPServerConfig

        # First LLM call: request tool
        tool_request = AIMessage(
            content="",
            tool_calls=[{
                "id": "call_1",
                "name": "search",
                "args": {"query": "test"},
            }],
            usage_metadata={
                "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
            },
            response_metadata={},
        )
        # Second LLM call: final answer with routing trigger
        final_answer = AIMessage(
            content="WRITER BRIEF: the answer is 42. END BRIEF",
            usage_metadata={
                "input_tokens": 20, "output_tokens": 10, "total_tokens": 30,
            },
            response_metadata={},
        )
        llm_mock = AsyncMock(side_effect=[tool_request, final_answer])
        mocker.patch("langchain_openai.ChatOpenAI.ainvoke", side_effect=llm_mock)

        # Mock MCP
        from langchain_core.tools import Tool

        mock_tool = Tool(
            name="search",
            description="Search",
            func=lambda q: "42",  # type: ignore[misc]
        )

        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[mock_tool])
        mock_client_cls = mocker.patch(
            "multiagent.core.agent.MultiServerMCPClient"
        )
        mock_client_cls.return_value.__aenter__ = AsyncMock(
            return_value=mock_client
        )
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_tool_node = mocker.patch("multiagent.core.agent.ToolNode")
        mock_tool_node.return_value = mocker.MagicMock(
            side_effect=lambda state: {  # type: ignore[misc]
                "messages": [
                    ToolMessage(content="42", tool_call_id="call_1")
                ]
            }
        )

        # Router that triggers on "WRITER BRIEF"
        router_config = RouterConfig(
            name="test_gate",
            type="keyword",
            routes={"writer": ["WRITER BRIEF"]},
            default="human",
        )
        router = KeywordRouter(router_config)

        configs = [MCPServerConfig(command="echo", args=["test"])]
        agent = LLMAgent(
            "researcher", test_settings, checkpointer, mock_cost_ledger,
            router=router,
            tool_configs=configs,
        )
        result = await agent.run("Research something", "thread-tools-route")
        # Tool loop ran (2 LLM calls)
        assert llm_mock.call_count == 2
        # Routing ran after tools — detected WRITER BRIEF
        assert result.next_agent == "writer"

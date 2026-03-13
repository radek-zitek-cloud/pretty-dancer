# pyright: reportPrivateUsage=false
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from langgraph.checkpoint.memory import MemorySaver

from multiagent.config.settings import Settings
from multiagent.core.agent import LLMAgent
from multiagent.exceptions import AgentConfigurationError, AgentLLMError


class TestLLMAgentInit:
    def test_loads_system_prompt_from_file(
        self, test_settings: Settings, checkpointer: MemorySaver
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer)
        assert agent._system_prompt == "You are a test researcher agent."

    def test_raises_agent_configuration_error_when_prompt_file_missing(
        self, test_settings: Settings, checkpointer: MemorySaver
    ) -> None:
        with pytest.raises(AgentConfigurationError, match="Prompt file not found"):
            LLMAgent("nonexistent", test_settings, checkpointer)

    def test_raises_agent_configuration_error_when_prompt_dir_missing(
        self, test_settings: Settings, checkpointer: MemorySaver
    ) -> None:
        test_settings.prompts_dir = Path("nonexistent/directory")
        with pytest.raises(AgentConfigurationError, match="Prompt file not found"):
            LLMAgent("researcher", test_settings, checkpointer)

    def test_name_is_set_correctly(
        self, test_settings: Settings, checkpointer: MemorySaver
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer)
        assert agent.name == "researcher"


class TestLLMAgentRun:
    async def test_returns_llm_response_string(
        self, test_settings: Settings, mock_llm: AsyncMock,
        mock_llm_response: str, checkpointer: MemorySaver,
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer)
        result = await agent.run("test input", "thread-1")
        assert result == mock_llm_response

    async def test_calls_llm_exactly_once_per_run(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer)
        await agent.run("test input", "thread-1")
        mock_llm.assert_called_once()

    async def test_passes_system_prompt_as_system_message(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer)
        await agent.run("test input", "thread-1")
        call_args = mock_llm.call_args[0][0]
        system_msg = call_args[0]
        assert system_msg.content == "You are a test researcher agent."

    async def test_passes_input_as_human_message(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer)
        await agent.run("test input", "thread-1")
        call_args = mock_llm.call_args[0][0]
        human_msg = call_args[1]
        assert human_msg.content == "test input"

    async def test_raises_agent_llm_error_on_llm_failure(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
    ) -> None:
        mock_llm.side_effect = RuntimeError("API error")
        agent = LLMAgent("researcher", test_settings, checkpointer)
        with pytest.raises(AgentLLMError, match="LLM call failed"):
            await agent.run("test input", "thread-1")

    async def test_run_is_independent_between_calls(
        self, test_settings: Settings, mock_llm: AsyncMock, checkpointer: MemorySaver,
    ) -> None:
        agent = LLMAgent("researcher", test_settings, checkpointer)
        result1 = await agent.run("first input", "thread-1")
        result2 = await agent.run("second input", "thread-2")
        assert result1 == result2
        assert mock_llm.call_count == 2


class TestLLMAgentHistory:
    async def test_second_call_includes_first_message_in_history(
        self, test_settings: Settings, mocker: pytest.MonkeyPatch, checkpointer: MemorySaver,
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

        agent = LLMAgent("researcher", test_settings, checkpointer)
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
        self, test_settings: Settings, mocker: pytest.MonkeyPatch, checkpointer: MemorySaver,
    ) -> None:
        """Different thread_ids do not share history."""
        from langchain_core.messages import AIMessage

        responses = [
            AIMessage(content="Response A"),
            AIMessage(content="Response B"),
        ]
        mock = AsyncMock(side_effect=responses)
        mocker.patch("langchain_openai.ChatOpenAI.ainvoke", side_effect=mock)

        agent = LLMAgent("researcher", test_settings, checkpointer)
        await agent.run("input for thread A", "thread-A")
        await agent.run("input for thread B", "thread-B")

        # Each call should only have 1 HumanMessage (no cross-thread leakage)
        for i in range(2):
            call_messages = mock.call_args_list[i][0][0]
            conversation_messages = call_messages[1:]  # skip SystemMessage
            assert len(conversation_messages) == 1

    async def test_same_thread_id_accumulates_messages_across_calls(
        self, test_settings: Settings, mocker: pytest.MonkeyPatch, checkpointer: MemorySaver,
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

        agent = LLMAgent("researcher", test_settings, checkpointer)
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

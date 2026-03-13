# pyright: reportPrivateUsage=false
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from multiagent.config.settings import Settings
from multiagent.core.agent import LLMAgent
from multiagent.exceptions import AgentConfigurationError, AgentLLMError


class TestLLMAgentInit:
    def test_loads_system_prompt_from_file(self, test_settings: Settings) -> None:
        agent = LLMAgent("researcher", test_settings)
        assert agent._system_prompt == "You are a test researcher agent."

    def test_raises_agent_configuration_error_when_prompt_file_missing(
        self, test_settings: Settings
    ) -> None:
        with pytest.raises(AgentConfigurationError, match="Prompt file not found"):
            LLMAgent("nonexistent", test_settings)

    def test_raises_agent_configuration_error_when_prompt_dir_missing(
        self, test_settings: Settings
    ) -> None:
        test_settings.prompts_dir = Path("nonexistent/directory")
        with pytest.raises(AgentConfigurationError, match="Prompt file not found"):
            LLMAgent("researcher", test_settings)

    def test_name_is_set_correctly(self, test_settings: Settings) -> None:
        agent = LLMAgent("researcher", test_settings)
        assert agent.name == "researcher"


class TestLLMAgentRun:
    async def test_returns_llm_response_string(
        self, test_settings: Settings, mock_llm: AsyncMock, mock_llm_response: str
    ) -> None:
        agent = LLMAgent("researcher", test_settings)
        result = await agent.run("test input")
        assert result == mock_llm_response

    async def test_calls_llm_exactly_once_per_run(
        self, test_settings: Settings, mock_llm: AsyncMock
    ) -> None:
        agent = LLMAgent("researcher", test_settings)
        await agent.run("test input")
        mock_llm.assert_called_once()

    async def test_passes_system_prompt_as_system_message(
        self, test_settings: Settings, mock_llm: AsyncMock
    ) -> None:
        agent = LLMAgent("researcher", test_settings)
        await agent.run("test input")
        call_args = mock_llm.call_args[0][0]
        system_msg = call_args[0]
        assert system_msg.content == "You are a test researcher agent."

    async def test_passes_input_as_human_message(
        self, test_settings: Settings, mock_llm: AsyncMock
    ) -> None:
        agent = LLMAgent("researcher", test_settings)
        await agent.run("test input")
        call_args = mock_llm.call_args[0][0]
        human_msg = call_args[1]
        assert human_msg.content == "test input"

    async def test_raises_agent_llm_error_on_llm_failure(
        self, test_settings: Settings, mock_llm: AsyncMock
    ) -> None:
        mock_llm.side_effect = RuntimeError("API error")
        agent = LLMAgent("researcher", test_settings)
        with pytest.raises(AgentLLMError, match="LLM call failed"):
            await agent.run("test input")

    async def test_run_is_independent_between_calls(
        self, test_settings: Settings, mock_llm: AsyncMock
    ) -> None:
        agent = LLMAgent("researcher", test_settings)
        result1 = await agent.run("first input")
        result2 = await agent.run("second input")
        assert result1 == result2
        assert mock_llm.call_count == 2

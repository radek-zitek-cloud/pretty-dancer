import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from multiagent.config.settings import Settings
from multiagent.core.runner import AgentRunner
from multiagent.exceptions import AgentLLMError
from multiagent.transport.base import Message


@pytest.fixture
def mock_agent() -> AsyncMock:
    agent = AsyncMock()
    agent.name = "researcher"
    agent.run = AsyncMock(return_value="LLM response text")
    return agent


@pytest.fixture
def mock_transport() -> AsyncMock:
    transport = AsyncMock()
    transport.receive = AsyncMock(return_value=None)
    transport.send = AsyncMock()
    transport.ack = AsyncMock()
    return transport


@pytest.fixture
def sample_msg() -> Message:
    return Message(
        id=1,
        from_agent="human",
        to_agent="researcher",
        body="What is quantum entanglement?",
        subject="research",
    )


@pytest.fixture
def runner(
    mock_agent: AsyncMock, mock_transport: AsyncMock, test_settings: Settings
) -> AgentRunner:
    return AgentRunner(mock_agent, mock_transport, test_settings, next_agent="critic")


@pytest.fixture
def terminal_runner(
    mock_agent: AsyncMock, mock_transport: AsyncMock, test_settings: Settings
) -> AgentRunner:
    return AgentRunner(mock_agent, mock_transport, test_settings, next_agent=None)


class TestAgentRunnerRunOnce:
    async def test_returns_false_when_inbox_empty(
        self, runner: AgentRunner, mock_transport: AsyncMock
    ) -> None:
        mock_transport.receive.return_value = None
        result = await runner.run_once()
        assert result is False

    async def test_returns_true_when_message_processed(
        self, runner: AgentRunner, mock_transport: AsyncMock, sample_msg: Message
    ) -> None:
        mock_transport.receive.return_value = sample_msg
        result = await runner.run_once()
        assert result is True

    async def test_calls_agent_run_with_message_body(
        self,
        runner: AgentRunner,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        sample_msg: Message,
    ) -> None:
        mock_transport.receive.return_value = sample_msg
        await runner.run_once()
        mock_agent.run.assert_called_once_with(sample_msg.body)

    async def test_acks_message_after_successful_processing(
        self, runner: AgentRunner, mock_transport: AsyncMock, sample_msg: Message
    ) -> None:
        mock_transport.receive.return_value = sample_msg
        await runner.run_once()
        mock_transport.ack.assert_called_once_with(sample_msg.id)

    async def test_forwards_response_to_next_agent_when_configured(
        self, runner: AgentRunner, mock_transport: AsyncMock, sample_msg: Message
    ) -> None:
        mock_transport.receive.return_value = sample_msg
        await runner.run_once()
        mock_transport.send.assert_called_once()
        sent_msg = mock_transport.send.call_args[0][0]
        assert sent_msg.to_agent == "critic"
        assert sent_msg.body == "LLM response text"

    async def test_does_not_forward_when_next_agent_is_none(
        self, terminal_runner: AgentRunner, mock_transport: AsyncMock, sample_msg: Message
    ) -> None:
        mock_transport.receive.return_value = sample_msg
        await terminal_runner.run_once()
        mock_transport.send.assert_not_called()

    async def test_preserves_thread_id_in_forwarded_message(
        self, runner: AgentRunner, mock_transport: AsyncMock, sample_msg: Message
    ) -> None:
        mock_transport.receive.return_value = sample_msg
        await runner.run_once()
        sent_msg = mock_transport.send.call_args[0][0]
        assert sent_msg.thread_id == sample_msg.thread_id

    async def test_sets_parent_id_in_forwarded_message(
        self, runner: AgentRunner, mock_transport: AsyncMock, sample_msg: Message
    ) -> None:
        mock_transport.receive.return_value = sample_msg
        await runner.run_once()
        sent_msg = mock_transport.send.call_args[0][0]
        assert sent_msg.parent_id == sample_msg.id


class TestAgentRunnerRetry:
    async def test_retries_on_agent_llm_error(
        self,
        runner: AgentRunner,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        sample_msg: Message,
    ) -> None:
        mock_transport.receive.return_value = sample_msg
        mock_agent.run.side_effect = [
            AgentLLMError("fail 1"),
            AgentLLMError("fail 2"),
            "success",
        ]
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await runner.run_once()
        assert result is True

    async def test_succeeds_after_transient_failure(
        self,
        runner: AgentRunner,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        sample_msg: Message,
    ) -> None:
        mock_transport.receive.return_value = sample_msg
        mock_agent.run.side_effect = [AgentLLMError("transient"), "recovered"]
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await runner.run_once()
        assert result is True
        assert mock_agent.run.call_count == 2

    async def test_raises_after_max_retries_exhausted(
        self,
        runner: AgentRunner,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        sample_msg: Message,
    ) -> None:
        mock_transport.receive.return_value = sample_msg
        mock_agent.run.side_effect = AgentLLMError("persistent failure")
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(AgentLLMError):
                await runner.run_once()

    async def test_exponential_backoff_between_retries(
        self,
        runner: AgentRunner,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        sample_msg: Message,
    ) -> None:
        mock_transport.receive.return_value = sample_msg
        mock_agent.run.side_effect = AgentLLMError("keep failing")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(AgentLLMError):
                await runner.run_once()
        # Backoff: 2.0, 4.0, 8.0 (3 retries before final raise)
        sleep_values = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_values == [2.0, 4.0, 8.0]


class TestAgentRunnerRunLoop:
    async def test_loop_exits_on_cancelled_error(
        self, runner: AgentRunner, mock_transport: AsyncMock
    ) -> None:
        mock_transport.receive.side_effect = asyncio.CancelledError
        with pytest.raises(asyncio.CancelledError):
            await runner.run_loop()

    async def test_loop_sleeps_when_inbox_empty(
        self, runner: AgentRunner, mock_transport: AsyncMock
    ) -> None:
        call_count = 0

        async def receive_then_cancel(agent_name: str) -> Message | None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError
            return None

        mock_transport.receive.side_effect = receive_then_cancel
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(asyncio.CancelledError):
                await runner.run_loop()
        mock_sleep.assert_called_once()

    async def test_loop_processes_messages_without_sleep_when_inbox_has_messages(
        self,
        runner: AgentRunner,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        sample_msg: Message,
    ) -> None:
        call_count = 0

        async def receive_then_cancel(agent_name: str) -> Message | None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError
            return sample_msg

        mock_transport.receive.side_effect = receive_then_cancel
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(asyncio.CancelledError):
                await runner.run_loop()
        mock_sleep.assert_not_called()

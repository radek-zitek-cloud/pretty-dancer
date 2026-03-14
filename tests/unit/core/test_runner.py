import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from multiagent.config.settings import Settings
from multiagent.core.agent import RunResult
from multiagent.core.runner import AgentRunner
from multiagent.core.shutdown import ShutdownMonitor
from multiagent.exceptions import AgentLLMError
from multiagent.transport.base import Message


@pytest.fixture
def mock_agent() -> AsyncMock:
    agent = AsyncMock()
    agent.name = "researcher"
    agent.run = AsyncMock(return_value=RunResult(response="LLM response text"))
    return agent


@pytest.fixture
def mock_transport() -> AsyncMock:
    transport = AsyncMock()
    transport.receive = AsyncMock(return_value=None)
    transport.send = AsyncMock()
    transport.ack = AsyncMock()
    transport.thread_messages_tail = AsyncMock(return_value=[])
    transport.thread_message_count = AsyncMock(return_value=0)
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
        mock_agent.run.assert_called_once_with(sample_msg.body, sample_msg.thread_id)

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

    async def test_passes_thread_id_to_agent_run(
        self,
        runner: AgentRunner,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        sample_msg: Message,
    ) -> None:
        mock_transport.receive.return_value = sample_msg
        await runner.run_once()
        mock_agent.run.assert_called_once_with(sample_msg.body, sample_msg.thread_id)

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
            RunResult(response="success"),
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
        mock_agent.run.side_effect = [AgentLLMError("transient"), RunResult(response="recovered")]
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

    async def test_loop_exits_when_shutdown_monitor_signals_stop(
        self,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        test_settings: Settings,
        tmp_path: Path,
    ) -> None:
        monitor = ShutdownMonitor(tmp_path)
        runner = AgentRunner(
            mock_agent, mock_transport, test_settings, shutdown_monitor=monitor
        )
        monitor.request_stop("researcher")
        # run_loop raises CancelledError so TaskGroup cleans up properly
        with pytest.raises(asyncio.CancelledError):
            await runner.run_loop()

    async def test_loop_continues_when_shutdown_monitor_has_no_sentinel(
        self,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        test_settings: Settings,
        tmp_path: Path,
    ) -> None:
        monitor = ShutdownMonitor(tmp_path)
        runner = AgentRunner(
            mock_agent, mock_transport, test_settings, shutdown_monitor=monitor
        )
        call_count = 0

        async def receive_then_cancel(agent_name: str) -> Message | None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError
            return None

        mock_transport.receive.side_effect = receive_then_cancel
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(asyncio.CancelledError):
                await runner.run_loop()
        # Verify it polled at least twice (didn't exit early)
        assert call_count == 2


class TestLoopDetection:
    async def test_loop_detected_when_threshold_consecutive_self_sends(
        self,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        test_settings: Settings,
        sample_msg: Message,
    ) -> None:
        """N consecutive self-sends → dispatch suppressed."""
        runner = AgentRunner(
            mock_agent, mock_transport, test_settings,
            next_agent="researcher",
        )
        mock_transport.receive.return_value = sample_msg
        mock_transport.thread_messages_tail.return_value = [
            ("researcher", "researcher"),
            ("researcher", "researcher"),
            ("researcher", "researcher"),
        ]
        await runner.run_once()
        mock_transport.send.assert_not_called()

    async def test_loop_not_detected_below_threshold(
        self,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        test_settings: Settings,
        sample_msg: Message,
    ) -> None:
        """N-1 self-sends → dispatch proceeds."""
        runner = AgentRunner(
            mock_agent, mock_transport, test_settings,
            next_agent="researcher",
        )
        mock_transport.receive.return_value = sample_msg
        mock_transport.thread_messages_tail.return_value = [
            ("researcher", "researcher"),
            ("researcher", "researcher"),
        ]
        await runner.run_once()
        mock_transport.send.assert_called_once()

    async def test_loop_not_detected_when_recipient_differs(
        self,
        runner: AgentRunner,
        mock_transport: AsyncMock,
        sample_msg: Message,
    ) -> None:
        """Different recipient → no query, dispatch proceeds."""
        mock_transport.receive.return_value = sample_msg
        await runner.run_once()
        mock_transport.thread_messages_tail.assert_not_called()
        mock_transport.send.assert_called_once()

    async def test_loop_not_detected_when_disabled(
        self,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        test_settings: Settings,
        sample_msg: Message,
    ) -> None:
        """threshold=0 → no detection regardless of messages."""
        test_settings.agent_loop_detection_threshold = 0
        runner = AgentRunner(
            mock_agent, mock_transport, test_settings,
            next_agent="researcher",
        )
        mock_transport.receive.return_value = sample_msg
        mock_transport.thread_messages_tail.return_value = [
            ("researcher", "researcher"),
            ("researcher", "researcher"),
            ("researcher", "researcher"),
        ]
        await runner.run_once()
        mock_transport.thread_messages_tail.assert_not_called()
        mock_transport.send.assert_called_once()

    async def test_loop_detection_resets_after_non_self_send(
        self,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        test_settings: Settings,
        sample_msg: Message,
    ) -> None:
        """Streak broken by a non-self-send → no loop detected."""
        runner = AgentRunner(
            mock_agent, mock_transport, test_settings,
            next_agent="researcher",
        )
        mock_transport.receive.return_value = sample_msg
        # Most recent 3: one from another agent breaks the streak
        mock_transport.thread_messages_tail.return_value = [
            ("researcher", "researcher"),
            ("human", "researcher"),
            ("researcher", "researcher"),
        ]
        await runner.run_once()
        mock_transport.send.assert_called_once()

    async def test_routing_loop_detected_event_logged(
        self,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        test_settings: Settings,
        sample_msg: Message,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop detection logs WARNING and suppresses dispatch."""
        runner = AgentRunner(
            mock_agent, mock_transport, test_settings,
            next_agent="researcher",
        )
        mock_transport.receive.return_value = sample_msg
        mock_transport.thread_messages_tail.return_value = [
            ("researcher", "researcher"),
            ("researcher", "researcher"),
            ("researcher", "researcher"),
        ]
        result = await runner.run_once()
        assert result is True
        mock_transport.send.assert_not_called()
        # Verify the warning was logged (captured by structlog to stderr/stdout)
        captured = capsys.readouterr()
        assert "routing_loop_detected" in captured.out


class TestMaxMessages:
    async def test_dispatch_suppressed_when_max_reached(
        self,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        test_settings: Settings,
        sample_msg: Message,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """thread count >= max → dispatch suppressed + WARNING logged."""
        test_settings.agent_max_messages_per_thread = 5
        runner = AgentRunner(
            mock_agent, mock_transport, test_settings,
            next_agent="critic",
        )
        mock_transport.receive.return_value = sample_msg
        mock_transport.thread_message_count.return_value = 5
        result = await runner.run_once()
        assert result is True
        mock_transport.send.assert_not_called()
        captured = capsys.readouterr()
        assert "max_messages_reached" in captured.out

    async def test_dispatch_proceeds_below_max(
        self,
        mock_agent: AsyncMock,
        mock_transport: AsyncMock,
        test_settings: Settings,
        sample_msg: Message,
    ) -> None:
        """thread count < max → normal dispatch."""
        test_settings.agent_max_messages_per_thread = 5
        runner = AgentRunner(
            mock_agent, mock_transport, test_settings,
            next_agent="critic",
        )
        mock_transport.receive.return_value = sample_msg
        mock_transport.thread_message_count.return_value = 4
        await runner.run_once()
        mock_transport.send.assert_called_once()

    async def test_max_messages_disabled_when_zero(
        self,
        runner: AgentRunner,
        mock_transport: AsyncMock,
        sample_msg: Message,
    ) -> None:
        """max=0 → no suppression regardless of count."""
        mock_transport.receive.return_value = sample_msg
        mock_transport.thread_message_count.return_value = 1000
        await runner.run_once()
        mock_transport.thread_message_count.assert_not_called()
        mock_transport.send.assert_called_once()

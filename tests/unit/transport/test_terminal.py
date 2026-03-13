from unittest.mock import AsyncMock, patch

import pytest

from multiagent.transport.base import Message
from multiagent.transport.terminal import TerminalTransport

_PATCH_TARGET = "multiagent.transport.terminal.asyncio.to_thread"


def _transport() -> TerminalTransport:
    return TerminalTransport()


class TestTerminalTransportReceive:
    async def test_receive_returns_message_with_user_input(self) -> None:
        t = _transport()
        with patch(_PATCH_TARGET, new_callable=AsyncMock) as m:
            m.return_value = "hello world"
            result = await t.receive("agent")
        assert result is not None
        assert result.body == "hello world"
        assert result.to_agent == "agent"

    async def test_receive_returns_none_on_empty_input(self) -> None:
        t = _transport()
        with patch(_PATCH_TARGET, new_callable=AsyncMock) as m:
            m.return_value = "   "
            result = await t.receive("agent")
        assert result is None

    async def test_receive_returns_none_on_eof(self) -> None:
        t = _transport()
        with patch(_PATCH_TARGET, new_callable=AsyncMock) as m:
            m.side_effect = EOFError
            result = await t.receive("agent")
        assert result is None

    async def test_receive_sets_all_timestamps_to_utc_now(self) -> None:
        t = _transport()
        with patch(_PATCH_TARGET, new_callable=AsyncMock) as m:
            m.return_value = "hi"
            result = await t.receive("agent")
        assert result is not None
        assert result.created_at is not None
        assert result.sent_at is not None
        assert result.received_at is not None
        assert result.created_at.tzinfo is not None
        assert result.sent_at.tzinfo is not None
        assert result.received_at.tzinfo is not None

    async def test_receive_sets_from_agent_to_human(self) -> None:
        t = _transport()
        with patch(_PATCH_TARGET, new_callable=AsyncMock) as m:
            m.return_value = "hi"
            result = await t.receive("agent")
        assert result is not None
        assert result.from_agent == "human"


class TestTerminalTransportSend:
    async def test_send_prints_formatted_line_to_stdout(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        t = _transport()
        msg = Message(from_agent="bot", to_agent="human", body="hello")
        await t.send(msg)
        captured = capsys.readouterr()
        assert "[bot] \u2192 [human]: hello" in captured.out

    async def test_send_sets_sent_at_on_message_object(self) -> None:
        t = _transport()
        msg = Message(from_agent="bot", to_agent="human", body="hello")
        assert msg.sent_at is None
        await t.send(msg)
        assert msg.sent_at is not None
        assert msg.sent_at.tzinfo is not None


class TestTerminalTransportNoOps:
    async def test_ack_does_not_raise(self) -> None:
        t = _transport()
        await t.ack(42)

    async def test_known_agents_returns_empty_list(self) -> None:
        t = _transport()
        result = await t.known_agents()
        assert result == []

    async def test_close_does_not_raise(self) -> None:
        t = _transport()
        await t.close()

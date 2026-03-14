# pyright: reportPrivateUsage=false
from datetime import datetime

import aiosqlite
import pytest
import pytest_asyncio

from multiagent.config.settings import Settings
from multiagent.exceptions import MessageAcknowledgementError
from multiagent.transport.base import Message
from multiagent.transport.sqlite import SQLiteTransport


@pytest_asyncio.fixture
async def transport():
    settings = Settings(
        greeting_secret="test-secret",  # type: ignore[call-arg]
        openrouter_api_key="test-key-not-real",  # type: ignore[call-arg]
        transport_backend="sqlite",  # type: ignore[call-arg]
        sqlite_db_path=":memory:",  # type: ignore[call-arg]
        sqlite_poll_interval_seconds=1.0,  # type: ignore[call-arg]
    )
    t = SQLiteTransport(settings)
    yield t
    await t.close()


def _msg(
    from_agent: str = "sender",
    to_agent: str | list[str] = "receiver",
    body: str = "hello",
) -> Message:
    return Message(from_agent=from_agent, to_agent=to_agent, body=body)


async def _count_rows(
    conn: aiosqlite.Connection, where: str = "", params: tuple[object, ...] = ()
) -> int:
    sql = "SELECT count(*) FROM messages"
    if where:
        sql += f" WHERE {where}"
    cursor = await conn.execute(sql, params)
    row = await cursor.fetchone()
    assert row is not None
    return int(row[0])


class TestSQLiteTransportSchema:
    async def test_schema_created_on_first_use(
        self, transport: SQLiteTransport
    ) -> None:
        conn = await transport._get_connection()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
        )
        row = await cursor.fetchone()
        assert row is not None

    async def test_schema_creation_is_idempotent(
        self, transport: SQLiteTransport
    ) -> None:
        await transport._get_connection()
        await transport._ensure_schema()
        conn = await transport._get_connection()
        cursor = await conn.execute(
            "SELECT count(*) FROM sqlite_master "
            "WHERE type='table' AND name='messages'"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == 1


class TestSQLiteTransportSend:
    async def test_send_single_recipient_persists_one_row(
        self, transport: SQLiteTransport
    ) -> None:
        await transport.send(_msg())
        conn = await transport._get_connection()
        assert await _count_rows(conn) == 1

    async def test_send_sets_sent_at_on_row(
        self, transport: SQLiteTransport
    ) -> None:
        await transport.send(_msg())
        conn = await transport._get_connection()
        cursor = await conn.execute("SELECT sent_at FROM messages")
        row = await cursor.fetchone()
        assert row is not None
        assert row["sent_at"] is not None

    async def test_send_list_recipients_persists_one_row_per_recipient(
        self, transport: SQLiteTransport
    ) -> None:
        await transport.send(_msg(to_agent=["a", "b", "c"]))
        conn = await transport._get_connection()
        assert await _count_rows(conn) == 3

    async def test_send_broadcast_fans_out_to_known_agents(
        self, transport: SQLiteTransport
    ) -> None:
        await transport.send(_msg(to_agent="agent_a"))
        await transport.send(_msg(to_agent="agent_b"))
        await transport.send(_msg(to_agent="*", body="broadcast"))
        conn = await transport._get_connection()
        assert await _count_rows(conn, "body='broadcast'") == 2

    async def test_send_broadcast_with_no_known_agents_logs_warning_and_returns(
        self, transport: SQLiteTransport
    ) -> None:
        await transport.send(_msg(to_agent="*"))
        conn = await transport._get_connection()
        assert await _count_rows(conn) == 0


class TestSQLiteTransportReceive:
    async def test_receive_returns_none_when_inbox_empty(
        self, transport: SQLiteTransport
    ) -> None:
        result = await transport.receive("agent")
        assert result is None

    async def test_receive_returns_oldest_message_first(
        self, transport: SQLiteTransport
    ) -> None:
        await transport.send(_msg(to_agent="agent", body="first"))
        await transport.send(_msg(to_agent="agent", body="second"))
        result = await transport.receive("agent")
        assert result is not None
        assert result.body == "first"

    async def test_receive_sets_received_at(
        self, transport: SQLiteTransport
    ) -> None:
        await transport.send(_msg(to_agent="agent"))
        result = await transport.receive("agent")
        assert result is not None
        assert result.received_at is not None
        assert result.received_at.tzinfo is not None

    async def test_receive_does_not_return_processed_messages(
        self, transport: SQLiteTransport
    ) -> None:
        await transport.send(_msg(to_agent="agent"))
        msg = await transport.receive("agent")
        assert msg is not None
        assert msg.id is not None
        await transport.ack(msg.id)
        result = await transport.receive("agent")
        assert result is None

    async def test_receive_only_returns_messages_for_named_agent(
        self, transport: SQLiteTransport
    ) -> None:
        await transport.send(_msg(to_agent="other_agent"))
        result = await transport.receive("agent")
        assert result is None


class TestSQLiteTransportAck:
    async def test_ack_sets_processed_at(
        self, transport: SQLiteTransport
    ) -> None:
        await transport.send(_msg(to_agent="agent"))
        msg = await transport.receive("agent")
        assert msg is not None
        assert msg.id is not None
        await transport.ack(msg.id)
        conn = await transport._get_connection()
        cursor = await conn.execute(
            "SELECT processed_at FROM messages WHERE id = ?", (msg.id,)
        )
        row = await cursor.fetchone()
        assert row is not None
        iso_value: str = row["processed_at"]
        assert iso_value is not None
        dt = datetime.fromisoformat(iso_value)
        assert dt.tzinfo is not None

    async def test_ack_prevents_redelivery_on_next_receive(
        self, transport: SQLiteTransport
    ) -> None:
        await transport.send(_msg(to_agent="agent"))
        msg = await transport.receive("agent")
        assert msg is not None
        assert msg.id is not None
        await transport.ack(msg.id)
        result = await transport.receive("agent")
        assert result is None

    async def test_ack_nonexistent_id_raises_message_acknowledgement_error(
        self, transport: SQLiteTransport
    ) -> None:
        with pytest.raises(MessageAcknowledgementError):
            await transport.ack(99999)


class TestSQLiteTransportKnownAgents:
    async def test_known_agents_returns_empty_before_any_sends(
        self, transport: SQLiteTransport
    ) -> None:
        result = await transport.known_agents()
        assert result == []

    async def test_known_agents_returns_distinct_sorted_names_after_sends(
        self, transport: SQLiteTransport
    ) -> None:
        await transport.send(_msg(to_agent="charlie"))
        await transport.send(_msg(to_agent="alice"))
        await transport.send(_msg(to_agent="bob"))
        await transport.send(_msg(to_agent="alice"))
        result = await transport.known_agents()
        assert result == ["alice", "bob", "charlie"]


class TestSQLiteTransportHumanRecipient:
    async def test_human_is_valid_recipient(
        self, transport: SQLiteTransport
    ) -> None:
        """Messages addressed to 'human' can be sent and received."""
        await transport.send(_msg(from_agent="architect", to_agent="human", body="reply"))
        result = await transport.receive("human")
        assert result is not None
        assert result.from_agent == "architect"
        assert result.to_agent == "human"
        assert result.body == "reply"


class TestSQLiteTransportThreadMessagesTail:
    async def test_returns_most_recent_first(
        self, transport: SQLiteTransport
    ) -> None:
        tid = "tail-thread"
        await transport.send(Message(from_agent="a", to_agent="b", body="1", thread_id=tid))
        await transport.send(Message(from_agent="b", to_agent="c", body="2", thread_id=tid))
        await transport.send(Message(from_agent="c", to_agent="d", body="3", thread_id=tid))
        result = await transport.thread_messages_tail(tid, 3)
        assert result == [("c", "d"), ("b", "c"), ("a", "b")]

    async def test_respects_limit(
        self, transport: SQLiteTransport
    ) -> None:
        tid = "limit-thread"
        await transport.send(Message(from_agent="a", to_agent="b", body="1", thread_id=tid))
        await transport.send(Message(from_agent="b", to_agent="c", body="2", thread_id=tid))
        await transport.send(Message(from_agent="c", to_agent="d", body="3", thread_id=tid))
        result = await transport.thread_messages_tail(tid, 2)
        assert len(result) == 2
        assert result[0] == ("c", "d")

    async def test_returns_empty_for_unknown_thread(
        self, transport: SQLiteTransport
    ) -> None:
        result = await transport.thread_messages_tail("nonexistent", 5)
        assert result == []


class TestSQLiteTransportThreadMessageCount:
    async def test_returns_correct_count(
        self, transport: SQLiteTransport
    ) -> None:
        tid = "count-thread"
        await transport.send(Message(from_agent="a", to_agent="b", body="1", thread_id=tid))
        await transport.send(Message(from_agent="b", to_agent="c", body="2", thread_id=tid))
        count = await transport.thread_message_count(tid)
        assert count == 2

    async def test_returns_zero_for_unknown_thread(
        self, transport: SQLiteTransport
    ) -> None:
        count = await transport.thread_message_count("nonexistent")
        assert count == 0


class TestSQLiteTransportClose:
    async def test_close_is_idempotent(
        self, transport: SQLiteTransport
    ) -> None:
        await transport._get_connection()
        await transport.close()
        await transport.close()

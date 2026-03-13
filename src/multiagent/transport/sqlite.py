"""SQLite-backed transport adapter.

Persists messages in a local SQLite database using aiosqlite.
All timestamps are stored as ISO8601 TEXT in UTC. Connection is
opened lazily on first use with WAL mode enabled.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import aiosqlite
import structlog

from multiagent.exceptions import MessageAcknowledgementError
from multiagent.transport.base import Message, Transport

if TYPE_CHECKING:
    from pathlib import Path

    from multiagent.config.settings import Settings

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    from_agent    TEXT     NOT NULL,
    to_agent      TEXT     NOT NULL,
    subject       TEXT     NOT NULL DEFAULT '',
    body          TEXT     NOT NULL DEFAULT '',
    thread_id     TEXT     NOT NULL,
    parent_id     INTEGER  REFERENCES messages(id),
    created_at    TEXT     NOT NULL,
    sent_at       TEXT,
    received_at   TEXT,
    processed_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_inbox
    ON messages(to_agent, processed_at, created_at);

CREATE INDEX IF NOT EXISTS idx_thread
    ON messages(thread_id, created_at);
"""


class SQLiteTransport(Transport):
    """Transport adapter backed by a local SQLite database.

    Uses aiosqlite for async access. Connection is opened lazily on
    first use with WAL journal mode and foreign keys enabled. Schema
    is applied idempotently via CREATE IF NOT EXISTS.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialise with database path and poll interval from settings."""
        self.db_path: Path = settings.sqlite_db_path
        self._poll_interval: float = settings.sqlite_poll_interval_seconds
        self._conn: aiosqlite.Connection | None = None
        self._log = structlog.get_logger().bind(transport="sqlite")

    async def _get_connection(self) -> aiosqlite.Connection:
        """Open or return the existing database connection.

        On first call, opens the connection, enables WAL mode and
        foreign keys, and applies the schema idempotently.
        """
        if self._conn is None:
            self._conn = await aiosqlite.connect(str(self.db_path))
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL;")
            await self._conn.execute("PRAGMA foreign_keys=ON;")
            await self._ensure_schema()
        return self._conn

    async def _ensure_schema(self) -> None:
        """Apply the messages table schema idempotently."""
        conn = self._conn
        assert conn is not None
        await conn.executescript(_SCHEMA_SQL)

    def _to_iso(self, dt: datetime | None) -> str | None:
        """Serialise a UTC datetime to ISO8601 string for storage."""
        return dt.isoformat() if dt is not None else None

    def _from_iso(self, value: str | None) -> datetime | None:
        """Deserialise an ISO8601 string from storage to UTC datetime."""
        return datetime.fromisoformat(value) if value is not None else None

    def _row_to_message(self, row: aiosqlite.Row) -> Message:
        """Convert a database row to a Message instance."""
        return Message(
            id=row["id"],
            from_agent=row["from_agent"],
            to_agent=row["to_agent"],
            subject=row["subject"],
            body=row["body"],
            thread_id=row["thread_id"],
            parent_id=row["parent_id"],
            created_at=self._from_iso(row["created_at"]),
            sent_at=self._from_iso(row["sent_at"]),
            received_at=self._from_iso(row["received_at"]),
            processed_at=self._from_iso(row["processed_at"]),
        )

    async def receive(self, agent_name: str) -> Message | None:
        """Fetch the next unprocessed message for agent_name.

        Non-blocking. Returns None immediately if the inbox is empty.
        Sets received_at to UTC now on the returned Message.

        Args:
            agent_name: The agent whose inbox to query.

        Returns:
            Oldest unprocessed Message for agent_name, or None.
        """
        conn = await self._get_connection()
        cursor = await conn.execute(
            """
            SELECT * FROM messages
            WHERE to_agent = ? AND processed_at IS NULL
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (agent_name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        now = datetime.now(UTC)
        await conn.execute(
            "UPDATE messages SET received_at = ? WHERE id = ?",
            (self._to_iso(now), row["id"]),
        )
        await conn.commit()

        msg = self._row_to_message(row)
        msg.received_at = now
        return msg

    async def send(self, message: Message) -> None:
        """Deliver a message, handling fanout for lists and broadcast.

        Sets sent_at to UTC now on every persisted row.

        Args:
            message: Message to deliver. to_agent may be str, list, "*".
        """
        recipients: list[str]

        if isinstance(message.to_agent, list):
            recipients = message.to_agent
        elif message.to_agent == "*":
            recipients = await self.known_agents()
            if not recipients:
                self._log.warning(
                    "broadcast_no_known_agents",
                    thread_id=message.thread_id,
                )
                return
        else:
            recipients = [message.to_agent]

        now = datetime.now(UTC)
        conn = await self._get_connection()

        for recipient in recipients:
            await conn.execute(
                """
                INSERT INTO messages
                    (from_agent, to_agent, subject, body,
                     thread_id, parent_id, created_at, sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.from_agent,
                    recipient,
                    message.subject,
                    message.body,
                    message.thread_id,
                    message.parent_id,
                    self._to_iso(message.created_at),
                    self._to_iso(now),
                ),
            )

        await conn.commit()

    async def ack(self, message_id: int) -> None:
        """Mark a message as processed. Sets processed_at to UTC now.

        Args:
            message_id: The id of the Message to acknowledge.

        Raises:
            MessageAcknowledgementError: If message_id does not exist.
        """
        conn = await self._get_connection()
        now = datetime.now(UTC)
        cursor = await conn.execute(
            "UPDATE messages SET processed_at = ? WHERE id = ?",
            (self._to_iso(now), message_id),
        )
        if cursor.rowcount == 0:
            raise MessageAcknowledgementError(
                f"No message found with id={message_id}"
            )
        await conn.commit()

    async def known_agents(self) -> list[str]:
        """Return all agent names ever seen as to_agent recipients.

        Returns:
            Sorted list of distinct agent name strings.
        """
        conn = await self._get_connection()
        cursor = await conn.execute(
            "SELECT DISTINCT to_agent FROM messages ORDER BY to_agent"
        )
        rows = await cursor.fetchall()
        return [row["to_agent"] for row in rows]

    async def get_thread(self, thread_id: str) -> list[Message]:
        """Return all messages belonging to a thread, ordered by created_at.

        This method is for test inspection and debugging only. It is not part
        of the Transport ABC and must not be called from agent or runner code.

        Args:
            thread_id: The UUID identifying the conversation thread.

        Returns:
            List of Message objects in chronological order.
        """
        conn = await self._get_connection()
        cursor = await conn.execute(
            "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
            (thread_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_message(row) for row in rows]

    async def close(self) -> None:
        """Release the database connection. Idempotent."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

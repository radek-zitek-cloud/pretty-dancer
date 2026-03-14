# pyright: reportPrivateUsage=false
"""Tests for the ``multiagent listen`` command."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import aiosqlite
import pytest

from multiagent.config.settings import Settings


def _make_settings(db_path: str) -> Settings:
    return Settings(
        greeting_secret="test-secret",  # type: ignore[call-arg]
        openrouter_api_key="test-key",  # type: ignore[call-arg]
        transport_backend="sqlite",  # type: ignore[call-arg]
        sqlite_db_path=db_path,  # type: ignore[call-arg]
        sqlite_poll_interval_seconds=0.05,  # type: ignore[call-arg]
        chat_reply_timeout_seconds=5.0,  # type: ignore[call-arg]
    )


async def _init_db(db_path: str) -> None:
    """Create the messages table in a fresh database."""
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript(
            """\
            CREATE TABLE IF NOT EXISTS messages (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                from_agent    TEXT NOT NULL,
                to_agent      TEXT NOT NULL,
                subject       TEXT NOT NULL DEFAULT '',
                body          TEXT NOT NULL DEFAULT '',
                thread_id     TEXT NOT NULL,
                parent_id     INTEGER REFERENCES messages(id),
                created_at    TEXT NOT NULL,
                sent_at       TEXT,
                received_at   TEXT,
                processed_at  TEXT
            );
            """
        )


async def _insert_message(
    db_path: str,
    *,
    from_agent: str = "architect",
    to_agent: str = "human",
    body: str = "Hello human",
    thread_id: str = "aaaaaaaa-0000-0000-0000-000000000001",
) -> int:
    """Insert a message and return its id."""
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute(
            """\
            INSERT INTO messages (from_agent, to_agent, body, thread_id, created_at, sent_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (from_agent, to_agent, body, thread_id, now, now),
        )
        await conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


async def _is_processed(db_path: str, msg_id: int) -> bool:
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT processed_at FROM messages WHERE id = ?", (msg_id,)
        )
        row = await cursor.fetchone()
        assert row is not None
        return row["processed_at"] is not None


class TestListenCommand:
    @pytest.fixture
    def db_path(self, tmp_path: object) -> str:
        from pathlib import Path

        assert isinstance(tmp_path, Path)
        return str(tmp_path / "test_listen.db")

    async def test_prints_incoming_message(
        self, db_path: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Listen should display a message addressed to human."""
        await _init_db(db_path)
        await _insert_message(db_path, body="Test message for human")

        from multiagent.cli.listen import _listen

        # Run one iteration then cancel
        async def _run_once() -> None:
            task = asyncio.create_task(
                _listen(db_path, None, 0.05)
            )
            await asyncio.sleep(0.15)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await _run_once()
        captured = capsys.readouterr()
        assert "Test message for human" in captured.out

    async def test_marks_message_as_processed(self, db_path: str) -> None:
        """After displaying, listen should set processed_at on the message."""
        await _init_db(db_path)
        msg_id = await _insert_message(db_path)

        from multiagent.cli.listen import _listen

        task = asyncio.create_task(_listen(db_path, None, 0.05))
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert await _is_processed(db_path, msg_id) is True

    async def test_filters_by_thread_id(
        self, db_path: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """With --thread-id, listen should only show matching messages."""
        await _init_db(db_path)
        target_thread = "bbbbbbbb-0000-0000-0000-000000000002"
        other_thread = "cccccccc-0000-0000-0000-000000000003"

        await _insert_message(db_path, body="target", thread_id=target_thread)
        await _insert_message(db_path, body="other", thread_id=other_thread)

        from multiagent.cli.listen import _listen

        task = asyncio.create_task(
            _listen(db_path, target_thread, 0.05)
        )
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        captured = capsys.readouterr()
        assert "target" in captured.out
        assert "other" not in captured.out

    def test_keyboard_interrupt_exits_zero(self) -> None:
        """KeyboardInterrupt in listen_command should exit with code 0."""
        from unittest.mock import patch

        from multiagent.cli.listen import listen_command

        with patch(
            "multiagent.cli.listen.asyncio.run",
            side_effect=KeyboardInterrupt,
        ), patch(
            "multiagent.cli.listen.load_settings",
            return_value=_make_settings(":memory:"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                listen_command(thread_id="", poll_interval=0)
            assert exc_info.value.code == 0

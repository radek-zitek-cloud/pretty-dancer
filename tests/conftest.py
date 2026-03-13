from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from multiagent.config.settings import Settings
    from multiagent.transport.base import Message
    from multiagent.transport.sqlite import SQLiteTransport
    from multiagent.transport.terminal import TerminalTransport


@pytest.fixture
def test_settings() -> Settings:
    """Construct a Settings instance with all required fields for testing.

    No real .env file is loaded — all values are supplied directly.
    """
    from multiagent.config.settings import Settings

    return Settings(
        app_name="multiagent",  # type: ignore[call-arg]
        app_env="development",  # type: ignore[call-arg]
        log_level="INFO",  # type: ignore[call-arg]
        log_format="console",  # type: ignore[call-arg]
        greeting_message="Hello from test config",  # type: ignore[call-arg]
        greeting_secret="test-secret-not-real",  # type: ignore[call-arg]
        transport_backend="sqlite",  # type: ignore[call-arg]
        sqlite_db_path=":memory:",  # type: ignore[call-arg]
        sqlite_poll_interval_seconds=1.0,  # type: ignore[call-arg]
    )


@pytest_asyncio.fixture
async def sqlite_transport(test_settings: Settings) -> AsyncGenerator[SQLiteTransport, None]:
    """SQLiteTransport backed by an in-memory database."""
    from multiagent.transport.sqlite import SQLiteTransport

    transport = SQLiteTransport(test_settings)
    yield transport
    await transport.close()


@pytest.fixture
def terminal_transport(test_settings: Settings) -> TerminalTransport:
    """TerminalTransport instance for testing."""
    from multiagent.transport.terminal import TerminalTransport

    return TerminalTransport()


@pytest.fixture
def sample_message() -> Message:
    """A valid Message for use in transport tests."""
    from multiagent.transport.base import Message

    return Message(
        from_agent="human",
        to_agent="researcher",
        body="What is quantum entanglement?",
        subject="research",
    )

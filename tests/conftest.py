from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

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
        log_console_enabled=True,  # type: ignore[call-arg]
        log_console_level="WARNING",  # type: ignore[call-arg]
        log_human_file_enabled=False,  # type: ignore[call-arg]
        log_json_file_enabled=False,  # type: ignore[call-arg]
        log_trace_llm=False,  # type: ignore[call-arg]
        greeting_message="Hello from test config",  # type: ignore[call-arg]
        greeting_secret="test-secret-not-real",  # type: ignore[call-arg]
        transport_backend="sqlite",  # type: ignore[call-arg]
        sqlite_db_path=":memory:",  # type: ignore[call-arg]
        sqlite_poll_interval_seconds=1.0,  # type: ignore[call-arg]
        openrouter_api_key="test-key-not-real",  # type: ignore[call-arg]
        prompts_dir=Path("tests/fixtures/prompts"),  # type: ignore[call-arg]
        agents_config_path=Path("tests/fixtures/agents.toml"),  # type: ignore[call-arg]
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


@pytest.fixture
def mock_llm_response() -> str:
    return "Mocked LLM response for testing."


@pytest.fixture
def mock_llm(mocker: MockerFixture, mock_llm_response: str) -> AsyncMock:
    """Mock ChatOpenAI.ainvoke to return a deterministic response.

    Intercepts at the LangChain level so the full LangGraph graph
    executes — only the actual HTTP call is replaced.

    The mock returns an object with a .content attribute, matching
    the real ChatOpenAI response structure.
    """
    mock = AsyncMock(
        return_value=type("AIMessage", (), {"content": mock_llm_response})()
    )
    mocker.patch(
        "langchain_openai.ChatOpenAI.ainvoke",
        side_effect=mock,
    )
    return mock

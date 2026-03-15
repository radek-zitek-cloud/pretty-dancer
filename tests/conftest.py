from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from langgraph.checkpoint.memory import MemorySaver

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from multiagent.config.settings import Settings
    from multiagent.transport.base import Message
    from multiagent.transport.sqlite import SQLiteTransport
    from multiagent.transport.terminal import TerminalTransport


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Construct a Settings instance with all required fields for testing.

    No real .env file is loaded — all values are supplied directly.
    Creates a minimal cluster directory structure under tmp_path.
    """
    from multiagent.config.settings import Settings

    clusters_dir = tmp_path / "clusters"
    default_dir = clusters_dir / "default"
    default_dir.mkdir(parents=True)

    # Minimal agents.toml for the default cluster
    (default_dir / "agents.toml").write_text(
        '[agents.researcher]\nnext_agent = "critic"\n\n'
        "[agents.critic]\n",
        encoding="utf-8",
    )
    # Minimal MCP config
    (default_dir / "agents.mcp.json").write_text(
        '{"mcpServers": {}}',
        encoding="utf-8",
    )
    # Prompts directory with test prompt files
    prompts = default_dir / "prompts"
    prompts.mkdir()
    (prompts / "researcher.md").write_text("You are a test researcher agent.", encoding="utf-8")
    (prompts / "critic.md").write_text("You are a test critic agent.", encoding="utf-8")
    (prompts / "progressive.md").write_text("You are a test progressive agent.", encoding="utf-8")
    (prompts / "conservative.md").write_text("You are a test conservative agent.", encoding="utf-8")

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
        chat_reply_timeout_seconds=5.0,  # type: ignore[call-arg]
        openrouter_api_key="test-key-not-real",  # type: ignore[call-arg]
        clusters_dir=clusters_dir,  # type: ignore[call-arg]
        cluster="",  # type: ignore[call-arg]
        checkpointer_db_path=Path(":memory:"),  # type: ignore[call-arg]
        cost_db_path=Path(":memory:"),  # type: ignore[call-arg]
        agent_loop_detection_threshold=3,  # type: ignore[call-arg]
        agent_max_messages_per_thread=0,  # type: ignore[call-arg]
    )


@pytest.fixture
def checkpointer() -> MemorySaver:
    """In-memory checkpointer for unit tests."""
    return MemorySaver()


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
def mock_cost_ledger() -> AsyncMock:
    """Mock CostLedger with an async record method."""
    from multiagent.core.costs import CostLedger

    mock = AsyncMock(spec=CostLedger)
    mock.record = AsyncMock()
    return mock


@pytest.fixture
def mock_llm_response() -> str:
    return "Mocked LLM response for testing."


@pytest.fixture
def mock_llm(mocker: MockerFixture, mock_llm_response: str) -> AsyncMock:
    """Mock ChatOpenAI.ainvoke to return a deterministic response.

    Intercepts at the LangChain level so the full LangGraph graph
    executes — only the actual HTTP call is replaced.

    Returns a real AIMessage with usage_metadata and response_metadata
    so MessagesState's add_messages reducer and cost tracking can
    process it correctly.
    """
    from langchain_core.messages import AIMessage

    mock = AsyncMock(
        return_value=AIMessage(
            content=mock_llm_response,
            usage_metadata={
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
            },
            response_metadata={
                "token_usage": {
                    "cost": 0.000330,
                    "cost_details": {
                        "upstream_inference_prompt_cost": 0.000030,
                        "upstream_inference_completions_cost": 0.000300,
                    },
                },
            },
        )
    )
    mocker.patch(
        "langchain_openai.ChatOpenAI.ainvoke",
        side_effect=mock,
    )
    return mock

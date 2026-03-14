"""Tests for the ``multiagent chat`` command."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer.testing

from multiagent.cli.main import app


@pytest.fixture
def cli_runner() -> typer.testing.CliRunner:
    return typer.testing.CliRunner()


@pytest.fixture
def _mock_chat_deps() -> Generator[dict[str, MagicMock | AsyncMock]]:
    """Mock settings, agents config, and transport for chat command."""
    mock_transport = AsyncMock()
    mock_transport.send = AsyncMock()

    mock_settings = MagicMock()
    mock_settings.agents_config_path = "agents.toml"
    mock_settings.sqlite_db_path = ":memory:"
    mock_settings.sqlite_poll_interval_seconds = 0.05
    mock_settings.chat_reply_timeout_seconds = 0.1
    mock_settings.experiment = ""

    with (
        patch("multiagent.cli.chat.load_settings", return_value=mock_settings),
        patch(
            "multiagent.cli.chat.load_agents_config",
            return_value={"progressive": {}, "conservative": {}},
        ),
        patch("multiagent.cli.chat.create_transport", return_value=mock_transport),
        patch("multiagent.cli.chat.asyncio.run") as mock_run,
    ):
        yield {
            "settings": mock_settings,
            "transport": mock_transport,
            "run": mock_run,
        }


class TestChatCommand:
    @pytest.mark.usefixtures("_mock_chat_deps")
    def test_sends_message_to_named_agent(
        self, cli_runner: typer.testing.CliRunner
    ) -> None:
        """Chat should accept an agent_name argument without error."""
        result = cli_runner.invoke(app, ["chat", "progressive"], input="\n")
        assert result.exit_code == 0

    @pytest.mark.usefixtures("_mock_chat_deps")
    def test_exits_on_empty_input(
        self, cli_runner: typer.testing.CliRunner
    ) -> None:
        """Empty input line should exit the chat loop."""
        result = cli_runner.invoke(app, ["chat", "progressive"], input="\n")
        assert result.exit_code == 0

    @pytest.mark.usefixtures("_mock_chat_deps")
    def test_uses_provided_thread_id(
        self, cli_runner: typer.testing.CliRunner
    ) -> None:
        """Supplied --thread-id should be used instead of generating a new one."""
        existing_id = str(uuid.uuid4())
        result = cli_runner.invoke(
            app,
            ["chat", "progressive", "--thread-id", existing_id],
            input="\n",
        )
        assert result.exit_code == 0

    @pytest.mark.usefixtures("_mock_chat_deps")
    def test_generates_thread_id_when_absent(
        self, cli_runner: typer.testing.CliRunner
    ) -> None:
        """When no --thread-id is given, a UUID should be generated."""
        result = cli_runner.invoke(app, ["chat", "progressive"], input="\n")
        assert result.exit_code == 0

    def test_keyboard_interrupt_exits_zero(self) -> None:
        """KeyboardInterrupt in chat_command should exit with code 0."""
        mock_settings = MagicMock()
        mock_settings.agents_config_path = "agents.toml"
        mock_settings.sqlite_db_path = ":memory:"
        mock_settings.sqlite_poll_interval_seconds = 0.05
        mock_settings.chat_reply_timeout_seconds = 0.1
        mock_settings.experiment = ""

        with (
            patch(
                "multiagent.cli.chat.load_settings",
                return_value=mock_settings,
            ),
            patch(
                "multiagent.cli.chat.load_agents_config",
                return_value={"progressive": {}},
            ),
            patch(
                "multiagent.cli.chat.create_transport",
                return_value=AsyncMock(),
            ),
            patch(
                "multiagent.cli.chat.asyncio.run",
                side_effect=KeyboardInterrupt,
            ),
        ):
            with pytest.raises(SystemExit) as exc_info:
                from multiagent.cli.chat import chat_command

                chat_command(agent_name="progressive")
            assert exc_info.value.code == 0

    @pytest.mark.usefixtures("_mock_chat_deps")
    def test_invalid_agent_name_fails(
        self, cli_runner: typer.testing.CliRunner
    ) -> None:
        """Unknown agent name should produce an error."""
        result = cli_runner.invoke(app, ["chat", "nonexistent"], input="\n")
        assert result.exit_code != 0
        assert "not found" in result.output

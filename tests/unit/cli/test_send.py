from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import typer
import typer.testing
import pytest

from multiagent.cli.main import app


@pytest.fixture
def cli_runner():
    return typer.testing.CliRunner()


@pytest.fixture
def _mock_send_deps():
    """Mock load_settings, load_agents_config, and create_transport."""
    mock_transport = AsyncMock()
    mock_transport.send = AsyncMock()

    with (
        patch("multiagent.cli.send.load_settings") as mock_settings,
        patch("multiagent.cli.send.load_agents_config") as mock_configs,
        patch("multiagent.cli.send.create_transport", return_value=mock_transport),
    ):
        mock_settings.return_value.agents_config_path = "agents.toml"
        mock_configs.return_value = {"progressive": {}, "conservative": {}}
        yield


class TestSendThreadId:
    @pytest.mark.usefixtures("_mock_send_deps")
    def test_new_thread_id_generated_when_flag_omitted(self, cli_runner):
        result = cli_runner.invoke(app, ["send", "progressive", "Hello"])
        assert result.exit_code == 0
        # Output contains a valid UUID thread_id
        output = result.output
        assert "Thread:" in output
        thread_part = output.split("Thread:")[1].strip()
        uuid.UUID(thread_part)  # raises if not valid UUID

    @pytest.mark.usefixtures("_mock_send_deps")
    def test_supplied_thread_id_used_in_message(self, cli_runner):
        existing_id = str(uuid.uuid4())
        result = cli_runner.invoke(
            app, ["send", "progressive", "Continue", "--thread-id", existing_id]
        )
        assert result.exit_code == 0
        assert existing_id in result.output

    @pytest.mark.usefixtures("_mock_send_deps")
    def test_invalid_uuid_raises_bad_parameter(self, cli_runner):
        result = cli_runner.invoke(
            app, ["send", "progressive", "body", "--thread-id", "not-a-uuid"]
        )
        assert result.exit_code != 0
        assert "thread-id must be a valid UUID" in result.output

    @pytest.mark.usefixtures("_mock_send_deps")
    def test_output_prints_thread_id_used(self, cli_runner):
        existing_id = str(uuid.uuid4())
        result = cli_runner.invoke(
            app, ["send", "progressive", "Resume", "-t", existing_id]
        )
        assert result.exit_code == 0
        assert f"Sent to progressive. Thread: {existing_id}" in result.output

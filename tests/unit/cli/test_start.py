# pyright: reportUnusedFunction=false
"""Tests for the ``multiagent start`` command."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from multiagent.config.agents import AgentConfig


@pytest.fixture
def _mock_start_deps() -> Any:
    """Mock all external dependencies for start_command / _start."""
    mock_transport = AsyncMock()

    # AsyncSqliteSaver as async context manager
    mock_checkpointer = AsyncMock()
    mock_saver_cls = MagicMock()
    mock_saver_cls.from_conn_string.return_value.__aenter__ = AsyncMock(
        return_value=mock_checkpointer
    )
    mock_saver_cls.from_conn_string.return_value.__aexit__ = AsyncMock(
        return_value=False
    )

    mock_runner_instance = MagicMock()
    mock_runner_instance.run_loop = AsyncMock()

    with (
        patch("multiagent.cli.start.load_settings") as mock_settings,
        patch("multiagent.cli.start.load_agents_config") as mock_configs,
        patch("multiagent.cli.start.configure_logging", return_value=(None, None)),
        patch(
            "multiagent.cli.start.create_transport", return_value=mock_transport
        ),
        patch("multiagent.cli.start.AsyncSqliteSaver", mock_saver_cls),
        patch("multiagent.cli.start.LLMAgent"),
        patch(
            "multiagent.cli.start.AgentRunner",
            return_value=mock_runner_instance,
        ) as mock_runner_cls,
    ):
        mock_settings.return_value.agents_config_path = "agents.toml"
        mock_settings.return_value.checkpointer_db_path = MagicMock()
        mock_settings.return_value.checkpointer_db_path.parent.mkdir = MagicMock()
        mock_configs.return_value = {
            "researcher": AgentConfig(name="researcher", next_agent="critic"),
            "critic": AgentConfig(name="critic"),
        }
        yield {
            "runner_cls": mock_runner_cls,
            "runner_instance": mock_runner_instance,
            "configs": mock_configs,
        }


class TestStartCommand:
    @pytest.mark.usefixtures("_mock_start_deps")
    def test_starts_all_agents_from_config(
        self, _mock_start_deps: Any
    ) -> None:
        """run_loop is called once per agent defined in config."""
        from multiagent.cli.start import start_command

        start_command()

        runner_instance: MagicMock = _mock_start_deps["runner_instance"]
        # run_loop should be called once per agent (2 agents in fixture)
        assert runner_instance.run_loop.call_count == 2

    def test_exits_cleanly_when_no_agents_configured(self) -> None:
        """No TaskGroup created when agents config is empty."""
        mock_checkpointer = AsyncMock()
        mock_saver_cls = MagicMock()
        mock_saver_cls.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_checkpointer
        )
        mock_saver_cls.from_conn_string.return_value.__aexit__ = AsyncMock(
            return_value=False
        )

        with (
            patch("multiagent.cli.start.load_settings") as mock_settings,
            patch(
                "multiagent.cli.start.load_agents_config", return_value={}
            ),
            patch(
                "multiagent.cli.start.configure_logging",
                return_value=(None, None),
            ),
            patch("multiagent.cli.start.create_transport"),
            patch("multiagent.cli.start.AsyncSqliteSaver", mock_saver_cls),
            patch("multiagent.cli.start.AgentRunner") as mock_runner_cls,
        ):
            mock_settings.return_value.agents_config_path = "agents.toml"
            mock_settings.return_value.checkpointer_db_path = MagicMock()
            mock_settings.return_value.checkpointer_db_path.parent.mkdir = MagicMock()

            from multiagent.cli.start import start_command

            # Should not raise, should not create any runners
            start_command()
            mock_runner_cls.assert_not_called()

    @pytest.mark.usefixtures("_mock_start_deps")
    def test_logs_cluster_starting_with_agent_names(
        self, _mock_start_deps: Any
    ) -> None:
        """cluster_starting log event contains all agent names."""
        with patch("multiagent.cli.start.structlog") as mock_structlog:
            mock_log = MagicMock()
            mock_structlog.get_logger.return_value = mock_log

            from multiagent.cli.start import start_command

            start_command()

            # Find the cluster_starting call
            cluster_starting_calls = [
                c
                for c in mock_log.info.call_args_list
                if c.args and c.args[0] == "cluster_starting"
            ]
            assert len(cluster_starting_calls) == 1
            call_kwargs = cluster_starting_calls[0].kwargs
            assert "agents" in call_kwargs
            assert set(call_kwargs["agents"]) == {"researcher", "critic"}

    def test_keyboard_interrupt_exits_zero(self) -> None:
        """KeyboardInterrupt from asyncio.run results in sys.exit(0)."""
        with patch(
            "multiagent.cli.start.asyncio.run", side_effect=KeyboardInterrupt
        ):
            from multiagent.cli.start import start_command

            with pytest.raises(SystemExit) as exc_info:
                start_command()
            assert exc_info.value.code == 0

"""Tests for the ``multiagent monitor`` command guard clauses."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from multiagent.config.settings import Settings


class TestMonitorCommand:
    def test_exits_nonzero_when_transport_not_sqlite(
        self, test_settings: Settings
    ) -> None:
        """Monitor requires SQLite transport — terminal backend rejected."""
        test_settings.transport_backend = "terminal"  # type: ignore[assignment]

        with patch(
            "multiagent.cli.monitor.load_settings", return_value=test_settings
        ):
            from multiagent.cli.monitor import monitor_command

            with pytest.raises(SystemExit) as exc_info:
                monitor_command()
            assert exc_info.value.code == 1

    def test_exits_nonzero_when_agents_db_missing(
        self, test_settings: Settings,
    ) -> None:
        """Monitor exits cleanly when agents.db does not exist."""
        from pathlib import Path

        test_settings.sqlite_db_path = Path("/tmp/nonexistent_monitor_test.db")  # type: ignore[assignment]

        with patch(
            "multiagent.cli.monitor.load_settings", return_value=test_settings
        ):
            from multiagent.cli.monitor import monitor_command

            with pytest.raises(SystemExit) as exc_info:
                monitor_command()
            assert exc_info.value.code == 1

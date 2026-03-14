from pathlib import Path

import pytest

from multiagent.core.shutdown import ShutdownMonitor


@pytest.fixture
def monitor(tmp_path: Path) -> ShutdownMonitor:
    return ShutdownMonitor(tmp_path)


class TestShutdownMonitorShouldStop:
    def test_returns_false_when_no_sentinel(self, monitor: ShutdownMonitor) -> None:
        assert monitor.should_stop("scout") is False

    def test_returns_true_when_global_sentinel_exists(
        self, monitor: ShutdownMonitor, tmp_path: Path
    ) -> None:
        (tmp_path / ".stop").touch()
        assert monitor.should_stop("scout") is True

    def test_returns_true_when_agent_sentinel_exists(
        self, monitor: ShutdownMonitor, tmp_path: Path
    ) -> None:
        (tmp_path / ".stop.scout").touch()
        assert monitor.should_stop("scout") is True

    def test_agent_sentinel_does_not_affect_other_agents(
        self, monitor: ShutdownMonitor, tmp_path: Path
    ) -> None:
        (tmp_path / ".stop.scout").touch()
        assert monitor.should_stop("critic") is False


class TestShutdownMonitorRequestStop:
    def test_creates_global_sentinel(
        self, monitor: ShutdownMonitor, tmp_path: Path
    ) -> None:
        path = monitor.request_stop()
        assert path == tmp_path / ".stop"
        assert path.exists()

    def test_creates_agent_sentinel(
        self, monitor: ShutdownMonitor, tmp_path: Path
    ) -> None:
        path = monitor.request_stop("scout")
        assert path == tmp_path / ".stop.scout"
        assert path.exists()

    def test_creates_data_dir_if_missing(self, tmp_path: Path) -> None:
        nested = tmp_path / "sub" / "dir"
        monitor = ShutdownMonitor(nested)
        monitor.request_stop()
        assert (nested / ".stop").exists()


class TestShutdownMonitorClear:
    def test_clears_global_and_all_agent_sentinels(
        self, monitor: ShutdownMonitor, tmp_path: Path
    ) -> None:
        (tmp_path / ".stop").touch()
        (tmp_path / ".stop.scout").touch()
        (tmp_path / ".stop.critic").touch()
        monitor.clear()
        assert not (tmp_path / ".stop").exists()
        assert not (tmp_path / ".stop.scout").exists()
        assert not (tmp_path / ".stop.critic").exists()

    def test_clears_only_named_agent_sentinel(
        self, monitor: ShutdownMonitor, tmp_path: Path
    ) -> None:
        (tmp_path / ".stop").touch()
        (tmp_path / ".stop.scout").touch()
        monitor.clear("scout")
        assert (tmp_path / ".stop").exists()
        assert not (tmp_path / ".stop.scout").exists()

    def test_clear_is_safe_when_no_sentinels_exist(
        self, monitor: ShutdownMonitor
    ) -> None:
        monitor.clear()  # should not raise
        monitor.clear("scout")  # should not raise

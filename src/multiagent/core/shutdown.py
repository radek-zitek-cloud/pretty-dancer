"""ShutdownMonitor — file-based sentinel for graceful agent shutdown."""

from __future__ import annotations

from pathlib import Path


class ShutdownMonitor:
    """Checks for sentinel files to signal graceful shutdown.

    Sentinel files:
        - ``<data_dir>/.stop``            — stop all agents
        - ``<data_dir>/.stop.<agent>``     — stop a single agent
    """

    _GLOBAL_SENTINEL = ".stop"

    def __init__(self, data_dir: Path) -> None:
        """Initialise the monitor with the directory for sentinel files."""
        self._data_dir = data_dir

    def _agent_sentinel(self, agent_name: str) -> Path:
        return self._data_dir / f".stop.{agent_name}"

    def _global_path(self) -> Path:
        return self._data_dir / self._GLOBAL_SENTINEL

    def should_stop(self, agent_name: str) -> bool:
        """Return True if a stop has been requested for this agent or globally."""
        return self._global_path().exists() or self._agent_sentinel(agent_name).exists()

    def request_stop(self, agent_name: str | None = None) -> Path:
        """Create a sentinel file requesting shutdown.

        Args:
            agent_name: If given, stop only that agent. Otherwise stop all.

        Returns:
            The path of the sentinel file created.
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        path = self._agent_sentinel(agent_name) if agent_name else self._global_path()
        path.touch()
        return path

    def clear(self, agent_name: str | None = None) -> None:
        """Remove sentinel files to allow clean restarts.

        Args:
            agent_name: If given, clear only that agent's sentinel.
                Otherwise clear the global sentinel and all per-agent sentinels.
        """
        if agent_name:
            self._agent_sentinel(agent_name).unlink(missing_ok=True)
        else:
            self._global_path().unlink(missing_ok=True)
            for p in self._data_dir.glob(".stop.*"):
                p.unlink(missing_ok=True)

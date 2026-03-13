"""Transport layer — abstract port and concrete adapters.

Public API:
    Message            — the data contract crossing the transport/core boundary
    Transport          — the abstract base class all adapters must implement
    create_transport   — factory to construct the configured transport adapter
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from multiagent.exceptions import InvalidConfigurationError
from multiagent.transport.base import Message, Transport

if TYPE_CHECKING:
    from multiagent.config.settings import Settings

__all__ = ["Message", "Transport", "create_transport"]


def create_transport(settings: Settings) -> Transport:
    """Construct the configured transport adapter.

    Reads settings.transport_backend and returns the appropriate
    Transport implementation. The transport is not yet connected —
    call connect() if the implementation requires it, or rely on
    lazy initialisation.

    Args:
        settings: Validated application settings.

    Returns:
        Configured Transport instance.

    Raises:
        InvalidConfigurationError: If transport_backend is unrecognised.
    """
    if settings.transport_backend == "sqlite":
        from multiagent.transport.sqlite import SQLiteTransport

        return SQLiteTransport(settings)
    if settings.transport_backend == "terminal":
        from multiagent.transport.terminal import TerminalTransport

        return TerminalTransport(settings)
    raise InvalidConfigurationError(
        f"Unknown transport backend: {settings.transport_backend}"
    )

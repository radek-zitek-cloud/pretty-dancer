from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio

from multiagent.config.settings import Settings
from multiagent.transport.sqlite import SQLiteTransport


@pytest_asyncio.fixture
async def integration_settings() -> Settings:
    """Settings for integration tests — real API key, in-memory transport."""
    return Settings(
        sqlite_db_path=Path(":memory:"),  # type: ignore[call-arg]
        log_level="WARNING",  # type: ignore[call-arg]
        clusters_dir=Path("clusters"),  # type: ignore[call-arg]
        cluster="",  # type: ignore[call-arg]
        checkpointer_db_path=Path(":memory:"),  # type: ignore[call-arg]
    )


@pytest_asyncio.fixture
async def shared_transport(
    integration_settings: Settings,
) -> AsyncGenerator[SQLiteTransport, None]:
    """A single SQLiteTransport instance shared between all agents in a test.

    In-memory SQLite — all data is lost when the fixture goes out of scope.
    Both runner fixtures receive this same instance so they share one DB.
    """
    transport = SQLiteTransport(integration_settings)
    yield transport
    await transport.close()

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from multiagent.config.settings import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Construct a Settings instance with all required fields for testing.

    No real .env file is loaded — all values are supplied directly.
    """
    from multiagent.config.settings import Settings

    return Settings(
        app_name="multiagent",  # type: ignore[call-arg]
        app_env="development",  # type: ignore[call-arg]
        log_level="INFO",  # type: ignore[call-arg]
        log_format="console",  # type: ignore[call-arg]
        greeting_message="Hello from test config",  # type: ignore[call-arg]
        greeting_secret="test-secret-not-real",  # type: ignore[call-arg]
    )

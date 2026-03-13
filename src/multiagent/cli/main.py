"""Main entry point for the multi-agent system.

Provides the synchronous main() wrapper and async _async_main() function
that implements the application lifecycle: load config, configure logging,
log startup, print identity, print config values, log shutdown, exit.
"""

from __future__ import annotations

import asyncio
import sys

import structlog

from multiagent import __version__
from multiagent.config import load_settings
from multiagent.constants import APP_NAME
from multiagent.exceptions import InvalidConfigurationError, MultiAgentError
from multiagent.logging import configure_logging


async def _async_main() -> None:
    """Run the application lifecycle.

    Steps:
        1. Load configuration
        2. Configure logging
        3. Log startup
        4. Print identity line
        5. Print and log configuration values
        6. Log shutdown
        7. Exit with code 0
    """
    settings = load_settings()

    configure_logging(level=settings.log_level, fmt=settings.log_format)

    log = structlog.get_logger(__name__)

    await log.ainfo("startup", app=APP_NAME, version=__version__, env=settings.app_env)

    print(f"{APP_NAME} v{__version__}")
    print(f"Greeting message : {settings.greeting_message}")
    print(f"Greeting secret  : {settings.greeting_secret}")

    await log.ainfo("config_value", key="greeting_message", value=settings.greeting_message)
    await log.ainfo("config_value", key="greeting_secret", value=settings.greeting_secret)

    await log.ainfo("shutdown", reason="completed")


def main() -> None:
    """Synchronous entry point for the multiagent CLI."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(_async_main())
    except InvalidConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)
    except MultiAgentError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:  # intentional broad catch at boundary
        print(f"Unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)

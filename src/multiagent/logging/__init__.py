"""Logging configuration and setup for the multi-agent system.

Exports configure_logging for application startup and get_logger for
obtaining module-level loggers.
"""

from __future__ import annotations

from multiagent.logging.setup import configure_logging, get_logger

__all__ = ["configure_logging", "get_logger"]

"""Structlog configuration for the multi-agent system.

Configures structlog with stdlib routing, providing both human-readable
console output for development and JSON output for production.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    """Configure structlog for the application.

    Must be called once at process startup before any logging occurs.
    Call this from CLI entry points, never from library code.

    Args:
        level: Minimum log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        fmt: Renderer format — 'console' for human-readable dev output,
             'json' for structured machine-parseable production output.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if fmt == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structlog bound logger for the given module name.

    Args:
        name: The module name, typically __name__.

    Returns:
        A bound structlog logger instance.
    """
    return structlog.get_logger(name)  # type: ignore[return-value]

"""Structlog configuration with three independent output streams.

Configures structlog with stdlib routing, providing up to three
independent handlers: console (colours), human-readable file (.log),
and JSON Lines file (.jsonl). Each stream has its own level and can
be toggled independently. LLM trace events are suppressed from
console and human file streams.
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog

from multiagent.config.settings import Settings


class _SuppressLLMTrace(logging.Filter):
    """Drop llm_trace events from console and human-readable file handlers.

    llm_trace events contain full prompt and response content and are
    intended for JSONL file analysis only. They must never appear in
    real-time console output or human-readable log files.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Return False for llm_trace events to suppress them."""
        return "llm_trace" not in record.getMessage()


def _build_filename(experiment: str) -> str:
    """Build a per-run filename prefix from current timestamp and experiment label.

    Args:
        experiment: Optional experiment label. Empty string for timestamp-only.

    Returns:
        Filename prefix like '2026-03-13T14-32-01' or '2026-03-13T14-32-01_prompt-v2'.
    """
    ts = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H-%M-%S")
    if experiment:
        safe_label = experiment.replace(" ", "-")
        return f"{ts}_{safe_label}"
    return ts


def configure_logging(
    settings: Settings,
    experiment: str = "",
) -> tuple[Path | None, Path | None]:
    """Configure structlog with up to three independent output streams.

    Attaches up to three stdlib logging handlers based on settings:
      - Console handler: ConsoleRenderer (colours) to stdout
      - Human file handler: ConsoleRenderer (no colours) to per-run .log
      - JSON file handler: JSONRenderer to per-run .jsonl

    Each handler has its own level. llm_trace events are suppressed from
    console and human file via _SuppressLLMTrace. Root logger is always
    set to DEBUG — handler levels control actual output.

    Must be called once at process startup. Call from CLI entry points only.

    Args:
        settings: Validated application settings.
        experiment: Experiment label from CLI flag. Overrides settings.experiment
            when non-empty.

    Returns:
        Tuple of (human_log_path, json_log_path). Either is None if that
        stream is disabled.

    Raises:
        OSError: If log_dir cannot be created.
    """
    effective_experiment = experiment if experiment else settings.experiment

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    suppress_filter = _SuppressLLMTrace()
    human_log_path: Path | None = None
    json_log_path: Path | None = None

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.DEBUG)

    # Console stream
    if settings.log_console_enabled:
        console_renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=True)
        console_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                console_renderer,
            ],
        )
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(settings.log_console_level.upper())
        console_handler.addFilter(suppress_filter)
        root_logger.addHandler(console_handler)

    # Create log_dir and build filename if any file stream is enabled
    filename_prefix = ""
    if settings.log_human_file_enabled or settings.log_json_file_enabled:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        filename_prefix = _build_filename(effective_experiment)

    # Human-readable file stream (.log)
    if settings.log_human_file_enabled:
        human_log_path = settings.log_dir / f"{filename_prefix}.log"
        human_renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=False)
        human_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                human_renderer,
            ],
        )
        human_handler = logging.FileHandler(str(human_log_path), encoding="utf-8")
        human_handler.setFormatter(human_formatter)
        human_handler.setLevel(settings.log_human_file_level.upper())
        human_handler.addFilter(suppress_filter)
        root_logger.addHandler(human_handler)

    # JSON Lines file stream (.jsonl)
    if settings.log_json_file_enabled:
        json_log_path = settings.log_dir / f"{filename_prefix}.jsonl"
        json_renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
        json_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                json_renderer,
            ],
        )
        json_handler = logging.FileHandler(str(json_log_path), encoding="utf-8")
        json_handler.setFormatter(json_formatter)
        json_handler.setLevel(settings.log_json_file_level.upper())
        root_logger.addHandler(json_handler)

    return human_log_path, json_log_path


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structlog bound logger for the given module name.

    Args:
        name: The module name, typically __name__.

    Returns:
        A bound structlog logger instance.
    """
    return structlog.get_logger(name)  # type: ignore[return-value]

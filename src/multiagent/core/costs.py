"""Cost ledger for recording per-call LLM costs to SQLite.

Provides a ``CostEntry`` dataclass for cost data and a ``CostLedger``
async context manager that owns the database connection and schema.
Cost recording failures are logged but never raised — cost tracking
must not degrade the LLM pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

import aiosqlite
import structlog

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS cost_ledger (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT    NOT NULL,
    thread_id         TEXT    NOT NULL,
    agent             TEXT    NOT NULL,
    model             TEXT    NOT NULL,
    input_tokens      INTEGER NOT NULL,
    output_tokens     INTEGER NOT NULL,
    total_tokens      INTEGER NOT NULL,
    input_unit_price  REAL    NOT NULL,
    output_unit_price REAL    NOT NULL,
    cost_usd          REAL    NOT NULL,
    experiment        TEXT    NOT NULL DEFAULT ''
)
"""

_INSERT = """\
INSERT INTO cost_ledger (
    timestamp, thread_id, agent, model,
    input_tokens, output_tokens, total_tokens,
    input_unit_price, output_unit_price, cost_usd,
    experiment
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


@dataclass(frozen=True)
class CostEntry:
    """A single LLM call cost record.

    Attributes:
        timestamp: ISO-8601 timestamp of the call.
        thread_id: Conversation thread identifier.
        agent: Name of the agent that made the call.
        model: OpenRouter model routing string.
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens generated.
        total_tokens: Sum of input and output tokens.
        input_unit_price: Price per input token in USD.
        output_unit_price: Price per output token in USD.
        cost_usd: Computed cost in USD.
        experiment: Optional experiment label.
    """

    timestamp: str
    thread_id: str
    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_unit_price: float
    output_unit_price: float
    cost_usd: float
    experiment: str = ""


class CostLedger:
    """Async context manager for the cost ledger SQLite database.

    Opens the database connection on entry, initialises the schema, and
    closes the connection on exit. The ``record`` method writes a single
    ``CostEntry`` row — failures are logged as warnings and never raised.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialise with the database file path."""
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._log = structlog.get_logger(__name__)

    async def __aenter__(self) -> CostLedger:
        """Open the database connection and initialise the schema."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self._db_path))
        await self._init_schema()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()

    async def _init_schema(self) -> None:
        """Create the cost_ledger table if it does not exist."""
        if self._conn:
            await self._conn.execute(_CREATE_TABLE)
            await self._conn.commit()

    async def record(self, entry: CostEntry) -> None:
        """Write a cost entry to the database.

        On failure, logs a warning and returns — never raises.

        Args:
            entry: The cost data to record.
        """
        try:
            if not self._conn:
                self._log.warning("cost_recording_failed", error="no database connection")
                return
            await self._conn.execute(
                _INSERT,
                (
                    entry.timestamp,
                    entry.thread_id,
                    entry.agent,
                    entry.model,
                    entry.input_tokens,
                    entry.output_tokens,
                    entry.total_tokens,
                    entry.input_unit_price,
                    entry.output_unit_price,
                    entry.cost_usd,
                    entry.experiment,
                ),
            )
            await self._conn.commit()
        except Exception as exc:
            self._log.warning("cost_recording_failed", error=str(exc))

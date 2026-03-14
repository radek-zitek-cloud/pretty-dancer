from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from multiagent.core.costs import CostEntry, CostLedger

SAMPLE_ENTRY = CostEntry(
    timestamp="2026-03-14T10:00:00",
    thread_id="thread-1",
    agent="researcher",
    model="anthropic/claude-sonnet-4-5",
    input_tokens=100,
    output_tokens=50,
    total_tokens=150,
    input_unit_price=0.000003,
    output_unit_price=0.000015,
    cost_usd=0.001050,
    experiment="test-exp",
)


class TestCostLedger:
    async def test_record_writes_row_to_database(self, tmp_path: Path):
        db = tmp_path / "costs.db"
        async with CostLedger(db) as ledger:
            await ledger.record(SAMPLE_ENTRY)

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM cost_ledger").fetchall()
        conn.close()

        assert len(rows) == 1
        row = rows[0]
        assert row["thread_id"] == "thread-1"
        assert row["agent"] == "researcher"
        assert row["input_tokens"] == 100
        assert row["output_tokens"] == 50
        assert row["total_tokens"] == 150
        assert row["cost_usd"] == pytest.approx(0.001050)
        assert row["experiment"] == "test-exp"

    async def test_record_failure_does_not_raise(self, tmp_path: Path):
        db = tmp_path / "costs.db"
        async with CostLedger(db) as ledger:
            # Close the connection to force a failure
            if ledger._conn:  # noqa: SLF001
                await ledger._conn.close()  # noqa: SLF001
                ledger._conn = None  # noqa: SLF001
            # Should not raise
            await ledger.record(SAMPLE_ENTRY)

    async def test_missing_parent_directory_is_created(self, tmp_path: Path):
        db = tmp_path / "nested" / "deep" / "costs.db"
        async with CostLedger(db) as ledger:
            await ledger.record(SAMPLE_ENTRY)

        assert db.exists()
        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT COUNT(*) FROM cost_ledger").fetchone()
        conn.close()
        assert rows is not None
        assert rows[0] == 1

    async def test_schema_is_idempotent(self, tmp_path: Path):
        db = tmp_path / "costs.db"
        async with CostLedger(db) as ledger:
            await ledger.record(SAMPLE_ENTRY)

        # Open a second time — should not error
        async with CostLedger(db) as ledger:
            await ledger.record(SAMPLE_ENTRY)

        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT COUNT(*) FROM cost_ledger").fetchone()
        conn.close()
        assert rows is not None
        assert rows[0] == 2

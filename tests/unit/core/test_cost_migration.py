# pyright: reportPrivateUsage=false, reportUnknownMemberType=false
"""Tests for cost_ledger experiment→cluster column migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

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
    cluster="test-cluster",
)


class TestCostLedgerMigration:
    async def test_migrates_experiment_column_to_cluster(
        self, tmp_path: Path
    ) -> None:
        """Old schema with 'experiment' column gets renamed to 'cluster'."""
        db = tmp_path / "costs.db"

        # Create old schema with experiment column
        conn = sqlite3.connect(str(db))
        conn.execute("""\
            CREATE TABLE cost_ledger (
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
        """)
        conn.execute(
            "INSERT INTO cost_ledger "
            "(timestamp, thread_id, agent, model, input_tokens, output_tokens, "
            "total_tokens, input_unit_price, output_unit_price, cost_usd, experiment) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "2026-03-14T10:00:00", "t1", "researcher", "model",
                100, 50, 150, 0.0, 0.0, 0.001, "old-exp",
            ),
        )
        conn.commit()
        conn.close()

        # Open with CostLedger — migration should run
        async with CostLedger(db) as ledger:
            await ledger.record(SAMPLE_ENTRY)

        # Verify: cluster column exists, experiment does not
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM cost_ledger ORDER BY id").fetchall()
        col_names = list(rows[0].keys())
        conn.close()

        assert "cluster" in col_names
        assert "experiment" not in col_names
        # Old row preserved with value intact
        assert rows[0]["cluster"] == "old-exp"
        # New row has new value
        assert rows[1]["cluster"] == "test-cluster"
        assert len(rows) == 2

    async def test_schema_already_migrated_is_idempotent(
        self, tmp_path: Path
    ) -> None:
        """Opening CostLedger twice on new schema does not error."""
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

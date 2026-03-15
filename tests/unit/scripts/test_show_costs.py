from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def _create_cost_db(db_path: Path, *, populate: bool = True) -> None:
    """Create a cost_ledger database, optionally with sample data."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""\
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
            cluster        TEXT    NOT NULL DEFAULT ''
        )
    """)
    if populate:
        conn.execute(
            "INSERT INTO cost_ledger "
            "(timestamp, thread_id, agent, model, input_tokens, output_tokens, "
            "total_tokens, input_unit_price, output_unit_price, cost_usd, cluster) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "2026-03-14T10:00:00",
                "thread-1",
                "researcher",
                "anthropic/claude-sonnet-4-5",
                100,
                50,
                150,
                0.000003,
                0.000015,
                0.001050,
                "test-exp",
            ),
        )
        conn.execute(
            "INSERT INTO cost_ledger "
            "(timestamp, thread_id, agent, model, input_tokens, output_tokens, "
            "total_tokens, input_unit_price, output_unit_price, cost_usd, cluster) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "2026-03-14T10:01:00",
                "thread-1",
                "critic",
                "openai/gpt-4o",
                200,
                100,
                300,
                0.000005,
                0.000015,
                0.002500,
                "test-exp",
            ),
        )
    conn.commit()
    conn.close()


def _env(db_path: Path) -> dict[str, str]:
    """Build env dict overriding cost_db_path and required settings."""
    env = os.environ.copy()
    env["COST_DB_PATH"] = str(db_path)
    env["OPENROUTER_API_KEY"] = "test-key"
    env["GREETING_SECRET"] = "test-secret"
    return env


class TestShowCosts:
    def test_exits_zero_when_no_data(self, tmp_path: Path):
        db = tmp_path / "costs.db"
        _create_cost_db(db, populate=False)
        result = subprocess.run(
            [sys.executable, "scripts/show_costs.py"],
            capture_output=True,
            text=True,
            env=_env(db),
        )
        assert result.returncode == 0
        assert "No cost data found" in result.stdout

    def test_exits_zero_with_missing_database(self, tmp_path: Path):
        db = tmp_path / "nonexistent" / "costs.db"
        result = subprocess.run(
            [sys.executable, "scripts/show_costs.py"],
            capture_output=True,
            text=True,
            env=_env(db),
        )
        assert result.returncode == 0
        assert "No cost data found" in result.stdout

    def test_by_agent_flag_produces_agent_grouped_output(self, tmp_path: Path):
        db = tmp_path / "costs.db"
        _create_cost_db(db)
        result = subprocess.run(
            [sys.executable, "scripts/show_costs.py", "--by-agent"],
            capture_output=True,
            text=True,
            env=_env(db),
        )
        assert result.returncode == 0
        assert "researcher" in result.stdout
        assert "critic" in result.stdout

    def test_by_model_flag_produces_model_grouped_output(self, tmp_path: Path):
        db = tmp_path / "costs.db"
        _create_cost_db(db)
        result = subprocess.run(
            [sys.executable, "scripts/show_costs.py", "--by-model"],
            capture_output=True,
            text=True,
            env=_env(db),
        )
        assert result.returncode == 0
        assert "claude-sonnet" in result.stdout
        assert "gpt-4o" in result.stdout

    def test_mutually_exclusive_flags_exit_nonzero(self, tmp_path: Path):
        db = tmp_path / "costs.db"
        _create_cost_db(db)
        result = subprocess.run(
            [sys.executable, "scripts/show_costs.py", "--by-agent", "--by-model"],
            capture_output=True,
            text=True,
            env=_env(db),
        )
        assert result.returncode != 0

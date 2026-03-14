import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def _env(**overrides: str) -> dict[str, str]:
    """Build env dict with required settings for subprocess tests."""
    env = os.environ.copy()
    env.setdefault("OPENROUTER_API_KEY", "test-key")
    env.setdefault("GREETING_SECRET", "test-secret")
    env.update(overrides)
    return env


class TestBrowseThreads:
    def test_exits_zero_when_no_threads(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE messages ("
            "id INTEGER PRIMARY KEY, from_agent TEXT, to_agent TEXT, "
            "body TEXT, thread_id TEXT, created_at TEXT, processed_at TEXT)"
        )
        conn.commit()
        conn.close()

        result = subprocess.run(
            [sys.executable, "scripts/browse_threads.py"],
            env=_env(SQLITE_DB_PATH=str(db)),
            input="q\n",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "No threads found" in result.stdout

    def test_exits_nonzero_with_missing_database(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/browse_threads.py"],
            env=_env(SQLITE_DB_PATH=str(tmp_path / "nonexistent.db")),
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "Database not found" in result.stderr

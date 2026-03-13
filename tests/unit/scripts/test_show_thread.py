import subprocess
import sys
from pathlib import Path


class TestShowThread:
    def test_exits_nonzero_with_no_args(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/show_thread.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_exits_nonzero_with_nonexistent_thread_id(self, tmp_path: Path) -> None:
        # Create an empty SQLite database with the messages table
        import sqlite3

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
            [sys.executable, "scripts/show_thread.py", "--db", str(db), "nonexistent-thread"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "No messages found" in result.stderr

    def test_exits_nonzero_with_missing_database(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/show_thread.py", "--db", "nonexistent.db", "some-thread"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "Database not found" in result.stderr

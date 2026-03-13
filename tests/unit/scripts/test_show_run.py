import subprocess
import sys


class TestShowRun:
    def test_exits_nonzero_with_no_args(self):
        result = subprocess.run(
            [sys.executable, "scripts/show_run.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_exits_nonzero_with_nonexistent_file(self):
        result = subprocess.run(
            [sys.executable, "scripts/show_run.py", "nonexistent.jsonl"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "File not found" in result.stderr

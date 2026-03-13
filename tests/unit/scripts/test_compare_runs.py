import subprocess
import sys


class TestCompareRuns:
    def test_exits_nonzero_with_no_args(self):
        result = subprocess.run(
            [sys.executable, "scripts/compare_runs.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_exits_nonzero_with_one_arg_only(self):
        result = subprocess.run(
            [sys.executable, "scripts/compare_runs.py", "file1.jsonl"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_exits_nonzero_with_nonexistent_files(self):
        result = subprocess.run(
            [sys.executable, "scripts/compare_runs.py", "nonexistent1.jsonl", "nonexistent2.jsonl"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "File not found" in result.stderr

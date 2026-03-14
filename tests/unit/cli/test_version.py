from __future__ import annotations

from unittest.mock import patch

import typer.testing

from multiagent.cli.main import app


def test_version_command_prints_version():
    runner = typer.testing.CliRunner()
    with patch("multiagent.cli.version.__version__", "1.2.3"):
        result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "1.2.3" in result.output

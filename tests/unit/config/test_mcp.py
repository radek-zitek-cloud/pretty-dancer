"""Tests for MCP server configuration loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from multiagent.config.mcp import MCPConfig, load_mcp_config
from multiagent.exceptions import ConfigurationError


class TestLoadMCPConfig:
    def test_loads_base_config_without_secrets(self, tmp_path: Path) -> None:
        """Base config loads with empty env when no secrets file exists."""
        config_path = tmp_path / "mcp.json"
        config_path.write_text(json.dumps({
            "mcpServers": {
                "test": {"command": "echo", "args": ["hello"]}
            }
        }))
        secrets_path = tmp_path / "secrets.json"  # does not exist

        result = load_mcp_config(config_path, secrets_path)
        assert "test" in result.servers
        assert result.servers["test"].command == "echo"
        assert result.servers["test"].args == ["hello"]
        assert result.servers["test"].env == {}
        assert result.servers["test"].transport == "stdio"

    def test_merges_secrets_into_base_config(self, tmp_path: Path) -> None:
        """Secrets env is merged into server config."""
        config_path = tmp_path / "mcp.json"
        config_path.write_text(json.dumps({
            "mcpServers": {
                "test": {"command": "echo", "args": []}
            }
        }))
        secrets_path = tmp_path / "secrets.json"
        secrets_path.write_text(json.dumps({
            "mcpServers": {
                "test": {"env": {"API_KEY": "secret123"}}
            }
        }))

        result = load_mcp_config(config_path, secrets_path)
        assert result.servers["test"].env == {"API_KEY": "secret123"}

    def test_secrets_file_absent_is_not_an_error(
        self, tmp_path: Path
    ) -> None:
        """Missing secrets file does not raise."""
        config_path = tmp_path / "mcp.json"
        config_path.write_text(json.dumps({
            "mcpServers": {"s": {"command": "echo"}}
        }))
        secrets_path = tmp_path / "nonexistent.json"

        result = load_mcp_config(config_path, secrets_path)
        assert "s" in result.servers

    def test_returns_empty_when_base_config_absent(
        self, tmp_path: Path
    ) -> None:
        """Missing base config returns empty MCPConfig."""
        config_path = tmp_path / "nonexistent.json"
        secrets_path = tmp_path / "secrets.json"

        result = load_mcp_config(config_path, secrets_path)
        assert result == MCPConfig()
        assert result.servers == {}

    def test_secrets_override_base_env_keys(self, tmp_path: Path) -> None:
        """Secrets values override base env values for the same key."""
        config_path = tmp_path / "mcp.json"
        config_path.write_text(json.dumps({
            "mcpServers": {
                "s": {
                    "command": "echo",
                    "env": {"KEY": "base_value", "OTHER": "keep"}
                }
            }
        }))
        secrets_path = tmp_path / "secrets.json"
        secrets_path.write_text(json.dumps({
            "mcpServers": {
                "s": {"env": {"KEY": "secret_value"}}
            }
        }))

        result = load_mcp_config(config_path, secrets_path)
        assert result.servers["s"].env["KEY"] == "secret_value"
        assert result.servers["s"].env["OTHER"] == "keep"

    def test_unknown_server_in_secrets_is_ignored(
        self, tmp_path: Path
    ) -> None:
        """Secrets referencing unknown servers are silently ignored."""
        config_path = tmp_path / "mcp.json"
        config_path.write_text(json.dumps({
            "mcpServers": {"known": {"command": "echo"}}
        }))
        secrets_path = tmp_path / "secrets.json"
        secrets_path.write_text(json.dumps({
            "mcpServers": {"unknown": {"env": {"K": "V"}}}
        }))

        result = load_mcp_config(config_path, secrets_path)
        assert "known" in result.servers
        assert "unknown" not in result.servers

    def test_raises_on_malformed_base_config(self, tmp_path: Path) -> None:
        """Malformed JSON in base config raises ConfigurationError."""
        config_path = tmp_path / "mcp.json"
        config_path.write_text("not valid json{{{")
        secrets_path = tmp_path / "secrets.json"

        with pytest.raises(ConfigurationError, match="Failed to read"):
            load_mcp_config(config_path, secrets_path)


class TestExperimentMCPResolution:
    def test_resolves_experiment_mcp_config(self, tmp_path: Path) -> None:
        """Experiment-specific MCP config loaded when present."""
        exp_config = tmp_path / "mcp.research-desk.json"
        exp_config.write_text(json.dumps({
            "mcpServers": {"exa": {"command": "echo"}}
        }))
        secrets_path = tmp_path / "secrets.json"
        result = load_mcp_config(
            tmp_path / "mcp.json", secrets_path, experiment="research-desk"
        )
        assert "exa" in result.servers

    def test_raises_when_experiment_mcp_config_missing(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ConfigurationError, match="Experiment MCP config"):
            load_mcp_config(
                tmp_path / "mcp.json",
                tmp_path / "secrets.json",
                experiment="nonexistent",
            )

    def test_secrets_falls_back_to_default(self, tmp_path: Path) -> None:
        """When experiment secrets absent, falls back to default."""
        exp_config = tmp_path / "mcp.test-exp.json"
        exp_config.write_text(json.dumps({
            "mcpServers": {"s": {"command": "echo"}}
        }))
        # Default secrets present, experiment secrets absent
        default_secrets = tmp_path / "secrets.json"
        default_secrets.write_text(json.dumps({
            "mcpServers": {"s": {"env": {"KEY": "default"}}}
        }))
        result = load_mcp_config(
            tmp_path / "mcp.json", default_secrets, experiment="test-exp"
        )
        assert result.servers["s"].env["KEY"] == "default"

    def test_secrets_uses_experiment_file_when_present(
        self, tmp_path: Path
    ) -> None:
        exp_config = tmp_path / "mcp.test-exp.json"
        exp_config.write_text(json.dumps({
            "mcpServers": {"s": {"command": "echo"}}
        }))
        exp_secrets = tmp_path / "secrets.test-exp.json"
        exp_secrets.write_text(json.dumps({
            "mcpServers": {"s": {"env": {"KEY": "experiment"}}}
        }))
        default_secrets = tmp_path / "secrets.json"
        default_secrets.write_text(json.dumps({
            "mcpServers": {"s": {"env": {"KEY": "default"}}}
        }))
        result = load_mcp_config(
            tmp_path / "mcp.json", default_secrets, experiment="test-exp"
        )
        # Experiment secrets should take precedence... but we pass
        # default_secrets as secrets_path. The resolver needs the base path.
        # Actually the secrets resolver checks for secrets.test-exp.json
        assert result.servers["s"].env["KEY"] == "experiment"

    def test_secrets_silent_when_neither_present(
        self, tmp_path: Path
    ) -> None:
        exp_config = tmp_path / "mcp.test-exp.json"
        exp_config.write_text(json.dumps({
            "mcpServers": {"s": {"command": "echo"}}
        }))
        result = load_mcp_config(
            tmp_path / "mcp.json",
            tmp_path / "secrets.json",
            experiment="test-exp",
        )
        assert result.servers["s"].env == {}

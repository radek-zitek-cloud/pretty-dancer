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

        result = load_mcp_config(config_path, None)
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

    def test_secrets_path_none_is_not_an_error(
        self, tmp_path: Path
    ) -> None:
        """None secrets path does not raise."""
        config_path = tmp_path / "mcp.json"
        config_path.write_text(json.dumps({
            "mcpServers": {"s": {"command": "echo"}}
        }))

        result = load_mcp_config(config_path, None)
        assert "s" in result.servers

    def test_returns_empty_when_base_config_absent(
        self, tmp_path: Path
    ) -> None:
        """Missing base config returns empty MCPConfig."""
        config_path = tmp_path / "nonexistent.json"

        result = load_mcp_config(config_path, None)
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

        with pytest.raises(ConfigurationError, match="Failed to read"):
            load_mcp_config(config_path, None)

    def test_nonexistent_secrets_path_is_not_an_error(
        self, tmp_path: Path
    ) -> None:
        """Secrets path pointing to non-existent file does not raise."""
        config_path = tmp_path / "mcp.json"
        config_path.write_text(json.dumps({
            "mcpServers": {"s": {"command": "echo"}}
        }))
        secrets_path = tmp_path / "nonexistent.json"

        result = load_mcp_config(config_path, secrets_path)
        assert "s" in result.servers

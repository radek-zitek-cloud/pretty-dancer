# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
"""MCP server configuration loader.

Loads and merges agents.mcp.json (server definitions) with
agents.mcp.secrets.json (credentials). Secrets file is optional.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from multiagent.exceptions import ConfigurationError


@dataclass(frozen=True)
class MCPServerConfig:
    """Configuration for a single MCP server."""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    transport: str = "stdio"


@dataclass(frozen=True)
class MCPConfig:
    """Complete MCP configuration for the cluster."""

    servers: dict[str, MCPServerConfig] = field(default_factory=dict)


def _parse_server(
    name: str,
    data: dict[str, Any],
    secret_env: dict[str, str],
) -> MCPServerConfig | None:
    """Parse a single server entry, returning None if invalid."""
    command = data.get("command")
    if not isinstance(command, str) or not command:
        return None

    raw_args = data.get("args", [])
    args: list[str] = [str(a) for a in raw_args] if isinstance(raw_args, list) else []

    raw_env = data.get("env", {})
    env: dict[str, str] = (
        {str(k): str(v) for k, v in raw_env.items()}
        if isinstance(raw_env, dict)
        else {}
    )
    # Secrets override base env
    env = {**env, **secret_env}

    transport = str(data.get("transport", "stdio"))

    return MCPServerConfig(
        command=command,
        args=args,
        env=env,
        transport=transport,
    )


def load_mcp_config(
    config_path: Path,
    secrets_path: Path,
) -> MCPConfig:
    """Load and merge MCP server config and secrets.

    Loads agents.mcp.json for server definitions and merges
    agents.mcp.secrets.json for credentials. Secrets file is
    optional — if absent, servers are loaded without env overrides.

    Args:
        config_path: Path to agents.mcp.json.
        secrets_path: Path to agents.mcp.secrets.json (may not exist).

    Returns:
        Merged MCPConfig with all server definitions and credentials.
        Returns empty MCPConfig if config_path does not exist.

    Raises:
        ConfigurationError: If agents.mcp.json exists but is malformed.
    """
    if not config_path.exists():
        return MCPConfig()

    try:
        raw: dict[str, Any] = json.loads(
            config_path.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigurationError(
            f"Failed to read MCP config from {config_path}: {exc}"
        ) from exc

    mcp_servers = raw.get("mcpServers", {})
    if not isinstance(mcp_servers, dict):
        raise ConfigurationError(
            f"'mcpServers' in {config_path} must be an object"
        )

    # Load secrets (optional)
    secrets_map: dict[str, dict[str, str]] = {}
    if secrets_path.exists():
        try:
            secrets_raw: dict[str, Any] = json.loads(
                secrets_path.read_text(encoding="utf-8")
            )
            for sname, sdata in secrets_raw.get("mcpServers", {}).items():
                if isinstance(sdata, dict):
                    raw_env = sdata.get("env", {})
                    if isinstance(raw_env, dict):
                        secrets_map[str(sname)] = {
                            str(k): str(v) for k, v in raw_env.items()
                        }
        except (json.JSONDecodeError, OSError):
            pass  # Malformed secrets file — silently ignore

    servers: dict[str, MCPServerConfig] = {}
    for name, server_data in mcp_servers.items():
        name_str = str(name)
        if not isinstance(server_data, dict):
            continue
        secret_env = secrets_map.get(name_str, {})
        parsed = _parse_server(name_str, server_data, secret_env)
        if parsed is not None:
            servers[name_str] = parsed

    return MCPConfig(servers=servers)

"""Configuration system for the multi-agent application.

Exports the Settings class, load_settings function, and agent wiring
configuration for application-wide configuration management.
"""

from __future__ import annotations

from multiagent.config.agents import (
    AgentConfig,
    AgentsConfig,
    RouterConfig,
    load_agents_config,
)
from multiagent.config.mcp import MCPConfig, MCPServerConfig, load_mcp_config
from multiagent.config.settings import (
    Settings,
    agents_config_path,
    cluster_dir,
    load_settings,
    mcp_config_path,
    mcp_secrets_path,
    prompts_dir,
)

__all__ = [
    "AgentConfig",
    "AgentsConfig",
    "MCPConfig",
    "MCPServerConfig",
    "RouterConfig",
    "Settings",
    "agents_config_path",
    "cluster_dir",
    "load_agents_config",
    "load_mcp_config",
    "load_settings",
    "mcp_config_path",
    "mcp_secrets_path",
    "prompts_dir",
]

"""Configuration system for the multi-agent application.

Exports the Settings class, load_settings function, and agent wiring
configuration for application-wide configuration management.
"""

from __future__ import annotations

from multiagent.config.agents import AgentConfig, load_agents_config
from multiagent.config.settings import Settings, load_settings

__all__ = ["AgentConfig", "Settings", "load_agents_config", "load_settings"]

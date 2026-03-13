"""Configuration system for the multi-agent application.

Exports the Settings class and load_settings function for application-wide
configuration management.
"""

from __future__ import annotations

from multiagent.config.settings import Settings, load_settings

__all__ = ["Settings", "load_settings"]

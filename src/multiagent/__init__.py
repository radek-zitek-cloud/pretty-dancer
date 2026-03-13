"""Multi-agent LLM system proof of concept.

A transport-agnostic multi-agent system where LLM-powered agents communicate
through a messaging layer. Agent logic is independent of the communication medium.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("multiagent")
except PackageNotFoundError:
    # Package is not installed — running from source without `uv pip install -e .`
    __version__ = "0.0.0+dev"

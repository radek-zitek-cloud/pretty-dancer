"""Agent core — LLMAgent and AgentRunner.

Public API:
    LLMAgent     — LLM-powered agent, transport-agnostic
    AgentRunner  — connects an LLMAgent to a Transport
"""

from multiagent.core.agent import LLMAgent
from multiagent.core.runner import AgentRunner

__all__ = ["AgentRunner", "LLMAgent"]

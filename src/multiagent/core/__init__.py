"""Agent core — LLMAgent, AgentRunner, and routing.

Public API:
    LLMAgent     — LLM-powered agent, transport-agnostic
    AgentRunner  — connects an LLMAgent to a Transport
    KeywordRouter — keyword-based routing
    LLMRouter    — LLM classifier routing
    build_router — factory for creating routers
"""

from multiagent.core.agent import LLMAgent
from multiagent.core.routing import KeywordRouter, LLMRouter, build_router
from multiagent.core.runner import AgentRunner

__all__ = [
    "AgentRunner",
    "KeywordRouter",
    "LLMAgent",
    "LLMRouter",
    "build_router",
]

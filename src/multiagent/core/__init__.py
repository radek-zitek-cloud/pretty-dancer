"""Agent core — LLMAgent, AgentRunner, cost tracking, and routing.

Public API:
    LLMAgent      — LLM-powered agent, transport-agnostic
    AgentRunner   — connects an LLMAgent to a Transport
    CostLedger    — async context manager for cost recording
    CostEntry     — single LLM call cost record
    KeywordRouter — keyword-based routing
    LLMRouter     — LLM classifier routing
    build_router  — factory for creating routers
"""

from multiagent.core.agent import LLMAgent
from multiagent.core.costs import CostEntry, CostLedger
from multiagent.core.routing import KeywordRouter, LLMRouter, build_router
from multiagent.core.runner import AgentRunner

__all__ = [
    "AgentRunner",
    "CostEntry",
    "CostLedger",
    "KeywordRouter",
    "LLMAgent",
    "LLMRouter",
    "build_router",
]

"""Exception hierarchy for the multi-agent system.

All custom exceptions inherit from MultiAgentError, allowing callers to catch
the entire domain with a single except clause at process boundaries.
"""

from __future__ import annotations


class MultiAgentError(Exception):
    """Base exception for all multiagent system errors."""


# ── Configuration ────────────────────────────────────────────────────────────


class ConfigurationError(MultiAgentError):
    """Raised when configuration is missing or invalid. Occurs at startup."""


class MissingConfigurationError(ConfigurationError):
    """Raised when a required configuration key has no value."""


class InvalidConfigurationError(ConfigurationError):
    """Raised when a configuration value fails type or constraint validation."""


# ── Transport ─────────────────────────────────────────────────────────────────


class TransportError(MultiAgentError):
    """Raised when message transport operations fail."""


class MessageDeliveryError(TransportError):
    """Raised when a message cannot be delivered after all configured retries."""


class MessageReceiveError(TransportError):
    """Raised when message retrieval from the transport backend fails."""


class MessageAcknowledgementError(TransportError):
    """Raised when a message acknowledgement cannot be persisted."""


class TransportConnectionError(TransportError):
    """Raised when the transport backend is unavailable or unreachable."""


# ── Agent ─────────────────────────────────────────────────────────────────────


class AgentError(MultiAgentError):
    """Raised when an agent fails to process a message."""


class AgentTimeoutError(AgentError):
    """Raised when an agent exceeds its configured execution time limit."""


class AgentLLMError(AgentError):
    """Raised when the LLM API returns an error or an unparseable response."""


class AgentConfigurationError(AgentError):
    """Raised when an agent has invalid or missing configuration."""


# ── Routing ───────────────────────────────────────────────────────────────────


class RoutingError(MultiAgentError):
    """Raised when the routing layer cannot determine the next agent."""


class UnknownAgentError(RoutingError):
    """Raised when a message is addressed to an agent that does not exist."""

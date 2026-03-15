"""Transport abstract base class and Message re-export.

Defines the abstract port (Transport) that all transport adapters must
implement. Message is defined in multiagent.models and re-exported here
for backward compatibility.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from multiagent.models import Message

__all__ = ["Message", "Transport"]


class Transport(ABC):
    """Abstract port defining the message transport contract.

    All transport adapters implement this interface. Agent and runner
    code depends only on this ABC — never on concrete implementations.
    Swapping adapters requires no changes to agent code.

    Fanout: when message.to_agent is a list or "*", send() must expand
    to one delivery row per resolved recipient. Adapters own this logic.

    Timestamp ownership:
        sent_at      — set by send() on each persisted row
        received_at  — set by receive() on the returned Message
        processed_at — set by ack() on the acknowledged row
    """

    @abstractmethod
    async def receive(self, agent_name: str) -> Message | None:
        """Fetch the next unprocessed message for agent_name.

        Non-blocking. Returns None immediately if the inbox is empty.
        The caller (AgentRunner) is responsible for polling and backoff.
        Sets received_at to UTC now on the returned Message.

        Args:
            agent_name: The agent whose inbox to query.

        Returns:
            Oldest unprocessed Message for agent_name, or None.

        Raises:
            MessageReceiveError: If the backend query fails.
            TransportConnectionError: If the backend is unavailable.
        """

    @abstractmethod
    async def send(self, message: Message) -> None:
        """Deliver a message, handling fanout for lists and broadcast.

        If message.to_agent is a str: write one row.
        If message.to_agent is a list: write one row per name in list.
        If message.to_agent is "*": resolve via known_agents(), write
            one row per known agent. If known_agents() returns empty,
            log a WARNING and write zero rows — do not raise.

        Sets sent_at to UTC now on every persisted row.

        Args:
            message: Message to deliver. to_agent may be str, list, "*".

        Raises:
            MessageDeliveryError: If persistence fails.
            TransportConnectionError: If the backend is unavailable.
        """

    @abstractmethod
    async def ack(self, message_id: int) -> None:
        """Mark a message as processed. Sets processed_at to UTC now.

        After ack(), receive() will not return this message again.
        At-least-once delivery: if ack() is never called, the message
        will be re-delivered on the next receive() call.

        Args:
            message_id: The id of the Message to acknowledge.

        Raises:
            MessageAcknowledgementError: If the update cannot be persisted.
        """

    @abstractmethod
    async def known_agents(self) -> list[str]:
        """Return all agent names ever seen as to_agent recipients.

        Used internally by send() to resolve broadcast "*". Returns an
        empty list (not an error) if no messages have been persisted.

        Returns:
            Sorted list of distinct agent name strings.

        Raises:
            TransportConnectionError: If the backend is unavailable.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release all backend resources held by this instance.

        Must be idempotent — safe to call more than once.
        """

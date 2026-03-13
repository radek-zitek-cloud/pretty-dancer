"""Terminal-based transport adapter for interactive single-agent testing.

Reads from stdin and writes to stdout. No persistence, no registry.
Uses asyncio.to_thread for non-blocking stdin reads.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from multiagent.transport.base import Message, Transport

if TYPE_CHECKING:
    from multiagent.config.settings import Settings


class TerminalTransport(Transport):
    """Transport adapter that reads from stdin and writes to stdout.

    Designed for interactive single-agent testing without infrastructure.
    No messages are persisted — send() prints to stdout, receive() reads
    from stdin, and ack/known_agents/close are no-ops.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialise the terminal transport.

        Args:
            settings: Accepted for interface consistency with other transports.
                No settings are currently consumed by TerminalTransport.
        """
        # settings accepted for interface consistency with other transports.
        # No settings are currently consumed by TerminalTransport.

    async def receive(self, agent_name: str) -> Message | None:
        """Read one line from stdin as a message to agent_name.

        Prints a prompt and waits for user input using asyncio.to_thread
        to avoid blocking the event loop. Returns None on empty input or EOF.

        Args:
            agent_name: The agent whose inbox to query.

        Returns:
            A Message from "human" to agent_name, or None.
        """
        try:
            line = await asyncio.to_thread(input, f"[{agent_name}] > ")
        except EOFError:
            return None
        line = line.strip()
        if not line:
            return None
        now = datetime.now(UTC)
        return Message(
            from_agent="human",
            to_agent=agent_name,
            body=line,
            created_at=now,
            sent_at=now,
            received_at=now,
        )

    async def send(self, message: Message) -> None:
        """Print the message to stdout. Sets sent_at to UTC now.

        Handles fanout: if to_agent is a list or "*", prints one line
        per recipient.

        Args:
            message: Message to display.
        """
        now = datetime.now(UTC)
        message.sent_at = now

        recipients: list[str]
        if isinstance(message.to_agent, list):
            recipients = message.to_agent
        elif message.to_agent == "*":
            recipients = await self.known_agents()
            if not recipients:
                return
        else:
            recipients = [message.to_agent]

        for recipient in recipients:
            print(f"[{message.from_agent}] \u2192 [{recipient}]: {message.body}")

    async def ack(self, message_id: int) -> None:
        """No-op. Terminal messages have no persistence.

        Args:
            message_id: Ignored.
        """

    async def known_agents(self) -> list[str]:
        """Return empty list. Terminal transport has no registry.

        Returns:
            Empty list.
        """
        return []

    async def close(self) -> None:
        """No-op. No resources to release."""

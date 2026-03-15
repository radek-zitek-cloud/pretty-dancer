"""Shared data types used across module boundaries.

Types defined here may be imported by both core/ and transport/ without
creating circular dependencies. This module imports only from stdlib.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Message:
    """A unit of communication between agents.

    This is the only type that crosses the transport/core boundary.
    Agent runners receive and produce Message objects. They never
    interact with transport internals directly.

    Addressing: to_agent accepts a single agent name, a list of agent
    names, or the broadcast sentinel "*". The transport layer resolves
    lists and "*" to individual per-recipient rows before persistence.
    After persistence and retrieval, to_agent is always a plain str.

    Timestamps: all UTC. Set by the transport at the relevant lifecycle
    event — never by agent code. created_at is the sole exception:
    it is set at object construction by the caller.

    Attributes:
        from_agent: Sending agent name, or "human" for external input.
        to_agent: Recipient — single name, list of names, or "*".
        body: Message payload — plain text.
        subject: Optional routing label. Empty string if unused.
        thread_id: UUID grouping all messages in one conversation chain.
            Pass an existing thread_id when continuing a thread.
            Defaults to a new UUID for thread-initiating messages.
        parent_id: Database id of the message this replies to.
            None for thread-initiating messages.
        id: Database-assigned integer id. None until persisted.
        created_at: UTC timestamp of object construction. Set by caller.
        sent_at: UTC timestamp set by transport.send() on persistence.
        received_at: UTC timestamp set by transport.receive() on retrieval.
        processed_at: UTC timestamp set by transport.ack() on completion.
    """

    from_agent: str
    to_agent: str | list[str]
    body: str
    subject: str = ""
    thread_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: int | None = None
    id: int | None = None
    created_at: datetime | None = field(
        default_factory=lambda: datetime.now(UTC)
    )
    sent_at: datetime | None = None
    received_at: datetime | None = None
    processed_at: datetime | None = None

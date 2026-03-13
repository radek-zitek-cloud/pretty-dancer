"""AgentRunner — bridges LLMAgent and Transport with retry logic."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from multiagent.exceptions import AgentLLMError
from multiagent.transport.base import Message

if TYPE_CHECKING:
    from multiagent.config.settings import Settings
    from multiagent.core.agent import LLMAgent
    from multiagent.transport.base import Transport


class AgentRunner:
    """Connects an LLMAgent to a Transport.

    Handles the message lifecycle: receive, process via LLM, acknowledge,
    and optionally forward to the next agent. Includes retry with
    exponential backoff for LLM failures.
    """

    def __init__(
        self,
        agent: LLMAgent,
        transport: Transport,
        settings: Settings,
        next_agent: str | None = None,
    ) -> None:
        """Initialise the runner with an agent, transport, and settings."""
        self._agent = agent
        self._transport = transport
        self._next_agent = next_agent
        self._max_retries = 3
        self._retry_backoff = 2.0
        self._poll_interval = settings.sqlite_poll_interval_seconds
        self._log = structlog.get_logger().bind(agent=agent.name)

    async def run_once(self) -> bool:
        """Fetch and process one message from the transport inbox.

        Implements the full message lifecycle:
            1. receive() — fetch next message, return False if inbox empty
            2. agent.run() — call LLM with message body, with retry on failure
            3. ack() — mark message as processed
            4. send() — forward response to next_agent if configured

        Returns:
            True if a message was processed. False if the inbox was empty.

        Raises:
            AgentLLMError: If all retry attempts are exhausted.
            TransportError: If transport operations fail unrecoverably.
        """
        msg = await self._transport.receive(self._agent.name)
        if msg is None:
            return False

        op_log = self._log.bind(message_id=msg.id, thread_id=msg.thread_id)

        # Retry loop for LLM call
        response_text: str | None = None
        for attempt in range(1, self._max_retries + 2):  # +2: retries + initial attempt
            try:
                response_text = await self._agent.run(msg.body)
                break
            except AgentLLMError:
                if attempt <= self._max_retries:
                    wait = self._retry_backoff * (2 ** (attempt - 1))
                    self._log.warning(
                        "llm_retry",
                        attempt=attempt,
                        max_retries=self._max_retries,
                        wait_seconds=wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    self._log.error("llm_retries_exhausted", attempts=attempt)
                    raise

        assert response_text is not None  # guaranteed by break above

        assert msg.id is not None  # set by transport on receive
        await self._transport.ack(msg.id)
        op_log.info("message_processed")

        if self._next_agent:
            await self._transport.send(Message(
                from_agent=self._agent.name,
                to_agent=self._next_agent,
                body=response_text,
                subject=msg.subject,
                thread_id=msg.thread_id,
                parent_id=msg.id,
            ))
            op_log.info("message_forwarded", to_agent=self._next_agent)

        return True

    async def run_loop(self) -> None:
        """Run the agent polling loop indefinitely.

        Polls the transport inbox at poll_interval when empty. Processes
        messages immediately when available. Exits cleanly on
        asyncio.CancelledError — the expected shutdown signal.

        This method never returns normally. It is intended to run as a
        long-lived asyncio task, cancelled from outside when shutdown
        is required.
        """
        self._log.info("agent_runner_started", next_agent=self._next_agent)
        try:
            while True:
                processed = await self.run_once()
                if not processed:
                    self._log.debug(
                        "inbox_empty",
                        poll_interval=self._poll_interval,
                    )
                    await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            self._log.info("agent_runner_stopped")
            raise  # always re-raise CancelledError

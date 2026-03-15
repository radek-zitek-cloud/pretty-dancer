"""AgentRunner — bridges LLMAgent and Transport with retry logic."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from multiagent.exceptions import AgentLLMError
from multiagent.transport.base import Message

if TYPE_CHECKING:
    from multiagent.config.settings import Settings
    from multiagent.core.agent import LLMAgent, RunResult
    from multiagent.core.shutdown import ShutdownMonitor
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
        shutdown_monitor: ShutdownMonitor | None = None,
    ) -> None:
        """Initialise the runner with an agent, transport, and settings."""
        self._agent = agent
        self._transport = transport
        self._next_agent = next_agent
        self._shutdown_monitor = shutdown_monitor
        self._max_retries = 3
        self._retry_backoff = 2.0
        self._poll_interval = settings.sqlite_poll_interval_seconds
        self._loop_threshold = settings.agent_loop_detection_threshold
        self._max_messages = settings.agent_max_messages_per_thread
        self._termination_warned = False
        self._log = structlog.get_logger().bind(agent=agent.name)

    @property
    def agent(self) -> LLMAgent:
        """The LLMAgent this runner drives."""
        return self._agent

    @property
    def transport(self) -> Transport:
        """The Transport this runner uses for message I/O."""
        return self._transport

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
        run_result: RunResult | None = None
        for attempt in range(1, self._max_retries + 2):  # +2: retries + initial attempt
            try:
                run_result = await self._agent.run(msg.body, msg.thread_id)
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

        assert run_result is not None  # guaranteed by break above

        # Empty LLM response — don't ack, don't dispatch. The message
        # stays unprocessed and will be retried on the next poll cycle.
        if not run_result.response:
            op_log.warning(
                "empty_response_retry",
                body_len=len(msg.body),
            )
            return False

        assert msg.id is not None  # set by transport on receive
        await self._transport.ack(msg.id)
        op_log.info("message_processed")

        # Dynamic routing takes priority over static next_agent
        effective_next = run_result.next_agent or self._next_agent
        if effective_next:
            if await self._check_loop_detected(
                msg.thread_id, effective_next
            ):
                op_log.warning(
                    "routing_loop_detected",
                    recipient=effective_next,
                    threshold=self._loop_threshold,
                )
                return True

            if await self._check_max_messages(msg.thread_id):
                op_log.warning(
                    "max_messages_reached",
                    count=self._max_messages,
                )
                return True

            await self._transport.send(Message(
                from_agent=self._agent.name,
                to_agent=effective_next,
                body=run_result.response,
                subject=msg.subject,
                thread_id=msg.thread_id,
                parent_id=msg.id,
            ))
            op_log.info("message_forwarded", to_agent=effective_next)

        return True

    def _has_transport_query(self, method: str) -> bool:
        """Check if the transport supports a query method (duck-typing).

        Logs a one-time WARNING if the method is missing, indicating
        termination checks are unavailable for this transport type.
        """
        if hasattr(self._transport, method):
            return True
        if not self._termination_warned:
            self._log.warning(
                "termination_checks_unavailable",
                reason=f"transport lacks '{method}' method",
            )
            self._termination_warned = True
        return False

    async def _check_loop_detected(
        self,
        thread_id: str,
        proposed_recipient: str,
    ) -> bool:
        """Return True if dispatching would extend a self-routing loop.

        Queries the transport for the N most recent messages on this thread.
        If all N were sent by this agent to itself, a loop is detected.
        """
        if proposed_recipient != self._agent.name:
            return False
        if self._loop_threshold == 0:
            return False
        if not self._has_transport_query("thread_messages_tail"):
            return False

        tail = list[tuple[str, str]](
            await self._transport.thread_messages_tail(  # type: ignore[union-attr]
                thread_id, self._loop_threshold,
            )
        )
        if len(tail) < self._loop_threshold:
            return False

        agent_name = self._agent.name
        return all(
            from_a == agent_name and to_a == agent_name
            for from_a, to_a in tail
        )

    async def _check_max_messages(self, thread_id: str) -> bool:
        """Return True if the thread has reached the message ceiling."""
        if self._max_messages == 0:
            return False
        if not self._has_transport_query("thread_message_count"):
            return False

        count = int(
            await self._transport.thread_message_count(  # type: ignore[union-attr]
                thread_id,
            )
        )
        return count >= self._max_messages

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
                if self._shutdown_monitor and self._shutdown_monitor.should_stop(
                    self._agent.name
                ):
                    self._log.info("agent_runner_stop_requested")
                    raise asyncio.CancelledError
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

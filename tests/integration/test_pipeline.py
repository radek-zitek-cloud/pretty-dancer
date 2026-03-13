import asyncio

import pytest

from multiagent.config.settings import Settings
from multiagent.core.agent import LLMAgent
from multiagent.core.runner import AgentRunner
from multiagent.transport.base import Message
from multiagent.transport.sqlite import SQLiteTransport


async def run_until_processed(
    runner: AgentRunner,
    count: int = 1,
    max_wait: float = 60.0,
) -> None:
    """Drive a runner until it has processed ``count`` messages or timeout expires.

    Args:
        runner: The AgentRunner to drive.
        count: Number of messages to process before returning.
        max_wait: Maximum seconds to wait before raising TimeoutError.

    Raises:
        TimeoutError: If ``count`` messages are not processed within ``max_wait`` seconds.
    """
    processed = 0
    loop = asyncio.get_event_loop()
    deadline = loop.time() + max_wait
    while processed < count:
        if loop.time() > deadline:
            raise TimeoutError(
                f"Runner for '{runner.agent.name}' did not process "
                f"{count} message(s) within {max_wait}s"
            )
        did_process = await runner.run_once()
        if did_process:
            processed += 1
        else:
            await asyncio.sleep(0.1)


@pytest.mark.integration
async def test_researcher_critic_pipeline(
    integration_settings: Settings,
    shared_transport: SQLiteTransport,
) -> None:
    """Full pipeline: human -> researcher -> critic.

    Injects one message addressed to researcher. researcher processes it
    and forwards to critic. critic processes it and terminates (no
    next_agent). Asserts both agents produced non-empty string responses.

    This test makes two real LLM API calls.
    """
    researcher = LLMAgent("researcher", integration_settings)
    critic = LLMAgent("critic", integration_settings)

    researcher_runner = AgentRunner(
        researcher, shared_transport, integration_settings, next_agent="critic"
    )
    critic_runner = AgentRunner(
        critic, shared_transport, integration_settings, next_agent=None
    )

    # Inject the initial message
    seed = Message(from_agent="human", to_agent="researcher", body="What is quantum entanglement?")
    await shared_transport.send(seed)

    # Run both agents concurrently
    await asyncio.gather(
        run_until_processed(researcher_runner, count=1),
        run_until_processed(critic_runner, count=1),
    )

    # Verify both messages were processed
    messages = await shared_transport.get_thread(seed.thread_id)
    assert len(messages) == 3  # seed + researcher response + critic response
    for msg in messages[1:]:
        assert isinstance(msg.body, str)
        assert len(msg.body) > 0
        assert msg.processed_at is not None


@pytest.mark.integration
async def test_pipeline_thread_continuity(
    integration_settings: Settings,
    shared_transport: SQLiteTransport,
) -> None:
    """All messages in the pipeline share the seed thread_id.

    Verifies that thread_id is preserved through the full researcher -> critic
    chain — a structural correctness requirement, not an LLM content check.
    """
    researcher = LLMAgent("researcher", integration_settings)
    critic = LLMAgent("critic", integration_settings)

    researcher_runner = AgentRunner(
        researcher, shared_transport, integration_settings, next_agent="critic"
    )
    critic_runner = AgentRunner(
        critic, shared_transport, integration_settings, next_agent=None
    )

    seed = Message(
        from_agent="human", to_agent="researcher", body="Explain neural networks briefly."
    )
    await shared_transport.send(seed)

    await asyncio.gather(
        run_until_processed(researcher_runner, count=1),
        run_until_processed(critic_runner, count=1),
    )

    messages = await shared_transport.get_thread(seed.thread_id)
    assert all(msg.thread_id == seed.thread_id for msg in messages)

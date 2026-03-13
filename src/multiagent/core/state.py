"""Typed state for the LangGraph agent graph."""

from typing import TypedDict


class AgentState(TypedDict):
    """Typed state passed through the LangGraph agent graph.

    This is the only state structure used by LLMAgent's graph. It is
    intentionally minimal for the stateless PoC. Conversation history
    and memory will be added when LangGraph checkpointers are introduced.

    Attributes:
        input: The raw message body the agent will process.
        output: The agent's response after LLM invocation. Empty string
            until the llm node completes.
    """

    input: str
    output: str

"""Transport layer — abstract port and concrete adapters.

Public API:
    Message    — the data contract crossing the transport/core boundary
    Transport  — the abstract base class all adapters must implement
"""

from multiagent.transport.base import Message, Transport

__all__ = ["Message", "Transport"]

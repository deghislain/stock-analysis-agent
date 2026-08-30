"""
Base class for all agents in the agent layer.

Every agent in the pipeline inherits from ``BaseAgent`` and implements the
single ``run`` coroutine.  The consistent interface lets the ``Orchestrator``
call every agent uniformly without knowing its internal implementation.

Agent execution contract
────────────────────────
- ``run(**kwargs)`` is always an ``async`` coroutine.
- It always returns a plain ``dict`` whose keys are defined by the concrete
  agent.  The orchestrator reads these keys to assemble the ``ReportPayload``.
- It must never raise an unhandled exception to the orchestrator — concrete
  agents are responsible for catching their own errors and returning an error
  dict instead (e.g. ``{"error": "...", "status": "failed"}``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """
    Abstract base class that every pipeline agent must extend.

    Subclasses implement ``run(**kwargs)`` as an ``async`` coroutine and
    return a plain dict.  The ``name`` property provides a human-readable
    label used in log messages and job-status updates.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the human-readable name of this agent (e.g. ``"DataAgent"``)."""

    @abstractmethod
    async def run(self, **kwargs) -> dict:
        """
        Execute the agent's task and return the result as a plain dict.

        Keyword arguments are agent-specific; each concrete agent documents
        what it expects.  The returned dict must always contain at least a
        ``"status"`` key with value ``"ok"`` or ``"error"``.

        This method must be implemented as an ``async`` coroutine so the
        orchestrator can ``await`` it and run agents concurrently if needed.
        """

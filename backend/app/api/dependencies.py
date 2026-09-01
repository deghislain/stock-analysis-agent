"""
FastAPI dependency-injection helpers shared across all route modules.

Both singletons are created once at module-import time and reused for the
lifetime of the process.  Tests can override them with ``app.dependency_overrides``.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.job_store import JobStore
from app.core.orchestrator import Orchestrator


# ── Singletons ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _job_store() -> JobStore:
    return JobStore()


@lru_cache(maxsize=1)
def _orchestrator() -> Orchestrator:
    return Orchestrator(job_store=_job_store())


# ── FastAPI dependency callables ──────────────────────────────────────────────


def get_job_store() -> JobStore:
    """
    FastAPI dependency that returns the shared ``JobStore`` singleton.

    Usage::

        @router.get("/example")
        async def example(store: JobStore = Depends(get_job_store)): ...
    """
    return _job_store()


def get_orchestrator() -> Orchestrator:
    """
    FastAPI dependency that returns the shared ``Orchestrator`` singleton.

    Usage::

        @router.post("/analyse")
        async def analyse(orch: Orchestrator = Depends(get_orchestrator)): ...
    """
    return _orchestrator()

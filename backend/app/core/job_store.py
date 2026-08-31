"""
In-memory job store for the async analysis pipeline.

Each analysis request is represented by a ``Job`` object keyed by a UUID
``job_id``.  The ``JobStore`` is a thin wrapper around a plain dict protected
by an ``asyncio.Lock`` so concurrent coroutines cannot race on reads/writes.

Job lifecycle
─────────────
    "pending"   — job created, orchestrator not yet started
    "running"   — orchestrator is executing; ``current_step`` says which agent
    "complete"  — all agents finished; ``result`` holds the full ReportPayload
    "error"     — orchestrator caught an unrecoverable error; ``error`` has details

This store is intentionally in-memory (no database), keeping the setup
dependency-free and the code simple (plan §"Why in-memory job store…").
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

# Sentinel object used in update_job() so that result=None can be written
# explicitly (None is a valid value) while still allowing the parameter to be
# omitted entirely.
_UNSET = object()


# ── Job dataclass ──────────────────────────────────────────────────────────────


@dataclass
class Job:
    """
    Represents a single analysis job.

    Attributes
    ----------
    job_id : str
        UUID string generated at ``POST /api/analyse`` time.
    status : str
        One of ``"pending"``, ``"running"``, ``"complete"``, ``"error"``.
    current_step : str | None
        Human-readable label of the step currently executing
        (e.g. ``"Fetching data"``).  ``None`` when status is not ``"running"``.
    result : Any | None
        The ``ReportPayload`` dict / model once the job is complete;
        ``None`` until then.
    error : str | None
        Error message when status is ``"error"``; ``None`` otherwise.
    """

    job_id: str
    status: str = "pending"
    current_step: str | None = None
    result: Any = field(default=None, repr=False)
    error: str | None = None

    def to_dict(self) -> dict:
        """Return a plain dict representation of this job for API serialisation."""
        return {
            "job_id":       self.job_id,
            "status":       self.status,
            "current_step": self.current_step,
            "result":       self.result,
            "error":        self.error,
        }


# ── JobStore ───────────────────────────────────────────────────────────────────


class JobStore:
    """
    Thread-safe, in-memory store for analysis ``Job`` objects.

    All mutations are guarded by an ``asyncio.Lock`` so concurrent
    coroutines (e.g. a polling GET while the orchestrator is running)
    cannot observe a half-written state.

    Usage
    -----
    ::

        store = JobStore()
        job_id = "550e8400-..."
        store.create_job(job_id)

        await store.update_job(job_id, status="running", current_step="Fetching data")
        await store.update_job(job_id, status="complete", result=payload)

        job = store.get_job(job_id)  # returns Job | None
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    # ── Write operations ──────────────────────────────────────────────────────

    def create_job(self, job_id: str) -> Job:
        """
        Create a new job with status ``"pending"`` and store it.

        This is a *synchronous* method because it is called from the FastAPI
        route handler (before ``BackgroundTasks`` fires) where there is no
        event-loop contention — the lock is therefore not acquired here.

        Parameters
        ----------
        job_id : str
            UUID string for the new job.

        Returns
        -------
        Job
            The newly created ``Job`` object.

        Raises
        ------
        ValueError
            If a job with ``job_id`` already exists (prevents accidental overwrites).
        """
        if job_id in self._jobs:
            raise ValueError(f"Job '{job_id}' already exists in the store.")
        job = Job(job_id=job_id)
        self._jobs[job_id] = job
        return job

    async def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        current_step: str | None = None,
        result: Any = _UNSET,
        error: str | None = None,
    ) -> Job:
        """
        Update one or more fields on an existing job.

        Only the fields that are explicitly passed are changed; all others
        keep their current values.  The special sentinel ``_UNSET`` is used
        for ``result`` so that ``None`` can be written explicitly.

        Parameters
        ----------
        job_id : str
            The job to update.
        status : str | None
            New status value, if provided.
        current_step : str | None
            Step label for the ``"running"`` status, if provided.
        result : Any
            Completed report payload, if provided.
        error : str | None
            Error message, if provided.

        Returns
        -------
        Job
            The updated ``Job`` object.

        Raises
        ------
        KeyError
            If no job with ``job_id`` exists.
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(f"Job '{job_id}' not found in the store.")
            if status is not None:
                job.status = status
            if current_step is not None:
                job.current_step = current_step
            if result is not _UNSET:
                job.result = result
            if error is not None:
                job.error = error
            return job

    # ── Read operations ───────────────────────────────────────────────────────

    def get_job(self, job_id: str) -> Job | None:
        """
        Return the ``Job`` for ``job_id``, or ``None`` if it does not exist.

        This is a synchronous, non-locking read.  In CPython the GIL makes
        a single dict lookup atomic, so no lock is needed for reads.
        """
        return self._jobs.get(job_id)

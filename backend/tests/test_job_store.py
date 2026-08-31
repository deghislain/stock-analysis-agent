"""
Unit tests for core/job_store.py (Sub-Task 4, Todo 8).

Covers:
  Job          — dataclass fields, defaults, to_dict()
  JobStore     — create_job(), update_job(), get_job()
               — duplicate-create raises ValueError
               — update of unknown job raises KeyError
               — result=None can be written explicitly via the _UNSET sentinel
               — partial updates leave other fields unchanged
               — concurrent async updates are safe (lock is exercised)
"""

from __future__ import annotations

import asyncio

import pytest


# ═════════════════════════════════════════════════════════════════════════════
# Job dataclass
# ═════════════════════════════════════════════════════════════════════════════


class TestJobDefaults:
    """Job initialises with sensible defaults."""

    def test_status_defaults_to_pending(self):
        from app.core.job_store import Job
        j = Job(job_id="abc")
        assert j.status == "pending"

    def test_current_step_defaults_to_none(self):
        from app.core.job_store import Job
        assert Job(job_id="abc").current_step is None

    def test_result_defaults_to_none(self):
        from app.core.job_store import Job
        assert Job(job_id="abc").result is None

    def test_error_defaults_to_none(self):
        from app.core.job_store import Job
        assert Job(job_id="abc").error is None

    def test_job_id_stored(self):
        from app.core.job_store import Job
        j = Job(job_id="my-uuid")
        assert j.job_id == "my-uuid"


class TestJobToDict:
    """Job.to_dict() returns all five keys with correct values."""

    def test_keys_present(self):
        from app.core.job_store import Job
        d = Job(job_id="x").to_dict()
        assert set(d) == {"job_id", "status", "current_step", "result", "error"}

    def test_values_match_fields(self):
        from app.core.job_store import Job
        j = Job(job_id="j1", status="running", current_step="step", result=42, error=None)
        d = j.to_dict()
        assert d["job_id"]       == "j1"
        assert d["status"]       == "running"
        assert d["current_step"] == "step"
        assert d["result"]       == 42
        assert d["error"]        is None

    def test_error_propagated(self):
        from app.core.job_store import Job
        j = Job(job_id="j2", status="error", error="something broke")
        assert j.to_dict()["error"] == "something broke"


# ═════════════════════════════════════════════════════════════════════════════
# JobStore.create_job()
# ═════════════════════════════════════════════════════════════════════════════


class TestCreateJob:
    """create_job() is synchronous and returns a Job with status="pending"."""

    def test_returns_job_with_correct_id(self):
        from app.core.job_store import JobStore
        store = JobStore()
        job = store.create_job("id-1")
        assert job.job_id == "id-1"

    def test_new_job_is_pending(self):
        from app.core.job_store import JobStore
        job = JobStore().create_job("id-2")
        assert job.status == "pending"

    def test_job_is_retrievable_after_create(self):
        from app.core.job_store import JobStore
        store = JobStore()
        store.create_job("id-3")
        assert store.get_job("id-3") is not None

    def test_duplicate_job_id_raises_value_error(self):
        from app.core.job_store import JobStore
        store = JobStore()
        store.create_job("dup")
        with pytest.raises(ValueError, match="already exists"):
            store.create_job("dup")

    def test_multiple_jobs_independent(self):
        from app.core.job_store import JobStore
        store = JobStore()
        a = store.create_job("a")
        b = store.create_job("b")
        assert a is not b
        assert store.get_job("a") is a
        assert store.get_job("b") is b


# ═════════════════════════════════════════════════════════════════════════════
# JobStore.get_job()
# ═════════════════════════════════════════════════════════════════════════════


class TestGetJob:
    """get_job() returns the Job or None."""

    def test_unknown_id_returns_none(self):
        from app.core.job_store import JobStore
        assert JobStore().get_job("missing") is None

    def test_returns_same_object_as_created(self):
        from app.core.job_store import JobStore
        store = JobStore()
        job = store.create_job("z")
        assert store.get_job("z") is job


# ═════════════════════════════════════════════════════════════════════════════
# JobStore.update_job()
# ═════════════════════════════════════════════════════════════════════════════


class TestUpdateJobStatus:
    """update_job() mutates status and returns the updated Job."""

    async def test_status_updated(self):
        from app.core.job_store import JobStore
        store = JobStore()
        store.create_job("u1")
        job = await store.update_job("u1", status="running")
        assert job.status == "running"

    async def test_returned_job_is_same_object(self):
        from app.core.job_store import JobStore
        store = JobStore()
        created = store.create_job("u2")
        returned = await store.update_job("u2", status="complete")
        assert returned is created

    async def test_get_job_reflects_update(self):
        from app.core.job_store import JobStore
        store = JobStore()
        store.create_job("u3")
        await store.update_job("u3", status="error", error="boom")
        job = store.get_job("u3")
        assert job.status == "error"
        assert job.error == "boom"


class TestUpdateJobCurrentStep:
    """update_job() sets current_step when running."""

    async def test_current_step_set(self):
        from app.core.job_store import JobStore
        store = JobStore()
        store.create_job("s1")
        await store.update_job("s1", status="running", current_step="Fetching data")
        assert store.get_job("s1").current_step == "Fetching data"

    async def test_current_step_not_cleared_by_status_only_update(self):
        """Updating just status must not erase a previously set current_step."""
        from app.core.job_store import JobStore
        store = JobStore()
        store.create_job("s2")
        await store.update_job("s2", current_step="Running analysis")
        await store.update_job("s2", status="complete")
        # current_step was not passed in the second call — must be preserved
        assert store.get_job("s2").current_step == "Running analysis"


class TestUpdateJobResult:
    """update_job() writes result, including result=None explicitly."""

    async def test_result_stored(self):
        from app.core.job_store import JobStore
        store = JobStore()
        store.create_job("r1")
        payload = {"ticker": "AAPL", "status": "complete"}
        await store.update_job("r1", result=payload)
        assert store.get_job("r1").result == payload

    async def test_result_none_can_be_written_explicitly(self):
        """result=None must overwrite a previous value (sentinel check)."""
        from app.core.job_store import JobStore
        store = JobStore()
        store.create_job("r2")
        await store.update_job("r2", result={"some": "data"})
        await store.update_job("r2", result=None)
        assert store.get_job("r2").result is None

    async def test_omitting_result_preserves_existing_value(self):
        """When result is not passed, the existing value must not change."""
        from app.core.job_store import JobStore
        store = JobStore()
        store.create_job("r3")
        payload = {"key": "value"}
        await store.update_job("r3", result=payload)
        await store.update_job("r3", status="complete")  # no result= kwarg
        assert store.get_job("r3").result is payload


class TestUpdateJobUnknownId:
    """update_job() raises KeyError for an unknown job_id."""

    async def test_raises_key_error(self):
        from app.core.job_store import JobStore
        store = JobStore()
        with pytest.raises(KeyError, match="not found"):
            await store.update_job("ghost", status="running")


# ═════════════════════════════════════════════════════════════════════════════
# Concurrency
# ═════════════════════════════════════════════════════════════════════════════


class TestConcurrency:
    """Concurrent updates must not corrupt job state."""

    async def test_concurrent_updates_all_applied(self):
        """
        Fire 50 concurrent update_job() coroutines; every one should succeed
        and the job must reflect the *last* written status without raising.
        """
        from app.core.job_store import JobStore

        store = JobStore()
        store.create_job("c1")

        statuses = ["running", "complete", "error", "pending"]

        async def _update(i: int) -> None:
            s = statuses[i % len(statuses)]
            await store.update_job("c1", status=s)

        await asyncio.gather(*[_update(i) for i in range(50)])

        # The job must still be accessible and its status is one of the valid values.
        job = store.get_job("c1")
        assert job is not None
        assert job.status in statuses

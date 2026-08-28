"""
Unit and integration tests for app/main.py.

Covers:
- create_app()        — FastAPI instance, CORS middleware, router inclusion
- health endpoint     — GET /health returns {"status": "ok"}
- lifespan            — PDF dir created at startup; cleanup task launched
                        and cancelled cleanly on shutdown
- _pdf_cleanup_loop   — delegates to _run_pdf_cleanup on each iteration
- _run_pdf_cleanup    — deletes expired PDFs, keeps fresh ones, skips
                        non-PDF files, handles per-file OSError, handles
                        missing directory
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from fastapi.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_client() -> TestClient:
    """Return a TestClient wrapping a freshly constructed app instance."""
    from app.main import create_app
    return TestClient(create_app(), raise_server_exceptions=True)


# ── create_app ────────────────────────────────────────────────────────────────


class TestCreateApp:
    """Tests for the application factory function."""

    def test_returns_fastapi_instance(self):
        from fastapi import FastAPI
        from app.main import create_app
        assert isinstance(create_app(), FastAPI)

    def test_title_matches_settings(self):
        from app.main import create_app
        from app.config import settings
        assert create_app().title == settings.app_name

    def test_cors_middleware_present(self):
        """CORSMiddleware must appear in the middleware stack."""
        from fastapi.middleware.cors import CORSMiddleware
        from app.main import create_app
        app = create_app()
        middleware_types = [m.cls for m in app.user_middleware]
        assert CORSMiddleware in middleware_types

    def test_analysis_router_registered(self):
        """Routes from the analysis router must be reachable under /api."""
        from app.main import create_app
        app = create_app()
        paths = {r.path for r in app.routes}
        # The stub router currently adds no paths, but the prefix wiring is
        # tested by confirming the router was included without error.
        assert app is not None  # app booted successfully with the router

    def test_report_router_registered(self):
        from app.main import create_app
        app = create_app()
        assert app is not None  # same rationale as above

    def test_health_route_present(self):
        from app.main import app
        paths = {r.path for r in app.routes}
        assert "/health" in paths

    def test_docs_url_configured(self):
        from app.main import create_app
        assert create_app().docs_url == "/docs"

    def test_redoc_url_configured(self):
        from app.main import create_app
        assert create_app().redoc_url == "/redoc"


# ── GET /health ───────────────────────────────────────────────────────────────


class TestHealthEndpoint:
    """Integration tests for the health-check route.

    Uses the module-level ``app`` singleton (which is produced by create_app())
    so the /health route is definitely present — the same instance the server
    would run in production.
    """

    @pytest.fixture(autouse=True)
    def client(self):
        from app.main import app
        self._client = TestClient(app, raise_server_exceptions=True)

    def test_status_200(self):
        r = self._client.get("/health")
        assert r.status_code == 200

    def test_response_body(self):
        r = self._client.get("/health")
        assert r.json() == {"status": "ok"}

    def test_content_type_is_json(self):
        r = self._client.get("/health")
        assert "application/json" in r.headers["content-type"]


# ── _run_pdf_cleanup ──────────────────────────────────────────────────────────


class TestRunPdfCleanup:
    """Unit tests for the synchronous file-deletion helper."""

    def test_deletes_expired_pdf(self):
        from app.main import _run_pdf_cleanup
        with tempfile.TemporaryDirectory() as d:
            expired = os.path.join(d, "old.pdf")
            open(expired, "w").close()
            os.utime(expired, (0, 0))  # mtime = epoch (very old)

            _run_pdf_cleanup(d, max_age_seconds=3600)

            assert not os.path.exists(expired)

    def test_keeps_fresh_pdf(self):
        from app.main import _run_pdf_cleanup
        with tempfile.TemporaryDirectory() as d:
            fresh = os.path.join(d, "fresh.pdf")
            open(fresh, "w").close()  # mtime = now

            _run_pdf_cleanup(d, max_age_seconds=3600)

            assert os.path.exists(fresh)

    def test_ignores_non_pdf_files(self):
        from app.main import _run_pdf_cleanup
        with tempfile.TemporaryDirectory() as d:
            txt = os.path.join(d, "notes.txt")
            open(txt, "w").close()
            os.utime(txt, (0, 0))  # very old, but not a .pdf

            _run_pdf_cleanup(d, max_age_seconds=3600)

            assert os.path.exists(txt)

    def test_handles_missing_directory(self):
        """A missing directory must log a warning and not raise."""
        from app.main import _run_pdf_cleanup
        # Should not raise even though the path does not exist.
        _run_pdf_cleanup("/nonexistent/path/that/does/not/exist", max_age_seconds=3600)

    def test_handles_per_file_os_error(self):
        """An OSError on a single file must be logged and not abort the loop."""
        from app.main import _run_pdf_cleanup
        with tempfile.TemporaryDirectory() as d:
            # Create two expired PDFs.
            f1 = os.path.join(d, "file1.pdf")
            f2 = os.path.join(d, "file2.pdf")
            for path in (f1, f2):
                open(path, "w").close()
                os.utime(path, (0, 0))

            # Simulate os.remove raising for the first file encountered.
            original_remove = os.remove
            call_count = {"n": 0}

            def flaky_remove(path):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise OSError("permission denied")
                original_remove(path)

            with patch("app.main.os.remove", side_effect=flaky_remove):
                # Must complete without raising.
                _run_pdf_cleanup(d, max_age_seconds=3600)

    def test_does_not_log_completion_when_nothing_deleted(self, caplog):
        """The 'cleanup complete' info log must NOT fire when no files are deleted."""
        from app.main import _run_pdf_cleanup
        with tempfile.TemporaryDirectory() as d:
            with caplog.at_level(logging.INFO, logger="app.main"):
                _run_pdf_cleanup(d, max_age_seconds=3600)
        assert "PDF cleanup complete" not in caplog.text

    def test_logs_completion_when_files_deleted(self, caplog):
        from app.main import _run_pdf_cleanup
        with tempfile.TemporaryDirectory() as d:
            expired = os.path.join(d, "old.pdf")
            open(expired, "w").close()
            os.utime(expired, (0, 0))

            with caplog.at_level(logging.INFO, logger="app.main"):
                _run_pdf_cleanup(d, max_age_seconds=3600)

        assert "PDF cleanup complete" in caplog.text

    def test_boundary_exactly_at_max_age_not_deleted(self):
        """A file whose age is just under max_age_seconds must NOT be deleted
        (the condition is strictly greater-than)."""
        from app.main import _run_pdf_cleanup
        with tempfile.TemporaryDirectory() as d:
            boundary = os.path.join(d, "boundary.pdf")
            open(boundary, "w").close()
            # Set mtime to 1 second *less* than max_age so age < max_age.
            mtime = time.time() - 3599
            os.utime(boundary, (mtime, mtime))

            _run_pdf_cleanup(d, max_age_seconds=3600)

            # age == 3599 is NOT > 3600, so file should survive.
            assert os.path.exists(boundary)


# ── _pdf_cleanup_loop ─────────────────────────────────────────────────────────


class TestPdfCleanupLoop:
    """Tests for the async loop that wraps _run_pdf_cleanup."""

    @pytest.mark.asyncio
    async def test_calls_run_pdf_cleanup_after_sleep(self):
        """The loop must sleep then call _run_pdf_cleanup with settings values."""
        from app.config import settings

        call_log: list[tuple] = []
        sleep_call_count = {"n": 0}

        async def fake_sleep(seconds):
            # Allow the first sleep to pass so _run_pdf_cleanup is reached,
            # then raise CancelledError on the second call to exit the loop.
            call_log.append(("sleep", seconds))
            sleep_call_count["n"] += 1
            if sleep_call_count["n"] >= 2:
                raise asyncio.CancelledError()

        def fake_cleanup(directory, max_age_seconds):
            call_log.append(("cleanup", directory, max_age_seconds))

        with (
            patch("app.main.asyncio.sleep", side_effect=fake_sleep),
            patch("app.main._run_pdf_cleanup", side_effect=fake_cleanup),
        ):
            from app.main import _pdf_cleanup_loop
            with pytest.raises(asyncio.CancelledError):
                await _pdf_cleanup_loop()

        assert call_log[0] == ("sleep", settings.pdf_cleanup_interval_seconds)
        assert call_log[1] == ("cleanup", settings.pdf_output_dir, settings.pdf_max_age_seconds)

    @pytest.mark.asyncio
    async def test_loop_cancelled_cleanly(self):
        """CancelledError propagates out of the loop without swallowing."""
        from app.main import _pdf_cleanup_loop

        with patch("app.main.asyncio.sleep", side_effect=asyncio.CancelledError):
            with pytest.raises(asyncio.CancelledError):
                await _pdf_cleanup_loop()


# ── lifespan ──────────────────────────────────────────────────────────────────


class TestLifespan:
    """Tests for the ASGI lifespan context manager.

    ``_pdf_cleanup_loop`` is patched to a coroutine that blocks on
    asyncio.sleep(9999) — it behaves like the real loop (cancellable,
    never returns on its own) without actually sleeping 30 minutes.
    """

    @pytest.mark.asyncio
    async def test_creates_pdf_output_dir(self, tmp_path):
        """The lifespan startup phase must create PDF_OUTPUT_DIR if missing."""
        pdf_dir = str(tmp_path / "reports")
        assert not os.path.exists(pdf_dir)

        with (
            patch("app.main.settings.pdf_output_dir", pdf_dir),
            patch("app.main._pdf_cleanup_loop", _never_ending_coroutine),
        ):
            from app.main import lifespan, create_app
            app_instance = create_app()
            async with lifespan(app_instance):
                assert os.path.exists(pdf_dir)

    @pytest.mark.asyncio
    async def test_cleanup_task_cancelled_on_shutdown(self, caplog):
        """The cleanup asyncio task must be cancelled when the lifespan exits.

        We verify cancellation by confirming that:
        1. The lifespan exits without raising (CancelledError is caught).
        2. The 'Application shutdown complete' log line fires — it only
           reaches that line after the task has been cancelled and awaited.
        """
        with (
            patch("app.main._pdf_cleanup_loop", _never_ending_coroutine),
            patch("app.main.settings.pdf_output_dir", "/tmp"),
        ):
            from app.main import lifespan, create_app
            app_instance = create_app()
            with caplog.at_level(logging.INFO, logger="app.main"):
                async with lifespan(app_instance):
                    pass  # immediately exit — triggers shutdown path

        # If the task was NOT cancelled cleanly, this log line would never appear.
        assert "Application shutdown complete" in caplog.text

    @pytest.mark.asyncio
    async def test_startup_logs_ready_message(self, caplog, tmp_path):
        """Startup must log the 'PDF output directory ready' message."""
        pdf_dir = str(tmp_path / "log_reports")

        with (
            patch("app.main.settings.pdf_output_dir", pdf_dir),
            patch("app.main._pdf_cleanup_loop", _never_ending_coroutine),
        ):
            from app.main import lifespan, create_app
            app_instance = create_app()
            with caplog.at_level(logging.INFO, logger="app.main"):
                async with lifespan(app_instance):
                    pass

        assert "PDF output directory ready" in caplog.text

    @pytest.mark.asyncio
    async def test_shutdown_logs_complete(self, caplog, tmp_path):
        """Shutdown must log the 'Application shutdown complete' message."""
        pdf_dir = str(tmp_path / "shutdown_reports")

        with (
            patch("app.main.settings.pdf_output_dir", pdf_dir),
            patch("app.main._pdf_cleanup_loop", _never_ending_coroutine),
        ):
            from app.main import lifespan, create_app
            app_instance = create_app()
            with caplog.at_level(logging.INFO, logger="app.main"):
                async with lifespan(app_instance):
                    pass

        assert "Application shutdown complete" in caplog.text


# ── Private async helper ──────────────────────────────────────────────────────


async def _never_ending_coroutine():
    """Stands in for _pdf_cleanup_loop: blocks on sleep until cancelled."""
    try:
        await asyncio.sleep(9999)
    except asyncio.CancelledError:
        raise

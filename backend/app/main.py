"""
FastAPI application entry point for the Stock Analysis Agent backend.

Responsibilities:
- Boot the FastAPI app with CORS middleware.
- Register all API routers under the /api prefix.
- Expose a health-check endpoint at GET /health.
- Use a lifespan context manager to:
    (a) create the PDF output directory at startup,
    (b) run a background task every 30 minutes that deletes PDF files
        older than 1 hour, keeping disk usage under control, and
    (c) call init_db() to create portfolio tables on first boot.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logger import configure_logging, get_logger
from app.api.routes.analysis import router as analysis_router
from app.api.routes.report import router as report_router
from app.api.routes.portfolios import router as portfolios_router
from app.api.routes.screener import router as screener_router
from app.api.routes.watchlist import router as watchlist_router
from app.portfolio.database import init_db, SessionLocal
from app.portfolio.scheduler import start_scheduler, stop_scheduler

# Configure logging as the very first thing so all subsequent log calls
# (including those that fire during import) use the right format.
configure_logging(debug=settings.debug)

logger = get_logger(__name__)


# ── PDF cleanup background task ───────────────────────────────────────────────


async def _pdf_cleanup_loop() -> None:
    """
    Runs forever, waking every ``pdf_cleanup_interval_seconds`` seconds to
    delete any ``.pdf`` files in ``PDF_OUTPUT_DIR`` that are older than
    ``pdf_max_age_seconds`` seconds.
    """
    interval = settings.pdf_cleanup_interval_seconds
    max_age = settings.pdf_max_age_seconds
    output_dir = settings.pdf_output_dir

    logger.info(
        "PDF cleanup task started",
        extra={
            "interval_seconds": interval,
            "max_age_seconds": max_age,
            "directory": output_dir,
        },
    )

    while True:
        await asyncio.sleep(interval)
        _run_pdf_cleanup(output_dir, max_age)


def _run_pdf_cleanup(directory: str, max_age_seconds: int) -> None:
    """
    Scan ``directory`` and delete every ``.pdf`` file whose last-modified
    time is older than ``max_age_seconds``.  Errors on individual files are
    logged and skipped so one bad file never breaks the loop.
    """
    now = time.time()
    deleted = 0

    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if not entry.name.endswith(".pdf"):
                    continue
                try:
                    age = now - entry.stat().st_mtime
                    if age > max_age_seconds:
                        os.remove(entry.path)
                        deleted += 1
                        logger.debug(
                            "Deleted expired PDF",
                            extra={"file": entry.name, "age_seconds": int(age)},
                        )
                except OSError as exc:
                    logger.warning(
                        "Could not remove PDF file",
                        extra={"file": entry.name, "error": str(exc)},
                    )
    except FileNotFoundError:
        # Directory was removed externally; recreate on next startup, ignore here.
        logger.warning(
            "PDF output directory not found during cleanup",
            extra={"directory": directory},
        )

    if deleted:
        logger.info("PDF cleanup complete", extra={"deleted_files": deleted})


# ── Lifespan context manager ──────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manages application startup and shutdown:
    - Creates the PDF output directory if it does not exist.
    - Launches the PDF cleanup background task.
    - Calls init_db() to create portfolio tables (no-op when they already exist).
    - Starts the APScheduler quarterly refresh scheduler.
    - Cancels the cleanup task and stops the scheduler cleanly on shutdown.
    """
    from app.api.dependencies import get_job_store, get_orchestrator  # avoid circular import

    # ── Startup ───────────────────────────────────────────────────────────────
    pdf_dir = settings.pdf_output_dir
    os.makedirs(pdf_dir, exist_ok=True)
    logger.info("PDF output directory ready", extra={"directory": pdf_dir})

    # Warn early if the API key is missing so the problem is obvious in logs
    # at boot time rather than surfacing only on the first LLM request.
    if not settings.groq_api_key:
        logger.warning(
            "GROQ_API_KEY is not set — AI-generated explanations will be "
            "unavailable. Set the env var before starting the server."
        )

    # Log FinBERT availability so operators know which sentiment path is active.
    try:
        import transformers  # noqa: F401
        logger.info(
            "FinBERT sentiment: transformers package found — "
            "ProsusAI/finbert will be loaded on first sentiment request."
        )
    except ImportError:
        logger.warning(
            "FinBERT sentiment: transformers not installed — "
            "falling back to keyword-based sentiment scoring."
        )

    init_db()

    # Resolve the shared orchestrator and job-store singletons that are also
    # used by the route handlers, then pass them to the scheduler.
    _job_store = get_job_store()
    _orchestrator = get_orchestrator()
    start_scheduler(_orchestrator, _job_store, SessionLocal)

    cleanup_task = asyncio.create_task(_pdf_cleanup_loop())
    logger.info("Application startup complete", extra={"app": settings.app_name})

    yield  # application is running

    # ── Shutdown ──────────────────────────────────────────────────────────────
    stop_scheduler()
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass  # expected — task was cancelled on purpose
    logger.info("Application shutdown complete")


# ── FastAPI app ───────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """
    Construct and return the configured FastAPI application instance.

    Separating construction into this factory function makes it easy to
    create test instances without running the full lifespan machinery.
    """
    application = FastAPI(
        title=settings.app_name,
        description=(
            "Agentic stock analysis for beginner investors. "
            "For informational purposes only — not financial advice."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS middleware ───────────────────────────────────────────────────────
    # Allows the React frontend (running on a different port during development)
    # to call the API.  Only the HTTP methods and headers actually used by the
    # frontend are allowed — wildcards are avoided so the policy is explicit.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    # All API routes live under /api so they are easy to proxy in production.
    application.include_router(analysis_router, prefix="/api", tags=["analysis"])
    application.include_router(report_router, prefix="/api", tags=["report"])
    application.include_router(portfolios_router, prefix="/api", tags=["portfolios"])
    application.include_router(screener_router, prefix="/api", tags=["screener"])
    application.include_router(watchlist_router, prefix="/api", tags=["watchlist"])

    # ── Request-ID middleware ─────────────────────────────────────────────────
    # Injects an X-Request-ID header into every response (using the incoming
    # header value if the client sent one, otherwise generating a new UUID).
    # The ID is stored in request.state so route handlers and background tasks
    # can attach it to log records for end-to-end trace correlation.
    @application.middleware("http")
    async def request_id_middleware(request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = req_id
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

    # ── Health check ──────────────────────────────────────────────────────────
    # Registered here (inside the factory) so every app instance created by
    # create_app() — including test instances — gets the route.
    @application.get("/health", tags=["health"], summary="Health check")
    async def health() -> dict[str, str | bool]:
        """
        Return liveness + DB connectivity status.

        Performs a ``SELECT 1`` against the portfolio database so that a
        failed or mis-configured database is detected immediately rather than
        on the first portfolio request.  The container healthcheck in
        docker-compose.yml calls this endpoint every 30 s.
        """
        db_ok = False
        try:
            from app.portfolio.database import SessionLocal as _SL
            from sqlalchemy import text

            with _SL() as _db:
                _db.execute(text("SELECT 1"))
            db_ok = True
        except Exception as _exc:  # noqa: BLE001
            logger.warning("Health check: DB connectivity failed", extra={"error": str(_exc)})

        return {"status": "ok", "db": db_ok}

    return application


app = create_app()

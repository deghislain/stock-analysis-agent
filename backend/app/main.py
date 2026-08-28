"""
FastAPI application entry point for the Stock Analysis Agent backend.

Responsibilities:
- Boot the FastAPI app with CORS middleware.
- Register all API routers under the /api prefix.
- Expose a health-check endpoint at GET /health.
- Use a lifespan context manager to:
    (a) create the PDF output directory at startup, and
    (b) run a background task every 30 minutes that deletes PDF files
        older than 1 hour, keeping disk usage under control.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logger import configure_logging, get_logger
from app.api.routes.analysis import router as analysis_router
from app.api.routes.report import router as report_router

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
    - Cancels the cleanup task cleanly on shutdown.
    """
    # ── Startup ───────────────────────────────────────────────────────────────
    pdf_dir = settings.pdf_output_dir
    os.makedirs(pdf_dir, exist_ok=True)
    logger.info("PDF output directory ready", extra={"directory": pdf_dir})

    cleanup_task = asyncio.create_task(_pdf_cleanup_loop())
    logger.info("Application startup complete", extra={"app": settings.app_name})

    yield  # application is running

    # ── Shutdown ──────────────────────────────────────────────────────────────
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
    # to call the API.  In production, restrict this to your actual domain.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    # All API routes live under /api so they are easy to proxy in production.
    application.include_router(analysis_router, prefix="/api", tags=["analysis"])
    application.include_router(report_router, prefix="/api", tags=["report"])

    # ── Health check ──────────────────────────────────────────────────────────
    # Registered here (inside the factory) so every app instance created by
    # create_app() — including test instances — gets the route.
    @application.get("/health", tags=["health"], summary="Health check")
    async def health() -> dict[str, str]:
        """Return a simple status payload confirming the API is reachable."""
        return {"status": "ok"}

    return application


app = create_app()

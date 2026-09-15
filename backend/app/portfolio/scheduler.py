"""
Quarterly refresh scheduler for the Portfolio module (Sub-Task P4).

Public API
──────────
    scheduler               — module-level ``AsyncIOScheduler`` instance.
    start_scheduler(orchestrator, job_store, db_session_factory)
                            — add the quarterly cron job and start the scheduler.
                              No-op when ``QUARTERLY_REFRESH_ENABLED=false``.
    stop_scheduler()        — gracefully shut down the scheduler on app teardown.
    run_portfolio_refresh(portfolio_id, orchestrator, job_store, db_session_factory)
                            — refresh a *single* portfolio; used by both the
                              quarterly job and the manual ``POST .../refresh``
                              endpoint.

Quarterly trigger
─────────────────
    Fires at 07:00 UTC on the 2nd of January, April, July, and October
    (first weekday after quarter close, allowing one day for markets to settle).

    CronTrigger config:
        month  = "1,4,7,10"
        day    = "2"
        hour   = "7"
        minute = "0"

    During development uncomment the ``minute="*/2"`` block and comment the
    production block to verify the end-to-end flow every 2 minutes.
    Revert before committing.

Concurrency
───────────
    ``asyncio.Semaphore(3)`` caps concurrent ``orchestrator.run()`` calls so
    that a large portfolio does not fire dozens of simultaneous Groq API calls,
    yfinance requests, and DuckDuckGo searches at once.  The semaphore wraps
    the *individual stock* run, not the outer portfolio loop, so stocks from the
    same portfolio can proceed concurrently up to the limit.

Error handling
──────────────
    A failure on one stock is logged as a warning and skipped — it does not
    abort the rest of the portfolio or the refresh of other portfolios.  After
    all stocks are attempted (regardless of individual outcomes), a ranking
    snapshot is written for every portfolio that had at least one scored stock.

Design notes
────────────
- ``AsyncIOScheduler`` runs in the same asyncio event loop as FastAPI/uvicorn.
  No separate thread or process is created.
- The ``db_session_factory`` argument is the ``SessionLocal`` callable from
  ``app/portfolio/database.py``.  A fresh session is opened and closed inside
  each refresh call — never reused across jobs.
- The ``JobStore`` is passed in so the scheduler can call
  ``job_store.create_job()`` before dispatching ``orchestrator.run()``, matching
  the pattern used by the route handlers.
- Sub-scores (fundamental, technical, sentiment) are extracted from the
  completed ``ReportPayload`` result and injected into the ranking entries
  *before* ``crud.save_ranking_snapshot`` is called, so historical snapshots
  show the full breakdown.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

# ── Module-level scheduler handle ────────────────────────────────────────────

# Initialised to None; replaced by a fresh AsyncIOScheduler inside
# start_scheduler() each time it is called.  This avoids the stale-event-loop
# problem that occurs when TestClient creates a new event loop per test while
# a previously created AsyncIOScheduler still holds a reference to the old one.
scheduler: AsyncIOScheduler | None = None
"""
Active ``AsyncIOScheduler`` instance, or ``None`` before ``start_scheduler()``
is called (or after ``stop_scheduler()`` completes).

``start_scheduler()`` creates a fresh instance, attaches the quarterly cron
job, and starts it.  ``stop_scheduler()`` shuts it down.
Both are wired into the FastAPI ``lifespan`` context manager in ``app/main.py``.
"""

# Semaphore that caps concurrent orchestrator calls across all refresh jobs.
# Defined at module level so all concurrent calls share the same limit.
_refresh_semaphore: asyncio.Semaphore = asyncio.Semaphore(3)


# ── Public lifecycle helpers ──────────────────────────────────────────────────


def start_scheduler(
    orchestrator,
    job_store,
    db_session_factory: Callable,
) -> None:
    """
    Register the quarterly refresh cron job and start the scheduler.

    When ``settings.quarterly_refresh_enabled`` is ``False`` this function
    returns immediately without adding any jobs — a clean no-op that keeps
    development and test environments quiet.

    Parameters
    ----------
    orchestrator:
        The ``Orchestrator`` instance created during app startup.
    job_store:
        The ``JobStore`` instance shared across the app.
    db_session_factory:
        Callable that returns a new ``Session`` — typically ``SessionLocal``
        imported from ``app.portfolio.database``.
    """
    global scheduler  # noqa: PLW0603 — intentional module-level reassignment

    if not settings.quarterly_refresh_enabled:
        logger.info(
            "Quarterly refresh scheduler disabled via config "
            "(QUARTERLY_REFRESH_ENABLED=false)."
        )
        return

    # Create a fresh scheduler instance each time so it binds to the current
    # event loop (required for correct behaviour under TestClient which creates
    # a new event loop per test, and for clean restarts in production).
    scheduler = AsyncIOScheduler()

    # ── Production schedule ───────────────────────────────────────────────────
    # Fires at 07:00 UTC on the 2nd of January, April, July, and October.
    trigger = CronTrigger(month="1,4,7,10", day="2", hour="7", minute="0")

    # ── Development schedule (uncomment to test every 2 minutes) ─────────────
    # trigger = CronTrigger(minute="*/2")
    # NOTE: revert to the production schedule above before committing.

    scheduler.add_job(
        _quarterly_refresh,
        trigger=trigger,
        id="quarterly_portfolio_refresh",
        name="Quarterly portfolio refresh",
        replace_existing=True,
        kwargs={
            "orchestrator": orchestrator,
            "job_store": job_store,
            "db_session_factory": db_session_factory,
        },
    )

    scheduler.start()
    logger.info(
        "Quarterly refresh scheduler started",
        extra={"trigger": str(trigger)},
    )


def stop_scheduler() -> None:
    """
    Gracefully shut down the scheduler.

    Safe to call even when ``start_scheduler()`` returned early (``scheduler``
    is ``None`` or not running) — the guard below makes this a no-op.
    """
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Quarterly refresh scheduler stopped.")


# ── Quarterly job ─────────────────────────────────────────────────────────────


async def _quarterly_refresh(
    orchestrator,
    job_store,
    db_session_factory: Callable,
) -> None:
    """
    Scheduled job: re-analyse every stock in every portfolio and save snapshots.

    Iterates over all portfolios and delegates each one to
    ``run_portfolio_refresh()``.  Failures on individual portfolios are caught
    and logged so a bad portfolio does not abort the whole batch.

    Parameters
    ----------
    orchestrator:
        Shared ``Orchestrator`` instance.
    job_store:
        Shared ``JobStore`` instance.
    db_session_factory:
        Callable that returns a new ``Session``.
    """
    from app.portfolio import crud  # deferred to avoid circular imports at module level

    logger.info("Quarterly refresh job started.")

    db = db_session_factory()
    try:
        portfolios = crud.list_portfolios(db)
    finally:
        db.close()

    if not portfolios:
        logger.info("Quarterly refresh: no portfolios found — nothing to do.")
        return

    logger.info(
        "Quarterly refresh: processing portfolios",
        extra={"portfolio_count": len(portfolios)},
    )

    for portfolio in portfolios:
        try:
            await run_portfolio_refresh(
                portfolio.id,
                orchestrator,
                job_store,
                db_session_factory,
                trigger="quarterly",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Quarterly refresh: portfolio failed — skipping",
                extra={"portfolio_id": portfolio.id, "error": str(exc)},
            )

    logger.info("Quarterly refresh job complete.")


# ── Per-portfolio refresh (shared by scheduler and manual endpoint) ───────────


async def run_portfolio_refresh(
    portfolio_id: str,
    orchestrator,
    job_store,
    db_session_factory: Callable,
    trigger: str = "manual",
) -> None:
    """
    Re-analyse every stock in ``portfolio_id`` and write a new ranking snapshot.

    This coroutine is called from two places:
      1. ``_quarterly_refresh`` — with ``trigger="quarterly"``.
      2. ``POST /api/portfolios/{id}/refresh`` route — with ``trigger="manual"``
         via FastAPI ``BackgroundTasks``.

    Algorithm
    ---------
    1. Load all stocks for the portfolio from the database.
    2. For each stock, create a new job in the ``JobStore`` and call
       ``orchestrator.run(ticker, job_id)`` — capped by ``_refresh_semaphore``
       to at most 3 concurrent calls.
    3. After all stocks are processed, query the completed job results from the
       ``JobStore`` and update each ``PortfolioStock`` row via
       ``crud.update_stock_from_report``.
    4. Build ranking entries (with sub-scores injected from the fresh reports)
       and call ``crud.save_ranking_snapshot`` to write the new snapshot.

    Failures on individual stocks are logged as warnings and skipped — they do
    not abort the portfolio refresh or the outer quarterly batch.

    Parameters
    ----------
    portfolio_id:
        UUID string of the portfolio to refresh.
    orchestrator:
        Shared ``Orchestrator`` instance.
    job_store:
        Shared ``JobStore`` instance.
    db_session_factory:
        Callable returning a new ``Session``.
    trigger:
        ``"manual"`` or ``"quarterly"`` — recorded in the snapshot row.
    """
    from app.portfolio import crud, ranking  # deferred to avoid circular imports

    logger.info(
        "Portfolio refresh started",
        extra={"portfolio_id": portfolio_id, "trigger": trigger},
    )

    # ── Load portfolio stocks ─────────────────────────────────────────────────
    db = db_session_factory()
    try:
        portfolio = crud.get_portfolio(db, portfolio_id)
        if portfolio is None:
            logger.warning(
                "Portfolio refresh: portfolio not found — aborting",
                extra={"portfolio_id": portfolio_id},
            )
            return
        tickers: list[str] = [s.ticker for s in portfolio.stocks]
    finally:
        db.close()

    if not tickers:
        logger.info(
            "Portfolio refresh: no stocks to refresh",
            extra={"portfolio_id": portfolio_id},
        )
        return

    # ── Run analysis for each stock (semaphore-limited concurrency) ───────────
    # Map ticker → job_id so we can retrieve results afterwards.
    ticker_to_job_id: dict[str, str] = {}

    async def _refresh_one(ticker: str) -> None:
        job_id = str(uuid.uuid4())
        ticker_to_job_id[ticker] = job_id
        job_store.create_job(job_id)
        async with _refresh_semaphore:
            try:
                await orchestrator.run(ticker, job_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Portfolio refresh: stock analysis failed — skipping",
                    extra={
                        "portfolio_id": portfolio_id,
                        "ticker": ticker,
                        "job_id": job_id,
                        "error": str(exc),
                    },
                )

    await asyncio.gather(*[_refresh_one(t) for t in tickers])

    # ── Update DB rows and build enriched ranking entries ─────────────────────
    db = db_session_factory()
    try:
        enriched_stocks: list = []  # objects that compute_ranking can sort

        for ticker in tickers:
            job_id = ticker_to_job_id.get(ticker)
            job = job_store.get_job(job_id) if job_id else None

            if job is None or job.status != "complete" or job.result is None:
                logger.warning(
                    "Portfolio refresh: stock result unavailable — skipping DB update",
                    extra={"portfolio_id": portfolio_id, "ticker": ticker},
                )
                # Still include the existing stock row so it appears in the
                # ranking (with whatever score it already had, or None).
                existing = crud.get_portfolio(db, portfolio_id)
                if existing:
                    matched = next(
                        (s for s in existing.stocks if s.ticker == ticker), None
                    )
                    if matched:
                        enriched_stocks.append(matched)
                continue

            # job.result may be a dict or a Pydantic model.
            result = job.result
            report: dict = result if isinstance(result, dict) else result.model_dump()

            # Persist updated scores back to portfolio_stocks.
            updated = crud.update_stock_from_report(db, portfolio_id, ticker, report)
            if updated is None:
                logger.warning(
                    "Portfolio refresh: update_stock_from_report returned None",
                    extra={"portfolio_id": portfolio_id, "ticker": ticker},
                )
                continue

            # Attach sub-scores to the ORM object as transient attributes so
            # compute_ranking (which reads only overall_score) can be augmented
            # by the snapshot writer below.
            fundamental_result: dict = report.get("fundamental_result") or {}
            technical_result: dict = report.get("technical_result") or {}
            sentiment_result: dict = report.get("sentiment_result") or {}

            updated._fundamental_score = fundamental_result.get("score")
            updated._technical_score = technical_result.get("score")
            updated._sentiment_score = sentiment_result.get("score")

            enriched_stocks.append(updated)

        # ── Build ranking entries with sub-scores ─────────────────────────────
        ranked: list[dict] = ranking.compute_ranking(enriched_stocks)

        # Inject the sub-scores from the transient attributes set above so the
        # snapshot rows carry the full breakdown (fundamental / technical /
        # sentiment).
        stock_map = {s.ticker: s for s in enriched_stocks}
        for entry in ranked:
            stock_obj = stock_map.get(entry["ticker"])
            if stock_obj is not None:
                entry["fundamental_score"] = getattr(
                    stock_obj, "_fundamental_score", None
                )
                entry["technical_score"] = getattr(
                    stock_obj, "_technical_score", None
                )
                entry["sentiment_score"] = getattr(
                    stock_obj, "_sentiment_score", None
                )

        # ── Save snapshot ─────────────────────────────────────────────────────
        if ranked:
            crud.save_ranking_snapshot(db, portfolio_id, ranked, trigger=trigger)
            logger.info(
                "Portfolio refresh complete — snapshot saved",
                extra={
                    "portfolio_id": portfolio_id,
                    "trigger": trigger,
                    "stock_count": len(ranked),
                },
            )
        else:
            logger.warning(
                "Portfolio refresh: no ranked entries produced — snapshot not saved",
                extra={"portfolio_id": portfolio_id},
            )

    finally:
        db.close()

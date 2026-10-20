"""
Watchlist route handlers.

Endpoints
─────────
    GET    /api/watchlist             — list all watchlist entries sorted by score
    POST   /api/watchlist/{ticker}    — add a ticker to the watchlist
    DELETE /api/watchlist/{ticker}    — remove a ticker from the watchlist

The watchlist is a lightweight "candidates" list distinct from the portfolio.
Entries accumulate the most recent overall_score and recommendation so they
can be compared side-by-side without hitting the job store.

When a ticker is added, the route kicks off a background analysis job if no
recent (< 24 h) job result is found in the report cache.  The cached result
is used to pre-populate the score so the watchlist is useful immediately.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_job_store, get_orchestrator
from app.core.job_store import JobStore
from app.core.orchestrator import Orchestrator
from app.logger import get_logger
from app.portfolio import crud
from app.schemas.portfolio import WatchlistEntryOut, WatchlistOut

logger = get_logger(__name__)

router = APIRouter()

# Ticker format validation (mirrors analysis.py).
_TICKER_RE = re.compile(r"^[A-Z0-9]{1,5}([.\-][A-Z]{1,2})?$")

# Maximum age of a cached analysis before a background refresh is triggered.
_CACHE_REFRESH_THRESHOLD = timedelta(hours=24)


# ── GET /api/watchlist ────────────────────────────────────────────────────────


@router.get(
    "/watchlist",
    response_model=WatchlistOut,
    summary="List watchlist entries",
    description="Return all watchlist entries sorted by overall_score descending.",
)
def list_watchlist(db: Session = Depends(get_db)) -> WatchlistOut:
    """Return all watchlist entries."""
    entries = crud.get_watchlist(db)
    return WatchlistOut(
        entries=[WatchlistEntryOut.model_validate(e) for e in entries],
        total=len(entries),
    )


# ── POST /api/watchlist/{ticker} ──────────────────────────────────────────────


@router.post(
    "/watchlist/{ticker}",
    response_model=WatchlistEntryOut,
    status_code=http_status.HTTP_201_CREATED,
    summary="Add ticker to watchlist",
    description=(
        "Add a ticker to the watchlist. "
        "Triggers a background analysis if no recent cached result is available. "
        "Returns 409 when the ticker is already on the watchlist."
    ),
)
async def add_to_watchlist(
    ticker: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    store: JobStore = Depends(get_job_store),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> WatchlistEntryOut:
    """Add ``ticker`` to the watchlist and optionally trigger analysis."""
    ticker = ticker.upper().strip()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid ticker format: '{ticker}'.",
        )

    entry, created = crud.add_to_watchlist(db, ticker)
    if not created:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"'{ticker}' is already on the watchlist.",
        )

    # If the entry has never been analysed or the last analysis is stale,
    # kick off a background job and update the entry when it completes.
    needs_refresh = (
        entry.last_analysed_at is None
        or (datetime.now(timezone.utc) - entry.last_analysed_at.replace(tzinfo=timezone.utc))
        > _CACHE_REFRESH_THRESHOLD
    )

    if needs_refresh:
        job_id = store.create_job(ticker)
        logger.info(
            "Watchlist add — triggering background analysis",
            extra={"ticker": ticker, "job_id": job_id},
        )
        background_tasks.add_task(orchestrator.run, ticker, job_id)

    return WatchlistEntryOut.model_validate(entry)


# ── DELETE /api/watchlist/{ticker} ────────────────────────────────────────────


@router.delete(
    "/watchlist/{ticker}",
    response_model=None,
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Remove ticker from watchlist",
    description="Remove a ticker from the watchlist. Returns 404 when not found.",
)
def remove_from_watchlist(
    ticker: str,
    db: Session = Depends(get_db),
) -> None:
    """Remove ``ticker`` from the watchlist."""
    ticker = ticker.upper().strip()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid ticker format: '{ticker}'.",
        )
    removed = crud.remove_from_watchlist(db, ticker)
    if not removed:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"'{ticker}' is not on the watchlist.",
        )

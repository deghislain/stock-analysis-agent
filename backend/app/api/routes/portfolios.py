"""
Portfolio route handlers — Sub-Task P2.

Endpoints
─────────
    GET    /api/portfolios                            — list all portfolios
    POST   /api/portfolios                            — create a portfolio
    GET    /api/portfolios/{portfolio_id}             — get one portfolio + stocks
    PATCH  /api/portfolios/{portfolio_id}             — rename / re-describe
    DELETE /api/portfolios/{portfolio_id}             — delete portfolio + cascade
    POST   /api/portfolios/{portfolio_id}/stocks      — add a stock from a report
    DELETE /api/portfolios/{portfolio_id}/stocks/{ticker}  — remove a stock
    GET    /api/portfolios/{portfolio_id}/ranking     — live ranked stock list
    POST   /api/portfolios/{portfolio_id}/refresh     — trigger manual refresh
    GET    /api/portfolios/{portfolio_id}/history     — list ranking snapshots
    GET    /api/portfolios/{portfolio_id}/history/{snapshot_id} — full snapshot

Design notes
────────────
- Handlers are intentionally thin: validate input, call crud.py or ranking.py,
  return a Pydantic schema.  No ORM or SQL appears here.
- ``POST .../stocks`` validates job completeness via the JobStore *before*
  touching the DB to avoid a partial insert that would be rolled back anyway.
- Ticker uniqueness is pre-checked in the route handler (HTTP 409) AND enforced
  by the UniqueConstraint on the model as a final safety net.
- ``POST .../refresh`` returns 202 immediately; the heavy work runs inside
  FastAPI BackgroundTasks via ``run_portfolio_refresh`` from scheduler.py.
- ``GET .../history`` returns snapshots without their entries (lightweight list
  view); ``GET .../history/{snapshot_id}`` fetches one snapshot with entries
  fully loaded (detail view).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_job_store, get_orchestrator
from app.core.job_store import JobStore
from app.core.orchestrator import Orchestrator
from app.logger import get_logger
from app.portfolio import crud
from app.portfolio.database import SessionLocal
from app.schemas.portfolio import (
    PortfolioCreate,
    PortfolioOut,
    PortfolioStockIn,
    PortfolioStockOut,
    PortfolioUpdate,
    RankingEntryOut,
    RankingSnapshotOut,
)

logger = get_logger(__name__)

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_portfolio_or_404(db: Session, portfolio_id: str):
    """
    Fetch a portfolio by ID or raise HTTP 404 with a clear message.

    Used by every endpoint that operates on a specific portfolio so the
    404 detail string is consistent across the API.
    """
    portfolio = crud.get_portfolio(db, portfolio_id)
    if portfolio is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio '{portfolio_id}' not found.",
        )
    return portfolio


# ── GET /api/portfolios ───────────────────────────────────────────────────────


@router.get(
    "/portfolios",
    response_model=list[PortfolioOut],
    summary="List all portfolios",
    description="Return all portfolios ordered by creation date (oldest first).",
)
def list_portfolios(db: Session = Depends(get_db)) -> list[PortfolioOut]:
    """Return every portfolio with its stock list."""
    portfolios = crud.list_portfolios(db)
    return [PortfolioOut.model_validate(p) for p in portfolios]


# ── POST /api/portfolios ──────────────────────────────────────────────────────


@router.post(
    "/portfolios",
    response_model=PortfolioOut,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create a portfolio",
    description="Create a new named portfolio. Returns the created portfolio.",
)
def create_portfolio(
    body: PortfolioCreate,
    db: Session = Depends(get_db),
) -> PortfolioOut:
    """Insert a new portfolio row and return it."""
    portfolio = crud.create_portfolio(db, name=body.name, description=body.description)
    logger.info("Portfolio created", extra={"portfolio_id": portfolio.id, "portfolio_name": portfolio.name})
    return PortfolioOut.model_validate(portfolio)


# ── GET /api/portfolios/{portfolio_id} ────────────────────────────────────────


@router.get(
    "/portfolios/{portfolio_id}",
    response_model=PortfolioOut,
    summary="Get a portfolio",
    description="Return a single portfolio with all its stocks. 404 when not found.",
)
def get_portfolio(
    portfolio_id: str,
    db: Session = Depends(get_db),
) -> PortfolioOut:
    """Fetch one portfolio by ID."""
    portfolio = _get_portfolio_or_404(db, portfolio_id)
    return PortfolioOut.model_validate(portfolio)


# ── PATCH /api/portfolios/{portfolio_id} ──────────────────────────────────────


@router.patch(
    "/portfolios/{portfolio_id}",
    response_model=PortfolioOut,
    summary="Update a portfolio",
    description=(
        "Partially update a portfolio's name and/or description. "
        "Omitted fields are left unchanged. 404 when not found."
    ),
)
def update_portfolio(
    portfolio_id: str,
    body: PortfolioUpdate,
    db: Session = Depends(get_db),
) -> PortfolioOut:
    """Apply a partial update to a portfolio's metadata."""
    # Confirm existence before update so the 404 message is consistent.
    _get_portfolio_or_404(db, portfolio_id)

    updated = crud.update_portfolio(
        db,
        portfolio_id,
        name=body.name,
        description=body.description,
    )
    logger.info("Portfolio updated", extra={"portfolio_id": portfolio_id})
    return PortfolioOut.model_validate(updated)


# ── DELETE /api/portfolios/{portfolio_id} ─────────────────────────────────────


@router.delete(
    "/portfolios/{portfolio_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a portfolio",
    description=(
        "Delete a portfolio and all its stocks and ranking snapshots. "
        "Returns 204 on success, 404 when not found."
    ),
)
def delete_portfolio(
    portfolio_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a portfolio; cascade removes all child rows."""
    deleted = crud.delete_portfolio(db, portfolio_id)
    if not deleted:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio '{portfolio_id}' not found.",
        )
    logger.info("Portfolio deleted", extra={"portfolio_id": portfolio_id})


# ── POST /api/portfolios/{portfolio_id}/stocks ────────────────────────────────


@router.post(
    "/portfolios/{portfolio_id}/stocks",
    response_model=PortfolioStockOut,
    status_code=http_status.HTTP_201_CREATED,
    summary="Add a stock to a portfolio",
    description=(
        "Add a stock to a portfolio using data from a completed analysis report. "
        "Returns 404 when the portfolio is not found, "
        "422 when the referenced job is not complete, "
        "409 when the ticker is already in the portfolio."
    ),
)
def add_stock(
    portfolio_id: str,
    body: PortfolioStockIn,
    db: Session = Depends(get_db),
    store: JobStore = Depends(get_job_store),
) -> PortfolioStockOut:
    """
    Add a stock to a portfolio.

    1. Confirm the portfolio exists (404 if not).
    2. Look up the job in the JobStore; reject with 422 if not complete.
    3. Pre-check ticker uniqueness; reject with 409 if already present.
    4. Insert the stock row and write cached report data back immediately.
    """
    portfolio = _get_portfolio_or_404(db, portfolio_id)

    # ── Validate job is complete ───────────────────────────────────────────────
    job = store.get_job(body.job_id)
    if job is None or job.status != "complete":
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Report for job '{body.job_id}' is not complete. "
                "Wait for the analysis to finish before adding to a portfolio."
            ),
        )

    # ── Pre-check ticker uniqueness ───────────────────────────────────────────
    already_in = any(s.ticker == body.ticker for s in portfolio.stocks)
    if already_in:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=(
                f"Ticker '{body.ticker}' is already in portfolio '{portfolio_id}'. "
                "Remove it first if you want to refresh its data."
            ),
        )

    # ── Extract report data ───────────────────────────────────────────────────
    # job.result is stored by the orchestrator as a plain dict whose nested
    # values may still be Pydantic model instances (e.g. fundamental_result is
    # a FundamentalResult object, not a nested dict).  Normalise shallowly:
    # convert any Pydantic value inside the dict to its own plain dict so
    # every subsequent .get() call works correctly.
    result = job.result
    if isinstance(result, dict):
        from pydantic import BaseModel as _BaseModel
        report: dict = {
            k: v.model_dump() if isinstance(v, _BaseModel) else v
            for k, v in result.items()
        }
    else:
        report = result.model_dump()

    # Pull company name from the report payload for immediate display.
    company_name: str = (
        report.get("company_name")
        or report.get("fundamental_result", {}).get("company_name")
        or body.ticker
    )

    # ── Persist ───────────────────────────────────────────────────────────────
    stock = crud.add_stock(db, portfolio_id, body.ticker, company_name=company_name)
    crud.update_stock_from_report(db, portfolio_id, body.ticker, report)

    # Re-fetch to get the fully populated row after update_stock_from_report.
    db.refresh(stock)

    logger.info(
        "Stock added to portfolio",
        extra={"portfolio_id": portfolio_id, "ticker": body.ticker},
    )
    return PortfolioStockOut.model_validate(stock)


# ── DELETE /api/portfolios/{portfolio_id}/stocks/{ticker} ─────────────────────


@router.delete(
    "/portfolios/{portfolio_id}/stocks/{ticker}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Remove a stock from a portfolio",
    description=(
        "Remove a stock from a portfolio. "
        "Returns 204 on success, 404 when the portfolio or the ticker is not found."
    ),
)
def remove_stock(
    portfolio_id: str,
    ticker: str,
    db: Session = Depends(get_db),
) -> None:
    """Remove a single stock from a portfolio."""
    _get_portfolio_or_404(db, portfolio_id)

    removed = crud.remove_stock(db, portfolio_id, ticker.upper().strip())
    if not removed:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=(
                f"Ticker '{ticker}' not found in portfolio '{portfolio_id}'."
            ),
        )
    logger.info(
        "Stock removed from portfolio",
        extra={"portfolio_id": portfolio_id, "ticker": ticker},
    )


# ── GET /api/portfolios/{portfolio_id}/ranking ────────────────────────────────


@router.get(
    "/portfolios/{portfolio_id}/ranking",
    response_model=list[RankingEntryOut],
    summary="Get live portfolio ranking",
    description=(
        "Return the current stocks in a portfolio ranked by overall score "
        "(descending). Equal scores are broken alphabetically by ticker. "
        "Stocks with no score appear at the bottom."
    ),
)
def get_ranking(
    portfolio_id: str,
    db: Session = Depends(get_db),
) -> list[RankingEntryOut]:
    """Compute and return the live ranking for a portfolio."""
    from app.portfolio import ranking  # deferred import — ranking.py is Sub-Task P3

    portfolio = _get_portfolio_or_404(db, portfolio_id)
    entries: list[dict] = ranking.compute_ranking(portfolio.stocks)
    return [RankingEntryOut(**e) for e in entries]


# ── POST /api/portfolios/{portfolio_id}/refresh ───────────────────────────────


@router.post(
    "/portfolios/{portfolio_id}/refresh",
    status_code=http_status.HTTP_202_ACCEPTED,
    summary="Trigger a manual portfolio refresh",
    description=(
        "Re-run analysis for every stock in the portfolio in the background "
        "and write a new ranking snapshot when done. "
        "Returns 202 immediately; poll the history endpoint to see the new snapshot."
    ),
)
def refresh_portfolio(
    portfolio_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    store: JobStore = Depends(get_job_store),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> dict[str, str]:
    """Accept a manual refresh request and hand it off to a background task."""
    from app.portfolio.scheduler import run_portfolio_refresh  # Sub-Task P4

    _get_portfolio_or_404(db, portfolio_id)

    background_tasks.add_task(
        run_portfolio_refresh,
        portfolio_id,
        orchestrator,
        store,
        SessionLocal,
    )
    logger.info("Manual refresh queued", extra={"portfolio_id": portfolio_id})
    return {"detail": "Refresh started. Check history for the new snapshot when complete."}


# ── GET /api/portfolios/{portfolio_id}/history ────────────────────────────────


@router.get(
    "/portfolios/{portfolio_id}/history",
    response_model=list[RankingSnapshotOut],
    summary="List ranking snapshots",
    description=(
        "Return all ranking snapshots for a portfolio, newest first. "
        "Entries are omitted from this list view — use the detail endpoint "
        "to load a snapshot's full entry list."
    ),
)
def get_ranking_history(
    portfolio_id: str,
    db: Session = Depends(get_db),
) -> list[RankingSnapshotOut]:
    """Return the ranking snapshot history (without entries) for a portfolio."""
    _get_portfolio_or_404(db, portfolio_id)
    snapshots = crud.get_ranking_history(db, portfolio_id)
    # Return snapshots with an empty entries list for the lightweight list view.
    return [
        RankingSnapshotOut(
            id=s.id,
            snapshot_at=s.snapshot_at,
            trigger=s.trigger,
            entries=[],
        )
        for s in snapshots
    ]


# ── GET /api/portfolios/{portfolio_id}/history/{snapshot_id} ─────────────────


@router.get(
    "/portfolios/{portfolio_id}/history/{snapshot_id}",
    response_model=RankingSnapshotOut,
    summary="Get a full ranking snapshot",
    description=(
        "Return a single ranking snapshot with its full list of ranked entries. "
        "404 when the snapshot or portfolio is not found."
    ),
)
def get_snapshot(
    portfolio_id: str,
    snapshot_id: str,
    db: Session = Depends(get_db),
) -> RankingSnapshotOut:
    """Return one snapshot with all its RankingEntry rows loaded."""
    _get_portfolio_or_404(db, portfolio_id)

    snapshot = crud.get_snapshot(db, snapshot_id)
    if snapshot is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot '{snapshot_id}' not found.",
        )
    # Guard against cross-portfolio access (snapshot exists but belongs to another portfolio).
    if snapshot.portfolio_id != portfolio_id:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot '{snapshot_id}' not found in portfolio '{portfolio_id}'.",
        )
    return RankingSnapshotOut.model_validate(snapshot)

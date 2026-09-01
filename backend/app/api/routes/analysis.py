"""
Analysis route handlers — Sub-Task 5.

Endpoints
─────────
    GET  /api/validate/{ticker}  — lightweight ticker validation (format + yfinance lookup)
    POST /api/analyse            — create a job and launch the orchestrator as a background task

Ticker format
─────────────
    Accepted pattern (applied after .upper().strip()):
        ^[A-Z0-9]{1,5}([.\\-][A-Z]{1,2})?$

    This covers standard US tickers (AAPL, MSFT) and common multi-class formats
    (BRK.B, BF.B).  Anything that does not match raises HTTP 422.

Design notes
────────────
- ``POST /api/analyse`` returns immediately with ``{job_id, status: "pending"}``;
  the heavy pipeline runs inside FastAPI's BackgroundTasks mechanism.
- ``GET /api/validate/{ticker}`` always returns HTTP 200 — the ``valid`` flag tells
  the frontend whether to proceed; 4xx is only raised for a malformed ticker string.
- Both handlers share the same ``_validate_ticker_format()`` helper so the regex
  lives in exactly one place.
"""

from __future__ import annotations

import re
import uuid

import yfinance as yf
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi import status as http_status

from app.api.dependencies import get_job_store, get_orchestrator
from app.core.job_store import JobStore
from app.core.orchestrator import Orchestrator
from app.logger import get_logger
from app.schemas.analysis import AnalyseRequest, AnalyseResponse, ValidateResponse

logger = get_logger(__name__)

router = APIRouter()

# Ticker regex — see module docstring for rationale.
# Compiled once at module load for performance.
_TICKER_RE = re.compile(r"^[A-Z0-9]{1,5}([.\-][A-Z]{1,2})?$")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _validate_ticker_format(raw: str) -> str:
    """
    Normalise *raw* to upper-case, strip whitespace, and validate the format.

    Returns the normalised ticker string on success.
    Raises ``HTTPException(422)`` when the format does not match.
    """
    ticker = raw.upper().strip()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid ticker format: '{raw}'. "
                "Ticker must be 1–5 alphanumeric characters with an optional "
                "single-letter or two-letter suffix separated by '.' or '-' "
                "(e.g. AAPL, BRK.B, BF-B)."
            ),
        )
    return ticker


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get(
    "/validate/{ticker}",
    response_model=ValidateResponse,
    summary="Validate a ticker symbol",
    description=(
        "Check whether *ticker* is a real, tradeable instrument. "
        "Always returns HTTP 200 — inspect the ``valid`` field to decide how to proceed. "
        "HTTP 422 is raised only when the ticker string fails the format check."
    ),
)
async def validate_ticker(ticker: str) -> ValidateResponse:
    """
    Validate *ticker* in two steps:

    1. Format check — regex ``^[A-Z0-9]{1,5}([.\\-][A-Z]{1,2})?$`` (raises 422 on failure).
    2. Existence check — calls ``yfinance.Ticker(ticker).info``; if the returned dict
       has no ``symbol`` or ``shortName`` key the ticker is considered unknown.

    Returns a ``ValidateResponse`` with ``valid=True`` and the company name, or
    ``valid=False`` and a human-readable ``reason``.
    """
    normalised = _validate_ticker_format(ticker)

    try:
        info: dict = yf.Ticker(normalised).info  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 — yfinance raises various undocumented errors
        logger.warning(
            "yfinance lookup failed",
            extra={"ticker": normalised, "error": str(exc)},
        )
        return ValidateResponse(valid=False, reason="Symbol not found")

    # yfinance returns a non-empty dict with a "symbol" or "shortName" key for
    # valid tickers.  An unknown ticker yields an almost-empty dict (no "symbol").
    name: str | None = info.get("shortName") or info.get("longName")
    if not info.get("symbol") and not name:
        return ValidateResponse(valid=False, reason="Symbol not found")

    return ValidateResponse(valid=True, name=name)


@router.post(
    "/analyse",
    response_model=AnalyseResponse,
    status_code=http_status.HTTP_202_ACCEPTED,
    summary="Start a stock analysis job",
    description=(
        "Validate the ticker, create a job, fire the analysis pipeline as a "
        "background task, and return the ``job_id`` immediately. "
        "Poll ``GET /api/report/{job_id}`` to track progress."
    ),
)
async def analyse(
    body: AnalyseRequest,
    background_tasks: BackgroundTasks,
    store: JobStore = Depends(get_job_store),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> AnalyseResponse:
    """
    Create an analysis job for the given ticker.

    1. Normalise and validate the ticker format (422 on failure).
    2. Generate a UUID ``job_id`` and register the job in the ``JobStore`` as ``"pending"``.
    3. Add ``orchestrator.run(ticker, job_id)`` to ``BackgroundTasks`` so it
       starts after the response is sent.
    4. Return ``{job_id, status: "pending"}`` with HTTP 202.
    """
    ticker = _validate_ticker_format(body.ticker)
    job_id = str(uuid.uuid4())

    store.create_job(job_id)
    logger.info(
        "Analysis job created",
        extra={"ticker": ticker, "job_id": job_id},
    )

    background_tasks.add_task(orchestrator.run, ticker, job_id)

    return AnalyseResponse(job_id=job_id, status="pending")

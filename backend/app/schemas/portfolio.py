"""
API-layer Pydantic schemas for the Portfolio module (Sub-Task P2).

Seven models are defined here:

    PortfolioCreate      — request body for POST /api/portfolios
    PortfolioUpdate      — request body for PATCH /api/portfolios/{id}
    PortfolioStockIn     — request body for POST /api/portfolios/{id}/stocks
    PortfolioStockOut    — a single stock as returned inside PortfolioOut
    PortfolioOut         — full portfolio response (id, name, stocks list …)
    RankingEntryOut      — one ranked stock row in a snapshot or live ranking
    RankingSnapshotOut   — a complete ranking snapshot with its entries list

Design notes
────────────
- Input models (Create, Update, StockIn) are NOT frozen — Pydantic validators
  mutate the ticker field to upper-case before the handler sees it.
- Output models (…Out) are NOT frozen either; SQLAlchemy ORM objects are fed
  through ``model_validate`` which requires mutable construction.
- ``model_config = ConfigDict(from_attributes=True)`` is set on every output
  model so they can be constructed directly from SQLAlchemy ORM instances via
  ``MyModel.model_validate(orm_obj)`` without manual field mapping.
- The ticker regex ``^[A-Z0-9]{1,5}([.\\-][A-Z]{1,2})?$`` mirrors the pattern
  in ``app/api/routes/analysis.py`` — both must stay in sync.
- ``PortfolioStockIn.ticker`` is upper-cased and stripped in a field validator
  so the route handler never receives a lower-case ticker.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Ticker regex — mirrors _TICKER_RE in app/api/routes/analysis.py.
# Applied by PortfolioStockIn to normalise and validate the ticker field.
_TICKER_RE = re.compile(r"^[A-Z0-9]{1,5}([.\-][A-Z]{1,2})?$")


# ── Input schemas ─────────────────────────────────────────────────────────────


class PortfolioCreate(BaseModel):
    """
    Request body for ``POST /api/portfolios``.

    Both fields are validated by Pydantic before the route handler runs.
    ``name`` must be non-empty and at most 120 characters.
    ``description`` is optional and defaults to an empty string.
    """

    name: str = Field(..., min_length=1, max_length=120)
    """
    Human-readable portfolio name.

    Required; must be between 1 and 120 characters inclusive.
    """

    description: str = ""
    """
    Optional free-text description of the portfolio's purpose or strategy.

    Defaults to empty string when omitted from the request body.
    """


class PortfolioUpdate(BaseModel):
    """
    Request body for ``PATCH /api/portfolios/{id}``.

    All fields are optional — only those present in the JSON body are applied.
    Sending ``{}`` is a valid no-op.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=120)
    """
    New portfolio name.

    ``None`` (field absent) means "do not change the existing name".
    When present, must satisfy the same 1–120 character constraint as
    ``PortfolioCreate.name``.
    """

    description: Optional[str] = None
    """
    New portfolio description.

    ``None`` (field absent) means "do not change the existing description".
    An explicit empty string (``""``) clears the description.
    """


class PortfolioStockIn(BaseModel):
    """
    Request body for ``POST /api/portfolios/{id}/stocks``.

    Adds a stock to a portfolio using data from a previously completed
    analysis report identified by ``job_id``.
    """

    ticker: str
    """
    Upper-case ticker symbol to add (e.g. ``"AAPL"``).

    Automatically upper-cased and stripped by the field validator.
    Must match ``^[A-Z0-9]{1,5}([.\\-][A-Z]{1,2})?$`` after normalisation;
    raises HTTP 422 when the format is invalid.
    """

    job_id: str
    """
    UUID string of a completed analysis report in the job store.

    The route handler looks up this job via ``get_job_store()``; if the job
    does not exist or has not reached ``status="complete"`` the request is
    rejected with HTTP 422.
    """

    @field_validator("ticker", mode="before")
    @classmethod
    def normalise_ticker(cls, v: str) -> str:
        """
        Upper-case and strip the ticker, then validate its format.

        Raises ``ValueError`` (surfaced as HTTP 422 by FastAPI) when the
        normalised ticker does not match the accepted pattern.
        """
        normalised = str(v).upper().strip()
        if not _TICKER_RE.match(normalised):
            raise ValueError(
                f"Invalid ticker format: '{v}'. "
                "Ticker must be 1–5 alphanumeric characters with an optional "
                "single-letter or two-letter suffix separated by '.' or '-' "
                "(e.g. AAPL, BRK.B, BF-B)."
            )
        return normalised


# ── Output schemas ────────────────────────────────────────────────────────────


class PortfolioStockOut(BaseModel):
    """
    A single stock entry as returned inside ``PortfolioOut.stocks`` and the
    portfolio ranking table.

    All optional fields are ``None`` until the first report is linked to the
    stock via ``crud.update_stock_from_report()``.
    """

    model_config = ConfigDict(from_attributes=True)

    ticker: str
    """Upper-case ticker symbol (e.g. ``"MSFT"``)."""

    company_name: str
    """Full company name (e.g. ``"Microsoft Corporation"``)."""

    short_summary: str
    """
    Executive summary from the most recent completed report.

    Empty string until the first report is linked.
    """

    overall_score: Optional[float]
    """
    Composite overall score (0–100) from the most recent report.

    ``None`` when data could not be fetched or no report has been linked yet.
    """

    recommendation: Optional[str]
    """
    Investment recommendation from the most recent report.

    One of ``"Buy"``, ``"Hold"``, or ``"Sell"``; ``None`` until first report.
    """

    latest_report_id: Optional[str]
    """
    Job ID of the most recently linked analysis report.

    Points into the in-memory ``JobStore``; becomes stale after a server
    restart.  ``None`` until the first report is linked.
    """

    added_at: datetime
    """UTC datetime when this stock was added to the portfolio."""

    last_refreshed: Optional[datetime]
    """
    UTC datetime of the most recent successful score update.

    ``None`` until ``crud.update_stock_from_report()`` runs for this stock.
    """


class PortfolioOut(BaseModel):
    """
    Full portfolio response returned by ``GET /api/portfolios/{id}`` and
    ``POST /api/portfolios``.

    Includes the portfolio metadata and the complete list of its stocks.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    """UUID string that uniquely identifies this portfolio."""

    name: str
    """Human-readable portfolio name."""

    description: str
    """Free-text description; empty string when none was provided."""

    created_at: datetime
    """UTC datetime when the portfolio was created."""

    updated_at: datetime
    """UTC datetime of the most recent update to the portfolio row."""

    stocks: list[PortfolioStockOut]
    """
    All stocks currently in this portfolio.

    Empty list when no stocks have been added yet.  Ordered by
    ``added_at`` ascending (insertion order) for the detail view; the route
    handler for ``GET /api/portfolios/{id}/ranking`` sorts this list by score
    instead.
    """


class RankingEntryOut(BaseModel):
    """
    One ranked stock row returned by ``GET /api/portfolios/{id}/ranking`` and
    embedded in ``RankingSnapshotOut.entries``.

    Sub-scores are ``None`` when the corresponding analyser could not produce
    a result for that refresh cycle.
    """

    model_config = ConfigDict(from_attributes=True)

    rank: int
    """
    1-based position in the ranking (rank 1 = highest ``overall_score``).

    Equal scores are broken alphabetically by ``ticker`` (ascending).
    Stocks with ``overall_score = null`` are placed at the bottom.
    """

    ticker: str
    """Upper-case ticker symbol."""

    overall_score: Optional[float]
    """
    Composite overall score (0–100).

    ``None`` signals "⚠ Data unavailable" in the frontend ranking table.
    """

    fundamental_score: Optional[float]
    """Fundamental analysis sub-score (0–100), or ``None`` if unavailable."""

    technical_score: Optional[float]
    """Technical analysis sub-score (0–100), or ``None`` if unavailable."""

    sentiment_score: Optional[float]
    """News sentiment sub-score (0–100), or ``None`` if unavailable."""

    recommendation: Optional[str]
    """
    Investment recommendation at the time of this ranking.

    One of ``"Buy"``, ``"Hold"``, ``"Sell"``; ``None`` when ``overall_score``
    is ``None``.
    """


class RankingSnapshotOut(BaseModel):
    """
    A complete ranking snapshot returned by
    ``GET /api/portfolios/{id}/history/{snapshot_id}``.

    The list view (``GET /api/portfolios/{id}/history``) uses the same model
    but the route handler omits ``entries`` by returning snapshots without
    fetching their children — callers lazy-load entries only when a row is
    expanded.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    """UUID string that uniquely identifies this snapshot."""

    snapshot_at: datetime
    """UTC datetime when this snapshot was written."""

    trigger: str
    """
    What caused this snapshot to be written.

    One of ``"manual"`` (user clicked "Refresh Now") or
    ``"quarterly"`` (APScheduler fired automatically).
    """

    entries: list[RankingEntryOut]
    """
    Ranked stock entries for this snapshot, ordered ascending by ``rank``.

    Empty list when the portfolio had no stocks at snapshot time.
    """

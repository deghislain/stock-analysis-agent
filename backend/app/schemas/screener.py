"""
Pydantic models for the stock screener endpoint.

Request:
    ScreenerRequest  — min_price, max_price, industry

Response:
    ScreenerCriterion — one row of the undervalued-growth criteria legend
    ScreenerStock     — one result row (passes all criteria)
    ScreenerResponse  — list of results + applied criteria legend + metadata
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ScreenerRequest(BaseModel):
    """Body for POST /api/screener/search."""

    min_price: float = Field(..., ge=0, description="Minimum stock price (USD).")
    max_price: float = Field(..., ge=0, description="Maximum stock price (USD).")
    industry: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Industry name, e.g. 'Technology', 'Healthcare'.",
    )

    @model_validator(mode="after")
    def _check_price_range(self) -> "ScreenerRequest":
        if self.max_price <= self.min_price:
            raise ValueError("max_price must be greater than min_price.")
        return self


class ScreenerCriterion(BaseModel):
    """One row of the undervalued-growth criteria legend shown to the user."""

    label: str
    """Metric name, e.g. 'Trailing P/E'."""
    threshold: str
    """Threshold expression, e.g. '< 25'."""
    rationale: str
    """One-sentence plain-language explanation."""


class ScreenerStock(BaseModel):
    """A single stock returned by the screener — guaranteed to pass all criteria."""

    ticker: str
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    current_price: Optional[float] = None
    market_cap: Optional[float] = None
    # ── Valuation metrics (the "undervalued" signals) ─────────────────────────
    pe_ratio: Optional[float] = None
    """Trailing P/E ratio (< 25 to pass)."""
    forward_pe: Optional[float] = None
    """Forward P/E ratio (< 15 to pass)."""
    peg_ratio: Optional[float] = None
    """PEG ratio — P/E divided by EPS growth % (< 1 to pass). Results sorted by this."""
    pb_ratio: Optional[float] = None
    """Price-to-Book ratio (< 1 to pass)."""
    # ── Growth metrics (the "growth" signals) ─────────────────────────────────
    revenue_growth: Optional[float] = None
    """Year-over-year revenue growth as a decimal (> 0 to pass), e.g. 0.12 = 12 %."""
    eps_growth: Optional[float] = None
    """Year-over-year earnings / EPS growth as a decimal (> 0 to pass)."""
    # ── Additional context ────────────────────────────────────────────────────
    profit_margin: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None


class ScreenerResponse(BaseModel):
    """Response body for POST /api/screener/search."""

    results: list[ScreenerStock]
    total: int
    industry: str
    min_price: float
    max_price: float
    # ── Criteria legend — always present so the UI can explain the results ────
    criteria: list[ScreenerCriterion] = Field(default_factory=list)
    """The undervalued-growth criteria that every result has passed."""
    warnings: list[str] = Field(default_factory=list)

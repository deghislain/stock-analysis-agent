"""
API routes for the stock screener.

Endpoints
─────────
GET  /api/screener/industries
    Returns a sorted list of industry / sector names for the frontend dropdown.
    Lightweight — uses the in-memory universe cache.

POST /api/screener/search
    Body: { min_price, max_price, industry }
    Returns undervalued growth stocks that pass Yahoo Finance's preset criteria
    (P/E < 25, Fwd P/E < 15, PEG < 1, P/B < 1, revenue growth > 0,
    earnings growth > 0), filtered by the user's industry and price range.
    May take 5–30 s depending on the number of industry candidates.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.screener import ScreenerCriterion, ScreenerRequest, ScreenerResponse
from app.screener.stock_screener import CRITERIA_DESCRIPTIONS, list_industries, search_stocks

router = APIRouter()


@router.get(
    "/screener/industries",
    summary="List available industries",
    response_model=list[str],
)
async def get_industries() -> list[str]:
    """
    Return a sorted list of all industry and sector names available in the
    stock universe.  The list is pre-computed from the cached universe and
    requires no external network call once the cache is warm.
    """
    return list_industries()


@router.post(
    "/screener/search",
    summary="Search stocks by industry and price range",
    response_model=ScreenerResponse,
)
async def screener_search(body: ScreenerRequest) -> ScreenerResponse:
    """
    Search for **undervalued growth stocks** in a given industry whose current
    price falls between ``min_price`` and ``max_price`` (USD).

    Results are fetched directly from Yahoo Finance's predefined
    ``undervalued_growth_stocks`` screener preset — the same endpoint that
    powers the Yahoo Finance Research Hub page — then filtered client-side by
    price and industry.  This guarantees the result set matches Yahoo Finance's
    website exactly (including edge cases that a custom EquityQuery would miss).

    Results are sorted by PEG ratio ascending (best value-growth ratio first).
    Live data is fetched from Yahoo Finance (no API key required).
    """
    results, warnings = search_stocks(
        industry=body.industry,
        min_price=body.min_price,
        max_price=body.max_price,
    )
    criteria = [ScreenerCriterion(**c) for c in CRITERIA_DESCRIPTIONS]
    return ScreenerResponse(
        results=results,
        total=len(results),
        industry=body.industry,
        min_price=body.min_price,
        max_price=body.max_price,
        criteria=criteria,
        warnings=warnings,
    )

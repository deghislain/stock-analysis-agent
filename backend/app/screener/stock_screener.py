"""
Stock screener — Undervalued Growth Stocks via Yahoo Finance screener API.

How it works
────────────
This module calls ``yf.screen('undervalued_growth_stocks', count=250)`` —
the **predefined Yahoo Finance endpoint** that powers
https://finance.yahoo.com/research-hub/screener/undervalued_growth_stocks/

This is the only approach guaranteed to return exactly the same stocks as
the Yahoo Finance website.  Using a custom ``EquityQuery`` with the same
criteria produces a subtly different result set (e.g. AMPY appears on
Yahoo Finance's page but is excluded by the EquityQuery replica) because
Yahoo's predefined endpoint applies its criteria server-side in a way that
the programmatic ``POST /v1/finance/screener`` endpoint does not exactly
replicate.

Pipeline
────────
1. Fetch up to 250 results from the predefined ``undervalued_growth_stocks``
   preset.  All 249 (current total) are retrieved in a single request.
2. For every quote that falls within the requested price range, concurrently
   fetch ``yf.Ticker(symbol).get_info()`` to obtain sector, industry, PEG
   ratio, revenue growth, and earnings growth (absent from the screener quote).
3. Apply the user's industry / sector filter client-side against the enriched
   data (case-insensitive substring match — tolerates partial input).
4. Return matching stocks sorted by PEG ratio ascending (best value first).

Industry / sector list
──────────────────────
``list_industries()`` returns a static catalogue of Yahoo Finance sector and
industry names.  No network call required.
"""

from __future__ import annotations

import concurrent.futures
from typing import Optional

import yfinance as yf

from app.schemas.screener import ScreenerStock
from app.logger import get_logger

logger = get_logger(__name__)

# Yahoo Finance predefined preset name
_PRESET: str = "undervalued_growth_stocks"

# Fetch the full result set in one call (Yahoo Finance max is 250)
_FETCH_COUNT: int = 250

# Thread-pool size for per-ticker enrichment
_ENRICH_WORKERS: int = 10

# Human-readable descriptions sent to the frontend for the criteria legend.
CRITERIA_DESCRIPTIONS: list[dict] = [
    {
        "label":     "Trailing P/E",
        "threshold": "0 – 20",
        "rationale": "Reasonably priced relative to past 12-month earnings",
    },
    {
        "label":     "5-Year PEG Ratio",
        "threshold": "< 1",
        "rationale": "Growth At a Reasonable Price — P/E divided by 5-year EPS growth %",
    },
    {
        "label":     "EPS Growth (LTM)",
        "threshold": "≥ 25%",
        "rationale": "Strong recent earnings-per-share expansion",
    },
    {
        "label":     "Exchange",
        "threshold": "NASDAQ / NYSE",
        "rationale": "Listed on major US exchanges for liquidity",
    },
]

# ── Static industry / sector catalogue ────────────────────────────────────────
# These are the exact strings Yahoo Finance's screener API accepts for the
# ``sector`` and ``industry`` ``eq`` operator.  Grouped by sector for readability.

_SECTORS: list[str] = [
    "Basic Materials",
    "Communication Services",
    "Consumer Cyclical",
    "Consumer Defensive",
    "Energy",
    "Financial Services",
    "Healthcare",
    "Industrials",
    "Real Estate",
    "Technology",
    "Utilities",
]

_INDUSTRIES: list[str] = [
    # Basic Materials
    "Agricultural Inputs",
    "Aluminum",
    "Building Materials",
    "Chemicals",
    "Coking Coal",
    "Copper",
    "Gold",
    "Lumber & Wood Production",
    "Other Industrial Metals & Mining",
    "Other Precious Metals & Mining",
    "Paper & Paper Products",
    "Silver",
    "Specialty Chemicals",
    "Steel",
    # Communication Services
    "Advertising Agencies",
    "Broadcasting",
    "Electronic Gaming & Multimedia",
    "Entertainment",
    "Internet Content & Information",
    "Publishing",
    "Telecom Services",
    # Consumer Cyclical
    "Apparel Manufacturing",
    "Apparel Retail",
    "Auto & Truck Dealerships",
    "Auto Manufacturers",
    "Auto Parts",
    "Department Stores",
    "Discount Stores",
    "Footwear & Accessories",
    "Furnishings, Fixtures & Appliances",
    "Home Improvement Retail",
    "Internet Retail",
    "Leisure",
    "Lodging",
    "Luxury Goods",
    "Personal Services",
    "Recreational Vehicles",
    "Residential Construction",
    "Resorts & Casinos",
    "Restaurants",
    "Specialty Retail",
    "Travel Services",
    # Consumer Defensive
    "Beverages—Brewers",
    "Beverages—Non-Alcoholic",
    "Beverages—Wineries & Distilleries",
    "Confectioners",
    "Discount Stores",
    "Education & Training Services",
    "Farm Products",
    "Food Distribution",
    "Grocery Stores",
    "Household & Personal Products",
    "Packaged Foods",
    "Tobacco",
    # Energy
    "Oil & Gas Drilling",
    "Oil & Gas E&P",
    "Oil & Gas Equipment & Services",
    "Oil & Gas Integrated",
    "Oil & Gas Midstream",
    "Oil & Gas Refining & Marketing",
    "Thermal Coal",
    "Uranium",
    # Financial Services
    "Asset Management",
    "Banks—Diversified",
    "Banks—Regional",
    "Capital Markets",
    "Credit Services",
    "Financial Conglomerates",
    "Financial Data & Stock Exchanges",
    "Insurance Brokers",
    "Insurance—Diversified",
    "Insurance—Life",
    "Insurance—Property & Casualty",
    "Insurance—Reinsurance",
    "Insurance—Specialty",
    "Mortgage Finance",
    "Shell Companies",
    # Healthcare
    "Biotechnology",
    "Diagnostics & Research",
    "Drug Manufacturers—General",
    "Drug Manufacturers—Specialty & Generic",
    "Health Information Services",
    "Healthcare Plans",
    "Hospitals",
    "Medical Care Facilities",
    "Medical Devices",
    "Medical Distribution",
    "Medical Instruments & Supplies",
    "Pharmaceutical Retailers",
    # Industrials
    "Aerospace & Defense",
    "Agricultural & Farm Machinery",
    "Airlines",
    "Airports & Air Services",
    "Building Products & Equipment",
    "Business Equipment & Supplies",
    "Conglomerates",
    "Consulting Services",
    "Electrical Equipment & Parts",
    "Engineering & Construction",
    "Farm & Heavy Construction Machinery",
    "Industrial Distribution",
    "Infrastructure Operations",
    "Integrated Freight & Logistics",
    "Marine Shipping",
    "Metal Fabrication",
    "Pollution & Treatment Controls",
    "Railroads",
    "Rental & Leasing Services",
    "Security & Protection Services",
    "Specialty Business Services",
    "Specialty Industrial Machinery",
    "Staffing & Employment Services",
    "Tools & Accessories",
    "Trucking",
    "Waste Management",
    # Real Estate
    "REIT—Diversified",
    "REIT—Healthcare Facilities",
    "REIT—Hotel & Motel",
    "REIT—Industrial",
    "REIT—Mortgage",
    "REIT—Office",
    "REIT—Residential",
    "REIT—Retail",
    "REIT—Specialty",
    "Real Estate Services",
    # Technology
    "Communication Equipment",
    "Computer Hardware",
    "Consumer Electronics",
    "Electronic Components",
    "Electronics & Computer Distribution",
    "Information Technology Services",
    "Scientific & Technical Instruments",
    "Semiconductor Equipment & Materials",
    "Semiconductors",
    "Software—Application",
    "Software—Infrastructure",
    "Solar",
    # Utilities
    "Utilities—Diversified",
    "Utilities—Independent Power Producers",
    "Utilities—Regulated Electric",
    "Utilities—Regulated Gas",
    "Utilities—Regulated Water",
    "Utilities—Renewable",
]


def list_industries() -> list[str]:
    """
    Return a sorted list of all sector and industry names accepted by the
    Yahoo Finance screener API.  Used to populate the frontend autocomplete.
    No network call required.
    """
    return sorted(set(_SECTORS + _INDUSTRIES))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _industry_matches(candidate: str | None, query: str) -> bool:
    """Case-insensitive substring match — tolerates partial input."""
    if not candidate:
        return False
    return query.lower() in candidate.lower()


def _enrich_quote(quote: dict) -> dict:
    """
    Fetch ``yf.Ticker(symbol).get_info()`` and merge sector, industry, PEG
    ratio, revenue growth, earnings growth, and profit margin into the quote.
    Returns the mutated quote dict (or the original on any failure).
    """
    symbol = quote.get("symbol", "")
    try:
        info = yf.Ticker(symbol).get_info() or {}
        for key in (
            "sector", "industry",
            "pegRatio", "trailingPegRatio",
            "revenueGrowth",
            "earningsGrowth", "earningsQuarterlyGrowth",
            "profitMargins",
        ):
            if quote.get(key) is None:
                val = info.get(key)
                if val is not None:
                    quote[key] = val
    except Exception as exc:  # noqa: BLE001
        logger.debug("Enrichment failed", extra={"symbol": symbol, "error": str(exc)})
    return quote


# ── Public API ─────────────────────────────────────────────────────────────────

def search_stocks(
    industry: str,
    min_price: float,
    max_price: float,
) -> tuple[list[ScreenerStock], list[str]]:
    """
    Return undervalued growth stocks matching ``industry`` and price range.

    Uses the predefined Yahoo Finance ``undervalued_growth_stocks`` screener
    preset — identical to the website's results, including edge cases like AMPY
    that a custom EquityQuery may miss due to server-side evaluation differences.

    Pipeline
    ────────
    1. Fetch up to 250 results from the predefined preset (one HTTP request).
    2. Filter client-side to only quotes whose price is in [min_price, max_price].
    3. Concurrently enrich the price-filtered quotes with yf.Ticker().get_info()
       to obtain sector, industry, PEG, revenue growth, earnings growth.
    4. Apply industry/sector filter (case-insensitive substring) client-side.
    5. Return matches sorted by PEG ascending (best value-growth ratio first).
    """
    warnings_out: list[str] = []

    # ── Step 1: fetch predefined preset ───────────────────────────────────────
    logger.info(
        "Screener fetching preset",
        extra={"preset": _PRESET, "industry": industry,
               "min_price": min_price, "max_price": max_price},
    )
    try:
        response = yf.screen(_PRESET, count=_FETCH_COUNT)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Yahoo Finance screener call failed", extra={"error": str(exc)})
        warnings_out.append(
            f"Yahoo Finance screener is temporarily unavailable: {exc}. "
            "Please try again in a moment."
        )
        return [], warnings_out

    all_quotes: list[dict] = response.get("quotes", [])
    total_preset = response.get("total", 0)
    logger.info(
        "Screener preset fetched",
        extra={"total_preset": total_preset, "returned": len(all_quotes)},
    )

    # ── Step 2: price filter (no network) ─────────────────────────────────────
    price_filtered: list[dict] = []
    for q in all_quotes:
        price = _safe_float(q.get("regularMarketPrice"))
        if price is not None and min_price <= price <= max_price:
            price_filtered.append(q)

    logger.info(
        "Screener after price filter",
        extra={"price_filtered": len(price_filtered)},
    )

    if not price_filtered:
        warnings_out.append(
            f"No undervalued growth stocks found with a price between "
            f"${min_price:,.2f} and ${max_price:,.2f}. "
            "Try widening the price range."
        )
        return [], warnings_out

    # ── Step 3: concurrent enrichment ─────────────────────────────────────────
    # Enrich only the price-filtered subset to minimise network calls.
    with concurrent.futures.ThreadPoolExecutor(max_workers=_ENRICH_WORKERS) as pool:
        enriched: list[dict] = list(pool.map(_enrich_quote, price_filtered))

    # ── Step 4: industry / sector filter (client-side, substring) ────────────
    industry_filtered = [
        q for q in enriched
        if _industry_matches(q.get("sector"),   industry)
        or _industry_matches(q.get("industry"), industry)
    ]

    if not industry_filtered:
        warnings_out.append(
            f"No undervalued growth stocks matched '{industry}' in the "
            f"${min_price:,.2f}–${max_price:,.2f} price range. "
            "Try a broader term such as 'Technology', 'Energy', or 'Healthcare'."
        )
        return [], warnings_out

    # ── Step 5: map to ScreenerStock ──────────────────────────────────────────
    results: list[ScreenerStock] = []
    for q in industry_filtered:
        peg = _safe_float(q.get("pegRatio") or q.get("trailingPegRatio"))
        eps_growth = _safe_float(
            q.get("earningsGrowth") or q.get("earningsQuarterlyGrowth")
        )
        results.append(
            ScreenerStock(
                ticker=q.get("symbol", ""),
                name=q.get("longName") or q.get("shortName") or q.get("symbol", ""),
                sector=q.get("sector"),
                industry=q.get("industry"),
                current_price=_safe_float(q.get("regularMarketPrice")),
                market_cap=_safe_float(q.get("marketCap")),
                pe_ratio=_safe_float(q.get("trailingPE")),
                forward_pe=_safe_float(q.get("forwardPE")),
                peg_ratio=peg,
                pb_ratio=_safe_float(q.get("priceToBook")),
                revenue_growth=_safe_float(q.get("revenueGrowth")),
                eps_growth=eps_growth,
                profit_margin=_safe_float(q.get("profitMargins")),
                week_52_high=_safe_float(q.get("fiftyTwoWeekHigh")),
                week_52_low=_safe_float(q.get("fiftyTwoWeekLow")),
            )
        )

    # Sort by PEG ascending; stocks without a PEG go to the end.
    results.sort(
        key=lambda s: (s.peg_ratio is None, s.peg_ratio if s.peg_ratio is not None else 0),
    )

    logger.info(
        "Screener search complete",
        extra={
            "industry": industry,
            "min_price": min_price,
            "max_price": max_price,
            "total_preset": total_preset,
            "price_filtered": len(price_filtered),
            "results": len(results),
        },
    )
    return results, warnings_out

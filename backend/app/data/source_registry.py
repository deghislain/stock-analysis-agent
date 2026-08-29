"""
Source registry for the stock data fallback chain.

Priority order:
    1. Yahoo Finance  — price history + fundamentals (primary)
    2. Stooq          — price history only (fallback 1; used when Yahoo price fails)
    3. FMP            — fundamentals only  (fallback 2; used when Yahoo fundamentals empty)

``SourceRegistry.get_data_with_fallback(ticker)`` orchestrates the chain:
    - Tries Yahoo for price history; falls back to Stooq if Yahoo returns None.
    - Tries Yahoo for company_info / financials; falls back to FMP if both are empty.
    - Merges the best available data into a single ``StockData`` object.
    - Returns that object plus a ``sources_used`` list (feeds ``DataSourcesBadge``
      in the UI) and a ``warnings`` list (feeds ``WarningFlags`` in the UI).

The sentinel warning for fully-missing fundamentals (plan §Sub-Task 2, line 224):
    "Fundamental data is unavailable for this ticker. Fundamental analysis
     section will be incomplete."
is appended whenever neither Yahoo nor FMP can supply company_info or financials.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from app.data.base_source import AbstractDataSource, StockData
from app.data.fmp_source import FMPSource
from app.data.stooq_source import StooqSource
from app.data.yahoo_finance import YahooFinanceSource
from app.logger import get_logger

logger = get_logger(__name__)

# Exact warning string required by the plan — propagates to WarningFlags and PDF.
_NO_FUNDAMENTALS_WARNING = (
    "Fundamental data is unavailable for this ticker. "
    "Fundamental analysis section will be incomplete."
)

_NO_PRICE_WARNING = (
    "Price history is unavailable from all data sources. "
    "Technical analysis and charts will be incomplete."
)


@dataclass
class FallbackResult:
    """
    The fully-merged output of ``SourceRegistry.get_data_with_fallback``.

    Carries the combined ``StockData`` object together with metadata about
    which sources contributed data and any warnings to surface in the UI.
    """

    stock_data: StockData
    """Merged stock data drawn from the best available sources."""

    sources_used: list[str] = field(default_factory=list)
    """
    Names of every source that contributed at least one non-empty field.

    Flows to the frontend ``DataSourcesBadge`` component.
    """

    warnings: list[str] = field(default_factory=list)
    """
    Deduplicated list of all warnings gathered during the fallback process.

    Flows to the frontend ``WarningFlags`` component and the PDF report.
    """


class SourceRegistry:
    """
    Orchestrates the priority-ordered data source fallback chain.

    Instantiate once and reuse — the three source objects are stateless
    and safe to share across requests.
    """

    def __init__(self) -> None:
        """Initialise the registry with the three built-in data sources."""
        self._yahoo: AbstractDataSource = YahooFinanceSource()
        self._stooq: AbstractDataSource = StooqSource()
        self._fmp: AbstractDataSource   = FMPSource()

    def get_data_with_fallback(self, ticker: str) -> FallbackResult:
        """
        Fetch and merge the best available data for ``ticker``.

        Merge strategy
        ──────────────
        Price history  : Yahoo preferred → Stooq fallback → None + warning
        company_info   : Yahoo preferred → FMP fallback   → {} + warning
        financials     : Yahoo preferred → FMP fallback   → {} + warning

        When neither Yahoo nor FMP provide fundamentals, the sentinel
        ``_NO_FUNDAMENTALS_WARNING`` is appended so the UI can show the
        appropriate section-incomplete message.
        """
        ticker = ticker.upper().strip()
        all_warnings: list[str] = []
        sources_used: list[str] = []

        # ── Step 1: price history ─────────────────────────────────────────────
        price_history, price_source = self._resolve_price_history(
            ticker, all_warnings, sources_used
        )

        # ── Step 2: fundamentals (company_info + financials) ──────────────────
        company_info, financials, fund_source = self._resolve_fundamentals(
            ticker, all_warnings, sources_used
        )

        # ── Step 3: check if fundamentals are completely missing ──────────────
        if not company_info and not financials:
            all_warnings.append(_NO_FUNDAMENTALS_WARNING)
            logger.warning(
                "No fundamental data from any source",
                extra={"ticker": ticker},
            )

        # ── Step 4: check if price history is completely missing ──────────────
        if price_history is None:
            all_warnings.append(_NO_PRICE_WARNING)

        # ── Step 5: assemble merged StockData ─────────────────────────────────
        # source_name on the merged object reflects the primary source used.
        primary_source = price_source or fund_source or "Unknown"

        merged = StockData(
            source_name=primary_source,
            price_history=price_history,
            company_info=company_info,
            financials=financials,
            warnings=_deduplicate(all_warnings),
        )

        logger.info(
            "Fallback resolution complete",
            extra={
                "ticker": ticker,
                "sources_used": sources_used,
                "warnings": len(merged.warnings),
                "has_price": price_history is not None,
                "has_fundamentals": bool(company_info or financials),
            },
        )

        return FallbackResult(
            stock_data=merged,
            sources_used=sources_used,
            warnings=merged.warnings,
        )

    # ── Private resolution helpers ────────────────────────────────────────────

    def _resolve_price_history(
        self,
        ticker: str,
        all_warnings: list[str],
        sources_used: list[str],
    ) -> tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Try Yahoo Finance first, then Stooq, for OHLCV price history.

        Returns the first non-None DataFrame and the name of the source
        that provided it, or ``(None, None)`` if both fail.
        """
        # Primary: Yahoo Finance
        yahoo_result = self._yahoo.get_price_history(ticker)
        _collect_warnings(yahoo_result, all_warnings)

        if yahoo_result.price_history is not None:
            _register_source(self._yahoo.source_name, sources_used)
            logger.debug("Price history from Yahoo", extra={"ticker": ticker})
            return yahoo_result.price_history, self._yahoo.source_name

        # Fallback 1: Stooq
        logger.debug("Yahoo price failed; trying Stooq", extra={"ticker": ticker})
        stooq_result = self._stooq.get_price_history(ticker)
        _collect_warnings(stooq_result, all_warnings)

        if stooq_result.price_history is not None:
            _register_source(self._stooq.source_name, sources_used)
            logger.debug("Price history from Stooq", extra={"ticker": ticker})
            return stooq_result.price_history, self._stooq.source_name

        logger.warning("No price history from any source", extra={"ticker": ticker})
        return None, None

    def _resolve_fundamentals(
        self,
        ticker: str,
        all_warnings: list[str],
        sources_used: list[str],
    ) -> tuple[dict, dict, Optional[str]]:
        """
        Try Yahoo Finance first, then FMP, for company_info and financials.

        Returns ``(company_info, financials, source_name)`` using the best
        available combination:
        - Yahoo company_info + Yahoo financials (preferred)
        - Yahoo company_info + FMP financials   (mixed, when Yahoo financials empty)
        - FMP company_info  + FMP financials    (full FMP fallback)
        - Empty dicts + None source             (both failed)
        """
        # Primary: Yahoo Finance
        yahoo_result = self._yahoo.get_company_info(ticker)
        _collect_warnings(yahoo_result, all_warnings)

        company_info = yahoo_result.company_info
        financials   = yahoo_result.financials
        yahoo_contributed = bool(company_info or financials)

        if yahoo_contributed:
            _register_source(self._yahoo.source_name, sources_used)

        # If Yahoo provided something, check whether financials need supplementing.
        if company_info and financials:
            logger.debug("Fundamentals from Yahoo", extra={"ticker": ticker})
            return company_info, financials, self._yahoo.source_name

        # Fallback 2: FMP (used whenever Yahoo fundamentals are incomplete)
        logger.debug("Yahoo fundamentals incomplete; trying FMP", extra={"ticker": ticker})

        fmp_info   = self._fmp.get_company_info(ticker)
        fmp_ratios = self._fmp.get_financials(ticker)
        _collect_warnings(fmp_info, all_warnings)
        _collect_warnings(fmp_ratios, all_warnings)

        fmp_company_info = fmp_info.company_info
        fmp_financials   = fmp_ratios.financials
        fmp_contributed  = bool(fmp_company_info or fmp_financials)

        if fmp_contributed:
            _register_source(self._fmp.source_name, sources_used)

        # Merge: prefer any Yahoo data that exists, fill gaps with FMP.
        merged_company_info = fmp_company_info | company_info   # Yahoo wins on collision
        merged_financials   = fmp_financials   | financials     # Yahoo wins on collision

        if fmp_contributed:
            logger.debug("Fundamentals supplemented by FMP", extra={"ticker": ticker})

        # Report the primary fundamentals source for the DataSourcesBadge.
        if merged_company_info or merged_financials:
            fund_source = (
                self._yahoo.source_name if yahoo_contributed else self._fmp.source_name
            )
        else:
            fund_source = None

        return merged_company_info, merged_financials, fund_source


# ── Module-level singleton ────────────────────────────────────────────────────

# Shared instance — import and call ``registry.get_data_with_fallback(ticker)``
# from the agent layer.  Creating it once avoids repeated object construction
# on every request.
registry = SourceRegistry()


# ── Private helpers ───────────────────────────────────────────────────────────


def _collect_warnings(result: StockData, target: list[str]) -> None:
    """Append all warnings from ``result`` into ``target``."""
    target.extend(result.warnings)


def _register_source(name: str, sources_used: list[str]) -> None:
    """Add ``name`` to ``sources_used`` if not already present."""
    if name not in sources_used:
        sources_used.append(name)


def _deduplicate(warnings: list[str]) -> list[str]:
    """Return a new list with duplicate warning strings removed (order preserved)."""
    seen: set[str] = set()
    result: list[str] = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            result.append(w)
    return result

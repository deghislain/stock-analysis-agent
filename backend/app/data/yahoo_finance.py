"""
Yahoo Finance data source — primary source in the fallback chain.

Uses the ``yfinance`` library (no API key required) to fetch:
- OHLCV price history (``get_price_history``)
- Company metadata such as P/E, market cap, sector  (``get_company_info``)
- Financial statement data: revenue, net income, debt  (``get_financials``)

All methods catch every exception and return a ``StockData`` with a warning
rather than letting errors propagate to the caller.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import yfinance as yf

from app.data.base_source import AbstractDataSource, StockData
from app.logger import get_logger

logger = get_logger(__name__)

# Keys pulled from yfinance ``info`` dict into ``company_info``.
_COMPANY_INFO_KEYS: tuple[str, ...] = (
    "longName",
    "shortName",
    "sector",
    "industry",
    "marketCap",
    "currentPrice",
    "trailingPE",
    "forwardPE",
    "trailingEps",
    "priceToBook",
    "dividendYield",
    "debtToEquity",
    "profitMargins",
    "grossMargins",
    "operatingMargins",
    "returnOnEquity",
    "revenueGrowth",
    "longBusinessSummary",
    "website",
    "fullTimeEmployees",
    "country",
)

# Keys pulled from yfinance ``info`` dict into ``financials``.
_FINANCIALS_KEYS: tuple[str, ...] = (
    "totalRevenue",
    "netIncomeToCommon",
    "totalDebt",
    "totalStockholderEquity",
    "grossProfit",
    "operatingCashflow",
    "freeCashflow",
    "earningsGrowth",
    "revenuePerShare",
)

# How many years of daily price history to fetch.
_PRICE_HISTORY_PERIOD = "2y"


class YahooFinanceSource(AbstractDataSource):
    """Fetches stock data from Yahoo Finance using the yfinance library."""

    @property
    def source_name(self) -> str:
        """Return the display name for this data source."""
        return "Yahoo Finance"

    def get_price_history(self, ticker: str) -> StockData:
        """
        Fetch 2 years of daily OHLCV history for ``ticker`` from Yahoo Finance.

        Returns a ``StockData`` with ``price_history`` set to a DataFrame
        (columns: Open, High, Low, Close, Volume) or ``None`` on failure.
        """
        warnings: list[str] = []
        price_history: Optional[pd.DataFrame] = None

        try:
            yf_ticker = yf.Ticker(ticker)
            df: pd.DataFrame = yf_ticker.history(
                period=_PRICE_HISTORY_PERIOD,
                interval="1d",
                auto_adjust=True,
                actions=False,
            )

            if df.empty:
                warnings.append(
                    f"Yahoo Finance returned no price history for '{ticker}'. "
                    "The ticker may be invalid or delisted."
                )
            else:
                # Keep only the standard OHLCV columns; drop any extras
                # (e.g. Dividends, Stock Splits) that yfinance may include.
                keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
                price_history = df[keep].copy()
                price_history.index = pd.to_datetime(price_history.index)
                logger.debug(
                    "Fetched price history",
                    extra={"ticker": ticker, "rows": len(price_history)},
                )

        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"Yahoo Finance price history unavailable for '{ticker}': {exc}"
            )
            logger.warning(
                "Yahoo Finance price history fetch failed",
                extra={"ticker": ticker, "error": str(exc)},
            )

        return StockData(
            source_name=self.source_name,
            price_history=price_history,
            company_info={},
            financials={},
            warnings=warnings,
        )

    def get_company_info(self, ticker: str) -> StockData:
        """
        Fetch company metadata for ``ticker`` from Yahoo Finance.

        Populates ``company_info`` with valuation and profile fields
        and ``financials`` with income/balance-sheet summary fields,
        both sourced from the yfinance ``info`` dict.
        """
        warnings: list[str] = []
        company_info: dict = {}
        financials: dict = {}

        try:
            info: dict = yf.Ticker(ticker).get_info()

            # Extract company profile fields.
            company_info = {k: info.get(k) for k in _COMPANY_INFO_KEYS if info.get(k) is not None}

            # Extract financial summary fields.
            financials = {k: info.get(k) for k in _FINANCIALS_KEYS if info.get(k) is not None}

            if not company_info:
                warnings.append(
                    f"Yahoo Finance returned no company info for '{ticker}'."
                )
            if not financials:
                warnings.append(
                    f"Yahoo Finance returned no financial data for '{ticker}'."
                )

            logger.debug(
                "Fetched company info",
                extra={
                    "ticker": ticker,
                    "info_keys": len(company_info),
                    "financials_keys": len(financials),
                },
            )

        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"Yahoo Finance company info unavailable for '{ticker}': {exc}"
            )
            logger.warning(
                "Yahoo Finance company info fetch failed",
                extra={"ticker": ticker, "error": str(exc)},
            )

        return StockData(
            source_name=self.source_name,
            price_history=None,
            company_info=company_info,
            financials=financials,
            warnings=warnings,
        )

    def get_financials(self, ticker: str) -> StockData:
        """
        Alias for ``get_company_info`` — Yahoo Finance exposes financials
        through the same ``info`` dict, so both are fetched in one call.
        """
        return self.get_company_info(ticker)

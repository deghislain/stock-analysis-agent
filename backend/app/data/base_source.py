"""
Abstract base for all stock data sources in the fallback chain.

Every concrete source (Yahoo Finance, Stooq, FMP) must inherit from
``AbstractDataSource`` and implement its three methods.  The agent layer
always works with ``StockData`` objects so it never needs to know which
source was actually used.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class StockData:
    """
    Unified data container returned by every data source.

    This is the contract between the data layer and the analysis layer —
    field names must remain stable across all sub-tasks.
    """

    source_name: str
    """Human-readable name of the source that produced this object (e.g. ``"Yahoo Finance"``)."""

    price_history: Optional[pd.DataFrame]
    """
    OHLCV price history as a DataFrame with a DatetimeIndex.

    Expected columns: ``Open``, ``High``, ``Low``, ``Close``, ``Volume``.
    ``None`` when the source cannot provide price data.
    """

    company_info: dict
    """
    Key company metadata returned by the source.

    Common keys (when available): ``longName``, ``sector``, ``industry``,
    ``marketCap``, ``trailingPE``, ``forwardPE``, ``trailingEps``,
    ``priceToBook``, ``dividendYield``, ``longBusinessSummary``.
    Empty dict ``{}`` when the source does not provide this data.
    """

    financials: dict
    """
    Financial statement data returned by the source.

    Common keys (when available): ``totalRevenue``, ``netIncome``,
    ``totalDebt``, ``totalStockholderEquity``, ``grossProfit``,
    ``operatingIncome``.
    Empty dict ``{}`` when the source does not provide this data.
    """

    warnings: list[str] = field(default_factory=list)
    """
    List of human-readable warning messages about missing or incomplete data.

    These flow all the way to the frontend ``WarningFlags`` component and
    are included in the PDF report warnings section.
    """


class AbstractDataSource(ABC):
    """
    Abstract base class that every data source implementation must extend.

    Concrete subclasses must implement all three methods.  Each method
    must catch its own network/parsing errors and return a ``StockData``
    object with ``None``/empty fields plus an appropriate warning —
    it must never raise an exception to the caller.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the human-readable name for this data source."""

    @abstractmethod
    def get_price_history(self, ticker: str) -> StockData:
        """
        Fetch OHLCV price history for ``ticker`` and return a ``StockData``.

        The ``price_history`` field must be a DataFrame with columns
        ``Open``, ``High``, ``Low``, ``Close``, ``Volume`` and a
        DatetimeIndex.  Set ``price_history=None`` and append a warning
        if the data cannot be retrieved.
        """

    @abstractmethod
    def get_company_info(self, ticker: str) -> StockData:
        """
        Fetch company metadata for ``ticker`` and return a ``StockData``.

        Populate ``company_info`` with whatever the source provides.
        Set ``company_info={}`` and append a warning if unavailable.
        """

    @abstractmethod
    def get_financials(self, ticker: str) -> StockData:
        """
        Fetch financial statement data for ``ticker`` and return a ``StockData``.

        Populate ``financials`` with whatever the source provides.
        Set ``financials={}`` and append a warning if unavailable.
        """

"""
Stooq data source — fallback 1 in the fallback chain.

Fetches daily OHLCV price history from the Stooq public CSV endpoint:
    https://stooq.com/q/d/l/?s={ticker}.US&d1={start}&d2={end}&i=d

No API key is required.  Stooq provides price history **only** — it has no
fundamentals or company-profile endpoints.  ``company_info`` and
``financials`` are always returned as empty dicts with an explanatory warning.

Implementation note: ``pandas-datareader`` v0.10+ dropped the Stooq reader,
so this source calls the Stooq CSV endpoint directly via ``httpx``.  The
behaviour is identical — the endpoint returns the same CSV the old reader
used internally.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta
from typing import Optional

import httpx
import pandas as pd

from app.data.base_source import AbstractDataSource, StockData
from app.logger import get_logger

logger = get_logger(__name__)

# Stooq CSV download endpoint.
# Parameters:
#   s  — ticker symbol (upper-case, US equities need the .US suffix)
#   d1 — start date YYYYMMDD
#   d2 — end date YYYYMMDD
#   i  — interval: d = daily
_STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&d1={start}&d2={end}&i=d"

# How many years of history to request.
_HISTORY_YEARS = 2

# Warning added to every response from this source because it only provides price data.
_FUNDAMENTALS_WARNING = (
    "Stooq provides price history only. "
    "Fundamental data not available from this source."
)

# HTTP timeout in seconds.
_TIMEOUT = 15


class StooqSource(AbstractDataSource):
    """Fetches daily OHLCV price history from the Stooq public CSV endpoint."""

    @property
    def source_name(self) -> str:
        """Return the display name for this data source."""
        return "Stooq"

    def get_price_history(self, ticker: str) -> StockData:
        """
        Fetch 2 years of daily OHLCV history for ``ticker`` from Stooq.

        The ticker is normalised to upper-case and the ``.US`` suffix is
        appended when not already present (required by the Stooq URL scheme
        for US-listed equities).  Returns ``price_history=None`` with a
        warning on any network or parsing error.
        """
        warnings: list[str] = [_FUNDAMENTALS_WARNING]
        price_history: Optional[pd.DataFrame] = None

        symbol = _normalise_ticker(ticker)
        end_dt = datetime.today()
        start_dt = end_dt - timedelta(days=_HISTORY_YEARS * 365)
        url = _STOOQ_URL.format(
            symbol=symbol,
            start=start_dt.strftime("%Y%m%d"),
            end=end_dt.strftime("%Y%m%d"),
        )

        try:
            response = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True)
            response.raise_for_status()

            df = pd.read_csv(io.StringIO(response.text))

            # Stooq CSV columns: Date, Open, High, Low, Close, Volume
            if df.empty or "Date" not in df.columns:
                warnings.append(
                    f"Stooq returned no price data for '{ticker}'. "
                    "The symbol may not be listed on Stooq."
                )
            else:
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date").sort_index()

                # Keep only standard OHLCV columns; Stooq may not include Volume.
                keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
                price_history = df[keep].copy()

                logger.debug(
                    "Fetched Stooq price history",
                    extra={"ticker": ticker, "symbol": symbol, "rows": len(price_history)},
                )

        except httpx.HTTPStatusError as exc:
            warnings.append(
                f"Stooq returned HTTP {exc.response.status_code} for '{ticker}'. "
                "Price history unavailable from this source."
            )
            logger.warning(
                "Stooq HTTP error",
                extra={"ticker": ticker, "status": exc.response.status_code},
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"Stooq price history unavailable for '{ticker}': {exc}"
            )
            logger.warning(
                "Stooq fetch failed",
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
        Stooq does not provide company metadata.

        Returns an empty ``company_info`` and the standard fundamentals
        warning so the registry knows to try the next source.
        """
        return StockData(
            source_name=self.source_name,
            price_history=None,
            company_info={},
            financials={},
            warnings=[_FUNDAMENTALS_WARNING],
        )

    def get_financials(self, ticker: str) -> StockData:
        """
        Stooq does not provide financial statement data.

        Returns an empty ``financials`` and the standard fundamentals
        warning so the registry knows to try the next source.
        """
        return StockData(
            source_name=self.source_name,
            price_history=None,
            company_info={},
            financials={},
            warnings=[_FUNDAMENTALS_WARNING],
        )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _normalise_ticker(ticker: str) -> str:
    """
    Convert a plain US ticker to the format Stooq expects.

    Stooq requires upper-case symbols with a ``.US`` suffix for US-listed
    equities (e.g. ``AAPL`` → ``AAPL.US``).  If the caller already supplies
    a suffix (e.g. ``BRK.B``) the whole string is upper-cased but no extra
    suffix is appended — Stooq handles dot-class shares natively.
    """
    upper = ticker.upper().strip()
    # If there's already a dot (e.g. BRK.B, AAPL.US) leave it as-is.
    if "." in upper:
        return upper
    return f"{upper}.US"

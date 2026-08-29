"""
Financial Modeling Prep (FMP) data source — fallback 2 in the fallback chain.

Fetches company metadata and financial ratios from two FMP free-tier endpoints:

    Profile    https://financialmodelingprep.com/api/v3/profile/{ticker}
    Ratios TTM https://financialmodelingprep.com/api/v3/ratios-ttm/{ticker}

Fields returned by the profile endpoint (relevant subset):
    companyName, symbol, price, mktCap, sector, industry, description,
    website, country, fullTimeEmployees, ipoDate, beta, volAvg,
    lastDiv, range, changes

Fields returned by the ratios-ttm endpoint (relevant subset):
    peRatioTTM, pegRatioTTM, pbRatioTTM, priceToSalesRatioTTM,
    debtToEquityRatioTTM, netProfitMarginTTM, grossProfitMarginTTM,
    operatingProfitMarginTTM, returnOnEquityTTM, dividendYieldTTM,
    revenueGrowthTTM, epsGrowthTTM

IMPORTANT — API key policy change:
    FMP changed its policy and now requires an API key even for the free
    tier (previously these endpoints were keyless).  Registration is free,
    takes ~30 seconds, and requires no credit card.  Set FMP_API_KEY in
    your .env file to enable this source.
    https://financialmodelingprep.com/developer/docs

    When FMP_API_KEY is empty this source skips all network calls and
    returns empty dicts with an explanatory warning — the fallback chain
    continues to operate without it.

This source does NOT provide price history.  ``price_history`` is always
``None`` with an explanatory warning.
"""

from __future__ import annotations

from typing import Optional

import httpx

from app.config import settings
from app.data.base_source import AbstractDataSource, StockData
from app.logger import get_logger

logger = get_logger(__name__)

# FMP free-tier endpoint templates.
_PROFILE_URL = "https://financialmodelingprep.com/api/v3/profile/{ticker}"
_RATIOS_URL  = "https://financialmodelingprep.com/api/v3/ratios-ttm/{ticker}"

# HTTP timeout in seconds.
_TIMEOUT = 15

# Warning used whenever this source is asked for price history.
_NO_PRICE_WARNING = (
    "FMP does not provide price history. "
    "Price chart data not available from this source."
)

# Warning shown when FMP_API_KEY is not configured.
_NO_KEY_WARNING = (
    "FMP_API_KEY is not set. Financial Modeling Prep fundamentals fallback is disabled. "
    "Set FMP_API_KEY in your .env file (free registration at "
    "https://financialmodelingprep.com/developer/docs) to enable it."
)

# Profile fields to promote into company_info.
_PROFILE_COMPANY_KEYS = (
    "companyName",
    "sector",
    "industry",
    "mktCap",
    "price",
    "description",
    "website",
    "country",
    "fullTimeEmployees",
    "ipoDate",
    "beta",
)

# Ratios-TTM fields to promote into financials.
_RATIOS_FINANCIALS_KEYS = (
    "peRatioTTM",
    "pegRatioTTM",
    "pbRatioTTM",
    "priceToSalesRatioTTM",
    "debtToEquityRatioTTM",
    "netProfitMarginTTM",
    "grossProfitMarginTTM",
    "operatingProfitMarginTTM",
    "returnOnEquityTTM",
    "dividendYieldTTM",
    "revenueGrowthTTM",
    "epsGrowthTTM",
)


class FMPSource(AbstractDataSource):
    """Fetches company metadata and financial ratios from FMP free-tier endpoints."""

    @property
    def source_name(self) -> str:
        """Return the display name for this data source."""
        return "Financial Modeling Prep"

    def get_price_history(self, ticker: str) -> StockData:
        """
        FMP does not provide price history.

        Always returns ``price_history=None`` with an explanatory warning
        so the registry knows to use a different source for chart data.
        """
        return StockData(
            source_name=self.source_name,
            price_history=None,
            company_info={},
            financials={},
            warnings=[_NO_PRICE_WARNING],
        )

    def get_company_info(self, ticker: str) -> StockData:
        """
        Fetch company profile for ``ticker`` from the FMP profile endpoint.

        Returns ``company_info`` populated from the profile response.
        Returns empty dict with a warning when the API key is missing,
        the ticker is not found, or a network error occurs.
        """
        warnings: list[str] = []
        company_info: dict = {}

        if not settings.fmp_api_key:
            return StockData(
                source_name=self.source_name,
                price_history=None,
                company_info={},
                financials={},
                warnings=[_NO_KEY_WARNING],
            )

        try:
            url = _PROFILE_URL.format(ticker=ticker.upper())
            data = _get_json(url, settings.fmp_api_key)

            # Profile endpoint returns a list with one item.
            profile = data[0] if isinstance(data, list) and data else {}

            if not profile:
                warnings.append(
                    f"FMP returned no profile data for '{ticker}'. "
                    "The ticker may not be covered by FMP."
                )
            else:
                company_info = {
                    k: profile[k]
                    for k in _PROFILE_COMPANY_KEYS
                    if profile.get(k) is not None
                }
                logger.debug(
                    "Fetched FMP company info",
                    extra={"ticker": ticker, "keys": len(company_info)},
                )

        except _FMPAuthError:
            warnings.append(
                "FMP API key is invalid or expired. "
                "Check FMP_API_KEY in your .env file."
            )
            logger.warning("FMP auth error", extra={"ticker": ticker})
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"FMP company info unavailable for '{ticker}': {exc}"
            )
            logger.warning(
                "FMP company info fetch failed",
                extra={"ticker": ticker, "error": str(exc)},
            )

        return StockData(
            source_name=self.source_name,
            price_history=None,
            company_info=company_info,
            financials={},
            warnings=warnings,
        )

    def get_financials(self, ticker: str) -> StockData:
        """
        Fetch trailing-twelve-month financial ratios for ``ticker`` from FMP.

        Returns ``financials`` populated from the ratios-ttm response.
        Returns empty dict with a warning when the API key is missing,
        the ticker is not found, or a network error occurs.
        """
        warnings: list[str] = []
        financials: dict = {}

        if not settings.fmp_api_key:
            return StockData(
                source_name=self.source_name,
                price_history=None,
                company_info={},
                financials={},
                warnings=[_NO_KEY_WARNING],
            )

        try:
            url = _RATIOS_URL.format(ticker=ticker.upper())
            data = _get_json(url, settings.fmp_api_key)

            # Ratios-TTM endpoint returns a list with one item.
            ratios = data[0] if isinstance(data, list) and data else {}

            if not ratios:
                warnings.append(
                    f"FMP returned no ratios data for '{ticker}'. "
                    "The ticker may not be covered by FMP."
                )
            else:
                financials = {
                    k: ratios[k]
                    for k in _RATIOS_FINANCIALS_KEYS
                    if ratios.get(k) is not None
                }
                logger.debug(
                    "Fetched FMP financials",
                    extra={"ticker": ticker, "keys": len(financials)},
                )

        except _FMPAuthError:
            warnings.append(
                "FMP API key is invalid or expired. "
                "Check FMP_API_KEY in your .env file."
            )
            logger.warning("FMP auth error", extra={"ticker": ticker})
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"FMP financials unavailable for '{ticker}': {exc}"
            )
            logger.warning(
                "FMP financials fetch failed",
                extra={"ticker": ticker, "error": str(exc)},
            )

        return StockData(
            source_name=self.source_name,
            price_history=None,
            company_info={},
            financials=financials,
            warnings=warnings,
        )


# ── Internal helpers ──────────────────────────────────────────────────────────


class _FMPAuthError(Exception):
    """Raised internally when FMP returns a 401 (invalid/missing API key)."""


def _get_json(url: str, api_key: str) -> list | dict:
    """
    Perform a GET request to ``url`` with the FMP ``apikey`` query parameter
    and return the parsed JSON body.

    Raises ``_FMPAuthError`` on HTTP 401, ``httpx.HTTPStatusError`` on other
    4xx/5xx responses, and re-raises any other exception unchanged.
    """
    response = httpx.get(
        url,
        params={"apikey": api_key},
        timeout=_TIMEOUT,
        follow_redirects=True,
    )
    if response.status_code == 401:
        raise _FMPAuthError(response.text)
    response.raise_for_status()
    return response.json()

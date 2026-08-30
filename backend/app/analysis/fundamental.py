"""
Fundamental analysis module.

``FundamentalAnalyser.analyse(stock_data)`` reads ``company_info`` and
``financials`` from a ``StockData`` object and computes seven key metrics:

    P/E ratio, EPS, P/B ratio, Debt-to-Equity, Profit Margin,
    Revenue Growth, Dividend Yield

Each metric is returned as a ``FundamentalMetric`` with a beginner-friendly
label, raw value, unit, and one-sentence interpretation hint.

A composite ``score`` (0–100) is derived from whichever metrics are
available.  Missing metrics add a warning and are excluded from scoring
rather than failing the whole analysis.

Key mappings
────────────
Yahoo Finance keys live in ``company_info``:
    trailingPE, trailingEps, priceToBook, debtToEquity,
    profitMargins, revenueGrowth, dividendYield

Yahoo Finance keys live in ``financials``:
    (not used directly here — the ratios above are already normalised)

FMP keys live in ``company_info``:
    (none of the ratio keys — FMP profile has mktCap, price, etc.)

FMP keys live in ``financials`` (ratios-ttm):
    peRatioTTM, pbRatioTTM, debtToEquityRatioTTM,
    netProfitMarginTTM, revenueGrowthTTM, dividendYieldTTM
"""

from __future__ import annotations

from app.data.base_source import StockData
from app.logger import get_logger
from app.schemas.analysis import FundamentalMetric, FundamentalResult

logger = get_logger(__name__)


class FundamentalAnalyser:
    """Computes fundamental metrics from a ``StockData`` object."""

    def analyse(self, ticker: str, stock_data: StockData) -> FundamentalResult:
        """
        Compute all seven fundamental metrics for ``ticker`` using ``stock_data``.

        Metrics that cannot be computed because source data is missing are
        returned with ``value=None`` and a warning is appended.  The scorer
        only uses metrics that are available so partial data still produces
        a valid result.
        """
        info = stock_data.company_info or {}
        fins = stock_data.financials or {}
        warnings: list[str] = []

        # ── Compute each metric ───────────────────────────────────────────────

        pe_ratio     = _pe_ratio(info, fins, warnings)
        eps          = _eps(info, warnings)
        pb_ratio     = _pb_ratio(info, fins, warnings)
        debt_to_eq   = _debt_to_equity(info, fins, warnings)
        profit_margin = _profit_margin(info, fins, warnings)
        rev_growth   = _revenue_growth(info, fins, warnings)
        div_yield    = _dividend_yield(info, fins, warnings)

        # ── Score ─────────────────────────────────────────────────────────────

        score = _compute_score(
            pe=pe_ratio.value,
            pb=pb_ratio.value,
            de=debt_to_eq.value,
            margin=profit_margin.value,
            growth=rev_growth.value,
        )

        logger.debug(
            "Fundamental analysis complete",
            extra={"ticker": ticker, "score": score, "warnings": len(warnings)},
        )

        return FundamentalResult(
            ticker=ticker.upper().strip(),
            pe_ratio=pe_ratio,
            eps=eps,
            pb_ratio=pb_ratio,
            debt_to_equity=debt_to_eq,
            profit_margin=profit_margin,
            revenue_growth=rev_growth,
            dividend_yield=div_yield,
            score=score,
            warnings=warnings,
        )


# ── Metric extractors ─────────────────────────────────────────────────────────
# Each function tries Yahoo-style keys first, then FMP-style keys.
# Returns a FundamentalMetric with value=None and appends a warning on failure.


def _pe_ratio(info: dict, fins: dict, warnings: list[str]) -> FundamentalMetric:
    """Extract P/E ratio; tries Yahoo ``trailingPE`` then FMP ``peRatioTTM``."""
    value = _coerce(info.get("trailingPE") or fins.get("peRatioTTM"))
    if value is None:
        warnings.append("P/E ratio is unavailable — trailingPE / peRatioTTM not found in source data.")
    return FundamentalMetric(
        label="Price / Earnings (P/E)",
        value=value,
        unit="x",
        interpretation="How much investors pay for every $1 of earnings. Lower can mean cheaper.",
    )


def _eps(info: dict, warnings: list[str]) -> FundamentalMetric:
    """Extract EPS; uses Yahoo ``trailingEps``."""
    value = _coerce(info.get("trailingEps"))
    if value is None:
        warnings.append("EPS is unavailable — trailingEps not found in source data.")
    return FundamentalMetric(
        label="Earnings Per Share (EPS)",
        value=value,
        unit="$",
        interpretation="Profit earned per share. Higher is generally better.",
    )


def _pb_ratio(info: dict, fins: dict, warnings: list[str]) -> FundamentalMetric:
    """Extract P/B ratio; tries Yahoo ``priceToBook`` then FMP ``pbRatioTTM``."""
    value = _coerce(info.get("priceToBook") or fins.get("pbRatioTTM"))
    if value is None:
        warnings.append("P/B ratio is unavailable — priceToBook / pbRatioTTM not found in source data.")
    return FundamentalMetric(
        label="Price / Book (P/B)",
        value=value,
        unit="x",
        interpretation="Market price vs. accounting value. Above 1 means the market values the company above its book assets.",
    )


def _debt_to_equity(info: dict, fins: dict, warnings: list[str]) -> FundamentalMetric:
    """Extract D/E ratio; tries Yahoo ``debtToEquity`` then FMP ``debtToEquityRatioTTM``."""
    value = _coerce(info.get("debtToEquity") or fins.get("debtToEquityRatioTTM"))
    # Yahoo reports debtToEquity as a percentage (e.g. 170 = 1.70x); normalise to ratio.
    if value is not None and value > 20:
        value = round(value / 100, 4)
    if value is None:
        warnings.append("Debt-to-Equity is unavailable — debtToEquity / debtToEquityRatioTTM not found in source data.")
    return FundamentalMetric(
        label="Debt / Equity (D/E)",
        value=value,
        unit="x",
        interpretation="How much debt the company carries relative to shareholder equity. Lower means less financial risk.",
    )


def _profit_margin(info: dict, fins: dict, warnings: list[str]) -> FundamentalMetric:
    """Extract net profit margin; tries Yahoo ``profitMargins`` then FMP ``netProfitMarginTTM``."""
    raw = info.get("profitMargins") or fins.get("netProfitMarginTTM")
    value = _coerce(raw)
    # Normalise to percentage: Yahoo returns 0–1 fractions; FMP also returns 0–1.
    if value is not None:
        value = round(value * 100, 2) if abs(value) <= 1.0 else round(value, 2)
    if value is None:
        warnings.append("Profit margin is unavailable — profitMargins / netProfitMarginTTM not found in source data.")
    return FundamentalMetric(
        label="Profit Margin",
        value=value,
        unit="%",
        interpretation="Percentage of revenue kept as profit. Higher means the business retains more from each sale.",
    )


def _revenue_growth(info: dict, fins: dict, warnings: list[str]) -> FundamentalMetric:
    """Extract revenue growth; tries Yahoo ``revenueGrowth`` then FMP ``revenueGrowthTTM``."""
    raw = info.get("revenueGrowth") or fins.get("revenueGrowthTTM")
    value = _coerce(raw)
    # Normalise to percentage.
    if value is not None:
        value = round(value * 100, 2) if abs(value) <= 1.0 else round(value, 2)
    if value is None:
        warnings.append("Revenue growth is unavailable — revenueGrowth / revenueGrowthTTM not found in source data.")
    return FundamentalMetric(
        label="Revenue Growth (YoY)",
        value=value,
        unit="%",
        interpretation="Year-over-year change in revenue. Positive means the company is growing its top line.",
    )


def _dividend_yield(info: dict, fins: dict, warnings: list[str]) -> FundamentalMetric:
    """Extract dividend yield; tries Yahoo ``dividendYield`` then FMP ``dividendYieldTTM``."""
    raw = info.get("dividendYield") or fins.get("dividendYieldTTM")
    value = _coerce(raw)
    # Normalise to percentage.
    if value is not None:
        value = round(value * 100, 4) if abs(value) <= 1.0 else round(value, 4)
    # Dividend yield being None is not a warning — many stocks pay no dividend.
    if value is None:
        warnings.append("Dividend yield is unavailable or the company pays no dividend.")
    return FundamentalMetric(
        label="Dividend Yield",
        value=value,
        unit="%",
        interpretation="Annual dividend as a percentage of the share price. 0% simply means the company reinvests profits instead of paying dividends.",
    )


# ── Scoring ───────────────────────────────────────────────────────────────────


def _compute_score(
    pe: float | None,
    pb: float | None,
    de: float | None,
    margin: float | None,
    growth: float | None,
) -> float:
    """
    Derive a composite fundamental health score between 0 and 100.

    Each available metric contributes a sub-score (0–100) based on
    simple industry-neutral thresholds suited to a beginner audience.
    Sub-scores are averaged across whichever metrics are available so
    missing data degrades the score proportionally rather than hard-failing.

    Thresholds (approximate large-cap benchmarks):
        P/E   < 15 → 100, 15–25 → 70, 25–40 → 45, > 40 → 20, negative → 10
        P/B   < 1  → 100, 1–3   → 75, 3–10  → 45, > 10  → 15
        D/E   < 0.5 → 100, 0.5–1 → 75, 1–2 → 50, > 2 → 20
        Margin > 20% → 100, 10–20% → 75, 0–10% → 45, negative → 10
        Growth > 15% → 100, 5–15% → 75, 0–5% → 50, negative → 20
    """
    sub_scores: list[float] = []

    if pe is not None:
        if pe < 0:
            sub_scores.append(10.0)
        elif pe < 15:
            sub_scores.append(100.0)
        elif pe < 25:
            sub_scores.append(70.0)
        elif pe < 40:
            sub_scores.append(45.0)
        else:
            sub_scores.append(20.0)

    if pb is not None:
        if pb < 1:
            sub_scores.append(100.0)
        elif pb < 3:
            sub_scores.append(75.0)
        elif pb < 10:
            sub_scores.append(45.0)
        else:
            sub_scores.append(15.0)

    if de is not None:
        if de < 0.5:
            sub_scores.append(100.0)
        elif de < 1.0:
            sub_scores.append(75.0)
        elif de < 2.0:
            sub_scores.append(50.0)
        else:
            sub_scores.append(20.0)

    if margin is not None:
        if margin > 20:
            sub_scores.append(100.0)
        elif margin > 10:
            sub_scores.append(75.0)
        elif margin >= 0:
            sub_scores.append(45.0)
        else:
            sub_scores.append(10.0)

    if growth is not None:
        if growth > 15:
            sub_scores.append(100.0)
        elif growth > 5:
            sub_scores.append(75.0)
        elif growth >= 0:
            sub_scores.append(50.0)
        else:
            sub_scores.append(20.0)

    if not sub_scores:
        return 50.0  # neutral when no metrics are available

    return round(sum(sub_scores) / len(sub_scores), 2)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _coerce(value: object) -> float | None:
    """
    Convert ``value`` to float, returning ``None`` for falsy or non-numeric input.

    Treats 0.0 as a valid numeric value — only ``None``, empty string, and
    non-numeric types are mapped to ``None``.
    """
    if value is None:
        return None
    try:
        result = float(value)
        return result
    except (TypeError, ValueError):
        return None



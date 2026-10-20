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

import json
import os

from app.config import settings
from app.data.base_source import StockData
from app.logger import get_logger
from app.schemas.analysis import (
    AnalystTargets,
    FundamentalMetric,
    FundamentalResult,
    SectorComparison,
)

# Path to static sector benchmark data (Sub-Task 8).
_SECTOR_BENCHMARKS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "sector_benchmarks.json"
)

logger = get_logger(__name__)


class FundamentalAnalyser:
    """Computes fundamental metrics from a ``StockData`` object."""

    def analyse(self, ticker: str, stock_data: StockData) -> FundamentalResult:
        """
        Compute all fundamental metrics for ``ticker`` using ``stock_data``.

        In addition to the seven core metrics, also computes:
        - Growth Quality Score
        - PEG ratio
        - Analyst price targets
        - Insider ownership & net activity
        - Sector comparison

        Metrics that cannot be computed because source data is missing are
        returned with ``value=None`` and a warning is appended.  The scorer
        only uses metrics that are available so partial data still produces
        a valid result.
        """
        info = stock_data.company_info or {}
        fins = stock_data.financials or {}
        warnings: list[str] = []

        # ── Compute each core metric ──────────────────────────────────────────

        pe_ratio      = _pe_ratio(info, fins, warnings)
        eps           = _eps(info, warnings)
        pb_ratio      = _pb_ratio(info, fins, warnings)
        debt_to_eq    = _debt_to_equity(info, fins, warnings)
        profit_margin = _profit_margin(info, fins, warnings)
        rev_growth    = _revenue_growth(info, fins, warnings)
        div_yield     = _dividend_yield(info, fins, warnings)

        # ── Core score ────────────────────────────────────────────────────────

        score = _compute_score(
            pe=pe_ratio.value,
            pb=pb_ratio.value,
            de=debt_to_eq.value,
            margin=profit_margin.value,
            growth=rev_growth.value,
        )

        # ── New investor signals ──────────────────────────────────────────────

        growth_quality = compute_growth_quality_score(
            revenue_growth=rev_growth.value,
            profit_margin=profit_margin.value,
            free_cash_flow=_coerce(fins.get("freeCashflow")),
            debt_to_equity=debt_to_eq.value,
        )

        peg = compute_peg_ratio(
            pe=pe_ratio.value,
            earnings_growth=_coerce(fins.get("earningsGrowth"))
                            or _coerce(fins.get("earningsQuarterlyGrowth")),
        )

        analyst_targets = _build_analyst_targets(info)
        insider_ownership_pct, insider_net_activity = _build_insider_signals(info, fins)
        sector_comparison = compare_to_sector(
            sector=info.get("sector"),
            pe=pe_ratio.value,
            pb=pb_ratio.value,
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
            growth_quality_score=growth_quality,
            peg_ratio=peg,
            analyst_targets=analyst_targets,
            insider_ownership_pct=insider_ownership_pct,
            insider_net_activity=insider_net_activity,
            sector_comparison=sector_comparison,
            score=score,
            warnings=warnings,
        )


# ── Metric extractors ─────────────────────────────────────────────────────────
# Each function tries Yahoo-style keys first, then FMP-style keys.
# Returns a FundamentalMetric with value=None and appends a warning on failure.


def _pe_ratio(info: dict, fins: dict, warnings: list[str]) -> FundamentalMetric:
    """Extract P/E ratio; tries Yahoo ``trailingPE`` then FMP ``peRatioTTM``."""
    value = _coerce(info.get("trailingPE")) if info.get("trailingPE") is not None else _coerce(fins.get("peRatioTTM"))
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
    value = _coerce(info.get("priceToBook")) if info.get("priceToBook") is not None else _coerce(fins.get("pbRatioTTM"))
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
    value = _coerce(info.get("debtToEquity")) if info.get("debtToEquity") is not None else _coerce(fins.get("debtToEquityRatioTTM"))
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
    raw = info.get("profitMargins") if info.get("profitMargins") is not None else fins.get("netProfitMarginTTM")
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
    raw = info.get("revenueGrowth") if info.get("revenueGrowth") is not None else fins.get("revenueGrowthTTM")
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
    raw = info.get("dividendYield") if info.get("dividendYield") is not None else fins.get("dividendYieldTTM")
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
    configurable industry-neutral thresholds (see ``Settings`` in config.py).
    Sub-scores are averaged across whichever metrics are available so
    missing data degrades the score proportionally rather than hard-failing.

    Default thresholds (approximate large-cap benchmarks):
        P/E   < 15 → 100, 15–25 → 70, 25–40 → 45, > 40 → 20, negative → 10
        P/B   negative → 10, < 1 → 100, 1–3 → 75, 3–10 → 45, > 10 → 15
        D/E   < 0.5 → 100, 0.5–1 → 75, 1–2 → 50, > 2 → 20
        Margin > 20% → 100, 10–20% → 75, 0–10% → 45, negative → 10
        Growth > 15% → 100, 5–15% → 75, 0–5% → 50, negative → 20

    Override via FUNDAMENTAL_PE_THRESHOLDS etc. in the environment.
    """
    sub_scores: list[float] = []

    pe_low, pe_mid, pe_high = settings.pe_thresholds
    pb_low, pb_mid, pb_high = settings.pb_thresholds
    de_low, de_mid, de_high = settings.de_thresholds
    mg_zero, mg_mid, mg_high = settings.margin_thresholds
    gr_zero, gr_mid, gr_high = settings.revenue_growth_thresholds

    if pe is not None:
        if pe < 0:
            sub_scores.append(10.0)
        elif pe < pe_low:
            sub_scores.append(100.0)
        elif pe < pe_mid:
            sub_scores.append(70.0)
        elif pe < pe_high:
            sub_scores.append(45.0)
        else:
            sub_scores.append(20.0)

    if pb is not None:
        if pb < 0:
            sub_scores.append(10.0)
        elif pb < pb_low:
            sub_scores.append(100.0)
        elif pb < pb_mid:
            sub_scores.append(75.0)
        elif pb < pb_high:
            sub_scores.append(45.0)
        else:
            sub_scores.append(15.0)

    if de is not None:
        if de < de_low:
            sub_scores.append(100.0)
        elif de < de_mid:
            sub_scores.append(75.0)
        elif de < de_high:
            sub_scores.append(50.0)
        else:
            sub_scores.append(20.0)

    if margin is not None:
        if margin > mg_high:
            sub_scores.append(100.0)
        elif margin > mg_mid:
            sub_scores.append(75.0)
        elif margin >= mg_zero:
            sub_scores.append(45.0)
        else:
            sub_scores.append(10.0)

    if growth is not None:
        if growth > gr_high:
            sub_scores.append(100.0)
        elif growth > gr_mid:
            sub_scores.append(75.0)
        elif growth >= gr_zero:
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




# ── New investor signal functions ─────────────────────────────────────────────


def compute_growth_quality_score(
    revenue_growth: float | None,
    profit_margin: float | None,
    free_cash_flow: float | None,
    debt_to_equity: float | None,
) -> float | None:
    """
    Compute a Growth Quality Score (0–100) that rewards sustainable, profitable growth.

    Formula (weighted sub-scores):
        revenue_growth_score  × 0.35  — is top-line growing?
        profit_margin_score   × 0.30  — is growth profitable?
        fcf_positive_bonus    × 0.20  — 100 pts if free cash flow > 0, else 0
        debt_direction_bonus  × 0.15  — 100 pts if D/E < 1 (manageable), else 0

    Returns ``None`` when both revenue growth and profit margin are unavailable
    (not enough data to compute a meaningful score).
    """
    # Require at least one of the two primary signals.
    if revenue_growth is None and profit_margin is None:
        return None

    # Re-use existing sub-score logic via _compute_score helpers.
    gr_zero, gr_mid, gr_high = settings.revenue_growth_thresholds
    mg_zero, mg_mid, mg_high = settings.margin_thresholds

    def _rev_score(g: float | None) -> float:
        if g is None:
            return 50.0
        if g > gr_high:
            return 100.0
        if g > gr_mid:
            return 75.0
        if g >= gr_zero:
            return 50.0
        return 20.0

    def _margin_score(m: float | None) -> float:
        if m is None:
            return 50.0
        if m > mg_high:
            return 100.0
        if m > mg_mid:
            return 75.0
        if m >= mg_zero:
            return 45.0
        return 10.0

    rev_s = _rev_score(revenue_growth)
    mar_s = _margin_score(profit_margin)
    fcf_bonus = 100.0 if (free_cash_flow is not None and free_cash_flow > 0) else 0.0
    de_bonus = 100.0 if (debt_to_equity is not None and debt_to_equity < 1.0) else 0.0

    raw = rev_s * 0.35 + mar_s * 0.30 + fcf_bonus * 0.20 + de_bonus * 0.15
    return round(max(0.0, min(100.0, raw)), 2)


def compute_peg_ratio(
    pe: float | None,
    earnings_growth: float | None,
) -> float | None:
    """
    Compute the PEG ratio (Price/Earnings ÷ annual EPS growth rate).

    Returns ``None`` when:
    - P/E is unavailable or negative.
    - EPS growth is unavailable, zero, or negative (division by zero / meaningless).

    The ``earnings_growth`` parameter is expected as a decimal fraction
    (e.g. 0.15 for 15 % growth) as returned by yfinance.
    """
    if pe is None or pe <= 0:
        return None
    if earnings_growth is None or earnings_growth <= 0:
        return None
    # Convert fraction to percentage for the classic PEG formula.
    growth_pct = earnings_growth * 100.0 if abs(earnings_growth) <= 1.0 else earnings_growth
    if growth_pct <= 0:
        return None
    return round(pe / growth_pct, 3)


def _build_analyst_targets(info: dict) -> "AnalystTargets | None":
    """Extract analyst consensus price targets from the yfinance info dict."""
    mean_t = _coerce(info.get("targetMeanPrice"))
    low_t  = _coerce(info.get("targetLowPrice"))
    high_t = _coerce(info.get("targetHighPrice"))
    count  = info.get("numberOfAnalystOpinions")
    key    = info.get("recommendationKey")

    if mean_t is None and low_t is None and high_t is None and key is None:
        return None

    return AnalystTargets(
        mean_target=mean_t,
        low_target=low_t,
        high_target=high_t,
        analyst_count=int(count) if count is not None else None,
        consensus=str(key).lower() if key else None,
    )


def _build_insider_signals(
    info: dict, fins: dict
) -> "tuple[float | None, str | None]":
    """
    Derive insider ownership percentage and net trading activity.

    Returns a 2-tuple: (ownership_pct, net_activity_label).
    """
    raw_pct = _coerce(info.get("heldPercentInsiders"))
    ownership_pct: float | None = None
    if raw_pct is not None:
        # yfinance returns fraction (0–1); convert to %.
        ownership_pct = round(raw_pct * 100.0, 2) if raw_pct <= 1.0 else round(raw_pct, 2)

    net_shares = fins.get("insider_net_shares_6m")
    net_activity: str | None = None
    if net_shares is not None:
        if net_shares > 1000:
            net_activity = "Net Buying"
        elif net_shares < -1000:
            net_activity = "Net Selling"
        else:
            net_activity = "Neutral"

    return ownership_pct, net_activity


def compare_to_sector(
    sector: str | None,
    pe: float | None,
    pb: float | None,
    margin: float | None,
    growth: float | None,
) -> "SectorComparison | None":
    """
    Compare the stock's key multiples against GICS sector medians.

    Returns ``None`` when:
    - ``sector`` is unknown or None.
    - The sector benchmarks JSON file cannot be loaded.
    - None of the multiples can be compared.

    Multiples within ±15 % of the sector median are labelled ``"In-line"``.
    Outside that band: ``"Above"`` or ``"Below"``.
    """
    if not sector:
        return None

    try:
        with open(_SECTOR_BENCHMARKS_PATH) as fh:
            benchmarks: dict = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load sector benchmarks: %s", exc)
        return None

    bench = benchmarks.get(sector)
    if bench is None:
        logger.debug("No sector benchmark found for sector %r", sector)
        return None

    _BAND = 0.15  # ±15 % tolerance for "In-line"

    def _classify(value: float | None, median: float | None) -> str | None:
        if value is None or median is None or median == 0:
            return None
        ratio = value / median
        if ratio > (1 + _BAND):
            return "Above"
        if ratio < (1 - _BAND):
            return "Below"
        return "In-line"

    result = SectorComparison(
        sector=sector,
        pe_vs_sector=_classify(pe, bench.get("pe")),
        pb_vs_sector=_classify(pb, bench.get("pb")),
        margin_vs_sector=_classify(margin, bench.get("margin")),
        growth_vs_sector=_classify(growth, bench.get("revenue_growth")),
    )

    # Return None if no comparison could be made (all metrics None).
    if all(
        v is None
        for v in (
            result.pe_vs_sector,
            result.pb_vs_sector,
            result.margin_vs_sector,
            result.growth_vs_sector,
        )
    ):
        return None

    return result

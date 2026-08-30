"""
Technical analysis module.

``TechnicalAnalyser.analyse(stock_data)`` runs the ``ta`` library over the
``price_history`` DataFrame in a ``StockData`` object and produces:

    Trend indicators  : SMA(20), SMA(50), SMA(200), EMA(12), EMA(26)
    Momentum          : RSI(14), MACD line, MACD signal, MACD histogram
    Volatility        : Bollinger Bands (window=20, 2 std-devs)

Each indicator is returned as an ``IndicatorSeries`` — a list of
``Optional[float]`` values aligned to the date axis — so the frontend can
plot them directly.  Seven scalar "latest_*" fields hold the most recent
non-NaN value from each key indicator for the scoring logic.

A composite ``score`` (0–100) is computed from the latest RSI, MACD
crossover, and price-vs-SMA relationships so the orchestrator can derive
a Buy / Hold / Sell recommendation without an LLM.

When ``price_history`` is ``None`` or has fewer than 2 rows the analyser
returns a result with all series empty, all latest values ``None``,
score 50 (neutral), and a warning — it never raises.
"""

from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from app.data.base_source import StockData
from app.logger import get_logger
from app.schemas.analysis import IndicatorSeries, TechnicalResult

logger = get_logger(__name__)

# Minimum bars required for any indicator to be meaningful.
_MIN_BARS = 2


class TechnicalAnalyser:
    """Computes technical indicators from the price history in a ``StockData`` object."""

    def analyse(self, ticker: str, stock_data: StockData) -> TechnicalResult:
        """
        Compute all technical indicators for ``ticker`` using ``stock_data.price_history``.

        Returns a ``TechnicalResult`` with full time-series for charting and
        scalar latest-values for scoring.  All series are aligned to the same
        date axis.  Missing or insufficient price data produces a neutral
        result with a warning rather than an exception.
        """
        warnings: list[str] = []
        df = stock_data.price_history

        if df is None or len(df) < _MIN_BARS:
            warnings.append(
                "Price history is unavailable or too short to compute technical indicators."
            )
            logger.warning(
                "Insufficient price history for technical analysis",
                extra={"ticker": ticker, "rows": 0 if df is None else len(df)},
            )
            return _empty_result(ticker, warnings)

        # Ensure we have a Close column (case-insensitive normalisation).
        df = _normalise_columns(df)
        if "Close" not in df.columns:
            warnings.append("Price history is missing the Close column — cannot compute indicators.")
            return _empty_result(ticker, warnings)

        close: pd.Series = df["Close"].astype(float)

        # ── Compute all indicators ────────────────────────────────────────────

        sma_20_s  = _sma(close, 20)
        sma_50_s  = _sma(close, 50)
        sma_200_s = _sma(close, 200)
        ema_12_s  = _ema(close, 12)
        ema_26_s  = _ema(close, 26)
        rsi_s     = _rsi(close, 14)
        macd_line, macd_sig, macd_hist = _macd(close, 12, 26, 9)
        bb_upper_s, bb_mid_s, bb_lower_s = _bollinger(close, 20, 2)

        # ── Build date axis ───────────────────────────────────────────────────

        dates = [d.strftime("%Y-%m-%d") for d in df.index]

        # ── Latest scalar values ──────────────────────────────────────────────

        latest_close   = _last(close)
        latest_sma_20  = _last(sma_20_s)
        latest_sma_50  = _last(sma_50_s)
        latest_sma_200 = _last(sma_200_s)
        latest_rsi     = _last(rsi_s)
        latest_macd    = _last(macd_line)
        latest_signal  = _last(macd_sig)

        # ── Score ─────────────────────────────────────────────────────────────

        score = _compute_score(
            rsi=latest_rsi,
            macd=latest_macd,
            macd_signal=latest_signal,
            close=latest_close,
            sma_20=latest_sma_20,
            sma_50=latest_sma_50,
            sma_200=latest_sma_200,
        )

        logger.debug(
            "Technical analysis complete",
            extra={"ticker": ticker, "bars": len(df), "score": score},
        )

        return TechnicalResult(
            ticker=ticker,
            dates=dates,
            close_prices=_to_list(close),
            sma_20=IndicatorSeries(name="SMA 20",  values=_to_list(sma_20_s)),
            sma_50=IndicatorSeries(name="SMA 50",  values=_to_list(sma_50_s)),
            sma_200=IndicatorSeries(name="SMA 200", values=_to_list(sma_200_s)),
            ema_12=IndicatorSeries(name="EMA 12",  values=_to_list(ema_12_s)),
            ema_26=IndicatorSeries(name="EMA 26",  values=_to_list(ema_26_s)),
            rsi_14=IndicatorSeries(name="RSI 14",  values=_to_list(rsi_s)),
            macd=IndicatorSeries(name="MACD",            values=_to_list(macd_line)),
            macd_signal=IndicatorSeries(name="MACD Signal",    values=_to_list(macd_sig)),
            macd_histogram=IndicatorSeries(name="MACD Histogram", values=_to_list(macd_hist)),
            bb_upper=IndicatorSeries(name="BB Upper",  values=_to_list(bb_upper_s)),
            bb_middle=IndicatorSeries(name="BB Middle", values=_to_list(bb_mid_s)),
            bb_lower=IndicatorSeries(name="BB Lower",  values=_to_list(bb_lower_s)),
            latest_close=latest_close,
            latest_sma_20=latest_sma_20,
            latest_sma_50=latest_sma_50,
            latest_sma_200=latest_sma_200,
            latest_rsi=latest_rsi,
            latest_macd=latest_macd,
            latest_macd_signal=latest_signal,
            score=score,
            warnings=warnings,
        )


# ── Indicator wrappers ────────────────────────────────────────────────────────
# Each returns a pd.Series of the same length as ``close``.
# Warm-up bars where the indicator is undefined are NaN.


def _sma(close: pd.Series, window: int) -> pd.Series:
    """Compute Simple Moving Average with the given ``window`` using the ``ta`` library."""
    try:
        import ta.trend
        return ta.trend.SMAIndicator(close=close, window=window).sma_indicator()
    except Exception:  # noqa: BLE001
        return pd.Series([float("nan")] * len(close), index=close.index)


def _ema(close: pd.Series, window: int) -> pd.Series:
    """Compute Exponential Moving Average with the given ``window`` using the ``ta`` library."""
    try:
        import ta.trend
        return ta.trend.EMAIndicator(close=close, window=window).ema_indicator()
    except Exception:  # noqa: BLE001
        return pd.Series([float("nan")] * len(close), index=close.index)


def _rsi(close: pd.Series, window: int) -> pd.Series:
    """Compute RSI with the given ``window`` using the ``ta`` library."""
    try:
        import ta.momentum
        return ta.momentum.RSIIndicator(close=close, window=window).rsi()
    except Exception:  # noqa: BLE001
        return pd.Series([float("nan")] * len(close), index=close.index)


def _macd(
    close: pd.Series,
    fast: int,
    slow: int,
    signal: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Compute MACD line, signal line, and histogram using the ``ta`` library.

    Returns a 3-tuple: ``(macd_line, macd_signal, macd_histogram)``.
    """
    try:
        import ta.trend
        obj = ta.trend.MACD(
            close=close,
            window_fast=fast,
            window_slow=slow,
            window_sign=signal,
        )
        return obj.macd(), obj.macd_signal(), obj.macd_diff()
    except Exception:  # noqa: BLE001
        nan_s = pd.Series([float("nan")] * len(close), index=close.index)
        return nan_s, nan_s.copy(), nan_s.copy()


def _bollinger(
    close: pd.Series,
    window: int,
    window_dev: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Compute Bollinger Bands (upper, middle, lower) using the ``ta`` library.

    Returns a 3-tuple: ``(bb_upper, bb_middle, bb_lower)``.
    """
    try:
        import ta.volatility
        bb = ta.volatility.BollingerBands(
            close=close,
            window=window,
            window_dev=window_dev,
        )
        return bb.bollinger_hband(), bb.bollinger_mavg(), bb.bollinger_lband()
    except Exception:  # noqa: BLE001
        nan_s = pd.Series([float("nan")] * len(close), index=close.index)
        return nan_s, nan_s.copy(), nan_s.copy()


# ── Scoring ───────────────────────────────────────────────────────────────────


def _compute_score(
    rsi: Optional[float],
    macd: Optional[float],
    macd_signal: Optional[float],
    close: Optional[float],
    sma_20: Optional[float],
    sma_50: Optional[float],
    sma_200: Optional[float],
) -> float:
    """
    Derive a composite technical momentum score between 0 and 100.

    Signals used and their weights:
        RSI(14)              25 pts  — overbought / oversold
        MACD crossover       25 pts  — momentum direction
        Price vs SMA(20)     20 pts  — short-term trend
        Price vs SMA(50)     15 pts  — medium-term trend
        Price vs SMA(200)    15 pts  — long-term trend (golden/death cross proxy)

    Any signal whose inputs are missing is skipped; the remaining weights are
    renormalised so the score stays on a 0–100 scale.  With no signals at
    all, 50 (neutral) is returned.
    """
    signals: list[tuple[float, float]] = []   # (raw_score_0_to_1, weight)

    # RSI: < 30 oversold (bullish opportunity) → high score,
    #       > 70 overbought (sell pressure)    → low score,
    #       30–70 neutral.
    if rsi is not None:
        if rsi < 30:
            rsi_score = 0.85
        elif rsi < 45:
            rsi_score = 0.70
        elif rsi <= 55:
            rsi_score = 0.50
        elif rsi <= 70:
            rsi_score = 0.35
        else:
            rsi_score = 0.20
        signals.append((rsi_score, 25.0))

    # MACD: line above signal → bullish momentum.
    if macd is not None and macd_signal is not None:
        macd_score = 0.75 if macd > macd_signal else 0.25
        signals.append((macd_score, 25.0))

    # Price vs SMA(20): price above → short-term bullish.
    if close is not None and sma_20 is not None:
        signals.append((0.70 if close > sma_20 else 0.30, 20.0))

    # Price vs SMA(50): price above → medium-term bullish.
    if close is not None and sma_50 is not None:
        signals.append((0.70 if close > sma_50 else 0.30, 15.0))

    # Price vs SMA(200): golden cross proxy.
    if close is not None and sma_200 is not None:
        signals.append((0.75 if close > sma_200 else 0.25, 15.0))

    if not signals:
        return 50.0

    total_weight = sum(w for _, w in signals)
    weighted_sum = sum(s * w for s, w in signals)
    raw = (weighted_sum / total_weight) * 100.0
    return round(max(0.0, min(100.0, raw)), 2)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _to_list(series: pd.Series) -> list[Optional[float]]:
    """Convert a pandas Series to a list of ``Optional[float]``, mapping NaN → None."""
    result: list[Optional[float]] = []
    for v in series:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            result.append(None)
        else:
            result.append(float(v))
    return result


def _last(series: pd.Series) -> Optional[float]:
    """Return the last non-NaN value in ``series``, or ``None`` if all are NaN."""
    clean = series.dropna()
    if clean.empty:
        return None
    return float(clean.iloc[-1])


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a copy of ``df`` with columns title-cased so ``open``, ``OPEN``,
    and ``Open`` all become ``Open``.

    This makes the analyser tolerant of minor casing differences from
    different data sources.
    """
    df = df.copy()
    df.columns = [str(c).capitalize() if str(c).lower() in
                  {"open", "high", "low", "close", "volume"}
                  else c for c in df.columns]
    return df


def _empty_result(ticker: str, warnings: list[str]) -> TechnicalResult:
    """Return a fully-empty ``TechnicalResult`` with a neutral score of 50."""
    empty_series = IndicatorSeries(name="", values=[])
    return TechnicalResult(
        ticker=ticker,
        dates=[],
        close_prices=[],
        sma_20=empty_series,
        sma_50=empty_series,
        sma_200=empty_series,
        ema_12=empty_series,
        ema_26=empty_series,
        rsi_14=empty_series,
        macd=empty_series,
        macd_signal=empty_series,
        macd_histogram=empty_series,
        bb_upper=empty_series,
        bb_middle=empty_series,
        bb_lower=empty_series,
        score=50.0,
        warnings=warnings,
    )

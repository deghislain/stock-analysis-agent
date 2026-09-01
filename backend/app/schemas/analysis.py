"""
Pydantic output schemas for the analysis layer (Sub-Task 3) and the API
request/response layer (Sub-Task 5).

Seven models are defined here:

    FundamentalResult  — output of FundamentalAnalyser.analyse()
    TechnicalResult    — output of TechnicalAnalyser.analyse()
    SentimentResult    — output of SentimentAnalyser.analyse()
    AnalysisResult     — aggregate that combines all three + a top-level score
                         and recommendation; this is what the agent layer
                         assembles and passes to the report agent.

    AnalyseRequest     — body of ``POST /api/analyse``
    AnalyseResponse    — response of ``POST /api/analyse``
    ValidateResponse   — response of ``GET /api/validate/{ticker}``

All analysis models are read-only (frozen) to prevent accidental mutation
downstream.  The three API models are intentionally not frozen — they are
short-lived request/response objects.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ── Fundamental ───────────────────────────────────────────────────────────────


class FundamentalMetric(BaseModel):
    """A single computed fundamental metric with its display label and raw value."""

    label: str
    """Beginner-friendly display name shown in the UI (e.g. ``"Price / Earnings (P/E)"``).  """

    value: Optional[float]
    """Raw numeric value, or ``None`` when the metric could not be computed."""

    unit: Optional[str] = None
    """
    Optional unit string for display purposes (e.g. ``"%"``, ``"x"``, ``"$"``).

    ``None`` when the value is already a plain ratio or dimensionless number.
    """

    interpretation: Optional[str] = None
    """
    One-sentence plain-language hint for beginners
    (e.g. ``"Lower is generally cheaper relative to earnings."``).

    Populated by the analyser so beginners understand what the number means
    without needing the LLM.
    """

    model_config = {"frozen": True}


class FundamentalResult(BaseModel):
    """Output of ``FundamentalAnalyser.analyse()`` for a single ticker."""

    ticker: str
    """Upper-case ticker symbol this result belongs to."""

    pe_ratio: FundamentalMetric
    """Price-to-Earnings ratio — how much investors pay per dollar of earnings."""

    eps: FundamentalMetric
    """Earnings Per Share — profit allocated to each outstanding share."""

    pb_ratio: FundamentalMetric
    """Price-to-Book ratio — market value relative to accounting book value."""

    debt_to_equity: FundamentalMetric
    """Debt-to-Equity ratio — financial leverage; higher means more debt."""

    profit_margin: FundamentalMetric
    """Net profit margin — percentage of revenue kept as net income."""

    revenue_growth: FundamentalMetric
    """Year-over-year revenue growth rate as a percentage."""

    dividend_yield: FundamentalMetric
    """Annual dividend as a percentage of the current share price."""

    score: float = Field(ge=0.0, le=100.0)
    """
    Composite fundamental health score from 0 (weakest) to 100 (strongest).

    Feeds the executive summary recommendation alongside ``TechnicalResult.score``.
    """

    warnings: list[str] = Field(default_factory=list)
    """
    Warning messages for any metric that could not be computed due to
    missing source data.  Propagates to the frontend ``WarningFlags`` component.
    """

    model_config = {"frozen": True}


# ── Technical ─────────────────────────────────────────────────────────────────


class IndicatorSeries(BaseModel):
    """A named time-series of indicator values for charting on the frontend."""

    name: str
    """Display name of the indicator (e.g. ``"SMA 20"``, ``"Bollinger Upper"``)."""

    values: list[Optional[float]]
    """
    Ordered list of indicator values aligned to ``TechnicalResult.dates``.

    ``None`` entries appear at the start of the series where insufficient
    history exists to compute the indicator (e.g. first 19 bars of SMA 20).
    """

    model_config = {"frozen": True}


class TechnicalResult(BaseModel):
    """Output of ``TechnicalAnalyser.analyse()`` for a single ticker."""

    ticker: str
    """Upper-case ticker symbol this result belongs to."""

    dates: list[str]
    """
    ISO-8601 date strings (``YYYY-MM-DD``) aligned with ``close_prices``
    and every ``IndicatorSeries.values`` list.  Used as the x-axis on charts.
    """

    close_prices: list[Optional[float]]
    """Closing price series aligned to ``dates`` — the primary chart line."""

    sma_20: IndicatorSeries
    """Simple Moving Average over the last 20 trading days."""

    sma_50: IndicatorSeries
    """Simple Moving Average over the last 50 trading days."""

    sma_200: IndicatorSeries
    """Simple Moving Average over the last 200 trading days."""

    ema_12: IndicatorSeries
    """Exponential Moving Average with a 12-period span."""

    ema_26: IndicatorSeries
    """Exponential Moving Average with a 26-period span."""

    rsi_14: IndicatorSeries
    """Relative Strength Index with a 14-period lookback (0–100 scale)."""

    macd: IndicatorSeries
    """MACD line — difference between EMA(12) and EMA(26)."""

    macd_signal: IndicatorSeries
    """MACD signal line — 9-period EMA of the MACD line."""

    macd_histogram: IndicatorSeries
    """MACD histogram — difference between MACD line and signal line."""

    bb_upper: IndicatorSeries
    """Bollinger Band upper boundary (SMA 20 + 2 standard deviations)."""

    bb_middle: IndicatorSeries
    """Bollinger Band middle line (SMA 20)."""

    bb_lower: IndicatorSeries
    """Bollinger Band lower boundary (SMA 20 − 2 standard deviations)."""

    # Latest snapshot values (scalar) — used by the scoring logic and report agent.

    latest_rsi: Optional[float] = None
    """Most recent RSI(14) value, or ``None`` if insufficient history."""

    latest_macd: Optional[float] = None
    """Most recent MACD line value, or ``None`` if insufficient history."""

    latest_macd_signal: Optional[float] = None
    """Most recent MACD signal line value, or ``None`` if insufficient history."""

    latest_close: Optional[float] = None
    """Most recent closing price, or ``None`` if price history is empty."""

    latest_sma_20: Optional[float] = None
    """Most recent SMA(20), or ``None`` if insufficient history."""

    latest_sma_50: Optional[float] = None
    """Most recent SMA(50), or ``None`` if insufficient history."""

    latest_sma_200: Optional[float] = None
    """Most recent SMA(200), or ``None`` if insufficient history."""

    score: float = Field(ge=0.0, le=100.0)
    """
    Composite technical momentum score from 0 (bearish) to 100 (bullish).

    Feeds the executive summary recommendation alongside ``FundamentalResult.score``.
    """

    warnings: list[str] = Field(default_factory=list)
    """Warning messages for any indicator that could not be computed."""

    model_config = {"frozen": True}


# ── Sentiment ─────────────────────────────────────────────────────────────────


class SentimentResult(BaseModel):
    """Output of ``SentimentAnalyser.analyse()`` for a list of news headlines."""

    ticker: str
    """Upper-case ticker symbol this result belongs to."""

    positive_count: int = Field(ge=0)
    """Number of headlines classified as positive."""

    neutral_count: int = Field(ge=0)
    """Number of headlines classified as neutral."""

    negative_count: int = Field(ge=0)
    """Number of headlines classified as negative."""

    score: float = Field(ge=0.0, le=100.0)
    """
    Overall sentiment score from 0 (very negative) to 100 (very positive).

    50 represents a perfectly neutral baseline.
    """

    label: str
    """
    Human-readable sentiment label derived from ``score``:
    one of ``"Positive"``, ``"Neutral"``, or ``"Negative"``.
    """

    headlines_analysed: int = Field(ge=0)
    """Total number of headlines that were fed into the analyser."""

    model_config = {"frozen": True}


# ── Aggregate ─────────────────────────────────────────────────────────────────


class AnalysisResult(BaseModel):
    """
    Aggregate output produced by the orchestrator after all three analysers run.

    This is the single object passed to the report agent for plain-language
    generation and to the API layer for serialisation into the final
    ``ReportPayload``.
    """

    ticker: str
    """Upper-case ticker symbol this result belongs to."""

    fundamental: FundamentalResult
    """Fundamental analysis output."""

    technical: TechnicalResult
    """Technical analysis output."""

    sentiment: SentimentResult
    """News sentiment analysis output."""

    overall_score: float = Field(ge=0.0, le=100.0)
    """
    Weighted composite of fundamental, technical, and sentiment scores.

    Weights: fundamental 40 %, technical 40 %, sentiment 20 %.
    Maps to ``recommendation`` via: ≥ 60 → Buy, 40–59 → Hold, < 40 → Sell.
    """

    recommendation: str
    """
    Top-level recommendation string: one of ``"Buy"``, ``"Hold"``, or ``"Sell"``.

    Derived from ``overall_score`` by the orchestrator.
    """

    sources_used: list[str] = Field(default_factory=list)
    """Data source names that contributed to this analysis (from ``FallbackResult``)."""

    warnings: list[str] = Field(default_factory=list)
    """
    Deduplicated union of all warnings from the data layer and analysis layer.

    Propagates to the frontend ``WarningFlags`` component and the PDF report.
    """

    disclaimer: str = Field(
        default=(
            "For informational purposes only. "
            "Not financial advice. "
            "Always consult a qualified financial adviser before making investment decisions."
        )
    )
    """
    Mandatory disclaimer baked into every result object and every generated report.

    This field must never be removed or left blank.
    """

    model_config = {"frozen": True}


# ── API request / response schemas (Sub-Task 5) ───────────────────────────────


class AnalyseRequest(BaseModel):
    """
    Request body for ``POST /api/analyse``.

    The ticker is normalised (upper-cased and stripped) and validated against
    the ticker regex in the route handler before this model is used.
    """

    ticker: str
    """
    Stock ticker symbol to analyse (e.g. ``"AAPL"``, ``"BRK.B"``).

    Must match ``^[A-Z0-9]{1,5}([.\\-][A-Z]{1,2})?$`` after
    ``.upper().strip()``.  The route handler raises HTTP 422 when validation
    fails.
    """


class AnalyseResponse(BaseModel):
    """
    Response body for ``POST /api/analyse``.

    Returned immediately after the job is created; the orchestrator runs
    in the background via FastAPI ``BackgroundTasks``.
    """

    job_id: str
    """UUID string that uniquely identifies the created analysis job."""

    status: str
    """
    Initial job status — always ``"pending"`` at the moment of job creation.
    """


class ValidateResponse(BaseModel):
    """
    Response body for ``GET /api/validate/{ticker}``.

    Always returns HTTP 200 — the caller (frontend) decides how to react based
    on the ``valid`` flag.  Never raises 4xx for unknown tickers; 422 is only
    raised when the ticker string fails the regex format check.
    """

    valid: bool
    """
    ``True`` when the ticker passes format validation *and* yfinance can
    resolve it to a real instrument; ``False`` otherwise.
    """

    name: Optional[str] = None
    """
    Company or instrument name returned by yfinance (e.g. ``"Apple Inc."``).

    Populated only when ``valid`` is ``True``; ``None`` otherwise.
    """

    reason: Optional[str] = None
    """
    Short human-readable explanation of why validation failed.

    Populated only when ``valid`` is ``False``; ``None`` otherwise.
    Examples: ``"Symbol not found"``, ``"Invalid ticker format"``.
    """

"""
Unit tests for the analysis layer (Sub-Task 3).

Covers:
  schemas/analysis.py  — FundamentalMetric, FundamentalResult, IndicatorSeries,
                          TechnicalResult, SentimentResult, AnalysisResult
  analysis/fundamental — FundamentalAnalyser, all seven extractors, scoring,
                          _coerce, _extract_ticker, D/E normalisation,
                          fraction-to-percent normalisation, Yahoo/FMP dual keys
  analysis/technical  — TechnicalAnalyser happy-path (250 bars), warm-up NaN→None,
                          series alignment, insufficient/None data, column
                          normalisation, _to_list, _last, _compute_score
  analysis/sentiment  — SentimentAnalyser, _extract_text, _score_text,
                          _net_to_score, _score_to_label, all label thresholds,
                          clamping, empty/positive/negative/mixed/no-text inputs
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

# ── Shared helpers ────────────────────────────────────────────────────────────


def _make_price_df(rows: int = 250, start: float = 100.0, end: float = 150.0) -> pd.DataFrame:
    """Return a synthetic OHLCV DataFrame with a DatetimeIndex."""
    import numpy as np
    dates  = pd.date_range("2023-01-01", periods=rows, freq="B")
    prices = np.linspace(start, end, rows)
    return pd.DataFrame(
        {
            "Open":   prices * 0.99,
            "High":   prices * 1.01,
            "Low":    prices * 0.98,
            "Close":  prices,
            "Volume": 1_000_000,
        },
        index=dates,
    )


def _make_stock_data(
    rows: int = 250,
    price_df: pd.DataFrame | None = None,
    company_info: dict | None = None,
    financials: dict | None = None,
    source_name: str = "Yahoo Finance",
):
    """Build a ``StockData`` for use in tests."""
    from app.data.base_source import StockData
    return StockData(
        source_name=source_name,
        price_history=price_df if price_df is not None else _make_price_df(rows),
        company_info=company_info or {},
        financials=financials or {},
    )


# ═════════════════════════════════════════════════════════════════════════════
# schemas/analysis.py
# ═════════════════════════════════════════════════════════════════════════════


class TestFundamentalMetric:
    """Tests for the FundamentalMetric schema model."""

    def test_instantiation_with_all_fields(self):
        """All fields are stored correctly."""
        from app.schemas.analysis import FundamentalMetric
        m = FundamentalMetric(label="P/E", value=28.5, unit="x", interpretation="Hint.")
        assert m.label == "P/E"
        assert m.value == 28.5
        assert m.unit == "x"
        assert m.interpretation == "Hint."

    def test_value_may_be_none(self):
        """value=None is valid and signals an unavailable metric."""
        from app.schemas.analysis import FundamentalMetric
        m = FundamentalMetric(label="EPS", value=None)
        assert m.value is None

    def test_unit_and_interpretation_default_to_none(self):
        """Optional fields default to None when omitted."""
        from app.schemas.analysis import FundamentalMetric
        m = FundamentalMetric(label="X", value=1.0)
        assert m.unit is None
        assert m.interpretation is None

    def test_frozen(self):
        """FundamentalMetric is immutable."""
        from app.schemas.analysis import FundamentalMetric
        m = FundamentalMetric(label="X", value=1.0)
        with pytest.raises(Exception):
            m.value = 99.0  # type: ignore[misc]


class TestFundamentalResult:
    """Tests for the FundamentalResult schema model."""

    def _make(self, score=50.0, **overrides):
        from app.schemas.analysis import FundamentalMetric, FundamentalResult
        metric = FundamentalMetric(label="X", value=None)
        defaults = dict(
            ticker="AAPL", pe_ratio=metric, eps=metric, pb_ratio=metric,
            debt_to_equity=metric, profit_margin=metric, revenue_growth=metric,
            dividend_yield=metric, score=score, warnings=[],
        )
        defaults.update(overrides)
        return FundamentalResult(**defaults)

    def test_score_bounds_enforced_high(self):
        """score > 100 raises ValidationError."""
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            self._make(score=101.0)

    def test_score_bounds_enforced_low(self):
        """score < 0 raises ValidationError."""
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            self._make(score=-1.0)

    def test_warnings_defaults_to_empty_list(self):
        """warnings defaults to [] when not supplied."""
        r = self._make()
        assert r.warnings == []

    def test_frozen(self):
        """FundamentalResult is immutable."""
        r = self._make()
        with pytest.raises(Exception):
            r.score = 99.0  # type: ignore[misc]


class TestIndicatorSeries:
    """Tests for the IndicatorSeries schema model."""

    def test_stores_values_including_none(self):
        """values list may contain None entries for warm-up bars."""
        from app.schemas.analysis import IndicatorSeries
        s = IndicatorSeries(name="SMA 20", values=[None, None, 101.5])
        assert s.values[0] is None
        assert s.values[2] == 101.5

    def test_frozen(self):
        """IndicatorSeries is immutable."""
        from app.schemas.analysis import IndicatorSeries
        s = IndicatorSeries(name="X", values=[1.0])
        with pytest.raises(Exception):
            s.name = "Y"  # type: ignore[misc]


class TestSentimentResult:
    """Tests for the SentimentResult schema model."""

    def _make(self, score=50.0):
        from app.schemas.analysis import SentimentResult
        return SentimentResult(
            ticker="AAPL", positive_count=1, neutral_count=1, negative_count=1,
            score=score, label="Neutral", headlines_analysed=3,
        )

    def test_score_bounds_high(self):
        """score > 100 raises ValidationError."""
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            self._make(score=100.1)

    def test_score_bounds_low(self):
        """score < 0 raises ValidationError."""
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            self._make(score=-0.1)

    def test_frozen(self):
        """SentimentResult is immutable."""
        r = self._make()
        with pytest.raises(Exception):
            r.score = 99.0  # type: ignore[misc]


class TestAnalysisResult:
    """Tests for the AnalysisResult aggregate schema."""

    def test_disclaimer_default_is_baked_in(self):
        """disclaimer is always present and contains required text."""
        from app.schemas.analysis import (
            AnalysisResult, FundamentalMetric, FundamentalResult,
            IndicatorSeries, TechnicalResult, SentimentResult,
        )
        metric  = FundamentalMetric(label="X", value=None)
        fund    = FundamentalResult(
            ticker="X", pe_ratio=metric, eps=metric, pb_ratio=metric,
            debt_to_equity=metric, profit_margin=metric, revenue_growth=metric,
            dividend_yield=metric, score=50.0,
        )
        empty_s = IndicatorSeries(name="", values=[])
        tech    = TechnicalResult(
            ticker="X", dates=[], close_prices=[],
            sma_20=empty_s, sma_50=empty_s, sma_200=empty_s,
            ema_12=empty_s, ema_26=empty_s, rsi_14=empty_s,
            macd=empty_s, macd_signal=empty_s, macd_histogram=empty_s,
            bb_upper=empty_s, bb_middle=empty_s, bb_lower=empty_s,
            score=50.0,
        )
        sent = SentimentResult(
            ticker="X", positive_count=0, neutral_count=0, negative_count=0,
            score=50.0, label="Neutral", headlines_analysed=0,
        )
        ar = AnalysisResult(
            ticker="AAPL", fundamental=fund, technical=tech, sentiment=sent,
            overall_score=50.0, recommendation="Hold",
        )
        assert "Not financial advice" in ar.disclaimer
        assert len(ar.disclaimer) > 0

    def test_frozen(self):
        """AnalysisResult is immutable."""
        from app.schemas.analysis import (
            AnalysisResult, FundamentalMetric, FundamentalResult,
            IndicatorSeries, TechnicalResult, SentimentResult,
        )
        metric  = FundamentalMetric(label="X", value=None)
        fund    = FundamentalResult(
            ticker="X", pe_ratio=metric, eps=metric, pb_ratio=metric,
            debt_to_equity=metric, profit_margin=metric, revenue_growth=metric,
            dividend_yield=metric, score=50.0,
        )
        empty_s = IndicatorSeries(name="", values=[])
        tech    = TechnicalResult(
            ticker="X", dates=[], close_prices=[],
            sma_20=empty_s, sma_50=empty_s, sma_200=empty_s,
            ema_12=empty_s, ema_26=empty_s, rsi_14=empty_s,
            macd=empty_s, macd_signal=empty_s, macd_histogram=empty_s,
            bb_upper=empty_s, bb_middle=empty_s, bb_lower=empty_s,
            score=50.0,
        )
        sent = SentimentResult(
            ticker="X", positive_count=0, neutral_count=0, negative_count=0,
            score=50.0, label="Neutral", headlines_analysed=0,
        )
        ar = AnalysisResult(
            ticker="AAPL", fundamental=fund, technical=tech, sentiment=sent,
            overall_score=50.0, recommendation="Hold",
        )
        with pytest.raises(Exception):
            ar.recommendation = "Buy"  # type: ignore[misc]


# ═════════════════════════════════════════════════════════════════════════════
# analysis/fundamental.py
# ═════════════════════════════════════════════════════════════════════════════


class TestFundamentalAnalyserHappyPath:
    """FundamentalAnalyser with complete Yahoo Finance data."""

    @pytest.fixture(autouse=True)
    def analyser(self):
        """Provide a fresh FundamentalAnalyser."""
        from app.analysis.fundamental import FundamentalAnalyser
        self.fa = FundamentalAnalyser()

    def _yahoo_sd(self, **info_overrides):
        base = {
            "symbol": "AAPL",
            "trailingPE": 28.5,
            "trailingEps": 6.43,
            "priceToBook": 45.2,
            "debtToEquity": 170.0,   # percentage format
            "profitMargins": 0.2531,
            "revenueGrowth": 0.051,
            "dividendYield": 0.0055,
        }
        base.update(info_overrides)
        return _make_stock_data(company_info=base, price_df=None)

    def test_ticker_stored_from_caller_argument(self):
        """ticker field is the uppercased value passed by the caller."""
        r = self.fa.analyse("AAPL", self._yahoo_sd())
        assert r.ticker == "AAPL"

    def test_pe_ratio_yahoo_key(self):
        """trailingPE is mapped to pe_ratio."""
        r = self.fa.analyse("AAPL", self._yahoo_sd())
        assert r.pe_ratio.value == 28.5
        assert r.pe_ratio.unit == "x"

    def test_eps_yahoo_key(self):
        """trailingEps is mapped to eps."""
        r = self.fa.analyse("AAPL", self._yahoo_sd())
        assert r.eps.value == 6.43

    def test_pb_ratio_yahoo_key(self):
        """priceToBook is mapped to pb_ratio."""
        r = self.fa.analyse("AAPL", self._yahoo_sd())
        assert r.pb_ratio.value == 45.2

    def test_debt_to_equity_normalised_from_yahoo_percentage(self):
        """debtToEquity=170 (Yahoo %) is normalised to 1.70x."""
        r = self.fa.analyse("AAPL", self._yahoo_sd())
        assert round(r.debt_to_equity.value, 2) == 1.70

    def test_debt_to_equity_small_value_not_divided(self):
        """debtToEquity=1.5 (already a ratio) is not divided by 100."""
        r = self.fa.analyse("AAPL", self._yahoo_sd(debtToEquity=1.5))
        assert r.debt_to_equity.value == 1.5

    def test_profit_margin_fraction_to_percent(self):
        """profitMargins=0.2531 → 25.31%."""
        r = self.fa.analyse("AAPL", self._yahoo_sd())
        assert r.profit_margin.value == 25.31
        assert r.profit_margin.unit == "%"

    def test_revenue_growth_fraction_to_percent(self):
        """revenueGrowth=0.051 → 5.1%."""
        r = self.fa.analyse("AAPL", self._yahoo_sd())
        assert r.revenue_growth.value == 5.1

    def test_dividend_yield_fraction_to_percent(self):
        """dividendYield=0.0055 → 0.55%."""
        r = self.fa.analyse("AAPL", self._yahoo_sd())
        assert r.dividend_yield.value == 0.55

    def test_no_warnings_when_all_data_present(self):
        """No warnings are produced when every metric is available."""
        r = self.fa.analyse("AAPL", self._yahoo_sd())
        assert r.warnings == []

    def test_score_in_bounds(self):
        """score is between 0 and 100."""
        r = self.fa.analyse("AAPL", self._yahoo_sd())
        assert 0 <= r.score <= 100


class TestFundamentalAnalyserFMPFallback:
    """FundamentalAnalyser falls back to FMP-style keys in financials."""

    @pytest.fixture(autouse=True)
    def analyser(self):
        from app.analysis.fundamental import FundamentalAnalyser
        self.fa = FundamentalAnalyser()

    def _fmp_sd(self):
        return _make_stock_data(
            company_info={"companyName": "Apple Inc."},
            financials={
                "peRatioTTM": 27.0,
                "pbRatioTTM": 40.0,
                "debtToEquityRatioTTM": 1.65,
                "netProfitMarginTTM": 0.241,
                "revenueGrowthTTM": 0.06,
                "dividendYieldTTM": 0.005,
            },
            price_df=None,
        )

    def test_pe_ratio_fmp_fallback(self):
        """peRatioTTM used when trailingPE absent."""
        r = self.fa.analyse("AAPL", self._fmp_sd())
        assert r.pe_ratio.value == 27.0

    def test_pb_ratio_fmp_fallback(self):
        """pbRatioTTM used when priceToBook absent."""
        r = self.fa.analyse("AAPL", self._fmp_sd())
        assert r.pb_ratio.value == 40.0

    def test_debt_to_equity_fmp_already_ratio(self):
        """debtToEquityRatioTTM=1.65 is kept as-is (already a ratio)."""
        r = self.fa.analyse("AAPL", self._fmp_sd())
        assert round(r.debt_to_equity.value, 2) == 1.65

    def test_profit_margin_fmp(self):
        """netProfitMarginTTM=0.241 → 24.1%."""
        r = self.fa.analyse("AAPL", self._fmp_sd())
        assert r.profit_margin.value == 24.1

    def test_eps_missing_produces_warning(self):
        """EPS has no FMP key → value=None and one warning."""
        r = self.fa.analyse("AAPL", self._fmp_sd())
        assert r.eps.value is None
        assert any("EPS" in w for w in r.warnings)


class TestFundamentalAnalyserMissingData:
    """FundamentalAnalyser with empty source data."""

    @pytest.fixture(autouse=True)
    def analyser(self):
        from app.analysis.fundamental import FundamentalAnalyser
        self.fa = FundamentalAnalyser()

    def test_all_metrics_none_when_both_dicts_empty(self):
        """Every metric value is None when company_info and financials are empty."""
        r = self.fa.analyse("AAPL", _make_stock_data(company_info={}, financials={}, price_df=None))
        assert r.pe_ratio.value is None
        assert r.eps.value is None
        assert r.pb_ratio.value is None
        assert r.debt_to_equity.value is None
        assert r.profit_margin.value is None
        assert r.revenue_growth.value is None
        assert r.dividend_yield.value is None

    def test_seven_warnings_when_all_missing(self):
        """One warning per missing metric."""
        r = self.fa.analyse("AAPL", _make_stock_data(company_info={}, financials={}, price_df=None))
        assert len(r.warnings) == 7

    def test_score_is_neutral_when_no_metrics(self):
        """Score defaults to 50 (neutral) when no metrics are available."""
        r = self.fa.analyse("AAPL", _make_stock_data(company_info={}, financials={}, price_df=None))
        assert r.score == 50.0

    def test_ticker_passed_through_to_result(self):
        """ticker on the result is exactly the caller-supplied ticker (uppercased)."""
        r = self.fa.analyse("aapl", _make_stock_data(company_info={}, financials={}, price_df=None))
        assert r.ticker == "AAPL"


class TestFundamentalScoring:
    """Unit tests for _compute_score thresholds."""

    def test_pe_below_15_scores_100(self):
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=10, pb=None, de=None, margin=None, growth=None) == 100.0

    def test_pe_15_to_25_scores_70(self):
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=20, pb=None, de=None, margin=None, growth=None) == 70.0

    def test_pe_25_to_40_scores_45(self):
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=30, pb=None, de=None, margin=None, growth=None) == 45.0

    def test_pe_above_40_scores_20(self):
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=50, pb=None, de=None, margin=None, growth=None) == 20.0

    def test_negative_pe_scores_10(self):
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=-5, pb=None, de=None, margin=None, growth=None) == 10.0

    def test_no_metrics_returns_50(self):
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=None, pb=None, de=None, margin=None, growth=None) == 50.0

    def test_multiple_metrics_averaged(self):
        """Score is the mean of available sub-scores."""
        from app.analysis.fundamental import _compute_score
        # pe<15 → 100, de<0.5 → 100, margin>20 → 100, growth>15 → 100 → avg=100
        assert _compute_score(pe=10, pb=None, de=0.3, margin=25.0, growth=20.0) == 100.0

    def test_single_metric_equals_that_subscore(self):
        """With one metric, score equals its individual sub-score."""
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=None, pb=0.5, de=None, margin=None, growth=None) == 100.0


class TestCoerce:
    """Unit tests for the _coerce helper."""

    def test_none_returns_none(self):
        from app.analysis.fundamental import _coerce
        assert _coerce(None) is None

    def test_empty_string_returns_none(self):
        from app.analysis.fundamental import _coerce
        assert _coerce("") is None

    def test_non_numeric_string_returns_none(self):
        from app.analysis.fundamental import _coerce
        assert _coerce("abc") is None

    def test_zero_float_is_valid(self):
        """0.0 must NOT be treated as missing."""
        from app.analysis.fundamental import _coerce
        assert _coerce(0.0) == 0.0

    def test_int_converted_to_float(self):
        from app.analysis.fundamental import _coerce
        assert _coerce(28) == 28.0

    def test_numeric_string_converted(self):
        from app.analysis.fundamental import _coerce
        assert _coerce("28.5") == 28.5


# ═════════════════════════════════════════════════════════════════════════════
# analysis/technical.py
# ═════════════════════════════════════════════════════════════════════════════


class TestTechnicalAnalyserHappyPath:
    """TechnicalAnalyser with a healthy 250-bar price history."""

    @pytest.fixture(autouse=True)
    def result(self):
        """Run the analyser once; share the result across all tests in this class."""
        from app.analysis.technical import TechnicalAnalyser
        self.r = TechnicalAnalyser().analyse("AAPL", _make_stock_data(rows=250))

    def test_ticker_stored(self):
        assert self.r.ticker == "AAPL"

    def test_dates_length(self):
        assert len(self.r.dates) == 250

    def test_close_prices_length(self):
        assert len(self.r.close_prices) == 250

    def test_all_series_same_length_as_dates(self):
        """Every IndicatorSeries.values list is aligned to the date axis."""
        for attr in (
            "sma_20", "sma_50", "sma_200", "ema_12", "ema_26", "rsi_14",
            "macd", "macd_signal", "macd_histogram",
            "bb_upper", "bb_middle", "bb_lower",
        ):
            series = getattr(self.r, attr)
            assert len(series.values) == 250, f"{attr}: expected 250 values"

    def test_sma_20_warmup_none(self):
        """First 19 bars of SMA(20) are None (warm-up period)."""
        assert self.r.sma_20.values[0] is None

    def test_sma_20_last_value_populated(self):
        """SMA(20) is populated at the last bar."""
        assert self.r.sma_20.values[-1] is not None

    def test_sma_200_last_value_populated(self):
        """SMA(200) is populated at bar 250."""
        assert self.r.sma_200.values[-1] is not None

    def test_latest_close_not_none(self):
        assert self.r.latest_close is not None

    def test_latest_rsi_not_none(self):
        assert self.r.latest_rsi is not None

    def test_latest_macd_not_none(self):
        assert self.r.latest_macd is not None

    def test_score_in_bounds(self):
        assert 0.0 <= self.r.score <= 100.0

    def test_no_warnings(self):
        assert self.r.warnings == []

    def test_dates_are_iso_format(self):
        """Dates are YYYY-MM-DD strings."""
        import re
        for d in self.r.dates[:5]:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", d), f"bad date: {d}"


class TestTechnicalAnalyserWarmup:
    """SMA(200) stays None with only 50 bars."""

    def test_sma200_all_none_with_50_bars(self):
        """SMA(200) requires 200 bars — all values must be None with 50 bars."""
        from app.analysis.technical import TechnicalAnalyser
        r = TechnicalAnalyser().analyse("MSFT", _make_stock_data(rows=50))
        assert all(v is None for v in r.sma_200.values)
        assert r.latest_sma_200 is None

    def test_sma20_populated_with_50_bars(self):
        """SMA(20) should have values with 50 bars."""
        from app.analysis.technical import TechnicalAnalyser
        r = TechnicalAnalyser().analyse("MSFT", _make_stock_data(rows=50))
        assert r.sma_20.values[-1] is not None


class TestTechnicalAnalyserInsufficientData:
    """TechnicalAnalyser returns safe empty result on bad/missing input."""

    def test_none_price_history_empty_result(self):
        """price_history=None → empty TechnicalResult with warning and score=50."""
        from app.analysis.technical import TechnicalAnalyser
        r = TechnicalAnalyser().analyse("X", _make_stock_data(price_df=None, rows=0))
        # price_df=None is passed via make_stock_data with explicit price_df arg
        sd = _make_stock_data.__wrapped__ if hasattr(_make_stock_data, "__wrapped__") else None
        from app.data.base_source import StockData
        r = TechnicalAnalyser().analyse("X", StockData(
            source_name="X", price_history=None, company_info={}, financials={},
        ))
        assert r.dates == []
        assert r.score == 50.0
        assert len(r.warnings) == 1
        assert "unavailable" in r.warnings[0]

    def test_single_row_price_history_empty_result(self):
        """1-row DataFrame → empty result (fewer than _MIN_BARS=2)."""
        from app.analysis.technical import TechnicalAnalyser
        r = TechnicalAnalyser().analyse("X", _make_stock_data(rows=1))
        assert r.dates == []
        assert r.score == 50.0

    def test_missing_close_column_empty_result(self):
        """DataFrame without a Close column → empty result with warning."""
        from app.analysis.technical import TechnicalAnalyser
        from app.data.base_source import StockData
        df = _make_price_df(50).drop(columns=["Close"])
        r = TechnicalAnalyser().analyse("X", StockData(
            source_name="X", price_history=df, company_info={}, financials={},
        ))
        assert r.dates == []
        assert any("Close" in w for w in r.warnings)


class TestTechnicalColumnNormalisation:
    """Lowercase column names are normalised to title-case."""

    def test_lowercase_columns_accepted(self):
        """price_history with lowercase column names still computes indicators."""
        from app.analysis.technical import TechnicalAnalyser
        from app.data.base_source import StockData
        df = _make_price_df(250)
        df.columns = [c.lower() for c in df.columns]
        r = TechnicalAnalyser().analyse("X", StockData(
            source_name="X", price_history=df, company_info={}, financials={},
        ))
        assert r.latest_close is not None

    def test_uppercase_columns_accepted(self):
        """price_history with upper-case column names still computes indicators."""
        from app.analysis.technical import TechnicalAnalyser
        from app.data.base_source import StockData
        df = _make_price_df(250)
        df.columns = [c.upper() for c in df.columns]
        r = TechnicalAnalyser().analyse("X", StockData(
            source_name="X", price_history=df, company_info={}, financials={},
        ))
        assert r.latest_close is not None


class TestToList:
    """Unit tests for the _to_list helper."""

    def test_nan_becomes_none(self):
        from app.analysis.technical import _to_list
        s = pd.Series([1.0, float("nan"), 3.0])
        assert _to_list(s) == [1.0, None, 3.0]

    def test_all_valid_floats_preserved(self):
        from app.analysis.technical import _to_list
        s = pd.Series([1.0, 2.0, 3.0])
        assert _to_list(s) == [1.0, 2.0, 3.0]

    def test_empty_series_returns_empty_list(self):
        from app.analysis.technical import _to_list
        assert _to_list(pd.Series([], dtype=float)) == []


class TestLast:
    """Unit tests for the _last helper."""

    def test_returns_last_non_nan(self):
        from app.analysis.technical import _last
        s = pd.Series([1.0, 2.0, float("nan")])
        assert _last(s) == 2.0

    def test_all_nan_returns_none(self):
        from app.analysis.technical import _last
        assert _last(pd.Series([float("nan"), float("nan")])) is None

    def test_empty_series_returns_none(self):
        from app.analysis.technical import _last
        assert _last(pd.Series([], dtype=float)) is None


class TestTechnicalScoring:
    """Unit tests for _compute_score."""

    def test_no_signals_returns_50(self):
        from app.analysis.technical import _compute_score
        assert _compute_score(None, None, None, None, None, None, None) == 50.0

    def test_rsi_oversold_bullish(self):
        """RSI < 30 → bullish (score > 50)."""
        from app.analysis.technical import _compute_score
        s = _compute_score(rsi=25, macd=None, macd_signal=None,
                           close=None, sma_20=None, sma_50=None, sma_200=None)
        assert s > 50.0

    def test_rsi_overbought_bearish(self):
        """RSI > 70 → bearish (score < 50)."""
        from app.analysis.technical import _compute_score
        s = _compute_score(rsi=80, macd=None, macd_signal=None,
                           close=None, sma_20=None, sma_50=None, sma_200=None)
        assert s < 50.0

    def test_macd_above_signal_bullish(self):
        """MACD line above signal line → bullish."""
        from app.analysis.technical import _compute_score
        bull = _compute_score(rsi=None, macd=1.0, macd_signal=0.5,
                              close=None, sma_20=None, sma_50=None, sma_200=None)
        bear = _compute_score(rsi=None, macd=0.5, macd_signal=1.0,
                              close=None, sma_20=None, sma_50=None, sma_200=None)
        assert bull > bear

    def test_price_above_sma20_bullish(self):
        from app.analysis.technical import _compute_score
        bull = _compute_score(rsi=None, macd=None, macd_signal=None,
                              close=110, sma_20=100, sma_50=None, sma_200=None)
        bear = _compute_score(rsi=None, macd=None, macd_signal=None,
                              close=90, sma_20=100, sma_50=None, sma_200=None)
        assert bull > bear

    def test_score_always_in_bounds(self):
        """Score is always clamped to [0, 100]."""
        from app.analysis.technical import _compute_score
        for rsi, macd, sig, close, s20, s50, s200 in [
            (25, 1.0, 0.0, 110, 100, 95, 90),
            (80, 0.0, 1.0, 90, 100, 105, 110),
        ]:
            s = _compute_score(rsi, macd, sig, close, s20, s50, s200)
            assert 0.0 <= s <= 100.0


# ═════════════════════════════════════════════════════════════════════════════
# analysis/sentiment.py
# ═════════════════════════════════════════════════════════════════════════════


class TestSentimentAnalyserEmptyInput:
    """SentimentAnalyser with no news items."""

    @pytest.fixture(autouse=True)
    def analyser(self):
        from app.analysis.sentiment import SentimentAnalyser
        self.sa = SentimentAnalyser()

    def test_empty_list_score_50(self):
        r = self.sa.analyse("AAPL", [])
        assert r.score == 50.0

    def test_empty_list_label_neutral(self):
        r = self.sa.analyse("AAPL", [])
        assert r.label == "Neutral"

    def test_empty_list_all_counts_zero(self):
        r = self.sa.analyse("AAPL", [])
        assert r.positive_count == 0
        assert r.neutral_count == 0
        assert r.negative_count == 0

    def test_empty_list_headlines_analysed_zero(self):
        r = self.sa.analyse("AAPL", [])
        assert r.headlines_analysed == 0

    def test_ticker_stored(self):
        r = self.sa.analyse("AAPL", [])
        assert r.ticker == "AAPL"


class TestSentimentAnalyserPositive:
    """SentimentAnalyser with clearly positive headlines."""

    @pytest.fixture(autouse=True)
    def analyser(self):
        from app.analysis.sentiment import SentimentAnalyser
        self.sa = SentimentAnalyser()
        self.items = [
            {"title": "Apple beats earnings estimates with record revenue growth"},
            {"title": "Stock soars after strong quarterly profit"},
            {"title": "Company gains momentum, analysts upgrade to buy"},
        ]
        self.r = self.sa.analyse("AAPL", self.items)

    def test_score_above_50(self):
        assert self.r.score > 50.0

    def test_label_positive(self):
        assert self.r.label == "Positive"

    def test_all_three_classified_positive(self):
        assert self.r.positive_count == 3
        assert self.r.negative_count == 0

    def test_headlines_analysed_correct(self):
        assert self.r.headlines_analysed == 3


class TestSentimentAnalyserNegative:
    """SentimentAnalyser with clearly negative headlines."""

    @pytest.fixture(autouse=True)
    def analyser(self):
        from app.analysis.sentiment import SentimentAnalyser
        self.sa = SentimentAnalyser()
        self.items = [
            {"title": "Apple misses earnings, stock drops on weak revenue"},
            {"title": "Company faces lawsuit and fraud investigation"},
            {"title": "Layoffs announced as earnings disappoint investors"},
        ]
        self.r = self.sa.analyse("AAPL", self.items)

    def test_score_below_50(self):
        assert self.r.score < 50.0

    def test_label_negative(self):
        assert self.r.label == "Negative"

    def test_all_three_classified_negative(self):
        assert self.r.negative_count == 3
        assert self.r.positive_count == 0


class TestSentimentAnalyserNoTextField:
    """News item with no recognised text field counts as neutral."""

    def test_no_text_item_is_neutral(self):
        from app.analysis.sentiment import SentimentAnalyser
        r = SentimentAnalyser().analyse("X", [{"url": "http://x.com", "date": "2024-01-01"}])
        assert r.neutral_count == 1
        assert r.score == 50.0
        assert r.headlines_analysed == 1


class TestSentimentAnalyserTextFields:
    """SentimentAnalyser reads body, snippet, and description fields."""

    def test_body_field_used(self):
        from app.analysis.sentiment import SentimentAnalyser
        r = SentimentAnalyser().analyse("X", [
            {"body": "Stock surges on record profit and strong growth"},
        ])
        assert r.positive_count == 1

    def test_snippet_field_used(self):
        from app.analysis.sentiment import SentimentAnalyser
        r = SentimentAnalyser().analyse("X", [
            {"snippet": "Revenue growth beats analyst expectations"},
        ])
        assert r.positive_count == 1

    def test_description_field_used(self):
        from app.analysis.sentiment import SentimentAnalyser
        r = SentimentAnalyser().analyse("X", [
            {"description": "Company expands with new investment and partnership"},
        ])
        assert r.positive_count == 1

    def test_multiple_fields_joined(self):
        """All text fields are combined before keyword matching."""
        from app.analysis.sentiment import SentimentAnalyser, _extract_text
        item = {"title": "Earnings Beat", "body": "Record profit growth", "snippet": "Surge"}
        text = _extract_text(item)
        assert "earnings beat" in text
        assert "record profit growth" in text
        assert "surge" in text


class TestExtractText:
    """Unit tests for the _extract_text helper."""

    def test_only_title(self):
        from app.analysis.sentiment import _extract_text
        assert _extract_text({"title": "Hello World"}) == "hello world"

    def test_multiple_fields_joined_with_space(self):
        from app.analysis.sentiment import _extract_text
        t = _extract_text({"title": "A", "body": "B"})
        assert t == "a b"

    def test_none_values_skipped(self):
        from app.analysis.sentiment import _extract_text
        t = _extract_text({"title": "A", "body": None, "snippet": "B"})
        assert t == "a b"

    def test_non_string_values_skipped(self):
        from app.analysis.sentiment import _extract_text
        t = _extract_text({"title": 123, "body": "Valid"})
        assert t == "valid"

    def test_empty_dict_returns_empty_string(self):
        from app.analysis.sentiment import _extract_text
        assert _extract_text({}) == ""


class TestScoreText:
    """Unit tests for the _score_text helper."""

    def test_positive_keyword_hit(self):
        from app.analysis.sentiment import _score_text
        pos, neg = _score_text("company records strong growth and beat expectations")
        assert pos >= 2
        assert neg == 0

    def test_negative_keyword_hit(self):
        from app.analysis.sentiment import _score_text
        pos, neg = _score_text("company faces lawsuit and layoff after earnings miss")
        assert neg >= 2

    def test_no_keywords_both_zero(self):
        from app.analysis.sentiment import _score_text
        pos, neg = _score_text("the company released a product today")
        assert pos == 0
        assert neg == 0


class TestNetToScore:
    """Unit tests for the _net_to_score helper."""

    def test_zero_returns_50(self):
        from app.analysis.sentiment import _net_to_score
        assert _net_to_score(0) == 50.0

    def test_positive_above_50(self):
        from app.analysis.sentiment import _net_to_score
        assert _net_to_score(2) == 60.0

    def test_negative_below_50(self):
        from app.analysis.sentiment import _net_to_score
        assert _net_to_score(-2) == 40.0

    def test_large_positive_clamped_to_100(self):
        from app.analysis.sentiment import _net_to_score
        assert _net_to_score(100) == 100.0

    def test_large_negative_clamped_to_0(self):
        from app.analysis.sentiment import _net_to_score
        assert _net_to_score(-100) == 0.0


class TestScoreToLabel:
    """Unit tests for the _score_to_label helper."""

    def test_60_is_positive(self):
        from app.analysis.sentiment import _score_to_label
        assert _score_to_label(60.0) == "Positive"

    def test_59_9_is_neutral(self):
        from app.analysis.sentiment import _score_to_label
        assert _score_to_label(59.9) == "Neutral"

    def test_40_1_is_neutral(self):
        from app.analysis.sentiment import _score_to_label
        assert _score_to_label(40.1) == "Neutral"

    def test_40_is_negative(self):
        from app.analysis.sentiment import _score_to_label
        assert _score_to_label(40.0) == "Negative"

    def test_100_is_positive(self):
        from app.analysis.sentiment import _score_to_label
        assert _score_to_label(100.0) == "Positive"

    def test_0_is_negative(self):
        from app.analysis.sentiment import _score_to_label
        assert _score_to_label(0.0) == "Negative"


# ═════════════════════════════════════════════════════════════════════════════
# Coverage gap fill-ins
# ═════════════════════════════════════════════════════════════════════════════


class TestFundamentalScoringAllBranches:
    """Explicit tests for every un-hit scoring bracket in _compute_score."""

    # ── P/B brackets ────────────────────────────────────────────────────────

    def test_pb_1_to_3_scores_75(self):
        """P/B in [1, 3) → sub-score 75."""
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=None, pb=2.0, de=None, margin=None, growth=None) == 75.0

    def test_pb_3_to_10_scores_45(self):
        """P/B in [3, 10) → sub-score 45."""
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=None, pb=5.0, de=None, margin=None, growth=None) == 45.0

    def test_pb_above_10_scores_15(self):
        """P/B >= 10 → sub-score 15."""
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=None, pb=12.0, de=None, margin=None, growth=None) == 15.0

    # ── D/E brackets ────────────────────────────────────────────────────────

    def test_de_0_5_to_1_scores_75(self):
        """D/E in [0.5, 1.0) → sub-score 75."""
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=None, pb=None, de=0.7, margin=None, growth=None) == 75.0

    def test_de_above_2_scores_20(self):
        """D/E >= 2.0 → sub-score 20."""
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=None, pb=None, de=3.0, margin=None, growth=None) == 20.0

    # ── Margin brackets ─────────────────────────────────────────────────────

    def test_margin_10_to_20_scores_75(self):
        """Margin in (10, 20] % → sub-score 75."""
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=None, pb=None, de=None, margin=15.0, growth=None) == 75.0

    def test_margin_0_to_10_scores_45(self):
        """Margin in [0, 10] % → sub-score 45."""
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=None, pb=None, de=None, margin=5.0, growth=None) == 45.0

    def test_margin_negative_scores_10(self):
        """Negative margin → sub-score 10."""
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=None, pb=None, de=None, margin=-3.0, growth=None) == 10.0

    # ── Growth brackets ─────────────────────────────────────────────────────

    def test_growth_0_to_5_scores_50(self):
        """Growth in [0, 5] % → sub-score 50."""
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=None, pb=None, de=None, margin=None, growth=3.0) == 50.0

    def test_growth_negative_scores_20(self):
        """Negative growth → sub-score 20."""
        from app.analysis.fundamental import _compute_score
        assert _compute_score(pe=None, pb=None, de=None, margin=None, growth=-5.0) == 20.0


class TestTechnicalScoringAllRSIBranches:
    """Every RSI scoring bracket in _compute_score."""

    def test_rsi_30_to_45_score_70(self):
        """RSI in [30, 45) → raw_score 0.70 → contributes to bullish side."""
        from app.analysis.technical import _compute_score
        s = _compute_score(rsi=38, macd=None, macd_signal=None,
                           close=None, sma_20=None, sma_50=None, sma_200=None)
        assert s == 70.0  # single signal: 0.70 * 100 = 70

    def test_rsi_45_to_55_score_50(self):
        """RSI in [45, 55] → raw_score 0.50 → neutral."""
        from app.analysis.technical import _compute_score
        s = _compute_score(rsi=50, macd=None, macd_signal=None,
                           close=None, sma_20=None, sma_50=None, sma_200=None)
        assert s == 50.0

    def test_rsi_55_to_70_score_35(self):
        """RSI in (55, 70] → raw_score 0.35 → bearish lean."""
        from app.analysis.technical import _compute_score
        s = _compute_score(rsi=62, macd=None, macd_signal=None,
                           close=None, sma_20=None, sma_50=None, sma_200=None)
        assert s == 35.0


class TestTechnicalIndicatorExceptionFallback:
    """The except branches in _sma, _ema, _rsi, _macd, _bollinger return NaN series."""

    def _close(self, n=10):
        """Return a simple close series for testing."""
        return pd.Series(range(100, 100 + n), dtype=float)

    def test_sma_exception_returns_nan_series(self):
        """When ta.trend raises, _sma returns an all-NaN series of the right length."""
        from unittest.mock import patch
        from app.analysis.technical import _sma
        close = self._close(10)
        with patch("ta.trend.SMAIndicator", side_effect=RuntimeError("boom")):
            result = _sma(close, 20)
        assert len(result) == 10
        assert all(math.isnan(v) for v in result)

    def test_ema_exception_returns_nan_series(self):
        """When ta.trend raises, _ema returns an all-NaN series of the right length."""
        from unittest.mock import patch
        from app.analysis.technical import _ema
        close = self._close(10)
        with patch("ta.trend.EMAIndicator", side_effect=RuntimeError("boom")):
            result = _ema(close, 12)
        assert len(result) == 10
        assert all(math.isnan(v) for v in result)

    def test_rsi_exception_returns_nan_series(self):
        """When ta.momentum raises, _rsi returns an all-NaN series of the right length."""
        from unittest.mock import patch
        from app.analysis.technical import _rsi
        close = self._close(10)
        with patch("ta.momentum.RSIIndicator", side_effect=RuntimeError("boom")):
            result = _rsi(close, 14)
        assert len(result) == 10
        assert all(math.isnan(v) for v in result)

    def test_macd_exception_returns_three_nan_series(self):
        """When ta.trend raises inside _macd, all three returned series are NaN."""
        from unittest.mock import patch
        from app.analysis.technical import _macd
        close = self._close(10)
        with patch("ta.trend.MACD", side_effect=RuntimeError("boom")):
            line, sig, hist = _macd(close, 12, 26, 9)
        for s in (line, sig, hist):
            assert len(s) == 10
            assert all(math.isnan(v) for v in s)

    def test_bollinger_exception_returns_three_nan_series(self):
        """When ta.volatility raises inside _bollinger, all three series are NaN."""
        from unittest.mock import patch
        from app.analysis.technical import _bollinger
        close = self._close(10)
        with patch("ta.volatility.BollingerBands", side_effect=RuntimeError("boom")):
            upper, mid, lower = _bollinger(close, 20, 2)
        for s in (upper, mid, lower):
            assert len(s) == 10
            assert all(math.isnan(v) for v in s)


class TestToListNoneEntry:
    """_to_list handles a Python None entry (e.g. from object-dtype Series)."""

    def test_python_none_in_object_series_becomes_none(self):
        """A Python None in an object-dtype Series is mapped to None in the output."""
        from app.analysis.technical import _to_list
        s = pd.Series([1.0, None, 3.0], dtype=object)
        result = _to_list(s)
        assert result == [1.0, None, 3.0]

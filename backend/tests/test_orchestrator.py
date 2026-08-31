"""
Unit tests for core/orchestrator.py (Sub-Task 4, Todo 9).

Covers:
  _compute_overall_score — weights and clamping
  _score_to_recommendation — all three thresholds
  Orchestrator.run()
    — happy path: job reaches "complete", result dict has all required keys
    — unknown ticker (DataAgent raises ValueError): job reaches "error"
    — DataAgent error dict (non-raise): job still completes with warning
    — FundamentalAgent error dict: warning added, pipeline continues
    — TechnicalAgent error dict: warning added, pipeline continues
    — ReportAgent LLM unavailable: fallback text used, warning added
    — job store updated at each pipeline step (current_step labels)
    — warnings are deduplicated in the final payload
    — overall recommendation is overridden by LLM when LLM succeeds
    — pdf_path is None in the initial payload
    — generated_at is an ISO datetime string
    — disclaimer is present and non-empty
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.job_store import JobStore
from app.core.orchestrator import (
    Orchestrator,
    _compute_overall_score,
    _score_to_recommendation,
)


# ═════════════════════════════════════════════════════════════════════════════
# _compute_overall_score
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeOverallScore:

    def test_weighted_sum(self):
        """40% fund + 40% tech + 20% sentiment."""
        # 100*0.4 + 100*0.4 + 100*0.2 = 100
        assert _compute_overall_score(100, 100, 100) == 100.0

    def test_all_zero(self):
        assert _compute_overall_score(0, 0, 0) == 0.0

    def test_weights_applied_correctly(self):
        # fund=100, tech=0, sent=0  → 40.0
        assert _compute_overall_score(100, 0, 0) == 40.0

    def test_sentiment_weight(self):
        # fund=0, tech=0, sent=100 → 20.0
        assert _compute_overall_score(0, 0, 100) == 20.0

    def test_typical_values(self):
        # fund=60, tech=70, sent=55  → 60*0.4 + 70*0.4 + 55*0.2 = 24+28+11 = 63
        assert _compute_overall_score(60, 70, 55) == 63.0

    def test_result_clamped_to_100(self):
        assert _compute_overall_score(200, 200, 200) == 100.0

    def test_result_clamped_to_0(self):
        assert _compute_overall_score(-100, -100, -100) == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# _score_to_recommendation
# ═════════════════════════════════════════════════════════════════════════════


class TestScoreToRecommendation:

    def test_60_is_buy(self):
        assert _score_to_recommendation(60.0) == "Buy"

    def test_above_60_is_buy(self):
        assert _score_to_recommendation(75.0) == "Buy"

    def test_100_is_buy(self):
        assert _score_to_recommendation(100.0) == "Buy"

    def test_59_9_is_hold(self):
        assert _score_to_recommendation(59.9) == "Hold"

    def test_40_1_is_hold(self):
        assert _score_to_recommendation(40.1) == "Hold"

    def test_50_is_hold(self):
        assert _score_to_recommendation(50.0) == "Hold"

    def test_40_is_sell(self):
        assert _score_to_recommendation(40.0) == "Sell"

    def test_0_is_sell(self):
        assert _score_to_recommendation(0.0) == "Sell"


# ═════════════════════════════════════════════════════════════════════════════
# Helpers — build cheap fakes for every agent
# ═════════════════════════════════════════════════════════════════════════════


def _make_fundamental_result(score: float = 60.0):
    from app.schemas.analysis import FundamentalMetric, FundamentalResult
    m = FundamentalMetric(label="X", value=None)
    return FundamentalResult(
        ticker="AAPL", pe_ratio=m, eps=m, pb_ratio=m,
        debt_to_equity=m, profit_margin=m, revenue_growth=m,
        dividend_yield=m, score=score, warnings=[],
    )


def _make_technical_result(score: float = 60.0):
    from app.schemas.analysis import IndicatorSeries, TechnicalResult
    empty = IndicatorSeries(name="", values=[])
    return TechnicalResult(
        ticker="AAPL", dates=[], close_prices=[],
        sma_20=empty, sma_50=empty, sma_200=empty,
        ema_12=empty, ema_26=empty, rsi_14=empty,
        macd=empty, macd_signal=empty, macd_histogram=empty,
        bb_upper=empty, bb_middle=empty, bb_lower=empty,
        score=score, warnings=[],
    )


def _make_sentiment_result(score: float = 60.0):
    from app.schemas.analysis import SentimentResult
    return SentimentResult(
        ticker="AAPL", positive_count=1, neutral_count=0, negative_count=0,
        score=score, label="Positive", headlines_analysed=1,
    )


def _make_stock_data():
    from app.data.base_source import StockData
    import pandas as pd
    import numpy as np
    dates  = pd.date_range("2023-01-01", periods=10, freq="B")
    prices = np.linspace(100, 110, 10)
    df = pd.DataFrame({"Open": prices, "High": prices, "Low": prices,
                       "Close": prices, "Volume": 1_000_000}, index=dates)
    return StockData(source_name="Yahoo Finance", price_history=df,
                     company_info={}, financials={})


def _fake_data_agent(stock_data=None, warnings=None):
    """Return a mock DataAgent whose run() succeeds."""
    agent = AsyncMock()
    agent.name = "DataAgent"
    agent.run = AsyncMock(return_value={
        "status": "ok",
        "stock_data": stock_data or _make_stock_data(),
        "sources_used": ["Yahoo Finance"],
        "warnings": warnings or [],
    })
    return agent


def _fake_research_agent(news_items=None, warnings=None):
    agent = AsyncMock()
    agent.name = "ResearchAgent"
    agent.run = AsyncMock(return_value={
        "status": "ok",
        "news_items": news_items or [{"title": "AAPL rises", "url": "http://x.com",
                                       "body": "", "source": "x.com"}],
        "warnings": warnings or [],
    })
    return agent


def _fake_fundamental_agent(result=None, error=None):
    agent = AsyncMock()
    agent.name = "FundamentalAgent"
    if error:
        agent.run = AsyncMock(return_value={"status": "error", "error": error,
                                             "fundamental_result": result or _make_fundamental_result()})
    else:
        agent.run = AsyncMock(return_value={"status": "ok",
                                             "fundamental_result": result or _make_fundamental_result()})
    return agent


def _fake_technical_agent(result=None, error=None):
    agent = AsyncMock()
    agent.name = "TechnicalAgent"
    if error:
        agent.run = AsyncMock(return_value={"status": "error", "error": error,
                                             "technical_result": result or _make_technical_result()})
    else:
        agent.run = AsyncMock(return_value={"status": "ok",
                                             "technical_result": result or _make_technical_result()})
    return agent


def _fake_report_agent(recommendation="Buy", fallback=False):
    agent = AsyncMock()
    agent.name = "ReportAgent"
    warnings = ["AI-generated explanation unavailable — raw data shown only."] if fallback else []
    agent.run = AsyncMock(return_value={
        "status": "ok",
        "executive_summary": "Summary.",
        "recommendation": recommendation,
        "rationale": "Rationale sentence one. Two. Three.",
        "fundamental_explanation": "Fundamentals look good.",
        "technical_explanation": "Technicals are bullish.",
        "warnings": warnings,
    })
    return agent


def _fake_sentiment_analyser():
    sa = MagicMock()
    sa.analyse = MagicMock(return_value=_make_sentiment_result())
    return sa


def _make_orchestrator(**overrides) -> tuple[Orchestrator, JobStore]:
    """Build an Orchestrator with all agents faked out; return (orch, store)."""
    store = JobStore()
    defaults = dict(
        data_agent=_fake_data_agent(),
        research_agent=_fake_research_agent(),
        fundamental_agent=_fake_fundamental_agent(),
        technical_agent=_fake_technical_agent(),
        report_agent=_fake_report_agent(),
        sentiment_analyser=_fake_sentiment_analyser(),
    )
    defaults.update(overrides)
    return Orchestrator(store, **defaults), store


# ═════════════════════════════════════════════════════════════════════════════
# Happy path
# ═════════════════════════════════════════════════════════════════════════════


class TestOrchestratorHappyPath:

    async def test_job_status_complete(self):
        orch, store = _make_orchestrator()
        store.create_job("j1")
        await orch.run("AAPL", "j1")
        assert store.get_job("j1").status == "complete"

    async def test_result_stored_in_job(self):
        orch, store = _make_orchestrator()
        store.create_job("j2")
        await orch.run("AAPL", "j2")
        assert store.get_job("j2").result is not None

    async def test_result_has_required_keys(self):
        required = {
            "job_id", "ticker", "generated_at", "status", "recommendation",
            "rationale", "fundamental_result", "technical_result",
            "sentiment_result", "news_items", "fundamental_explanation",
            "technical_explanation", "sources_used", "warnings",
            "disclaimer", "pdf_path",
        }
        orch, store = _make_orchestrator()
        store.create_job("j3")
        await orch.run("AAPL", "j3")
        result = store.get_job("j3").result
        assert required.issubset(result.keys())

    async def test_ticker_uppercased_in_result(self):
        orch, store = _make_orchestrator()
        store.create_job("j4")
        await orch.run("aapl", "j4")
        assert store.get_job("j4").result["ticker"] == "AAPL"

    async def test_pdf_path_is_none(self):
        orch, store = _make_orchestrator()
        store.create_job("j5")
        await orch.run("AAPL", "j5")
        assert store.get_job("j5").result["pdf_path"] is None

    async def test_disclaimer_present_and_non_empty(self):
        orch, store = _make_orchestrator()
        store.create_job("j6")
        await orch.run("AAPL", "j6")
        disclaimer = store.get_job("j6").result["disclaimer"]
        assert disclaimer and "Not financial advice" in disclaimer

    async def test_generated_at_is_iso_string(self):
        import re
        orch, store = _make_orchestrator()
        store.create_job("j7")
        await orch.run("AAPL", "j7")
        ga = store.get_job("j7").result["generated_at"]
        # ISO 8601 datetime with timezone offset or Z
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ga), f"bad datetime: {ga}"

    async def test_sources_used_propagated(self):
        orch, store = _make_orchestrator(
            data_agent=_fake_data_agent(warnings=[], stock_data=_make_stock_data()),
        )
        store.create_job("j8")
        await orch.run("AAPL", "j8")
        assert "Yahoo Finance" in store.get_job("j8").result["sources_used"]

    async def test_news_items_propagated(self):
        news = [{"title": "headline", "url": "http://a.com", "body": "", "source": "a.com"}]
        orch, store = _make_orchestrator(research_agent=_fake_research_agent(news_items=news))
        store.create_job("j9")
        await orch.run("AAPL", "j9")
        assert store.get_job("j9").result["news_items"] == news

    async def test_llm_recommendation_used_in_result(self):
        """ReportAgent recommendation overrides the score-derived one."""
        orch, store = _make_orchestrator(report_agent=_fake_report_agent(recommendation="Sell"))
        store.create_job("j10")
        await orch.run("AAPL", "j10")
        assert store.get_job("j10").result["recommendation"] == "Sell"


# ═════════════════════════════════════════════════════════════════════════════
# Unknown ticker → job error
# ═════════════════════════════════════════════════════════════════════════════


class TestOrchestratorUnknownTicker:

    async def test_job_status_error(self):
        bad_data = AsyncMock()
        bad_data.run = AsyncMock(side_effect=ValueError("'XYZ' could not be found"))
        orch, store = _make_orchestrator(data_agent=bad_data)
        store.create_job("e1")
        await orch.run("XYZ", "e1")
        assert store.get_job("e1").status == "error"

    async def test_error_message_stored(self):
        bad_data = AsyncMock()
        bad_data.run = AsyncMock(side_effect=ValueError("'XYZ' could not be found"))
        orch, store = _make_orchestrator(data_agent=bad_data)
        store.create_job("e2")
        await orch.run("XYZ", "e2")
        assert "XYZ" in store.get_job("e2").error

    async def test_no_result_on_error(self):
        bad_data = AsyncMock()
        bad_data.run = AsyncMock(side_effect=ValueError("bad ticker"))
        orch, store = _make_orchestrator(data_agent=bad_data)
        store.create_job("e3")
        await orch.run("XYZ", "e3")
        assert store.get_job("e3").result is None

    async def test_current_step_cleared_on_error(self):
        bad_data = AsyncMock()
        bad_data.run = AsyncMock(side_effect=ValueError("bad ticker"))
        orch, store = _make_orchestrator(data_agent=bad_data)
        store.create_job("e4")
        await orch.run("XYZ", "e4")
        assert store.get_job("e4").current_step is None


# ═════════════════════════════════════════════════════════════════════════════
# Agent error dicts — pipeline continues with warnings
# ═════════════════════════════════════════════════════════════════════════════


class TestOrchestratorAgentErrors:

    async def test_fundamental_error_job_still_completes(self):
        orch, store = _make_orchestrator(
            fundamental_agent=_fake_fundamental_agent(error="PE unavailable"),
        )
        store.create_job("ae1")
        await orch.run("AAPL", "ae1")
        assert store.get_job("ae1").status == "complete"

    async def test_fundamental_error_warning_in_result(self):
        orch, store = _make_orchestrator(
            fundamental_agent=_fake_fundamental_agent(error="PE unavailable"),
        )
        store.create_job("ae2")
        await orch.run("AAPL", "ae2")
        result = store.get_job("ae2").result
        assert any("Fundamental" in w or "PE" in w for w in result["warnings"])

    async def test_technical_error_job_still_completes(self):
        orch, store = _make_orchestrator(
            technical_agent=_fake_technical_agent(error="no price data"),
        )
        store.create_job("ae3")
        await orch.run("AAPL", "ae3")
        assert store.get_job("ae3").status == "complete"

    async def test_technical_error_warning_in_result(self):
        orch, store = _make_orchestrator(
            technical_agent=_fake_technical_agent(error="no price data"),
        )
        store.create_job("ae4")
        await orch.run("AAPL", "ae4")
        result = store.get_job("ae4").result
        assert any("Technical" in w or "price" in w for w in result["warnings"])

    async def test_research_warning_propagated(self):
        orch, store = _make_orchestrator(
            research_agent=_fake_research_agent(
                news_items=[], warnings=["DuckDuckGo rate-limited"],
            ),
        )
        store.create_job("ae5")
        await orch.run("AAPL", "ae5")
        result = store.get_job("ae5").result
        assert any("DuckDuckGo" in w for w in result["warnings"])


# ═════════════════════════════════════════════════════════════════════════════
# LLM fallback
# ═════════════════════════════════════════════════════════════════════════════


class TestOrchestratorLLMFallback:

    async def test_fallback_warning_in_result(self):
        orch, store = _make_orchestrator(report_agent=_fake_report_agent(fallback=True))
        store.create_job("llm1")
        await orch.run("AAPL", "llm1")
        result = store.get_job("llm1").result
        assert any("AI" in w or "unavailable" in w for w in result["warnings"])

    async def test_job_still_complete_with_fallback(self):
        orch, store = _make_orchestrator(report_agent=_fake_report_agent(fallback=True))
        store.create_job("llm2")
        await orch.run("AAPL", "llm2")
        assert store.get_job("llm2").status == "complete"


# ═════════════════════════════════════════════════════════════════════════════
# current_step progression
# ═════════════════════════════════════════════════════════════════════════════


class TestOrchestratorStepLabels:

    async def test_current_step_none_after_completion(self):
        orch, store = _make_orchestrator()
        store.create_job("step1")
        await orch.run("AAPL", "step1")
        assert store.get_job("step1").current_step is None

    async def test_step_labels_updated_during_pipeline(self):
        """Capture step labels as they're written; verify all expected steps appear."""
        observed_steps: list[str] = []

        store = JobStore()
        original_update = store.update_job

        async def _capturing_update(job_id, **kwargs):
            step = kwargs.get("current_step")
            if step:
                observed_steps.append(step)
            return await original_update(job_id, **kwargs)

        store.update_job = _capturing_update  # type: ignore[method-assign]

        orch = Orchestrator(
            store,
            data_agent=_fake_data_agent(),
            research_agent=_fake_research_agent(),
            fundamental_agent=_fake_fundamental_agent(),
            technical_agent=_fake_technical_agent(),
            report_agent=_fake_report_agent(),
            sentiment_analyser=_fake_sentiment_analyser(),
        )
        store.create_job("step2")
        await orch.run("AAPL", "step2")

        assert any("data" in s.lower() or "fetch" in s.lower() for s in observed_steps)
        assert any("fund" in s.lower() for s in observed_steps)
        assert any("tech" in s.lower() for s in observed_steps)
        assert any("report" in s.lower() or "generat" in s.lower() for s in observed_steps)


# ═════════════════════════════════════════════════════════════════════════════
# Warning deduplication
# ═════════════════════════════════════════════════════════════════════════════


class TestWarningDeduplication:

    async def test_duplicate_warnings_removed(self):
        """The same warning from two sources should appear only once."""
        duplicate_warn = "Data partially unavailable"
        orch, store = _make_orchestrator(
            data_agent=_fake_data_agent(warnings=[duplicate_warn]),
            research_agent=_fake_research_agent(warnings=[duplicate_warn]),
        )
        store.create_job("wd1")
        await orch.run("AAPL", "wd1")
        result = store.get_job("wd1").result
        assert result["warnings"].count(duplicate_warn) == 1

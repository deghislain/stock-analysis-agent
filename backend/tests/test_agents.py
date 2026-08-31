"""
Unit tests for the agent layer (Sub-Task 4, Todo 10).

Covers every public surface of:
  agents/base_agent.py    — BaseAgent ABC (abstract enforcement)
  agents/data_agent.py    — DataAgent: happy path, unknown ticker, ticker normalisation,
                            sources_used + warnings forwarded
  agents/research_agent.py — ResearchAgent: happy path, empty results, network failure,
                             rate-limit error, timeout error, generic DDGS error;
                             helpers: _clean_item, _extract_domain, _classify_error
  agents/fundamental_agent.py — FundamentalAgent: happy path, analyser exception caught
  agents/technical_agent.py  — TechnicalAgent:  happy path, analyser exception caught
  agents/report_agent.py     — ReportAgent: LLM success path (all keys returned),
                               LLM unavailable → fallback template used + warning added,
                               bad JSON → fallback, invalid recommendation → reset to Hold;
                               helpers: _build_prompt (disclaimer present, ticker present,
                               all five section headers present), _parse_response (clean JSON,
                               markdown-fenced JSON, no-JSON string, invalid recommendation)
  core/llm_client.py      — LLMClient: no-key raises LLMUnavailableError immediately,
                             GroqError re-raised as LLMUnavailableError,
                             unexpected exception re-raised as LLMUnavailableError,
                             successful call returns content string
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Shared test fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_stock_data(price_history=None, sources_used=None, warnings=None):
    """Return a minimal StockData for use in tests."""
    from app.data.base_source import StockData
    return StockData(
        source_name="Yahoo Finance",
        price_history=price_history,
        company_info={},
        financials={},
        warnings=warnings or [],
    )


def _make_fallback_result(stock_data=None, sources_used=None, warnings=None):
    """Return a FallbackResult with sensible defaults."""
    from app.data.source_registry import FallbackResult
    return FallbackResult(
        stock_data=stock_data or _make_stock_data(price_history=_make_df()),
        sources_used=sources_used if sources_used is not None else ["Yahoo Finance"],
        warnings=warnings or [],
    )


def _make_df(rows: int = 10):
    """Return a small synthetic OHLCV DataFrame."""
    import numpy as np
    import pandas as pd
    dates  = pd.date_range("2024-01-01", periods=rows, freq="B")
    prices = np.linspace(100.0, 110.0, rows)
    return pd.DataFrame(
        {"Open": prices, "High": prices, "Low": prices,
         "Close": prices, "Volume": 1_000_000},
        index=dates,
    )


def _make_fundamental_result(score: float = 60.0):
    from app.schemas.analysis import FundamentalMetric, FundamentalResult
    m = FundamentalMetric(label="X", value=None)
    return FundamentalResult(
        ticker="AAPL", pe_ratio=m, eps=m, pb_ratio=m,
        debt_to_equity=m, profit_margin=m, revenue_growth=m,
        dividend_yield=m, score=score, warnings=[],
    )


def _make_technical_result(score: float = 55.0):
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


def _make_sentiment_result(score: float = 50.0):
    from app.schemas.analysis import SentimentResult
    return SentimentResult(
        ticker="AAPL", positive_count=0, neutral_count=1, negative_count=0,
        score=score, label="Neutral", headlines_analysed=1,
    )


def _make_analysis_result(ticker: str = "AAPL"):
    """Build a complete AnalysisResult for ReportAgent tests."""
    from app.schemas.analysis import AnalysisResult
    return AnalysisResult(
        ticker=ticker,
        fundamental=_make_fundamental_result(),
        technical=_make_technical_result(),
        sentiment=_make_sentiment_result(),
        overall_score=57.0,
        recommendation="Hold",
    )


# ═════════════════════════════════════════════════════════════════════════════
# BaseAgent — ABC enforcement
# ═════════════════════════════════════════════════════════════════════════════


class TestBaseAgent:

    def test_cannot_instantiate_directly(self):
        """BaseAgent is abstract — direct instantiation must raise TypeError."""
        from app.agents.base_agent import BaseAgent
        with pytest.raises(TypeError):
            BaseAgent()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_name(self):
        """Subclass missing ``name`` raises TypeError."""
        from app.agents.base_agent import BaseAgent
        class NoName(BaseAgent):
            async def run(self, **kwargs) -> dict:
                return {}
        with pytest.raises(TypeError):
            NoName()

    def test_concrete_subclass_must_implement_run(self):
        """Subclass missing ``run`` raises TypeError."""
        from app.agents.base_agent import BaseAgent
        class NoRun(BaseAgent):
            @property
            def name(self) -> str:
                return "NoRun"
        with pytest.raises(TypeError):
            NoRun()

    def test_valid_subclass_instantiates(self):
        """A fully-implemented subclass can be instantiated."""
        from app.agents.base_agent import BaseAgent
        class Good(BaseAgent):
            @property
            def name(self) -> str:
                return "Good"
            async def run(self, **kwargs) -> dict:
                return {"status": "ok"}
        assert Good().name == "Good"


# ═════════════════════════════════════════════════════════════════════════════
# DataAgent
# ═════════════════════════════════════════════════════════════════════════════


class TestDataAgentHappyPath:

    def _make_registry(self, result):
        reg = MagicMock()
        reg.get_data_with_fallback.return_value = result
        return reg

    async def test_status_ok(self):
        from app.agents.data_agent import DataAgent
        reg = self._make_registry(_make_fallback_result())
        result = await DataAgent(registry=reg).run(ticker="AAPL")
        assert result["status"] == "ok"

    async def test_stock_data_returned(self):
        from app.agents.data_agent import DataAgent
        sd = _make_stock_data(price_history=_make_df())
        reg = self._make_registry(_make_fallback_result(stock_data=sd))
        result = await DataAgent(registry=reg).run(ticker="AAPL")
        assert result["stock_data"] is sd

    async def test_sources_used_forwarded(self):
        from app.agents.data_agent import DataAgent
        reg = self._make_registry(
            _make_fallback_result(sources_used=["Yahoo Finance", "Stooq"])
        )
        result = await DataAgent(registry=reg).run(ticker="AAPL")
        assert result["sources_used"] == ["Yahoo Finance", "Stooq"]

    async def test_warnings_forwarded(self):
        from app.agents.data_agent import DataAgent
        reg = self._make_registry(
            _make_fallback_result(warnings=["Some data missing"])
        )
        result = await DataAgent(registry=reg).run(ticker="AAPL")
        assert "Some data missing" in result["warnings"]

    async def test_ticker_uppercased(self):
        from app.agents.data_agent import DataAgent
        reg = self._make_registry(_make_fallback_result())
        await DataAgent(registry=reg).run(ticker="aapl")
        reg.get_data_with_fallback.assert_called_once_with("AAPL")

    async def test_name_property(self):
        from app.agents.data_agent import DataAgent
        assert DataAgent.__new__(DataAgent).name == "DataAgent" or True
        # Just confirm the class has the right name attribute
        reg = self._make_registry(_make_fallback_result())
        agent = DataAgent(registry=reg)
        assert agent.name == "DataAgent"


class TestDataAgentUnknownTicker:
    """Unknown ticker: price_history=None AND sources_used=[] → raises ValueError."""

    def _make_empty_registry(self):
        from app.data.base_source import StockData
        sd = StockData(source_name="", price_history=None, company_info={}, financials={})
        from app.data.source_registry import FallbackResult
        fr = FallbackResult(stock_data=sd, sources_used=[], warnings=[])
        reg = MagicMock()
        reg.get_data_with_fallback.return_value = fr
        return reg

    async def test_raises_value_error(self):
        from app.agents.data_agent import DataAgent
        with pytest.raises(ValueError, match="could not be found"):
            await DataAgent(registry=self._make_empty_registry()).run(ticker="XXXX")

    async def test_error_message_contains_ticker(self):
        from app.agents.data_agent import DataAgent
        with pytest.raises(ValueError) as exc_info:
            await DataAgent(registry=self._make_empty_registry()).run(ticker="ZZZZ")
        assert "ZZZZ" in str(exc_info.value)

    async def test_price_none_but_sources_present_does_not_raise(self):
        """price_history=None is OK as long as at least one source contributed."""
        from app.agents.data_agent import DataAgent
        from app.data.base_source import StockData
        from app.data.source_registry import FallbackResult
        sd = StockData(source_name="FMP", price_history=None, company_info={"a": 1}, financials={})
        fr = FallbackResult(stock_data=sd, sources_used=["FMP"], warnings=[])
        reg = MagicMock()
        reg.get_data_with_fallback.return_value = fr
        result = await DataAgent(registry=reg).run(ticker="AAPL")
        assert result["status"] == "ok"


# ═════════════════════════════════════════════════════════════════════════════
# ResearchAgent
# ═════════════════════════════════════════════════════════════════════════════


class TestResearchAgentHappyPath:

    def _mock_ddgs(self, raw_results):
        """Patch DDGS().text() to return ``raw_results``."""
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = raw_results
        return mock_ddgs_instance

    async def test_status_always_ok(self):
        from app.agents.research_agent import ResearchAgent
        raw = [{"title": "AAPL up", "href": "https://reuters.com/a", "body": "Up 2%"}]
        with patch("app.agents.research_agent.DDGS", return_value=self._mock_ddgs(raw)):
            result = await ResearchAgent().run(ticker="AAPL")
        assert result["status"] == "ok"

    async def test_news_items_returned(self):
        from app.agents.research_agent import ResearchAgent
        raw = [{"title": "AAPL up", "href": "https://reuters.com/a", "body": "Up 2%"}]
        with patch("app.agents.research_agent.DDGS", return_value=self._mock_ddgs(raw)):
            result = await ResearchAgent().run(ticker="AAPL")
        assert len(result["news_items"]) == 1

    async def test_news_item_keys(self):
        from app.agents.research_agent import ResearchAgent
        raw = [{"title": "AAPL up", "href": "https://reuters.com/a", "body": "Gains"}]
        with patch("app.agents.research_agent.DDGS", return_value=self._mock_ddgs(raw)):
            result = await ResearchAgent().run(ticker="AAPL")
        item = result["news_items"][0]
        # date is now required by the NewsItem schema (Sub-Task 5)
        assert {"title", "url", "date", "body", "source"} == set(item.keys())

    async def test_date_field_populated_when_provided(self):
        from app.agents.research_agent import ResearchAgent
        raw = [{"title": "T", "href": "http://x.com", "body": "B", "date": "2024-06-01"}]
        with patch("app.agents.research_agent.DDGS", return_value=self._mock_ddgs(raw)):
            result = await ResearchAgent().run(ticker="AAPL")
        assert result["news_items"][0]["date"] == "2024-06-01"

    async def test_date_field_empty_string_when_absent(self):
        from app.agents.research_agent import ResearchAgent
        raw = [{"title": "T", "href": "http://x.com", "body": "B"}]
        with patch("app.agents.research_agent.DDGS", return_value=self._mock_ddgs(raw)):
            result = await ResearchAgent().run(ticker="AAPL")
        assert result["news_items"][0]["date"] == ""

    async def test_href_mapped_to_url(self):
        from app.agents.research_agent import ResearchAgent
        raw = [{"title": "T", "href": "https://example.com/story", "body": "B"}]
        with patch("app.agents.research_agent.DDGS", return_value=self._mock_ddgs(raw)):
            result = await ResearchAgent().run(ticker="AAPL")
        assert result["news_items"][0]["url"] == "https://example.com/story"

    async def test_source_extracted_from_url(self):
        from app.agents.research_agent import ResearchAgent
        raw = [{"title": "T", "href": "https://www.reuters.com/story", "body": "B"}]
        with patch("app.agents.research_agent.DDGS", return_value=self._mock_ddgs(raw)):
            result = await ResearchAgent().run(ticker="AAPL")
        assert result["news_items"][0]["source"] == "reuters.com"

    async def test_no_warnings_on_success(self):
        from app.agents.research_agent import ResearchAgent
        raw = [{"title": "T", "href": "http://x.com", "body": "B"}]
        with patch("app.agents.research_agent.DDGS", return_value=self._mock_ddgs(raw)):
            result = await ResearchAgent().run(ticker="AAPL")
        assert result["warnings"] == []

    async def test_ticker_uppercased_in_query(self):
        from app.agents.research_agent import ResearchAgent
        mock = self._mock_ddgs([])
        with patch("app.agents.research_agent.DDGS", return_value=mock):
            await ResearchAgent().run(ticker="aapl")
        call_args = mock.text.call_args
        assert "AAPL" in call_args[0][0]

    async def test_items_without_title_and_body_discarded(self):
        from app.agents.research_agent import ResearchAgent
        raw = [
            {"title": "", "href": "http://x.com", "body": ""},  # discarded
            {"title": "Valid", "href": "http://y.com", "body": "Body"},  # kept
        ]
        with patch("app.agents.research_agent.DDGS", return_value=self._mock_ddgs(raw)):
            result = await ResearchAgent().run(ticker="AAPL")
        assert len(result["news_items"]) == 1
        assert result["news_items"][0]["title"] == "Valid"


class TestResearchAgentEmptyResults:

    async def test_empty_results_adds_warning(self):
        from app.agents.research_agent import ResearchAgent
        mock = MagicMock()
        mock.text.return_value = []
        with patch("app.agents.research_agent.DDGS", return_value=mock):
            result = await ResearchAgent().run(ticker="AAPL")
        assert len(result["warnings"]) == 1
        assert "AAPL" in result["warnings"][0]

    async def test_empty_results_status_still_ok(self):
        from app.agents.research_agent import ResearchAgent
        mock = MagicMock()
        mock.text.return_value = []
        with patch("app.agents.research_agent.DDGS", return_value=mock):
            result = await ResearchAgent().run(ticker="AAPL")
        assert result["status"] == "ok"


class TestResearchAgentNetworkFailure:

    async def test_generic_exception_caught(self):
        from app.agents.research_agent import ResearchAgent
        mock = MagicMock()
        mock.text.side_effect = ConnectionError("network down")
        with patch("app.agents.research_agent.DDGS", return_value=mock):
            result = await ResearchAgent().run(ticker="AAPL")
        assert result["status"] == "ok"
        assert result["news_items"] == []
        assert len(result["warnings"]) == 1

    async def test_ratelimit_warning_message(self):
        from app.agents.research_agent import ResearchAgent

        class RatelimitException(Exception):
            pass

        mock = MagicMock()
        mock.text.side_effect = RatelimitException("too many requests")
        with patch("app.agents.research_agent.DDGS", return_value=mock):
            result = await ResearchAgent().run(ticker="TSLA")
        assert any("rate-limit" in w.lower() or "ratelimit" in w.lower()
                   for w in result["warnings"])

    async def test_timeout_warning_message(self):
        from app.agents.research_agent import ResearchAgent

        class TimeoutException(Exception):
            pass

        mock = MagicMock()
        mock.text.side_effect = TimeoutException("timed out")
        with patch("app.agents.research_agent.DDGS", return_value=mock):
            result = await ResearchAgent().run(ticker="MSFT")
        assert any("timed out" in w.lower() or "timeout" in w.lower()
                   for w in result["warnings"])


# ── _clean_item ───────────────────────────────────────────────────────────────


class TestCleanItem:

    def test_maps_href_to_url(self):
        from app.agents.research_agent import _clean_item
        item = _clean_item({"title": "T", "href": "http://x.com", "body": "B"})
        assert item["url"] == "http://x.com"

    def test_no_title_and_no_body_returns_empty_dict(self):
        from app.agents.research_agent import _clean_item
        assert _clean_item({"href": "http://x.com"}) == {}

    def test_title_only_is_kept(self):
        from app.agents.research_agent import _clean_item
        item = _clean_item({"title": "Headline", "href": "", "body": ""})
        assert item["title"] == "Headline"

    def test_body_only_is_kept(self):
        from app.agents.research_agent import _clean_item
        item = _clean_item({"title": "", "href": "", "body": "Some text"})
        assert item["body"] == "Some text"

    def test_whitespace_stripped(self):
        from app.agents.research_agent import _clean_item
        item = _clean_item({"title": "  Hello  ", "href": "", "body": ""})
        assert item["title"] == "Hello"

    def test_date_field_present_in_output(self):
        from app.agents.research_agent import _clean_item
        item = _clean_item({"title": "T", "href": "", "body": "", "date": "2024-03-15"})
        assert "date" in item
        assert item["date"] == "2024-03-15"

    def test_date_field_empty_when_absent(self):
        from app.agents.research_agent import _clean_item
        item = _clean_item({"title": "T", "href": "", "body": ""})
        assert item["date"] == ""


# ── _normalise_date ───────────────────────────────────────────────────────────


class TestNormaliseDate:

    def test_iso_date_unchanged(self):
        from app.agents.research_agent import _normalise_date
        assert _normalise_date("2024-06-15") == "2024-06-15"

    def test_iso_datetime_truncated_to_date(self):
        from app.agents.research_agent import _normalise_date
        assert _normalise_date("2024-06-15T10:30:00") == "2024-06-15"

    def test_long_month_format_parsed(self):
        from app.agents.research_agent import _normalise_date
        assert _normalise_date("June 15, 2024") == "2024-06-15"

    def test_short_month_format_parsed(self):
        from app.agents.research_agent import _normalise_date
        assert _normalise_date("Jun 15, 2024") == "2024-06-15"

    def test_empty_string_returns_empty(self):
        from app.agents.research_agent import _normalise_date
        assert _normalise_date("") == ""

    def test_whitespace_only_returns_empty(self):
        from app.agents.research_agent import _normalise_date
        assert _normalise_date("   ") == ""

    def test_unrecognised_format_returned_as_is_when_short(self):
        from app.agents.research_agent import _normalise_date
        # A short unrecognised string is passed through as-is.
        result = _normalise_date("yesterday")
        assert result == "yesterday"

    def test_very_long_unrecognised_value_returns_empty(self):
        from app.agents.research_agent import _normalise_date
        # A long unrecognised string is discarded.
        assert _normalise_date("this is not a date at all, it is very long text") == ""


# ── _extract_domain ───────────────────────────────────────────────────────────


class TestExtractDomain:

    def test_www_prefix_stripped(self):
        from app.agents.research_agent import _extract_domain
        assert _extract_domain("https://www.reuters.com/article") == "reuters.com"

    def test_bare_domain(self):
        from app.agents.research_agent import _extract_domain
        assert _extract_domain("https://bloomberg.com/news") == "bloomberg.com"

    def test_empty_url_returns_empty_string(self):
        from app.agents.research_agent import _extract_domain
        assert _extract_domain("") == ""

    def test_subdomain_preserved(self):
        from app.agents.research_agent import _extract_domain
        assert _extract_domain("https://finance.yahoo.com/q?s=AAPL") == "finance.yahoo.com"


# ── _classify_error ───────────────────────────────────────────────────────────


class TestClassifyError:

    def test_ratelimit_error(self):
        from app.agents.research_agent import _classify_error

        class RatelimitException(Exception):
            pass

        msg = _classify_error(RatelimitException("x"), "AAPL")
        assert "rate-limit" in msg.lower() or "ratelimit" in msg.lower()
        assert "AAPL" in msg

    def test_timeout_error(self):
        from app.agents.research_agent import _classify_error

        class TimeoutException(Exception):
            pass

        msg = _classify_error(TimeoutException("x"), "TSLA")
        assert "timed out" in msg.lower() or "timeout" in msg.lower()
        assert "TSLA" in msg

    def test_generic_error(self):
        from app.agents.research_agent import _classify_error
        msg = _classify_error(RuntimeError("boom"), "MSFT")
        assert "MSFT" in msg
        assert "RuntimeError" in msg


# ═════════════════════════════════════════════════════════════════════════════
# FundamentalAgent
# ═════════════════════════════════════════════════════════════════════════════


class TestFundamentalAgent:

    async def test_happy_path_status_ok(self):
        from app.agents.fundamental_agent import FundamentalAgent
        analyser = MagicMock()
        analyser.analyse.return_value = _make_fundamental_result()
        result = await FundamentalAgent(analyser=analyser).run(
            ticker="AAPL", stock_data=_make_stock_data()
        )
        assert result["status"] == "ok"

    async def test_fundamental_result_in_dict(self):
        from app.agents.fundamental_agent import FundamentalAgent
        fr = _make_fundamental_result(score=72.0)
        analyser = MagicMock()
        analyser.analyse.return_value = fr
        result = await FundamentalAgent(analyser=analyser).run(
            ticker="AAPL", stock_data=_make_stock_data()
        )
        assert result["fundamental_result"] is fr

    async def test_ticker_forwarded_to_analyser(self):
        from app.agents.fundamental_agent import FundamentalAgent
        analyser = MagicMock()
        analyser.analyse.return_value = _make_fundamental_result()
        await FundamentalAgent(analyser=analyser).run(
            ticker="TSLA", stock_data=_make_stock_data()
        )
        call_ticker = analyser.analyse.call_args[0][0]
        assert call_ticker == "TSLA"

    async def test_analyser_exception_returns_error_dict(self):
        from app.agents.fundamental_agent import FundamentalAgent
        analyser = MagicMock()
        analyser.analyse.side_effect = RuntimeError("parse error")
        result = await FundamentalAgent(analyser=analyser).run(
            ticker="AAPL", stock_data=_make_stock_data()
        )
        assert result["status"] == "error"
        assert "parse error" in result["error"]

    async def test_name_property(self):
        from app.agents.fundamental_agent import FundamentalAgent
        analyser = MagicMock()
        analyser.analyse.return_value = _make_fundamental_result()
        assert FundamentalAgent(analyser=analyser).name == "FundamentalAgent"


# ═════════════════════════════════════════════════════════════════════════════
# TechnicalAgent
# ═════════════════════════════════════════════════════════════════════════════


class TestTechnicalAgent:

    async def test_happy_path_status_ok(self):
        from app.agents.technical_agent import TechnicalAgent
        analyser = MagicMock()
        analyser.analyse.return_value = _make_technical_result()
        result = await TechnicalAgent(analyser=analyser).run(
            ticker="AAPL", stock_data=_make_stock_data()
        )
        assert result["status"] == "ok"

    async def test_technical_result_in_dict(self):
        from app.agents.technical_agent import TechnicalAgent
        tr = _make_technical_result(score=42.0)
        analyser = MagicMock()
        analyser.analyse.return_value = tr
        result = await TechnicalAgent(analyser=analyser).run(
            ticker="AAPL", stock_data=_make_stock_data()
        )
        assert result["technical_result"] is tr

    async def test_ticker_forwarded_to_analyser(self):
        from app.agents.technical_agent import TechnicalAgent
        analyser = MagicMock()
        analyser.analyse.return_value = _make_technical_result()
        await TechnicalAgent(analyser=analyser).run(
            ticker="MSFT", stock_data=_make_stock_data()
        )
        call_ticker = analyser.analyse.call_args[0][0]
        assert call_ticker == "MSFT"

    async def test_analyser_exception_returns_error_dict(self):
        from app.agents.technical_agent import TechnicalAgent
        analyser = MagicMock()
        analyser.analyse.side_effect = RuntimeError("ta crash")
        result = await TechnicalAgent(analyser=analyser).run(
            ticker="AAPL", stock_data=_make_stock_data()
        )
        assert result["status"] == "error"
        assert "ta crash" in result["error"]

    async def test_name_property(self):
        from app.agents.technical_agent import TechnicalAgent
        analyser = MagicMock()
        analyser.analyse.return_value = _make_technical_result()
        assert TechnicalAgent(analyser=analyser).name == "TechnicalAgent"


# ═════════════════════════════════════════════════════════════════════════════
# ReportAgent
# ═════════════════════════════════════════════════════════════════════════════


class TestReportAgentLLMSuccess:

    def _llm_response(self, rec: str = "Buy") -> str:
        return json.dumps({
            "executive_summary": "This is a strong stock.",
            "recommendation": rec,
            "rationale": "Sentence one. Sentence two. Sentence three.",
            "fundamental_explanation": "Fundamentals are solid.",
            "technical_explanation": "Technicals are bullish.",
        })

    async def test_status_always_ok(self):
        from app.agents.report_agent import ReportAgent
        llm = AsyncMock()
        llm.generate = AsyncMock(return_value=self._llm_response())
        result = await ReportAgent(llm_client=llm).run(
            analysis_result=_make_analysis_result()
        )
        assert result["status"] == "ok"

    async def test_all_keys_present(self):
        from app.agents.report_agent import ReportAgent
        llm = AsyncMock()
        llm.generate = AsyncMock(return_value=self._llm_response())
        result = await ReportAgent(llm_client=llm).run(
            analysis_result=_make_analysis_result()
        )
        required = {
            "status", "executive_summary", "recommendation",
            "rationale", "fundamental_explanation",
            "technical_explanation", "warnings",
        }
        assert required.issubset(result.keys())

    async def test_recommendation_forwarded(self):
        from app.agents.report_agent import ReportAgent
        llm = AsyncMock()
        llm.generate = AsyncMock(return_value=self._llm_response(rec="Sell"))
        result = await ReportAgent(llm_client=llm).run(
            analysis_result=_make_analysis_result()
        )
        assert result["recommendation"] == "Sell"

    async def test_no_warnings_on_success(self):
        from app.agents.report_agent import ReportAgent
        llm = AsyncMock()
        llm.generate = AsyncMock(return_value=self._llm_response())
        result = await ReportAgent(llm_client=llm).run(
            analysis_result=_make_analysis_result()
        )
        assert result["warnings"] == []

    async def test_name_property(self):
        from app.agents.report_agent import ReportAgent
        assert ReportAgent(llm_client=AsyncMock()).name == "ReportAgent"


class TestReportAgentLLMFallback:

    async def test_fallback_on_llm_exception(self):
        from app.agents.report_agent import ReportAgent, GROQ_FALLBACK_TEMPLATE
        llm = AsyncMock()
        llm.generate = AsyncMock(side_effect=Exception("no key"))
        result = await ReportAgent(llm_client=llm).run(
            analysis_result=_make_analysis_result()
        )
        assert result["recommendation"] == GROQ_FALLBACK_TEMPLATE["recommendation"]

    async def test_fallback_warning_added(self):
        from app.agents.report_agent import ReportAgent
        llm = AsyncMock()
        llm.generate = AsyncMock(side_effect=Exception("unavailable"))
        result = await ReportAgent(llm_client=llm).run(
            analysis_result=_make_analysis_result()
        )
        assert len(result["warnings"]) == 1
        assert "unavailable" in result["warnings"][0].lower()

    async def test_status_still_ok_on_fallback(self):
        from app.agents.report_agent import ReportAgent
        llm = AsyncMock()
        llm.generate = AsyncMock(side_effect=RuntimeError("boom"))
        result = await ReportAgent(llm_client=llm).run(
            analysis_result=_make_analysis_result()
        )
        assert result["status"] == "ok"

    async def test_fallback_on_bad_json(self):
        from app.agents.report_agent import ReportAgent, GROQ_FALLBACK_TEMPLATE
        llm = AsyncMock()
        llm.generate = AsyncMock(return_value="not json at all")
        result = await ReportAgent(llm_client=llm).run(
            analysis_result=_make_analysis_result()
        )
        assert result["recommendation"] == GROQ_FALLBACK_TEMPLATE["recommendation"]
        assert len(result["warnings"]) == 1


# ── _build_prompt ─────────────────────────────────────────────────────────────


class TestBuildPrompt:

    def _prompt(self):
        from app.agents.report_agent import _build_prompt
        return _build_prompt(_make_analysis_result("NVDA"))

    def test_ticker_in_prompt(self):
        assert "NVDA" in self._prompt()

    def test_disclaimer_in_prompt(self):
        p = self._prompt()
        assert "Not financial advice" in p

    def test_fundamental_section_header(self):
        assert "FUNDAMENTAL DATA" in self._prompt()

    def test_technical_section_header(self):
        assert "TECHNICAL DATA" in self._prompt()

    def test_sentiment_section_header(self):
        assert "SENTIMENT DATA" in self._prompt()

    def test_response_format_section(self):
        assert "RESPONSE FORMAT" in self._prompt()

    def test_all_five_json_keys_mentioned(self):
        p = self._prompt()
        for key in ("executive_summary", "recommendation", "rationale",
                    "fundamental_explanation", "technical_explanation"):
            assert key in p

    def test_buy_hold_sell_listed(self):
        p = self._prompt()
        assert "Buy" in p and "Hold" in p and "Sell" in p


# ── _parse_response ───────────────────────────────────────────────────────────


class TestParseResponse:

    def _valid_json(self, rec: str = "Buy") -> str:
        return json.dumps({
            "executive_summary": "Summary.",
            "recommendation": rec,
            "rationale": "R1. R2. R3.",
            "fundamental_explanation": "F.",
            "technical_explanation": "T.",
        })

    def test_clean_json_parsed(self):
        from app.agents.report_agent import _parse_response
        result = _parse_response(self._valid_json("Hold"))
        assert result["recommendation"] == "Hold"

    def test_markdown_fenced_json_parsed(self):
        from app.agents.report_agent import _parse_response
        fenced = f"```json\n{self._valid_json('Buy')}\n```"
        result = _parse_response(fenced)
        assert result["recommendation"] == "Buy"

    def test_preamble_text_ignored(self):
        from app.agents.report_agent import _parse_response
        with_preamble = "Here is your analysis:\n" + self._valid_json("Sell")
        result = _parse_response(with_preamble)
        assert result["recommendation"] == "Sell"

    def test_no_json_raises_value_error(self):
        from app.agents.report_agent import _parse_response
        with pytest.raises(ValueError, match="No JSON object found"):
            _parse_response("This has no JSON at all.")

    def test_invalid_recommendation_reset_to_hold(self):
        from app.agents.report_agent import _parse_response
        bad = json.dumps({
            "executive_summary": "",
            "recommendation": "STRONG BUY",
            "rationale": "",
            "fundamental_explanation": "",
            "technical_explanation": "",
        })
        result = _parse_response(bad)
        assert result["recommendation"] == "Hold"

    def test_valid_buy_accepted(self):
        from app.agents.report_agent import _parse_response
        assert _parse_response(self._valid_json("Buy"))["recommendation"] == "Buy"

    def test_valid_sell_accepted(self):
        from app.agents.report_agent import _parse_response
        assert _parse_response(self._valid_json("Sell"))["recommendation"] == "Sell"


# ═════════════════════════════════════════════════════════════════════════════
# LLMClient
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMClientNoKey:

    async def test_empty_key_raises_llm_unavailable(self):
        from app.core.llm_client import LLMClient, LLMUnavailableError
        client = LLMClient(api_key="", model="llama3-8b-8192")
        with pytest.raises(LLMUnavailableError, match="GROQ_API_KEY"):
            await client.generate("Hello")

    async def test_none_key_falls_back_to_settings_empty(self):
        """When settings.groq_api_key is '' (default), no-key error fires."""
        from app.core.llm_client import LLMClient, LLMUnavailableError
        with patch("app.core.llm_client.settings") as mock_settings:
            mock_settings.groq_api_key = ""
            mock_settings.groq_model   = "llama3-8b-8192"
            client = LLMClient()
            with pytest.raises(LLMUnavailableError):
                await client.generate("Hello")


class TestLLMClientGroqError:

    async def test_groq_error_reraised_as_llm_unavailable(self):
        from app.core.llm_client import LLMClient, LLMUnavailableError

        # Use the GroqError stub registered in conftest.
        class FakeGroqError(Exception):
            pass

        mock_groq_instance = AsyncMock()
        mock_groq_instance.chat.completions.create.side_effect = FakeGroqError("auth failed")

        with patch("app.core.llm_client.GroqError", FakeGroqError), \
             patch("app.core.llm_client.AsyncGroq", return_value=mock_groq_instance):
            client = LLMClient(api_key="fake-key", model="llama3-8b-8192")
            with pytest.raises(LLMUnavailableError):
                await client.generate("Hello")

    async def test_network_error_reraised_as_llm_unavailable(self):
        from app.core.llm_client import LLMClient, LLMUnavailableError

        mock_groq_instance = AsyncMock()
        mock_groq_instance.chat.completions.create.side_effect = OSError("connection reset")

        with patch("app.core.llm_client.GroqError", Exception), \
             patch("app.core.llm_client.AsyncGroq", return_value=mock_groq_instance):
            client = LLMClient(api_key="fake-key", model="llama3-8b-8192")
            with pytest.raises(LLMUnavailableError):
                await client.generate("Hello")


class TestLLMClientSuccess:

    async def test_successful_call_returns_content(self):
        from app.core.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"recommendation": "Buy"}'

        mock_groq_instance = AsyncMock()
        mock_groq_instance.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("app.core.llm_client.GroqError", Exception), \
             patch("app.core.llm_client.AsyncGroq", return_value=mock_groq_instance):
            client = LLMClient(api_key="real-key", model="llama3-8b-8192")
            content = await client.generate("Analyse AAPL")

        assert content == '{"recommendation": "Buy"}'

    async def test_none_content_returns_empty_string(self):
        from app.core.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.choices[0].message.content = None

        mock_groq_instance = AsyncMock()
        mock_groq_instance.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("app.core.llm_client.GroqError", Exception), \
             patch("app.core.llm_client.AsyncGroq", return_value=mock_groq_instance):
            client = LLMClient(api_key="real-key", model="llama3-8b-8192")
            content = await client.generate("Hello")

        assert content == ""

    async def test_correct_model_sent_in_request(self):
        from app.core.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "ok"

        mock_groq_instance = AsyncMock()
        mock_groq_instance.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("app.core.llm_client.GroqError", Exception), \
             patch("app.core.llm_client.AsyncGroq", return_value=mock_groq_instance):
            client = LLMClient(api_key="key", model="mixtral-8x7b-32768")
            await client.generate("prompt")

        call_kwargs = mock_groq_instance.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "mixtral-8x7b-32768"


# ═════════════════════════════════════════════════════════════════════════════
# Coverage gap fill-ins
# ═════════════════════════════════════════════════════════════════════════════


# ── report_agent.py:115-116 — lazy LLMClient instantiation ───────────────────

class TestReportAgentLazyLLMInit:
    """ReportAgent with llm_client=None instantiates LLMClient on first call."""

    async def test_lazy_init_runs_and_uses_llm_client(self):
        """
        When ReportAgent is constructed with no llm_client, it imports and
        creates LLMClient on the first run() call.  We stub LLMClient so the
        real Groq SDK is never touched.
        """
        import json as _json
        from unittest.mock import patch, AsyncMock, MagicMock

        fake_response = _json.dumps({
            "executive_summary": "Auto-init worked.",
            "recommendation": "Hold",
            "rationale": "One. Two. Three.",
            "fundamental_explanation": "F.",
            "technical_explanation": "T.",
        })

        fake_client_instance = AsyncMock()
        fake_client_instance.generate = AsyncMock(return_value=fake_response)

        fake_llm_class = MagicMock(return_value=fake_client_instance)

        from app.agents.report_agent import ReportAgent
        # Construct with no llm_client — triggers the lazy branch.
        agent = ReportAgent(llm_client=None)

        with patch("app.core.llm_client.LLMClient", fake_llm_class):
            # Force the lazy branch by ensuring _llm_client is None.
            agent._llm_client = None
            result = await agent.run(analysis_result=_make_analysis_result())

        assert result["status"] == "ok"
        assert result["recommendation"] == "Hold"
        fake_llm_class.assert_called_once()


# ── report_agent.py:169 — _fmt() with a non-None value ───────────────────────

class TestBuildPromptNonNullMetrics:
    """_build_prompt formats non-None metric values with their units."""

    def test_non_null_pe_ratio_formatted_in_prompt(self):
        """When pe_ratio.value is set, the prompt must show the value+unit, not 'N/A'."""
        from app.agents.report_agent import _build_prompt
        from app.schemas.analysis import (
            AnalysisResult, FundamentalMetric, FundamentalResult,
            IndicatorSeries, TechnicalResult, SentimentResult,
        )
        # Build a FundamentalResult with a real pe_ratio value.
        m_none = FundamentalMetric(label="X", value=None)
        m_pe   = FundamentalMetric(label="P/E", value=28.5, unit="x")
        fund = FundamentalResult(
            ticker="AAPL", pe_ratio=m_pe, eps=m_none, pb_ratio=m_none,
            debt_to_equity=m_none, profit_margin=m_none,
            revenue_growth=m_none, dividend_yield=m_none, score=60.0,
        )
        empty = IndicatorSeries(name="", values=[])
        tech = TechnicalResult(
            ticker="AAPL", dates=[], close_prices=[],
            sma_20=empty, sma_50=empty, sma_200=empty,
            ema_12=empty, ema_26=empty, rsi_14=empty,
            macd=empty, macd_signal=empty, macd_histogram=empty,
            bb_upper=empty, bb_middle=empty, bb_lower=empty,
            score=55.0,
        )
        sent = SentimentResult(
            ticker="AAPL", positive_count=0, neutral_count=1, negative_count=0,
            score=50.0, label="Neutral", headlines_analysed=1,
        )
        ar = AnalysisResult(
            ticker="AAPL", fundamental=fund, technical=tech,
            sentiment=sent, overall_score=57.0, recommendation="Hold",
        )
        prompt = _build_prompt(ar)
        # The non-None pe_ratio must appear as "28.5x", not "N/A".
        assert "28.5x" in prompt
        assert "N/A" not in prompt.split("P/E ratio:")[1].split("\n")[0]


# ── research_agent.py:62 — ResearchAgent.name property ───────────────────────

class TestResearchAgentNameProperty:

    def test_name_returns_research_agent(self):
        from app.agents.research_agent import ResearchAgent
        assert ResearchAgent().name == "ResearchAgent"


# ── research_agent.py:186-187 — _extract_domain except branch ────────────────

class TestExtractDomainExceptionBranch:

    def test_unparseable_url_returns_empty_string(self):
        """
        Force urlparse to raise so the except branch on line 186-187 is hit.
        urlparse itself never raises on a string, but patching it allows us
        to exercise the guard.
        """
        from unittest.mock import patch
        from app.agents.research_agent import _extract_domain
        with patch("app.agents.research_agent.urlparse", side_effect=ValueError("bad")):
            result = _extract_domain("http://anything.com")
        assert result == ""


# ── llm_client.py:129-134 — bare except Exception branch ─────────────────────

class TestLLMClientBareExceptionBranch:
    """
    The ``except Exception`` block (lines 129-134) is only reachable when the
    raised exception is NOT an instance of ``GroqError``.  The earlier
    ``except GroqError`` guard must be patched to a *different* class so that
    an OSError bypasses it and falls through to the bare ``except``.
    """

    async def test_non_groq_exception_hits_bare_except_branch(self):
        from unittest.mock import AsyncMock, patch
        from app.core.llm_client import LLMClient, LLMUnavailableError

        # Make GroqError something that OSError is NOT a subclass of,
        # so the first except doesn't catch it and the bare except does.
        class UnrelatedGroqError(Exception):
            pass

        mock_groq_instance = AsyncMock()
        mock_groq_instance.chat.completions.create.side_effect = OSError("reset by peer")

        with patch("app.core.llm_client.GroqError", UnrelatedGroqError), \
             patch("app.core.llm_client.AsyncGroq", return_value=mock_groq_instance):
            client = LLMClient(api_key="valid-key", model="llama3-8b-8192")
            with pytest.raises(LLMUnavailableError, match="reset by peer"):
                await client.generate("hello")

    async def test_bare_except_chains_original_exception(self):
        """The LLMUnavailableError raised from the bare except must chain __cause__."""
        from unittest.mock import AsyncMock, patch
        from app.core.llm_client import LLMClient, LLMUnavailableError

        class UnrelatedGroqError(Exception):
            pass

        original_error = OSError("timed out")
        mock_groq_instance = AsyncMock()
        mock_groq_instance.chat.completions.create.side_effect = original_error

        with patch("app.core.llm_client.GroqError", UnrelatedGroqError), \
             patch("app.core.llm_client.AsyncGroq", return_value=mock_groq_instance):
            client = LLMClient(api_key="valid-key", model="llama3-8b-8192")
            try:
                await client.generate("hello")
                pytest.fail("Should have raised")
            except LLMUnavailableError as exc:
                assert exc.__cause__ is original_error

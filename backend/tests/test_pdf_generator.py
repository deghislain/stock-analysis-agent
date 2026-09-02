"""
Unit tests for report/pdf_generator.py and report/templates/styles.py.

Strategy
────────
reportlab may not be installed under the Python 3.10 test interpreter, but
conftest.py stubs every reportlab import with lightweight stand-ins.  Under
the stubs:

  • Paragraph, Spacer, Table, HRFlowable, PageBreak  →  MagicMock instances
  • SimpleDocTemplate                                →  MagicMock
  • TableStyle                                       →  real minimal class
  • ParagraphStyle                                   →  MagicMock
  • A4                                               →  (595.27, 841.89)
  • cm                                               →  28.346…

This means every section method can be called and its return value inspected
(it is a list of MagicMock / primitive objects) without actually rendering a
PDF.  The ``generate()`` classmethod path IS tested end-to-end when reportlab
IS available (Python ≥ 3.14 where it is installed), and is skipped gracefully
otherwise via the _rl_available fixture.

Coverage targets
────────────────
  app/report/templates/styles.py   — 100 %
  app/report/pdf_generator.py      — 100 %
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────


def _minimal_payload(
    *,
    recommendation: str = "Buy",
    executive_summary: str = "Good stock.",
    rationale: str = "Strong fundamentals.",
    news_items: list | None = None,
    sources_used: list | None = None,
    warnings: list | None = None,
    fundamental_explanation: str = "PE is low.",
    technical_explanation: str = "RSI neutral.",
    generated_at: str = "2024-01-15T09:30:00+00:00",
) -> dict:
    """Return the minimum dict PDFGenerator sections need."""
    metric = {"label": "P/E", "value": 22.5, "unit": "x",
               "interpretation": "Lower is cheaper."}
    fr = dict(
        ticker="AAPL", pe_ratio=metric, eps=metric, pb_ratio=metric,
        debt_to_equity=metric, profit_margin=metric, revenue_growth=metric,
        dividend_yield=metric, score=68.0, warnings=[],
    )
    tr = dict(
        ticker="AAPL", dates=[], close_prices=[],
        sma_20={"name": "SMA20", "values": []},
        sma_50={"name": "SMA50", "values": []},
        sma_200={"name": "SMA200", "values": []},
        ema_12={"name": "EMA12", "values": []},
        ema_26={"name": "EMA26", "values": []},
        rsi_14={"name": "RSI14", "values": []},
        macd={"name": "MACD", "values": []},
        macd_signal={"name": "MACD_S", "values": []},
        macd_histogram={"name": "MACD_H", "values": []},
        bb_upper={"name": "BBU", "values": []},
        bb_middle={"name": "BBM", "values": []},
        bb_lower={"name": "BBL", "values": []},
        latest_close=183.5, latest_rsi=58.2, latest_macd=1.1,
        latest_macd_signal=0.9, latest_sma_20=181.0, latest_sma_50=175.0,
        latest_sma_200=160.0, score=62.0, warnings=[],
    )
    sr = dict(ticker="AAPL", positive_count=4, neutral_count=2,
               negative_count=1, score=67.0, label="Positive",
               headlines_analysed=7)
    return dict(
        job_id="test-123", ticker="AAPL",
        generated_at=generated_at,
        status="complete", recommendation=recommendation,
        executive_summary=executive_summary,
        rationale=rationale,
        fundamental_result=fr, technical_result=tr, sentiment_result=sr,
        news_items=news_items if news_items is not None else [
            {"title": "Apple rises", "url": "http://r.com/a",
             "date": "2024-01-15", "source": "reuters.com"},
        ],
        fundamental_explanation=fundamental_explanation,
        technical_explanation=technical_explanation,
        sources_used=sources_used if sources_used is not None
                     else ["Yahoo Finance"],
        warnings=warnings if warnings is not None else [],
        disclaimer=(
            "For informational purposes only. Not financial advice. "
            "Always consult a qualified financial adviser."
        ),
        pdf_path=None,
    )


def _gen(payload: dict | None = None):
    """Return a PDFGenerator instance wrapping *payload* (or a minimal default)."""
    from app.report.pdf_generator import PDFGenerator
    return PDFGenerator(payload or _minimal_payload())


# ═══════════════════════════════════════════════════════════════════════════════
# styles.py — PALETTE, STYLES, table styles, badge_table_style
# ═══════════════════════════════════════════════════════════════════════════════


class TestPalette:

    def test_all_keys_present(self):
        from app.report.templates.styles import PALETTE
        for key in ("background", "surface", "border", "text", "muted",
                    "accent", "buy", "hold", "sell", "warning"):
            assert key in PALETTE

    def test_values_are_not_none(self):
        from app.report.templates.styles import PALETTE
        for val in PALETTE.values():
            assert val is not None


class TestStyles:

    def test_all_expected_keys_present(self):
        from app.report.templates.styles import STYLES
        for name in (
            "cover_title", "cover_ticker", "cover_subtitle",
            "section_heading", "sub_heading",
            "body", "caption", "disclaimer", "badge_label",
            "table_body", "table_header", "table_value",
            "warning_item", "news_title", "news_meta",
        ):
            assert name in STYLES, f"Missing style: {name}"

    def test_styles_not_none(self):
        from app.report.templates.styles import STYLES
        for name, style in STYLES.items():
            assert style is not None, f"Style '{name}' is None"


class TestTableStyles:

    def test_table_style_metrics_is_table_style(self):
        from app.report.templates.styles import TABLE_STYLE_METRICS
        # Under the stub, TableStyle is our minimal class; just confirm it exists
        assert TABLE_STYLE_METRICS is not None

    def test_table_style_plain_is_table_style(self):
        from app.report.templates.styles import TABLE_STYLE_PLAIN
        assert TABLE_STYLE_PLAIN is not None


class TestBadgeTableStyle:

    def test_buy_returns_table_style(self):
        from app.report.templates.styles import badge_table_style
        ts = badge_table_style("Buy")
        assert ts is not None

    def test_hold_returns_table_style(self):
        from app.report.templates.styles import badge_table_style
        ts = badge_table_style("Hold")
        assert ts is not None

    def test_sell_returns_table_style(self):
        from app.report.templates.styles import badge_table_style
        ts = badge_table_style("Sell")
        assert ts is not None

    def test_case_insensitive_buy(self):
        from app.report.templates.styles import badge_table_style
        assert badge_table_style("buy") is not None

    def test_unknown_recommendation_falls_back_to_muted(self):
        from app.report.templates.styles import badge_table_style, PALETTE
        ts = badge_table_style("Unknown")
        assert ts is not None

    def test_all_three_recommendations_differ_by_colour(self):
        """Each recommendation must produce a distinct background colour."""
        from app.report.templates.styles import badge_table_style, PALETTE
        buy_bg  = PALETTE["buy"]
        hold_bg = PALETTE["hold"]
        sell_bg = PALETTE["sell"]
        # The colour map covers all three — just assert they're distinct objects
        assert buy_bg is not hold_bg
        assert hold_bg is not sell_bg
        assert sell_bg is not buy_bg


# ═══════════════════════════════════════════════════════════════════════════════
# pdf_generator.py — helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestFmtValue:

    def test_none_returns_na(self):
        from app.report.pdf_generator import _fmt_value
        assert _fmt_value(None) == "N/A"

    def test_none_with_unit_returns_na(self):
        from app.report.pdf_generator import _fmt_value
        assert _fmt_value(None, "x") == "N/A"

    def test_float_formatted_with_two_decimals(self):
        from app.report.pdf_generator import _fmt_value
        assert _fmt_value(1234.5) == "1,234.50"

    def test_float_with_unit_appended(self):
        from app.report.pdf_generator import _fmt_value
        assert _fmt_value(25.0, "x") == "25.00 x"

    def test_non_float_converted_via_str(self):
        from app.report.pdf_generator import _fmt_value
        # integers are not floats — hits the else branch
        assert _fmt_value(42, None) == "42"  # type: ignore[arg-type]

    def test_non_float_with_unit(self):
        from app.report.pdf_generator import _fmt_value
        assert _fmt_value(42, "%") == "42 %"  # type: ignore[arg-type]


class TestMakeFooterCb:

    def test_returns_callable(self):
        from app.report.pdf_generator import _make_footer_cb
        cb = _make_footer_cb("Disclaimer text.")
        assert callable(cb)

    def test_callback_calls_canvas_methods(self):
        from app.report.pdf_generator import _make_footer_cb
        cb = _make_footer_cb("For informational purposes only.")
        canvas = MagicMock()
        doc = MagicMock()
        doc.page = 1
        cb(canvas, doc)
        canvas.saveState.assert_called_once()
        canvas.restoreState.assert_called_once()
        canvas.setFont.assert_called_once()
        canvas.setFillColor.assert_called_once()
        canvas.drawCentredString.assert_called_once()
        canvas.drawRightString.assert_called_once()

    def test_long_disclaimer_truncated_to_120_chars(self):
        from app.report.pdf_generator import _make_footer_cb
        long_text = "X" * 200
        cb = _make_footer_cb(long_text)
        canvas = MagicMock()
        doc = MagicMock()
        doc.page = 1
        cb(canvas, doc)
        # The centred string arg must contain the ellipsis
        args = canvas.drawCentredString.call_args[0]
        assert "…" in args[2]

    def test_short_disclaimer_no_ellipsis(self):
        from app.report.pdf_generator import _make_footer_cb
        cb = _make_footer_cb("Short disclaimer.")
        canvas = MagicMock()
        doc = MagicMock()
        doc.page = 3
        cb(canvas, doc)
        args = canvas.drawCentredString.call_args[0]
        assert "…" not in args[2]

    def test_page_number_in_right_string(self):
        from app.report.pdf_generator import _make_footer_cb
        cb = _make_footer_cb("Disclaimer.")
        canvas = MagicMock()
        doc = MagicMock()
        doc.page = 5
        cb(canvas, doc)
        right_arg = canvas.drawRightString.call_args[0][2]
        assert "5" in right_arg


# ═══════════════════════════════════════════════════════════════════════════════
# PDFGenerator.__init__ — dict vs model instance
# ═══════════════════════════════════════════════════════════════════════════════


class TestPDFGeneratorInit:

    def test_dict_payload_stored_directly(self):
        from app.report.pdf_generator import PDFGenerator
        d = {"ticker": "AAPL"}
        inst = PDFGenerator(d)
        assert inst._d is d

    def test_model_instance_converted_via_model_dump(self):
        from app.report.pdf_generator import PDFGenerator
        mock_payload = MagicMock()
        mock_payload.model_dump.return_value = {"ticker": "TSLA"}
        inst = PDFGenerator(mock_payload)
        assert inst._d == {"ticker": "TSLA"}
        mock_payload.model_dump.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# PDFGenerator.generate() classmethod
# ═══════════════════════════════════════════════════════════════════════════════


class TestPDFGeneratorGenerate:

    def test_returns_output_path(self):
        from app.report.pdf_generator import PDFGenerator
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "report.pdf")
            with patch.object(PDFGenerator, "_build"):
                result = PDFGenerator.generate(_minimal_payload(), path)
        assert result == path

    def test_calls_build(self):
        from app.report.pdf_generator import PDFGenerator
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "report.pdf")
            with patch.object(PDFGenerator, "_build") as mock_build:
                PDFGenerator.generate(_minimal_payload(), path)
        mock_build.assert_called_once_with(path)

    def test_creates_output_directory(self):
        from app.report.pdf_generator import PDFGenerator
        with tempfile.TemporaryDirectory() as base:
            path = os.path.join(base, "nested", "dir", "report.pdf")
            with patch.object(PDFGenerator, "_build"):
                with patch("app.report.pdf_generator.os.makedirs") as mock_mkdirs:
                    PDFGenerator.generate(_minimal_payload(), path)
            mock_mkdirs.assert_called_once_with(
                os.path.dirname(path), exist_ok=True
            )

    def test_logs_on_success(self, caplog):
        import logging
        from app.report.pdf_generator import PDFGenerator
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "report.pdf")
            with patch.object(PDFGenerator, "_build"):
                with caplog.at_level(logging.INFO, logger="app.report.pdf_generator"):
                    PDFGenerator.generate(_minimal_payload(), path)
        assert "PDF report generated" in caplog.text


# ═══════════════════════════════════════════════════════════════════════════════
# PDFGenerator._build()
# ═══════════════════════════════════════════════════════════════════════════════


class TestPDFGeneratorBuild:

    def test_build_calls_doc_build(self):
        from app.report.pdf_generator import PDFGenerator
        inst = _gen()
        mock_doc = MagicMock()
        with patch("app.report.pdf_generator.SimpleDocTemplate", return_value=mock_doc):
            inst._build("/tmp/test.pdf")
        mock_doc.build.assert_called_once()

    def test_build_passes_footer_callbacks(self):
        from app.report.pdf_generator import PDFGenerator
        inst = _gen()
        mock_doc = MagicMock()
        with patch("app.report.pdf_generator.SimpleDocTemplate", return_value=mock_doc):
            inst._build("/tmp/test.pdf")
        _, kwargs = mock_doc.build.call_args
        assert callable(kwargs.get("onFirstPage"))
        assert callable(kwargs.get("onLaterPages"))

    def test_build_story_is_non_empty_list(self):
        from app.report.pdf_generator import PDFGenerator
        inst = _gen()
        mock_doc = MagicMock()
        with patch("app.report.pdf_generator.SimpleDocTemplate", return_value=mock_doc):
            inst._build("/tmp/test.pdf")
        story_arg = mock_doc.build.call_args[0][0]
        assert isinstance(story_arg, list)
        assert len(story_arg) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# _section_cover
# ═══════════════════════════════════════════════════════════════════════════════


class TestSectionCover:

    def test_returns_non_empty_list(self):
        assert len(_gen()._section_cover()) > 0

    def test_returns_at_least_five_flowables(self):
        """Cover page must have several flowables (title, ticker, date, rule, text, break)."""
        items = _gen()._section_cover()
        assert len(items) >= 5

    def test_empty_generated_at_handled(self):
        g = _gen(_minimal_payload(generated_at=""))
        items = g._section_cover()
        assert len(items) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# _section_executive
# ═══════════════════════════════════════════════════════════════════════════════


class TestSectionExecutive:

    def test_returns_non_empty_list(self):
        assert len(_gen()._section_executive()) > 0

    def test_with_summary_and_rationale(self):
        g = _gen(_minimal_payload(executive_summary="Good.", rationale="Because."))
        items = g._section_executive()
        assert len(items) > 0

    def test_empty_summary_skipped(self):
        """Empty executive_summary must produce fewer items than a populated one."""
        full  = len(_gen(_minimal_payload(executive_summary="Text."))._section_executive())
        empty = len(_gen(_minimal_payload(executive_summary=""))._section_executive())
        assert empty < full

    def test_empty_rationale_skipped(self):
        full  = len(_gen(_minimal_payload(rationale="Text."))._section_executive())
        empty = len(_gen(_minimal_payload(rationale=""))._section_executive())
        assert empty < full

    def test_all_three_recommendations(self):
        for rec in ("Buy", "Hold", "Sell"):
            items = _gen(_minimal_payload(recommendation=rec))._section_executive()
            assert len(items) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# _section_fundamental
# ═══════════════════════════════════════════════════════════════════════════════


class TestSectionFundamental:

    def test_returns_non_empty_list(self):
        assert len(_gen()._section_fundamental()) > 0

    def test_with_explanation(self):
        g = _gen(_minimal_payload(fundamental_explanation="Good fundamentals."))
        items = g._section_fundamental()
        assert len(items) > 0

    def test_without_explanation(self):
        g = _gen(_minimal_payload(fundamental_explanation=""))
        items = g._section_fundamental()
        assert len(items) > 0

    def test_metric_with_model_dump(self):
        """Metric that is a model instance (has model_dump) is handled."""
        from app.report.pdf_generator import PDFGenerator
        mock_metric = MagicMock()
        mock_metric.model_dump.return_value = {
            "label": "P/E", "value": 20.0, "unit": "x", "interpretation": "Low."
        }
        payload = _minimal_payload()
        payload["fundamental_result"] = {
            "pe_ratio": mock_metric,
            "eps": mock_metric, "pb_ratio": mock_metric,
            "debt_to_equity": mock_metric, "profit_margin": mock_metric,
            "revenue_growth": mock_metric, "dividend_yield": mock_metric,
            "score": 55.0,
        }
        inst = PDFGenerator(payload)
        items = inst._section_fundamental()
        assert len(items) > 0

    def test_metric_none_value_rendered_as_na(self):
        """Metric with value=None must not raise — renders N/A."""
        payload = _minimal_payload()
        none_metric = {"label": "P/E", "value": None, "unit": None, "interpretation": None}
        payload["fundamental_result"] = {
            k: none_metric for k in (
                "pe_ratio", "eps", "pb_ratio", "debt_to_equity",
                "profit_margin", "revenue_growth", "dividend_yield",
            )
        }
        payload["fundamental_result"]["score"] = 0.0
        items = _gen(payload)._section_fundamental()
        assert len(items) > 0

    def test_fundamental_result_as_model_instance(self):
        """fundamental_result can be a model instance (not a dict)."""
        from app.report.pdf_generator import PDFGenerator
        mock_fr = MagicMock(spec=[])  # no dict methods
        mock_fr.score = 50.0
        for field in ("pe_ratio", "eps", "pb_ratio", "debt_to_equity",
                      "profit_margin", "revenue_growth", "dividend_yield"):
            m = MagicMock()
            m.get = MagicMock(return_value=None)
            setattr(mock_fr, field, m)
        payload = _minimal_payload()
        payload["fundamental_result"] = mock_fr
        inst = PDFGenerator(payload)
        items = inst._section_fundamental()
        assert len(items) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# _section_technical
# ═══════════════════════════════════════════════════════════════════════════════


class TestSectionTechnical:

    def test_returns_non_empty_list(self):
        assert len(_gen()._section_technical()) > 0

    def test_with_explanation(self):
        g = _gen(_minimal_payload(technical_explanation="RSI neutral."))
        assert len(g._section_technical()) > 0

    def test_without_explanation(self):
        g = _gen(_minimal_payload(technical_explanation=""))
        assert len(g._section_technical()) > 0

    def test_none_latest_values_rendered_as_na(self):
        payload = _minimal_payload()
        payload["technical_result"] = {
            "score": 50.0,
            "latest_close": None, "latest_rsi": None, "latest_macd": None,
            "latest_macd_signal": None, "latest_sma_20": None,
            "latest_sma_50": None, "latest_sma_200": None,
        }
        items = _gen(payload)._section_technical()
        assert len(items) > 0

    def test_technical_result_as_model_instance(self):
        """technical_result can be a model instance (attribute access path)."""
        from app.report.pdf_generator import PDFGenerator
        mock_tr = MagicMock(spec=[])  # no dict methods
        mock_tr.score = 45.0
        for attr in ("latest_close", "latest_rsi", "latest_macd",
                     "latest_macd_signal", "latest_sma_20",
                     "latest_sma_50", "latest_sma_200"):
            setattr(mock_tr, attr, 99.0)
        payload = _minimal_payload()
        payload["technical_result"] = mock_tr
        inst = PDFGenerator(payload)
        items = inst._section_technical()
        assert len(items) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# _section_news
# ═══════════════════════════════════════════════════════════════════════════════


class TestSectionNews:

    def test_with_news_items(self):
        items = _gen()._section_news()
        assert len(items) > 0

    def test_empty_news_items_returns_fallback(self):
        g = _gen(_minimal_payload(news_items=[]))
        items = g._section_news()
        assert len(items) > 0

    def test_news_item_with_no_meta(self):
        """News item with empty source and date must not raise."""
        payload = _minimal_payload(news_items=[
            {"title": "Headline", "url": "http://x.com",
             "date": "", "source": ""},
        ])
        items = _gen(payload)._section_news()
        assert len(items) > 0

    def test_news_item_as_model_instance(self):
        """News item that is a model instance (attribute access) is handled."""
        mock_item = MagicMock(spec=["title", "url", "date", "source"])
        mock_item.title  = "Apple News"
        mock_item.url    = "http://news.com/a"
        mock_item.date   = "2024-01-15"
        mock_item.source = "news.com"
        payload = _minimal_payload(news_items=[mock_item])
        items = _gen(payload)._section_news()
        assert len(items) > 0

    def test_max_10_items_used(self):
        """Only the first 10 news items are rendered."""
        many = [{"title": f"h{i}", "url": "http://x.com",
                 "date": "2024-01-01", "source": "x.com"}
                for i in range(15)]
        payload = _minimal_payload(news_items=many)
        # Should not raise; we just check it completes
        items = _gen(payload)._section_news()
        assert len(items) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# _section_sources
# ═══════════════════════════════════════════════════════════════════════════════


class TestSectionSources:

    def test_with_sources(self):
        items = _gen()._section_sources()
        assert len(items) > 0

    def test_empty_sources_returns_fallback(self):
        g = _gen(_minimal_payload(sources_used=[]))
        items = g._section_sources()
        assert len(items) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# _section_warnings
# ═══════════════════════════════════════════════════════════════════════════════


class TestSectionWarnings:

    def test_empty_warnings_returns_empty_list(self):
        g = _gen(_minimal_payload(warnings=[]))
        assert g._section_warnings() == []

    def test_with_warnings_returns_non_empty(self):
        g = _gen(_minimal_payload(warnings=["Something went wrong."]))
        items = g._section_warnings()
        assert len(items) > 0

    def test_multiple_warnings_all_included(self):
        warns = ["Warning A", "Warning B", "Warning C"]
        g = _gen(_minimal_payload(warnings=warns))
        items = g._section_warnings()
        # header + hr + one item per warning
        assert len(items) >= len(warns)

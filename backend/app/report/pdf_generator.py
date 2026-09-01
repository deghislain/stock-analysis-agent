"""
PDF report generator for the Stock Analysis Agent — Sub-Task 6.

Public API
──────────
    from app.report.pdf_generator import PDFGenerator

    pdf_path = PDFGenerator.generate(payload, output_path)

``PDFGenerator.generate()`` is a class method that accepts a completed
``ReportPayload`` (or an equivalent plain dict) and writes a PDF to
``output_path``.  It returns the same path so callers can store it directly.

PDF structure (one flowable section per method)
───────────────────────────────────────────────
    1. _section_cover            — ticker, date, brief disclaimer
    2. _section_executive        — recommendation badge + rationale + executive summary
    3. _section_fundamental      — metrics table + plain-language explanation
    4. _section_technical        — key indicator snapshot table + explanation
    5. _section_news             — up to 10 news headlines with source/date
    6. _section_sources          — data sources used
    7. _section_warnings         — warning flags (omitted when list is empty)
    8. _footer (on every page)   — full disclaimer via SimpleDocTemplate.onFirstPage
                                   / onLaterPages

Design
──────
- ``SimpleDocTemplate`` + ``Story`` list of flowables — no raw canvas drawing.
- Page size: A4.  Margins: 2 cm on all sides.
- All styling is imported from ``report/templates/styles.py``; this module
  contains no hard-coded colours or font sizes.
- ``None`` metric values are rendered as ``"N/A"`` so the table never crashes.
- The generator is stateless: every call to ``generate()`` creates a fresh
  ``PDFGenerator`` instance internally, so there is no risk of cross-request
  contamination when the app handles concurrent jobs.
"""

from __future__ import annotations

import html
import os
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
)

from app.logger import get_logger
from app.report.templates.styles import (
    PALETTE,
    STYLES,
    TABLE_STYLE_METRICS,
    TABLE_STYLE_PLAIN,
    badge_table_style,
)

logger = get_logger(__name__)

# Page geometry
_PAGE_W, _PAGE_H = A4
_MARGIN = 2 * cm
_CONTENT_W = _PAGE_W - 2 * _MARGIN  # usable width for tables


# ── Helpers ───────────────────────────────────────────────────────────────────


def _p(text: str, style_key: str) -> Paragraph:
    """Return a ``Paragraph`` flowable with XML-escaped *text* and *style_key*."""
    return Paragraph(html.escape(str(text)), STYLES[style_key])


def _hr() -> HRFlowable:
    """Thin horizontal rule using the border palette colour."""
    return HRFlowable(
        width="100%",
        thickness=0.5,
        color=PALETTE["border"],
        spaceAfter=6,
        spaceBefore=4,
    )


def _fmt_value(value: float | None, unit: str | None = None) -> str:
    """Format a metric value for table display; returns ``"N/A"`` when ``None``."""
    if value is None:
        return "N/A"
    if isinstance(value, float):
        formatted = f"{value:,.2f}"
    else:
        formatted = str(value)
    return f"{formatted} {unit}".strip() if unit else formatted


# ── Footer callback ───────────────────────────────────────────────────────────


def _make_footer_cb(disclaimer: str):
    """
    Return an ``onPage`` callback that draws a disclaimer footer and page number
    on every page via the ReportLab canvas.

    This is the *only* place raw canvas drawing is used — it is required because
    ReportLab does not support repeating footers via flowables.
    """
    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(PALETTE["muted"])
        # Disclaimer centred at the bottom
        canvas.drawCentredString(
            _PAGE_W / 2,
            _MARGIN * 0.55,
            disclaimer[:120] + ("…" if len(disclaimer) > 120 else ""),
        )
        # Page number right-aligned
        canvas.drawRightString(
            _PAGE_W - _MARGIN,
            _MARGIN * 0.55,
            f"Page {doc.page}",
        )
        canvas.restoreState()

    return _footer


# ── PDFGenerator ──────────────────────────────────────────────────────────────


class PDFGenerator:
    """
    Builds the PDF report from a completed ``ReportPayload``.

    Usage
    ─────
    ::

        path = PDFGenerator.generate(payload, "/tmp/stock_reports/AAPL_abc.pdf")

    The class is intentionally stateless between calls — ``generate()`` is a
    ``@classmethod`` that constructs a private instance for each invocation.
    """

    def __init__(self, payload: Any) -> None:
        # Accept both ReportPayload model instances and plain dicts (the
        # orchestrator stores either format depending on the code path).
        if isinstance(payload, dict):
            self._d = payload
        else:
            self._d = payload.model_dump()

    # ── Public entry point ────────────────────────────────────────────────────

    @classmethod
    def generate(cls, payload: Any, output_path: str) -> str:
        """
        Generate the PDF report and write it to *output_path*.

        Parameters
        ----------
        payload : ReportPayload | dict
            The completed analysis result.
        output_path : str
            Absolute path where the PDF should be written.  The directory must
            already exist (created by the lifespan startup hook in ``main.py``).

        Returns
        -------
        str
            The same *output_path*, so callers can chain the call::

                pdf_path = PDFGenerator.generate(payload, path)
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        instance = cls(payload)
        instance._build(output_path)
        logger.info(
            "PDF report generated",
            extra={
                "ticker": instance._d.get("ticker"),
                "job_id": instance._d.get("job_id"),
                "output_path": output_path,
            },
        )
        return output_path

    # ── Internal builder ──────────────────────────────────────────────────────

    def _build(self, output_path: str) -> None:
        """Assemble the Story list and render the PDF."""
        disclaimer = self._d.get("disclaimer", "For informational purposes only.")
        footer_cb = _make_footer_cb(disclaimer)

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=_MARGIN,
            rightMargin=_MARGIN,
            topMargin=_MARGIN,
            bottomMargin=_MARGIN * 1.6,  # extra bottom space for footer
            title=f"Stock Analysis — {self._d.get('ticker', '')}",
            author="Stock Analysis Agent",
        )

        story: list = []
        story += self._section_cover()
        story += self._section_executive()
        story += self._section_fundamental()
        story += self._section_technical()
        story += self._section_news()
        story += self._section_sources()
        story += self._section_warnings()

        doc.build(
            story,
            onFirstPage=footer_cb,
            onLaterPages=footer_cb,
        )

    # ── Section: Cover ────────────────────────────────────────────────────────

    def _section_cover(self) -> list:
        ticker = self._d.get("ticker", "")
        generated_at = self._d.get("generated_at", "")
        # Trim the timezone suffix to keep it readable: "2024-01-15T09:30:00"
        date_display = generated_at[:19].replace("T", "  ") if generated_at else ""

        return [
            Spacer(1, 2 * cm),
            _p("Stock Analysis Report", "cover_title"),
            Spacer(1, 0.3 * cm),
            _p(ticker, "cover_ticker"),
            Spacer(1, 0.2 * cm),
            _p(f"Generated: {date_display}", "cover_subtitle"),
            Spacer(1, 1.2 * cm),
            _hr(),
            Spacer(1, 0.5 * cm),
            _p(
                "This report is for informational purposes only and does not "
                "constitute financial advice. Past performance is not a reliable "
                "indicator of future results.",
                "caption",
            ),
            PageBreak(),
        ]

    # ── Section: Executive Summary ────────────────────────────────────────────

    def _section_executive(self) -> list:
        rec = self._d.get("recommendation", "Hold")
        rationale = self._d.get("rationale", "")
        summary = self._d.get("executive_summary", "")

        # Badge: single-cell table with coloured background
        badge_para = Paragraph(rec.upper(), STYLES["badge_label"])
        badge_table = Table([[badge_para]], colWidths=[6 * cm])
        badge_table.setStyle(badge_table_style(rec))

        flowables: list = [
            _p("Executive Summary", "section_heading"),
            _hr(),
            Spacer(1, 0.3 * cm),
            badge_table,
            Spacer(1, 0.4 * cm),
        ]

        if summary:
            flowables.append(_p(summary, "body"))
            flowables.append(Spacer(1, 0.2 * cm))

        if rationale:
            flowables.append(_p("Rationale", "sub_heading"))
            flowables.append(_p(rationale, "body"))

        return flowables

    # ── Section: Fundamental Analysis ─────────────────────────────────────────

    def _section_fundamental(self) -> list:
        fr = self._d.get("fundamental_result", {})
        explanation = self._d.get("fundamental_explanation", "")

        # Metric order matches the FundamentalResult field order
        metric_fields = [
            ("pe_ratio",       "P/E Ratio"),
            ("eps",            "Earnings Per Share (EPS)"),
            ("pb_ratio",       "P/B Ratio"),
            ("debt_to_equity", "Debt / Equity"),
            ("profit_margin",  "Profit Margin"),
            ("revenue_growth", "Revenue Growth"),
            ("dividend_yield", "Dividend Yield"),
        ]

        rows = [[
            _p("Metric",         "table_header"),
            _p("Value",          "table_header"),
            _p("Interpretation", "table_header"),
        ]]
        for field, label in metric_fields:
            m = fr.get(field, {}) if isinstance(fr, dict) else getattr(fr, field, {})
            if hasattr(m, "model_dump"):
                m = m.model_dump()
            value_str = _fmt_value(m.get("value"), m.get("unit"))
            interp = m.get("interpretation") or ""
            rows.append([
                _p(label,     "table_body"),
                _p(value_str, "table_value"),
                _p(interp,    "table_body"),
            ])

        score = fr.get("score", 0) if isinstance(fr, dict) else getattr(fr, "score", 0)
        col_widths = [_CONTENT_W * 0.28, _CONTENT_W * 0.18, _CONTENT_W * 0.54]
        tbl = Table(rows, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TABLE_STYLE_METRICS)

        flowables: list = [
            _p("Fundamental Analysis", "section_heading"),
            _hr(),
            _p("Key Metrics", "sub_heading"),
            tbl,
            _p(f"Fundamental Score: {score:.0f} / 100", "caption"),
            Spacer(1, 0.3 * cm),
        ]
        if explanation:
            flowables.append(_p("Plain-Language Explanation", "sub_heading"))
            flowables.append(_p(explanation, "body"))

        return flowables

    # ── Section: Technical Analysis ───────────────────────────────────────────

    def _section_technical(self) -> list:
        tr = self._d.get("technical_result", {})
        explanation = self._d.get("technical_explanation", "")

        def _latest(field: str) -> str:
            if isinstance(tr, dict):
                val = tr.get(field)
            else:
                val = getattr(tr, field, None)
            return _fmt_value(val)

        rows = [
            [_p("Indicator",         "table_header"), _p("Latest Value", "table_header")],
            [_p("Closing Price",     "table_body"),   _p(_latest("latest_close"),       "table_value")],
            [_p("RSI (14)",          "table_body"),   _p(_latest("latest_rsi"),         "table_value")],
            [_p("MACD",              "table_body"),   _p(_latest("latest_macd"),        "table_value")],
            [_p("MACD Signal",       "table_body"),   _p(_latest("latest_macd_signal"), "table_value")],
            [_p("SMA 20",            "table_body"),   _p(_latest("latest_sma_20"),      "table_value")],
            [_p("SMA 50",            "table_body"),   _p(_latest("latest_sma_50"),      "table_value")],
            [_p("SMA 200",           "table_body"),   _p(_latest("latest_sma_200"),     "table_value")],
        ]

        score = tr.get("score", 0) if isinstance(tr, dict) else getattr(tr, "score", 0)
        col_widths = [_CONTENT_W * 0.55, _CONTENT_W * 0.45]
        tbl = Table(rows, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TABLE_STYLE_METRICS)

        flowables: list = [
            _p("Technical Analysis", "section_heading"),
            _hr(),
            _p("Key Indicators (Latest Values)", "sub_heading"),
            tbl,
            _p(f"Technical Score: {score:.0f} / 100", "caption"),
            Spacer(1, 0.3 * cm),
        ]
        if explanation:
            flowables.append(_p("Plain-Language Explanation", "sub_heading"))
            flowables.append(_p(explanation, "body"))

        return flowables

    # ── Section: News ─────────────────────────────────────────────────────────

    def _section_news(self) -> list:
        items = self._d.get("news_items", [])

        # Accept both model instances and plain dicts
        def _get(item, key: str, default: str = "") -> str:
            if isinstance(item, dict):
                return item.get(key, default) or default
            return getattr(item, key, default) or default

        flowables: list = [
            _p("News Summary", "section_heading"),
            _hr(),
        ]

        if not items:
            flowables.append(_p("No news items available.", "caption"))
            return flowables

        for item in items[:10]:
            title  = _get(item, "title",  "Untitled")
            source = _get(item, "source", "")
            date   = _get(item, "date",   "")
            meta_parts = [p for p in (source, date) if p]
            meta = "  ·  ".join(meta_parts) if meta_parts else ""

            flowables.append(_p(title, "news_title"))
            if meta:
                flowables.append(_p(meta, "news_meta"))
            else:
                flowables.append(Spacer(1, 0.15 * cm))

        return flowables

    # ── Section: Data Sources ─────────────────────────────────────────────────

    def _section_sources(self) -> list:
        sources = self._d.get("sources_used", [])

        flowables: list = [
            _p("Data Sources Used", "section_heading"),
            _hr(),
        ]

        if not sources:
            flowables.append(_p("No data source information available.", "caption"))
            return flowables

        rows = [[_p("Source", "table_header")]]
        for src in sources:
            rows.append([_p(str(src), "table_body")])

        tbl = Table(rows, colWidths=[_CONTENT_W * 0.5], repeatRows=1)
        tbl.setStyle(TABLE_STYLE_PLAIN)
        flowables.append(tbl)

        return flowables

    # ── Section: Warnings ─────────────────────────────────────────────────────

    def _section_warnings(self) -> list:
        warnings = self._d.get("warnings", [])
        if not warnings:
            return []  # Omit section entirely when there are no warnings

        flowables: list = [
            _p("Warning Flags", "section_heading"),
            _hr(),
        ]
        for w in warnings:
            flowables.append(_p(f"⚠  {w}", "warning_item"))

        return flowables

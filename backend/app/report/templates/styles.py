"""
ReportLab style definitions for the Stock Analysis Agent PDF report.

All ``ParagraphStyle`` and ``TableStyle`` objects used by ``pdf_generator.py``
are defined here so the generator module stays free of style boilerplate.

Palette
───────
    Background      #FFFFFF  white
    Surface         #F7F8FA  light grey — table header / badge backgrounds
    Border          #E5E7EB  subtle grey — table grid lines
    Text            #1F2328  near-black body text
    Muted           #57606A  secondary / caption text
    Accent          #3B82D4  blue — section headings, links
    Buy             #16A34A  green
    Hold            #CA8A04  amber
    Sell            #DC2626  red
    Warning         #D97706  orange

Usage
─────
    from app.report.templates.styles import (
        STYLES,
        TABLE_STYLE_METRICS,
        TABLE_STYLE_PLAIN,
        badge_table_style,
        PALETTE,
    )
"""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import TableStyle

# ── Colour palette ────────────────────────────────────────────────────────────

PALETTE: dict[str, colors.Color] = {
    "background": colors.HexColor("#FFFFFF"),
    "surface":    colors.HexColor("#F7F8FA"),
    "border":     colors.HexColor("#E5E7EB"),
    "text":       colors.HexColor("#1F2328"),
    "muted":      colors.HexColor("#57606A"),
    "accent":     colors.HexColor("#3B82D4"),
    "buy":        colors.HexColor("#16A34A"),
    "hold":       colors.HexColor("#CA8A04"),
    "sell":       colors.HexColor("#DC2626"),
    "warning":    colors.HexColor("#D97706"),
}

# ── Paragraph styles ──────────────────────────────────────────────────────────

_base = getSampleStyleSheet()

# Each style is built from scratch (not inherited from getSampleStyleSheet)
# so the output is predictable regardless of ReportLab version defaults.

STYLES: dict[str, ParagraphStyle] = {

    # ── Document title on the cover page ────────────────────────────────────
    "cover_title": ParagraphStyle(
        name="cover_title",
        fontName="Helvetica-Bold",
        fontSize=28,
        leading=34,
        textColor=PALETTE["text"],
        alignment=TA_CENTER,
        spaceAfter=8,
    ),

    # ── Ticker symbol rendered large on the cover ────────────────────────────
    "cover_ticker": ParagraphStyle(
        name="cover_ticker",
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=26,
        textColor=PALETTE["accent"],
        alignment=TA_CENTER,
        spaceAfter=6,
    ),

    # ── Subtitle / date line on the cover ────────────────────────────────────
    "cover_subtitle": ParagraphStyle(
        name="cover_subtitle",
        fontName="Helvetica",
        fontSize=11,
        leading=16,
        textColor=PALETTE["muted"],
        alignment=TA_CENTER,
        spaceAfter=4,
    ),

    # ── Top-level section heading (e.g. "Fundamental Analysis") ─────────────
    "section_heading": ParagraphStyle(
        name="section_heading",
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=PALETTE["accent"],
        spaceBefore=18,
        spaceAfter=6,
        borderPadding=(0, 0, 4, 0),
    ),

    # ── Sub-heading within a section (e.g. "Key Metrics") ───────────────────
    "sub_heading": ParagraphStyle(
        name="sub_heading",
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=PALETTE["text"],
        spaceBefore=10,
        spaceAfter=4,
    ),

    # ── Standard body paragraph ───────────────────────────────────────────────
    "body": ParagraphStyle(
        name="body",
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=PALETTE["text"],
        spaceAfter=6,
    ),

    # ── Muted / caption text (sources, footnotes) ────────────────────────────
    "caption": ParagraphStyle(
        name="caption",
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=PALETTE["muted"],
        spaceAfter=4,
    ),

    # ── Disclaimer text — small, centred, muted ───────────────────────────────
    "disclaimer": ParagraphStyle(
        name="disclaimer",
        fontName="Helvetica-Oblique",
        fontSize=8,
        leading=12,
        textColor=PALETTE["muted"],
        alignment=TA_CENTER,
        spaceBefore=8,
        spaceAfter=4,
    ),

    # ── Recommendation badge label (Buy / Hold / Sell) ────────────────────────
    "badge_label": ParagraphStyle(
        name="badge_label",
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=PALETTE["background"],  # white text on coloured background
        alignment=TA_CENTER,
    ),

    # ── Table cell — normal body text ─────────────────────────────────────────
    "table_body": ParagraphStyle(
        name="table_body",
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=PALETTE["text"],
    ),

    # ── Table cell — header row text ──────────────────────────────────────────
    "table_header": ParagraphStyle(
        name="table_header",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=PALETTE["text"],
    ),

    # ── Numeric value cell — right-aligned ────────────────────────────────────
    "table_value": ParagraphStyle(
        name="table_value",
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=PALETTE["text"],
        alignment=TA_RIGHT,
    ),

    # ── Warning item bullet text ──────────────────────────────────────────────
    "warning_item": ParagraphStyle(
        name="warning_item",
        fontName="Helvetica",
        fontSize=9,
        leading=14,
        textColor=PALETTE["warning"],
        spaceAfter=3,
    ),

    # ── News headline ─────────────────────────────────────────────────────────
    "news_title": ParagraphStyle(
        name="news_title",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=PALETTE["text"],
        spaceAfter=1,
    ),

    # ── News source / date caption ────────────────────────────────────────────
    "news_meta": ParagraphStyle(
        name="news_meta",
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=PALETTE["muted"],
        spaceAfter=6,
    ),
}


# ── Table styles ──────────────────────────────────────────────────────────────

# Shared commands used by all tables.
_TABLE_BASE_COMMANDS = [
    # Header row background
    ("BACKGROUND",  (0, 0), (-1, 0),  PALETTE["surface"]),
    # Header row text bold — handled via Paragraph styles, this is a safety net
    ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
    ("FONTSIZE",    (0, 0), (-1, 0),  9),
    # Body rows
    ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE",    (0, 1), (-1, -1), 9),
    # Padding
    ("TOPPADDING",  (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    # Grid
    ("GRID",        (0, 0), (-1, -1), 0.5, PALETTE["border"]),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
     [PALETTE["background"], PALETTE["surface"]]),
    # Vertical alignment
    ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
]


TABLE_STYLE_METRICS: TableStyle = TableStyle(
    _TABLE_BASE_COMMANDS + [
        # Right-align the value column (index 1).
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        # Right-align the unit column (index 2) when present.
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
    ]
)
"""
Style for the fundamental / technical metrics table.

Expected column layout: [Metric, Value, Unit, Interpretation]
"""

TABLE_STYLE_PLAIN: TableStyle = TableStyle(
    _TABLE_BASE_COMMANDS
)
"""
General-purpose table style — uniform left alignment, alternating row shading.
"""


def badge_table_style(recommendation: str) -> TableStyle:
    """
    Return a ``TableStyle`` whose background colour matches the recommendation.

    Parameters
    ----------
    recommendation : str
        One of ``"Buy"``, ``"Hold"``, or ``"Sell"`` (case-insensitive).

    Returns
    -------
    TableStyle
        Single-cell table style with the appropriate badge colour.
    """
    colour_map = {
        "buy":  PALETTE["buy"],
        "hold": PALETTE["hold"],
        "sell": PALETTE["sell"],
    }
    bg = colour_map.get(recommendation.lower(), PALETTE["muted"])
    return TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 24),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 24),
        ("ROUNDEDCORNERS", [4]),
    ])

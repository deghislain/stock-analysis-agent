"""
API-layer output schemas for the report endpoints (Sub-Task 5).

Three models are defined here:

    NewsItem           — a single cleaned news headline returned by ResearchAgent;
                         used inside ReportPayload.news_items.

    ReportPayload      — the complete analysis result returned by
                         ``GET /api/report/{job_id}`` once the job is "complete".
                         Field names are fixed by the plan and must be respected
                         by every sub-task that reads or writes this object.

    JobStatusResponse  — the lightweight in-progress response returned by
                         ``GET /api/report/{job_id}`` while the job is still
                         "pending" or "running" (or has hit "error").
                         The optional ``current_step`` string feeds the
                         frontend's LoadingSpinner step labels directly.

Design notes
────────────
- ReportPayload is NOT frozen: ``pdf_path`` is written by the PDF-generation
  step (Sub-Task 6) after the initial payload is stored, so the model must
  allow mutation.
- All nested result types (FundamentalResult, TechnicalResult, SentimentResult)
  are imported from ``schemas/analysis.py`` to keep a single source of truth.
- ``executive_summary`` is included even though it is not listed in the plan's
  schema table; the orchestrator assembles it from the ReportAgent and the
  frontend displays it as the top card on the report page.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.analysis import FundamentalResult, SentimentResult, TechnicalResult

# Hardcoded disclaimer — must appear in every payload (plan §"Disclaimer enforcement").
_DISCLAIMER = (
    "For informational purposes only. "
    "Not financial advice. "
    "Always consult a qualified financial adviser before making investment decisions."
)


# ── NewsItem ───────────────────────────────────────────────────────────────────


class NewsItem(BaseModel):
    """
    A single news headline returned by ``ResearchAgent`` and embedded in
    ``ReportPayload.news_items``.

    The ``body`` field used internally for sentiment analysis is intentionally
    omitted here — it is an implementation detail of the analysis layer and
    not needed by the frontend.
    """

    title: str
    """Headline text."""

    url: str
    """Link to the full article."""

    date: str
    """
    Publication date as an ISO date string (``YYYY-MM-DD``).

    Empty string when DuckDuckGo does not provide a date for this item.
    """

    source: str
    """Bare domain name extracted from ``url`` (e.g. ``"reuters.com"``)."""


# ── ReportPayload ──────────────────────────────────────────────────────────────


class ReportPayload(BaseModel):
    """
    The complete analysis result stored in the job store and returned by
    ``GET /api/report/{job_id}`` once the job reaches ``status="complete"``.

    Field names are fixed by the plan (Sub-Task 5) and must not be renamed.
    Every consuming layer — PDF generator, frontend, integration tests — reads
    these names verbatim.
    """

    # ── Identity ──────────────────────────────────────────────────────────────

    job_id: str
    """UUID string that uniquely identifies this analysis job."""

    ticker: str
    """Upper-case ticker symbol that was analysed."""

    generated_at: str
    """ISO 8601 UTC datetime string (``YYYY-MM-DDTHH:MM:SS+00:00``) of when
    the report was assembled by the orchestrator."""

    # ── Status ────────────────────────────────────────────────────────────────

    status: str
    """
    Final job status: one of ``"complete"`` or ``"error"``.

    When ``"error"`` the analysis fields will contain neutral/empty values
    and the ``warnings`` list will explain what went wrong.
    """

    # ── LLM-generated text ────────────────────────────────────────────────────

    recommendation: str
    """
    Top-level investment recommendation: one of ``"Buy"``, ``"Hold"``, ``"Sell"``.

    Derived from the composite score and optionally overridden by the LLM.
    """

    executive_summary: str
    """
    2–3 sentence overview of the stock written by the Groq LLM for beginners.

    Empty string when the LLM fallback is active.
    """

    rationale: str
    """3-sentence justification for the recommendation (LLM output)."""

    fundamental_explanation: str
    """Plain-language explanation of the fundamental metrics (LLM, ≤ 150 words)."""

    technical_explanation: str
    """Plain-language explanation of the technical indicators (LLM, ≤ 150 words)."""

    # ── Structured analysis results ───────────────────────────────────────────

    fundamental_result: FundamentalResult
    """Output of ``FundamentalAnalyser`` — all seven metrics with scores."""

    technical_result: TechnicalResult
    """Output of ``TechnicalAnalyser`` — full indicator time-series + scalar latests."""

    sentiment_result: SentimentResult
    """Output of ``SentimentAnalyser`` — headline counts + 0–100 sentiment score."""

    news_items: list[NewsItem]
    """Up to 10 cleaned news headlines from ``ResearchAgent`` / DuckDuckGo."""

    # ── Metadata ──────────────────────────────────────────────────────────────

    sources_used: list[str]
    """Names of every data source that contributed to this analysis
    (e.g. ``["Yahoo Finance", "Stooq"]``). Feeds the ``DataSourcesBadge``."""

    warnings: list[str]
    """
    Deduplicated union of all warnings from the data, analysis, and report
    layers.  Feeds the ``WarningFlags`` component and the PDF report.
    """

    disclaimer: str = Field(default=_DISCLAIMER)
    """
    Mandatory disclaimer baked into every report.

    Defaults to the canonical disclaimer string; must never be blank.
    """

    pdf_path: Optional[str] = None
    """
    Absolute path to the generated PDF file on the server, or ``None`` before
    PDF generation runs.  Set by the PDF generator (Sub-Task 6) after the
    initial payload is stored.
    """


# ── JobStatusResponse ──────────────────────────────────────────────────────────


class JobStatusResponse(BaseModel):
    """
    Lightweight response returned by ``GET /api/report/{job_id}`` while the
    job has not yet reached ``"complete"``.

    The frontend polls this endpoint and uses ``current_step`` to update its
    ``LoadingSpinner`` step labels in real time.
    """

    status: str
    """
    Current job status: one of ``"pending"``, ``"running"``, or ``"error"``.

    ``"pending"``  — job was created but the orchestrator has not started yet.
    ``"running"``  — orchestrator is actively executing pipeline steps.
    ``"error"``    — orchestrator encountered an unrecoverable error.
    """

    current_step: Optional[str] = None
    """
    Human-readable label of the pipeline step currently executing,
    e.g. ``"Fetching data"``, ``"Analysing fundamentals"``.

    ``None`` when status is ``"pending"`` or ``"error"``.
    Populated only while ``status == "running"``.
    """

    error: Optional[str] = None
    """
    Error message when ``status == "error"``; ``None`` otherwise.

    Kept brief and safe — no internal stack traces.
    """

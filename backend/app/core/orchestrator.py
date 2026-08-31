"""
Orchestrator — runs the full analysis pipeline for a single ticker.

``Orchestrator.run(ticker, job_id)`` is called as a FastAPI ``BackgroundTask``
immediately after ``POST /api/analyse`` returns.  It executes every agent in
sequence, updates the job's ``current_step`` in the ``JobStore`` after each
one, and writes the assembled ``ReportPayload`` dict into the store when done.

Pipeline steps (in order)
──────────────────────────
  1. DataAgent       — fetch price history + fundamentals via source fallback chain
  2. ResearchAgent   — fetch recent news headlines via DuckDuckGo
  3. FundamentalAgent — compute fundamental metrics + score
  4. TechnicalAgent  — compute technical indicators + score
  5. Sentiment       — classify headlines; score 0–100   (direct call, not an agent)
  6. ReportAgent     — call Groq LLM for plain-language explanation + recommendation

Scoring & recommendation
────────────────────────
  overall_score = fundamental * 0.40 + technical * 0.40 + sentiment * 0.20
  >= 60  → "Buy"
  40–59  → "Hold"
  < 40   → "Sell"

Error handling
──────────────
  Any unhandled exception (including ``ValueError`` from ``DataAgent`` for an
  unknown ticker) causes the job to be marked ``"error"`` immediately.  All
  other agent failures return ``{"status": "error"}`` dicts; the orchestrator
  logs them as warnings and continues with neutral placeholder values so a
  partial report is always produced.

ReportPayload shape (assembled as a plain dict — mirrors ``schemas/report.py``)
────────────────────────────────────────────────────────────────────────────────
  job_id, ticker, generated_at, status, recommendation, rationale,
  fundamental_result, technical_result, sentiment_result, news_items,
  fundamental_explanation, technical_explanation, sources_used, warnings,
  disclaimer, pdf_path
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.agents.data_agent import DataAgent
from app.agents.fundamental_agent import FundamentalAgent
from app.agents.report_agent import ReportAgent
from app.agents.research_agent import ResearchAgent
from app.agents.technical_agent import TechnicalAgent
from app.analysis.sentiment import SentimentAnalyser
from app.core.job_store import JobStore
from app.logger import get_logger
from app.schemas.analysis import AnalysisResult

if TYPE_CHECKING:
    from app.data.base_source import StockData
    from app.schemas.analysis import (
        FundamentalResult,
        SentimentResult,
        TechnicalResult,
    )

logger = get_logger(__name__)

# Disclaimer baked into every report (plan §"Disclaimer enforcement").
_DISCLAIMER = (
    "For informational purposes only. "
    "Not financial advice. "
    "Always consult a qualified financial adviser before making investment decisions."
)

# Score → recommendation thresholds (plan §AnalysisResult.overall_score).
_BUY_THRESHOLD  = 60.0
_SELL_THRESHOLD = 40.0

# Weights for the composite score.
_W_FUNDAMENTAL = 0.40
_W_TECHNICAL   = 0.40
_W_SENTIMENT   = 0.20


class Orchestrator:
    """
    Runs the full stock-analysis pipeline and stores the result in a ``JobStore``.

    All agent dependencies are injected at construction time so the class is
    fully testable without patching module globals.

    Parameters
    ----------
    job_store : JobStore
        Shared store that persists job state between the route handler and the
        background task.
    data_agent : DataAgent | None
        Provide a custom instance to override the default in tests.
    research_agent : ResearchAgent | None
    fundamental_agent : FundamentalAgent | None
    technical_agent : TechnicalAgent | None
    report_agent : ReportAgent | None
    sentiment_analyser : SentimentAnalyser | None
    """

    def __init__(
        self,
        job_store: JobStore,
        *,
        data_agent:        DataAgent         | None = None,
        research_agent:    ResearchAgent     | None = None,
        fundamental_agent: FundamentalAgent  | None = None,
        technical_agent:   TechnicalAgent    | None = None,
        report_agent:      ReportAgent       | None = None,
        sentiment_analyser: SentimentAnalyser | None = None,
    ) -> None:
        self._store             = job_store
        self._data_agent        = data_agent        or DataAgent()
        self._research_agent    = research_agent    or ResearchAgent()
        self._fundamental_agent = fundamental_agent or FundamentalAgent()
        self._technical_agent   = technical_agent   or TechnicalAgent()
        self._report_agent      = report_agent      or ReportAgent()
        self._sentiment         = sentiment_analyser or SentimentAnalyser()

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self, ticker: str, job_id: str) -> None:
        """
        Execute the full analysis pipeline for ``ticker`` and store the result.

        This coroutine is designed to be called as a FastAPI ``BackgroundTask``.
        It never raises — all errors are caught and written into the job store
        so the polling ``GET /api/report/{job_id}`` always gets a response.

        Parameters
        ----------
        ticker : str
            The stock ticker symbol (will be upper-cased here as a safety net).
        job_id : str
            UUID string created by the route handler via ``JobStore.create_job``.
        """
        ticker = ticker.upper().strip()
        logger.info("Orchestrator starting", extra={"ticker": ticker, "job_id": job_id})

        try:
            await self._store.update_job(job_id, status="running", current_step="Fetching data")
            payload = await self._execute(ticker, job_id)
            await self._store.update_job(
                job_id,
                status="complete",
                current_step=None,
                result=payload,
            )
            logger.info("Orchestrator complete", extra={"ticker": ticker, "job_id": job_id})

        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            logger.error(
                "Orchestrator failed",
                extra={"ticker": ticker, "job_id": job_id, "error": error_msg},
            )
            await self._store.update_job(
                job_id,
                status="error",
                current_step=None,
                error=error_msg,
            )

    # ── Private pipeline ──────────────────────────────────────────────────────

    async def _execute(self, ticker: str, job_id: str) -> dict:
        """
        Run every agent, assemble, and return the ``ReportPayload`` dict.

        Raises on unrecoverable errors (e.g. unknown ticker from DataAgent).
        Individual agent failures produce warnings and neutral placeholders.
        """
        warnings: list[str] = []

        # ── Step 1: DataAgent ─────────────────────────────────────────────────
        # Raises ValueError for unknown tickers; let it propagate to run().
        data_result = await self._data_agent.run(ticker=ticker)
        stock_data: StockData = data_result["stock_data"]
        sources_used: list[str] = data_result.get("sources_used", [])
        warnings.extend(data_result.get("warnings", []))

        # ── Step 2: ResearchAgent ─────────────────────────────────────────────
        await self._store.update_job(job_id, current_step="Fetching news")
        research_result = await self._research_agent.run(ticker=ticker)
        news_items: list[dict] = research_result.get("news_items", [])
        warnings.extend(research_result.get("warnings", []))

        # ── Step 3: FundamentalAgent ──────────────────────────────────────────
        await self._store.update_job(job_id, current_step="Analysing fundamentals")
        fund_result = await self._fundamental_agent.run(ticker=ticker, stock_data=stock_data)
        fundamental_result: FundamentalResult = fund_result["fundamental_result"]
        if fund_result.get("status") == "error":
            warnings.append(f"Fundamental analysis error: {fund_result.get('error', 'unknown')}")

        # ── Step 4: TechnicalAgent ────────────────────────────────────────────
        await self._store.update_job(job_id, current_step="Analysing technical indicators")
        tech_result = await self._technical_agent.run(ticker=ticker, stock_data=stock_data)
        technical_result: TechnicalResult = tech_result["technical_result"]
        if tech_result.get("status") == "error":
            warnings.append(f"Technical analysis error: {tech_result.get('error', 'unknown')}")

        # Propagate per-analyser warnings.
        warnings.extend(getattr(fundamental_result, "warnings", []))
        warnings.extend(getattr(technical_result,   "warnings", []))

        # ── Step 5: Sentiment ─────────────────────────────────────────────────
        await self._store.update_job(job_id, current_step="Scoring sentiment")
        sentiment_result: SentimentResult = self._sentiment.analyse(ticker, news_items)

        # ── Score & recommendation ────────────────────────────────────────────
        overall_score  = _compute_overall_score(
            fundamental_result.score,
            technical_result.score,
            sentiment_result.score,
        )
        recommendation = _score_to_recommendation(overall_score)

        # ── Step 6: ReportAgent ───────────────────────────────────────────────
        await self._store.update_job(job_id, current_step="Generating report")
        analysis_result = AnalysisResult(
            ticker=ticker,
            fundamental=fundamental_result,
            technical=technical_result,
            sentiment=sentiment_result,
            overall_score=overall_score,
            recommendation=recommendation,
            sources_used=sources_used,
            warnings=list(dict.fromkeys(warnings)),  # deduplicate, preserve order
        )
        report_result = await self._report_agent.run(analysis_result=analysis_result)
        warnings.extend(report_result.get("warnings", []))

        # ── Assemble ReportPayload dict ───────────────────────────────────────
        return {
            "job_id":                  job_id,
            "ticker":                  ticker,
            "generated_at":            datetime.now(timezone.utc).isoformat(),
            "status":                  "complete",
            "recommendation":          report_result.get("recommendation", recommendation),
            "rationale":               report_result.get("rationale", ""),
            "executive_summary":       report_result.get("executive_summary", ""),
            "fundamental_result":      fundamental_result,
            "technical_result":        technical_result,
            "sentiment_result":        sentiment_result,
            "news_items":              news_items,
            "fundamental_explanation": report_result.get("fundamental_explanation", ""),
            "technical_explanation":   report_result.get("technical_explanation", ""),
            "sources_used":            sources_used,
            "warnings":                list(dict.fromkeys(warnings)),
            "disclaimer":              _DISCLAIMER,
            "pdf_path":                None,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _compute_overall_score(
    fundamental_score: float,
    technical_score:   float,
    sentiment_score:   float,
) -> float:
    """
    Compute the weighted composite score (0–100).

    Weights: fundamental 40 %, technical 40 %, sentiment 20 %.
    """
    raw = (
        fundamental_score * _W_FUNDAMENTAL
        + technical_score * _W_TECHNICAL
        + sentiment_score * _W_SENTIMENT
    )
    return round(max(0.0, min(100.0, raw)), 2)


def _score_to_recommendation(score: float) -> str:
    """Return ``"Buy"``, ``"Hold"``, or ``"Sell"`` for the given composite score."""
    if score >= _BUY_THRESHOLD:
        return "Buy"
    if score <= _SELL_THRESHOLD:
        return "Sell"
    return "Hold"

"""
Report agent — generates plain-language explanations via the Groq LLM.

``ReportAgent.run(analysis_result=...)`` builds a structured prompt from the
``AnalysisResult`` object and calls the Groq API via ``LLMClient``.  The LLM
is instructed to respond with a JSON object containing:

    executive_summary        : 2–3 sentence overview of the stock
    recommendation           : "Buy" | "Hold" | "Sell"
    rationale                : 3-sentence justification for the recommendation
    fundamental_explanation  : plain-language summary of fundamentals (≤ 150 words)
    technical_explanation    : plain-language summary of technicals   (≤ 150 words)

Disclaimer enforcement (plan §"Disclaimer enforcement"):
    The disclaimer "For informational purposes only. Not financial advice." is
    baked into every prompt so the LLM cannot omit it from its output.

Fallback (plan §"Groq LLM fallback template"):
    When the Groq API is unavailable (missing key, network error, rate limit,
    or malformed JSON response) the agent returns a canned template rather than
    failing.  A ``WarningFlags`` entry is added to the warnings list so the UI
    can display an appropriate message.

Return dict keys
────────────────
    status                  : "ok"  (always — errors surface as warnings)
    executive_summary       : str
    recommendation          : str   "Buy" | "Hold" | "Sell"
    rationale               : str
    fundamental_explanation : str
    technical_explanation   : str
    warnings                : list[str]
"""

from __future__ import annotations

import json
import re

from app.agents.base_agent import BaseAgent
from app.logger import get_logger
from app.schemas.analysis import AnalysisResult

logger = get_logger(__name__)

# ── Fallback template (plan §"Groq LLM fallback template") ───────────────────

GROQ_FALLBACK_TEMPLATE: dict[str, str] = {
    "recommendation": "Hold",
    "rationale": (
        "Automated narrative generation is temporarily unavailable. "
        "The raw metrics are shown below so you can review the data directly. "
        "Please try again later for a full plain-language explanation."
    ),
    "fundamental_explanation": (
        "Plain-language explanation unavailable. See the metrics table above."
    ),
    "technical_explanation": (
        "Plain-language explanation unavailable. See the indicator table above."
    ),
}

# Warning added to the payload whenever the fallback is used.
_FALLBACK_WARNING = (
    "AI-generated explanation unavailable — raw data shown only."
)

# Valid recommendation values; used to validate the LLM response.
_VALID_RECOMMENDATIONS = {"Buy", "Hold", "Sell"}


class ReportAgent(BaseAgent):
    """
    Generates plain-language analysis text for a ticker using the Groq LLM.

    Accepts an optional ``llm_client`` argument so the LLM call can be
    replaced with a test double without patching module globals.
    """

    def __init__(self, llm_client=None) -> None:
        """
        Initialise with an optional LLM client.

        When ``llm_client`` is ``None`` the agent imports and instantiates
        ``LLMClient`` lazily at first call so the module can be imported
        even when the Groq SDK is not installed.
        """
        self._llm_client = llm_client

    @property
    def name(self) -> str:
        """Return the display name of this agent."""
        return "ReportAgent"

    async def run(self, *, analysis_result: AnalysisResult) -> dict:
        """
        Generate plain-language report text for the analysis in ``analysis_result``.

        Parameters
        ----------
        analysis_result : AnalysisResult
            Fully assembled analysis object from the orchestrator.

        Returns
        -------
        dict
            Always ``{"status": "ok", ...}`` — LLM failures surface as warnings
            and the fallback template is returned so the pipeline never stalls.
        """
        ticker = analysis_result.ticker
        logger.info("ReportAgent starting", extra={"ticker": ticker})

        # ── Lazy-initialise the LLM client ────────────────────────────────────
        if self._llm_client is None:
            from app.core.llm_client import LLMClient
            self._llm_client = LLMClient()

        # ── Build and send the prompt ─────────────────────────────────────────
        prompt = _build_prompt(analysis_result)
        warnings: list[str] = []

        try:
            raw_text = await self._llm_client.generate(prompt)
            parsed   = _parse_response(raw_text)
            logger.info("ReportAgent LLM call succeeded", extra={"ticker": ticker})

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ReportAgent LLM call failed — using fallback",
                extra={"ticker": ticker, "error": str(exc), "type": type(exc).__name__},
            )
            parsed = _apply_fallback()
            warnings.append(_FALLBACK_WARNING)

        return {
            "status":                  "ok",
            "executive_summary":       parsed.get("executive_summary", ""),
            "recommendation":          parsed.get("recommendation",    GROQ_FALLBACK_TEMPLATE["recommendation"]),
            "rationale":               parsed.get("rationale",         GROQ_FALLBACK_TEMPLATE["rationale"]),
            "fundamental_explanation": parsed.get("fundamental_explanation", GROQ_FALLBACK_TEMPLATE["fundamental_explanation"]),
            "technical_explanation":   parsed.get("technical_explanation",   GROQ_FALLBACK_TEMPLATE["technical_explanation"]),
            "warnings":                warnings,
        }


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_prompt(ar: AnalysisResult) -> str:
    """
    Construct the Groq prompt from an ``AnalysisResult``.

    The prompt includes:
    - Key fundamental metrics (P/E, EPS, profit margin, revenue growth)
    - Key technical signals (RSI, MACD crossover, price vs SMAs, score)
    - Sentiment summary (label + score)
    - The computed overall score and recommendation
    - Hard-coded disclaimer so the LLM cannot omit it
    - Explicit JSON response schema the LLM must follow
    """
    fund = ar.fundamental
    tech = ar.technical
    sent = ar.sentiment

    # Format a metric value safely.
    def _fmt(v, unit="", default="N/A"):
        if v is None:
            return default
        return f"{v}{unit}"

    fundamental_section = (
        f"  P/E ratio:       {_fmt(fund.pe_ratio.value, 'x')}\n"
        f"  EPS:             {_fmt(fund.eps.value, '$')}\n"
        f"  P/B ratio:       {_fmt(fund.pb_ratio.value, 'x')}\n"
        f"  Debt/Equity:     {_fmt(fund.debt_to_equity.value, 'x')}\n"
        f"  Profit margin:   {_fmt(fund.profit_margin.value, '%')}\n"
        f"  Revenue growth:  {_fmt(fund.revenue_growth.value, '%')}\n"
        f"  Dividend yield:  {_fmt(fund.dividend_yield.value, '%')}\n"
        f"  Fundamental score: {fund.score}/100"
    )

    technical_section = (
        f"  Latest close:    {_fmt(tech.latest_close, '$')}\n"
        f"  SMA 20:          {_fmt(tech.latest_sma_20, '$')}\n"
        f"  SMA 50:          {_fmt(tech.latest_sma_50, '$')}\n"
        f"  SMA 200:         {_fmt(tech.latest_sma_200, '$')}\n"
        f"  RSI(14):         {_fmt(tech.latest_rsi)}\n"
        f"  MACD:            {_fmt(tech.latest_macd)}\n"
        f"  MACD Signal:     {_fmt(tech.latest_macd_signal)}\n"
        f"  Technical score: {tech.score}/100"
    )

    sentiment_section = (
        f"  Sentiment label: {sent.label}\n"
        f"  Sentiment score: {sent.score}/100\n"
        f"  Headlines:       {sent.positive_count} positive, "
        f"{sent.neutral_count} neutral, {sent.negative_count} negative"
    )

    prompt = f"""You are a beginner-friendly stock analysis assistant.
Analyse the following data for ticker {ar.ticker} and respond ONLY with a valid JSON object.

DISCLAIMER: {ar.disclaimer}

=== FUNDAMENTAL DATA ===
{fundamental_section}

=== TECHNICAL DATA ===
{technical_section}

=== SENTIMENT DATA ===
{sentiment_section}

=== OVERALL ===
  Overall score:     {ar.overall_score}/100
  Recommendation:    {ar.recommendation}

=== RESPONSE FORMAT ===
Respond with ONLY this JSON object — no markdown, no extra text:
{{
  "executive_summary":       "<2–3 sentence overview of this stock for a beginner>",
  "recommendation":          "<Buy|Hold|Sell>",
  "rationale":               "<exactly 3 sentences explaining the recommendation>",
  "fundamental_explanation": "<plain-language explanation of the fundamentals, max 150 words>",
  "technical_explanation":   "<plain-language explanation of the technical indicators, max 150 words>"
}}

Important rules:
- recommendation must be exactly one of: Buy, Hold, Sell
- Do NOT include the disclaimer in the JSON values
- Write for a complete beginner — avoid jargon, explain any terms you use
- For informational purposes only. Not financial advice."""

    return prompt


# ── Response parser ───────────────────────────────────────────────────────────


def _parse_response(raw: str) -> dict:
    """
    Extract the JSON object from the LLM's raw text response.

    The LLM may wrap the JSON in markdown code fences or add preamble text.
    This function strips those and parses the first JSON object it finds.
    Falls back to the GROQ_FALLBACK_TEMPLATE if parsing fails or if the
    recommendation field contains an unexpected value.

    Raises ``ValueError`` when no valid JSON can be extracted so the caller
    can catch it and apply the fallback.
    """
    # Strip markdown code fences (```json ... ``` or ``` ... ```).
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

    # Find the outermost JSON object.
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {raw[:200]!r}")

    parsed = json.loads(match.group())

    # Validate recommendation; reset to fallback value if unexpected.
    rec = parsed.get("recommendation", "")
    if rec not in _VALID_RECOMMENDATIONS:
        logger.warning("LLM returned unexpected recommendation %r — resetting to Hold", rec)
        parsed["recommendation"] = "Hold"

    return parsed


def _apply_fallback() -> dict:
    """Return a copy of ``GROQ_FALLBACK_TEMPLATE`` with an empty executive_summary."""
    return {**GROQ_FALLBACK_TEMPLATE, "executive_summary": ""}

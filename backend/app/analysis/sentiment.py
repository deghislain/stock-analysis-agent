"""
Sentiment analysis module.

``SentimentAnalyser.analyse(ticker, news_items)`` classifies each news
headline as Positive, Neutral, or Negative.

When the ``transformers`` package is installed and ``ProsusAI/finbert``
can be loaded, each headline is scored by FinBERT — a BERT model
fine-tuned on financial news text.  This gives context-aware sentiment
that handles mixed headlines (e.g. "record high despite concerns") far
better than keyword matching.

When ``transformers`` is not installed, or the model cannot be loaded,
the module falls back to the original keyword-matching approach
transparently.  No exception is raised in either case.

Each news item is a dict that may contain any of these text fields:
    ``title``, ``body``, ``snippet``, ``description``

FinBERT scoring
───────────────
FinBERT returns one of three labels per text: ``positive``, ``neutral``,
``negative``.  Per-headline polarity:
    positive → +1,  neutral → 0,  negative → -1

Keyword-matching fallback scoring
──────────────────────────────────
    +1 point for every positive keyword hit
    -1 point for every negative keyword hit

Overall score (0–100) for both paths:
    score = clamp(50 + net_polarity * SCALE_FACTOR, 0, 100)

Where SCALE_FACTOR = 5.

Label thresholds:
    score >= 60  → "Positive"
    score <= 40  → "Negative"
    otherwise    → "Neutral"
"""

from __future__ import annotations

from app.logger import get_logger
from app.schemas.analysis import SentimentResult

logger = get_logger(__name__)

# How much each net sentiment unit shifts the score away from 50.
_SCALE_FACTOR = 5

# Module-level cache for the FinBERT pipeline.
# Populated lazily on first call to _finbert_score(); stays None if
# transformers is not installed or model loading fails.
_finbert_pipeline = None
_finbert_checked   = False   # ensures we only attempt loading once

# ── Keyword lists ─────────────────────────────────────────────────────────────
# Used as the fallback when FinBERT is unavailable.
# Kept intentionally broad so they catch common financial headlines without
# false-precision.  Ordered alphabetically for easy maintenance.

_POSITIVE_WORDS: frozenset[str] = frozenset({
    "accelerat", "acqui", "ahead", "analyst upgrade", "beat", "boom",
    "breakthrough", "bullish", "buy", "confident", "deal", "dividend",
    "earnings beat", "exceed", "expansion", "gain", "grew", "growth",
    "high", "hike", "improve", "increase", "invest", "launch", "milestone",
    "momentum", "opportunit", "optimis", "outperform", "partner", "profit",
    "raise", "rally", "rebound", "record", "recovery", "revenue growth",
    "rise", "robust", "soar", "strong", "success", "surge", "top",
    "upsid", "upgrad", "win",
})

_NEGATIVE_WORDS: frozenset[str] = frozenset({
    "bankrupt", "bearish", "below expect", "concern", "crash", "cut",
    "decline", "default", "deficit", "delay", "disappoint", "divest",
    "doubt", "downgrad", "drop", "earn miss", "fail", "fall", "fear",
    "fine", "fraud", "hit", "investigation", "laid off", "layoff",
    "lawsuit", "loss", "loss", "lower", "miss", "negative", "outage",
    "penalt", "probe", "recall", "restructur", "risk", "scandal",
    "sell", "shortfall", "shrink", "slump", "struggle", "sue", "suspend",
    "uncertain", "underperform", "warn", "weak", "withdraw", "worst",
})


class SentimentAnalyser:
    """Classifies news headlines with FinBERT (or keyword fallback) to produce a sentiment score."""

    def analyse(self, ticker: str, news_items: list[dict]) -> SentimentResult:
        """
        Score each item in ``news_items`` and return an aggregated ``SentimentResult``.

        Each dict in ``news_items`` should have at least one of:
        ``title``, ``body``, ``snippet``, ``description``.
        Items that contain none of these fields are counted in
        ``headlines_analysed`` but contribute 0 to the net score.
        An empty list produces a perfectly neutral result (score=50).
        """
        positive_count = 0
        neutral_count  = 0
        negative_count = 0
        net_polarity   = 0

        for item in news_items:
            text = _extract_text(item)
            net = _score_item(text)

            if net > 0:
                positive_count += 1
            elif net < 0:
                negative_count += 1
            else:
                neutral_count += 1

            net_polarity += net

        headlines_analysed = len(news_items)
        score = _net_to_score(net_polarity)
        label = _score_to_label(score)

        logger.debug(
            "Sentiment analysis complete",
            extra={
                "ticker": ticker,
                "headlines": headlines_analysed,
                "positive": positive_count,
                "neutral": neutral_count,
                "negative": negative_count,
                "score": score,
                "label": label,
            },
        )

        return SentimentResult(
            ticker=ticker,
            positive_count=positive_count,
            neutral_count=neutral_count,
            negative_count=negative_count,
            score=score,
            label=label,
            headlines_analysed=headlines_analysed,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_text(item: dict) -> str:
    """
    Concatenate all available text fields from a news item into one lowercase string.

    Checks ``title``, ``body``, ``snippet``, and ``description`` in that order,
    joining whichever are present with a space separator.
    """
    parts: list[str] = []
    for key in ("title", "body", "snippet", "description"):
        val = item.get(key)
        if val and isinstance(val, str):
            parts.append(val.lower())
    return " ".join(parts)


def _score_item(text: str) -> int:
    """
    Return a polarity integer (+1, 0, or -1) for a single headline text.

    Uses FinBERT when available; falls back to keyword matching otherwise.
    Empty text always returns 0 (neutral).
    """
    if not text:
        return 0

    finbert = _get_finbert()
    if finbert is not None:
        return _finbert_score(finbert, text)

    pos_hits, neg_hits = _score_text(text)
    net = pos_hits - neg_hits
    # Clamp to -1 / 0 / +1 to keep the same polarity scale as FinBERT.
    if net > 0:
        return 1
    if net < 0:
        return -1
    return 0


def _get_finbert():
    """
    Return the FinBERT pipeline, loading it once on first call.

    Returns ``None`` if ``transformers`` is not installed or the model
    cannot be loaded for any reason (network unavailable, disk full, etc.).
    The result is cached so the model is only loaded once per process.
    """
    global _finbert_pipeline, _finbert_checked
    if _finbert_checked:
        return _finbert_pipeline

    _finbert_checked = True
    try:
        from transformers import pipeline as hf_pipeline  # type: ignore[import]
        _finbert_pipeline = hf_pipeline(
            "text-classification",
            model="ProsusAI/finbert",
        )
        logger.info("FinBERT sentiment model loaded successfully")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "FinBERT unavailable — falling back to keyword sentiment",
            extra={"reason": str(exc)},
        )
        _finbert_pipeline = None

    return _finbert_pipeline


def _finbert_score(finbert_pipeline, text: str) -> int:
    """
    Run ``text`` through the FinBERT pipeline and return +1, 0, or -1.

    FinBERT truncates inputs longer than 512 tokens internally.
    Returns 0 (neutral) if the pipeline raises for any reason.
    """
    try:
        # pipeline() returns a list of dicts: [{"label": "positive", "score": 0.98}]
        result = finbert_pipeline(text[:512], truncation=True)
        label: str = result[0]["label"].lower()
        if label == "positive":
            return 1
        if label == "negative":
            return -1
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("FinBERT inference failed for item", extra={"error": str(exc)})
        return 0


def _score_text(text: str) -> tuple[int, int]:
    """
    Count positive and negative keyword hits in ``text``.

    Returns ``(positive_hits, negative_hits)``.  Each keyword in the word-list
    is a substring match against the already-lowercased ``text``.
    """
    pos = sum(1 for kw in _POSITIVE_WORDS if kw in text)
    neg = sum(1 for kw in _NEGATIVE_WORDS if kw in text)
    return pos, neg


def _net_to_score(net_polarity: int) -> float:
    """
    Convert a net polarity integer to a 0–100 score centred on 50.

    Each unit of net polarity shifts the score by ``_SCALE_FACTOR`` points.
    The result is clamped to [0, 100].
    """
    raw = 50.0 + net_polarity * _SCALE_FACTOR
    return round(max(0.0, min(100.0, raw)), 2)


def _score_to_label(score: float) -> str:
    """Return ``"Positive"``, ``"Neutral"``, or ``"Negative"`` for the given score."""
    if score >= 60.0:
        return "Positive"
    if score <= 40.0:
        return "Negative"
    return "Neutral"

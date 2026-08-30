"""
Sentiment analysis module.

``SentimentAnalyser.analyse(ticker, news_items)`` classifies each news
headline as Positive, Neutral, or Negative using a keyword-matching
approach — no external model or API call is needed.

Each news item is a dict that may contain any of these text fields:
    ``title``, ``body``, ``snippet``, ``description``

The text is lowercased and scanned against two word-lists:

    POSITIVE_WORDS  — growth, beat, record, upgrade, bullish, …
    NEGATIVE_WORDS  — loss, miss, downgrade, recall, lawsuit, …

Scoring
───────
Per headline:
    +1 point for every positive keyword hit
    -1 point for every negative keyword hit

Net polarity = sum of all per-headline net scores.

Overall score (0–100):
    score = clamp(50 + net_polarity * SCALE_FACTOR, 0, 100)

Where SCALE_FACTOR = 5 (each net unit of sentiment moves the score ±5 pts).
This keeps the range usable even for small news sets (< 10 items).

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

# ── Keyword lists ─────────────────────────────────────────────────────────────
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
    """Classifies news headlines with keyword matching to produce a sentiment score."""

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
            pos_hits, neg_hits = _score_text(text)
            net = pos_hits - neg_hits

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

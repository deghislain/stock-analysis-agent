"""
Pure ranking logic for the Portfolio module (Sub-Task P3).

Public API
──────────
    compute_ranking(stocks) -> list[dict]

        Rank a list of ``PortfolioStock`` ORM objects by composite overall
        score and return them as plain dicts ready for:
          - serialisation into ``RankingEntryOut`` by the route handler, and
          - insertion into ``RankingEntry`` rows by ``crud.save_ranking_snapshot``.

Sort key
────────
    Primary   : overall_score  — descending (highest score = rank 1)
    Secondary : ticker         — ascending  (A < Z, stable tiebreaker)
    Null rule : stocks whose overall_score is None are always placed at the
                *bottom* of the ranking, sorted among themselves alphabetically
                by ticker.

Design notes
────────────
- ``compute_ranking`` is a *pure function*: no database queries, no HTTP calls,
  no side effects.  Input is a plain list; output is a plain list of dicts.
  This makes it trivially unit-testable with mock objects.
- ``fundamental_score``, ``technical_score``, and ``sentiment_score`` are NOT
  stored on ``PortfolioStock`` rows (only ``overall_score`` is cached there).
  The three sub-scores therefore default to ``None`` in the output dicts for
  the live ranking view.  They are populated with real values when the caller
  is ``crud.save_ranking_snapshot`` (which receives them from the orchestrator
  report at refresh time).
- The function accepts any object with the attributes ``ticker``,
  ``overall_score``, and ``recommendation`` — duck-typed so tests can pass
  simple ``SimpleNamespace`` or dataclass mocks without importing ORM models.
"""

from __future__ import annotations

from typing import Any


def compute_ranking(stocks: list[Any]) -> list[dict]:
    """
    Sort ``stocks`` by performance and return a ranked list of plain dicts.

    Parameters
    ----------
    stocks:
        A list of objects that expose at minimum the attributes:
        ``ticker`` (str), ``overall_score`` (float | None),
        ``recommendation`` (str | None).
        Typically a list of ``PortfolioStock`` ORM instances, but any
        duck-typed object with these attributes is accepted.

    Returns
    -------
    list[dict]
        One dict per stock, ordered rank 1 … N.  Each dict has the keys:

        ``rank``              — 1-based integer position.
        ``ticker``            — upper-case ticker symbol.
        ``overall_score``     — float 0–100 or ``None``.
        ``fundamental_score`` — always ``None`` here (not stored on
                                PortfolioStock; populated by the snapshot
                                writer at refresh time).
        ``technical_score``   — always ``None`` here (same reason).
        ``sentiment_score``   — always ``None`` here (same reason).
        ``recommendation``    — ``"Buy"`` / ``"Hold"`` / ``"Sell"`` or ``None``.

    Sort key
    --------
    Stocks with a non-null ``overall_score`` are sorted:
      1. overall_score DESC  (higher score = better rank)
      2. ticker ASC          (alphabetical tiebreaker for equal scores)

    Stocks with ``overall_score = None`` follow all scored stocks, sorted
    alphabetically among themselves.  They receive a "⚠ Data unavailable"
    label on the frontend — the route layer handles that display logic.

    Examples
    --------
    >>> class S:
    ...     def __init__(self, ticker, score, rec="Hold"):
    ...         self.ticker = ticker
    ...         self.overall_score = score
    ...         self.recommendation = rec
    >>> result = compute_ranking([S("TSLA", 40), S("AAPL", 80), S("MSFT", 80)])
    >>> [e["ticker"] for e in result]
    ['AAPL', 'MSFT', 'TSLA']
    >>> [e["rank"] for e in result]
    [1, 2, 3]
    """
    if not stocks:
        return []

    # Partition into scored and unscored groups.
    scored = [s for s in stocks if s.overall_score is not None]
    unscored = [s for s in stocks if s.overall_score is None]

    # Sort scored stocks: overall_score DESC, then ticker ASC.
    scored_sorted = sorted(scored, key=lambda s: (-s.overall_score, s.ticker))

    # Sort unscored stocks: ticker ASC only.
    unscored_sorted = sorted(unscored, key=lambda s: s.ticker)

    ordered = scored_sorted + unscored_sorted

    return [
        {
            "rank": idx + 1,
            "ticker": s.ticker,
            "overall_score": s.overall_score,
            # Sub-scores are not stored on PortfolioStock — callers that need
            # them (e.g. save_ranking_snapshot called from the scheduler) must
            # inject the values from the fresh ReportPayload before passing
            # entries to crud.save_ranking_snapshot().
            "fundamental_score": None,
            "technical_score": None,
            "sentiment_score": None,
            "recommendation": s.recommendation,
        }
        for idx, s in enumerate(ordered)
    ]

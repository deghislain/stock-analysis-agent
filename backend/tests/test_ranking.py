"""
Unit tests for ``app.portfolio.ranking.compute_ranking`` — Sub-Task P3, Todo 3.

All tests use plain ``SimpleNamespace`` objects as stock mocks so this module
has no database dependency and runs in milliseconds.

Coverage
────────
    test_normal_sort                — descending score order
    test_equal_scores_alpha         — alpha tiebreaker for equal overall_score
    test_null_scores_last           — null-score stocks follow all scored stocks
    test_null_scores_alpha_among_themselves — null stocks sorted A→Z
    test_mixed_scored_and_null      — scored + null in one list
    test_all_null                   — list where every stock has score = None
    test_empty_list                 — empty input → empty output
    test_single_stock               — single stock → rank 1
    test_rank_values                — rank integers are 1-based and contiguous
    test_output_keys                — every dict has exactly the required keys
    test_sub_scores_always_none     — fundamental/technical/sentiment = None
    test_recommendation_preserved   — recommendation field copied from input
    test_pure_function_no_mutation  — input list not mutated by the call
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.portfolio.ranking import compute_ranking


# ── Helpers ───────────────────────────────────────────────────────────────────


def _stock(ticker: str, score: float | None, rec: str = "Hold") -> SimpleNamespace:
    """Build a minimal mock stock object accepted by compute_ranking."""
    return SimpleNamespace(ticker=ticker, overall_score=score, recommendation=rec)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_normal_sort():
    """Stocks are ranked descending by overall_score."""
    stocks = [
        _stock("TSLA", 30.0, "Sell"),
        _stock("MSFT", 80.0, "Buy"),
        _stock("AAPL", 60.0, "Buy"),
    ]
    result = compute_ranking(stocks)
    assert [e["ticker"] for e in result] == ["MSFT", "AAPL", "TSLA"]
    assert [e["overall_score"] for e in result] == [80.0, 60.0, 30.0]


def test_equal_scores_alpha():
    """Equal overall_scores are broken alphabetically by ticker (A < Z)."""
    stocks = [
        _stock("TSLA", 70.0),
        _stock("AAPL", 70.0),
        _stock("MSFT", 70.0),
    ]
    result = compute_ranking(stocks)
    assert [e["ticker"] for e in result] == ["AAPL", "MSFT", "TSLA"]


def test_null_scores_last():
    """Stocks with overall_score=None are placed after all scored stocks."""
    stocks = [
        _stock("NVDA", None),
        _stock("AAPL", 60.0),
        _stock("GOOG", None),
    ]
    result = compute_ranking(stocks)
    # AAPL (scored) must come before GOOG and NVDA (both null)
    tickers = [e["ticker"] for e in result]
    assert tickers[0] == "AAPL"
    assert set(tickers[1:]) == {"GOOG", "NVDA"}


def test_null_scores_alpha_among_themselves():
    """Null-score stocks are sorted alphabetically among themselves."""
    stocks = [
        _stock("TSLA", None),
        _stock("AAPL", None),
        _stock("MSFT", None),
    ]
    result = compute_ranking(stocks)
    assert [e["ticker"] for e in result] == ["AAPL", "MSFT", "TSLA"]


def test_mixed_scored_and_null():
    """Integration: scored stocks first (desc score, alpha tie), null stocks after (alpha)."""
    stocks = [
        _stock("ZZZZ", None),
        _stock("AAAA", None),
        _stock("MSFT", 80.0, "Buy"),
        _stock("GOOG", 80.0, "Buy"),   # tie with MSFT — GOOG < MSFT alpha
        _stock("TSLA", 30.0, "Sell"),
    ]
    result = compute_ranking(stocks)
    assert [e["ticker"] for e in result] == ["GOOG", "MSFT", "TSLA", "AAAA", "ZZZZ"]


def test_all_null():
    """When every stock has overall_score=None, all are returned sorted alpha."""
    stocks = [_stock("TSLA", None), _stock("AAPL", None)]
    result = compute_ranking(stocks)
    assert len(result) == 2
    assert [e["ticker"] for e in result] == ["AAPL", "TSLA"]
    assert all(e["overall_score"] is None for e in result)


def test_empty_list():
    """Empty input returns empty output without raising."""
    assert compute_ranking([]) == []


def test_single_stock():
    """A single stock is ranked 1 regardless of its score."""
    result = compute_ranking([_stock("AAPL", 55.0, "Hold")])
    assert len(result) == 1
    assert result[0]["rank"] == 1
    assert result[0]["ticker"] == "AAPL"


def test_rank_values_are_contiguous_from_one():
    """rank values form the sequence 1, 2, 3, … N."""
    stocks = [_stock(t, s) for t, s in [("A", 90), ("B", 70), ("C", 50), ("D", None)]]
    result = compute_ranking(stocks)
    assert [e["rank"] for e in result] == [1, 2, 3, 4]


def test_output_keys():
    """Every entry dict exposes exactly the seven required keys."""
    required = {
        "rank", "ticker", "overall_score",
        "fundamental_score", "technical_score", "sentiment_score",
        "recommendation",
    }
    result = compute_ranking([_stock("AAPL", 70.0)])
    assert set(result[0].keys()) == required


def test_sub_scores_always_none():
    """
    fundamental_score, technical_score, and sentiment_score are always None
    in compute_ranking output — they are not stored on PortfolioStock.
    """
    result = compute_ranking([_stock("AAPL", 70.0)])
    assert result[0]["fundamental_score"] is None
    assert result[0]["technical_score"] is None
    assert result[0]["sentiment_score"] is None


def test_recommendation_preserved():
    """recommendation from the input stock is copied verbatim into the entry."""
    stocks = [
        _stock("AAPL", 75.0, "Buy"),
        _stock("TSLA", 35.0, "Sell"),
        _stock("GOOG", None, None),
    ]
    result = compute_ranking(stocks)
    recs = {e["ticker"]: e["recommendation"] for e in result}
    assert recs["AAPL"] == "Buy"
    assert recs["TSLA"] == "Sell"
    assert recs["GOOG"] is None


def test_pure_function_no_mutation():
    """compute_ranking must not mutate the input list or its objects."""
    stocks = [_stock("TSLA", 30.0), _stock("AAPL", 80.0)]
    original_order = [s.ticker for s in stocks]
    original_scores = [s.overall_score for s in stocks]

    compute_ranking(stocks)

    assert [s.ticker for s in stocks] == original_order
    assert [s.overall_score for s in stocks] == original_scores

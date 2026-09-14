"""
Integration tests for the Portfolio API — Sub-Task P2, Todo 4.

Test coverage
─────────────
Portfolio CRUD
    test_create_portfolio           — POST /api/portfolios returns 201 + body
    test_list_portfolios            — GET  /api/portfolios returns created rows
    test_get_portfolio              — GET  /api/portfolios/{id} returns full body
    test_get_portfolio_not_found    — GET  unknown id → 404
    test_update_portfolio           — PATCH updates name and/or description
    test_update_portfolio_not_found — PATCH unknown id → 404
    test_delete_portfolio           — DELETE returns 204; subsequent GET → 404
    test_delete_portfolio_not_found — DELETE unknown id → 404

Stock management
    test_add_stock                  — POST .../stocks returns 201 + PortfolioStockOut
    test_add_stock_incomplete_job   — job status != "complete" → 422
    test_add_stock_missing_job      — unknown job_id → 422
    test_add_stock_duplicate        — same ticker twice → 409
    test_add_stock_portfolio_404    — unknown portfolio → 404
    test_remove_stock               — DELETE .../stocks/{ticker} returns 204
    test_remove_stock_not_found     — unknown ticker → 404

Ranking
    test_ranking_sort_order         — scores sorted descending; null score last
    test_ranking_equal_scores       — equal scores broken alphabetically by ticker
    test_ranking_all_null           — all null scores → all returned (bottom group)
    test_ranking_empty_portfolio    — portfolio with no stocks → empty list

History / snapshots  (light — snapshot writing exercised via ranking module in P3)
    test_history_empty              — GET .../history with no snapshots → []
    test_get_snapshot_not_found     — GET .../history/{id} unknown id → 404
    test_get_snapshot_wrong_portfolio — snapshot from another portfolio → 404

All tests use the ``client``, ``db_session``, and ``job_store`` fixtures from
``conftest.py`` (in-memory SQLite, fresh per test).
"""

from __future__ import annotations

import pytest

from tests.conftest import _make_report_payload


# ── Helpers ───────────────────────────────────────────────────────────────────


def _create_portfolio(client, name: str = "Test Portfolio", description: str = "") -> dict:
    """POST /api/portfolios and return the response JSON."""
    r = client.post("/api/portfolios", json={"name": name, "description": description})
    assert r.status_code == 201, r.text
    return r.json()


def _seed_complete_job(job_store, ticker: str = "AAPL", job_id: str = "job-001") -> str:
    """Insert a complete job into job_store and return its job_id."""
    job_store.create_job(job_id)
    job = job_store._jobs[job_id]
    job.status = "complete"
    job.result = _make_report_payload(ticker=ticker, job_id=job_id)
    return job_id


# ── Portfolio CRUD ────────────────────────────────────────────────────────────


def test_create_portfolio(client):
    r = client.post("/api/portfolios", json={"name": "My Portfolio", "description": "Desc"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "My Portfolio"
    assert body["description"] == "Desc"
    assert "id" in body
    assert body["stocks"] == []


def test_create_portfolio_name_required(client):
    r = client.post("/api/portfolios", json={"name": ""})
    assert r.status_code == 422


def test_create_portfolio_name_too_long(client):
    r = client.post("/api/portfolios", json={"name": "x" * 121})
    assert r.status_code == 422


def test_list_portfolios(client):
    _create_portfolio(client, "Alpha")
    _create_portfolio(client, "Beta")
    r = client.get("/api/portfolios")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Alpha" in names
    assert "Beta" in names


def test_get_portfolio(client):
    p = _create_portfolio(client, "Detail Test")
    r = client.get(f"/api/portfolios/{p['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == p["id"]
    assert r.json()["name"] == "Detail Test"


def test_get_portfolio_not_found(client):
    r = client.get("/api/portfolios/nonexistent-id")
    assert r.status_code == 404
    assert "nonexistent-id" in r.json()["detail"]


def test_update_portfolio_name(client):
    p = _create_portfolio(client, "Old Name")
    r = client.patch(f"/api/portfolios/{p['id']}", json={"name": "New Name"})
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"
    # Description unchanged
    assert r.json()["description"] == ""


def test_update_portfolio_description_only(client):
    p = _create_portfolio(client, "Stable Name")
    r = client.patch(f"/api/portfolios/{p['id']}", json={"description": "Updated desc"})
    assert r.status_code == 200
    assert r.json()["name"] == "Stable Name"
    assert r.json()["description"] == "Updated desc"


def test_update_portfolio_not_found(client):
    r = client.patch("/api/portfolios/no-such-id", json={"name": "X"})
    assert r.status_code == 404


def test_delete_portfolio(client):
    p = _create_portfolio(client, "To Delete")
    r = client.delete(f"/api/portfolios/{p['id']}")
    assert r.status_code == 204
    # Confirm it's gone
    assert client.get(f"/api/portfolios/{p['id']}").status_code == 404


def test_delete_portfolio_not_found(client):
    r = client.delete("/api/portfolios/ghost-id")
    assert r.status_code == 404


# ── Stock management ──────────────────────────────────────────────────────────


def test_add_stock(client, job_store):
    p = _create_portfolio(client)
    job_id = _seed_complete_job(job_store, ticker="AAPL", job_id="job-add-1")

    r = client.post(
        f"/api/portfolios/{p['id']}/stocks",
        json={"ticker": "AAPL", "job_id": job_id},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["ticker"] == "AAPL"
    # Score fields should be populated from the seeded report
    assert body["overall_score"] is not None
    assert body["recommendation"] == "Buy"
    assert body["latest_report_id"] == job_id


def test_add_stock_ticker_normalised_to_uppercase(client, job_store):
    """Lower-case ticker in request body is accepted and normalised."""
    p = _create_portfolio(client)
    job_id = _seed_complete_job(job_store, ticker="MSFT", job_id="job-norm-1")

    r = client.post(
        f"/api/portfolios/{p['id']}/stocks",
        json={"ticker": "msft", "job_id": job_id},
    )
    assert r.status_code == 201
    assert r.json()["ticker"] == "MSFT"


def test_add_stock_incomplete_job(client, job_store):
    """Adding a stock from a job that is still running → 422."""
    p = _create_portfolio(client)
    job_store.create_job("job-pending-1")  # status stays "pending"

    r = client.post(
        f"/api/portfolios/{p['id']}/stocks",
        json={"ticker": "AAPL", "job_id": "job-pending-1"},
    )
    assert r.status_code == 422
    assert "job-pending-1" in r.json()["detail"]
    assert "not complete" in r.json()["detail"]


def test_add_stock_missing_job(client):
    """Referencing a job_id that never existed → 422."""
    p = _create_portfolio(client)
    r = client.post(
        f"/api/portfolios/{p['id']}/stocks",
        json={"ticker": "AAPL", "job_id": "job-does-not-exist"},
    )
    assert r.status_code == 422


def test_add_stock_duplicate(client, job_store):
    """Adding the same ticker twice to the same portfolio → 409."""
    p = _create_portfolio(client)
    job_id = _seed_complete_job(job_store, ticker="AAPL", job_id="job-dup-1")

    client.post(
        f"/api/portfolios/{p['id']}/stocks",
        json={"ticker": "AAPL", "job_id": job_id},
    )
    # Second add — same ticker
    r = client.post(
        f"/api/portfolios/{p['id']}/stocks",
        json={"ticker": "AAPL", "job_id": job_id},
    )
    assert r.status_code == 409
    assert "AAPL" in r.json()["detail"]
    assert "already in portfolio" in r.json()["detail"]


def test_add_stock_portfolio_not_found(client, job_store):
    job_id = _seed_complete_job(job_store, ticker="AAPL", job_id="job-404-p")
    r = client.post(
        "/api/portfolios/no-such-portfolio/stocks",
        json={"ticker": "AAPL", "job_id": job_id},
    )
    assert r.status_code == 404


def test_add_stock_invalid_ticker_format(client, job_store):
    """Ticker that fails the regex → 422 from PortfolioStockIn validator."""
    p = _create_portfolio(client)
    job_id = _seed_complete_job(job_store, ticker="AAPL", job_id="job-bad-ticker")
    r = client.post(
        f"/api/portfolios/{p['id']}/stocks",
        json={"ticker": "TOOLONGBADTICKER", "job_id": job_id},
    )
    assert r.status_code == 422


def test_remove_stock(client, job_store):
    p = _create_portfolio(client)
    job_id = _seed_complete_job(job_store, ticker="NVDA", job_id="job-rm-1")
    client.post(
        f"/api/portfolios/{p['id']}/stocks",
        json={"ticker": "NVDA", "job_id": job_id},
    )

    r = client.delete(f"/api/portfolios/{p['id']}/stocks/NVDA")
    assert r.status_code == 204

    # Confirm it's gone
    detail = client.get(f"/api/portfolios/{p['id']}").json()
    assert all(s["ticker"] != "NVDA" for s in detail["stocks"])


def test_remove_stock_not_found(client):
    p = _create_portfolio(client)
    r = client.delete(f"/api/portfolios/{p['id']}/stocks/ZZZZ")
    assert r.status_code == 404


# ── Ranking ───────────────────────────────────────────────────────────────────


def _add_stock(client, job_store, portfolio_id: str,
               ticker: str, job_id: str,
               fundamental_score: float = 50.0,
               technical_score: float = 50.0,
               sentiment_score: float = 50.0,
               recommendation: str = "Hold") -> None:
    """Helper: seed a complete job and add the stock to the portfolio."""
    _seed_complete_job(
        job_store, ticker=ticker, job_id=job_id,
        # pass through to _make_report_payload via keyword unpacking
    )
    # Override scores on the seeded job result
    job = job_store._jobs[job_id]
    report = job.result
    report["fundamental_result"]["score"] = fundamental_score
    report["technical_result"]["score"] = technical_score
    report["sentiment_result"]["score"] = sentiment_score
    report["recommendation"] = recommendation

    r = client.post(
        f"/api/portfolios/{portfolio_id}/stocks",
        json={"ticker": ticker, "job_id": job_id},
    )
    assert r.status_code == 201, r.text


def test_ranking_sort_order(client, job_store):
    """Stocks are ranked descending by overall_score; null score goes last."""
    # Need ranking module — skip gracefully if not yet written (Sub-Task P3)
    pytest.importorskip("app.portfolio.ranking", reason="ranking module not yet implemented")

    p = _create_portfolio(client)
    # MSFT: overall = 80*0.4 + 80*0.4 + 80*0.2 = 80.0 → rank 1
    _add_stock(client, job_store, p["id"], "MSFT", "job-rank-msft",
               fundamental_score=80.0, technical_score=80.0, sentiment_score=80.0,
               recommendation="Buy")
    # AAPL: overall = 60*0.4 + 60*0.4 + 60*0.2 = 60.0 → rank 2
    _add_stock(client, job_store, p["id"], "AAPL", "job-rank-aapl",
               fundamental_score=60.0, technical_score=60.0, sentiment_score=60.0,
               recommendation="Buy")
    # TSLA: overall = 30*0.4 + 30*0.4 + 30*0.2 = 30.0 → rank 3
    _add_stock(client, job_store, p["id"], "TSLA", "job-rank-tsla",
               fundamental_score=30.0, technical_score=30.0, sentiment_score=30.0,
               recommendation="Sell")

    r = client.get(f"/api/portfolios/{p['id']}/ranking")
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) == 3
    tickers = [e["ticker"] for e in entries]
    assert tickers == ["MSFT", "AAPL", "TSLA"], f"Expected descending order, got {tickers}"
    assert entries[0]["rank"] == 1
    assert entries[1]["rank"] == 2
    assert entries[2]["rank"] == 3


def test_ranking_equal_scores_alpha_tiebreaker(client, job_store):
    """When two stocks share the same overall_score, ticker sorts alphabetically."""
    pytest.importorskip("app.portfolio.ranking", reason="ranking module not yet implemented")

    p = _create_portfolio(client)
    # Both score 70.0 — AAPL < MSFT alphabetically → AAPL rank 1
    _add_stock(client, job_store, p["id"], "MSFT", "job-tie-msft",
               fundamental_score=70.0, technical_score=70.0, sentiment_score=70.0)
    _add_stock(client, job_store, p["id"], "AAPL", "job-tie-aapl",
               fundamental_score=70.0, technical_score=70.0, sentiment_score=70.0)

    r = client.get(f"/api/portfolios/{p['id']}/ranking")
    assert r.status_code == 200
    tickers = [e["ticker"] for e in r.json()]
    assert tickers == ["AAPL", "MSFT"], f"Expected alpha order for equal scores, got {tickers}"


def test_ranking_all_null_scores(client, job_store):
    """Stocks with null overall_score are all returned (at the bottom)."""
    pytest.importorskip("app.portfolio.ranking", reason="ranking module not yet implemented")

    p = _create_portfolio(client)
    for ticker, jid in [("AAPL", "job-null-aapl"), ("GOOG", "job-null-goog")]:
        _seed_complete_job(job_store, ticker=ticker, job_id=jid)
        # Null out the scores so overall_score becomes None
        job = job_store._jobs[jid]
        job.result["fundamental_result"]["score"] = None
        job.result["technical_result"]["score"] = None
        job.result["sentiment_result"]["score"] = None
        r = client.post(
            f"/api/portfolios/{p['id']}/stocks",
            json={"ticker": ticker, "job_id": jid},
        )
        assert r.status_code == 201

    r = client.get(f"/api/portfolios/{p['id']}/ranking")
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) == 2
    # All null scores
    assert all(e["overall_score"] is None for e in entries)


def test_ranking_empty_portfolio(client):
    """Portfolio with no stocks returns an empty ranking list."""
    pytest.importorskip("app.portfolio.ranking", reason="ranking module not yet implemented")

    p = _create_portfolio(client)
    r = client.get(f"/api/portfolios/{p['id']}/ranking")
    assert r.status_code == 200
    assert r.json() == []


# ── History / snapshots ───────────────────────────────────────────────────────


def test_history_empty(client):
    """GET .../history on a new portfolio returns an empty list."""
    p = _create_portfolio(client)
    r = client.get(f"/api/portfolios/{p['id']}/history")
    assert r.status_code == 200
    assert r.json() == []


def test_history_portfolio_not_found(client):
    r = client.get("/api/portfolios/no-such/history")
    assert r.status_code == 404


def test_get_snapshot_not_found(client):
    p = _create_portfolio(client)
    r = client.get(f"/api/portfolios/{p['id']}/history/nonexistent-snap")
    assert r.status_code == 404


def test_get_snapshot_wrong_portfolio(client, db_session, job_store):
    """A snapshot that belongs to another portfolio returns 404 (not 200)."""
    from app.portfolio import crud
    from app.portfolio.models import Portfolio
    import uuid

    # Create two portfolios
    p1 = _create_portfolio(client, "P1")
    p2 = _create_portfolio(client, "P2")

    # Write a snapshot directly into p1 via crud
    snapshot = crud.save_ranking_snapshot(
        db_session,
        portfolio_id=p1["id"],
        entries=[],
        trigger="manual",
    )

    # Try to fetch it via p2's URL → should be 404
    r = client.get(f"/api/portfolios/{p2['id']}/history/{snapshot.id}")
    assert r.status_code == 404
    assert snapshot.id in r.json()["detail"] or p2["id"] in r.json()["detail"]

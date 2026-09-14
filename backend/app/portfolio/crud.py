"""
Database read/write helpers for the Portfolio module (Sub-Task P1).

Every database operation used by the route handlers and the scheduler lives
here.  No raw SQL or ORM calls appear in route files — they delegate entirely
to this module.

Public API
──────────
Portfolio CRUD
    create_portfolio(db, name, description) -> Portfolio
    get_portfolio(db, portfolio_id)         -> Portfolio | None
    list_portfolios(db)                     -> list[Portfolio]
    update_portfolio(db, portfolio_id, **fields) -> Portfolio | None
    delete_portfolio(db, portfolio_id)      -> bool

Stock management
    add_stock(db, portfolio_id, ticker, company_name) -> PortfolioStock
    remove_stock(db, portfolio_id, ticker)            -> bool
    update_stock_from_report(db, portfolio_id, ticker, report) -> PortfolioStock | None

Ranking snapshots
    save_ranking_snapshot(db, portfolio_id, entries, trigger) -> RankingSnapshot
    get_ranking_history(db, portfolio_id)                     -> list[RankingSnapshot]
    get_snapshot(db, snapshot_id)                             -> RankingSnapshot | None

Design notes
────────────
- Every write function calls ``db.commit()`` explicitly before returning.
  ``autocommit=False`` is the session default (set in ``database.py``), so
  nothing is persisted until ``commit()`` is called — every transaction
  boundary is therefore visible and auditable here.
- ``db.refresh(obj)`` is called after every insert/update so that the returned
  ORM object reflects the latest DB state (e.g. server-side defaults).
- ``update_stock_from_report`` accepts a plain ``dict`` (the serialised
  ``ReportPayload``) so this module does not import the Pydantic schema and
  avoids a circular-import risk with the route layer.
- ``save_ranking_snapshot`` wraps all inserts (one snapshot + N entries) in a
  single ``db.commit()`` call — either everything is written or nothing is.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.portfolio.models import (
    Portfolio,
    PortfolioStock,
    RankingEntry,
    RankingSnapshot,
)


# ── Portfolio CRUD ────────────────────────────────────────────────────────────


def create_portfolio(
    db: Session,
    name: str,
    description: str = "",
) -> Portfolio:
    """
    Insert a new ``Portfolio`` row and return the persisted object.

    Parameters
    ----------
    db:
        Active SQLAlchemy session (injected by ``get_db()``).
    name:
        Human-readable portfolio name (1–120 characters).
    description:
        Optional free-text description; defaults to empty string.

    Returns
    -------
    Portfolio
        The freshly created and committed ``Portfolio`` ORM instance.
    """
    portfolio = Portfolio(
        id=str(uuid4()),
        name=name,
        description=description,
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return portfolio


def get_portfolio(db: Session, portfolio_id: str) -> Portfolio | None:
    """
    Fetch a single ``Portfolio`` by primary key, eagerly loading its stocks.

    Returns ``None`` when no row with ``portfolio_id`` exists.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    portfolio_id:
        UUID string of the portfolio to retrieve.

    Returns
    -------
    Portfolio | None
        The matching ``Portfolio`` (with ``.stocks`` loaded), or ``None``.
    """
    return db.get(Portfolio, portfolio_id)


def list_portfolios(db: Session) -> list[Portfolio]:
    """
    Return all portfolios ordered by creation date (oldest first).

    Parameters
    ----------
    db:
        Active SQLAlchemy session.

    Returns
    -------
    list[Portfolio]
        All ``Portfolio`` rows, each with its ``.stocks`` relationship loaded.
    """
    return (
        db.query(Portfolio)
        .order_by(Portfolio.created_at.asc())
        .all()
    )


def update_portfolio(
    db: Session,
    portfolio_id: str,
    name: str | None = None,
    description: str | None = None,
) -> Portfolio | None:
    """
    Partially update a ``Portfolio`` row and return the updated object.

    Only fields explicitly passed (not ``None``) are written.  ``updated_at``
    is refreshed automatically by the SQLAlchemy ``onupdate`` hook on the model.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    portfolio_id:
        UUID string of the portfolio to update.
    name:
        New name to apply, or ``None`` to leave unchanged.
    description:
        New description to apply, or ``None`` to leave unchanged.

    Returns
    -------
    Portfolio | None
        The updated ``Portfolio``, or ``None`` when ``portfolio_id`` was not found.
    """
    portfolio = db.get(Portfolio, portfolio_id)
    if portfolio is None:
        return None

    if name is not None:
        portfolio.name = name
    if description is not None:
        portfolio.description = description

    db.commit()
    db.refresh(portfolio)
    return portfolio


def delete_portfolio(db: Session, portfolio_id: str) -> bool:
    """
    Delete a ``Portfolio`` and all its child rows (cascade on the ORM model).

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    portfolio_id:
        UUID string of the portfolio to delete.

    Returns
    -------
    bool
        ``True`` when the row was found and deleted; ``False`` when it did not exist.
    """
    portfolio = db.get(Portfolio, portfolio_id)
    if portfolio is None:
        return False

    db.delete(portfolio)
    db.commit()
    return True


# ── Stock management ──────────────────────────────────────────────────────────


def add_stock(
    db: Session,
    portfolio_id: str,
    ticker: str,
    company_name: str = "",
) -> PortfolioStock:
    """
    Add a new stock entry to a portfolio and return the persisted object.

    The caller is responsible for checking that the ticker is not already
    present (``UniqueConstraint`` on the model is the final guard, but the
    route handler should pre-check and return HTTP 409 before hitting the DB).

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    portfolio_id:
        UUID string of the owning portfolio.
    ticker:
        Upper-case ticker symbol (e.g. ``"AAPL"``).
    company_name:
        Full company name; populated from the report payload immediately after
        ``add_stock`` by a follow-up call to ``update_stock_from_report``.

    Returns
    -------
    PortfolioStock
        The newly created and committed ``PortfolioStock`` instance.
    """
    stock = PortfolioStock(
        id=str(uuid4()),
        portfolio_id=portfolio_id,
        ticker=ticker,
        company_name=company_name,
    )
    db.add(stock)
    db.commit()
    db.refresh(stock)
    return stock


def remove_stock(db: Session, portfolio_id: str, ticker: str) -> bool:
    """
    Remove a stock from a portfolio.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    portfolio_id:
        UUID string of the owning portfolio.
    ticker:
        Upper-case ticker symbol to remove.

    Returns
    -------
    bool
        ``True`` when the stock was found and removed; ``False`` otherwise.
    """
    stock = (
        db.query(PortfolioStock)
        .filter(
            PortfolioStock.portfolio_id == portfolio_id,
            PortfolioStock.ticker == ticker,
        )
        .first()
    )
    if stock is None:
        return False

    db.delete(stock)
    db.commit()
    return True


def update_stock_from_report(
    db: Session,
    portfolio_id: str,
    ticker: str,
    report: dict[str, Any],
) -> PortfolioStock | None:
    """
    Refresh the cached score/recommendation fields on a ``PortfolioStock`` row
    using data from a completed ``ReportPayload`` (passed as a plain ``dict``).

    Fields written
    ~~~~~~~~~~~~~~
    - ``company_name``     ← ``report["ticker"]`` looked up via yfinance company name;
                             falls back to ``report.get("ticker", ticker)`` since the
                             full company name is not directly in ``ReportPayload`` —
                             the route handler should pass it explicitly via the
                             ``company_name`` key if available.
    - ``short_summary``    ← ``report["executive_summary"]``
    - ``overall_score``    ← ``report["fundamental_result"]["score"] * 0.40
                                + report["technical_result"]["score"] * 0.40
                                + report["sentiment_result"]["score"] * 0.20``
                             (mirrors the orchestrator formula)
    - ``recommendation``   ← ``report["recommendation"]``
    - ``latest_report_id`` ← ``report["job_id"]``
    - ``last_refreshed``   ← ``datetime.utcnow()``

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    portfolio_id:
        UUID string of the owning portfolio.
    ticker:
        Upper-case ticker symbol of the stock to update.
    report:
        Serialised ``ReportPayload`` as a plain ``dict``.  All expected keys
        must be present; missing sub-keys are handled gracefully with ``None``.

    Returns
    -------
    PortfolioStock | None
        The updated stock row, or ``None`` when the ticker is not in the portfolio.
    """
    stock = (
        db.query(PortfolioStock)
        .filter(
            PortfolioStock.portfolio_id == portfolio_id,
            PortfolioStock.ticker == ticker,
        )
        .first()
    )
    if stock is None:
        return None

    # Extract sub-scores from their nested result dicts; default to None
    # when a key is absent (e.g. data fetch failed and the field is missing).
    fundamental_result: dict = report.get("fundamental_result") or {}
    technical_result: dict = report.get("technical_result") or {}
    sentiment_result: dict = report.get("sentiment_result") or {}

    f_score: float | None = fundamental_result.get("score")
    t_score: float | None = technical_result.get("score")
    s_score: float | None = sentiment_result.get("score")

    # Recompute overall_score using the same weights as the orchestrator.
    # If any sub-score is None the overall score becomes None as well —
    # that signals "data unavailable" in the ranking.
    if f_score is not None and t_score is not None and s_score is not None:
        overall_score: float | None = (
            f_score * 0.40 + t_score * 0.40 + s_score * 0.20
        )
    else:
        overall_score = None

    # company_name: prefer an explicit key injected by the caller; otherwise
    # keep the existing value (avoids blanking a previously stored name).
    company_name: str = report.get("company_name") or stock.company_name

    stock.company_name = company_name
    stock.short_summary = report.get("executive_summary") or ""
    stock.overall_score = overall_score
    stock.recommendation = report.get("recommendation")
    stock.latest_report_id = report.get("job_id")
    stock.last_refreshed = datetime.utcnow()

    db.commit()
    db.refresh(stock)
    return stock


# ── Ranking snapshots ─────────────────────────────────────────────────────────


def save_ranking_snapshot(
    db: Session,
    portfolio_id: str,
    entries: list[dict[str, Any]],
    trigger: str = "manual",
) -> RankingSnapshot:
    """
    Write a new immutable ``RankingSnapshot`` and its ``RankingEntry`` children
    in a single database transaction.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    portfolio_id:
        UUID string of the owning portfolio.
    entries:
        Ordered list of entry dicts produced by ``ranking.compute_ranking()``.
        Each dict must contain the keys: ``rank``, ``ticker``, ``overall_score``,
        ``fundamental_score``, ``technical_score``, ``sentiment_score``,
        ``recommendation``.
    trigger:
        What caused this snapshot — ``"manual"`` (default) or ``"quarterly"``.

    Returns
    -------
    RankingSnapshot
        The committed snapshot with its ``entries`` relationship populated.
    """
    snapshot = RankingSnapshot(
        id=str(uuid4()),
        portfolio_id=portfolio_id,
        snapshot_at=datetime.utcnow(),
        trigger=trigger,
    )
    db.add(snapshot)

    for entry_dict in entries:
        entry = RankingEntry(
            id=str(uuid4()),
            snapshot_id=snapshot.id,
            rank=entry_dict["rank"],
            ticker=entry_dict["ticker"],
            overall_score=entry_dict.get("overall_score"),
            fundamental_score=entry_dict.get("fundamental_score"),
            technical_score=entry_dict.get("technical_score"),
            sentiment_score=entry_dict.get("sentiment_score"),
            recommendation=entry_dict.get("recommendation"),
        )
        db.add(entry)

    # Single commit — all rows land atomically or none do.
    db.commit()
    db.refresh(snapshot)
    return snapshot


def get_ranking_history(
    db: Session,
    portfolio_id: str,
) -> list[RankingSnapshot]:
    """
    Return all ``RankingSnapshot`` rows for a portfolio, newest first.

    The ``entries`` relationship is loaded automatically by SQLAlchemy lazy
    loading when accessed.  For the history *list* view the entries are not
    needed, so this is intentionally left as lazy.  ``get_snapshot()`` should
    be used to retrieve a single snapshot with its full entry list.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    portfolio_id:
        UUID string of the portfolio whose history to retrieve.

    Returns
    -------
    list[RankingSnapshot]
        All snapshots ordered descending by ``snapshot_at`` (most recent first).
    """
    return (
        db.query(RankingSnapshot)
        .filter(RankingSnapshot.portfolio_id == portfolio_id)
        .order_by(RankingSnapshot.snapshot_at.desc())
        .all()
    )


def get_snapshot(
    db: Session,
    snapshot_id: str,
) -> RankingSnapshot | None:
    """
    Fetch a single ``RankingSnapshot`` by primary key with its ``entries``
    eagerly loaded.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    snapshot_id:
        UUID string of the snapshot to retrieve.

    Returns
    -------
    RankingSnapshot | None
        The snapshot with its ``entries`` list populated, or ``None`` when not found.
    """
    from sqlalchemy.orm import joinedload  # local import to keep top-level clean

    return (
        db.query(RankingSnapshot)
        .options(joinedload(RankingSnapshot.entries))
        .filter(RankingSnapshot.id == snapshot_id)
        .first()
    )

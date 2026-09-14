"""
Shared pytest fixtures for the Stock Analysis Agent test suite.

Fixtures
────────
engine        — in-memory SQLite engine; tables created once per session
db_session    — per-test SQLAlchemy session; rolled back after each test so
                tests are fully isolated without re-creating tables
job_store     — fresh in-memory JobStore for each test
client        — FastAPI TestClient wired to an in-memory DB and a stub JobStore
                via dependency_overrides; all heavy imports (pandas, yfinance …)
                are bypassed because the overrides replace every dependency
                before the app processes a request

Design notes
────────────
- The ``engine`` fixture has ``scope="session"`` so table DDL runs once; the
  per-test ``db_session`` wraps each test in a transaction that is rolled back
  rather than committed, keeping tests hermetic without the cost of DROP+CREATE.
- ``dependency_overrides`` is reset to ``{}`` after every test via the ``client``
  fixture's teardown, preventing cross-test bleed.
- ``_make_report_payload`` is a module-level helper (not a fixture) that builds
  a minimal but schema-valid ReportPayload dict; tests call it to seed the
  JobStore with complete jobs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.api.dependencies import get_db, get_job_store
from app.core.job_store import JobStore
from app.main import create_app
from app.portfolio.database import init_db
from app.portfolio.models import Base


# ── Minimal ReportPayload dict factory ────────────────────────────────────────


def _make_report_payload(
    ticker: str = "AAPL",
    job_id: str = "job-test-001",
    fundamental_score: float = 70.0,
    technical_score: float = 60.0,
    sentiment_score: float = 50.0,
    recommendation: str = "Buy",
    executive_summary: str = "Solid company.",
) -> dict:
    """
    Return a minimal dict that satisfies the ReportPayload schema and is
    accepted by ``crud.update_stock_from_report``.

    Only the fields actually consumed by the portfolio layer are populated;
    all other required ReportPayload fields are present but stubbed.
    """
    overall = fundamental_score * 0.40 + technical_score * 0.40 + sentiment_score * 0.20

    def _metric(label: str) -> dict:
        return {"label": label, "value": None, "unit": None, "interpretation": None}

    indicator: dict = {"name": "stub", "values": []}
    fundamental_result = {
        "ticker": ticker,
        "pe_ratio": _metric("P/E"),
        "eps": _metric("EPS"),
        "pb_ratio": _metric("P/B"),
        "debt_to_equity": _metric("D/E"),
        "profit_margin": _metric("Profit Margin"),
        "revenue_growth": _metric("Revenue Growth"),
        "dividend_yield": _metric("Dividend Yield"),
        "score": fundamental_score,
        "warnings": [],
    }
    technical_result = {
        "ticker": ticker,
        "dates": [],
        "close_prices": [],
        "sma_20": indicator, "sma_50": indicator, "sma_200": indicator,
        "ema_12": indicator, "ema_26": indicator,
        "rsi_14": indicator,
        "macd": indicator, "macd_signal": indicator, "macd_histogram": indicator,
        "bb_upper": indicator, "bb_middle": indicator, "bb_lower": indicator,
        "score": technical_score,
        "warnings": [],
    }
    sentiment_result = {
        "ticker": ticker,
        "positive_count": 1,
        "neutral_count": 0,
        "negative_count": 0,
        "score": sentiment_score,
        "label": "Positive",
        "headlines_analysed": 1,
    }
    return {
        "job_id": job_id,
        "ticker": ticker,
        "generated_at": "2024-01-01T00:00:00+00:00",
        "status": "complete",
        "recommendation": recommendation,
        "executive_summary": executive_summary,
        "rationale": "Stub rationale.",
        "fundamental_explanation": "Stub.",
        "technical_explanation": "Stub.",
        "news_summary": "",
        "fundamental_result": fundamental_result,
        "technical_result": technical_result,
        "sentiment_result": sentiment_result,
        "news_items": [],
        "sources_used": ["Yahoo Finance"],
        "warnings": [],
        "disclaimer": "For informational purposes only.",
        "pdf_path": None,
        # Extra key consumed by add_stock route to populate company_name
        "company_name": f"{ticker} Corp",
    }


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def engine():
    """
    In-memory SQLite engine shared across the whole test session.

    Tables are created once here; individual tests use ``db_session`` which
    rolls back after each test rather than re-creating the schema.
    """
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine) -> Session:
    """
    Per-test SQLAlchemy session backed by the in-memory engine.

    Each test runs inside a transaction that is rolled back on teardown so
    every test starts with an empty database without dropping tables.
    """
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def job_store() -> JobStore:
    """Fresh in-memory JobStore for each test."""
    return JobStore()


@pytest.fixture
def client(db_session: Session, job_store: JobStore) -> TestClient:
    """
    FastAPI TestClient with dependency overrides wired to the in-memory
    database session and a fresh JobStore.

    This bypasses every heavy import (pandas, yfinance, Groq …) because the
    overrides replace ``get_db`` and ``get_job_store`` before any route handler
    runs.  ``get_orchestrator`` is overridden with a no-op lambda so the app
    boots without needing the full agent stack.
    """
    app = create_app()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_job_store] = lambda: job_store
    # Orchestrator is only used by the refresh endpoint's background task in
    # these tests; replace it with a lightweight stub so imports don't fail.
    from app.api.dependencies import get_orchestrator
    app.dependency_overrides[get_orchestrator] = lambda: None

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides = {}

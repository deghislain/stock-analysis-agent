"""
Integration tests for the API layer — Sub-Task 5, Todo 7.

Covers every route defined in Sub-Task 5:

    GET  /api/validate/{ticker}      — TestValidateTicker
    POST /api/analyse                — TestAnalyse
    GET  /api/report/{job_id}        — TestGetReport
    GET  /api/report/{job_id}/pdf    — TestGetReportPdf

Strategy
────────
The ``Orchestrator`` and ``JobStore`` singletons in ``app.api.dependencies``
are replaced for every test via ``app.dependency_overrides``.  This keeps
tests fast (no I/O) and deterministic (no real network/LLM calls).

The ``yfinance.Ticker`` call inside the validate endpoint is patched per-test
with ``unittest.mock.patch``.
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_job_store, get_orchestrator
from app.core.job_store import Job, JobStore
from app.main import create_app


# ── Shared fixtures ───────────────────────────────────────────────────────────


def _make_client(
    store: JobStore | None = None,
    orchestrator=None,
) -> TestClient:
    """
    Build a TestClient with dependency overrides for JobStore and Orchestrator.

    If *store* is not provided a fresh empty ``JobStore`` is used.
    If *orchestrator* is not provided a ``MagicMock`` with an ``AsyncMock.run``
    is used (fire-and-forget — the background task completes instantly).
    """
    app = create_app()

    _store = store or JobStore()

    if orchestrator is None:
        _orch = MagicMock()
        _orch.run = AsyncMock()
    else:
        _orch = orchestrator

    app.dependency_overrides[get_job_store] = lambda: _store
    app.dependency_overrides[get_orchestrator] = lambda: _orch

    return TestClient(app, raise_server_exceptions=True)


def _minimal_report_dict(job_id: str = "test-job-id", ticker: str = "AAPL") -> dict:
    """
    Return the minimum valid dict that ``ReportPayload(**d)`` accepts.
    Nested Pydantic models are passed as dicts; all list fields default to [].
    """
    metric = {
        "label": "P/E Ratio",
        "value": 25.0,
        "unit": "x",
        "interpretation": "Lower is cheaper.",
    }
    indicator = {"name": "SMA 20", "values": [100.0, 101.0]}
    fundamental_result = {
        "ticker": ticker,
        "pe_ratio": metric,
        "eps": metric,
        "pb_ratio": metric,
        "debt_to_equity": metric,
        "profit_margin": metric,
        "revenue_growth": metric,
        "dividend_yield": metric,
        "score": 60.0,
        "warnings": [],
    }
    technical_result = {
        "ticker": ticker,
        "dates": ["2024-01-01", "2024-01-02"],
        "close_prices": [150.0, 151.0],
        "sma_20": indicator,
        "sma_50": indicator,
        "sma_200": indicator,
        "ema_12": indicator,
        "ema_26": indicator,
        "rsi_14": indicator,
        "macd": indicator,
        "macd_signal": indicator,
        "macd_histogram": indicator,
        "bb_upper": indicator,
        "bb_middle": indicator,
        "bb_lower": indicator,
        "score": 55.0,
        "warnings": [],
    }
    sentiment_result = {
        "ticker": ticker,
        "positive_count": 3,
        "neutral_count": 2,
        "negative_count": 1,
        "score": 60.0,
        "label": "Positive",
        "headlines_analysed": 6,
    }
    return {
        "job_id": job_id,
        "ticker": ticker,
        "generated_at": "2024-01-01T00:00:00+00:00",
        "status": "complete",
        "recommendation": "Buy",
        "executive_summary": "Good stock.",
        "rationale": "Strong fundamentals.",
        "fundamental_result": fundamental_result,
        "technical_result": technical_result,
        "sentiment_result": sentiment_result,
        "news_items": [],
        "fundamental_explanation": "PE is low.",
        "technical_explanation": "RSI is neutral.",
        "sources_used": ["Yahoo Finance"],
        "warnings": [],
        "disclaimer": "For informational purposes only. Not financial advice. Always consult a qualified financial adviser before making investment decisions.",
        "pdf_path": None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/validate/{ticker}
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateTicker:
    """Tests for GET /api/validate/{ticker}."""

    # ── Valid ticker ──────────────────────────────────────────────────────────

    def test_valid_ticker_returns_200(self):
        mock_info = {"symbol": "AAPL", "shortName": "Apple Inc."}
        with patch("app.api.routes.analysis.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = mock_info
            r = _make_client().get("/api/validate/AAPL")
        assert r.status_code == 200

    def test_valid_ticker_returns_valid_true(self):
        mock_info = {"symbol": "AAPL", "shortName": "Apple Inc."}
        with patch("app.api.routes.analysis.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = mock_info
            r = _make_client().get("/api/validate/AAPL")
        assert r.json()["valid"] is True

    def test_valid_ticker_returns_company_name(self):
        mock_info = {"symbol": "AAPL", "shortName": "Apple Inc."}
        with patch("app.api.routes.analysis.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = mock_info
            r = _make_client().get("/api/validate/AAPL")
        assert r.json()["name"] == "Apple Inc."

    def test_valid_ticker_reason_is_null(self):
        mock_info = {"symbol": "AAPL", "shortName": "Apple Inc."}
        with patch("app.api.routes.analysis.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = mock_info
            r = _make_client().get("/api/validate/AAPL")
        assert r.json()["reason"] is None

    def test_ticker_normalised_to_uppercase(self):
        """Lower-case ticker in URL must be upper-cased before yfinance lookup."""
        mock_info = {"symbol": "MSFT", "shortName": "Microsoft Corporation"}
        with patch("app.api.routes.analysis.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = mock_info
            r = _make_client().get("/api/validate/msft")
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_multi_class_ticker_brk_b_accepted(self):
        """BRK.B format must pass format validation and reach yfinance."""
        mock_info = {"symbol": "BRK-B", "shortName": "Berkshire Hathaway Inc."}
        with patch("app.api.routes.analysis.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = mock_info
            r = _make_client().get("/api/validate/BRK.B")
        assert r.status_code == 200

    def test_uses_long_name_when_short_name_missing(self):
        """Falls back to longName when shortName is absent."""
        mock_info = {"symbol": "XYZ", "longName": "XYZ Corp"}
        with patch("app.api.routes.analysis.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = mock_info
            r = _make_client().get("/api/validate/XYZ")
        assert r.json()["name"] == "XYZ Corp"

    # ── Unknown / not-found ticker ────────────────────────────────────────────

    def test_unknown_ticker_returns_200(self):
        """Unknown ticker must still return 200 — frontend reads ``valid`` flag."""
        with patch("app.api.routes.analysis.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = {}  # empty dict = unknown ticker
            r = _make_client().get("/api/validate/ZZZZ")
        assert r.status_code == 200

    def test_unknown_ticker_returns_valid_false(self):
        with patch("app.api.routes.analysis.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = {}
            r = _make_client().get("/api/validate/ZZZZ")
        assert r.json()["valid"] is False

    def test_unknown_ticker_returns_reason(self):
        with patch("app.api.routes.analysis.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = {}
            r = _make_client().get("/api/validate/ZZZZ")
        assert r.json()["reason"] == "Symbol not found"

    def test_unknown_ticker_name_is_null(self):
        with patch("app.api.routes.analysis.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = {}
            r = _make_client().get("/api/validate/ZZZZ")
        assert r.json()["name"] is None

    def test_yfinance_exception_returns_valid_false(self):
        """Any exception from yfinance must be caught and return valid=False."""
        with patch("app.api.routes.analysis.yf.Ticker", side_effect=Exception("timeout")):
            r = _make_client().get("/api/validate/AAPL")
        assert r.status_code == 200
        assert r.json()["valid"] is False

    # ── Format validation (422) ───────────────────────────────────────────────

    def test_too_long_ticker_returns_422(self):
        r = _make_client().get("/api/validate/TOOLONGTICKER")
        assert r.status_code == 422

    def test_ticker_with_spaces_returns_422(self):
        r = _make_client().get("/api/validate/AA PL")
        # URL path parsing may treat spaces differently; the regex will reject the result
        assert r.status_code in (404, 422)

    def test_special_char_ticker_returns_422(self):
        r = _make_client().get("/api/validate/AA@PL")
        assert r.status_code == 422

    def test_empty_ticker_returns_404_or_422(self):
        """An empty ticker segment is a routing miss (404) or validation fail (422)."""
        r = _make_client().get("/api/validate/")
        assert r.status_code in (404, 422)


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/analyse
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalyse:
    """Tests for POST /api/analyse."""

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_returns_202(self):
        r = _make_client().post("/api/analyse", json={"ticker": "AAPL"})
        assert r.status_code == 202

    def test_response_contains_job_id(self):
        r = _make_client().post("/api/analyse", json={"ticker": "AAPL"})
        assert "job_id" in r.json()

    def test_response_status_is_pending(self):
        r = _make_client().post("/api/analyse", json={"ticker": "AAPL"})
        assert r.json()["status"] == "pending"

    def test_job_id_is_uuid_string(self):
        import uuid
        r = _make_client().post("/api/analyse", json={"ticker": "AAPL"})
        job_id = r.json()["job_id"]
        # Must be parseable as a valid UUID.
        uuid.UUID(job_id)

    def test_job_created_in_store(self):
        store = JobStore()
        _make_client(store=store).post("/api/analyse", json={"ticker": "AAPL"})
        assert len(store._jobs) == 1

    def test_job_initial_status_is_pending(self):
        store = JobStore()
        r = _make_client(store=store).post("/api/analyse", json={"ticker": "AAPL"})
        job_id = r.json()["job_id"]
        assert store.get_job(job_id).status == "pending"

    def test_orchestrator_run_scheduled(self):
        """``orchestrator.run`` must be registered as a background task."""
        store = JobStore()
        orch = MagicMock()
        orch.run = AsyncMock()
        client = _make_client(store=store, orchestrator=orch)
        client.post("/api/analyse", json={"ticker": "AAPL"})
        # TestClient runs background tasks synchronously, so run() is called.
        orch.run.assert_called_once()

    def test_orchestrator_called_with_normalised_ticker(self):
        """Ticker must be upper-cased before being passed to the orchestrator."""
        store = JobStore()
        orch = MagicMock()
        orch.run = AsyncMock()
        _make_client(store=store, orchestrator=orch).post(
            "/api/analyse", json={"ticker": "aapl"}
        )
        args, _ = orch.run.call_args
        assert args[0] == "AAPL"

    def test_multi_class_ticker_accepted(self):
        r = _make_client().post("/api/analyse", json={"ticker": "BRK.B"})
        assert r.status_code == 202

    def test_hyphen_suffix_ticker_accepted(self):
        r = _make_client().post("/api/analyse", json={"ticker": "BF-B"})
        assert r.status_code == 202

    # ── Format validation (422) ───────────────────────────────────────────────

    def test_too_long_ticker_returns_422(self):
        r = _make_client().post("/api/analyse", json={"ticker": "TOOLONGTICKER"})
        assert r.status_code == 422

    def test_special_char_ticker_returns_422(self):
        r = _make_client().post("/api/analyse", json={"ticker": "AA@PL"})
        assert r.status_code == 422

    def test_empty_ticker_returns_422(self):
        r = _make_client().post("/api/analyse", json={"ticker": ""})
        assert r.status_code == 422

    def test_missing_body_returns_422(self):
        r = _make_client().post("/api/analyse")
        assert r.status_code == 422

    def test_numeric_only_ticker_accepted(self):
        """Purely numeric tickers (e.g. some ETFs) are valid per the regex."""
        r = _make_client().post("/api/analyse", json={"ticker": "1234"})
        assert r.status_code == 202


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/report/{job_id}
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetReport:
    """Tests for GET /api/report/{job_id}."""

    # ── Unknown job ───────────────────────────────────────────────────────────

    def test_unknown_job_returns_404(self):
        r = _make_client().get("/api/report/nonexistent-id")
        assert r.status_code == 404

    def test_unknown_job_detail_message(self):
        r = _make_client().get("/api/report/nonexistent-id")
        assert "nonexistent-id" in r.json()["detail"]

    # ── Pending job ───────────────────────────────────────────────────────────

    def test_pending_job_returns_200(self):
        store = JobStore()
        store.create_job("job-1")
        r = _make_client(store=store).get("/api/report/job-1")
        assert r.status_code == 200

    def test_pending_job_returns_status_pending(self):
        store = JobStore()
        store.create_job("job-1")
        r = _make_client(store=store).get("/api/report/job-1")
        assert r.json()["status"] == "pending"

    def test_pending_job_current_step_is_null(self):
        store = JobStore()
        store.create_job("job-1")
        r = _make_client(store=store).get("/api/report/job-1")
        assert r.json()["current_step"] is None

    # ── Running job ───────────────────────────────────────────────────────────

    def test_running_job_returns_status_running(self):
        store = JobStore()
        store.create_job("job-2")
        store._jobs["job-2"].status = "running"
        store._jobs["job-2"].current_step = "Analysing fundamentals"
        r = _make_client(store=store).get("/api/report/job-2")
        assert r.json()["status"] == "running"

    def test_running_job_returns_current_step(self):
        store = JobStore()
        store.create_job("job-2")
        store._jobs["job-2"].status = "running"
        store._jobs["job-2"].current_step = "Analysing fundamentals"
        r = _make_client(store=store).get("/api/report/job-2")
        assert r.json()["current_step"] == "Analysing fundamentals"

    # ── Error job ─────────────────────────────────────────────────────────────

    def test_error_job_returns_status_error(self):
        store = JobStore()
        store.create_job("job-3")
        store._jobs["job-3"].status = "error"
        store._jobs["job-3"].error = "Unknown ticker"
        r = _make_client(store=store).get("/api/report/job-3")
        assert r.json()["status"] == "error"

    def test_error_job_returns_error_message(self):
        store = JobStore()
        store.create_job("job-3")
        store._jobs["job-3"].status = "error"
        store._jobs["job-3"].error = "Unknown ticker"
        r = _make_client(store=store).get("/api/report/job-3")
        assert r.json()["error"] == "Unknown ticker"

    # ── Complete job ──────────────────────────────────────────────────────────

    def test_complete_job_returns_200(self):
        store = JobStore()
        store.create_job("job-4")
        store._jobs["job-4"].status = "complete"
        store._jobs["job-4"].result = _minimal_report_dict("job-4")
        r = _make_client(store=store).get("/api/report/job-4")
        assert r.status_code == 200

    def test_complete_job_returns_report_payload_fields(self):
        store = JobStore()
        store.create_job("job-4")
        store._jobs["job-4"].status = "complete"
        store._jobs["job-4"].result = _minimal_report_dict("job-4", "AAPL")
        r = _make_client(store=store).get("/api/report/job-4")
        body = r.json()
        assert body["ticker"] == "AAPL"
        assert body["recommendation"] == "Buy"
        assert body["status"] == "complete"

    def test_complete_job_contains_disclaimer(self):
        store = JobStore()
        store.create_job("job-5")
        store._jobs["job-5"].status = "complete"
        store._jobs["job-5"].result = _minimal_report_dict("job-5")
        r = _make_client(store=store).get("/api/report/job-5")
        assert "Not financial advice" in r.json()["disclaimer"]

    def test_complete_job_news_items_is_list(self):
        store = JobStore()
        store.create_job("job-6")
        store._jobs["job-6"].status = "complete"
        store._jobs["job-6"].result = _minimal_report_dict("job-6")
        r = _make_client(store=store).get("/api/report/job-6")
        assert isinstance(r.json()["news_items"], list)

    def test_complete_job_sources_used_is_list(self):
        store = JobStore()
        store.create_job("job-6")
        store._jobs["job-6"].status = "complete"
        store._jobs["job-6"].result = _minimal_report_dict("job-6")
        r = _make_client(store=store).get("/api/report/job-6")
        assert isinstance(r.json()["sources_used"], list)


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/report/{job_id}/pdf
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetReportPdf:
    """Tests for GET /api/report/{job_id}/pdf."""

    # ── Unknown / incomplete job ──────────────────────────────────────────────

    def test_unknown_job_returns_404(self):
        r = _make_client().get("/api/report/nonexistent/pdf")
        assert r.status_code == 404

    def test_pending_job_returns_404(self):
        store = JobStore()
        store.create_job("job-1")
        r = _make_client(store=store).get("/api/report/job-1/pdf")
        assert r.status_code == 404

    def test_running_job_returns_404(self):
        store = JobStore()
        store.create_job("job-2")
        store._jobs["job-2"].status = "running"
        r = _make_client(store=store).get("/api/report/job-2/pdf")
        assert r.status_code == 404

    def test_error_job_returns_404(self):
        store = JobStore()
        store.create_job("job-3")
        store._jobs["job-3"].status = "error"
        r = _make_client(store=store).get("/api/report/job-3/pdf")
        assert r.status_code == 404

    # ── Complete job, pdf_path is None ────────────────────────────────────────

    def test_complete_job_no_pdf_path_returns_404(self):
        store = JobStore()
        store.create_job("job-4")
        store._jobs["job-4"].status = "complete"
        store._jobs["job-4"].result = _minimal_report_dict("job-4")
        # pdf_path is None in the minimal dict
        r = _make_client(store=store).get("/api/report/job-4/pdf")
        assert r.status_code == 404

    # ── Complete job, pdf_path set but file missing ───────────────────────────

    def test_missing_file_on_disk_returns_404(self):
        store = JobStore()
        store.create_job("job-5")
        store._jobs["job-5"].status = "complete"
        result = _minimal_report_dict("job-5")
        result["pdf_path"] = "/tmp/nonexistent_report.pdf"
        store._jobs["job-5"].result = result
        r = _make_client(store=store).get("/api/report/job-5/pdf")
        assert r.status_code == 404

    # ── Complete job, pdf file exists ─────────────────────────────────────────

    def test_existing_pdf_returns_200(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake content")
            pdf_path = f.name
        try:
            store = JobStore()
            store.create_job("job-6")
            store._jobs["job-6"].status = "complete"
            result = _minimal_report_dict("job-6")
            result["pdf_path"] = pdf_path
            store._jobs["job-6"].result = result
            r = _make_client(store=store).get("/api/report/job-6/pdf")
            assert r.status_code == 200
        finally:
            os.unlink(pdf_path)

    def test_existing_pdf_content_type_is_pdf(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake content")
            pdf_path = f.name
        try:
            store = JobStore()
            store.create_job("job-7")
            store._jobs["job-7"].status = "complete"
            result = _minimal_report_dict("job-7")
            result["pdf_path"] = pdf_path
            store._jobs["job-7"].result = result
            r = _make_client(store=store).get("/api/report/job-7/pdf")
            assert "application/pdf" in r.headers["content-type"]
        finally:
            os.unlink(pdf_path)

    def test_existing_pdf_content_disposition_attachment(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake content")
            pdf_path = f.name
        try:
            store = JobStore()
            store.create_job("job-8")
            store._jobs["job-8"].status = "complete"
            result = _minimal_report_dict("job-8")
            result["pdf_path"] = pdf_path
            store._jobs["job-8"].result = result
            r = _make_client(store=store).get("/api/report/job-8/pdf")
            assert "attachment" in r.headers.get("content-disposition", "")
        finally:
            os.unlink(pdf_path)

    def test_existing_pdf_filename_matches_basename(self):
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", prefix="AAPL_", delete=False
        ) as f:
            f.write(b"%PDF-1.4 fake content")
            pdf_path = f.name
        try:
            store = JobStore()
            store.create_job("job-9")
            store._jobs["job-9"].status = "complete"
            result = _minimal_report_dict("job-9")
            result["pdf_path"] = pdf_path
            store._jobs["job-9"].result = result
            r = _make_client(store=store).get("/api/report/job-9/pdf")
            expected_name = os.path.basename(pdf_path)
            assert expected_name in r.headers.get("content-disposition", "")
        finally:
            os.unlink(pdf_path)


# ═══════════════════════════════════════════════════════════════════════════════
# app.api.dependencies — singleton factories and public dependency callables
# ═══════════════════════════════════════════════════════════════════════════════


class TestDependencies:
    """
    Direct unit tests for the singleton factory functions and the public
    FastAPI dependency callables in ``app.api.dependencies``.

    ``lru_cache`` is cleared before each test so every test gets a fresh
    call through the function body, guaranteeing the return statements on
    lines 20, 25, 40, and 52 are executed.
    """

    def setup_method(self):
        from app.api import dependencies
        dependencies._job_store.cache_clear()
        dependencies._orchestrator.cache_clear()

    def teardown_method(self):
        from app.api import dependencies
        dependencies._job_store.cache_clear()
        dependencies._orchestrator.cache_clear()

    def test_job_store_factory_returns_job_store_instance(self):
        from app.api.dependencies import _job_store
        from app.core.job_store import JobStore
        assert isinstance(_job_store(), JobStore)

    def test_orchestrator_factory_returns_orchestrator_instance(self):
        from app.api.dependencies import _orchestrator
        from app.core.orchestrator import Orchestrator
        assert isinstance(_orchestrator(), Orchestrator)

    def test_get_job_store_returns_job_store_instance(self):
        from app.api.dependencies import get_job_store
        from app.core.job_store import JobStore
        assert isinstance(get_job_store(), JobStore)

    def test_get_orchestrator_returns_orchestrator_instance(self):
        from app.api.dependencies import get_orchestrator
        from app.core.orchestrator import Orchestrator
        assert isinstance(get_orchestrator(), Orchestrator)

    def test_get_job_store_returns_same_singleton(self):
        from app.api.dependencies import get_job_store
        assert get_job_store() is get_job_store()

    def test_get_orchestrator_returns_same_singleton(self):
        from app.api.dependencies import get_orchestrator
        assert get_orchestrator() is get_orchestrator()

    def test_orchestrator_shares_same_job_store(self):
        """The orchestrator must be wired to the same JobStore singleton."""
        from app.api.dependencies import get_job_store, get_orchestrator
        store = get_job_store()
        orch = get_orchestrator()
        assert orch._store is store


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/report/{job_id} — ReportPayload instance branch (line 80)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetReportPayloadInstance:
    """
    Covers the branch in ``get_report`` where ``job.result`` is already a
    ``ReportPayload`` model instance rather than a plain dict.
    The orchestrator always stores a dict; this path is used by tests and
    any future code that constructs a ``ReportPayload`` directly.
    """

    def test_complete_job_with_model_instance_returns_200(self):
        from app.schemas.report import ReportPayload
        store = JobStore()
        store.create_job("job-m1")
        store._jobs["job-m1"].status = "complete"
        store._jobs["job-m1"].result = ReportPayload(**_minimal_report_dict("job-m1"))
        r = _make_client(store=store).get("/api/report/job-m1")
        assert r.status_code == 200

    def test_complete_job_with_model_instance_fields_serialised(self):
        from app.schemas.report import ReportPayload
        store = JobStore()
        store.create_job("job-m2")
        store._jobs["job-m2"].status = "complete"
        store._jobs["job-m2"].result = ReportPayload(**_minimal_report_dict("job-m2", "TSLA"))
        r = _make_client(store=store).get("/api/report/job-m2")
        assert r.json()["ticker"] == "TSLA"


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/report/{job_id}/pdf — ReportPayload instance branch (lines 137-138)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetReportPdfPayloadInstance:
    """
    Covers the ``elif hasattr(result, "pdf_path")`` branch in ``get_report_pdf``
    where ``job.result`` is a ``ReportPayload`` model instance.
    """

    def test_pdf_path_none_on_model_instance_returns_404(self):
        """pdf_path=None on a ReportPayload instance → 404."""
        from app.schemas.report import ReportPayload
        store = JobStore()
        store.create_job("job-p1")
        store._jobs["job-p1"].status = "complete"
        store._jobs["job-p1"].result = ReportPayload(**_minimal_report_dict("job-p1"))
        r = _make_client(store=store).get("/api/report/job-p1/pdf")
        assert r.status_code == 404

    def test_pdf_path_set_on_model_instance_serves_file(self):
        """pdf_path set on a ReportPayload instance → FileResponse."""
        from app.schemas.report import ReportPayload
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake")
            pdf_path = f.name
        try:
            d = _minimal_report_dict("job-p2")
            d["pdf_path"] = pdf_path
            store = JobStore()
            store.create_job("job-p2")
            store._jobs["job-p2"].status = "complete"
            store._jobs["job-p2"].result = ReportPayload(**d)
            r = _make_client(store=store).get("/api/report/job-p2/pdf")
            assert r.status_code == 200
            assert "application/pdf" in r.headers["content-type"]
        finally:
            os.unlink(pdf_path)

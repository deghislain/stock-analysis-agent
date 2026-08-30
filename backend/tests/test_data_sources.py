"""
Unit tests for the data layer (Sub-Task 2).

Covers:
- base_source      — StockData dataclass, AbstractDataSource ABC
- yahoo_finance    — YahooFinanceSource: price history, company info,
                     financials, exception handling, column filtering
- stooq_source     — StooqSource: CSV parsing, HTTP errors, network errors,
                     empty CSV, Volume-less CSV, get_company_info / get_financials
                     stubs, _normalise_ticker helper
- fmp_source       — FMPSource: price history stub, no-key fast-path,
                     profile happy-path, ratios happy-path, 401 auth error,
                     empty response, network error, None-value exclusion,
                     _get_json helper
- source_registry  — SourceRegistry: all 8 merge scenarios, _deduplicate,
                     _collect_warnings, _register_source, FallbackResult,
                     module-level singleton, ticker normalisation
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import httpx
import pandas as pd
import pytest

# ── Shared test fixtures ──────────────────────────────────────────────────────


def _make_price_df(rows: int = 3) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame with a DatetimeIndex."""
    dates = pd.date_range("2024-01-02", periods=rows, freq="B")
    return pd.DataFrame(
        {
            "Open":   [100.0] * rows,
            "High":   [101.0] * rows,
            "Low":    [99.0]  * rows,
            "Close":  [100.5] * rows,
            "Volume": [1_000_000] * rows,
        },
        index=dates,
    )


def _stock(source="Test", price=None, info=None, fins=None, warns=None):
    """Build a StockData for use as a mock return value."""
    from app.data.base_source import StockData
    return StockData(
        source_name=source,
        price_history=price,
        company_info=info or {},
        financials=fins or {},
        warnings=warns or [],
    )


PRICE_DF   = _make_price_df()
GOOD_INFO  = {"longName": "Apple Inc.", "sector": "Technology", "trailingPE": 30.0}
GOOD_FINS  = {"totalRevenue": 400e9, "netIncomeToCommon": 100e9}
FMP_INFO   = {"companyName": "Apple Inc.", "sector": "Technology", "mktCap": 3e12}
FMP_FINS   = {"peRatioTTM": 28.5, "debtToEquityRatioTTM": 1.5}


# ═════════════════════════════════════════════════════════════════════════════
# base_source
# ═════════════════════════════════════════════════════════════════════════════


class TestStockData:
    """Tests for the StockData dataclass."""

    def test_instantiation_with_all_fields(self):
        """StockData accepts all fields and stores them correctly."""
        from app.data.base_source import StockData
        sd = StockData(
            source_name="Yahoo Finance",
            price_history=PRICE_DF,
            company_info={"longName": "Apple"},
            financials={"totalRevenue": 1e9},
            warnings=["w1"],
        )
        assert sd.source_name == "Yahoo Finance"
        assert sd.price_history is PRICE_DF
        assert sd.company_info == {"longName": "Apple"}
        assert sd.financials == {"totalRevenue": 1e9}
        assert sd.warnings == ["w1"]

    def test_warnings_defaults_to_empty_list(self):
        """warnings defaults to [] when not supplied."""
        from app.data.base_source import StockData
        sd = StockData("S", None, {}, {})
        assert sd.warnings == []

    def test_warnings_default_is_independent_per_instance(self):
        """Two StockData instances must not share the same warnings list."""
        from app.data.base_source import StockData
        sd1 = StockData("A", None, {}, {})
        sd2 = StockData("B", None, {}, {})
        sd1.warnings.append("x")
        assert sd2.warnings == []

    def test_price_history_may_be_none(self):
        """price_history accepts None to signal unavailability."""
        from app.data.base_source import StockData
        sd = StockData("S", None, {}, {})
        assert sd.price_history is None


class TestAbstractDataSource:
    """Tests for the AbstractDataSource ABC."""

    def test_cannot_instantiate_directly(self):
        """AbstractDataSource must raise TypeError when instantiated."""
        from app.data.base_source import AbstractDataSource
        with pytest.raises(TypeError):
            AbstractDataSource()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_all_methods(self):
        """A subclass missing any abstract method cannot be instantiated."""
        from app.data.base_source import AbstractDataSource

        class Incomplete(AbstractDataSource):
            @property
            def source_name(self) -> str:
                return "X"
            # get_price_history and friends deliberately omitted

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_complete_concrete_subclass_instantiates(self):
        """A fully-implemented subclass can be instantiated."""
        from app.data.base_source import AbstractDataSource, StockData

        class Complete(AbstractDataSource):
            @property
            def source_name(self) -> str:
                return "Complete"
            def get_price_history(self, ticker):
                return StockData("Complete", None, {}, {})
            def get_company_info(self, ticker):
                return StockData("Complete", None, {}, {})
            def get_financials(self, ticker):
                return StockData("Complete", None, {}, {})

        src = Complete()
        assert src.source_name == "Complete"


# ═════════════════════════════════════════════════════════════════════════════
# yahoo_finance
# ═════════════════════════════════════════════════════════════════════════════


class TestYahooFinanceSource:
    """Tests for YahooFinanceSource."""

    @pytest.fixture(autouse=True)
    def source(self):
        """Provide a fresh YahooFinanceSource for each test."""
        from app.data.yahoo_finance import YahooFinanceSource
        self.src = YahooFinanceSource()

    # ── source_name ───────────────────────────────────────────────────────────

    def test_source_name(self):
        assert self.src.source_name == "Yahoo Finance"

    # ── get_price_history ─────────────────────────────────────────────────────

    def test_price_history_happy_path(self):
        """Returns a StockData with OHLCV DataFrame on success."""
        mock_df = _make_price_df()
        with patch("app.data.yahoo_finance.yf.Ticker") as MockTicker:
            MockTicker.return_value.history.return_value = mock_df
            result = self.src.get_price_history("AAPL")

        assert result.source_name == "Yahoo Finance"
        assert result.price_history is not None
        assert list(result.price_history.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert result.warnings == []

    def test_price_history_filters_extra_columns(self):
        """Extra columns returned by yfinance (e.g. Dividends) are stripped."""
        mock_df = _make_price_df()
        mock_df["Dividends"] = 0.0
        mock_df["Stock Splits"] = 0.0
        with patch("app.data.yahoo_finance.yf.Ticker") as MockTicker:
            MockTicker.return_value.history.return_value = mock_df
            result = self.src.get_price_history("AAPL")

        assert "Dividends" not in result.price_history.columns
        assert "Stock Splits" not in result.price_history.columns

    def test_price_history_empty_dataframe_returns_none(self):
        """Empty DataFrame → price_history=None + warning."""
        with patch("app.data.yahoo_finance.yf.Ticker") as MockTicker:
            MockTicker.return_value.history.return_value = pd.DataFrame()
            result = self.src.get_price_history("INVALID")

        assert result.price_history is None
        assert len(result.warnings) == 1
        assert "no price history" in result.warnings[0]

    def test_price_history_exception_returns_none_with_warning(self):
        """Any exception → price_history=None + warning containing error text."""
        with patch("app.data.yahoo_finance.yf.Ticker") as MockTicker:
            MockTicker.return_value.history.side_effect = ConnectionError("timeout")
            result = self.src.get_price_history("AAPL")

        assert result.price_history is None
        assert len(result.warnings) == 1
        assert "timeout" in result.warnings[0]

    def test_price_history_company_info_always_empty(self):
        """get_price_history never populates company_info or financials."""
        with patch("app.data.yahoo_finance.yf.Ticker") as MockTicker:
            MockTicker.return_value.history.return_value = _make_price_df()
            result = self.src.get_price_history("AAPL")

        assert result.company_info == {}
        assert result.financials == {}

    # ── get_company_info ──────────────────────────────────────────────────────

    def test_company_info_happy_path(self):
        """Returns populated company_info and financials from info dict."""
        mock_info = {
            "longName": "Apple Inc.",
            "sector": "Technology",
            "trailingPE": 30.5,
            "totalRevenue": 400e9,
            "netIncomeToCommon": 100e9,
        }
        with patch("app.data.yahoo_finance.yf.Ticker") as MockTicker:
            MockTicker.return_value.get_info.return_value = mock_info
            result = self.src.get_company_info("AAPL")

        assert result.company_info["longName"] == "Apple Inc."
        assert result.company_info["sector"] == "Technology"
        assert result.financials["totalRevenue"] == 400e9
        assert result.warnings == []

    def test_company_info_none_values_excluded(self):
        """Keys with None values are not included in company_info or financials."""
        mock_info = {"longName": "Apple Inc.", "sector": None, "trailingPE": None}
        with patch("app.data.yahoo_finance.yf.Ticker") as MockTicker:
            MockTicker.return_value.get_info.return_value = mock_info
            result = self.src.get_company_info("AAPL")

        assert "sector" not in result.company_info
        assert "trailingPE" not in result.company_info

    def test_company_info_empty_dict_produces_two_warnings(self):
        """Empty info dict → two warnings (one for info, one for financials)."""
        with patch("app.data.yahoo_finance.yf.Ticker") as MockTicker:
            MockTicker.return_value.get_info.return_value = {}
            result = self.src.get_company_info("AAPL")

        assert result.company_info == {}
        assert result.financials == {}
        assert len(result.warnings) == 2

    def test_company_info_exception_returns_empty_with_warning(self):
        """Network exception → both dicts empty, one warning with error text."""
        with patch("app.data.yahoo_finance.yf.Ticker") as MockTicker:
            MockTicker.return_value.get_info.side_effect = OSError("refused")
            result = self.src.get_company_info("AAPL")

        assert result.company_info == {}
        assert result.financials == {}
        assert len(result.warnings) == 1
        assert "refused" in result.warnings[0]

    def test_company_info_price_history_always_none(self):
        """get_company_info never returns price_history."""
        with patch("app.data.yahoo_finance.yf.Ticker") as MockTicker:
            MockTicker.return_value.get_info.return_value = GOOD_INFO
            result = self.src.get_company_info("AAPL")

        assert result.price_history is None

    # ── get_financials ────────────────────────────────────────────────────────

    def test_get_financials_delegates_to_get_company_info(self):
        """get_financials returns the same data as get_company_info."""
        mock_info = {**GOOD_INFO, **GOOD_FINS}
        with patch("app.data.yahoo_finance.yf.Ticker") as MockTicker:
            MockTicker.return_value.get_info.return_value = mock_info
            r_info = self.src.get_company_info("AAPL")
        with patch("app.data.yahoo_finance.yf.Ticker") as MockTicker:
            MockTicker.return_value.get_info.return_value = mock_info
            r_fins = self.src.get_financials("AAPL")

        assert r_info.company_info == r_fins.company_info
        assert r_info.financials   == r_fins.financials


# ═════════════════════════════════════════════════════════════════════════════
# stooq_source
# ═════════════════════════════════════════════════════════════════════════════

_STOOQ_CSV_FULL = (
    "Date,Open,High,Low,Close,Volume\n"
    "2024-01-02,185.0,186.0,184.0,185.5,50000000\n"
    "2024-01-03,186.0,187.0,185.0,186.5,45000000\n"
)
_STOOQ_CSV_NO_VOLUME = (
    "Date,Open,High,Low,Close\n"
    "2024-01-02,185.0,186.0,184.0,185.5\n"
)
_STOOQ_CSV_EMPTY = "Date,Open,High,Low,Close,Volume\n"


def _mock_stooq_response(text: str) -> MagicMock:
    """Build a mock httpx Response that returns ``text`` and passes raise_for_status."""
    resp = MagicMock()
    resp.text = text
    resp.raise_for_status = MagicMock()
    return resp


class TestStooqSource:
    """Tests for StooqSource."""

    @pytest.fixture(autouse=True)
    def source(self):
        """Provide a fresh StooqSource for each test."""
        from app.data.stooq_source import StooqSource
        self.src = StooqSource()

    # ── source_name ───────────────────────────────────────────────────────────

    def test_source_name(self):
        assert self.src.source_name == "Stooq"

    # ── get_price_history — happy paths ───────────────────────────────────────

    def test_price_history_full_csv(self):
        """Parses full OHLCV CSV into a DataFrame with DatetimeIndex."""
        with patch("app.data.stooq_source.httpx.get",
                   return_value=_mock_stooq_response(_STOOQ_CSV_FULL)):
            result = self.src.get_price_history("AAPL")

        assert result.price_history is not None
        assert list(result.price_history.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert len(result.price_history) == 2
        assert isinstance(result.price_history.index, pd.DatetimeIndex)

    def test_price_history_no_volume_column(self):
        """CSV without Volume column still produces a valid DataFrame."""
        with patch("app.data.stooq_source.httpx.get",
                   return_value=_mock_stooq_response(_STOOQ_CSV_NO_VOLUME)):
            result = self.src.get_price_history("AAPL")

        assert result.price_history is not None
        assert list(result.price_history.columns) == ["Open", "High", "Low", "Close"]

    def test_price_history_always_includes_fundamentals_warning(self):
        """The fundamentals-unavailable warning is always present."""
        with patch("app.data.stooq_source.httpx.get",
                   return_value=_mock_stooq_response(_STOOQ_CSV_FULL)):
            result = self.src.get_price_history("AAPL")

        assert any("price history only" in w for w in result.warnings)

    def test_price_history_company_info_always_empty(self):
        """get_price_history never populates company_info or financials."""
        with patch("app.data.stooq_source.httpx.get",
                   return_value=_mock_stooq_response(_STOOQ_CSV_FULL)):
            result = self.src.get_price_history("AAPL")

        assert result.company_info == {}
        assert result.financials == {}

    # ── get_price_history — error paths ───────────────────────────────────────

    def test_price_history_empty_csv_returns_none(self):
        """Empty CSV body → price_history=None + extra warning."""
        with patch("app.data.stooq_source.httpx.get",
                   return_value=_mock_stooq_response(_STOOQ_CSV_EMPTY)):
            result = self.src.get_price_history("INVALID")

        assert result.price_history is None
        assert any("no price data" in w for w in result.warnings)

    def test_price_history_http_404(self):
        """HTTP 4xx error → price_history=None + warning with status code."""
        err = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = err
        with patch("app.data.stooq_source.httpx.get", return_value=mock_resp):
            result = self.src.get_price_history("AAPL")

        assert result.price_history is None
        assert any("HTTP 404" in w for w in result.warnings)

    def test_price_history_network_error(self):
        """ConnectTimeout → price_history=None + warning with error text."""
        with patch("app.data.stooq_source.httpx.get",
                   side_effect=httpx.ConnectTimeout("timed out")):
            result = self.src.get_price_history("AAPL")

        assert result.price_history is None
        assert any("timed out" in w for w in result.warnings)

    # ── get_company_info / get_financials stubs ───────────────────────────────

    def test_get_company_info_returns_empty_with_warning(self):
        """Stooq never provides company info — returns {} + fundamentals warning."""
        result = self.src.get_company_info("AAPL")
        assert result.company_info == {}
        assert result.financials == {}
        assert result.price_history is None
        assert any("price history only" in w for w in result.warnings)

    def test_get_financials_returns_empty_with_warning(self):
        """Stooq never provides financials — returns {} + fundamentals warning."""
        result = self.src.get_financials("AAPL")
        assert result.financials == {}
        assert any("price history only" in w for w in result.warnings)


class TestNormaliseTicker:
    """Tests for the _normalise_ticker helper."""

    def test_plain_lowercase(self):
        from app.data.stooq_source import _normalise_ticker
        assert _normalise_ticker("aapl") == "AAPL.US"

    def test_plain_uppercase(self):
        from app.data.stooq_source import _normalise_ticker
        assert _normalise_ticker("MSFT") == "MSFT.US"

    def test_dot_class_share_not_double_suffixed(self):
        from app.data.stooq_source import _normalise_ticker
        assert _normalise_ticker("BRK.B") == "BRK.B"

    def test_already_has_us_suffix(self):
        from app.data.stooq_source import _normalise_ticker
        assert _normalise_ticker("aapl.us") == "AAPL.US"

    def test_strips_whitespace(self):
        from app.data.stooq_source import _normalise_ticker
        assert _normalise_ticker("  aapl  ") == "AAPL.US"


# ═════════════════════════════════════════════════════════════════════════════
# fmp_source
# ═════════════════════════════════════════════════════════════════════════════

_FMP_PROFILE_PAYLOAD = [
    {
        "companyName": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "mktCap": 3_000_000_000_000,
        "price": 200.0,
        "description": "Makes iPhones.",
        "beta": 1.2,
        "website": "https://apple.com",
        "country": "US",
        "fullTimeEmployees": 164000,
        "ipoDate": "1980-12-12",
    }
]

_FMP_RATIOS_PAYLOAD = [
    {
        "peRatioTTM": 28.5,
        "pbRatioTTM": 42.1,
        "debtToEquityRatioTTM": 1.5,
        "netProfitMarginTTM": 0.25,
        "dividendYieldTTM": 0.005,
        "revenueGrowthTTM": 0.10,
    }
]


class TestFMPSource:
    """Tests for FMPSource."""

    @pytest.fixture(autouse=True)
    def source(self):
        """Provide a fresh FMPSource for each test."""
        from app.data.fmp_source import FMPSource
        self.src = FMPSource()

    # ── source_name ───────────────────────────────────────────────────────────

    def test_source_name(self):
        assert self.src.source_name == "Financial Modeling Prep"

    # ── get_price_history (always unavailable) ────────────────────────────────

    def test_price_history_always_none(self):
        """FMP never provides price history."""
        result = self.src.get_price_history("AAPL")
        assert result.price_history is None
        assert result.company_info == {}
        assert result.financials == {}
        assert any("does not provide price history" in w for w in result.warnings)

    # ── no API key fast-path ──────────────────────────────────────────────────

    def test_company_info_no_key_returns_warning_without_network_call(self):
        """When fmp_api_key is empty, no HTTP call is made."""
        with patch("app.data.fmp_source.settings") as mock_cfg:
            mock_cfg.fmp_api_key = ""
            with patch("app.data.fmp_source._get_json") as mock_get:
                result = self.src.get_company_info("AAPL")
                mock_get.assert_not_called()

        assert result.company_info == {}
        assert any("FMP_API_KEY is not set" in w for w in result.warnings)

    def test_financials_no_key_returns_warning_without_network_call(self):
        """When fmp_api_key is empty, no HTTP call is made."""
        with patch("app.data.fmp_source.settings") as mock_cfg:
            mock_cfg.fmp_api_key = ""
            with patch("app.data.fmp_source._get_json") as mock_get:
                result = self.src.get_financials("AAPL")
                mock_get.assert_not_called()

        assert result.financials == {}
        assert any("FMP_API_KEY is not set" in w for w in result.warnings)

    # ── get_company_info happy path ───────────────────────────────────────────

    def test_company_info_happy_path(self):
        """Populates company_info from the profile payload."""
        with patch("app.data.fmp_source.settings") as mock_cfg:
            mock_cfg.fmp_api_key = "testkey"
            with patch("app.data.fmp_source._get_json", return_value=_FMP_PROFILE_PAYLOAD):
                result = self.src.get_company_info("AAPL")

        assert result.company_info["companyName"] == "Apple Inc."
        assert result.company_info["sector"] == "Technology"
        assert result.company_info["mktCap"] == 3_000_000_000_000
        assert result.financials == {}
        assert result.warnings == []

    def test_company_info_none_values_excluded(self):
        """Fields with None values are excluded from company_info."""
        payload = [{"companyName": "Corp", "sector": None, "mktCap": None}]
        with patch("app.data.fmp_source.settings") as mock_cfg:
            mock_cfg.fmp_api_key = "testkey"
            with patch("app.data.fmp_source._get_json", return_value=payload):
                result = self.src.get_company_info("CORP")

        assert "companyName" in result.company_info
        assert "sector" not in result.company_info
        assert "mktCap" not in result.company_info

    def test_company_info_empty_list_returns_warning(self):
        """Empty list response → company_info={} + warning."""
        with patch("app.data.fmp_source.settings") as mock_cfg:
            mock_cfg.fmp_api_key = "testkey"
            with patch("app.data.fmp_source._get_json", return_value=[]):
                result = self.src.get_company_info("ZZZZZ")

        assert result.company_info == {}
        assert any("no profile data" in w for w in result.warnings)

    def test_company_info_401_returns_auth_warning(self):
        """401 response raises _FMPAuthError → key-expired warning."""
        from app.data.fmp_source import _FMPAuthError
        with patch("app.data.fmp_source.settings") as mock_cfg:
            mock_cfg.fmp_api_key = "badkey"
            with patch("app.data.fmp_source._get_json", side_effect=_FMPAuthError()):
                result = self.src.get_company_info("AAPL")

        assert result.company_info == {}
        assert any("invalid or expired" in w for w in result.warnings)

    def test_company_info_network_error_returns_warning(self):
        """ConnectTimeout → company_info={} + warning with error text."""
        with patch("app.data.fmp_source.settings") as mock_cfg:
            mock_cfg.fmp_api_key = "testkey"
            with patch("app.data.fmp_source._get_json",
                       side_effect=httpx.ConnectTimeout("timeout")):
                result = self.src.get_company_info("AAPL")

        assert result.company_info == {}
        assert any("timeout" in w for w in result.warnings)

    # ── get_financials happy path ─────────────────────────────────────────────

    def test_financials_happy_path(self):
        """Populates financials from the ratios-ttm payload."""
        with patch("app.data.fmp_source.settings") as mock_cfg:
            mock_cfg.fmp_api_key = "testkey"
            with patch("app.data.fmp_source._get_json", return_value=_FMP_RATIOS_PAYLOAD):
                result = self.src.get_financials("AAPL")

        assert result.financials["peRatioTTM"] == 28.5
        assert result.financials["debtToEquityRatioTTM"] == 1.5
        assert result.company_info == {}
        assert result.warnings == []

    def test_financials_empty_list_returns_warning(self):
        """Empty list response → financials={} + warning."""
        with patch("app.data.fmp_source.settings") as mock_cfg:
            mock_cfg.fmp_api_key = "testkey"
            with patch("app.data.fmp_source._get_json", return_value=[]):
                result = self.src.get_financials("ZZZZZ")

        assert result.financials == {}
        assert any("no ratios data" in w for w in result.warnings)

    def test_financials_401_returns_auth_warning(self):
        """401 response → key-expired warning."""
        from app.data.fmp_source import _FMPAuthError
        with patch("app.data.fmp_source.settings") as mock_cfg:
            mock_cfg.fmp_api_key = "badkey"
            with patch("app.data.fmp_source._get_json", side_effect=_FMPAuthError()):
                result = self.src.get_financials("AAPL")

        assert any("invalid or expired" in w for w in result.warnings)

    def test_financials_network_error_returns_warning(self):
        """ConnectTimeout → financials={} + warning."""
        with patch("app.data.fmp_source.settings") as mock_cfg:
            mock_cfg.fmp_api_key = "testkey"
            with patch("app.data.fmp_source._get_json",
                       side_effect=httpx.ConnectTimeout("timeout")):
                result = self.src.get_financials("AAPL")

        assert result.financials == {}
        assert any("timeout" in w for w in result.warnings)


class TestFMPGetJson:
    """Tests for the _get_json internal helper."""

    def test_returns_parsed_json_on_200(self):
        """200 response → parsed JSON returned."""
        from app.data.fmp_source import _get_json

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [{"key": "value"}]

        with patch("app.data.fmp_source.httpx.get", return_value=mock_resp):
            data = _get_json("https://example.com", "key123")

        assert data == [{"key": "value"}]

    def test_raises_fmp_auth_error_on_401(self):
        """401 status → _FMPAuthError raised (not HTTPStatusError)."""
        from app.data.fmp_source import _get_json, _FMPAuthError

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Invalid API KEY."

        with patch("app.data.fmp_source.httpx.get", return_value=mock_resp):
            with pytest.raises(_FMPAuthError):
                _get_json("https://example.com", "badkey")

    def test_raises_http_status_error_on_500(self):
        """Non-401 HTTP error → raise_for_status propagates."""
        from app.data.fmp_source import _get_json

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock(status_code=500)
        )

        with patch("app.data.fmp_source.httpx.get", return_value=mock_resp):
            with pytest.raises(httpx.HTTPStatusError):
                _get_json("https://example.com", "key")

    def test_apikey_sent_as_query_param(self):
        """The api_key is passed as the ``apikey`` query parameter."""
        from app.data.fmp_source import _get_json

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = []

        with patch("app.data.fmp_source.httpx.get", return_value=mock_resp) as mock_get:
            _get_json("https://example.com/api", "my_secret_key")

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["apikey"] == "my_secret_key"


# ═════════════════════════════════════════════════════════════════════════════
# source_registry
# ═════════════════════════════════════════════════════════════════════════════


class TestFallbackResult:
    """Tests for the FallbackResult dataclass."""

    def test_instantiation(self):
        """FallbackResult stores all three fields correctly."""
        from app.data.source_registry import FallbackResult
        sd = _stock()
        r = FallbackResult(stock_data=sd, sources_used=["Yahoo"], warnings=["w"])
        assert r.stock_data is sd
        assert r.sources_used == ["Yahoo"]
        assert r.warnings == ["w"]

    def test_defaults_are_empty_lists(self):
        """sources_used and warnings default to [] and are independent."""
        from app.data.source_registry import FallbackResult
        r1 = FallbackResult(stock_data=_stock())
        r2 = FallbackResult(stock_data=_stock())
        r1.sources_used.append("X")
        assert r2.sources_used == []


class TestRegistryHelpers:
    """Tests for _deduplicate, _collect_warnings, _register_source."""

    def test_deduplicate_removes_duplicates_preserving_order(self):
        from app.data.source_registry import _deduplicate
        assert _deduplicate(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]

    def test_deduplicate_empty_list(self):
        from app.data.source_registry import _deduplicate
        assert _deduplicate([]) == []

    def test_deduplicate_all_unique(self):
        from app.data.source_registry import _deduplicate
        assert _deduplicate(["x", "y", "z"]) == ["x", "y", "z"]

    def test_collect_warnings_appends_all(self):
        from app.data.source_registry import _collect_warnings
        target = ["existing"]
        result = _stock(warns=["w1", "w2"])
        _collect_warnings(result, target)
        assert target == ["existing", "w1", "w2"]

    def test_register_source_adds_once(self):
        from app.data.source_registry import _register_source
        used: list[str] = []
        _register_source("Yahoo Finance", used)
        _register_source("Yahoo Finance", used)
        assert used == ["Yahoo Finance"]

    def test_register_source_adds_different_sources(self):
        from app.data.source_registry import _register_source
        used: list[str] = []
        _register_source("Yahoo Finance", used)
        _register_source("Stooq", used)
        assert used == ["Yahoo Finance", "Stooq"]


class TestModuleSingleton:
    """Tests for the module-level registry singleton."""

    def test_registry_singleton_is_source_registry_instance(self):
        from app.data.source_registry import registry, SourceRegistry
        assert isinstance(registry, SourceRegistry)


class TestSourceRegistry:
    """Tests for SourceRegistry.get_data_with_fallback — all merge scenarios."""

    @pytest.fixture()
    def sr(self):
        """Return a SourceRegistry with all source methods patchable."""
        from app.data.source_registry import SourceRegistry
        return SourceRegistry()

    # ── Scenario 1: Yahoo provides everything ─────────────────────────────────

    def test_yahoo_full_no_fallback_needed(self, sr):
        """When Yahoo returns price + fundamentals, no other source is queried."""
        sr._yahoo.get_price_history = lambda t: _stock("Yahoo Finance", price=PRICE_DF)
        sr._yahoo.get_company_info  = lambda t: _stock("Yahoo Finance", info=GOOD_INFO, fins=GOOD_FINS)

        result = sr.get_data_with_fallback("AAPL")

        assert result.stock_data.price_history is not None
        assert result.stock_data.company_info == GOOD_INFO
        assert result.stock_data.financials   == GOOD_FINS
        assert "Yahoo Finance" in result.sources_used
        assert "Stooq" not in result.sources_used
        assert "Financial Modeling Prep" not in result.sources_used
        assert not any("Fundamental data is unavailable" in w for w in result.warnings)

    # ── Scenario 2: Yahoo price OK, Yahoo fundamentals empty → FMP fills in ───

    def test_yahoo_price_fmp_fundamentals(self, sr):
        """Yahoo supplies price; FMP fills empty fundamentals."""
        sr._yahoo.get_price_history = lambda t: _stock("Yahoo Finance", price=PRICE_DF)
        sr._yahoo.get_company_info  = lambda t: _stock("Yahoo Finance")
        sr._fmp.get_company_info    = lambda t: _stock("Financial Modeling Prep", info=FMP_INFO)
        sr._fmp.get_financials      = lambda t: _stock("Financial Modeling Prep", fins=FMP_FINS)

        result = sr.get_data_with_fallback("AAPL")

        assert result.stock_data.price_history is not None
        assert result.stock_data.company_info == FMP_INFO
        assert result.stock_data.financials   == FMP_FINS
        assert "Yahoo Finance" in result.sources_used
        assert "Financial Modeling Prep" in result.sources_used
        assert not any("Fundamental data is unavailable" in w for w in result.warnings)

    # ── Scenario 3: Yahoo price fails → Stooq ─────────────────────────────────

    def test_stooq_price_fallback(self, sr):
        """Yahoo price fails; Stooq provides the fallback price history."""
        sr._yahoo.get_price_history = lambda t: _stock("Yahoo Finance", warns=["yahoo down"])
        sr._stooq.get_price_history = lambda t: _stock("Stooq", price=PRICE_DF)
        sr._yahoo.get_company_info  = lambda t: _stock("Yahoo Finance", info=GOOD_INFO, fins=GOOD_FINS)

        result = sr.get_data_with_fallback("AAPL")

        assert result.stock_data.price_history is not None
        assert "Stooq" in result.sources_used
        assert "Yahoo Finance" in result.sources_used  # contributed fundamentals

    # ── Scenario 4: Stooq price + FMP fundamentals ────────────────────────────

    def test_stooq_price_and_fmp_fundamentals(self, sr):
        """Yahoo fails completely; Stooq provides price, FMP provides fundamentals."""
        sr._yahoo.get_price_history = lambda t: _stock("Yahoo Finance", warns=["fail"])
        sr._stooq.get_price_history = lambda t: _stock("Stooq", price=PRICE_DF)
        sr._yahoo.get_company_info  = lambda t: _stock("Yahoo Finance")
        sr._fmp.get_company_info    = lambda t: _stock("Financial Modeling Prep", info=FMP_INFO)
        sr._fmp.get_financials      = lambda t: _stock("Financial Modeling Prep", fins=FMP_FINS)

        result = sr.get_data_with_fallback("AAPL")

        assert "Stooq" in result.sources_used
        assert "Financial Modeling Prep" in result.sources_used
        assert "Yahoo Finance" not in result.sources_used

    # ── Scenario 5: All sources fail → both sentinel warnings ─────────────────

    def test_all_sources_fail_sentinel_warnings(self, sr):
        """When every source fails, both sentinel warnings are present."""
        sr._yahoo.get_price_history = lambda t: _stock(warns=["yp"])
        sr._stooq.get_price_history = lambda t: _stock(warns=["sp"])
        sr._yahoo.get_company_info  = lambda t: _stock(warns=["yi"])
        sr._fmp.get_company_info    = lambda t: _stock(warns=["fi"])
        sr._fmp.get_financials      = lambda t: _stock(warns=["ff"])

        result = sr.get_data_with_fallback("AAPL")

        assert result.stock_data.price_history is None
        assert result.stock_data.company_info == {}
        assert result.stock_data.financials   == {}
        assert result.sources_used == []
        assert any("Fundamental data is unavailable" in w for w in result.warnings)
        assert any("Price history is unavailable" in w for w in result.warnings)

    # ── Scenario 6: Yahoo partial info (no fins) → FMP fills fins ─────────────

    def test_yahoo_partial_info_fmp_fills_fins(self, sr):
        """Yahoo has company_info but no financials; FMP fills the gap."""
        sr._yahoo.get_price_history = lambda t: _stock("Yahoo Finance", price=PRICE_DF)
        sr._yahoo.get_company_info  = lambda t: _stock("Yahoo Finance", info=GOOD_INFO)
        sr._fmp.get_company_info    = lambda t: _stock("Financial Modeling Prep", info=FMP_INFO)
        sr._fmp.get_financials      = lambda t: _stock("Financial Modeling Prep", fins=FMP_FINS)

        result = sr.get_data_with_fallback("AAPL")

        assert result.stock_data.company_info.get("longName") == "Apple Inc."
        assert result.stock_data.financials == FMP_FINS
        assert "Yahoo Finance" in result.sources_used
        assert "Financial Modeling Prep" in result.sources_used

    # ── Scenario 7: Yahoo wins on key collision ────────────────────────────────

    def test_yahoo_wins_on_key_collision(self, sr):
        """When Yahoo and FMP both provide the same key, Yahoo's value is used."""
        yahoo_info = {"sector": "Technology (Yahoo)", "trailingPE": 30.0}
        fmp_info   = {"sector": "Technology (FMP)",  "companyName": "Apple FMP"}

        sr._yahoo.get_price_history = lambda t: _stock("Yahoo Finance", price=PRICE_DF)
        sr._yahoo.get_company_info  = lambda t: _stock("Yahoo Finance", info=yahoo_info)
        sr._fmp.get_company_info    = lambda t: _stock("Financial Modeling Prep", info=fmp_info)
        sr._fmp.get_financials      = lambda t: _stock("Financial Modeling Prep", fins=FMP_FINS)

        result = sr.get_data_with_fallback("AAPL")

        assert result.stock_data.company_info["sector"] == "Technology (Yahoo)"
        assert result.stock_data.company_info["companyName"] == "Apple FMP"  # FMP-only key

    # ── Scenario 8: duplicate warnings are deduplicated ───────────────────────

    def test_duplicate_warnings_deduplicated(self, sr):
        """The same warning string from multiple sources appears only once."""
        dup = "Stooq provides price history only. Fundamental data not available from this source."

        sr._yahoo.get_price_history = lambda t: _stock(warns=[dup])
        sr._stooq.get_price_history = lambda t: _stock("Stooq", price=PRICE_DF, warns=[dup])
        sr._yahoo.get_company_info  = lambda t: _stock("Yahoo Finance", info=GOOD_INFO, fins=GOOD_FINS)

        result = sr.get_data_with_fallback("AAPL")

        assert result.warnings.count(dup) == 1

    # ── Ticker normalisation ──────────────────────────────────────────────────

    def test_ticker_normalised_to_uppercase(self, sr):
        """Lower-case ticker is normalised before being passed to sources."""
        seen: list[str] = []

        def capturing(t: str):
            seen.append(t)
            return _stock("Yahoo Finance", price=PRICE_DF)

        sr._yahoo.get_price_history = capturing
        sr._yahoo.get_company_info  = lambda t: _stock("Yahoo Finance", info=GOOD_INFO, fins=GOOD_FINS)

        sr.get_data_with_fallback("aapl")

        assert seen[0] == "AAPL"

    # ── Merged StockData fields ───────────────────────────────────────────────

    def test_merged_stock_data_source_name_reflects_primary_source(self, sr):
        """source_name on the merged StockData is the primary contributing source."""
        sr._yahoo.get_price_history = lambda t: _stock("Yahoo Finance", price=PRICE_DF)
        sr._yahoo.get_company_info  = lambda t: _stock("Yahoo Finance", info=GOOD_INFO, fins=GOOD_FINS)

        result = sr.get_data_with_fallback("AAPL")

        assert result.stock_data.source_name == "Yahoo Finance"

    def test_warnings_on_stock_data_match_result_warnings(self, sr):
        """stock_data.warnings and FallbackResult.warnings are the same list."""
        sr._yahoo.get_price_history = lambda t: _stock("Yahoo Finance", price=PRICE_DF)
        sr._yahoo.get_company_info  = lambda t: _stock("Yahoo Finance", info=GOOD_INFO, fins=GOOD_FINS)

        result = sr.get_data_with_fallback("AAPL")

        assert result.stock_data.warnings is result.warnings

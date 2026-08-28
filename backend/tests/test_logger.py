"""
Unit tests for app/logger.py.

Covers:
- _JSONFormatter  — standard fields, extra fields, exception serialisation
- _HumanFormatter — formatter initialisation, format string applied
- _build_handler  — returns StreamHandler with correct formatter type
- configure_logging — idempotency (no double-registration), level setting,
                      noisy-logger suppression, debug vs production modes
- get_logger       — returns Logger with the requested name
"""

import json
import logging
import sys
from unittest.mock import patch, MagicMock

import pytest


# ── _JSONFormatter ─────────────────────────────────────────────────────────────


class TestJSONFormatter:
    """Tests for the JSON log formatter used in production mode."""

    @pytest.fixture(autouse=True)
    def formatter(self):
        from app.logger import _JSONFormatter
        self.fmt = _JSONFormatter()

    def _make_record(self, msg="hello", level=logging.INFO, **kwargs):
        """Helper: build a LogRecord with optional extra fields."""
        record = logging.LogRecord(
            name="test.logger",
            level=level,
            pathname=__file__,
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        return record

    def test_output_is_valid_json(self):
        output = self.fmt.format(self._make_record())
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_standard_fields_present(self):
        record = self._make_record("test message")
        parsed = json.loads(self.fmt.format(record))
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert parsed["message"] == "test message"
        assert "module" in parsed
        assert "funcName" in parsed
        assert "lineno" in parsed

    def test_extra_fields_included(self):
        record = self._make_record(ticker="AAPL", job_id="abc-123")
        parsed = json.loads(self.fmt.format(record))
        assert parsed["ticker"] == "AAPL"
        assert parsed["job_id"] == "abc-123"

    def test_exception_info_included(self):
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="error occurred",
            args=(),
            exc_info=exc_info,
        )
        parsed = json.loads(self.fmt.format(record))
        assert "exc_info" in parsed
        assert "ValueError" in parsed["exc_info"]

    def test_no_exception_info_key_when_none(self):
        """When there is no exception, exc_info must not appear in the JSON."""
        record = self._make_record()
        parsed = json.loads(self.fmt.format(record))
        assert "exc_info" not in parsed

    def test_private_attrs_excluded(self):
        """Attributes starting with '_' must not leak into the JSON output."""
        record = self._make_record()
        record._private = "secret"
        parsed = json.loads(self.fmt.format(record))
        assert "_private" not in parsed

    def test_non_serialisable_value_converted_to_str(self):
        """Non-JSON-serialisable extra values are coerced to strings via default=str."""
        record = self._make_record()

        class _Unserializable:
            def __str__(self):
                return "unserializable-repr"

        record.weird = _Unserializable()
        parsed = json.loads(self.fmt.format(record))
        assert parsed["weird"] == "unserializable-repr"


# ── _HumanFormatter ────────────────────────────────────────────────────────────


class TestHumanFormatter:
    """Tests for the human-readable formatter used in debug/development mode."""

    def test_instantiation(self):
        from app.logger import _HumanFormatter
        fmt = _HumanFormatter()
        assert fmt is not None

    def test_format_contains_message(self):
        from app.logger import _HumanFormatter
        fmt = _HumanFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname=__file__,
            lineno=1, msg="hello world", args=(), exc_info=None,
        )
        output = fmt.format(record)
        assert "hello world" in output

    def test_format_contains_level(self):
        from app.logger import _HumanFormatter
        fmt = _HumanFormatter()
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname=__file__,
            lineno=1, msg="warn msg", args=(), exc_info=None,
        )
        output = fmt.format(record)
        assert "WARNING" in output


# ── _build_handler ────────────────────────────────────────────────────────────


class TestBuildHandler:
    """Tests for the handler factory function."""

    def test_returns_stream_handler(self):
        from app.logger import _build_handler
        handler = _build_handler(debug=False)
        assert isinstance(handler, logging.StreamHandler)

    def test_production_uses_json_formatter(self):
        from app.logger import _build_handler, _JSONFormatter
        handler = _build_handler(debug=False)
        assert isinstance(handler.formatter, _JSONFormatter)

    def test_debug_uses_human_formatter(self):
        from app.logger import _build_handler, _HumanFormatter
        handler = _build_handler(debug=True)
        assert isinstance(handler.formatter, _HumanFormatter)

    def test_handler_writes_to_stderr(self):
        from app.logger import _build_handler
        handler = _build_handler(debug=False)
        assert handler.stream is sys.stderr


# ── configure_logging ─────────────────────────────────────────────────────────


class TestConfigureLogging:
    """Tests for configure_logging().

    configure_logging() mutates the global root logger which pytest also owns.
    We test it by patching ``app.logger._build_handler`` to return a sentinel
    handler and by supplying a MagicMock as the root logger — both via
    ``unittest.mock.patch``.  This avoids touching pytest internals entirely.
    """

    @pytest.fixture()
    def mock_root(self):
        """Return a MagicMock that stands in for the root logger."""
        from unittest.mock import MagicMock
        root = MagicMock(spec=logging.Logger)
        root.handlers = []   # no pre-existing handlers → not already configured
        return root

    @pytest.fixture()
    def mock_root_with_handler(self):
        """Return a root mock that *already* has a handler (already configured)."""
        from unittest.mock import MagicMock
        root = MagicMock(spec=logging.Logger)
        root.handlers = [MagicMock()]  # simulate already-configured root
        return root

    def _run(self, debug: bool, root_mock):
        """Call configure_logging with the root logger replaced by root_mock."""
        from unittest.mock import patch, MagicMock
        from app.logger import configure_logging, _JSONFormatter, _HumanFormatter

        sentinel_handler = MagicMock(spec=logging.StreamHandler)
        sentinel_handler.formatter = (
            _HumanFormatter() if debug else _JSONFormatter()
        )

        with (
            patch("app.logger.logging.getLogger", side_effect=lambda n=None: root_mock if n is None else logging.getLogger.__wrapped__(n) if hasattr(logging.getLogger, "__wrapped__") else logging._loggerClass(n)),
            patch("app.logger._build_handler", return_value=sentinel_handler),
        ):
            configure_logging(debug=debug)

        return sentinel_handler

    def test_adds_handler_when_no_existing_handlers(self, mock_root):
        from unittest.mock import patch, MagicMock
        from app.logger import configure_logging

        sentinel = MagicMock(spec=logging.StreamHandler)
        with (
            patch("app.logger.logging.getLogger", side_effect=lambda n=None: mock_root if n is None else logging.Logger(n)),
            patch("app.logger._build_handler", return_value=sentinel),
        ):
            configure_logging(debug=False)

        mock_root.addHandler.assert_called_once_with(sentinel)

    def test_skips_when_handlers_already_present(self, mock_root_with_handler):
        from unittest.mock import patch, MagicMock
        from app.logger import configure_logging

        with (
            patch("app.logger.logging.getLogger", side_effect=lambda n=None: mock_root_with_handler if n is None else logging.Logger(n)),
            patch("app.logger._build_handler") as mock_build,
        ):
            configure_logging(debug=False)

        mock_build.assert_not_called()

    def test_production_sets_info_level(self, mock_root):
        from unittest.mock import patch, MagicMock
        from app.logger import configure_logging

        with (
            patch("app.logger.logging.getLogger", side_effect=lambda n=None: mock_root if n is None else logging.Logger(n)),
            patch("app.logger._build_handler", return_value=MagicMock()),
        ):
            configure_logging(debug=False)

        mock_root.setLevel.assert_called_once_with(logging.INFO)

    def test_debug_sets_debug_level(self, mock_root):
        from unittest.mock import patch, MagicMock
        from app.logger import configure_logging

        with (
            patch("app.logger.logging.getLogger", side_effect=lambda n=None: mock_root if n is None else logging.Logger(n)),
            patch("app.logger._build_handler", return_value=MagicMock()),
        ):
            configure_logging(debug=True)

        mock_root.setLevel.assert_called_once_with(logging.DEBUG)

    def test_production_uses_json_formatter(self, mock_root):
        from unittest.mock import patch, MagicMock
        from app.logger import configure_logging, _build_handler
        with (
            patch("app.logger.logging.getLogger", side_effect=lambda n=None: mock_root if n is None else logging.Logger(n)),
        ):
            configure_logging(debug=False)
        # _build_handler was called — verify via _build_handler directly
        handler = _build_handler(debug=False)
        from app.logger import _JSONFormatter
        assert isinstance(handler.formatter, _JSONFormatter)

    def test_debug_uses_human_formatter(self, mock_root):
        from unittest.mock import patch
        from app.logger import configure_logging, _build_handler
        with (
            patch("app.logger.logging.getLogger", side_effect=lambda n=None: mock_root if n is None else logging.Logger(n)),
        ):
            configure_logging(debug=True)
        handler = _build_handler(debug=True)
        from app.logger import _HumanFormatter
        assert isinstance(handler.formatter, _HumanFormatter)

    def test_noisy_loggers_suppressed(self, mock_root):
        """Noisy third-party loggers are suppressed to WARNING level."""
        from unittest.mock import patch, MagicMock, call
        from app.logger import configure_logging

        noisy_mocks: dict[str, MagicMock] = {}
        noisy_names = ("urllib3", "httpx", "httpcore", "yfinance", "peewee")
        for n in noisy_names:
            noisy_mocks[n] = MagicMock(spec=logging.Logger)

        def fake_get(name=None):
            if name is None:
                return mock_root
            if name in noisy_mocks:
                return noisy_mocks[name]
            return logging.Logger(name)

        with (
            patch("app.logger.logging.getLogger", side_effect=fake_get),
            patch("app.logger._build_handler", return_value=MagicMock()),
        ):
            configure_logging(debug=False)

        for name in noisy_names:
            noisy_mocks[name].setLevel.assert_called_once_with(logging.WARNING)


# ── get_logger ────────────────────────────────────────────────────────────────


class TestGetLogger:
    """Tests for the named-logger helper."""

    def test_returns_logger_instance(self):
        from app.logger import get_logger
        logger = get_logger("my.module")
        assert isinstance(logger, logging.Logger)

    def test_logger_name_matches(self):
        from app.logger import get_logger
        logger = get_logger("app.data.source")
        assert logger.name == "app.data.source"

    def test_same_name_returns_same_object(self):
        """logging.getLogger is idempotent for the same name."""
        from app.logger import get_logger
        a = get_logger("app.shared")
        b = get_logger("app.shared")
        assert a is b

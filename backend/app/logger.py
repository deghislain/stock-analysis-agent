"""
Structured logging setup for the Stock Analysis Agent backend.

In production (DEBUG=False) every log record is emitted as a single-line
JSON object so it can be ingested by log-aggregation tools.
In development (DEBUG=True) a human-readable format is used instead.

Usage:
    from app.logger import get_logger
    logger = get_logger(__name__)
    logger.info("something happened", extra={"ticker": "AAPL"})
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


class _JSONFormatter(logging.Formatter):
    """Formats each log record as a compact JSON object on a single line."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialise the log record to a JSON string."""
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno,
        }

        # Include exception info when present.
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        # Merge any extra fields the caller passed via `extra={}`.
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = value

        return json.dumps(payload, default=str)


class _HumanFormatter(logging.Formatter):
    """Formats log records as readable text for local development."""

    _FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    _DATE_FMT = "%Y-%m-%d %H:%M:%S"

    def __init__(self) -> None:
        """Initialise with a fixed timestamp and level format."""
        super().__init__(fmt=self._FMT, datefmt=self._DATE_FMT)


# All attribute names that belong to a standard LogRecord — used to avoid
# double-emitting them in the JSON formatter's extra-field loop.
_STANDARD_LOG_RECORD_ATTRS: frozenset[str] = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "id", "levelname", "levelno", "lineno", "module",
        "msecs", "message", "msg", "name", "pathname", "process",
        "processName", "relativeCreated", "stack_info", "thread",
        "threadName", "taskName",
    }
)


def _build_handler(debug: bool) -> logging.StreamHandler:  # type: ignore[type-arg]
    """Create and return a stderr stream handler with the appropriate formatter."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_HumanFormatter() if debug else _JSONFormatter())
    return handler


def configure_logging(debug: bool = False) -> None:
    """
    Configure the root logger once at application startup.

    Call this exactly once from ``main.py`` before any other module logs.
    Subsequent calls from other modules have no effect because the root
    logger is only configured when it has no handlers already.
    """
    root = logging.getLogger()
    if root.handlers:
        # Already configured — nothing to do.
        return

    root.setLevel(logging.DEBUG if debug else logging.INFO)
    root.addHandler(_build_handler(debug))

    # Suppress overly verbose third-party loggers that clutter output.
    for noisy in ("urllib3", "httpx", "httpcore", "yfinance", "peewee"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for the given module; call with ``__name__``."""
    return logging.getLogger(name)

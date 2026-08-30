"""
Root-level pytest configuration for the Stock Analysis Agent backend tests.

Adds the ``backend/`` directory to ``sys.path`` so ``app.*`` imports resolve
without needing to install the package.

Also stubs out optional third-party packages that may not be installed in the
test environment (e.g. a bare Python 3.x without a project venv activated):

  yfinance          — required by app/data/yahoo_finance.py at import time.
                      Stubbed with a MagicMock so the module-level
                      ``import yfinance as yf`` never raises ModuleNotFoundError.
                      Individual tests patch ``app.data.yahoo_finance.yf.*``
                      at the method level, so the stub is never called directly.

These stubs are installed into ``sys.modules`` *before* any test module is
collected, which is why they must live here in conftest.py rather than inside
individual test files.
"""

import sys
import os
from unittest.mock import MagicMock

# ── sys.path ──────────────────────────────────────────────────────────────────
# Ensure ``backend/`` is on the path when pytest is run from the repo root
# or from within the ``backend/`` directory itself.
sys.path.insert(0, os.path.dirname(__file__))

# ── Optional-dependency stubs ─────────────────────────────────────────────────
# Only install the stub when the real package is absent — this avoids shadowing
# a properly-installed package in environments that do have it.

if "yfinance" not in sys.modules:
    try:
        import yfinance  # noqa: F401
    except ModuleNotFoundError:
        # Build a MagicMock that satisfies ``import yfinance as yf`` and
        # ``yf.Ticker(...)`` without any real network calls.
        _yfinance_stub = MagicMock()
        sys.modules["yfinance"] = _yfinance_stub

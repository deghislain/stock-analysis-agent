"""
Root-level pytest configuration for the Stock Analysis Agent backend tests.

Adds the ``backend/`` directory to ``sys.path`` so ``app.*`` imports resolve
without needing to install the package.

Also stubs out optional third-party packages that may not be installed in the
test environment (e.g. a bare Python 3.x without a project venv activated):

  yfinance            — required by app/data/yahoo_finance.py at import time.
  duckduckgo_search   — required by app/agents/research_agent.py at import time.
  groq                — required by app/core/llm_client.py at import time.
  ta                  — required by app/analysis/technical.py at import time.

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


def _stub_if_missing(module_name: str) -> None:
    """Install a MagicMock into sys.modules for ``module_name`` if not importable."""
    if module_name in sys.modules:
        return
    try:
        __import__(module_name)
    except ModuleNotFoundError:
        stub = MagicMock()
        # Ensure sub-module attribute access also returns MagicMocks.
        stub.__path__ = []
        sys.modules[module_name] = stub


# ── Optional-dependency stubs ─────────────────────────────────────────────────

_stub_if_missing("yfinance")
_stub_if_missing("duckduckgo_search")
# duckduckgo_search.exceptions must be a real-ish module for ``from … import`` to work.
if "duckduckgo_search.exceptions" not in sys.modules:
    _exc_stub = MagicMock()
    _exc_stub.DuckDuckGoSearchException = Exception
    sys.modules["duckduckgo_search.exceptions"] = _exc_stub
_stub_if_missing("groq")
# groq._exceptions must expose the error classes llm_client.py imports.
if "groq._exceptions" not in sys.modules:
    _groq_exc_stub = MagicMock()
    _groq_exc_stub.APIConnectionError = Exception
    _groq_exc_stub.APIStatusError = Exception
    _groq_exc_stub.APITimeoutError = Exception
    _groq_exc_stub.GroqError = Exception
    sys.modules["groq._exceptions"] = _groq_exc_stub
# Note: ``ta`` (technical analysis library) is imported lazily inside
# app/analysis/technical.py function bodies, so no stub is needed here.
# Tests that exercise the real ``ta`` code are expected to be skipped /
# fail gracefully when ``ta`` is not installed in the environment.

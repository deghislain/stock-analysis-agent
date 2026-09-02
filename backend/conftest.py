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

# ── reportlab stubs ───────────────────────────────────────────────────────────
# reportlab is installed in the system Python 3.14 environment but not in the
# Python 3.10 environment used by this pytest installation.  Stub it out so
# every module that imports from reportlab at the top level (pdf_generator.py,
# styles.py) can be collected without crashing.
#
# Key requirements for the stubs:
#   • reportlab.lib.pagesizes.A4  must be a 2-tuple (page generator unpacks it)
#   • reportlab.lib.units.cm      must be a number (used in arithmetic)
#   • All other attributes return MagicMocks (harmless during import)

try:
    import reportlab  # noqa: F401 — only checking importability
except ModuleNotFoundError:
    import types

    def _make_rl_stub(name: str):
        m = types.ModuleType(name)
        sys.modules[name] = m
        return m

    _rl = _make_rl_stub("reportlab")
    _rl_lib = _make_rl_stub("reportlab.lib")
    _rl.lib = _rl_lib

    # colors — attribute access returns MagicMock (HexColor calls etc.)
    _rl_colors = _make_rl_stub("reportlab.lib.colors")
    _rl_colors.Color = MagicMock
    _rl_colors.HexColor = MagicMock
    _rl_lib.colors = _rl_colors

    # enums — alignment constants used as ints at import time
    _rl_enums = _make_rl_stub("reportlab.lib.enums")
    _rl_enums.TA_LEFT   = 0
    _rl_enums.TA_CENTER = 1
    _rl_enums.TA_RIGHT  = 2
    _rl_lib.enums = _rl_enums

    # pagesizes — A4 must be an unpackable 2-tuple
    _rl_pagesizes = _make_rl_stub("reportlab.lib.pagesizes")
    _rl_pagesizes.A4 = (595.27, 841.89)  # points
    _rl_lib.pagesizes = _rl_pagesizes

    # styles — getSampleStyleSheet and ParagraphStyle
    _rl_styles = _make_rl_stub("reportlab.lib.styles")
    _rl_styles.getSampleStyleSheet = MagicMock(return_value=MagicMock())
    _rl_styles.ParagraphStyle = MagicMock
    _rl_lib.styles = _rl_styles

    # units — cm must be a number for arithmetic
    _rl_units = _make_rl_stub("reportlab.lib.units")
    _rl_units.cm = 28.346456692913385  # 1 cm in points
    _rl_lib.units = _rl_units

    # platypus — most flowable constructors return a MagicMock instance.
    # Table and TableStyle need real minimal classes: the generator calls
    # Table([[...]]) and TableStyle([...]) with list args, and MagicMock
    # raises TypeError("unhashable type: 'list'") on those calls.
    class _TableStyle:
        def __init__(self, cmds=None):
            self._cmds = cmds or []
        def add(self, *args):
            pass

    class _Table:
        def __init__(self, data=None, **kwargs):
            self._data = data
        def setStyle(self, style):
            pass

    _rl_platypus = _make_rl_stub("reportlab.platypus")
    for _cls in (
        "SimpleDocTemplate", "Paragraph", "Spacer",
        "PageBreak", "HRFlowable",
    ):
        setattr(_rl_platypus, _cls, MagicMock)
    _rl_platypus.TableStyle = _TableStyle
    _rl_platypus.Table = _Table

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

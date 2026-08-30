"""
Fundamental agent — thin wrapper around ``FundamentalAnalyser``.

``FundamentalAgent.run(ticker=..., stock_data=...)`` calls
``FundamentalAnalyser.analyse`` and returns the ``FundamentalResult``
together with a status flag.

Having the analyser behind an agent interface means the orchestrator treats
every step uniformly and the analyser itself stays free of pipeline concerns.

Return dict keys
────────────────
    status             : "ok" | "error"
    fundamental_result : FundamentalResult   (present when status="ok")
    error              : str                 (present when status="error")
"""

from __future__ import annotations

from app.agents.base_agent import BaseAgent
from app.analysis.fundamental import FundamentalAnalyser
from app.data.base_source import StockData
from app.logger import get_logger
from app.schemas.analysis import FundamentalResult

logger = get_logger(__name__)


class FundamentalAgent(BaseAgent):
    """
    Runs fundamental analysis on a ``StockData`` object.

    Accepts an optional ``analyser`` argument so the ``FundamentalAnalyser``
    can be replaced with a test double without patching module globals.
    """

    def __init__(self, analyser: FundamentalAnalyser | None = None) -> None:
        """Initialise with the default ``FundamentalAnalyser`` or a custom one."""
        self._analyser = analyser or FundamentalAnalyser()

    @property
    def name(self) -> str:
        """Return the display name of this agent."""
        return "FundamentalAgent"

    async def run(self, *, ticker: str, stock_data: StockData) -> dict:
        """
        Run fundamental analysis for ``ticker`` using ``stock_data``.

        Parameters
        ----------
        ticker : str
            Upper-case ticker symbol passed through to ``FundamentalAnalyser``.
        stock_data : StockData
            Merged data object produced by ``DataAgent``.

        Returns
        -------
        dict
            ``{"status": "ok", "fundamental_result": FundamentalResult}``
            or ``{"status": "error", "error": str}`` on unexpected failure.
        """
        logger.info("FundamentalAgent starting", extra={"ticker": ticker})

        try:
            result: FundamentalResult = self._analyser.analyse(ticker, stock_data)

            logger.info(
                "FundamentalAgent complete",
                extra={"ticker": ticker, "score": result.score, "warnings": len(result.warnings)},
            )

            return {"status": "ok", "fundamental_result": result}

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "FundamentalAgent failed",
                extra={"ticker": ticker, "error": str(exc)},
            )
            return {"status": "error", "error": str(exc)}

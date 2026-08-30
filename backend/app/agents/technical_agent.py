"""
Technical agent — thin wrapper around ``TechnicalAnalyser``.

``TechnicalAgent.run(ticker=..., stock_data=...)`` calls
``TechnicalAnalyser.analyse`` and returns the ``TechnicalResult``
together with a status flag.

Return dict keys
────────────────
    status           : "ok" | "error"
    technical_result : TechnicalResult   (present when status="ok")
    error            : str               (present when status="error")
"""

from __future__ import annotations

from app.agents.base_agent import BaseAgent
from app.analysis.technical import TechnicalAnalyser
from app.data.base_source import StockData
from app.logger import get_logger
from app.schemas.analysis import TechnicalResult

logger = get_logger(__name__)


class TechnicalAgent(BaseAgent):
    """
    Runs technical indicator analysis on the price history in a ``StockData`` object.

    Accepts an optional ``analyser`` argument so the ``TechnicalAnalyser``
    can be replaced with a test double without patching module globals.
    """

    def __init__(self, analyser: TechnicalAnalyser | None = None) -> None:
        """Initialise with the default ``TechnicalAnalyser`` or a custom one."""
        self._analyser = analyser or TechnicalAnalyser()

    @property
    def name(self) -> str:
        """Return the display name of this agent."""
        return "TechnicalAgent"

    async def run(self, *, ticker: str, stock_data: StockData) -> dict:
        """
        Run technical analysis for ``ticker`` using ``stock_data.price_history``.

        Parameters
        ----------
        ticker : str
            Upper-case ticker symbol passed through to ``TechnicalAnalyser``.
        stock_data : StockData
            Merged data object produced by ``DataAgent``.  When
            ``price_history`` is ``None`` the analyser returns a neutral
            result with a warning — no exception is raised.

        Returns
        -------
        dict
            ``{"status": "ok", "technical_result": TechnicalResult}``
            or ``{"status": "error", "error": str}`` on unexpected failure.
        """
        logger.info("TechnicalAgent starting", extra={"ticker": ticker})

        try:
            result: TechnicalResult = self._analyser.analyse(ticker, stock_data)

            logger.info(
                "TechnicalAgent complete",
                extra={"ticker": ticker, "score": result.score, "warnings": len(result.warnings)},
            )

            return {"status": "ok", "technical_result": result}

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "TechnicalAgent failed",
                extra={"ticker": ticker, "error": str(exc)},
            )
            return {"status": "error", "error": str(exc)}

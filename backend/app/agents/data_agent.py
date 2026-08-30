"""
Data agent — first step in the orchestration pipeline.

``DataAgent.run(ticker=...)`` calls the source registry's fallback chain
and returns the merged ``StockData`` together with ``sources_used`` and
``warnings``.  It is the only agent that interacts with the data layer;
every downstream agent receives its output rather than fetching data itself.

Ticker validation
─────────────────
The registry never raises — it always returns a result, even for completely
unknown tickers (with all fields empty and ``sources_used=[]``).  The agent
treats a result where both ``price_history`` is ``None`` AND ``sources_used``
is empty as an unknown / invalid ticker and raises ``ValueError`` so the
orchestrator can immediately mark the job as failed with a clear message.

Return dict keys
────────────────
    status       : "ok" | "error"
    stock_data   : StockData object (present when status="ok")
    sources_used : list[str]        (present when status="ok")
    warnings     : list[str]        (present when status="ok")
    error        : str              (present when status="error")
"""

from __future__ import annotations

from app.agents.base_agent import BaseAgent
from app.data.source_registry import registry as _default_registry
from app.data.source_registry import SourceRegistry
from app.logger import get_logger

logger = get_logger(__name__)


class DataAgent(BaseAgent):
    """
    Fetches and merges stock data for a ticker using the source fallback chain.

    Accepts an optional ``registry`` argument so the registry can be swapped
    out in tests without patching module globals.
    """

    def __init__(self, registry: SourceRegistry | None = None) -> None:
        """Initialise with the shared module-level registry, or a custom one for testing."""
        self._registry = registry or _default_registry

    @property
    def name(self) -> str:
        """Return the display name of this agent."""
        return "DataAgent"

    async def run(self, *, ticker: str) -> dict:
        """
        Fetch merged stock data for ``ticker`` via the source registry.

        Parameters
        ----------
        ticker : str
            The stock ticker symbol (case-insensitive; normalised to upper-case).

        Returns
        -------
        dict
            ``{"status": "ok", "stock_data": StockData, "sources_used": [...],
               "warnings": [...]}``

        Raises
        ------
        ValueError
            When every data source returns empty results, indicating the ticker
            is unknown or not supported by any source.  The orchestrator catches
            this and marks the job as failed.
        """
        ticker = ticker.upper().strip()
        logger.info("DataAgent starting", extra={"ticker": ticker})

        result = self._registry.get_data_with_fallback(ticker)
        sd = result.stock_data

        # ── Ticker validation ─────────────────────────────────────────────────
        # A completely unknown ticker returns no price history AND no sources.
        # Treat this as an invalid ticker so the orchestrator can fail fast
        # with a human-readable error rather than producing an empty report.
        if sd.price_history is None and not result.sources_used:
            logger.warning("Unknown ticker — all sources returned empty", extra={"ticker": ticker})
            raise ValueError(
                f"'{ticker}' could not be found on any data source. "
                "Please check the ticker symbol and try again."
            )

        logger.info(
            "DataAgent complete",
            extra={
                "ticker": ticker,
                "sources_used": result.sources_used,
                "warnings": len(result.warnings),
                "has_price": sd.price_history is not None,
                "has_fundamentals": bool(sd.company_info or sd.financials),
            },
        )

        return {
            "status": "ok",
            "stock_data": sd,
            "sources_used": result.sources_used,
            "warnings": result.warnings,
        }

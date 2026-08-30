"""
Research agent — fetches recent news headlines for a ticker via DuckDuckGo.

``ResearchAgent.run(ticker=...)`` calls ``DDGS().text()`` with the query
``"{ticker} stock news"`` and returns up to ``max_results`` cleaned news
items.  Each item is a plain dict with normalised keys:

    title       : str  — headline text
    url         : str  — link to the full article
    body        : str  — short snippet / description
    source      : str  — domain extracted from the URL (best-effort)

The agent never raises — network errors, rate-limits, and empty result sets
are all returned as status="ok" with an empty ``news_items`` list plus a
warning so the orchestrator can continue with the rest of the pipeline.

DDGS exception hierarchy
─────────────────────────
    DuckDuckGoSearchException  ← base
        RatelimitException
        TimeoutException
        ConversationLimitException   (not expected here, but caught for safety)
"""

from __future__ import annotations

from urllib.parse import urlparse

from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException

from app.agents.base_agent import BaseAgent
from app.logger import get_logger

logger = get_logger(__name__)

# Default number of results to request from DuckDuckGo.
_MAX_RESULTS = 10

# Query template — keeps the search focused on stock-market news.
_QUERY_TEMPLATE = "{ticker} stock news"


class ResearchAgent(BaseAgent):
    """
    Fetches recent news headlines for a ticker using the DuckDuckGo Search API.

    Accepts an optional ``max_results`` parameter at construction time so
    callers can tune the result count without subclassing.
    """

    def __init__(self, max_results: int = _MAX_RESULTS) -> None:
        """Initialise with the desired maximum number of news results."""
        self._max_results = max_results

    @property
    def name(self) -> str:
        """Return the display name of this agent."""
        return "ResearchAgent"

    async def run(self, *, ticker: str) -> dict:
        """
        Search DuckDuckGo for recent news about ``ticker`` and return cleaned items.

        Parameters
        ----------
        ticker : str
            The stock ticker symbol (case-insensitive; used in the search query).

        Returns
        -------
        dict
            ``{"status": "ok", "news_items": [...], "warnings": [...]}``

            ``news_items`` is a list of dicts with keys:
            ``title``, ``url``, ``body``, ``source``.
            It may be empty if the search returned no results or failed.
        """
        ticker = ticker.upper().strip()
        query = _QUERY_TEMPLATE.format(ticker=ticker)
        warnings: list[str] = []
        news_items: list[dict] = []

        logger.info("ResearchAgent starting", extra={"ticker": ticker, "query": query})

        try:
            raw_results: list[dict] = DDGS().text(query, max_results=self._max_results)
            news_items = [_clean_item(r) for r in raw_results if _clean_item(r)]

            if not news_items:
                warnings.append(
                    f"No news results found for '{ticker}'. "
                    "Sentiment analysis will be skipped."
                )

            logger.info(
                "ResearchAgent complete",
                extra={"ticker": ticker, "results": len(news_items)},
            )

        except Exception as exc:  # noqa: BLE001 — covers all DDGS exceptions + network errors
            msg = _classify_error(exc, ticker)
            warnings.append(msg)
            logger.warning(
                "ResearchAgent fetch failed",
                extra={"ticker": ticker, "error": str(exc), "type": type(exc).__name__},
            )

        return {
            "status": "ok",
            "news_items": news_items,
            "warnings": warnings,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _clean_item(raw: dict) -> dict:
    """
    Normalise a raw DuckDuckGo result dict into the agent's output shape.

    DuckDuckGo text results use these keys: ``title``, ``href``, ``body``.
    This function maps ``href`` → ``url`` and adds a ``source`` field
    extracted from the URL domain.  Items missing both title and body are
    discarded (return value is an empty dict, filtered by the caller).
    """
    title = (raw.get("title") or "").strip()
    url   = (raw.get("href")  or "").strip()
    body  = (raw.get("body")  or "").strip()

    if not title and not body:
        return {}

    source = _extract_domain(url)

    return {
        "title":  title,
        "url":    url,
        "body":   body,
        "source": source,
    }


def _extract_domain(url: str) -> str:
    """
    Return the bare domain name from ``url`` (e.g. ``"reuters.com"``).

    Falls back to an empty string when ``url`` is blank or cannot be parsed.
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Strip the common "www." prefix for cleaner display.
        return domain.removeprefix("www.")
    except Exception:  # noqa: BLE001
        return ""


def _classify_error(exc: Exception, ticker: str) -> str:
    """
    Return a human-readable warning string for a DDGS exception.

    Distinguishes rate-limit errors (likely transient) from generic
    network/search errors so the UI can display a relevant message.
    """
    name = type(exc).__name__
    if "Ratelimit" in name:
        return (
            f"DuckDuckGo rate-limited the news search for '{ticker}'. "
            "News sentiment analysis will be skipped for this request."
        )
    if "Timeout" in name:
        return (
            f"News search timed out for '{ticker}'. "
            "Sentiment analysis will be skipped."
        )
    return (
        f"News search failed for '{ticker}' ({name}: {exc}). "
        "Sentiment analysis will be skipped."
    )

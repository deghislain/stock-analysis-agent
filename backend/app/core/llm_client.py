"""
LLM client — thin async wrapper around the Groq Python SDK.

``LLMClient.generate(prompt)`` sends a single user message to the configured
Groq model and returns the content of the assistant reply as a plain string.

Configuration is read from ``app.config.settings``:
    groq_api_key : str  — must be non-empty for real calls
    groq_model   : str  — defaults to ``"llama3-8b-8192"``

No-key behaviour
────────────────
When ``groq_api_key`` is empty the client raises ``LLMUnavailableError``
immediately without making a network call.  This lets the ``ReportAgent``
catch it cleanly and apply the fallback template.

Exception hierarchy
───────────────────
All Groq SDK exceptions (``AuthenticationError``, ``RateLimitError``,
``APIConnectionError``, ``APITimeoutError``, …) are re-raised as
``LLMUnavailableError`` so callers only need to catch one exception type.
The original exception is chained (``raise ... from exc``) for debugging.
"""

from __future__ import annotations

from groq import AsyncGroq
from groq._exceptions import APIConnectionError, APIStatusError, APITimeoutError, GroqError

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

# Token budget for the LLM response — generous enough for all five JSON fields.
_MAX_TOKENS = 1024

# Temperature: low for deterministic, structured JSON output.
_TEMPERATURE = 0.3


class LLMUnavailableError(Exception):
    """Raised when the Groq LLM cannot be reached or is not configured."""


class LLMClient:
    """
    Async client for the Groq LLM API.

    Wraps ``groq.AsyncGroq`` and exposes a single ``generate`` coroutine.
    Accepts an optional ``api_key`` and ``model`` at construction time so
    the client can be overridden in tests without touching ``settings``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        """
        Initialise the LLM client.

        Parameters
        ----------
        api_key : str | None
            Groq API key.  Falls back to ``settings.groq_api_key`` when omitted.
        model : str | None
            Groq model identifier.  Falls back to ``settings.groq_model``.
        """
        self._api_key = api_key if api_key is not None else settings.groq_api_key
        self._model   = model   if model   is not None else settings.groq_model

    async def generate(self, prompt: str) -> str:
        """
        Send ``prompt`` to the Groq model and return the assistant reply as a string.

        Parameters
        ----------
        prompt : str
            The full prompt string built by ``ReportAgent._build_prompt``.

        Returns
        -------
        str
            The raw text content of the LLM's first response message.

        Raises
        ------
        LLMUnavailableError
            When ``groq_api_key`` is not set, or when any Groq SDK or network
            error occurs.  The original exception is chained for traceability.
        """
        if not self._api_key:
            raise LLMUnavailableError(
                "GROQ_API_KEY is not configured. "
                "Set it in your .env file to enable AI-generated explanations."
            )

        logger.debug(
            "LLMClient sending request",
            extra={"model": self._model, "prompt_chars": len(prompt)},
        )

        try:
            client = AsyncGroq(api_key=self._api_key)
            response = await client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self._model,
                max_tokens=_MAX_TOKENS,
                temperature=_TEMPERATURE,
            )
            content: str = response.choices[0].message.content or ""

            logger.debug(
                "LLMClient received response",
                extra={"model": self._model, "response_chars": len(content)},
            )
            return content

        except GroqError as exc:
            # Covers AuthenticationError, RateLimitError, APIConnectionError,
            # APITimeoutError, APIStatusError, and all other Groq SDK errors.
            logger.warning(
                "LLMClient Groq error",
                extra={"model": self._model, "error": str(exc), "type": type(exc).__name__},
            )
            raise LLMUnavailableError(str(exc)) from exc

        except Exception as exc:  # noqa: BLE001 — network / OS errors
            logger.warning(
                "LLMClient unexpected error",
                extra={"model": self._model, "error": str(exc), "type": type(exc).__name__},
            )
            raise LLMUnavailableError(str(exc)) from exc

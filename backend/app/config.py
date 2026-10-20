"""
Central configuration for the Stock Analysis Agent backend.

All settings are read from environment variables (or a .env file).
Pydantic Settings validates types and provides defaults so the app
starts safely even without a fully populated .env.
"""

from __future__ import annotations

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Holds every runtime configuration value for the application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────

    app_name: str = Field(
        default="Stock Analysis Agent",
        description="Human-readable name shown in logs and API metadata.",
    )

    debug: bool = Field(
        default=False,
        description="Enable debug mode: verbose logging, auto-reload, detailed errors.",
    )

    # ── Groq LLM ─────────────────────────────────────────────────────────────

    groq_api_key: str = Field(
        default="",
        description="API key for the Groq inference service. Required for AI-generated explanations.",
    )

    groq_model: str = Field(
        default="llama3-8b-8192",
        description="Groq model ID to use for plain-language report generation.",
    )

    # ── CORS ─────────────────────────────────────────────────────────────────

    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"],
        description="List of frontend origins allowed to call the API.",
    )

    # ── Data layer ───────────────────────────────────────────────────────────

    fmp_api_key: str = Field(
        default="",
        description=(
            "API key for Financial Modeling Prep (FMP). "
            "Required for the fundamentals fallback source. "
            "Get a free key (no credit card) at https://financialmodelingprep.com/developer/docs."
        ),
    )

    data_cache_ttl_seconds: int = Field(
        default=300,
        description="How long (seconds) to cache fetched stock data in memory before re-fetching.",
    )

    # ── PDF output ───────────────────────────────────────────────────────────

    pdf_output_dir: str = Field(
        default="/tmp/stock_reports",
        description="Directory where generated PDF reports are stored temporarily.",
    )

    pdf_cleanup_interval_seconds: int = Field(
        default=1800,
        description="How often (seconds) the cleanup task runs to delete old PDF files.",
    )

    pdf_max_age_seconds: int = Field(
        default=3600,
        description="Maximum age (seconds) a PDF file is kept before being deleted.",
    )

    # ── Portfolio / persistence ───────────────────────────────────────────────

    database_url: str = Field(
        default="sqlite:///./portfolios.db",
        description=(
            "SQLAlchemy database URL for the portfolio persistence layer. "
            "Defaults to a local SQLite file (`portfolios.db`) in the working directory. "
            "Override to `sqlite:////app/data/portfolios.db` in Docker so the file lands "
            "on the named volume instead of inside the container layer."
        ),
    )

    quarterly_refresh_enabled: bool = Field(
        default=True,
        description=(
            "Enable the APScheduler quarterly refresh job. "
            "Set to `false` during development or testing to prevent the scheduler "
            "from firing background analysis jobs automatically."
        ),
    )

    # ── Scoring thresholds ────────────────────────────────────────────────────
    # These control the break-points used in the fundamental and technical
    # scoring functions. Override via environment variables to tune the model
    # without touching source code.

    fundamental_pe_thresholds: str = Field(
        default="15,25,40",
        description=(
            "Comma-separated P/E ratio break-points (low,mid,high). "
            "Scores: below low→100, low–mid→70, mid–high→45, above high→20."
        ),
    )

    fundamental_pb_thresholds: str = Field(
        default="1,3,10",
        description=(
            "Comma-separated P/B ratio break-points (low,mid,high). "
            "Scores: negative→10, below low→100, low–mid→75, mid–high→45, above high→15."
        ),
    )

    fundamental_de_thresholds: str = Field(
        default="0.5,1,2",
        description=(
            "Comma-separated Debt/Equity break-points (low,mid,high). "
            "Scores: below low→100, low–mid→75, mid–high→50, above high→20."
        ),
    )

    fundamental_margin_thresholds: str = Field(
        default="0,10,20",
        description=(
            "Comma-separated net profit margin break-points in % (zero,mid,high). "
            "Scores: above high→100, mid–high→75, zero–mid→45, negative→10."
        ),
    )

    fundamental_revenue_growth_thresholds: str = Field(
        default="0,5,15",
        description=(
            "Comma-separated revenue growth break-points in % (zero,mid,high). "
            "Scores: above high→100, mid–high→75, zero–mid→50, negative→20."
        ),
    )

    technical_rsi_bands: str = Field(
        default="30,45,55,70",
        description=(
            "Comma-separated RSI band boundaries (oversold,low,high,overbought). "
            "Scores: below oversold→0.85, oversold–low→0.70, low–high→0.50, "
            "high–overbought→0.35, above overbought→0.20."
        ),
    )

    technical_signal_weights: str = Field(
        default="25,25,20,15,15",
        description=(
            "Comma-separated weights for technical signals "
            "(RSI, MACD, SMA20, SMA50, SMA200). Must sum to 100."
        ),
    )

    # ── Composite score weights ───────────────────────────────────────────────
    # These three weights must sum to 1.0.  They control how much each analysis
    # dimension contributes to the final overall_score that drives the
    # Buy / Hold / Sell recommendation.

    score_weight_fundamental: float = Field(
        default=0.40,
        ge=0.0,
        le=1.0,
        description="Weight given to the fundamental score in the composite score (0–1).",
    )

    score_weight_technical: float = Field(
        default=0.40,
        ge=0.0,
        le=1.0,
        description="Weight given to the technical score in the composite score (0–1).",
    )

    score_weight_sentiment: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Weight given to the sentiment score in the composite score (0–1).",
    )

    @field_validator(
        "fundamental_pe_thresholds",
        "fundamental_pb_thresholds",
        "fundamental_de_thresholds",
        "fundamental_margin_thresholds",
        "fundamental_revenue_growth_thresholds",
        "technical_rsi_bands",
        "technical_signal_weights",
        mode="before",
    )
    @classmethod
    def _validate_numeric_csv(cls, v: str) -> str:
        """Ensure the value is a comma-separated list of numbers."""
        for part in str(v).split(","):
            try:
                float(part.strip())
            except ValueError:
                raise ValueError(
                    f"Expected comma-separated numbers, got: {v!r}"
                )
        return str(v)

    def _parse_thresholds(self, raw: str) -> list[float]:
        """Parse a comma-separated threshold string into a sorted list of floats."""
        return sorted(float(x.strip()) for x in raw.split(","))

    @property
    def pe_thresholds(self) -> list[float]:
        """Parsed P/E thresholds [low, mid, high]."""
        return self._parse_thresholds(self.fundamental_pe_thresholds)

    @property
    def pb_thresholds(self) -> list[float]:
        """Parsed P/B thresholds [low, mid, high]."""
        return self._parse_thresholds(self.fundamental_pb_thresholds)

    @property
    def de_thresholds(self) -> list[float]:
        """Parsed D/E thresholds [low, mid, high]."""
        return self._parse_thresholds(self.fundamental_de_thresholds)

    @property
    def margin_thresholds(self) -> list[float]:
        """Parsed profit margin thresholds in % [zero, mid, high]."""
        return self._parse_thresholds(self.fundamental_margin_thresholds)

    @property
    def revenue_growth_thresholds(self) -> list[float]:
        """Parsed revenue growth thresholds in % [zero, mid, high]."""
        return self._parse_thresholds(self.fundamental_revenue_growth_thresholds)

    @property
    def rsi_bands(self) -> list[float]:
        """Parsed RSI band boundaries [oversold, low, high, overbought]."""
        return self._parse_thresholds(self.technical_rsi_bands)

    @property
    def signal_weights(self) -> list[float]:
        """Parsed technical signal weights [RSI, MACD, SMA20, SMA50, SMA200]."""
        parts = [float(x.strip()) for x in self.technical_signal_weights.split(",")]
        return parts


# Module-level singleton — import this everywhere instead of instantiating Settings() directly.
settings = Settings()

"""
Central configuration for the Stock Analysis Agent backend.

All settings are read from environment variables (or a .env file).
Pydantic Settings validates types and provides defaults so the app
starts safely even without a fully populated .env.
"""

from __future__ import annotations

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


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


# Module-level singleton — import this everywhere instead of instantiating Settings() directly.
settings = Settings()

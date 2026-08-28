"""
Unit tests for app/config.py.

Covers:
- All default values of the Settings model.
- Environment-variable overrides for every field.
- The module-level ``settings`` singleton is a ``Settings`` instance.
"""

import os
import importlib

import pytest
from pydantic import ValidationError


class TestSettingsDefaults:
    """Verify every field ships with the documented default value."""

    def test_app_name_default(self, fresh_settings):
        assert fresh_settings.app_name == "Stock Analysis Agent"

    def test_debug_default(self, fresh_settings):
        assert fresh_settings.debug is False

    def test_groq_api_key_default(self, fresh_settings):
        assert fresh_settings.groq_api_key == ""

    def test_groq_model_default(self, fresh_settings):
        assert fresh_settings.groq_model == "llama3-8b-8192"

    def test_cors_origins_default(self, fresh_settings):
        assert fresh_settings.cors_origins == [
            "http://localhost:5173",
            "http://localhost:3000",
        ]

    def test_data_cache_ttl_default(self, fresh_settings):
        assert fresh_settings.data_cache_ttl_seconds == 300

    def test_pdf_output_dir_default(self, fresh_settings):
        assert fresh_settings.pdf_output_dir == "/tmp/stock_reports"

    def test_pdf_cleanup_interval_default(self, fresh_settings):
        assert fresh_settings.pdf_cleanup_interval_seconds == 1800

    def test_pdf_max_age_default(self, fresh_settings):
        assert fresh_settings.pdf_max_age_seconds == 3600


class TestSettingsEnvOverrides:
    """Verify each field can be overridden via an environment variable."""

    def test_app_name_override(self, monkeypatch):
        monkeypatch.setenv("APP_NAME", "My Custom App")
        s = _make_settings()
        assert s.app_name == "My Custom App"

    def test_debug_override_true(self, monkeypatch):
        monkeypatch.setenv("DEBUG", "true")
        s = _make_settings()
        assert s.debug is True

    def test_debug_override_false(self, monkeypatch):
        monkeypatch.setenv("DEBUG", "false")
        s = _make_settings()
        assert s.debug is False

    def test_groq_api_key_override(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_testkey")
        s = _make_settings()
        assert s.groq_api_key == "gsk_testkey"

    def test_groq_model_override(self, monkeypatch):
        monkeypatch.setenv("GROQ_MODEL", "llama3-70b-8192")
        s = _make_settings()
        assert s.groq_model == "llama3-70b-8192"

    def test_cors_origins_override(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", '["https://example.com"]')
        s = _make_settings()
        assert s.cors_origins == ["https://example.com"]

    def test_data_cache_ttl_override(self, monkeypatch):
        monkeypatch.setenv("DATA_CACHE_TTL_SECONDS", "60")
        s = _make_settings()
        assert s.data_cache_ttl_seconds == 60

    def test_pdf_output_dir_override(self, monkeypatch):
        monkeypatch.setenv("PDF_OUTPUT_DIR", "/var/reports")
        s = _make_settings()
        assert s.pdf_output_dir == "/var/reports"

    def test_pdf_cleanup_interval_override(self, monkeypatch):
        monkeypatch.setenv("PDF_CLEANUP_INTERVAL_SECONDS", "900")
        s = _make_settings()
        assert s.pdf_cleanup_interval_seconds == 900

    def test_pdf_max_age_override(self, monkeypatch):
        monkeypatch.setenv("PDF_MAX_AGE_SECONDS", "7200")
        s = _make_settings()
        assert s.pdf_max_age_seconds == 7200

    def test_case_insensitive_env(self, monkeypatch):
        """Field names are case-insensitive (model_config sets case_sensitive=False)."""
        monkeypatch.setenv("app_name", "lowercase override")
        s = _make_settings()
        assert s.app_name == "lowercase override"

    def test_extra_env_vars_ignored(self, monkeypatch):
        """Unknown env vars must not raise (extra='ignore')."""
        monkeypatch.setenv("TOTALLY_UNKNOWN_VAR", "whatever")
        s = _make_settings()  # should not raise
        assert s is not None


class TestSettingsSingleton:
    """Verify the module-level singleton is a properly typed Settings object."""

    def test_singleton_exists(self):
        from app.config import settings, Settings
        assert isinstance(settings, Settings)

    def test_singleton_has_all_fields(self):
        from app.config import settings
        # Access every field to confirm none raise AttributeError.
        _ = (
            settings.app_name,
            settings.debug,
            settings.groq_api_key,
            settings.groq_model,
            settings.cors_origins,
            settings.data_cache_ttl_seconds,
            settings.pdf_output_dir,
            settings.pdf_cleanup_interval_seconds,
            settings.pdf_max_age_seconds,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_settings():
    """Instantiate a fresh Settings object (reads current os.environ)."""
    from app.config import Settings
    return Settings()


@pytest.fixture()
def fresh_settings():
    """Return a Settings instance with no environment overrides active."""
    return _make_settings()

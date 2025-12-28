"""Tests for configuration."""

import os
from unittest.mock import patch

from src.config import Environment, Settings


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self):
        """Test default configuration values."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

        assert settings.app_env == Environment.DEVELOPMENT
        assert settings.debug is True
        assert settings.log_level == "INFO"
        assert settings.max_applications_per_day == 10
        assert settings.max_auto_applications_per_day == 5

    def test_environment_override(self):
        """Test environment variable overrides."""
        env_vars = {
            "APP_ENV": "production",
            "DEBUG": "false",
            "MAX_APPLICATIONS_PER_DAY": "20",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()

        assert settings.app_env == Environment.PRODUCTION
        assert settings.debug is False
        assert settings.max_applications_per_day == 20

    def test_is_production_property(self):
        """Test is_production property."""
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=True):
            settings = Settings()
            assert settings.is_production is True

        with patch.dict(os.environ, {"APP_ENV": "development"}, clear=True):
            settings = Settings()
            assert settings.is_production is False

    def test_is_development_property(self):
        """Test is_development property."""
        with patch.dict(os.environ, {"APP_ENV": "development"}, clear=True):
            settings = Settings()
            assert settings.is_development is True

        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=True):
            settings = Settings()
            assert settings.is_development is False

    def test_database_url_default(self):
        """Test default database URL."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

        assert "sqlite" in settings.database_url

    def test_langfuse_configuration(self):
        """Test Langfuse configuration."""
        env_vars = {
            "LANGFUSE_SECRET_KEY": "sk-lf-test",
            "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
            "LANGFUSE_BASE_URL": "https://custom.langfuse.com",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()

        assert settings.langfuse_secret_key == "sk-lf-test"
        assert settings.langfuse_public_key == "pk-lf-test"
        assert settings.langfuse_base_url == "https://custom.langfuse.com"


class TestEnvironmentEnum:
    """Tests for Environment enum."""

    def test_environment_values(self):
        """Test environment enum values."""
        assert Environment.DEVELOPMENT.value == "development"
        assert Environment.STAGING.value == "staging"
        assert Environment.PRODUCTION.value == "production"

    def test_environment_from_string(self):
        """Test creating environment from string."""
        assert Environment("development") == Environment.DEVELOPMENT
        assert Environment("production") == Environment.PRODUCTION

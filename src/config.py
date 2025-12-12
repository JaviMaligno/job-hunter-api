"""Application configuration using pydantic-settings."""

from enum import Enum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Application environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Environment = Environment.DEVELOPMENT
    debug: bool = True
    log_level: str = "INFO"

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/job_hunter.db"

    # Anthropic Claude SDK
    anthropic_api_key: str | None = None

    # AWS Bedrock (alternative to direct Anthropic API)
    bedrock_enabled: bool = False
    bedrock_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"

    # Langfuse Observability
    langfuse_secret_key: str | None = None
    langfuse_public_key: str | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # Google OAuth (Gmail)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    # Microsoft OAuth (Outlook)
    microsoft_client_id: str | None = None
    microsoft_client_secret: str | None = None
    microsoft_redirect_uri: str = "http://localhost:8000/api/auth/microsoft/callback"

    # Encryption for storing user API keys
    encryption_key: str | None = None

    # Rate Limiting
    max_applications_per_day: int = Field(default=10, ge=1, le=100)
    max_auto_applications_per_day: int = Field(default=5, ge=1, le=50)

    # Browser Service (Phase 2)
    browser_service_url: str = "http://localhost:8001"
    browser_service_timeout: int = Field(default=30000, ge=5000, le=120000)  # ms
    default_browser_mode: str = "playwright"  # "chrome-devtools" or "playwright"

    # Playwright Settings
    playwright_headless: bool = True
    playwright_slow_mo: int = Field(default=0, ge=0, le=1000)  # ms between actions

    # Application Automation
    pre_submit_pause: bool = True  # Always pause before submit in assisted mode
    screenshot_dir: str = "./data/screenshots"

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.app_env == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.app_env == Environment.DEVELOPMENT


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience access
settings = get_settings()

"""Tests for LinkedIn OAuth integration."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from src.db.models import EmailConnection, EmailProvider


class TestLinkedInRoutes:
    """Tests for LinkedIn OAuth routes."""

    def test_linkedin_provider_exists(self):
        """Test that LINKEDIN provider exists in EmailProvider enum."""
        assert hasattr(EmailProvider, "LINKEDIN")
        assert EmailProvider.LINKEDIN.value == "linkedin"

    def test_email_connection_with_linkedin(self):
        """Test that EmailConnection can be created with LinkedIn provider."""
        user_id = uuid4()
        connection = EmailConnection(
            user_id=user_id,
            provider=EmailProvider.LINKEDIN,
            access_token_encrypted="test_token",
            refresh_token_encrypted="test_refresh",
            token_expires_at=datetime.utcnow() + timedelta(days=60),
            granted_scopes="openid profile email",
            is_active=True,
        )

        assert connection.provider == EmailProvider.LINKEDIN
        assert connection.access_token_encrypted == "test_token"
        assert connection.is_active is True


class TestLinkedInClient:
    """Tests for LinkedIn client."""

    @pytest.mark.asyncio
    async def test_linkedin_client_creation(self):
        """Test LinkedInClient can be created with tokens."""
        from src.integrations.linkedin.client import LinkedInClient

        client = LinkedInClient(
            access_token="test_access_token", refresh_token="test_refresh_token"
        )

        assert client.access_token == "test_access_token"
        assert client.refresh_token == "test_refresh_token"

    def test_linkedin_client_auth_header(self):
        """Test LinkedInClient returns correct auth header."""
        from src.integrations.linkedin.client import LinkedInClient

        client = LinkedInClient(access_token="my_token")
        header = client.get_auth_header()

        assert header == {"Authorization": "Bearer my_token"}

    @pytest.mark.asyncio
    async def test_linkedin_client_session_cookies_empty(self):
        """Test that session cookies returns empty (OAuth tokens != browser cookies)."""
        from src.integrations.linkedin.client import LinkedInClient

        client = LinkedInClient(access_token="test_token")
        cookies = await client.get_session_cookies()

        # OAuth tokens cannot be converted to browser cookies
        assert cookies == []


class TestLinkedInConfig:
    """Tests for LinkedIn configuration."""

    def test_linkedin_config_exists(self):
        """Test that LinkedIn config fields exist in settings."""
        from src.config import Settings

        settings = Settings()

        # These should exist (may be None if not set)
        assert hasattr(settings, "linkedin_client_id")
        assert hasattr(settings, "linkedin_client_secret")
        assert hasattr(settings, "linkedin_redirect_uri")

    def test_linkedin_redirect_uri_default(self):
        """Test default LinkedIn redirect URI."""
        from src.config import Settings

        settings = Settings()

        assert settings.linkedin_redirect_uri == "http://localhost:8000/api/linkedin/callback"


class TestLinkedInRouterRegistration:
    """Tests for LinkedIn router registration."""

    def test_linkedin_router_has_routes(self):
        """Test that LinkedIn router has expected routes."""
        from src.api.routes.linkedin import router

        route_paths = [r.path for r in router.routes]

        assert "/connect/{user_id}" in route_paths
        assert "/callback" in route_paths
        assert "/status/{user_id}" in route_paths
        assert "/disconnect/{user_id}" in route_paths

    def test_linkedin_router_in_app(self):
        """Test that LinkedIn router is registered in the main app."""
        from src.main import app

        # Check that /api/linkedin routes exist
        route_paths = []
        for route in app.routes:
            if hasattr(route, "path"):
                route_paths.append(route.path)
            elif hasattr(route, "routes"):
                for subroute in route.routes:
                    if hasattr(subroute, "path"):
                        route_paths.append(f"{route.path}{subroute.path}")

        # The routes should be registered under /api/linkedin
        assert any(
            "/api/linkedin" in str(route)
            for route in app.routes
            if hasattr(route, "path") or hasattr(route, "prefix")
        )

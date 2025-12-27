"""LinkedIn client for session management and job applications."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import EmailConnection, EmailProvider


async def _refresh_token(refresh_token: str) -> dict:
    """Refresh LinkedIn access token using refresh token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.linkedin_client_id,
                "client_secret": settings.linkedin_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()


async def get_user_linkedin_credentials(
    db: AsyncSession, user_id: UUID
) -> tuple[str | None, str | None]:
    """
    Get LinkedIn credentials for a specific user from the database.

    Returns (access_token, refresh_token) or (None, None) if not connected.
    """
    result = await db.execute(
        select(EmailConnection).where(
            EmailConnection.user_id == user_id,
            EmailConnection.provider == EmailProvider.LINKEDIN,
            EmailConnection.is_active == True,  # noqa: E712
        )
    )
    connection = result.scalar_one_or_none()

    if not connection or not connection.access_token_encrypted:
        return None, None

    # Check if token is expired and refresh if needed
    if connection.token_expires_at and connection.token_expires_at < datetime.utcnow():
        if connection.refresh_token_encrypted:
            try:
                new_tokens = await _refresh_token(connection.refresh_token_encrypted)
                connection.access_token_encrypted = new_tokens["access_token"]
                if new_tokens.get("refresh_token"):
                    connection.refresh_token_encrypted = new_tokens["refresh_token"]
                expires_in = new_tokens.get("expires_in", 5184000)  # 60 days default
                connection.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                await db.flush()
            except Exception:
                # Token refresh failed - connection may be revoked
                connection.is_active = False
                await db.flush()
                return None, None

    return connection.access_token_encrypted, connection.refresh_token_encrypted


async def is_linkedin_connected(db: AsyncSession, user_id: UUID) -> bool:
    """Check if user has an active LinkedIn connection."""
    result = await db.execute(
        select(EmailConnection).where(
            EmailConnection.user_id == user_id,
            EmailConnection.provider == EmailProvider.LINKEDIN,
            EmailConnection.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none() is not None


class LinkedInClient:
    """
    LinkedIn client for session management.

    Used to get session cookies for browser automation of job applications.
    Note: LinkedIn's OAuth tokens cannot directly be used as browser cookies,
    but having an active connection indicates the user has authorized the app.
    """

    def __init__(self, access_token: str, refresh_token: str | None = None):
        """
        Initialize LinkedIn client with access token.

        Args:
            access_token: OAuth2 access token
            refresh_token: OAuth2 refresh token (optional)
        """
        self.access_token = access_token
        self.refresh_token = refresh_token

    @classmethod
    async def for_user(cls, db: AsyncSession, user_id: UUID) -> "LinkedInClient | None":
        """
        Create a LinkedInClient for a specific user.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            LinkedInClient instance or None if user has no LinkedIn connection.
        """
        access_token, refresh_token = await get_user_linkedin_credentials(db, user_id)
        if not access_token:
            return None
        return cls(access_token, refresh_token)

    async def get_user_info(self) -> dict[str, Any]:
        """Get user profile information from LinkedIn."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            response.raise_for_status()
            return response.json()

    async def is_token_valid(self) -> bool:
        """Check if the access token is still valid."""
        try:
            await self.get_user_info()
            return True
        except Exception:
            return False

    def get_auth_header(self) -> dict[str, str]:
        """Get Authorization header for API requests."""
        return {"Authorization": f"Bearer {self.access_token}"}

    async def get_session_cookies(self) -> list[dict[str, Any]]:
        """
        Get cookies for browser session injection.

        Note: OAuth tokens cannot be directly converted to browser cookies.
        LinkedIn uses different authentication for browser sessions.
        This method returns a structure that indicates LinkedIn is connected,
        which the browser automation can use to determine if login is needed.

        Returns:
            List of cookie dictionaries for CDP injection, or empty if not possible.
        """
        # LinkedIn OAuth tokens don't translate to browser cookies directly.
        # The browser automation will need to:
        # 1. Check if user has LinkedIn OAuth connected
        # 2. If yes, try to navigate to LinkedIn job
        # 3. If login is required, it will be detected as a blocker
        #
        # For now, return empty - the important thing is that we can check
        # if the user has authorized LinkedIn integration.
        return []

"""Base OAuth provider class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OAuthUserInfo:
    """User information from OAuth provider."""

    provider_user_id: str
    email: str
    email_verified: bool = False
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None
    raw_data: dict | None = None


class OAuthProvider(ABC):
    """Abstract base class for OAuth providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'google', 'linkedin', 'github')."""
        pass

    @property
    @abstractmethod
    def authorization_url(self) -> str:
        """OAuth authorization URL."""
        pass

    @property
    @abstractmethod
    def token_url(self) -> str:
        """OAuth token exchange URL."""
        pass

    @property
    @abstractmethod
    def scopes(self) -> list[str]:
        """Required OAuth scopes."""
        pass

    @abstractmethod
    def get_authorization_url(self, state: str) -> str:
        """Generate the authorization URL for the OAuth flow.

        Args:
            state: CSRF protection state parameter.

        Returns:
            Full authorization URL to redirect user to.
        """
        pass

    @abstractmethod
    async def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback.

        Returns:
            Token response containing access_token and possibly refresh_token.
        """
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Get user information from the provider.

        Args:
            access_token: OAuth access token.

        Returns:
            User information from the provider.
        """
        pass

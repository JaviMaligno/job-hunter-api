"""Google OAuth provider."""

from urllib.parse import urlencode

import httpx

from src.auth.providers.base import OAuthProvider, OAuthUserInfo
from src.config import settings


class GoogleProvider(OAuthProvider):
    """Google OAuth 2.0 provider."""

    @property
    def name(self) -> str:
        return "google"

    @property
    def authorization_url(self) -> str:
        return "https://accounts.google.com/o/oauth2/v2/auth"

    @property
    def token_url(self) -> str:
        return "https://oauth2.googleapis.com/token"

    @property
    def user_info_url(self) -> str:
        return "https://www.googleapis.com/oauth2/v2/userinfo"

    @property
    def scopes(self) -> list[str]:
        return ["openid", "email", "profile"]

    def get_authorization_url(self, state: str) -> str:
        """Generate Google authorization URL."""
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            "access_type": "offline",  # Get refresh token
            "prompt": "consent",  # Always show consent screen
        }
        return f"{self.authorization_url}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            return response.json()

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Get user info from Google."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.user_info_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            data = response.json()

        return OAuthUserInfo(
            provider_user_id=data["id"],
            email=data["email"],
            email_verified=data.get("verified_email", False),
            first_name=data.get("given_name"),
            last_name=data.get("family_name"),
            avatar_url=data.get("picture"),
            raw_data=data,
        )

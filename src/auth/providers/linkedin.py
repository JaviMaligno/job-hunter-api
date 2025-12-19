"""LinkedIn OAuth provider."""

from urllib.parse import urlencode

import httpx

from src.auth.providers.base import OAuthProvider, OAuthUserInfo
from src.config import settings


class LinkedInProvider(OAuthProvider):
    """LinkedIn OAuth 2.0 provider."""

    @property
    def name(self) -> str:
        return "linkedin"

    @property
    def authorization_url(self) -> str:
        return "https://www.linkedin.com/oauth/v2/authorization"

    @property
    def token_url(self) -> str:
        return "https://www.linkedin.com/oauth/v2/accessToken"

    @property
    def user_info_url(self) -> str:
        return "https://api.linkedin.com/v2/userinfo"

    @property
    def scopes(self) -> list[str]:
        # OpenID Connect scopes for LinkedIn
        return ["openid", "profile", "email"]

    def get_authorization_url(self, state: str) -> str:
        """Generate LinkedIn authorization URL."""
        params = {
            "client_id": settings.linkedin_client_id,
            "redirect_uri": settings.linkedin_redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
        }
        return f"{self.authorization_url}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "client_id": settings.linkedin_client_id,
                    "client_secret": settings.linkedin_client_secret,
                    "code": code,
                    "redirect_uri": settings.linkedin_redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            return response.json()

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Get user info from LinkedIn using OpenID Connect."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.user_info_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            data = response.json()

        return OAuthUserInfo(
            provider_user_id=data["sub"],
            email=data.get("email", ""),
            email_verified=data.get("email_verified", False),
            first_name=data.get("given_name"),
            last_name=data.get("family_name"),
            avatar_url=data.get("picture"),
            raw_data=data,
        )

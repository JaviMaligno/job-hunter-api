"""GitHub OAuth provider."""

from urllib.parse import urlencode

import httpx

from src.auth.providers.base import OAuthProvider, OAuthUserInfo
from src.config import settings


class GitHubProvider(OAuthProvider):
    """GitHub OAuth 2.0 provider."""

    @property
    def name(self) -> str:
        return "github"

    @property
    def authorization_url(self) -> str:
        return "https://github.com/login/oauth/authorize"

    @property
    def token_url(self) -> str:
        return "https://github.com/login/oauth/access_token"

    @property
    def user_info_url(self) -> str:
        return "https://api.github.com/user"

    @property
    def emails_url(self) -> str:
        return "https://api.github.com/user/emails"

    @property
    def scopes(self) -> list[str]:
        return ["read:user", "user:email"]

    def get_authorization_url(self, state: str) -> str:
        """Generate GitHub authorization URL."""
        params = {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_redirect_uri,
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
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": settings.github_redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Get user info from GitHub."""
        async with httpx.AsyncClient() as client:
            # Get basic user info
            user_response = await client.get(
                self.user_info_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            user_response.raise_for_status()
            user_data = user_response.json()

            # Get user emails (primary and verified)
            email_response = await client.get(
                self.emails_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            email_response.raise_for_status()
            emails_data = email_response.json()

        # Find primary verified email
        primary_email = None
        email_verified = False
        for email_info in emails_data:
            if email_info.get("primary"):
                primary_email = email_info.get("email")
                email_verified = email_info.get("verified", False)
                break

        # Fallback to first email if no primary
        if not primary_email and emails_data:
            primary_email = emails_data[0].get("email")
            email_verified = emails_data[0].get("verified", False)

        # Parse name (GitHub has single 'name' field)
        full_name = user_data.get("name", "")
        first_name = None
        last_name = None
        if full_name:
            name_parts = full_name.split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else None

        return OAuthUserInfo(
            provider_user_id=str(user_data["id"]),
            email=primary_email or user_data.get("email", ""),
            email_verified=email_verified,
            first_name=first_name,
            last_name=last_name,
            avatar_url=user_data.get("avatar_url"),
            raw_data=user_data,
        )

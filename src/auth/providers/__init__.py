"""OAuth provider implementations."""

from src.auth.providers.base import OAuthProvider, OAuthUserInfo
from src.auth.providers.github import GitHubProvider
from src.auth.providers.google import GoogleProvider
from src.auth.providers.linkedin import LinkedInProvider

__all__ = [
    "OAuthProvider",
    "OAuthUserInfo",
    "GoogleProvider",
    "LinkedInProvider",
    "GitHubProvider",
]

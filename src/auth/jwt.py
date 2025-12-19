"""JWT token utilities."""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import JWTError, jwt

from src.config import settings


class TokenError(Exception):
    """Exception raised for token-related errors."""

    pass


def create_access_token(
    user_id: UUID,
    email: str,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """Create a new JWT access token.

    Args:
        user_id: User's unique identifier.
        email: User's email address.
        additional_claims: Optional additional claims to include in token.

    Returns:
        Encoded JWT token string.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )

    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(user_id: UUID) -> tuple[str, str, datetime]:
    """Create a new JWT refresh token.

    Args:
        user_id: User's unique identifier.

    Returns:
        Tuple of (token string, token hash for storage, expiry datetime).
    """
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )

    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    # Create hash of token for secure storage
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    return token, token_hash, expire


def verify_token(token: str, token_type: str = "access") -> dict[str, Any]:
    """Verify and decode a JWT token.

    Args:
        token: JWT token string to verify.
        token_type: Expected token type ('access' or 'refresh').

    Returns:
        Decoded token payload.

    Raises:
        TokenError: If token is invalid, expired, or wrong type.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )

        # Verify token type
        if payload.get("type") != token_type:
            raise TokenError(f"Invalid token type. Expected {token_type}.")

        # Verify user_id exists
        if not payload.get("sub"):
            raise TokenError("Token missing user identifier.")

        return payload

    except JWTError as e:
        raise TokenError(f"Invalid token: {e!s}") from e


def hash_token(token: str) -> str:
    """Create a hash of a token for secure storage.

    Args:
        token: Token string to hash.

    Returns:
        SHA256 hash of the token.
    """
    return hashlib.sha256(token.encode()).hexdigest()

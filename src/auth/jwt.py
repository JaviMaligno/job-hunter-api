"""JWT token utilities."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509 import load_pem_x509_certificate
from jwt import PyJWTError

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
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)

    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
        "iat": datetime.now(UTC),
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
    expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)

    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(UTC),
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


def _verification_key(key: str | bytes, algorithm: str) -> str | bytes | RSAPublicKey:
    """Keep the existing RSA private-PEM/certificate verification formats."""
    if algorithm not in {"RS256", "RS384", "RS512"}:
        return key
    encoded = (key.encode("utf-8") if isinstance(key, str) else key).lstrip()
    try:
        if encoded.startswith(b"-----BEGIN CERTIFICATE-----"):
            public = load_pem_x509_certificate(encoded).public_key()
            if not isinstance(public, RSAPublicKey):
                raise jwt.InvalidKeyError("Expected an RSA verification certificate")
            return public
        if encoded.startswith((b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN RSA PRIVATE KEY-----")):
            private = load_pem_private_key(encoded, password=None)
            if not isinstance(private, RSAPrivateKey):
                raise jwt.InvalidKeyError("Expected an RSA private key")
            return private.public_key()
    except (TypeError, ValueError, UnsupportedAlgorithm) as error:
        raise jwt.InvalidKeyError("Invalid RSA verification key") from error
    return key


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
            _verification_key(settings.jwt_secret_key, settings.jwt_algorithm),
            algorithms=[settings.jwt_algorithm],
        )

        # Preserve existing audience/OIDC rejection after signature validation.
        # No caller supplies an expected audience or a separate OIDC access token.
        if "aud" in payload:
            raise jwt.InvalidAudienceError("Invalid audience")
        if "at_hash" in payload:
            raise jwt.InvalidTokenError(
                "No access_token provided to compare against at_hash claim."
            )

        # Verify token type
        if payload.get("type") != token_type:
            raise TokenError(f"Invalid token type. Expected {token_type}.")

        # Verify user_id exists
        if not payload.get("sub"):
            raise TokenError("Token missing user identifier.")

        return payload

    except PyJWTError as e:
        raise TokenError(f"Invalid token: {e!s}") from e


def hash_token(token: str) -> str:
    """Create a hash of a token for secure storage.

    Args:
        token: Token string to hash.

    Returns:
        SHA256 hash of the token.
    """
    return hashlib.sha256(token.encode()).hexdigest()

"""LinkedIn OAuth routes for connecting user's LinkedIn account."""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from src.api.dependencies import DbDep
from src.config import settings
from src.db.models import EmailConnection, EmailProvider, User


def _generate_state(user_id: str) -> str:
    """Generate a secure state token that encodes the user_id."""
    # Create a random nonce
    nonce = secrets.token_urlsafe(16)
    # Create payload: user_id|nonce
    payload = f"{user_id}|{nonce}"
    # Create HMAC signature
    secret_key = (settings.secret_key or "default-secret-key").encode()
    signature = hmac.new(secret_key, payload.encode(), hashlib.sha256).hexdigest()[:16]
    # Encode as base64: payload|signature
    state_data = f"{payload}|{signature}"
    return base64.urlsafe_b64encode(state_data.encode()).decode()


def _verify_state(state: str) -> str | None:
    """Verify state token and extract user_id. Returns None if invalid."""
    try:
        state_data = base64.urlsafe_b64decode(state.encode()).decode()
        parts = state_data.split("|")
        if len(parts) != 3:
            return None
        user_id, nonce, signature = parts
        # Verify signature
        payload = f"{user_id}|{nonce}"
        secret_key = (settings.secret_key or "default-secret-key").encode()
        expected_signature = hmac.new(secret_key, payload.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(signature, expected_signature):
            return None
        return user_id
    except Exception:
        return None


router = APIRouter()

# LinkedIn OAuth scopes
# https://learn.microsoft.com/en-us/linkedin/shared/authentication/authentication
LINKEDIN_SCOPES = [
    "openid",  # Required for OIDC
    "profile",  # Read basic profile
    "email",  # Get user's email
]


# ============================================================================
# Schemas
# ============================================================================


class LinkedInStatusResponse(BaseModel):
    """Response for LinkedIn connection status."""

    connected: bool
    email: str | None = None
    name: str | None = None
    profile_url: str | None = None
    last_sync_at: datetime | None = None


class LinkedInConnectionResponse(BaseModel):
    """Response after successful LinkedIn connection."""

    success: bool
    message: str


# ============================================================================
# Helper Functions
# ============================================================================


def _get_linkedin_authorization_url(state: str) -> str:
    """Generate LinkedIn OAuth authorization URL."""
    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": settings.linkedin_redirect_uri,
        "state": state,
        "scope": " ".join(LINKEDIN_SCOPES),
    }
    return f"https://www.linkedin.com/oauth/v2/authorization?{urlencode(params)}"


async def _exchange_code_for_tokens(code: str) -> dict:
    """Exchange authorization code for LinkedIn tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.linkedin_client_id,
                "client_secret": settings.linkedin_client_secret,
                "redirect_uri": settings.linkedin_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()


async def _refresh_linkedin_token(refresh_token: str) -> dict:
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


async def _get_linkedin_user_info(access_token: str) -> dict:
    """Get the user info from LinkedIn using the access token."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()


# ============================================================================
# Routes
# ============================================================================


@router.get("/connect/{user_id}")
async def initiate_linkedin_connection(
    user_id: UUID,
    db: DbDep,
) -> RedirectResponse:
    """
    Initiate LinkedIn OAuth flow for a user.

    This redirects the user to LinkedIn's authorization page.
    After authorization, LinkedIn redirects back to /api/linkedin/callback.
    """
    # Verify user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not settings.linkedin_client_id or not settings.linkedin_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LinkedIn OAuth not configured. Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET.",
        )

    # Generate state with embedded user_id (survives server restarts)
    state = _generate_state(str(user_id))

    auth_url = _get_linkedin_authorization_url(state)
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def linkedin_oauth_callback(
    db: DbDep,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
) -> RedirectResponse:
    """
    Handle LinkedIn OAuth callback.

    Exchanges the authorization code for tokens and stores them.
    """
    # Handle errors from LinkedIn
    if error:
        error_msg = error_description or error
        error_url = f"{settings.frontend_url}/profile?linkedin_error={error_msg}"
        return RedirectResponse(url=error_url)

    if not code or not state:
        error_url = f"{settings.frontend_url}/profile?linkedin_error=missing_params"
        return RedirectResponse(url=error_url)

    # Verify state and extract user_id
    user_id_str = _verify_state(state)
    if not user_id_str:
        error_url = f"{settings.frontend_url}/profile?linkedin_error=invalid_state"
        return RedirectResponse(url=error_url)

    user_id = UUID(user_id_str)

    try:
        # Exchange code for tokens
        token_data = await _exchange_code_for_tokens(code)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 5184000)  # LinkedIn default is 60 days
        scope = token_data.get("scope", "")

        if not access_token:
            raise ValueError("No access token received")

        # Get the LinkedIn user info
        user_info = await _get_linkedin_user_info(access_token)
        user_info.get("email", "")
        linkedin_name = user_info.get("name", "")

        # Calculate token expiry
        token_expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=expires_in)

        # Find or create EmailConnection (using LINKEDIN provider)
        result = await db.execute(
            select(EmailConnection).where(
                EmailConnection.user_id == user_id,
                EmailConnection.provider == EmailProvider.LINKEDIN,
            )
        )
        connection = result.scalar_one_or_none()

        if connection:
            # Update existing connection
            connection.access_token_encrypted = access_token  # TODO: encrypt
            connection.refresh_token_encrypted = refresh_token  # TODO: encrypt
            connection.token_expires_at = token_expires_at
            connection.granted_scopes = scope
            connection.is_active = True
        else:
            # Create new connection
            connection = EmailConnection(
                user_id=user_id,
                provider=EmailProvider.LINKEDIN,
                access_token_encrypted=access_token,  # TODO: encrypt
                refresh_token_encrypted=refresh_token,  # TODO: encrypt
                token_expires_at=token_expires_at,
                granted_scopes=scope,
                is_active=True,
            )
            db.add(connection)

        await db.flush()

        # Redirect to frontend with success
        success_url = (
            f"{settings.frontend_url}/profile?linkedin_connected=true&linkedin_name={linkedin_name}"
        )
        return RedirectResponse(url=success_url)

    except httpx.HTTPStatusError:
        error_url = f"{settings.frontend_url}/profile?linkedin_error=token_exchange_failed"
        return RedirectResponse(url=error_url)
    except Exception as e:
        error_url = f"{settings.frontend_url}/profile?linkedin_error={str(e)}"
        return RedirectResponse(url=error_url)


@router.get("/status/{user_id}", response_model=LinkedInStatusResponse)
async def get_linkedin_status(user_id: UUID, db: DbDep) -> LinkedInStatusResponse:
    """
    Check if a user has LinkedIn connected.

    Returns connection status and profile info if connected.
    """
    # Find LinkedIn connection
    result = await db.execute(
        select(EmailConnection).where(
            EmailConnection.user_id == user_id,
            EmailConnection.provider == EmailProvider.LINKEDIN,
            EmailConnection.is_active == True,  # noqa: E712
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        return LinkedInStatusResponse(connected=False)

    # Try to get user info from token (if still valid)
    email = None
    name = None
    if connection.access_token_encrypted:
        try:
            # Check if token is expired
            if connection.token_expires_at and connection.token_expires_at < datetime.utcnow():
                # Try to refresh token
                if connection.refresh_token_encrypted:
                    token_data = await _refresh_linkedin_token(connection.refresh_token_encrypted)
                    connection.access_token_encrypted = token_data.get("access_token")
                    expires_in = token_data.get("expires_in", 5184000)
                    connection.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                    await db.flush()

            user_info = await _get_linkedin_user_info(connection.access_token_encrypted)
            email = user_info.get("email")
            name = user_info.get("name")
        except Exception:
            # Token might be revoked
            pass

    return LinkedInStatusResponse(
        connected=True,
        email=email,
        name=name,
        last_sync_at=connection.last_sync_at,
    )


@router.delete("/disconnect/{user_id}")
async def disconnect_linkedin(user_id: UUID, db: DbDep) -> LinkedInConnectionResponse:
    """
    Disconnect LinkedIn from a user's account.

    This removes the connection (LinkedIn doesn't support programmatic token revocation).
    """
    # Find LinkedIn connection
    result = await db.execute(
        select(EmailConnection).where(
            EmailConnection.user_id == user_id,
            EmailConnection.provider == EmailProvider.LINKEDIN,
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No LinkedIn connection found",
        )

    # Delete the connection
    await db.delete(connection)
    await db.flush()

    return LinkedInConnectionResponse(
        success=True,
        message="LinkedIn disconnected successfully",
    )

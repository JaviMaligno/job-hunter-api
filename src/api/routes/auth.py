"""Authentication API routes."""

import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from src.api.dependencies import CurrentUser, DbDep
from src.auth.jwt import (
    TokenError,
    create_access_token,
    create_refresh_token,
    hash_token,
    verify_token,
)
from src.auth.password import hash_password, verify_password
from src.auth.providers import GitHubProvider, GoogleProvider, LinkedInProvider
from src.config import settings
from src.db.models import AuthProvider, RefreshToken, User

router = APIRouter()

# OAuth state storage (in production, use Redis or database)
_oauth_states: dict[str, dict] = {}


# ============================================================================
# Schemas
# ============================================================================


class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)


class LoginRequest(BaseModel):
    """User login request."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token response for login/register."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str


class UserResponse(BaseModel):
    """User profile response."""

    id: str
    email: str
    first_name: str | None
    last_name: str | None
    avatar_url: str | None
    auth_provider: str
    email_verified: bool

    class Config:
        from_attributes = True


# ============================================================================
# Email/Password Authentication
# ============================================================================


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: DbDep) -> TokenResponse:
    """
    Register a new user with email and password.

    Returns access and refresh tokens on successful registration.
    """
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == request.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user
    user = User(
        email=request.email,
        password_hash=hash_password(request.password),
        first_name=request.first_name,
        last_name=request.last_name,
        auth_provider=AuthProvider.EMAIL,
        email_verified=False,
    )
    db.add(user)
    await db.flush()

    # Create tokens
    access_token = create_access_token(user.id, user.email)
    refresh_token, token_hash, expires_at = create_refresh_token(user.id)

    # Store refresh token
    db_refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(db_refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: DbDep) -> TokenResponse:
    """
    Login with email and password.

    Returns access and refresh tokens on successful login.
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Verify password
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Create tokens
    access_token = create_access_token(user.id, user.email)
    refresh_token, token_hash, expires_at = create_refresh_token(user.id)

    # Store refresh token
    db_refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(db_refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(request: RefreshRequest, db: DbDep) -> TokenResponse:
    """
    Refresh access token using a refresh token.

    The old refresh token is revoked and a new one is issued.
    """
    try:
        payload = verify_token(request.refresh_token, token_type="refresh")
    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e

    # Find refresh token in database
    token_hash = hash_token(request.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,  # noqa: E712
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    db_token = result.scalar_one_or_none()

    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Get user
    user_result = await db.execute(select(User).where(User.id == db_token.user_id))
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Revoke old token
    db_token.revoked = True

    # Create new tokens
    access_token = create_access_token(user.id, user.email)
    new_refresh_token, new_token_hash, expires_at = create_refresh_token(user.id)

    # Store new refresh token
    new_db_token = RefreshToken(
        user_id=user.id,
        token_hash=new_token_hash,
        expires_at=expires_at,
    )
    db.add(new_db_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/logout")
async def logout(
    current_user: CurrentUser,
    db: DbDep,
    refresh_token: str | None = None,
) -> dict:
    """
    Logout the current user.

    If refresh_token is provided, only that token is revoked.
    Otherwise, all refresh tokens for the user are revoked.
    """
    if refresh_token:
        # Revoke specific token
        token_hash = hash_token(refresh_token)
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.user_id == current_user.id,
            )
        )
        db_token = result.scalar_one_or_none()
        if db_token:
            db_token.revoked = True
    else:
        # Revoke all tokens for user
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == current_user.id,
                RefreshToken.revoked == False,  # noqa: E712
            )
        )
        tokens = result.scalars().all()
        for token in tokens:
            token.revoked = True

    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: CurrentUser) -> UserResponse:
    """Get the current authenticated user's profile."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        avatar_url=current_user.avatar_url,
        auth_provider=current_user.auth_provider.value if current_user.auth_provider else "email",
        email_verified=current_user.email_verified or False,
    )


# ============================================================================
# OAuth Authentication
# ============================================================================


def _get_provider(provider_name: str):
    """Get OAuth provider by name."""
    providers = {
        "google": GoogleProvider(),
        "linkedin": LinkedInProvider(),
        "github": GitHubProvider(),
    }
    provider = providers.get(provider_name)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown OAuth provider: {provider_name}",
        )
    return provider


@router.get("/{provider}")
async def oauth_login(provider: str) -> RedirectResponse:
    """
    Initiate OAuth login flow.

    Redirects the user to the OAuth provider's authorization page.
    """
    oauth_provider = _get_provider(provider)

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = {
        "provider": provider,
        "created_at": datetime.now(timezone.utc),
    }

    auth_url = oauth_provider.get_authorization_url(state)
    return RedirectResponse(url=auth_url)


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    db: DbDep,
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
) -> RedirectResponse:
    """
    Handle OAuth callback from provider.

    Exchanges the authorization code for tokens, creates or updates the user,
    and redirects to the frontend with tokens.
    """
    # Verify state
    state_data = _oauth_states.pop(state, None)
    if not state_data or state_data["provider"] != provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state",
        )

    oauth_provider = _get_provider(provider)

    try:
        # Exchange code for tokens
        token_data = await oauth_provider.exchange_code(code)
        access_token = token_data.get("access_token")

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No access token received from provider",
            )

        # Get user info from provider
        user_info = await oauth_provider.get_user_info(access_token)

    except Exception as e:
        # Redirect to frontend with error
        error_url = f"{settings.frontend_url}/login?error=oauth_failed&message={str(e)}"
        return RedirectResponse(url=error_url)

    # Find or create user
    result = await db.execute(select(User).where(User.email == user_info.email))
    user = result.scalar_one_or_none()

    auth_provider_enum = AuthProvider(provider)

    if user:
        # Update existing user with OAuth info
        if not user.provider_user_id:
            user.provider_user_id = user_info.provider_user_id
            user.auth_provider = auth_provider_enum
        if user_info.avatar_url and not user.avatar_url:
            user.avatar_url = user_info.avatar_url
        if user_info.email_verified:
            user.email_verified = True
    else:
        # Create new user
        user = User(
            email=user_info.email,
            first_name=user_info.first_name,
            last_name=user_info.last_name,
            avatar_url=user_info.avatar_url,
            auth_provider=auth_provider_enum,
            provider_user_id=user_info.provider_user_id,
            email_verified=user_info.email_verified,
        )
        db.add(user)
        await db.flush()

    # Create tokens
    jwt_access_token = create_access_token(user.id, user.email)
    refresh_token, token_hash, expires_at = create_refresh_token(user.id)

    # Store refresh token
    db_refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(db_refresh_token)

    # Redirect to frontend with tokens
    # In production, you might want to use a more secure method (e.g., httpOnly cookies)
    redirect_url = (
        f"{settings.frontend_url}/auth/callback"
        f"?access_token={jwt_access_token}"
        f"&refresh_token={refresh_token}"
    )
    return RedirectResponse(url=redirect_url)

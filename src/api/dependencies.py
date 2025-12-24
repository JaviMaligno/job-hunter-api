"""FastAPI dependencies."""

from typing import Annotated
from uuid import UUID

from anthropic import Anthropic
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.jwt import TokenError, verify_token
from src.config import settings
from src.db.models import User
from src.db.session import get_db
from src.integrations.claude.client import get_claude_client


# HTTP Bearer security scheme
security = HTTPBearer(auto_error=False)


async def get_claude_dependency(
    x_anthropic_api_key: Annotated[str | None, Header()] = None,
) -> Anthropic:
    """
    Dependency to get Claude client.

    Supports:
    1. AWS Bedrock (if BEDROCK_ENABLED=true) - uses AWS credentials
    2. Direct Anthropic API - requires API key from header or environment
    """
    # If Bedrock is enabled, no API key is needed
    if settings.bedrock_enabled:
        return get_claude_client()

    # Otherwise, require an API key
    api_key = x_anthropic_api_key or settings.anthropic_api_key
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Anthropic API key required. Provide via X-Anthropic-Api-Key header, configure ANTHROPIC_API_KEY, or enable BEDROCK_ENABLED=true.",
        )
    return get_claude_client(api_key)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.

    Raises HTTPException 401 if not authenticated.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = verify_token(credentials.credentials, token_type="access")
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        # Convert string user_id to UUID for database query
        try:
            user_uuid = UUID(user_id)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user ID format in token",
            ) from e

        # Get user from database
        result = await db.execute(select(User).where(User.id == user_uuid))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        return user

    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


# Type aliases for dependency injection
ClaudeDep = Annotated[Anthropic, Depends(get_claude_dependency)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

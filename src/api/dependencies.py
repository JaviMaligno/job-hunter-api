"""FastAPI dependencies."""

from typing import Annotated

from anthropic import Anthropic
from fastapi import Header, HTTPException

from src.config import settings
from src.integrations.claude.client import get_claude_client


async def get_claude_dependency(
    x_anthropic_api_key: Annotated[str | None, Header()] = None,
) -> Anthropic:
    """
    Dependency to get Claude client.

    Users can provide their own API key via X-Anthropic-Api-Key header.
    Falls back to environment variable if not provided.
    """
    api_key = x_anthropic_api_key or settings.anthropic_api_key
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Anthropic API key required. Provide via X-Anthropic-Api-Key header or configure ANTHROPIC_API_KEY environment variable.",
        )
    return get_claude_client(api_key)


# Type alias for dependency injection
ClaudeDep = Annotated[Anthropic, get_claude_dependency]

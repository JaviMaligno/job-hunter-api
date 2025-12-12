"""Langfuse tracing configuration."""

from functools import lru_cache

from langfuse import Langfuse

from src.config import settings


@lru_cache
def get_langfuse() -> Langfuse | None:
    """
    Get Langfuse client instance.

    Returns:
        Langfuse client if configured, None otherwise.
    """
    if not settings.langfuse_secret_key or not settings.langfuse_public_key:
        return None

    return Langfuse(
        secret_key=settings.langfuse_secret_key,
        public_key=settings.langfuse_public_key,
        host=settings.langfuse_base_url,
    )


def init_langfuse() -> None:
    """Initialize Langfuse for the application."""
    client = get_langfuse()
    if client:
        # Verify connection
        try:
            client.auth_check()
        except Exception as e:
            import logging

            logging.warning(f"Langfuse auth check failed: {e}")


def flush_langfuse() -> None:
    """Flush pending Langfuse traces (call on shutdown)."""
    client = get_langfuse()
    if client:
        client.flush()


def shutdown_langfuse() -> None:
    """Shutdown Langfuse client properly."""
    client = get_langfuse()
    if client:
        client.shutdown()

"""Import the real applications router without providers, jobs or DB access."""

import importlib
import inspect

import anthropic
import httpx
from sqlalchemy.ext.asyncio import AsyncEngine


def test_applications_router_registers_real_database_dependency(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Import contract must not initialize providers or connect to data")

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("BEDROCK_ENABLED", "false")
    for name in (
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGSMITH_API_KEY",
        "LANGCHAIN_API_KEY",
    ):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setattr(anthropic.Anthropic, "__init__", forbidden)
    monkeypatch.setattr(anthropic.AnthropicBedrock, "__init__", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    monkeypatch.setattr(AsyncEngine, "connect", forbidden)

    # Actual route decorators resolve the annotation during this import. Do not
    # start main's lifespan, call any endpoint, create an agent or execute get_db.
    applications = importlib.import_module("src.api.routes.applications")
    from src.api.dependencies import DbDep
    from src.db.session import get_db

    endpoint = applications.mark_session_applied
    assert inspect.signature(endpoint).parameters["db"].annotation == DbDep
    route = next(route for route in applications.router.routes if route.endpoint is endpoint)
    assert any(dependency.call is get_db for dependency in route.dependant.dependencies)

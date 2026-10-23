"""Browser resource contracts without SDK, browser, HTTP or database access."""

import ast
import importlib
import inspect
import sys
import textwrap
import types
from unittest.mock import AsyncMock, Mock

import anthropic
import httpx
import pytest
from pydantic_settings.sources import DotEnvSettingsSource
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
def orchestrator_module(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline contract crossed a provider or data boundary")

    for name in (
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGSMITH_API_KEY",
        "LANGCHAIN_API_KEY",
    ):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("BEDROCK_ENABLED", "false")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setattr(anthropic.Anthropic, "__init__", forbidden)
    monkeypatch.setattr(anthropic.AnthropicBedrock, "__init__", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    monkeypatch.setattr(AsyncEngine, "connect", forbidden)
    monkeypatch.setattr(DotEnvSettingsSource, "_read_env_files", lambda self: {})
    playwright = types.ModuleType("playwright")
    playwright.__path__ = []
    playwright_api = types.ModuleType("playwright.async_api")
    for type_name in ("Browser", "BrowserContext", "Page"):
        setattr(playwright_api, type_name, type(type_name, (), {}))
    playwright_api.async_playwright = forbidden
    playwright.async_api = playwright_api
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_api)

    # This minimum framework environment intentionally does not install Gemini.
    # Replace only the SDK boundary; import the real application and browser types.
    google = types.ModuleType("google")
    google.__path__ = []
    genai = types.ModuleType("google.genai")
    errors = types.ModuleType("google.genai.errors")
    errors.ClientError = type("ClientError", (Exception,), {})
    genai.errors = errors
    genai.Client = Mock(return_value=types.SimpleNamespace(models=Mock()))
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.errors", errors)
    decorators = types.ModuleType("langfuse.decorators")
    decorators.observe = lambda **kwargs: lambda function: function
    decorators.langfuse_context = Mock()
    monkeypatch.setitem(sys.modules, "langfuse.decorators", decorators)
    name = "src.agents.gemini_http_orchestrator"
    monkeypatch.delitem(sys.modules, name, raising=False)
    browser_name = "src.automation.browserless_client"
    previous_browser = sys.modules.get(browser_name)
    module = importlib.import_module(name)
    monkeypatch.setattr(module.BrowserlessClient, "__aenter__", forbidden)
    yield module
    sys.modules.pop(name, None)
    if previous_browser is None:
        sys.modules.pop(browser_name, None)


def test_browser_annotation_resolves_to_actual_context_manager(orchestrator_module):
    module = orchestrator_module
    init = ast.parse(
        textwrap.dedent(inspect.getsource(module.GeminiHTTPOrchestratorAgent.__init__))
    )
    annotation = next(
        node.annotation
        for node in ast.walk(init)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Attribute)
        and node.target.attr == "_browser"
    )
    annotated_type = eval(
        compile(ast.Expression(annotation), "<browser annotation>", "eval"), vars(module)
    )
    run = ast.parse(textwrap.dedent(inspect.getsource(module.GeminiHTTPOrchestratorAgent.run)))
    resource_name = next(
        node.items[0].context_expr.func.id
        for node in ast.walk(run)
        if isinstance(node, ast.AsyncWith)
    )
    assert annotated_type == vars(module)[resource_name] | None
    assert vars(module)[resource_name].__module__ == "src.automation.browserless_client"


def test_page_info_preserves_browserless_payload_without_provider_calls(orchestrator_module):
    import asyncio

    module = orchestrator_module
    agent = module.GeminiHTTPOrchestratorAgent(
        api_key="synthetic-not-a-key", auto_solve_captcha=False
    )
    module.genai.Client.assert_called_once_with(api_key="synthetic-not-a-key")
    assert agent._browser is None
    with pytest.raises(RuntimeError, match="Browser not initialized"):
        asyncio.run(agent._get_page_info())
    browser = module.BrowserlessClient.__new__(module.BrowserlessClient)
    attributes = {"type": "email", "name": "email", "id": "email", "required": ""}
    element = types.SimpleNamespace(
        evaluate=AsyncMock(return_value="input"),
        get_attribute=AsyncMock(side_effect=lambda key: attributes.get(key)),
    )
    browser._page = types.SimpleNamespace(
        url="https://synthetic.invalid/form",
        content=AsyncMock(return_value="x" * 15001),
        title=AsyncMock(return_value="Synthetic form"),
        query_selector_all=AsyncMock(return_value=[element]),
    )
    agent._browser = browser
    assert asyncio.run(agent._get_page_info()) == {
        "html": "x" * 15000,
        "url": "https://synthetic.invalid/form",
        "form_fields": [
            {
                "selector": "#email",
                "type": "email",
                "name": "email",
                "label": None,
                "required": True,
                "value": None,
            }
        ],
    }
    browser._page.query_selector_all.assert_awaited_once_with("input, textarea, select")
    browser._page.content.assert_awaited_once()
    agent.client.models.generate_content.assert_not_called()

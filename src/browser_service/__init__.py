"""Browser Service - Separate FastAPI service for browser automation.

This service provides a unified API for controlling browsers via:
- Playwright (cloud/headless mode)
- Chrome DevTools via MCP (local/assisted mode)
"""

from src.browser_service.models import (
    BrowserAction,
    BrowserMode,
    BrowserSession,
    ClickRequest,
    DOMResponse,
    EvaluateRequest,
    EvaluateResponse,
    FillRequest,
    NavigateRequest,
    ScreenshotResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionStatus,
)

__all__ = [
    "BrowserAction",
    "BrowserMode",
    "BrowserSession",
    "ClickRequest",
    "DOMResponse",
    "EvaluateRequest",
    "EvaluateResponse",
    "FillRequest",
    "NavigateRequest",
    "ScreenshotResponse",
    "SessionCreateRequest",
    "SessionCreateResponse",
    "SessionStatus",
]

"""
Browser Service for Job Hunter - Standalone Leapcell Deployment

A lightweight browser automation service using Playwright.
Provides HTTP API for browser control operations.
"""

import base64
import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Models
# =============================================================================


class SessionCreateRequest(BaseModel):
    """Request to create a browser session."""
    headless: bool = True
    viewport_width: int = 1280
    viewport_height: int = 720
    timeout: int = 30000
    slow_mo: int = 0
    user_agent: str | None = None


class SessionCreateResponse(BaseModel):
    """Response after creating a session."""
    session_id: str
    status: str = "active"
    mode: str = "playwright"
    websocket_url: str = ""  # Not used in standalone mode
    created_at: datetime


class NavigateRequest(BaseModel):
    """Request to navigate to a URL."""
    url: str
    wait_until: str = "load"  # load, domcontentloaded, networkidle


class NavigateResponse(BaseModel):
    """Response after navigation."""
    success: bool
    action: str = "navigate"
    duration_ms: int = 0
    url: str | None = None
    page_title: str | None = None
    error: str | None = None


class FillRequest(BaseModel):
    """Request to fill a form field."""
    selector: str
    value: str


class ClickRequest(BaseModel):
    """Request to click an element."""
    selector: str


class ScreenshotResponse(BaseModel):
    """Response with screenshot data."""
    success: bool
    screenshot_base64: str | None = None
    error: str | None = None


class EvaluateRequest(BaseModel):
    """Request to evaluate JavaScript."""
    script: str
    args: list | None = None


class EvaluateResponse(BaseModel):
    """Response from JavaScript evaluation."""
    success: bool
    action: str = "evaluate"
    duration_ms: int = 0
    result: Any = None
    error: str | None = None


class FormField(BaseModel):
    """Detected form field from DOM."""
    selector: str
    field_id: str | None = None
    field_name: str | None = None
    field_type: str  # text, email, tel, select, textarea, file, checkbox, radio, hidden
    tag_name: str = "input"  # input, select, textarea
    label: str | None = None
    placeholder: str | None = None
    required: bool = False
    current_value: str | None = None
    options: list[str] | None = None  # For select elements
    is_visible: bool = True
    is_enabled: bool = True

    # Compatibility aliases
    @property
    def name(self) -> str | None:
        return self.field_name

    @property
    def id(self) -> str | None:
        return self.field_id

    @property
    def type(self) -> str:
        return self.field_type


class DOMResponse(BaseModel):
    """Response with DOM information."""
    success: bool
    page_url: str = ""
    page_title: str = ""
    html_snippet: str | None = None
    form_fields: list[FormField] = Field(default_factory=list)
    error: str | None = None


# =============================================================================
# Browser Session Manager
# =============================================================================


class BrowserSession:
    """Manages a single browser session."""

    def __init__(self, session_id: str, config: SessionCreateRequest):
        self.session_id = session_id
        self.config = config
        self.created_at = datetime.utcnow()
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def initialize(self) -> None:
        """Initialize the browser."""
        logger.info(f"Initializing session {self.session_id} (headless={self.config.headless})")

        self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo,
        )

        viewport = {"width": self.config.viewport_width, "height": self.config.viewport_height}
        self._context = await self._browser.new_context(
            viewport=viewport,
            user_agent=self.config.user_agent,
        )
        self._context.set_default_timeout(self.config.timeout)

        self._page = await self._context.new_page()
        logger.info(f"Session {self.session_id} initialized")

    async def close(self) -> None:
        """Close the browser session."""
        logger.info(f"Closing session {self.session_id}")

        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Session not initialized")
        return self._page

    async def navigate(self, url: str, wait_until: str = "load") -> NavigateResponse:
        """Navigate to a URL."""
        import time
        start = time.time()
        try:
            await self.page.goto(url, wait_until=wait_until)
            duration_ms = int((time.time() - start) * 1000)
            return NavigateResponse(
                success=True,
                duration_ms=duration_ms,
                url=self.page.url,
                page_title=await self.page.title(),
            )
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            return NavigateResponse(success=False, duration_ms=duration_ms, error=str(e))

    async def fill(self, selector: str, value: str) -> dict:
        """Fill a form field."""
        try:
            await self.page.fill(selector, value)
            return {"success": True, "selector": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def click(self, selector: str) -> dict:
        """Click an element."""
        try:
            await self.page.click(selector)
            return {"success": True, "selector": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def screenshot(self, full_page: bool = False) -> ScreenshotResponse:
        """Take a screenshot."""
        try:
            screenshot_bytes = await self.page.screenshot(full_page=full_page)
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            return ScreenshotResponse(success=True, screenshot_base64=screenshot_base64)
        except Exception as e:
            return ScreenshotResponse(success=False, error=str(e))

    async def get_dom(self, selector: str | None = None, form_fields_only: bool = False) -> DOMResponse:
        """Get DOM content and form fields."""
        try:
            page_url = self.page.url
            page_title = await self.page.title()

            html_snippet = None
            if not form_fields_only:
                if selector:
                    element = await self.page.query_selector(selector)
                    html_snippet = await element.inner_html() if element else None
                else:
                    html_snippet = await self.page.content()
                if html_snippet:
                    html_snippet = html_snippet[:100000]

            # Extract form fields
            form_fields: list[FormField] = []
            inputs = await self.page.query_selector_all("input, textarea, select")
            for inp in inputs[:50]:  # Limit to 50 fields
                tag_name = await inp.evaluate("el => el.tagName.toLowerCase()")
                field_type = await inp.get_attribute("type") or ("textarea" if tag_name == "textarea" else "text")
                field_name = await inp.get_attribute("name") or None
                field_id = await inp.get_attribute("id") or None
                placeholder = await inp.get_attribute("placeholder") or None
                required = await inp.get_attribute("required") is not None

                # Build selector
                if field_id:
                    field_selector = f"#{field_id}"
                elif field_name:
                    field_selector = f"[name='{field_name}']"
                else:
                    continue  # Skip fields without id or name

                form_fields.append(FormField(
                    selector=field_selector,
                    field_id=field_id,
                    field_name=field_name,
                    field_type=field_type,
                    tag_name=tag_name,
                    placeholder=placeholder,
                    required=required,
                ))

            return DOMResponse(
                success=True,
                page_url=page_url,
                page_title=page_title,
                html_snippet=html_snippet,
                form_fields=form_fields,
            )
        except Exception as e:
            return DOMResponse(success=False, error=str(e))


# Session storage
sessions: dict[str, BrowserSession] = {}


# =============================================================================
# FastAPI Application
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    logger.info("Starting Browser Service...")
    yield
    # Cleanup all sessions on shutdown
    logger.info("Shutting down Browser Service...")
    for session in list(sessions.values()):
        await session.close()
    sessions.clear()


app = FastAPI(
    title="Job Hunter Browser Service",
    description="Browser automation service using Playwright",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Endpoints
# =============================================================================


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "browser-service",
        "active_sessions": len(sessions),
    }


@app.post("/sessions", response_model=SessionCreateResponse)
async def create_session(request: SessionCreateRequest) -> SessionCreateResponse:
    """Create a new browser session."""
    session_id = str(uuid.uuid4())
    session = BrowserSession(session_id, request)

    try:
        await session.initialize()
        sessions[session_id] = session
        return SessionCreateResponse(
            session_id=session_id,
            status="active",
            created_at=session.created_at,
        )
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions")
async def list_sessions() -> list[dict]:
    """List all active sessions."""
    return [
        {
            "session_id": s.session_id,
            "created_at": s.created_at.isoformat(),
            "url": s.page.url if s._page else None,
        }
        for s in sessions.values()
    ]


@app.delete("/sessions/{session_id}")
async def close_session(session_id: str) -> dict:
    """Close a browser session."""
    session = sessions.pop(session_id, None)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await session.close()
    return {"status": "closed", "session_id": session_id}


@app.post("/sessions/{session_id}/navigate", response_model=NavigateResponse)
async def navigate(session_id: str, request: NavigateRequest) -> NavigateResponse:
    """Navigate to a URL."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return await session.navigate(request.url, request.wait_until)


@app.post("/sessions/{session_id}/fill")
async def fill_field(session_id: str, request: FillRequest) -> dict:
    """Fill a form field."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return await session.fill(request.selector, request.value)


@app.post("/sessions/{session_id}/click")
async def click_element(session_id: str, request: ClickRequest) -> dict:
    """Click an element."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return await session.click(request.selector)


@app.post("/sessions/{session_id}/screenshot", response_model=ScreenshotResponse)
async def take_screenshot(session_id: str, full_page: bool = False) -> ScreenshotResponse:
    """Take a screenshot."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return await session.screenshot(full_page)


@app.get("/sessions/{session_id}/dom", response_model=DOMResponse)
async def get_dom(
    session_id: str,
    selector: str | None = None,
    form_fields_only: bool = False,
) -> DOMResponse:
    """Get DOM content and form fields."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return await session.get_dom(selector, form_fields_only)


@app.get("/sessions/{session_id}/content")
async def get_page_content(session_id: str) -> dict:
    """Get raw page HTML content."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    content = await session.page.content()
    return {"content": content}


@app.post("/sessions/{session_id}/evaluate", response_model=EvaluateResponse)
async def evaluate_script(session_id: str, request: EvaluateRequest) -> EvaluateResponse:
    """Execute JavaScript in the page context."""
    import time

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    start = time.time()
    try:
        result = await session.page.evaluate(request.script, request.args)
        duration_ms = int((time.time() - start) * 1000)
        return EvaluateResponse(success=True, duration_ms=duration_ms, result=result)
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        logger.error(f"Evaluate error: {e}")
        return EvaluateResponse(success=False, duration_ms=duration_ms, error=str(e))


@app.get("/sessions/{session_id}/url")
async def get_current_url(session_id: str) -> dict:
    """Get current page URL."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "url": session.page.url,
        "title": await session.page.title(),
    }


# =============================================================================
# CLI Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

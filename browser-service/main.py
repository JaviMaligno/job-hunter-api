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
    created_at: datetime


class NavigateRequest(BaseModel):
    """Request to navigate to a URL."""
    url: str
    wait_until: str = "load"  # load, domcontentloaded, networkidle


class NavigateResponse(BaseModel):
    """Response after navigation."""
    success: bool
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


class DOMResponse(BaseModel):
    """Response with DOM information."""
    success: bool
    html: str | None = None
    form_fields: list[dict] = Field(default_factory=list)
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
        try:
            await self.page.goto(url, wait_until=wait_until)
            return NavigateResponse(
                success=True,
                url=self.page.url,
                page_title=await self.page.title(),
            )
        except Exception as e:
            return NavigateResponse(success=False, error=str(e))

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

    async def get_dom(self, selector: str | None = None) -> DOMResponse:
        """Get DOM content."""
        try:
            if selector:
                element = await self.page.query_selector(selector)
                html = await element.inner_html() if element else None
            else:
                html = await self.page.content()

            # Extract form fields
            form_fields = []
            inputs = await self.page.query_selector_all("input, textarea, select")
            for inp in inputs[:50]:  # Limit to 50 fields
                field_type = await inp.get_attribute("type") or "text"
                field_name = await inp.get_attribute("name") or ""
                field_id = await inp.get_attribute("id") or ""
                placeholder = await inp.get_attribute("placeholder") or ""
                form_fields.append({
                    "type": field_type,
                    "name": field_name,
                    "id": field_id,
                    "placeholder": placeholder,
                    "selector": f"#{field_id}" if field_id else f"[name='{field_name}']" if field_name else None,
                })

            return DOMResponse(success=True, html=html[:100000] if html else None, form_fields=form_fields)
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
async def get_dom(session_id: str, selector: str | None = None) -> DOMResponse:
    """Get DOM content and form fields."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return await session.get_dom(selector)


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

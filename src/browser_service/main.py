"""Browser Service - FastAPI application for browser automation.

This service runs on port 8001 and provides HTTP/WebSocket APIs
for controlling browser instances via Playwright or Chrome DevTools MCP.

Run with:
    uvicorn src.browser_service.main:app --port 8001
"""

import logging
from contextlib import asynccontextmanager
from typing import Annotated, AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.browser_service.models import (
    BrowserSession,
    ClickRequest,
    DOMResponse,
    EvaluateRequest,
    EvaluateResponse,
    FillRequest,
    NavigateRequest,
    NavigateResponse,
    ScreenshotResponse,
    SelectRequest,
    SessionCreateRequest,
    SessionCreateResponse,
    UploadRequest,
)
from src.browser_service.session_manager import (
    SessionManager,
    get_session_manager,
    init_session_manager,
    shutdown_session_manager,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Startup
    logger.info("Starting Browser Service...")
    await init_session_manager()
    logger.info("Browser Service started on port 8001")
    yield
    # Shutdown
    logger.info("Shutting down Browser Service...")
    await shutdown_session_manager()
    logger.info("Browser Service stopped")


app = FastAPI(
    title="Job Hunter Browser Service",
    description="Browser automation service for job applications",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Dependencies
# ============================================================================


def get_manager() -> SessionManager:
    """Dependency to get session manager."""
    return get_session_manager()


ManagerDep = Annotated[SessionManager, Depends(get_manager)]


# ============================================================================
# Health Check
# ============================================================================


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    manager = get_session_manager()
    return {
        "status": "healthy",
        "service": "browser-service",
        "active_sessions": len(manager.list_sessions()),
    }


# ============================================================================
# Session Endpoints
# ============================================================================


@app.post("/sessions", response_model=SessionCreateResponse)
async def create_session(
    request: SessionCreateRequest,
    manager: ManagerDep,
) -> SessionCreateResponse:
    """Create a new browser session.

    Initializes a browser instance with the specified configuration.
    Returns session ID and WebSocket URL for real-time events.
    """
    try:
        return await manager.create_session(request)
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions", response_model=list[BrowserSession])
async def list_sessions(manager: ManagerDep) -> list[BrowserSession]:
    """List all active browser sessions."""
    return manager.list_sessions()


@app.get("/sessions/{session_id}", response_model=BrowserSession)
async def get_session(session_id: str, manager: ManagerDep) -> BrowserSession:
    """Get session details by ID."""
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.delete("/sessions/{session_id}")
async def close_session(session_id: str, manager: ManagerDep) -> dict:
    """Close a browser session."""
    success = await manager.close_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "closed", "session_id": session_id}


# ============================================================================
# Browser Action Endpoints
# ============================================================================


@app.post("/sessions/{session_id}/navigate", response_model=NavigateResponse)
async def navigate(
    session_id: str,
    request: NavigateRequest,
    manager: ManagerDep,
) -> NavigateResponse:
    """Navigate to a URL."""
    adapter = manager.get_adapter(session_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Session not found")

    response = await adapter.navigate(request)
    manager.update_session_activity(session_id)

    if response.success:
        manager.update_session_url(session_id, response.url, response.page_title)

    return response


@app.post("/sessions/{session_id}/fill")
async def fill_field(
    session_id: str,
    request: FillRequest,
    manager: ManagerDep,
) -> dict:
    """Fill a form field."""
    adapter = manager.get_adapter(session_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Session not found")

    response = await adapter.fill(request)
    manager.update_session_activity(session_id)

    return response.model_dump()


@app.post("/sessions/{session_id}/click")
async def click_element(
    session_id: str,
    request: ClickRequest,
    manager: ManagerDep,
) -> dict:
    """Click an element."""
    adapter = manager.get_adapter(session_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Session not found")

    response = await adapter.click(request)
    manager.update_session_activity(session_id)

    return response.model_dump()


@app.post("/sessions/{session_id}/select")
async def select_option(
    session_id: str,
    request: SelectRequest,
    manager: ManagerDep,
) -> dict:
    """Select option from dropdown."""
    adapter = manager.get_adapter(session_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Session not found")

    response = await adapter.select(request)
    manager.update_session_activity(session_id)

    return response


@app.post("/sessions/{session_id}/upload")
async def upload_file(
    session_id: str,
    request: UploadRequest,
    manager: ManagerDep,
) -> dict:
    """Upload a file."""
    adapter = manager.get_adapter(session_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Session not found")

    response = await adapter.upload(request)
    manager.update_session_activity(session_id)

    return response


@app.post("/sessions/{session_id}/screenshot", response_model=ScreenshotResponse)
async def take_screenshot(
    session_id: str,
    manager: ManagerDep,
    full_page: bool = False,
    path: str | None = None,
) -> ScreenshotResponse:
    """Take a screenshot of the current page."""
    adapter = manager.get_adapter(session_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Session not found")

    response = await adapter.screenshot(full_page=full_page, path=path)
    manager.update_session_activity(session_id)

    return response


@app.post("/sessions/{session_id}/evaluate", response_model=EvaluateResponse)
async def evaluate_script(
    session_id: str,
    request: EvaluateRequest,
    manager: ManagerDep,
) -> EvaluateResponse:
    """Execute JavaScript in the page context."""
    adapter = manager.get_adapter(session_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Session not found")

    response = await adapter.evaluate(request)
    manager.update_session_activity(session_id)

    return response


@app.get("/sessions/{session_id}/dom", response_model=DOMResponse)
async def get_dom(
    session_id: str,
    manager: ManagerDep,
    selector: str | None = None,
    form_fields_only: bool = False,
) -> DOMResponse:
    """Get DOM information and form fields."""
    adapter = manager.get_adapter(session_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Session not found")

    response = await adapter.get_dom(selector=selector, form_fields_only=form_fields_only)
    manager.update_session_activity(session_id)

    return response


@app.get("/sessions/{session_id}/url")
async def get_current_url(session_id: str, manager: ManagerDep) -> dict:
    """Get current page URL."""
    adapter = manager.get_adapter(session_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Session not found")

    url = await adapter.get_current_url()
    title = await adapter.get_page_title()
    manager.update_session_activity(session_id)

    return {"url": url, "title": title}


@app.get("/sessions/{session_id}/content")
async def get_page_content(session_id: str, manager: ManagerDep) -> dict:
    """Get current page HTML content."""
    adapter = manager.get_adapter(session_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Session not found")

    content = await adapter.get_page_content()
    manager.update_session_activity(session_id)

    return {"content": content[:50000]}  # Limit to 50KB


# ============================================================================
# WebSocket Endpoint
# ============================================================================


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for real-time session events.

    Clients can connect to receive updates about:
    - Page navigation events
    - Form field interactions
    - Blocker detection (CAPTCHA, login required)
    - Errors and status changes
    """
    manager = get_session_manager()
    session = manager.get_session(session_id)

    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()
    logger.info(f"WebSocket connected for session {session_id}")

    try:
        while True:
            # Keep connection alive and handle client messages
            data = await websocket.receive_text()

            # Echo back for now - can be extended for bidirectional communication
            await websocket.send_json({
                "type": "ack",
                "session_id": session_id,
                "message": data,
            })
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")


# ============================================================================
# CLI Entry Point
# ============================================================================


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.browser_service.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )

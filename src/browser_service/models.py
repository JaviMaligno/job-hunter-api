"""Pydantic models for Browser Service API."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BrowserMode(str, Enum):
    """Browser adapter mode."""

    PLAYWRIGHT = "playwright"
    CHROME_DEVTOOLS = "chrome-devtools"


class SessionStatus(str, Enum):
    """Browser session status."""

    CREATING = "creating"
    ACTIVE = "active"
    NAVIGATING = "navigating"
    IDLE = "idle"
    CLOSED = "closed"
    ERROR = "error"


class BrowserAction(str, Enum):
    """Browser action types for logging/events."""

    NAVIGATE = "navigate"
    FILL = "fill"
    CLICK = "click"
    SCREENSHOT = "screenshot"
    EVALUATE = "evaluate"
    GET_DOM = "get_dom"
    WAIT = "wait"
    SELECT = "select"
    UPLOAD = "upload"


# ============================================================================
# Session Models
# ============================================================================


class SessionCreateRequest(BaseModel):
    """Request to create a new browser session."""

    mode: BrowserMode = BrowserMode.PLAYWRIGHT
    headless: bool = True
    slow_mo: int = Field(default=0, ge=0, le=1000, description="Slow motion delay in ms")
    viewport_width: int = Field(default=1280, ge=800, le=3840)
    viewport_height: int = Field(default=720, ge=600, le=2160)
    user_agent: str | None = None
    timeout: int = Field(default=30000, ge=5000, le=120000, description="Default timeout in ms")


class SessionCreateResponse(BaseModel):
    """Response after creating a browser session."""

    session_id: str
    status: SessionStatus
    mode: BrowserMode
    websocket_url: str
    created_at: datetime


class BrowserSession(BaseModel):
    """Browser session state."""

    session_id: str
    status: SessionStatus
    mode: BrowserMode
    current_url: str | None = None
    page_title: str | None = None
    created_at: datetime
    last_action_at: datetime | None = None
    action_count: int = 0


# ============================================================================
# Action Request Models
# ============================================================================


class NavigateRequest(BaseModel):
    """Request to navigate to a URL."""

    url: str
    wait_until: str = Field(
        default="domcontentloaded",
        description="When to consider navigation done: domcontentloaded, load, networkidle",
    )
    timeout: int | None = Field(default=None, description="Override default timeout")


class FillRequest(BaseModel):
    """Request to fill a form field."""

    selector: str = Field(description="CSS selector for the input element")
    value: str = Field(description="Value to fill")
    clear_first: bool = Field(default=True, description="Clear existing value first")
    force: bool = Field(default=False, description="Force fill even if element not visible")
    timeout: int | None = None


class ClickRequest(BaseModel):
    """Request to click an element."""

    selector: str = Field(description="CSS selector for the element")
    button: str = Field(default="left", description="Mouse button: left, right, middle")
    click_count: int = Field(default=1, ge=1, le=3, description="Number of clicks")
    delay: int = Field(default=0, ge=0, le=1000, description="Delay between clicks in ms")
    force: bool = Field(default=False, description="Force click even if element not visible")
    timeout: int | None = None


class SelectRequest(BaseModel):
    """Request to select option(s) from a dropdown."""

    selector: str = Field(description="CSS selector for the select element")
    value: str | None = Field(default=None, description="Option value to select")
    label: str | None = Field(default=None, description="Option label to select")
    index: int | None = Field(default=None, description="Option index to select")
    timeout: int | None = None


class UploadRequest(BaseModel):
    """Request to upload a file."""

    selector: str = Field(description="CSS selector for the file input")
    file_path: str = Field(description="Path to the file to upload")
    timeout: int | None = None


class EvaluateRequest(BaseModel):
    """Request to evaluate JavaScript in the page context."""

    script: str = Field(description="JavaScript code to execute")
    args: list[Any] | None = Field(default=None, description="Arguments to pass to the script")


class WaitRequest(BaseModel):
    """Request to wait for a condition."""

    selector: str | None = Field(default=None, description="Wait for element selector")
    state: str = Field(
        default="visible",
        description="Element state to wait for: visible, hidden, attached, detached",
    )
    timeout: int | None = None


class GetDOMRequest(BaseModel):
    """Request to get DOM information."""

    selector: str | None = Field(default=None, description="Optional root selector")
    include_styles: bool = Field(default=False, description="Include computed styles")
    form_fields_only: bool = Field(default=False, description="Only return form elements")


# ============================================================================
# Response Models
# ============================================================================


class ActionResponse(BaseModel):
    """Generic response for browser actions."""

    success: bool
    action: BrowserAction
    duration_ms: int
    error: str | None = None


class NavigateResponse(ActionResponse):
    """Response from navigation."""

    action: BrowserAction = BrowserAction.NAVIGATE
    url: str
    page_title: str | None = None


class FillResponse(ActionResponse):
    """Response from filling a field."""

    action: BrowserAction = BrowserAction.FILL
    selector: str
    value_filled: str


class ClickResponse(ActionResponse):
    """Response from clicking."""

    action: BrowserAction = BrowserAction.CLICK
    selector: str


class ScreenshotResponse(BaseModel):
    """Response with screenshot data."""

    success: bool
    screenshot_base64: str | None = None
    screenshot_path: str | None = None
    width: int | None = None
    height: int | None = None
    error: str | None = None


class EvaluateResponse(ActionResponse):
    """Response from JavaScript evaluation."""

    action: BrowserAction = BrowserAction.EVALUATE
    result: Any = None


class FormField(BaseModel):
    """Detected form field from DOM."""

    selector: str
    field_id: str | None = None
    field_name: str | None = None
    field_type: str  # text, email, tel, select, textarea, file, checkbox, radio, hidden
    tag_name: str  # input, select, textarea
    label: str | None = None
    placeholder: str | None = None
    required: bool = False
    current_value: str | None = None
    options: list[str] | None = None  # For select elements
    is_visible: bool = True
    is_enabled: bool = True


class DOMResponse(BaseModel):
    """Response with DOM information."""

    success: bool
    page_url: str
    page_title: str
    form_fields: list[FormField] = []
    html_snippet: str | None = None
    error: str | None = None


# ============================================================================
# WebSocket Event Models
# ============================================================================


class WebSocketEvent(BaseModel):
    """Base WebSocket event."""

    event_type: str
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PageLoadedEvent(WebSocketEvent):
    """Event when page has loaded."""

    event_type: str = "page_loaded"
    url: str
    title: str


class ActionCompletedEvent(WebSocketEvent):
    """Event when an action completes."""

    event_type: str = "action_completed"
    action: BrowserAction
    success: bool
    duration_ms: int
    error: str | None = None


class BlockerDetectedEvent(WebSocketEvent):
    """Event when a blocker is detected."""

    event_type: str = "blocker_detected"
    blocker_type: str  # captcha, login_required, etc.
    blocker_subtype: str | None = None  # cloudflare, hcaptcha, etc.
    message: str


class ErrorEvent(WebSocketEvent):
    """Event when an error occurs."""

    event_type: str = "error"
    error_type: str
    message: str
    recoverable: bool = True

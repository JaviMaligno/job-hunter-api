"""HTTP client for Browser Service communication."""

import logging
from typing import Any

import httpx

from src.browser_service.models import (
    BrowserMode,
    BrowserSession,
    ClickRequest,
    DOMResponse,
    EvaluateRequest,
    EvaluateResponse,
    FillRequest,
    FormField,
    NavigateRequest,
    NavigateResponse,
    ScreenshotResponse,
    SelectRequest,
    SessionCreateRequest,
    SessionCreateResponse,
    UploadRequest,
)
from src.config import settings

logger = logging.getLogger(__name__)


class BrowserServiceClient:
    """HTTP client for interacting with the Browser Service.

    Provides a high-level interface for browser automation operations.
    All methods are async and communicate with the Browser Service via HTTP.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: Browser Service URL (defaults to settings)
            timeout: Request timeout in seconds (defaults to settings)
        """
        self.base_url = base_url or settings.browser_service_url
        self.timeout = timeout or (settings.browser_service_timeout / 1000)  # Convert ms to s
        self._client: httpx.AsyncClient | None = None
        self._session_id: str | None = None

    async def __aenter__(self) -> "BrowserServiceClient":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._session_id:
            try:
                await self.close_session()
            except Exception as e:
                logger.warning(f"Failed to close session on exit: {e}")
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        """Get HTTP client, raising if not initialized."""
        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return self._client

    @property
    def session_id(self) -> str:
        """Get current session ID, raising if not created."""
        if self._session_id is None:
            raise RuntimeError("No active session. Call create_session() first.")
        return self._session_id

    # =========================================================================
    # Session Management
    # =========================================================================

    async def create_session(
        self,
        mode: BrowserMode = BrowserMode.PLAYWRIGHT,
        headless: bool = True,
        slow_mo: int = 0,
        viewport_width: int = 1280,
        viewport_height: int = 720,
        devtools_url: str | None = None,
    ) -> SessionCreateResponse:
        """Create a new browser session.

        Args:
            mode: Browser mode (playwright or chrome-devtools)
            headless: Run browser in headless mode
            slow_mo: Slow motion delay in ms
            viewport_width: Browser viewport width
            viewport_height: Browser viewport height
            devtools_url: Chrome DevTools URL (required for chrome-devtools mode)

        Returns:
            SessionCreateResponse with session ID and WebSocket URL
        """
        request = SessionCreateRequest(
            mode=mode,
            headless=headless,
            slow_mo=slow_mo,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            devtools_url=devtools_url,
        )

        response = await self.client.post("/sessions", json=request.model_dump())
        response.raise_for_status()

        result = SessionCreateResponse.model_validate(response.json())
        self._session_id = result.session_id

        logger.info(f"Created browser session: {self._session_id}")
        return result

    async def close_session(self) -> None:
        """Close the current browser session."""
        if not self._session_id:
            return

        response = await self.client.delete(f"/sessions/{self._session_id}")
        response.raise_for_status()

        logger.info(f"Closed browser session: {self._session_id}")
        self._session_id = None

    async def close_session_by_id(self, session_id: str, timeout: float = 10.0) -> None:
        """Close a browser session by its ID.

        This is useful for closing sessions that were created elsewhere.

        Args:
            session_id: The ID of the session to close
            timeout: Timeout in seconds (default 10s, MCP close can be slow)
        """
        import httpx
        response = await self.client.delete(
            f"/sessions/{session_id}",
            timeout=httpx.Timeout(timeout)
        )
        response.raise_for_status()
        logger.info(f"Closed browser session: {session_id}")

    async def get_session(self) -> BrowserSession:
        """Get current session details."""
        response = await self.client.get(f"/sessions/{self.session_id}")
        response.raise_for_status()
        return BrowserSession.model_validate(response.json())

    # =========================================================================
    # Navigation
    # =========================================================================

    async def navigate(
        self,
        url: str,
        wait_until: str = "networkidle",
        timeout: int | None = None,
    ) -> NavigateResponse:
        """Navigate to a URL.

        Args:
            url: URL to navigate to
            wait_until: When to consider navigation done
            timeout: Optional timeout override in ms

        Returns:
            NavigateResponse with success status and page info
        """
        request = NavigateRequest(url=url, wait_until=wait_until, timeout=timeout)

        # Use extended timeout for navigation (can take longer than other operations)
        response = await self.client.post(
            f"/sessions/{self.session_id}/navigate",
            json=request.model_dump(),
            timeout=60.0,  # 60 second timeout for navigation
        )
        response.raise_for_status()

        return NavigateResponse.model_validate(response.json())

    async def get_current_url(self) -> str:
        """Get current page URL."""
        response = await self.client.get(f"/sessions/{self.session_id}/url")
        response.raise_for_status()
        return response.json()["url"]

    async def get_page_title(self) -> str:
        """Get current page title."""
        response = await self.client.get(f"/sessions/{self.session_id}/url")
        response.raise_for_status()
        return response.json()["title"]

    async def get_page_content(self) -> str:
        """Get current page HTML content."""
        response = await self.client.get(f"/sessions/{self.session_id}/content")
        response.raise_for_status()
        return response.json()["content"]

    # =========================================================================
    # Form Interactions
    # =========================================================================

    async def fill(
        self,
        selector: str,
        value: str,
        clear_first: bool = True,
        force: bool = False,
        timeout: int | None = None,
    ) -> dict:
        """Fill a form field.

        Args:
            selector: CSS selector for the input element
            value: Value to fill
            clear_first: Clear existing value first
            force: Force fill even if not visible
            timeout: Optional timeout override

        Returns:
            Response dict with success status
        """
        request = FillRequest(
            selector=selector,
            value=value,
            clear_first=clear_first,
            force=force,
            timeout=timeout,
        )

        response = await self.client.post(
            f"/sessions/{self.session_id}/fill",
            json=request.model_dump(),
        )
        response.raise_for_status()

        return response.json()

    async def click(
        self,
        selector: str,
        button: str = "left",
        click_count: int = 1,
        force: bool = False,
        timeout: int | None = None,
    ) -> dict:
        """Click an element.

        Args:
            selector: CSS selector for the element, or special button:text-match("text") selector
            button: Mouse button (left, right, middle)
            click_count: Number of clicks
            force: Force click even if not visible
            timeout: Optional timeout override

        Returns:
            Response dict with success status
        """
        # Handle special text-match selector for buttons
        if selector.startswith('button:text-match("'):
            text = selector[19:-2]  # Extract text from button:text-match("...")
            return await self.click_by_text(text)

        request = ClickRequest(
            selector=selector,
            button=button,
            click_count=click_count,
            force=force,
            timeout=timeout,
        )

        response = await self.client.post(
            f"/sessions/{self.session_id}/click",
            json=request.model_dump(),
        )
        response.raise_for_status()

        return response.json()

    async def click_by_text(self, text: str) -> dict:
        """Click a button by its text content.

        Args:
            text: Button text to find and click

        Returns:
            Response dict with success status
        """
        result = await self.evaluate(f"""
            (() => {{
                const searchText = "{text}";
                const buttons = document.querySelectorAll('button, input[type="button"], input[type="submit"], a.btn, a.button');
                for (const btn of buttons) {{
                    const btnText = btn.textContent || btn.value || '';
                    if (btnText.trim() === searchText || btnText.trim().toLowerCase().includes(searchText.toLowerCase())) {{
                        if (btn.offsetParent !== null) {{
                            btn.click();
                            return {{ success: true, clicked: btnText.trim() }};
                        }}
                    }}
                }}
                return {{ success: false, error: 'Button not found: ' + searchText }};
            }})()
        """)
        return result.result if result else {"success": False, "error": "Evaluation failed"}

    async def select(
        self,
        selector: str,
        value: str | None = None,
        label: str | None = None,
        index: int | None = None,
        timeout: int | None = None,
    ) -> dict:
        """Select option from dropdown.

        Args:
            selector: CSS selector for select element
            value: Option value to select
            label: Option label to select
            index: Option index to select
            timeout: Optional timeout override

        Returns:
            Response dict with success status
        """
        request = SelectRequest(
            selector=selector,
            value=value,
            label=label,
            index=index,
            timeout=timeout,
        )

        response = await self.client.post(
            f"/sessions/{self.session_id}/select",
            json=request.model_dump(),
        )
        response.raise_for_status()

        return response.json()

    async def upload(
        self,
        selector: str,
        file_path: str,
        timeout: int | None = None,
    ) -> dict:
        """Upload a file.

        Args:
            selector: CSS selector for file input
            file_path: Path to file to upload
            timeout: Optional timeout override

        Returns:
            Response dict with success status
        """
        request = UploadRequest(
            selector=selector,
            file_path=file_path,
            timeout=timeout,
        )

        response = await self.client.post(
            f"/sessions/{self.session_id}/upload",
            json=request.model_dump(),
        )
        response.raise_for_status()

        return response.json()

    # =========================================================================
    # DOM & Screenshots
    # =========================================================================

    async def get_dom(
        self,
        selector: str | None = None,
        form_fields_only: bool = False,
    ) -> DOMResponse:
        """Get DOM information and form fields.

        Args:
            selector: Optional root selector to scope query
            form_fields_only: Only return form field elements

        Returns:
            DOMResponse with page info and form fields
        """
        params = {}
        if selector:
            params["selector"] = selector
        if form_fields_only:
            params["form_fields_only"] = "true"

        response = await self.client.get(
            f"/sessions/{self.session_id}/dom",
            params=params,
        )
        response.raise_for_status()

        return DOMResponse.model_validate(response.json())

    async def get_form_fields(self) -> list[FormField]:
        """Get all form fields on the page.

        Returns:
            List of FormField objects
        """
        dom = await self.get_dom(form_fields_only=True)
        return dom.form_fields

    async def screenshot(
        self,
        full_page: bool = False,
        path: str | None = None,
    ) -> ScreenshotResponse:
        """Take a screenshot.

        Args:
            full_page: Capture full scrollable page
            path: Optional path to save screenshot

        Returns:
            ScreenshotResponse with base64 data or path
        """
        params = {}
        if full_page:
            params["full_page"] = "true"
        if path:
            params["path"] = path

        response = await self.client.post(
            f"/sessions/{self.session_id}/screenshot",
            params=params,
        )
        response.raise_for_status()

        return ScreenshotResponse.model_validate(response.json())

    # =========================================================================
    # JavaScript Evaluation
    # =========================================================================

    async def evaluate(
        self,
        script: str,
        args: list[Any] | None = None,
    ) -> EvaluateResponse:
        """Execute JavaScript in the page context.

        Args:
            script: JavaScript code to execute
            args: Optional arguments to pass

        Returns:
            EvaluateResponse with the result
        """
        request = EvaluateRequest(script=script, args=args)

        response = await self.client.post(
            f"/sessions/{self.session_id}/evaluate",
            json=request.model_dump(),
        )
        response.raise_for_status()

        return EvaluateResponse.model_validate(response.json())

    async def is_element_visible(self, selector: str) -> bool:
        """Check if element is visible.

        Args:
            selector: CSS selector

        Returns:
            True if element is visible
        """
        result = await self.evaluate(f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                const style = window.getComputedStyle(el);
                return style.display !== 'none' &&
                       style.visibility !== 'hidden' &&
                       style.opacity !== '0' &&
                       el.offsetParent !== null;
            }})()
        """)
        return bool(result.result) if result.success else False

    async def get_element_text(self, selector: str) -> str | None:
        """Get text content of element.

        Args:
            selector: CSS selector

        Returns:
            Element text or None if not found
        """
        result = await self.evaluate(f"""
            (() => {{
                const el = document.querySelector('{selector}');
                return el ? el.textContent.trim() : null;
            }})()
        """)
        return result.result if result.success else None

    # =========================================================================
    # Health Check
    # =========================================================================

    async def health_check(self) -> dict:
        """Check Browser Service health.

        Returns:
            Health status dict
        """
        response = await self.client.get("/health")
        response.raise_for_status()
        return response.json()

    @classmethod
    async def is_service_available(cls, base_url: str | None = None) -> bool:
        """Check if Browser Service is available.

        Args:
            base_url: Optional URL override

        Returns:
            True if service is reachable and healthy
        """
        url = base_url or settings.browser_service_url
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{url}/health")
                return response.status_code == 200
        except Exception:
            return False

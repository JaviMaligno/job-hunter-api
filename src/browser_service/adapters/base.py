"""Base browser adapter protocol."""

from abc import ABC, abstractmethod
from typing import Any

from src.browser_service.models import (
    ClickRequest,
    ClickResponse,
    DOMResponse,
    EvaluateRequest,
    EvaluateResponse,
    FillRequest,
    FillResponse,
    NavigateRequest,
    NavigateResponse,
    ScreenshotResponse,
    SelectRequest,
    SessionCreateRequest,
    UploadRequest,
    WaitRequest,
)


class BrowserAdapter(ABC):
    """Abstract base class for browser automation adapters.

    Implementations:
    - PlaywrightAdapter: Uses Playwright for headless/cloud automation
    - ChromeDevToolsAdapter: Uses MCP Chrome DevTools for local automation
    """

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Return the adapter name for logging."""
        ...

    @abstractmethod
    async def initialize(self, config: SessionCreateRequest) -> None:
        """Initialize the browser instance.

        Args:
            config: Session configuration options
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the browser and cleanup resources."""
        ...

    @abstractmethod
    async def navigate(self, request: NavigateRequest) -> NavigateResponse:
        """Navigate to a URL.

        Args:
            request: Navigation request with URL and wait conditions

        Returns:
            NavigateResponse with success status and page info
        """
        ...

    @abstractmethod
    async def fill(self, request: FillRequest) -> FillResponse:
        """Fill a form field.

        Args:
            request: Fill request with selector and value

        Returns:
            FillResponse with success status
        """
        ...

    @abstractmethod
    async def click(self, request: ClickRequest) -> ClickResponse:
        """Click an element.

        Args:
            request: Click request with selector and options

        Returns:
            ClickResponse with success status
        """
        ...

    @abstractmethod
    async def select(self, request: SelectRequest) -> Any:
        """Select option(s) from a dropdown.

        Args:
            request: Select request with selector and value/label/index

        Returns:
            Response with selected values
        """
        ...

    @abstractmethod
    async def upload(self, request: UploadRequest) -> Any:
        """Upload a file to a file input.

        Args:
            request: Upload request with selector and file path

        Returns:
            Response with upload status
        """
        ...

    @abstractmethod
    async def screenshot(
        self, full_page: bool = False, path: str | None = None
    ) -> ScreenshotResponse:
        """Take a screenshot.

        Args:
            full_page: Whether to capture the full scrollable page
            path: Optional path to save the screenshot

        Returns:
            ScreenshotResponse with base64 data or path
        """
        ...

    @abstractmethod
    async def evaluate(self, request: EvaluateRequest) -> EvaluateResponse:
        """Execute JavaScript in the page context.

        Args:
            request: JavaScript code to execute

        Returns:
            EvaluateResponse with the result
        """
        ...

    @abstractmethod
    async def get_dom(
        self, selector: str | None = None, form_fields_only: bool = False
    ) -> DOMResponse:
        """Get DOM information.

        Args:
            selector: Optional root selector to scope the query
            form_fields_only: If True, only return form field elements

        Returns:
            DOMResponse with page info and form fields
        """
        ...

    @abstractmethod
    async def wait_for(self, request: WaitRequest) -> bool:
        """Wait for a condition.

        Args:
            request: Wait request with selector and state

        Returns:
            True if condition met, False if timeout
        """
        ...

    @abstractmethod
    async def get_current_url(self) -> str:
        """Get the current page URL."""
        ...

    @abstractmethod
    async def get_page_title(self) -> str:
        """Get the current page title."""
        ...

    @abstractmethod
    async def get_page_content(self) -> str:
        """Get the current page HTML content."""
        ...

    async def is_element_visible(self, selector: str) -> bool:
        """Check if an element is visible.

        Default implementation uses evaluate. Subclasses may override.
        """
        result = await self.evaluate(
            EvaluateRequest(
                script=f"""
                    const el = document.querySelector('{selector}');
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    return style.display !== 'none' &&
                           style.visibility !== 'hidden' &&
                           style.opacity !== '0' &&
                           el.offsetParent !== null;
                """
            )
        )
        return bool(result.result) if result.success else False

    async def get_element_text(self, selector: str) -> str | None:
        """Get text content of an element.

        Default implementation uses evaluate. Subclasses may override.
        """
        result = await self.evaluate(
            EvaluateRequest(
                script=f"""
                    const el = document.querySelector('{selector}');
                    return el ? el.textContent.trim() : null;
                """
            )
        )
        return result.result if result.success else None

    async def get_element_attribute(self, selector: str, attribute: str) -> str | None:
        """Get an attribute value of an element.

        Default implementation uses evaluate. Subclasses may override.
        """
        result = await self.evaluate(
            EvaluateRequest(
                script=f"""
                    const el = document.querySelector('{selector}');
                    return el ? el.getAttribute('{attribute}') : null;
                """
            )
        )
        return result.result if result.success else None

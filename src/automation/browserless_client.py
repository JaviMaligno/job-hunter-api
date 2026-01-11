"""Direct Browserless.io client using Playwright CDP connection.

Replaces the HTTP-based BrowserServiceClient by connecting directly
to Browserless.io cloud browsers, eliminating the need for a separate
browser service deployment.
"""

import base64
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from src.browser_service.models import (
    DOMResponse,
    EvaluateResponse,
    FormField,
    NavigateResponse,
    ScreenshotResponse,
    SessionCreateResponse,
)
from src.config import settings

logger = logging.getLogger(__name__)


class BrowserlessClient:
    """Direct client for Browserless.io using Playwright CDP.

    Provides the same interface as BrowserServiceClient but connects
    directly to Browserless.io without an intermediate HTTP service.
    """

    def __init__(
        self,
        browserless_token: str | None = None,
        browserless_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the client.

        Args:
            browserless_token: Browserless.io API token (defaults to settings)
            browserless_url: Browserless.io WebSocket URL (defaults to settings)
            timeout: Default timeout in seconds
        """
        self.browserless_token = browserless_token or settings.browserless_token
        self.browserless_url = browserless_url or settings.browserless_url
        self.timeout = timeout
        self._timeout_ms = int(timeout * 1000)

        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._session_id: str | None = None
        self._created_at: datetime | None = None

    async def __aenter__(self) -> "BrowserlessClient":
        """Async context manager entry - connects to Browserless.io."""
        if not self.browserless_token:
            raise RuntimeError("BROWSERLESS_TOKEN not configured")

        self._playwright = await async_playwright().start()

        endpoint = f"{self.browserless_url}?token={self.browserless_token}"
        logger.info(f"Connecting to Browserless.io at {self.browserless_url}...")

        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(endpoint)
            logger.info(f"Connected to Browserless.io (version: {self._browser.version})")
        except Exception as e:
            await self._playwright.stop()
            raise RuntimeError(f"Failed to connect to Browserless.io: {e}") from e

        # Create context and page
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
        )
        self._context.set_default_timeout(self._timeout_ms)

        self._page = await self._context.new_page()
        self._session_id = str(uuid.uuid4())
        self._created_at = datetime.utcnow()

        logger.info(f"Browser session ready: {self._session_id}")
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit - closes browser."""
        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
        finally:
            if self._playwright:
                await self._playwright.stop()
            self._session_id = None

    @property
    def page(self) -> Page:
        """Get current page, raising if not initialized."""
        if self._page is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return self._page

    @property
    def session_id(self) -> str:
        """Get current session ID."""
        if self._session_id is None:
            raise RuntimeError("No active session.")
        return self._session_id

    # =========================================================================
    # Session Management (compatibility with BrowserServiceClient)
    # =========================================================================

    async def create_session(self, **kwargs: Any) -> SessionCreateResponse:
        """No-op for compatibility - session created in __aenter__."""
        return SessionCreateResponse(
            session_id=self.session_id,
            status="active",
            mode="browserless",
            websocket_url="",
            created_at=self._created_at or datetime.utcnow(),
        )

    async def close_session(self) -> None:
        """No-op for compatibility - session closed in __aexit__."""
        pass

    async def health_check(self) -> dict:
        """Check connection health."""
        return {
            "status": "healthy" if self._browser else "disconnected",
            "service": "browserless-direct",
            "mode": "browserless",
            "session_id": self._session_id,
        }

    # =========================================================================
    # Navigation
    # =========================================================================

    async def navigate(
        self,
        url: str,
        wait_until: str = "networkidle",
        timeout: int | None = None,
    ) -> NavigateResponse:
        """Navigate to a URL."""
        start = time.time()
        try:
            await self.page.goto(
                url,
                wait_until=wait_until,  # type: ignore
                timeout=timeout or self._timeout_ms,
            )
            duration_ms = int((time.time() - start) * 1000)
            return NavigateResponse(
                success=True,
                action="navigate",
                duration_ms=duration_ms,
                url=self.page.url,
                page_title=await self.page.title(),
            )
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            # Always include url even on failure
            current_url = url
            try:
                current_url = self.page.url or url
            except Exception:
                pass
            return NavigateResponse(
                success=False,
                action="navigate",
                duration_ms=duration_ms,
                url=current_url,
                error=str(e),
            )

    async def get_current_url(self) -> str:
        """Get current page URL."""
        return self.page.url

    async def get_page_title(self) -> str:
        """Get current page title."""
        return await self.page.title()

    async def get_page_content(self) -> str:
        """Get current page HTML content."""
        return await self.page.content()

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
        """Fill a form field."""
        try:
            if clear_first:
                await self.page.fill(
                    selector,
                    "",
                    force=force,
                    timeout=timeout or self._timeout_ms,
                )
            await self.page.fill(
                selector,
                value,
                force=force,
                timeout=timeout or self._timeout_ms,
            )
            return {"success": True, "selector": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def click(
        self,
        selector: str,
        button: str = "left",
        click_count: int = 1,
        force: bool = False,
        timeout: int | None = None,
    ) -> dict:
        """Click an element."""
        # Handle special text-match selector for buttons
        if selector.startswith('button:text-match("'):
            text = selector[19:-2]
            return await self.click_by_text(text)

        try:
            await self.page.click(
                selector,
                button=button,  # type: ignore
                click_count=click_count,
                force=force,
                timeout=timeout or self._timeout_ms,
            )
            return {"success": True, "selector": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def click_by_text(self, text: str) -> dict:
        """Click a button by its text content."""
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
        return result.result if result.success else {"success": False, "error": "Evaluation failed"}

    async def select(
        self,
        selector: str,
        value: str | None = None,
        label: str | None = None,
        index: int | None = None,
        timeout: int | None = None,
    ) -> dict:
        """Select option from dropdown."""
        try:
            if value:
                await self.page.select_option(
                    selector,
                    value=value,
                    timeout=timeout or self._timeout_ms,
                )
            elif label:
                await self.page.select_option(
                    selector,
                    label=label,
                    timeout=timeout or self._timeout_ms,
                )
            elif index is not None:
                await self.page.select_option(
                    selector,
                    index=index,
                    timeout=timeout or self._timeout_ms,
                )
            return {"success": True, "selector": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def upload(
        self,
        selector: str,
        file_path: str,
        timeout: int | None = None,
    ) -> dict:
        """Upload a file."""
        try:
            await self.page.set_input_files(
                selector,
                file_path,
                timeout=timeout or self._timeout_ms,
            )
            return {"success": True, "selector": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # DOM & Screenshots
    # =========================================================================

    async def get_dom(
        self,
        selector: str | None = None,
        form_fields_only: bool = False,
    ) -> DOMResponse:
        """Get DOM information and form fields."""
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
            for inp in inputs[:50]:
                tag_name = await inp.evaluate("el => el.tagName.toLowerCase()")
                field_type = await inp.get_attribute("type") or (
                    "textarea" if tag_name == "textarea" else "text"
                )
                field_name = await inp.get_attribute("name") or None
                field_id = await inp.get_attribute("id") or None
                placeholder = await inp.get_attribute("placeholder") or None
                required = await inp.get_attribute("required") is not None

                if field_id:
                    field_selector = f"#{field_id}"
                elif field_name:
                    field_selector = f"[name='{field_name}']"
                else:
                    continue

                form_fields.append(
                    FormField(
                        selector=field_selector,
                        field_id=field_id,
                        field_name=field_name,
                        field_type=field_type,
                        tag_name=tag_name,
                        placeholder=placeholder,
                        required=required,
                    )
                )

            return DOMResponse(
                success=True,
                page_url=page_url,
                page_title=page_title,
                html_snippet=html_snippet,
                form_fields=form_fields,
            )
        except Exception as e:
            return DOMResponse(success=False, error=str(e))

    async def get_form_fields(self) -> list[FormField]:
        """Get all form fields on the page."""
        dom = await self.get_dom(form_fields_only=True)
        return dom.form_fields

    async def screenshot(
        self,
        full_page: bool = False,
        path: str | None = None,
    ) -> ScreenshotResponse:
        """Take a screenshot."""
        try:
            screenshot_bytes = await self.page.screenshot(full_page=full_page, path=path)
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            return ScreenshotResponse(success=True, screenshot_base64=screenshot_base64)
        except Exception as e:
            return ScreenshotResponse(success=False, error=str(e))

    # =========================================================================
    # JavaScript Evaluation
    # =========================================================================

    async def evaluate(
        self,
        script: str,
        args: list[Any] | None = None,
    ) -> EvaluateResponse:
        """Execute JavaScript in the page context."""
        start = time.time()
        try:
            result = await self.page.evaluate(script, args)
            duration_ms = int((time.time() - start) * 1000)
            return EvaluateResponse(success=True, duration_ms=duration_ms, result=result)
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            return EvaluateResponse(success=False, duration_ms=duration_ms, error=str(e))

    async def is_element_visible(self, selector: str) -> bool:
        """Check if element is visible."""
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
        """Get text content of element."""
        result = await self.evaluate(f"""
            (() => {{
                const el = document.querySelector('{selector}');
                return el ? el.textContent.trim() : null;
            }})()
        """)
        return result.result if result.success else None

    # =========================================================================
    # Static Methods
    # =========================================================================

    @classmethod
    async def is_service_available(cls, **kwargs: Any) -> bool:
        """Check if Browserless.io is available."""
        token = kwargs.get("browserless_token") or settings.browserless_token
        url = kwargs.get("browserless_url") or settings.browserless_url

        if not token:
            return False

        try:
            pw = await async_playwright().start()
            try:
                browser = await pw.chromium.connect_over_cdp(f"{url}?token={token}")
                await browser.close()
                return True
            finally:
                await pw.stop()
        except Exception:
            return False

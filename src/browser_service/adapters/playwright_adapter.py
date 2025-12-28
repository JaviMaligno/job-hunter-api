"""Playwright browser adapter for headless/cloud automation."""

import base64
import logging
import time
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from src.browser_service.adapters.base import BrowserAdapter
from src.browser_service.models import (
    BrowserAction,
    ClickRequest,
    ClickResponse,
    DOMResponse,
    EvaluateRequest,
    EvaluateResponse,
    FillRequest,
    FillResponse,
    FormField,
    NavigateRequest,
    NavigateResponse,
    ScreenshotResponse,
    SelectRequest,
    SessionCreateRequest,
    UploadRequest,
    WaitRequest,
)

logger = logging.getLogger(__name__)


class PlaywrightAdapter(BrowserAdapter):
    """Browser adapter using Playwright for automation.

    Supports headless and headed modes, suitable for both local
    development and cloud deployment.
    """

    def __init__(self) -> None:
        """Initialize adapter state."""
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._default_timeout: int = 30000

    @property
    def adapter_name(self) -> str:
        """Return adapter name."""
        return "playwright"

    @property
    def page(self) -> Page:
        """Get the current page, raising if not initialized."""
        if self._page is None:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        return self._page

    async def initialize(self, config: SessionCreateRequest) -> None:
        """Initialize Playwright browser.

        Args:
            config: Session configuration with headless, viewport, etc.
        """
        logger.info(f"Initializing Playwright adapter (headless={config.headless})")

        self._playwright = await async_playwright().start()
        self._default_timeout = config.timeout

        # Launch browser
        self._browser = await self._playwright.chromium.launch(
            headless=config.headless,
            slow_mo=config.slow_mo,
        )

        # Create context with viewport
        self._context = await self._browser.new_context(
            viewport={"width": config.viewport_width, "height": config.viewport_height},
            user_agent=config.user_agent,
        )

        # Set default timeout
        self._context.set_default_timeout(config.timeout)

        # Create page
        self._page = await self._context.new_page()

        logger.info("Playwright browser initialized successfully")

    async def close(self) -> None:
        """Close browser and cleanup."""
        logger.info("Closing Playwright browser")

        if self._page:
            await self._page.close()
            self._page = None

        if self._context:
            await self._context.close()
            self._context = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        logger.info("Playwright browser closed")

    async def navigate(self, request: NavigateRequest) -> NavigateResponse:
        """Navigate to URL."""
        start = time.time()
        try:
            timeout = request.timeout or self._default_timeout

            response = await self.page.goto(
                request.url,
                wait_until=request.wait_until,  # type: ignore
                timeout=timeout,
            )

            duration = int((time.time() - start) * 1000)

            # Check if navigation was successful
            is_success = response is not None and response.ok
            error_msg = None
            if response is None:
                error_msg = "Navigation returned no response"
            elif not response.ok:
                error_msg = f"HTTP {response.status}: {response.status_text}"

            return NavigateResponse(
                success=is_success,
                duration_ms=duration,
                url=self.page.url,
                page_title=await self.page.title(),
                error=error_msg,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"Navigation failed: {e}")
            return NavigateResponse(
                success=False,
                duration_ms=duration,
                url=request.url,
                error=str(e),
            )

    async def fill(self, request: FillRequest) -> FillResponse:
        """Fill a form field."""
        start = time.time()
        try:
            timeout = request.timeout or self._default_timeout

            if request.clear_first:
                await self.page.fill(
                    request.selector,
                    "",
                    timeout=timeout,
                    force=request.force,
                )

            await self.page.fill(
                request.selector,
                request.value,
                timeout=timeout,
                force=request.force,
            )

            duration = int((time.time() - start) * 1000)

            return FillResponse(
                success=True,
                duration_ms=duration,
                selector=request.selector,
                value_filled=request.value,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"Fill failed for {request.selector}: {e}")
            return FillResponse(
                success=False,
                duration_ms=duration,
                selector=request.selector,
                value_filled="",
                error=str(e),
            )

    async def click(self, request: ClickRequest) -> ClickResponse:
        """Click an element."""
        start = time.time()
        try:
            timeout = request.timeout or self._default_timeout

            await self.page.click(
                request.selector,
                button=request.button,  # type: ignore
                click_count=request.click_count,
                delay=request.delay,
                force=request.force,
                timeout=timeout,
            )

            duration = int((time.time() - start) * 1000)

            return ClickResponse(
                success=True,
                duration_ms=duration,
                selector=request.selector,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"Click failed for {request.selector}: {e}")
            return ClickResponse(
                success=False,
                duration_ms=duration,
                selector=request.selector,
                error=str(e),
            )

    async def select(self, request: SelectRequest) -> Any:
        """Select option from dropdown."""
        start = time.time()
        try:
            timeout = request.timeout or self._default_timeout

            if request.value:
                await self.page.select_option(
                    request.selector,
                    value=request.value,
                    timeout=timeout,
                )
            elif request.label:
                await self.page.select_option(
                    request.selector,
                    label=request.label,
                    timeout=timeout,
                )
            elif request.index is not None:
                await self.page.select_option(
                    request.selector,
                    index=request.index,
                    timeout=timeout,
                )

            duration = int((time.time() - start) * 1000)

            return {
                "success": True,
                "action": BrowserAction.SELECT,
                "duration_ms": duration,
                "selector": request.selector,
            }
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"Select failed for {request.selector}: {e}")
            return {
                "success": False,
                "action": BrowserAction.SELECT,
                "duration_ms": duration,
                "selector": request.selector,
                "error": str(e),
            }

    async def upload(self, request: UploadRequest) -> Any:
        """Upload file to file input."""
        start = time.time()
        try:
            timeout = request.timeout or self._default_timeout

            await self.page.set_input_files(
                request.selector,
                request.file_path,
                timeout=timeout,
            )

            duration = int((time.time() - start) * 1000)

            return {
                "success": True,
                "action": BrowserAction.UPLOAD,
                "duration_ms": duration,
                "selector": request.selector,
                "file_path": request.file_path,
            }
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"Upload failed for {request.selector}: {e}")
            return {
                "success": False,
                "action": BrowserAction.UPLOAD,
                "duration_ms": duration,
                "selector": request.selector,
                "error": str(e),
            }

    async def screenshot(
        self, full_page: bool = False, path: str | None = None
    ) -> ScreenshotResponse:
        """Take a screenshot."""
        try:
            screenshot_bytes = await self.page.screenshot(
                full_page=full_page,
                path=path,
            )

            viewport = self.page.viewport_size

            return ScreenshotResponse(
                success=True,
                screenshot_base64=base64.b64encode(screenshot_bytes).decode("utf-8"),
                screenshot_path=path,
                width=viewport["width"] if viewport else None,
                height=viewport["height"] if viewport else None,
            )
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return ScreenshotResponse(
                success=False,
                error=str(e),
            )

    async def evaluate(self, request: EvaluateRequest) -> EvaluateResponse:
        """Execute JavaScript."""
        start = time.time()
        try:
            if request.args:
                result = await self.page.evaluate(request.script, request.args)
            else:
                result = await self.page.evaluate(request.script)

            duration = int((time.time() - start) * 1000)

            return EvaluateResponse(
                success=True,
                duration_ms=duration,
                result=result,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"Evaluate failed: {e}")
            return EvaluateResponse(
                success=False,
                duration_ms=duration,
                error=str(e),
            )

    async def get_dom(
        self, selector: str | None = None, form_fields_only: bool = False
    ) -> DOMResponse:
        """Get DOM information and form fields."""
        try:
            # JavaScript to extract form fields - using object arg for clarity
            js_script = """
                (args) => {
                    const rootSelector = args.rootSelector;
                    const formFieldsOnly = args.formFieldsOnly;

                    const root = rootSelector
                        ? document.querySelector(rootSelector)
                        : document;

                    if (!root) return { fields: [], html: null };

                    const fields = [];
                    const selectors = formFieldsOnly
                        ? 'input, select, textarea'
                        : 'input, select, textarea, button[type="submit"]';

                    root.querySelectorAll(selectors).forEach((el, index) => {
                        // Skip hidden inputs (but include type=hidden for form data)
                        const style = window.getComputedStyle(el);
                        const isVisible = style.display !== 'none' &&
                                         style.visibility !== 'hidden' &&
                                         el.offsetParent !== null;

                        // Get label
                        let label = null;
                        const labelEl = el.labels?.[0] ||
                                       document.querySelector(`label[for="${el.id}"]`);
                        if (labelEl) {
                            label = labelEl.textContent.trim();
                        }

                        // Get options for select
                        let options = null;
                        if (el.tagName === 'SELECT') {
                            options = Array.from(el.options).map(o => o.text);
                        }

                        // Build unique selector
                        let uniqueSelector = '';
                        if (el.id) {
                            uniqueSelector = `#${el.id}`;
                        } else if (el.name) {
                            uniqueSelector = `${el.tagName.toLowerCase()}[name="${el.name}"]`;
                        } else {
                            uniqueSelector = `${el.tagName.toLowerCase()}:nth-of-type(${index + 1})`;
                        }

                        fields.push({
                            selector: uniqueSelector,
                            field_id: el.id || null,
                            field_name: el.name || null,
                            field_type: el.type || el.tagName.toLowerCase(),
                            tag_name: el.tagName.toLowerCase(),
                            label: label,
                            placeholder: el.placeholder || null,
                            required: el.required || el.hasAttribute('aria-required'),
                            current_value: el.value || null,
                            options: options,
                            is_visible: isVisible,
                            is_enabled: !el.disabled,
                        });
                    });

                    return {
                        fields: fields,
                        html: root.innerHTML?.substring(0, 5000) || null
                    };
                }
            """

            result = await self.page.evaluate(
                js_script, {"rootSelector": selector, "formFieldsOnly": form_fields_only}
            )

            form_fields = [FormField(**f) for f in result.get("fields", [])]

            return DOMResponse(
                success=True,
                page_url=self.page.url,
                page_title=await self.page.title(),
                form_fields=form_fields,
                html_snippet=result.get("html"),
            )
        except Exception as e:
            logger.error(f"Get DOM failed: {e}")
            return DOMResponse(
                success=False,
                page_url=self.page.url if self._page else "",
                page_title="",
                error=str(e),
            )

    async def wait_for(self, request: WaitRequest) -> bool:
        """Wait for element/condition."""
        try:
            timeout = request.timeout or self._default_timeout

            if request.selector:
                await self.page.wait_for_selector(
                    request.selector,
                    state=request.state,  # type: ignore
                    timeout=timeout,
                )
            return True
        except Exception as e:
            logger.warning(f"Wait timeout for {request.selector}: {e}")
            return False

    async def get_current_url(self) -> str:
        """Get current page URL."""
        return self.page.url

    async def get_page_title(self) -> str:
        """Get current page title."""
        return await self.page.title()

    async def get_page_content(self) -> str:
        """Get page HTML content."""
        return await self.page.content()

"""Chrome DevTools MCP adapter for local browser automation.

This adapter uses the chrome-devtools-mcp server via MCP protocol
for browser automation. Ideal for local/assisted mode where the user can
see the browser.

The MCP protocol uses accessibility-tree based element identification with UIDs,
not CSS selectors. This adapter bridges the gap by:
1. Taking snapshots to get element UIDs
2. Finding elements by role, name, or accessibility properties
3. Using UIDs for actual MCP operations
"""

import logging
import re
import time
from typing import Any

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
from src.mcp.chrome_client import ChromeDevToolsMCP

logger = logging.getLogger(__name__)


class ChromeDevToolsAdapter(BrowserAdapter):
    """Browser adapter using Chrome DevTools MCP.

    This adapter connects to the chrome-devtools-mcp server
    and provides browser automation through the MCP protocol.

    Requires:
        - Chrome/Chromium browser installed
        - Node.js with npx available
        - chrome-devtools-mcp package
    """

    def __init__(self) -> None:
        """Initialize adapter state."""
        self._mcp_client: ChromeDevToolsMCP | None = None
        self._current_url: str = ""
        self._current_title: str = ""
        self._default_timeout: int = 30000
        self._cached_snapshot: str = ""
        self._cached_elements: list[dict] = []

    @property
    def adapter_name(self) -> str:
        """Return adapter name."""
        return "chrome-devtools"

    @property
    def mcp(self) -> ChromeDevToolsMCP:
        """Get MCP client, raising if not initialized."""
        if self._mcp_client is None:
            raise RuntimeError("MCP client not initialized. Call initialize() first.")
        return self._mcp_client

    async def initialize(self, config: SessionCreateRequest) -> None:
        """Initialize Chrome DevTools MCP connection.

        Args:
            config: Session configuration
        """
        logger.info("Initializing Chrome DevTools MCP adapter")

        self._default_timeout = config.timeout

        # Parse port from devtools_url if provided (e.g., "http://localhost:9222")
        port = None
        if config.devtools_url:
            import re
            port_match = re.search(r':(\d+)/?$', config.devtools_url)
            if port_match:
                port = int(port_match.group(1))
            logger.info(f"Using Chrome DevTools at port {port} (from {config.devtools_url})")

        # Create and connect MCP client
        self._mcp_client = ChromeDevToolsMCP(port=port)
        await self._mcp_client.__aenter__()

        # List available tools for debugging
        tools = await self._mcp_client.list_available_tools()
        logger.info(f"Chrome DevTools MCP initialized with tools: {tools}")

    async def close(self) -> None:
        """Close MCP connection."""
        logger.info("Closing Chrome DevTools MCP adapter")

        if self._mcp_client:
            await self._mcp_client.__aexit__(None, None, None)
            self._mcp_client = None

        logger.info("Chrome DevTools MCP adapter closed")

    # =========================================================================
    # Snapshot and element finding helpers
    # =========================================================================

    async def _refresh_snapshot(self) -> list[dict]:
        """Take a fresh accessibility snapshot and parse elements.

        Returns:
            List of element dicts with uid, role, name
        """
        result = await self.mcp.take_snapshot()
        logger.debug(f"Snapshot raw result type: {type(result)}, keys: {result.keys() if isinstance(result, dict) else 'N/A'}")

        # Handle different result structures from MCP
        if isinstance(result, dict):
            # Try 'text' first, then 'content', then stringify
            if "text" in result:
                self._cached_snapshot = result["text"]
            elif "content" in result:
                content = result["content"]
                if isinstance(content, list) and len(content) > 0:
                    first = content[0]
                    self._cached_snapshot = getattr(first, 'text', str(first))
                else:
                    self._cached_snapshot = str(content)
            else:
                self._cached_snapshot = str(result)
        else:
            self._cached_snapshot = str(result) if result else ""

        logger.debug(f"Snapshot content length: {len(self._cached_snapshot)}, first 500 chars: {self._cached_snapshot[:500]}")
        self._cached_elements = self._parse_snapshot(self._cached_snapshot)
        logger.info(f"Parsed {len(self._cached_elements)} elements from snapshot")
        return self._cached_elements

    def _parse_snapshot(self, snapshot_text: str) -> list[dict]:
        """Parse snapshot markdown to extract elements with UIDs.

        The snapshot format is:
        uid=1_0 RootWebArea "Example Domain" url="https://example.com/"
          uid=1_1 heading "Example Domain" level="1"
          uid=1_2 StaticText "Some text"
          uid=1_3 link "Learn more" url="..."

        Args:
            snapshot_text: Raw snapshot markdown

        Returns:
            List of element dicts with uid, role, name
        """
        elements = []
        # Pattern to match uid=X_Y followed by role and optional name
        pattern = r'uid=(\d+_\d+)\s+(\w+)(?:\s+"([^"]*)")?'

        for match in re.finditer(pattern, snapshot_text):
            uid = match.group(1)
            role = match.group(2)
            name = match.group(3) or ""
            elements.append({
                "uid": uid,
                "role": role,
                "name": name,
            })

        return elements

    def _find_element_by_role(
        self, role: str, name_contains: str = ""
    ) -> dict | None:
        """Find element by role and optionally name.

        Args:
            role: Accessibility role (e.g., 'textbox', 'button', 'link')
            name_contains: Optional substring to match in element name

        Returns:
            Element dict or None if not found
        """
        for el in self._cached_elements:
            if el.get("role", "").lower() == role.lower():
                if not name_contains or name_contains.lower() in el.get("name", "").lower():
                    return el
        return None

    def _find_element_by_name(self, name_contains: str) -> dict | None:
        """Find element whose name contains the given string.

        Args:
            name_contains: Substring to match in element name

        Returns:
            Element dict or None if not found
        """
        for el in self._cached_elements:
            if name_contains.lower() in el.get("name", "").lower():
                return el
        return None

    def _find_elements_by_role(self, role: str) -> list[dict]:
        """Find all elements with given role.

        Args:
            role: Accessibility role

        Returns:
            List of matching element dicts
        """
        return [
            el for el in self._cached_elements
            if el.get("role", "").lower() == role.lower()
        ]

    def _guess_role_from_selector(self, selector: str) -> tuple[str, str]:
        """Guess accessibility role from CSS selector.

        Args:
            selector: CSS selector

        Returns:
            Tuple of (role, name_hint)
        """
        selector_lower = selector.lower()

        # Input types to roles
        if "input" in selector_lower:
            if "type=" in selector_lower:
                if "submit" in selector_lower:
                    return ("button", "")
                if "checkbox" in selector_lower:
                    return ("checkbox", "")
                if "radio" in selector_lower:
                    return ("radio", "")
                if "file" in selector_lower:
                    return ("button", "")  # File inputs are buttons
            return ("textbox", "")

        if "button" in selector_lower:
            return ("button", "")
        if "select" in selector_lower:
            return ("combobox", "")
        if "textarea" in selector_lower:
            return ("textbox", "")
        if "a[" in selector_lower or "link" in selector_lower:
            return ("link", "")

        # Extract name hint from selector
        name_match = re.search(r'name="([^"]+)"', selector)
        if name_match:
            return ("textbox", name_match.group(1))

        # Extract id hint
        id_match = re.search(r'#([a-zA-Z0-9_-]+)', selector)
        if id_match:
            return ("", id_match.group(1))

        return ("", "")

    async def _find_element_for_selector(self, selector: str) -> dict | None:
        """Find element UID for a CSS-like selector.

        This is a best-effort mapping from CSS selectors to accessibility tree elements.

        Args:
            selector: CSS selector

        Returns:
            Element dict with uid, or None if not found
        """
        # Refresh snapshot to get current elements
        await self._refresh_snapshot()

        # Try to guess role and name from selector
        role_hint, name_hint = self._guess_role_from_selector(selector)

        if role_hint:
            element = self._find_element_by_role(role_hint, name_hint)
            if element:
                return element

        if name_hint:
            element = self._find_element_by_name(name_hint)
            if element:
                return element

        # Fallback: try to find any textbox/combobox for form inputs
        if "input" in selector.lower() or "textarea" in selector.lower():
            textboxes = self._find_elements_by_role("textbox")
            if textboxes:
                return textboxes[0]

        logger.warning(f"Could not find element for selector: {selector}")
        return None

    # =========================================================================
    # BrowserAdapter interface implementation
    # =========================================================================

    async def navigate(self, request: NavigateRequest) -> NavigateResponse:
        """Navigate to URL via MCP."""
        start = time.time()

        try:
            result = await self.mcp.navigate(request.url)
            duration = int((time.time() - start) * 1000)

            # Update cached URL/title
            self._current_url = await self.mcp.get_current_url()
            self._current_title = await self.mcp.get_page_title()

            return NavigateResponse(
                success=True,
                duration_ms=duration,
                url=self._current_url,
                page_title=self._current_title,
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
        """Fill form field via MCP.

        Maps CSS selector to element UID, then fills.
        """
        start = time.time()

        try:
            # Find element UID for selector
            element = await self._find_element_for_selector(request.selector)
            if not element:
                raise ValueError(f"Could not find element for selector: {request.selector}")

            # Fill using UID
            await self.mcp.fill(element["uid"], request.value)
            duration = int((time.time() - start) * 1000)

            return FillResponse(
                success=True,
                duration_ms=duration,
                selector=request.selector,
                value_filled=request.value,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"Fill failed: {e}")
            return FillResponse(
                success=False,
                duration_ms=duration,
                selector=request.selector,
                value_filled="",
                error=str(e),
            )

    async def click(self, request: ClickRequest) -> ClickResponse:
        """Click element via MCP.

        Maps CSS selector to element UID, then clicks.
        """
        start = time.time()

        try:
            # Find element UID for selector
            element = await self._find_element_for_selector(request.selector)
            if not element:
                raise ValueError(f"Could not find element for selector: {request.selector}")

            # Click using UID
            await self.mcp.click(element["uid"])
            duration = int((time.time() - start) * 1000)

            return ClickResponse(
                success=True,
                duration_ms=duration,
                selector=request.selector,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"Click failed: {e}")
            return ClickResponse(
                success=False,
                duration_ms=duration,
                selector=request.selector,
                error=str(e),
            )

    async def select(self, request: SelectRequest) -> Any:
        """Select dropdown option via MCP."""
        start = time.time()

        try:
            # Find element UID
            element = await self._find_element_for_selector(request.selector)
            if not element:
                raise ValueError(f"Could not find element for selector: {request.selector}")

            # For select, we need to click then select option
            # MCP doesn't have a direct select_option, so we click and use keyboard
            await self.mcp.click(element["uid"])

            # Type the value to filter/select
            value = request.value or request.label or ""
            if value:
                await self.mcp.press_key("Enter")  # Open dropdown
                # Type to filter
                for char in value:
                    await self.mcp.press_key(char)
                await self.mcp.press_key("Enter")  # Select

            duration = int((time.time() - start) * 1000)

            return {
                "success": True,
                "action": BrowserAction.SELECT,
                "duration_ms": duration,
                "selector": request.selector,
            }
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"Select failed: {e}")
            return {
                "success": False,
                "action": BrowserAction.SELECT,
                "duration_ms": duration,
                "selector": request.selector,
                "error": str(e),
            }

    async def upload(self, request: UploadRequest) -> Any:
        """Upload file via MCP."""
        start = time.time()

        try:
            # Find file input element
            element = await self._find_element_for_selector(request.selector)
            if not element:
                raise ValueError(f"Could not find element for selector: {request.selector}")

            # Use upload_file tool
            await self.mcp.upload_file(element["uid"], request.file_path)
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
            logger.error(f"Upload failed: {e}")
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
        """Take screenshot via MCP."""
        try:
            result = await self.mcp.screenshot(full_page=full_page)

            # MCP returns text response with base64 data
            screenshot_text = result.get("text", "")

            # Extract base64 from markdown if present
            base64_match = re.search(r'!\[.*?\]\(data:image/\w+;base64,([^)]+)\)', screenshot_text)
            if base64_match:
                screenshot_base64 = base64_match.group(1)
            else:
                # Might be raw base64
                screenshot_base64 = result.get("data", "")

            # Save to file if path provided
            if path and screenshot_base64:
                import base64
                with open(path, "wb") as f:
                    f.write(base64.b64decode(screenshot_base64))

            return ScreenshotResponse(
                success=True,
                screenshot_base64=screenshot_base64,
                screenshot_path=path,
            )
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return ScreenshotResponse(
                success=False,
                error=str(e),
            )

    async def evaluate(self, request: EvaluateRequest) -> EvaluateResponse:
        """Execute JavaScript via MCP.

        Note: MCP expects arrow function syntax for evaluate_script.
        """
        start = time.time()

        try:
            # Wrap script in arrow function if not already
            script = request.script
            if not script.strip().startswith("()"):
                script = f"() => {script}"

            result = await self.mcp.evaluate(script)
            duration = int((time.time() - start) * 1000)

            # Extract value from result
            value = self.mcp._extract_json_value(result)

            return EvaluateResponse(
                success=True,
                duration_ms=duration,
                result=value,
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
        """Get DOM information via accessibility snapshot.

        MCP uses accessibility tree, so we map to FormField model.
        """
        try:
            # Refresh snapshot
            await self._refresh_snapshot()
            logger.info(f"DOM snapshot: {len(self._cached_elements)} elements parsed")

            # Map accessibility elements to FormField
            form_fields = []
            for el in self._cached_elements:
                role = el.get("role", "")
                name = el.get("name", "")
                uid = el.get("uid", "")

                # Filter to form-like elements (expanded list for better form detection)
                form_roles = (
                    "textbox", "combobox", "checkbox", "radio", "button", "searchbox",
                    "listbox", "spinbutton", "option", "slider", "switch", "menuitemcheckbox",
                    "menuitemradio", "searchbox", "textarea"
                )
                if role.lower() in form_roles:
                    field_type = "text"
                    role_lower = role.lower()
                    if role_lower in ("combobox", "listbox"):
                        field_type = "select"
                    elif role_lower == "checkbox":
                        field_type = "checkbox"
                    elif role_lower in ("radio", "menuitemradio"):
                        field_type = "radio"
                    elif role_lower == "button":
                        field_type = "submit"
                    elif role_lower == "searchbox":
                        field_type = "search"
                    elif role_lower in ("spinbutton", "slider"):
                        field_type = "number"
                    elif role_lower == "switch":
                        field_type = "checkbox"
                    elif role_lower == "textarea":
                        field_type = "textarea"

                    form_fields.append(FormField(
                        selector=f"[uid={uid}]",  # Use UID as selector
                        field_id=uid,
                        field_name=name,
                        field_type=field_type,
                        tag_name=role.lower(),
                        label=name,
                        placeholder=None,
                        required=False,
                        current_value=None,
                        options=None,
                        is_visible=True,
                        is_enabled=True,
                    ))

            logger.info(f"DOM found {len(form_fields)} form fields")
            return DOMResponse(
                success=True,
                page_url=self._current_url or await self.mcp.get_current_url(),
                page_title=self._current_title or await self.mcp.get_page_title(),
                form_fields=form_fields,
                html_snippet=self._cached_snapshot[:5000],
            )
        except Exception as e:
            logger.error(f"Get DOM failed: {e}")
            return DOMResponse(
                success=False,
                page_url=self._current_url,
                page_title=self._current_title,
                error=str(e),
            )

    async def wait_for(self, request: WaitRequest) -> bool:
        """Wait for element/condition via MCP."""
        try:
            timeout = request.timeout or self._default_timeout
            if request.selector:
                result = await self.mcp.wait_for(
                    selector=request.selector,
                    timeout=timeout,
                    state=request.state or "visible",
                )
                return "error" not in str(result).lower()
            return True
        except Exception as e:
            logger.warning(f"Wait timeout: {e}")
            return False

    async def get_current_url(self) -> str:
        """Get current page URL."""
        try:
            self._current_url = await self.mcp.get_current_url()
            return self._current_url
        except Exception:
            return self._current_url

    async def get_page_title(self) -> str:
        """Get current page title."""
        try:
            self._current_title = await self.mcp.get_page_title()
            return self._current_title
        except Exception:
            return self._current_title

    async def get_page_content(self) -> str:
        """Get page HTML content."""
        try:
            return await self.mcp.get_content()
        except Exception:
            return ""

    # =========================================================================
    # MCP-specific methods (direct UID access)
    # =========================================================================

    async def fill_by_uid(self, uid: str, value: str) -> dict[str, Any]:
        """Fill element directly by UID.

        Args:
            uid: Element UID from snapshot
            value: Value to fill

        Returns:
            Result dict
        """
        return await self.mcp.fill(uid, value)

    async def click_by_uid(self, uid: str) -> dict[str, Any]:
        """Click element directly by UID.

        Args:
            uid: Element UID from snapshot

        Returns:
            Result dict
        """
        return await self.mcp.click(uid)

    async def get_snapshot(self) -> tuple[str, list[dict]]:
        """Get accessibility snapshot and parsed elements.

        Returns:
            Tuple of (raw_snapshot, parsed_elements)
        """
        await self._refresh_snapshot()
        return self._cached_snapshot, self._cached_elements

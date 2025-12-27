"""Chrome DevTools MCP client wrapper.

This module provides a Python interface to the chrome-devtools-mcp
server, enabling browser automation via the Model Context Protocol.

Based on: https://github.com/ChromeDevTools/chrome-devtools-mcp

Available tools (26 total):
- Input: click, drag, fill, fill_form, handle_dialog, hover, upload_file
- Navigation: navigate_page, new_page, list_pages, select_page, close_page,
              navigate_page_history, wait_for
- Debugging: evaluate_script, list_console_messages, take_screenshot, take_snapshot
- Network: list_network_requests, get_network_request

Usage:
    async with ChromeDevToolsMCP() as chrome:
        await chrome.navigate("https://example.com")
        await chrome.fill("input[name='email']", "user@example.com")
        await chrome.click("button[type='submit']")
        screenshot = await chrome.screenshot()
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logger = logging.getLogger(__name__)


class ChromeDevToolsMCP:
    """MCP client for Chrome DevTools browser automation.

    Connects to chrome-devtools-mcp server via stdio
    and provides browser automation capabilities.

    Requirements:
        - Node.js 22 or above
        - Chrome browser (stable channel or newer)

    The MCP server is run via npx (default):
        npx chrome-devtools-mcp@latest
    """

    def __init__(
        self,
        command: str = "npx",
        args: list[str] | None = None,
        cwd: str | None = None,
        port: int | None = None,
    ) -> None:
        """Initialize Chrome DevTools MCP client.

        Args:
            command: Command to run MCP server (default: npx)
            args: Arguments for command (default: [chrome-devtools-mcp@latest])
            cwd: Working directory for server process
            port: Chrome DevTools debugging port (default: 9222)
        """
        default_args = ["chrome-devtools-mcp@latest", "--isolated"]
        if port:
            default_args.append(f"--port={port}")

        self.server_params = StdioServerParameters(
            command=command,
            args=args or default_args,
            cwd=cwd,
        )
        self._session: ClientSession | None = None
        self._context_manager: Any = None
        self._tools: dict[str, Any] = {}

    async def __aenter__(self) -> "ChromeDevToolsMCP":
        """Start MCP server and establish connection."""
        logger.info("Starting Chrome DevTools MCP server...")

        # Create stdio client context
        self._context_manager = stdio_client(self.server_params)
        read_stream, write_stream = await self._context_manager.__aenter__()

        # Create and initialize session
        self._session = ClientSession(read_stream, write_stream)
        await self._session.__aenter__()

        # Initialize the session
        result = await self._session.initialize()
        server_info = getattr(result, 'serverInfo', getattr(result, 'server_info', None))
        logger.info(f"MCP session initialized: {server_info}")

        # Cache available tools
        tools_result = await self._session.list_tools()
        self._tools = {tool.name: tool for tool in tools_result.tools}
        logger.info(f"Available browser tools: {list(self._tools.keys())}")

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close MCP connection and stop server."""
        if self._session:
            await self._session.__aexit__(exc_type, exc_val, exc_tb)
            self._session = None

        if self._context_manager:
            await self._context_manager.__aexit__(exc_type, exc_val, exc_tb)
            self._context_manager = None

        logger.info("Chrome DevTools MCP session closed")

    @property
    def session(self) -> ClientSession:
        """Get current session, raising if not connected."""
        if self._session is None:
            raise RuntimeError("Not connected. Use 'async with ChromeDevToolsMCP()' context.")
        return self._session

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call an MCP tool.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result
        """
        logger.debug(f"Calling tool: {name} with args: {arguments}")
        result = await self.session.call_tool(name, arguments or {})
        return result

    # =========================================================================
    # Navigation tools
    # =========================================================================

    async def navigate(self, url: str) -> dict[str, Any]:
        """Navigate to a URL.

        Args:
            url: URL to navigate to

        Returns:
            Navigation result
        """
        result = await self.call_tool("navigate_page", {"url": url})
        return self._parse_result(result)

    async def new_page(self, url: str | None = None) -> dict[str, Any]:
        """Open a new page/tab.

        Args:
            url: Optional URL to navigate to

        Returns:
            New page result
        """
        args = {"url": url} if url else {}
        result = await self.call_tool("new_page", args)
        return self._parse_result(result)

    async def list_pages(self) -> dict[str, Any]:
        """List all open pages.

        Returns:
            List of pages
        """
        result = await self.call_tool("list_pages", {})
        return self._parse_result(result)

    async def select_page(self, page_id: str) -> dict[str, Any]:
        """Select/focus a specific page.

        Args:
            page_id: Page ID to select

        Returns:
            Selection result
        """
        result = await self.call_tool("select_page", {"pageId": page_id})
        return self._parse_result(result)

    async def close_page(self, page_id: str | None = None) -> dict[str, Any]:
        """Close a page.

        Args:
            page_id: Page ID to close (current if None)

        Returns:
            Close result
        """
        args = {"pageId": page_id} if page_id else {}
        result = await self.call_tool("close_page", args)
        return self._parse_result(result)

    async def wait_for(
        self,
        selector: str | None = None,
        timeout: int = 30000,
        state: str = "visible"
    ) -> dict[str, Any]:
        """Wait for element/condition.

        Args:
            selector: CSS selector to wait for
            timeout: Timeout in milliseconds
            state: State to wait for (visible, hidden, attached, detached)

        Returns:
            Wait result
        """
        args: dict[str, Any] = {"timeout": timeout}
        if selector:
            args["selector"] = selector
            args["state"] = state
        result = await self.call_tool("wait_for", args)
        return self._parse_result(result)

    # =========================================================================
    # Input tools
    # =========================================================================

    async def fill(self, uid: str, value: str) -> dict[str, Any]:
        """Fill a form field.

        Args:
            uid: Element unique identifier from accessibility snapshot
            value: Value to fill

        Returns:
            Fill result
        """
        result = await self.call_tool("fill", {
            "uid": uid,
            "value": value,
        })
        return self._parse_result(result)

    async def fill_form(self, fields: list[dict[str, str]]) -> dict[str, Any]:
        """Fill multiple form fields at once.

        Args:
            fields: List of {uid, value} dicts

        Returns:
            Fill result
        """
        result = await self.call_tool("fill_form", {"fields": fields})
        return self._parse_result(result)

    async def click(self, uid: str) -> dict[str, Any]:
        """Click an element.

        Args:
            uid: Element unique identifier from accessibility snapshot

        Returns:
            Click result
        """
        result = await self.call_tool("click", {"uid": uid})
        return self._parse_result(result)

    async def hover(self, uid: str) -> dict[str, Any]:
        """Hover over an element.

        Args:
            uid: Element unique identifier from accessibility snapshot

        Returns:
            Hover result
        """
        result = await self.call_tool("hover", {"uid": uid})
        return self._parse_result(result)

    async def drag(
        self,
        source_uid: str,
        target_uid: str
    ) -> dict[str, Any]:
        """Drag from one element to another.

        Args:
            source_uid: Source element UID
            target_uid: Target element UID

        Returns:
            Drag result
        """
        result = await self.call_tool("drag", {
            "sourceUid": source_uid,
            "targetUid": target_uid,
        })
        return self._parse_result(result)

    async def upload_file(self, uid: str, file_path: str) -> dict[str, Any]:
        """Upload a file to a file input.

        Args:
            uid: Element unique identifier from accessibility snapshot
            file_path: Path to file to upload

        Returns:
            Upload result
        """
        result = await self.call_tool("upload_file", {
            "uid": uid,
            "filePath": file_path,
        })
        return self._parse_result(result)

    async def press_key(self, key: str, uid: str | None = None) -> dict[str, Any]:
        """Press a key.

        Args:
            key: Key to press (e.g., 'Enter', 'Tab', 'Escape')
            uid: Optional element to focus first

        Returns:
            Press result
        """
        args: dict[str, Any] = {"key": key}
        if uid:
            args["uid"] = uid
        result = await self.call_tool("press_key", args)
        return self._parse_result(result)

    async def handle_dialog(self, accept: bool, prompt_text: str | None = None) -> dict[str, Any]:
        """Handle a dialog (alert, confirm, prompt).

        Args:
            accept: Whether to accept the dialog
            prompt_text: Text to enter for prompt dialogs

        Returns:
            Dialog result
        """
        args: dict[str, Any] = {"accept": accept}
        if prompt_text is not None:
            args["promptText"] = prompt_text
        result = await self.call_tool("handle_dialog", args)
        return self._parse_result(result)

    # =========================================================================
    # Debugging tools
    # =========================================================================

    async def evaluate(self, script: str) -> Any:
        """Execute JavaScript in the page context.

        Args:
            script: JavaScript code to execute

        Returns:
            Evaluation result
        """
        # MCP tool expects "function" argument, not "script"
        result = await self.call_tool("evaluate_script", {"function": script})
        return self._parse_result(result)

    async def screenshot(self, full_page: bool = False) -> dict[str, Any]:
        """Take a screenshot of the current page.

        Args:
            full_page: Capture full scrollable page

        Returns:
            Screenshot result with base64 data
        """
        result = await self.call_tool("take_screenshot", {"fullPage": full_page})
        return self._parse_result(result)

    async def take_snapshot(self) -> dict[str, Any]:
        """Take a DOM snapshot.

        Returns:
            Snapshot result
        """
        result = await self.call_tool("take_snapshot", {})
        return self._parse_result(result)

    async def list_console_messages(self) -> dict[str, Any]:
        """List console messages.

        Returns:
            Console messages
        """
        result = await self.call_tool("list_console_messages", {})
        return self._parse_result(result)

    # =========================================================================
    # Network tools
    # =========================================================================

    async def list_network_requests(self) -> dict[str, Any]:
        """List network requests.

        Returns:
            Network requests
        """
        result = await self.call_tool("list_network_requests", {})
        return self._parse_result(result)

    async def get_network_request(self, request_id: str) -> dict[str, Any]:
        """Get details of a specific network request.

        Args:
            request_id: Request ID

        Returns:
            Request details
        """
        result = await self.call_tool("get_network_request", {"requestId": request_id})
        return self._parse_result(result)

    # =========================================================================
    # Helper methods
    # =========================================================================

    async def get_content(self) -> str:
        """Get the page HTML content via evaluate.

        Returns:
            Page HTML
        """
        # MCP expects arrow function syntax
        result = await self.evaluate("() => document.documentElement.outerHTML")
        return self._extract_json_value(result)

    async def get_current_url(self) -> str:
        """Get current page URL via evaluate.

        Returns:
            Current URL
        """
        # MCP expects arrow function syntax
        result = await self.evaluate("() => window.location.href")
        return self._extract_json_value(result)

    async def get_page_title(self) -> str:
        """Get current page title via evaluate.

        Returns:
            Page title
        """
        # MCP expects arrow function syntax
        result = await self.evaluate("() => document.title")
        return self._extract_json_value(result)

    def _extract_json_value(self, result: Any) -> str:
        """Extract JSON value from MCP markdown response.

        MCP returns evaluate results in markdown format:
        ```
        # evaluate_script response
        Script ran on page and returned:
        ```json
        "value"
        ```
        ```

        Args:
            result: MCP tool result

        Returns:
            Extracted string value
        """
        import json
        import re

        if isinstance(result, dict):
            text = result.get("text", "")
        else:
            text = str(result) if result else ""

        # Try to extract JSON from markdown code block
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return match.group(1).strip('"')

        return text

    async def list_available_tools(self) -> list[str]:
        """List all available MCP tools.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def _parse_result(self, result: Any) -> dict[str, Any]:
        """Parse MCP tool result into a dictionary.

        Args:
            result: Raw MCP result

        Returns:
            Parsed result dict
        """
        # MCP results come as CallToolResult with content
        if hasattr(result, 'content'):
            content = result.content
            if isinstance(content, list) and len(content) > 0:
                first = content[0]
                if hasattr(first, 'text'):
                    # Try to parse as JSON
                    import json
                    try:
                        return json.loads(first.text)
                    except json.JSONDecodeError:
                        return {"text": first.text}
                elif hasattr(first, 'data'):
                    return {"data": first.data}
            return {"content": content}
        return {"result": result}


@asynccontextmanager
async def create_chrome_mcp():
    """Context manager factory for Chrome DevTools MCP.

    Usage:
        async with create_chrome_mcp() as chrome:
            await chrome.navigate("https://example.com")
    """
    client = ChromeDevToolsMCP()
    async with client:
        yield client

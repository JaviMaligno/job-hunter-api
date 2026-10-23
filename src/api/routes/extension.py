"""
Chrome Extension WebSocket API.

Handles bidirectional communication with the Job Hunter Chrome extension
for local browser automation.
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


class ExtensionConnectionManager:
    """Manages Chrome extension WebSocket connections.

    Features:
    - One extension connection at a time (per user in future)
    - Command queue for sending automation commands
    - Response tracking with timeouts
    """

    def __init__(self):
        self._connection: WebSocket | None = None
        self._connected = False
        self._pending_responses: dict[str, asyncio.Future] = {}
        self._message_id = 0
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if an extension is connected."""
        return self._connected and self._connection is not None

    async def connect(self, websocket: WebSocket) -> None:
        """Accept an extension connection."""
        await websocket.accept()

        async with self._lock:
            # Close existing connection if any
            if self._connection:
                try:
                    await self._connection.close()
                except Exception:
                    pass

            self._connection = websocket
            self._connected = True
            self._pending_responses.clear()

        logger.info("Chrome extension connected")

    async def disconnect(self) -> None:
        """Handle extension disconnect."""
        async with self._lock:
            self._connected = False
            self._connection = None

            # Cancel all pending responses
            for future in self._pending_responses.values():
                if not future.done():
                    future.cancel()
            self._pending_responses.clear()

        logger.info("Chrome extension disconnected")

    async def send_command(
        self,
        command_type: str,
        data: dict[str, Any],
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Send a command to the extension and wait for response.

        Args:
            command_type: Type of command (OPEN_TAB, FILL_FIELD, etc.)
            data: Command payload
            timeout: Response timeout in seconds

        Returns:
            Response from extension

        Raises:
            RuntimeError: If no extension connected
            asyncio.TimeoutError: If response times out
        """
        if not self.is_connected:
            raise RuntimeError("No extension connected")

        # Generate unique message ID
        async with self._lock:
            self._message_id += 1
            msg_id = f"msg_{self._message_id}"

        # Create future for response
        response_future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_responses[msg_id] = response_future

        # Send command
        message = {
            "id": msg_id,
            "type": command_type,
            **data,
        }

        try:
            await self._connection.send_json(message)
            logger.debug(f"Sent command: {command_type} (id={msg_id})")

            # Wait for response with timeout
            response = await asyncio.wait_for(response_future, timeout=timeout)
            return response

        except TimeoutError:
            logger.warning(f"Command {command_type} timed out (id={msg_id})")
            raise
        except Exception as e:
            logger.error(f"Error sending command: {e}")
            raise
        finally:
            self._pending_responses.pop(msg_id, None)

    async def handle_response(self, message: dict[str, Any]) -> None:
        """Handle response from extension."""
        msg_id = message.get("id")
        if msg_id and msg_id in self._pending_responses:
            future = self._pending_responses[msg_id]
            if not future.done():
                future.set_result(message)

    # High-level command methods

    async def open_tab(self, url: str) -> dict:
        """Open a new tab with URL."""
        return await self.send_command("OPEN_TAB", {"url": url})

    async def close_tab(self, tab_id: int) -> dict:
        """Close a tab."""
        return await self.send_command("CLOSE_TAB", {"tabId": tab_id})

    async def navigate(self, tab_id: int, url: str) -> dict:
        """Navigate tab to URL."""
        return await self.send_command("NAVIGATE", {"tabId": tab_id, "url": url})

    async def fill_field(self, tab_id: int, selector: str, value: str) -> dict:
        """Fill a form field."""
        return await self.send_command(
            "FILL_FIELD",
            {"tabId": tab_id, "selector": selector, "value": value},
        )

    async def click(self, tab_id: int, selector: str) -> dict:
        """Click an element."""
        return await self.send_command(
            "CLICK",
            {"tabId": tab_id, "selector": selector},
        )

    async def select(self, tab_id: int, selector: str, value: str) -> dict:
        """Select option from dropdown."""
        return await self.send_command(
            "SELECT",
            {"tabId": tab_id, "selector": selector, "value": value},
        )

    async def get_page_state(self, tab_id: int) -> dict:
        """Get current page state."""
        return await self.send_command("GET_PAGE_STATE", {"tabId": tab_id})

    async def get_form_fields(self, tab_id: int) -> dict:
        """Get all form fields on page."""
        return await self.send_command("GET_FORM_FIELDS", {"tabId": tab_id})

    async def screenshot(self, tab_id: int) -> dict:
        """Capture screenshot."""
        return await self.send_command("SCREENSHOT", {"tabId": tab_id})

    async def batch_fill(self, tab_id: int, fields: list[dict]) -> dict:
        """Fill multiple fields in sequence."""
        return await self.send_command(
            "BATCH_FILL",
            {"tabId": tab_id, "fields": fields},
            timeout=60.0,  # Longer timeout for batch operations
        )

    async def wait(self, ms: int = 1000) -> dict:
        """Wait for specified milliseconds."""
        return await self.send_command("WAIT", {"ms": ms})


# Global singleton
_extension_manager: ExtensionConnectionManager | None = None


def get_extension_manager() -> ExtensionConnectionManager:
    """Get the global extension manager instance."""
    global _extension_manager
    if _extension_manager is None:
        _extension_manager = ExtensionConnectionManager()
    return _extension_manager


@router.websocket("/ws/extension")
async def extension_websocket(websocket: WebSocket):
    """WebSocket endpoint for Chrome extension.

    The extension connects here and receives automation commands.
    Responses are sent back through the same connection.
    """
    manager = get_extension_manager()
    await manager.connect(websocket)

    try:
        while True:
            # Receive messages from extension
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            logger.debug(f"Received from extension: {msg_type}")

            if msg_type == "EXTENSION_CONNECTED":
                # Handshake response
                await websocket.send_json(
                    {
                        "type": "HANDSHAKE_ACK",
                        "server": "job-hunter-api",
                        "version": "1.0.0",
                    }
                )

            elif msg_type == "PONG":
                # Ping response - handled by send_command
                await manager.handle_response(data)

            elif msg_type in [
                "TAB_OPENED",
                "TAB_CLOSED",
                "NAVIGATED",
                "FIELD_FILLED",
                "CLICKED",
                "SELECTED",
                "PAGE_STATE",
                "FORM_FIELDS",
                "SCREENSHOT",
                "WAITED",
                "BATCH_FILLED",
                "ERROR",
            ]:
                # Command responses
                await manager.handle_response(data)

            elif msg_type == "PAGE_LOADED":
                # Content script notification
                logger.info(f"Page loaded: {data.get('url')}")

            elif msg_type == "BLOCKER_DETECTED":
                # Blocker detected by content script
                logger.warning(
                    f"Blocker detected: {data.get('blockerType')} on tab {data.get('tabId')}"
                )

            elif msg_type == "FILL_PROGRESS":
                # Batch fill progress notification
                logger.debug(f"Fill progress: {data.get('field')}")

            else:
                logger.warning(f"Unknown message type from extension: {msg_type}")

    except WebSocketDisconnect:
        logger.info("Extension WebSocket disconnected")
    except Exception as e:
        logger.exception(f"Extension WebSocket error: {e}")
    finally:
        await manager.disconnect()


@router.get("/extension/status")
async def extension_status():
    """Check if an extension is currently connected."""
    manager = get_extension_manager()
    return {
        "connected": manager.is_connected,
    }


@router.post("/extension/test")
async def test_extension():
    """Test the extension connection by sending a ping."""
    manager = get_extension_manager()

    if not manager.is_connected:
        return {"success": False, "error": "No extension connected"}

    try:
        response = await manager.send_command("PING", {}, timeout=5.0)
        return {"success": True, "response": response}
    except TimeoutError:
        return {"success": False, "error": "Extension did not respond (timeout)"}
    except Exception as e:
        return {"success": False, "error": str(e)}

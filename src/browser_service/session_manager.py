"""Browser session lifecycle management."""

import asyncio
import logging
import uuid
from datetime import datetime

from src.browser_service.adapters.base import BrowserAdapter
from src.browser_service.adapters.chrome_devtools import ChromeDevToolsAdapter
from src.browser_service.adapters.playwright_adapter import PlaywrightAdapter
from src.browser_service.models import (
    BrowserMode,
    BrowserSession,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionStatus,
)

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages browser session lifecycle.

    Handles creation, tracking, and cleanup of browser sessions.
    Each session has its own browser adapter instance.
    """

    def __init__(self, websocket_base_url: str = "ws://localhost:8001") -> None:
        """Initialize session manager.

        Args:
            websocket_base_url: Base URL for WebSocket connections
        """
        self._sessions: dict[str, BrowserSession] = {}
        self._adapters: dict[str, BrowserAdapter] = {}
        self._websocket_base_url = websocket_base_url
        self._cleanup_task: asyncio.Task | None = None
        self._cleanup_interval = 300  # 5 minutes
        self._session_timeout = 1800  # 30 minutes of inactivity

    async def start(self) -> None:
        """Start the session manager background tasks."""
        logger.info("Starting session manager")
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """Stop the session manager and cleanup all sessions."""
        logger.info("Stopping session manager")

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Close all sessions
        for session_id in list(self._sessions.keys()):
            await self.close_session(session_id)

        logger.info("Session manager stopped")

    async def create_session(self, request: SessionCreateRequest) -> SessionCreateResponse:
        """Create a new browser session.

        Args:
            request: Session configuration

        Returns:
            SessionCreateResponse with session ID and WebSocket URL
        """
        session_id = str(uuid.uuid4())
        logger.info(f"Creating session {session_id} (mode={request.mode})")

        # Create adapter based on mode
        adapter = self._create_adapter(request.mode)

        # Initialize browser
        try:
            await adapter.initialize(request)
        except Exception as e:
            logger.error(f"Failed to initialize browser for session {session_id}: {e}")
            raise RuntimeError(f"Failed to create browser session: {e}")

        # Create session record
        now = datetime.utcnow()
        session = BrowserSession(
            session_id=session_id,
            status=SessionStatus.ACTIVE,
            mode=request.mode,
            created_at=now,
            last_action_at=now,
        )

        # Store session and adapter
        self._sessions[session_id] = session
        self._adapters[session_id] = adapter

        logger.info(f"Session {session_id} created successfully")

        return SessionCreateResponse(
            session_id=session_id,
            status=SessionStatus.ACTIVE,
            mode=request.mode,
            websocket_url=f"{self._websocket_base_url}/ws/{session_id}",
            created_at=now,
        )

    async def close_session(self, session_id: str) -> bool:
        """Close a browser session.

        Args:
            session_id: ID of the session to close

        Returns:
            True if session was closed, False if not found
        """
        if session_id not in self._sessions:
            logger.warning(f"Session {session_id} not found for closing")
            return False

        logger.info(f"Closing session {session_id}")

        # Close browser adapter
        adapter = self._adapters.pop(session_id, None)
        if adapter:
            try:
                await adapter.close()
            except Exception as e:
                logger.error(f"Error closing adapter for session {session_id}: {e}")

        # Update session status
        session = self._sessions.pop(session_id, None)
        if session:
            session.status = SessionStatus.CLOSED

        logger.info(f"Session {session_id} closed")
        return True

    def get_session(self, session_id: str) -> BrowserSession | None:
        """Get session by ID.

        Args:
            session_id: Session ID

        Returns:
            BrowserSession if found, None otherwise
        """
        return self._sessions.get(session_id)

    def get_adapter(self, session_id: str) -> BrowserAdapter | None:
        """Get browser adapter for a session.

        Args:
            session_id: Session ID

        Returns:
            BrowserAdapter if found, None otherwise
        """
        return self._adapters.get(session_id)

    def list_sessions(self) -> list[BrowserSession]:
        """List all active sessions.

        Returns:
            List of active browser sessions
        """
        return list(self._sessions.values())

    def update_session_activity(self, session_id: str) -> None:
        """Update last activity timestamp for a session.

        Args:
            session_id: Session ID
        """
        session = self._sessions.get(session_id)
        if session:
            session.last_action_at = datetime.utcnow()
            session.action_count += 1

    def update_session_url(self, session_id: str, url: str, title: str | None = None) -> None:
        """Update session's current URL and title.

        Args:
            session_id: Session ID
            url: Current page URL
            title: Current page title
        """
        session = self._sessions.get(session_id)
        if session:
            session.current_url = url
            if title:
                session.page_title = title
            session.last_action_at = datetime.utcnow()

    def _create_adapter(self, mode: BrowserMode) -> BrowserAdapter:
        """Create browser adapter based on mode.

        Args:
            mode: Browser mode (playwright or chrome-devtools)

        Returns:
            BrowserAdapter instance

        Modes:
            - PLAYWRIGHT: Direct Playwright library (cloud/headless mode)
            - CHROME_DEVTOOLS: Chrome DevTools MCP (local/assisted mode)
        """
        if mode == BrowserMode.PLAYWRIGHT:
            logger.info("Creating Playwright adapter (cloud mode)")
            return PlaywrightAdapter()
        elif mode == BrowserMode.CHROME_DEVTOOLS:
            logger.info("Creating Chrome DevTools MCP adapter (local mode)")
            return ChromeDevToolsAdapter()
        else:
            raise ValueError(f"Unknown browser mode: {mode}")

    async def _cleanup_loop(self) -> None:
        """Background task to cleanup inactive sessions."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_inactive_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _cleanup_inactive_sessions(self) -> None:
        """Close sessions that have been inactive too long."""
        now = datetime.utcnow()
        inactive_sessions = []

        for session_id, session in self._sessions.items():
            if session.last_action_at:
                inactive_seconds = (now - session.last_action_at).total_seconds()
                if inactive_seconds > self._session_timeout:
                    inactive_sessions.append(session_id)

        for session_id in inactive_sessions:
            logger.info(f"Closing inactive session {session_id}")
            await self.close_session(session_id)


# Global session manager instance
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get the global session manager instance.

    Returns:
        SessionManager instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


async def init_session_manager() -> SessionManager:
    """Initialize and start the global session manager.

    Returns:
        Started SessionManager instance
    """
    manager = get_session_manager()
    await manager.start()
    return manager


async def shutdown_session_manager() -> None:
    """Shutdown the global session manager."""
    global _session_manager
    if _session_manager:
        await _session_manager.stop()
        _session_manager = None

"""Blocker handling and resolution."""

import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel

from src.automation.blockers.detector import DetectedBlocker
from src.automation.client import BrowserServiceClient
from src.config import settings
from src.db.models import BlockerType

logger = logging.getLogger(__name__)


class BlockerResolution(BaseModel):
    """Result of handling a blocker."""

    resolved: bool
    requires_user: bool
    message: str | None = None
    next_action: str | None = None
    screenshot_path: str | None = None


class PausedSession(BaseModel):
    """A paused application session."""

    session_id: str
    job_id: UUID | None = None
    blocker_type: BlockerType
    blocker_message: str
    screenshot_path: str | None = None
    paused_at: datetime
    page_url: str | None = None


class BlockerHandler:
    """Handles detected blockers with appropriate actions.

    For most blockers (CAPTCHA, login required), the handler will:
    1. Take a screenshot for evidence
    2. Pause the session
    3. Notify the user (via return value)
    4. Wait for user to resolve and resume

    Usage:
        handler = BlockerHandler()
        resolution = await handler.handle(blocker, client, session_id)
        if resolution.requires_user:
            # Pause and wait for user
    """

    def __init__(self, screenshot_dir: str | None = None) -> None:
        """Initialize handler.

        Args:
            screenshot_dir: Directory for screenshots
        """
        self.screenshot_dir = Path(screenshot_dir or settings.screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._paused_sessions: dict[str, PausedSession] = {}

    async def handle(
        self,
        blocker: DetectedBlocker,
        client: BrowserServiceClient,
        session_id: str,
        job_id: UUID | None = None,
    ) -> BlockerResolution:
        """Handle a detected blocker.

        Args:
            blocker: Detected blocker
            client: Browser service client
            session_id: Browser session ID
            job_id: Optional job ID

        Returns:
            BlockerResolution indicating next steps
        """
        logger.info(f"Handling blocker: {blocker.type} ({blocker.subtype})")

        if blocker.type == BlockerType.CAPTCHA:
            return await self._handle_captcha(blocker, client, session_id, job_id)
        elif blocker.type == BlockerType.LOGIN_REQUIRED:
            return await self._handle_login(blocker, client, session_id, job_id)
        elif blocker.type == BlockerType.FILE_UPLOAD:
            return await self._handle_file_upload(blocker, client, session_id, job_id)
        elif blocker.type == BlockerType.MULTI_STEP_FORM:
            return await self._handle_multi_step(blocker, client, session_id, job_id)
        elif blocker.type == BlockerType.LOCATION_MISMATCH:
            return await self._handle_location(blocker, client, session_id, job_id)

        return BlockerResolution(
            resolved=False,
            requires_user=True,
            message=f"Unknown blocker type: {blocker.type}",
        )

    async def _handle_captcha(
        self,
        blocker: DetectedBlocker,
        client: BrowserServiceClient,
        session_id: str,
        job_id: UUID | None,
    ) -> BlockerResolution:
        """Handle CAPTCHA blocker.

        CAPTCHAs always require user intervention.
        """
        # Take screenshot
        screenshot_path = await self._take_screenshot(client, session_id, "captcha")

        # Pause session
        page_url = await client.get_current_url()
        self._pause_session(
            session_id=session_id,
            job_id=job_id,
            blocker_type=BlockerType.CAPTCHA,
            message=f"{blocker.subtype or 'Unknown'} CAPTCHA requires manual completion",
            screenshot_path=screenshot_path,
            page_url=page_url,
        )

        return BlockerResolution(
            resolved=False,
            requires_user=True,
            message=f"CAPTCHA detected ({blocker.subtype}). Please complete it manually and resume.",
            next_action="Complete CAPTCHA in browser window, then call resume",
            screenshot_path=screenshot_path,
        )

    async def _handle_login(
        self,
        blocker: DetectedBlocker,
        client: BrowserServiceClient,
        session_id: str,
        job_id: UUID | None,
    ) -> BlockerResolution:
        """Handle login required blocker.

        Login always requires user intervention.
        """
        # Take screenshot
        screenshot_path = await self._take_screenshot(client, session_id, "login")

        # Pause session
        page_url = await client.get_current_url()
        self._pause_session(
            session_id=session_id,
            job_id=job_id,
            blocker_type=BlockerType.LOGIN_REQUIRED,
            message="Platform requires authentication",
            screenshot_path=screenshot_path,
            page_url=page_url,
        )

        return BlockerResolution(
            resolved=False,
            requires_user=True,
            message="Login required. Please log in to the platform and resume.",
            next_action="Log in to the platform in browser window, then call resume",
            screenshot_path=screenshot_path,
        )

    async def _handle_file_upload(
        self,
        blocker: DetectedBlocker,
        client: BrowserServiceClient,
        session_id: str,
        job_id: UUID | None,
    ) -> BlockerResolution:
        """Handle file upload issues.

        Some platforms have file upload restrictions that may require
        manual intervention.
        """
        screenshot_path = await self._take_screenshot(client, session_id, "upload")

        return BlockerResolution(
            resolved=False,
            requires_user=True,
            message="File upload issue detected. Please upload the file manually.",
            next_action="Upload the file in browser window, then call resume",
            screenshot_path=screenshot_path,
        )

    async def _handle_multi_step(
        self,
        blocker: DetectedBlocker,
        client: BrowserServiceClient,
        session_id: str,
        job_id: UUID | None,
    ) -> BlockerResolution:
        """Handle multi-step form complexity.

        Multi-step forms can often be handled automatically,
        but we notify the user about the complexity.
        """
        return BlockerResolution(
            resolved=True,  # Can continue, just informational
            requires_user=False,
            message="Multi-step form detected. Will handle each step.",
            next_action="Continue with multi-step form filling",
        )

    async def _handle_location(
        self,
        blocker: DetectedBlocker,
        client: BrowserServiceClient,
        session_id: str,
        job_id: UUID | None,
    ) -> BlockerResolution:
        """Handle location mismatch warnings.

        Location warnings are informational - user should verify eligibility.
        """
        screenshot_path = await self._take_screenshot(client, session_id, "location")

        return BlockerResolution(
            resolved=False,
            requires_user=True,
            message="Job has location requirements. Please verify your eligibility.",
            next_action="Verify location requirements and decide whether to continue",
            screenshot_path=screenshot_path,
        )

    async def _take_screenshot(
        self,
        client: BrowserServiceClient,
        session_id: str,
        context: str,
    ) -> str | None:
        """Take a screenshot for evidence.

        Args:
            client: Browser service client
            session_id: Session ID
            context: Context for filename (e.g., 'captcha', 'login')

        Returns:
            Path to screenshot or None if failed
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{session_id}_{context}_{timestamp}.png"
            filepath = self.screenshot_dir / filename

            result = await client.screenshot(path=str(filepath))
            if result.success:
                logger.info(f"Screenshot saved: {filepath}")
                return str(filepath)
        except Exception as e:
            logger.warning(f"Failed to take screenshot: {e}")

        return None

    def _pause_session(
        self,
        session_id: str,
        job_id: UUID | None,
        blocker_type: BlockerType,
        message: str,
        screenshot_path: str | None,
        page_url: str | None,
    ) -> None:
        """Record a paused session.

        Args:
            session_id: Browser session ID
            job_id: Job ID
            blocker_type: Type of blocker
            message: Blocker message
            screenshot_path: Path to screenshot
            page_url: Current page URL
        """
        self._paused_sessions[session_id] = PausedSession(
            session_id=session_id,
            job_id=job_id,
            blocker_type=blocker_type,
            blocker_message=message,
            screenshot_path=screenshot_path,
            paused_at=datetime.utcnow(),
            page_url=page_url,
        )
        logger.info(f"Session {session_id} paused: {message}")

    def get_paused_session(self, session_id: str) -> PausedSession | None:
        """Get a paused session by ID.

        Args:
            session_id: Session ID

        Returns:
            PausedSession or None
        """
        return self._paused_sessions.get(session_id)

    def list_paused_sessions(self) -> list[PausedSession]:
        """List all paused sessions.

        Returns:
            List of paused sessions
        """
        return list(self._paused_sessions.values())

    def resume_session(self, session_id: str) -> bool:
        """Mark a session as resumed.

        Args:
            session_id: Session ID

        Returns:
            True if session was paused and is now resumed
        """
        if session_id in self._paused_sessions:
            del self._paused_sessions[session_id]
            logger.info(f"Session {session_id} resumed")
            return True
        return False

    def clear_session(self, session_id: str) -> None:
        """Clear a session from paused list.

        Args:
            session_id: Session ID
        """
        self._paused_sessions.pop(session_id, None)

"""Pause Manager for application session state management.

Handles pause/resume logic for job application automation,
including state persistence, timeout handling, and user interaction.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from src.db.models import ApplicationStatus, BlockerType

logger = logging.getLogger(__name__)


# ============================================================================
# Models
# ============================================================================


class PauseReason(str, Enum):
    """Reason for pausing an application."""

    PRE_SUBMIT_REVIEW = "pre_submit_review"  # Always pause before submit
    CAPTCHA_DETECTED = "captcha_detected"
    LOGIN_REQUIRED = "login_required"
    FILE_UPLOAD_ISSUE = "file_upload_issue"
    MULTI_STEP_FORM = "multi_step_form"
    CUSTOM_QUESTION = "custom_question"
    ERROR = "error"
    USER_REQUESTED = "user_requested"


class ResumeAction(str, Enum):
    """Action to take when resuming."""

    CONTINUE = "continue"  # Continue filling/processing
    SUBMIT = "submit"  # Submit the application
    CANCEL = "cancel"  # Cancel the application
    RETRY = "retry"  # Retry the last action


class PauseState(BaseModel):
    """State of a paused application session."""

    session_id: str
    reason: PauseReason
    message: str | None = None
    browser_session_id: str | None = None
    current_url: str | None = None
    screenshot_path: str | None = None
    fields_filled: dict[str, str] = Field(default_factory=dict)
    current_step: int = 1
    total_steps: int | None = None
    blocker_type: BlockerType | None = None
    paused_at: datetime = Field(default_factory=datetime.utcnow)
    timeout_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResumeResult(BaseModel):
    """Result of a resume operation."""

    success: bool
    action_taken: ResumeAction
    new_status: ApplicationStatus
    message: str | None = None
    error: str | None = None


# ============================================================================
# Pause Manager
# ============================================================================


class PauseManager:
    """Manages pause/resume state for application sessions.

    Features:
    - In-memory state storage (can be extended to Redis/DB)
    - Timeout handling for abandoned sessions
    - Callback support for UI notifications
    - Thread-safe operations
    """

    def __init__(
        self,
        default_timeout_minutes: int = 30,
        cleanup_interval_seconds: int = 60,
    ):
        """Initialize pause manager.

        Args:
            default_timeout_minutes: Default timeout for paused sessions
            cleanup_interval_seconds: Interval for cleanup task
        """
        self._states: dict[str, PauseState] = {}
        self._resume_events: dict[str, asyncio.Event] = {}
        self._resume_actions: dict[str, ResumeAction] = {}
        self._callbacks: list[Callable[[PauseState], Coroutine[Any, Any, None]]] = []
        self._default_timeout = timedelta(minutes=default_timeout_minutes)
        self._cleanup_interval = cleanup_interval_seconds
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the pause manager background tasks."""
        logger.info("Starting pause manager")
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """Stop the pause manager."""
        logger.info("Stopping pause manager")
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    def register_callback(
        self, callback: Callable[[PauseState], Coroutine[Any, Any, None]]
    ) -> None:
        """Register a callback for pause events.

        Args:
            callback: Async function called when a session is paused
        """
        self._callbacks.append(callback)

    async def pause(
        self,
        session_id: str,
        reason: PauseReason,
        message: str | None = None,
        browser_session_id: str | None = None,
        current_url: str | None = None,
        screenshot_path: str | None = None,
        fields_filled: dict[str, str] | None = None,
        current_step: int = 1,
        total_steps: int | None = None,
        blocker_type: BlockerType | None = None,
        timeout_minutes: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PauseState:
        """Pause an application session.

        Args:
            session_id: Unique session identifier
            reason: Reason for pausing
            message: Optional message for user
            browser_session_id: Browser session ID
            current_url: Current page URL
            screenshot_path: Path to screenshot
            fields_filled: Fields filled so far
            current_step: Current step number
            total_steps: Total steps if known
            blocker_type: Type of blocker if any
            timeout_minutes: Custom timeout (uses default if None)
            metadata: Additional metadata

        Returns:
            PauseState object
        """
        timeout = timedelta(minutes=timeout_minutes) if timeout_minutes else self._default_timeout

        state = PauseState(
            session_id=session_id,
            reason=reason,
            message=message,
            browser_session_id=browser_session_id,
            current_url=current_url,
            screenshot_path=screenshot_path,
            fields_filled=fields_filled or {},
            current_step=current_step,
            total_steps=total_steps,
            blocker_type=blocker_type,
            paused_at=datetime.utcnow(),
            timeout_at=datetime.utcnow() + timeout,
            metadata=metadata or {},
        )

        self._states[session_id] = state
        self._resume_events[session_id] = asyncio.Event()

        logger.info(f"Session {session_id} paused: {reason.value} - {message}")

        # Notify callbacks
        for callback in self._callbacks:
            try:
                await callback(state)
            except Exception as e:
                logger.error(f"Pause callback failed: {e}")

        return state

    async def wait_for_resume(
        self,
        session_id: str,
        timeout_seconds: float | None = None,
    ) -> tuple[ResumeAction, PauseState | None]:
        """Wait for a session to be resumed.

        Args:
            session_id: Session to wait for
            timeout_seconds: Custom timeout (uses state timeout if None)

        Returns:
            Tuple of (action taken, current state)
        """
        if session_id not in self._states:
            logger.warning(f"Session {session_id} not found in pause states")
            return ResumeAction.CANCEL, None

        state = self._states[session_id]
        event = self._resume_events.get(session_id)

        if not event:
            return ResumeAction.CANCEL, state

        # Calculate timeout
        if timeout_seconds is not None:
            timeout = timeout_seconds
        elif state.timeout_at:
            remaining = (state.timeout_at - datetime.utcnow()).total_seconds()
            timeout = max(0, remaining)
        else:
            timeout = self._default_timeout.total_seconds()

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            action = self._resume_actions.get(session_id, ResumeAction.CONTINUE)
            return action, self._states.get(session_id)
        except TimeoutError:
            logger.info(f"Session {session_id} timed out while waiting for resume")
            return ResumeAction.CANCEL, state

    def resume(self, session_id: str, action: ResumeAction = ResumeAction.CONTINUE) -> bool:
        """Resume a paused session.

        Args:
            session_id: Session to resume
            action: Action to take

        Returns:
            True if session was resumed, False if not found
        """
        if session_id not in self._states:
            logger.warning(f"Session {session_id} not found for resume")
            return False

        self._resume_actions[session_id] = action
        event = self._resume_events.get(session_id)

        if event:
            event.set()
            logger.info(f"Session {session_id} resumed with action: {action.value}")
            return True

        return False

    def get_state(self, session_id: str) -> PauseState | None:
        """Get the pause state for a session.

        Args:
            session_id: Session ID

        Returns:
            PauseState or None if not found
        """
        return self._states.get(session_id)

    def list_paused_sessions(self) -> list[PauseState]:
        """List all paused sessions.

        Returns:
            List of PauseState objects
        """
        return list(self._states.values())

    def clear_state(self, session_id: str) -> bool:
        """Clear the pause state for a session.

        Args:
            session_id: Session ID

        Returns:
            True if state was cleared, False if not found
        """
        if session_id in self._states:
            del self._states[session_id]
            self._resume_events.pop(session_id, None)
            self._resume_actions.pop(session_id, None)
            logger.info(f"Cleared pause state for session {session_id}")
            return True
        return False

    def is_paused(self, session_id: str) -> bool:
        """Check if a session is paused.

        Args:
            session_id: Session ID

        Returns:
            True if session is paused
        """
        return session_id in self._states

    async def _cleanup_loop(self) -> None:
        """Background task to clean up timed out sessions."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_timed_out()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _cleanup_timed_out(self) -> None:
        """Clean up sessions that have timed out."""
        now = datetime.utcnow()
        timed_out = []

        for session_id, state in self._states.items():
            if state.timeout_at and now > state.timeout_at:
                timed_out.append(session_id)

        for session_id in timed_out:
            logger.info(f"Session {session_id} timed out, cleaning up")
            # Resume with cancel action to trigger cleanup
            self.resume(session_id, ResumeAction.CANCEL)


# ============================================================================
# Global Instance
# ============================================================================

_pause_manager: PauseManager | None = None


def get_pause_manager() -> PauseManager:
    """Get the global pause manager instance.

    Returns:
        PauseManager instance
    """
    global _pause_manager
    if _pause_manager is None:
        _pause_manager = PauseManager()
    return _pause_manager


async def init_pause_manager() -> PauseManager:
    """Initialize and start the global pause manager.

    Returns:
        Started PauseManager instance
    """
    manager = get_pause_manager()
    await manager.start()
    return manager


async def shutdown_pause_manager() -> None:
    """Shutdown the global pause manager."""
    global _pause_manager
    if _pause_manager:
        await _pause_manager.stop()
        _pause_manager = None

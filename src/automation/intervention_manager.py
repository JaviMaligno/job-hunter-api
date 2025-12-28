"""
Intervention Manager for human-in-the-loop job application automation.

Handles cases where automatic processing cannot continue and requires
human intervention (CAPTCHA, login, file upload issues, etc.).
"""

import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# Models
# =============================================================================


class InterventionType(str, Enum):
    """Type of intervention required."""

    CAPTCHA = "captcha"
    LOGIN_REQUIRED = "login_required"
    FILE_UPLOAD = "file_upload"
    CUSTOM_QUESTION = "custom_question"
    MULTI_STEP_FORM = "multi_step_form"
    REVIEW_BEFORE_SUBMIT = "review_before_submit"
    ERROR = "error"
    OTHER = "other"


class InterventionStatus(str, Enum):
    """Status of an intervention request."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class InterventionRequest(BaseModel):
    """A request for human intervention."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    job_id: str | None = None
    user_id: str

    intervention_type: InterventionType
    status: InterventionStatus = InterventionStatus.PENDING

    title: str
    description: str
    instructions: str | None = None

    # Context
    current_url: str | None = None
    screenshot_base64: str | None = None
    screenshot_path: str | None = None
    fields_filled: dict[str, str] = Field(default_factory=dict)
    fields_remaining: list[str] = Field(default_factory=list)

    # CAPTCHA specific
    captcha_type: str | None = None  # turnstile, hcaptcha, recaptcha
    captcha_sitekey: str | None = None
    captcha_solve_attempted: bool = False
    captcha_solve_error: str | None = None

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    timeout_at: datetime | None = None
    resolved_at: datetime | None = None

    # Resolution
    resolution_action: str | None = None  # continue, submit, cancel, retry
    resolution_notes: str | None = None

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)


class InterventionResolution(BaseModel):
    """Resolution of an intervention."""

    action: str  # continue, submit, cancel, retry
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Intervention Manager
# =============================================================================


class InterventionManager:
    """
    Manages intervention requests for job application automation.

    Features:
    - Create and track intervention requests
    - WebSocket notification support via callbacks
    - Timeout handling for abandoned interventions
    - Resolution tracking
    """

    def __init__(
        self,
        default_timeout_minutes: int = 30,
        cleanup_interval_seconds: int = 60,
    ):
        """
        Initialize intervention manager.

        Args:
            default_timeout_minutes: Default timeout for interventions
            cleanup_interval_seconds: Interval for cleanup task
        """
        self._interventions: dict[str, InterventionRequest] = {}
        self._resolution_events: dict[str, asyncio.Event] = {}
        self._resolutions: dict[str, InterventionResolution] = {}

        self._callbacks: list[Callable[[InterventionRequest], Coroutine[Any, Any, None]]] = []
        self._resolution_callbacks: list[
            Callable[[InterventionRequest, InterventionResolution], Coroutine[Any, Any, None]]
        ] = []

        self._default_timeout = timedelta(minutes=default_timeout_minutes)
        self._cleanup_interval = cleanup_interval_seconds
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start background tasks."""
        logger.info("Starting intervention manager")
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """Stop background tasks."""
        logger.info("Stopping intervention manager")
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    def on_intervention(
        self,
        callback: Callable[[InterventionRequest], Coroutine[Any, Any, None]],
    ) -> None:
        """Register callback for new interventions."""
        self._callbacks.append(callback)

    def on_resolution(
        self,
        callback: Callable[
            [InterventionRequest, InterventionResolution], Coroutine[Any, Any, None]
        ],
    ) -> None:
        """Register callback for intervention resolutions."""
        self._resolution_callbacks.append(callback)

    async def request_intervention(
        self,
        session_id: str,
        user_id: str,
        intervention_type: InterventionType,
        title: str,
        description: str,
        job_id: str | None = None,
        instructions: str | None = None,
        current_url: str | None = None,
        screenshot_base64: str | None = None,
        screenshot_path: str | None = None,
        fields_filled: dict[str, str] | None = None,
        fields_remaining: list[str] | None = None,
        captcha_type: str | None = None,
        captcha_sitekey: str | None = None,
        captcha_solve_attempted: bool = False,
        captcha_solve_error: str | None = None,
        timeout_minutes: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> InterventionRequest:
        """
        Create a new intervention request.

        Args:
            session_id: Application session ID
            user_id: User ID
            intervention_type: Type of intervention needed
            title: Short title for the intervention
            description: Detailed description
            job_id: Optional job ID
            instructions: Instructions for the user
            current_url: Current page URL
            screenshot_base64: Screenshot as base64 (optional)
            screenshot_path: Path to screenshot file
            fields_filled: Fields already filled
            fields_remaining: Fields still needing input
            captcha_type: Type of CAPTCHA (if applicable)
            captcha_sitekey: CAPTCHA sitekey (if applicable)
            captcha_solve_attempted: Whether auto-solve was attempted
            captcha_solve_error: Error from auto-solve attempt
            timeout_minutes: Custom timeout
            metadata: Additional metadata

        Returns:
            InterventionRequest object
        """
        timeout = timedelta(minutes=timeout_minutes) if timeout_minutes else self._default_timeout

        intervention = InterventionRequest(
            session_id=session_id,
            user_id=user_id,
            job_id=job_id,
            intervention_type=intervention_type,
            title=title,
            description=description,
            instructions=instructions,
            current_url=current_url,
            screenshot_base64=screenshot_base64,
            screenshot_path=screenshot_path,
            fields_filled=fields_filled or {},
            fields_remaining=fields_remaining or [],
            captcha_type=captcha_type,
            captcha_sitekey=captcha_sitekey,
            captcha_solve_attempted=captcha_solve_attempted,
            captcha_solve_error=captcha_solve_error,
            timeout_at=datetime.utcnow() + timeout,
            metadata=metadata or {},
        )

        self._interventions[intervention.id] = intervention
        self._resolution_events[intervention.id] = asyncio.Event()

        logger.info(
            f"Intervention requested: {intervention.id} "
            f"({intervention_type.value}) for session {session_id}"
        )

        # Notify callbacks
        for callback in self._callbacks:
            try:
                await callback(intervention)
            except Exception as e:
                logger.error(f"Intervention callback failed: {e}")

        return intervention

    async def wait_for_resolution(
        self,
        intervention_id: str,
        timeout_seconds: float | None = None,
    ) -> tuple[InterventionResolution | None, InterventionRequest | None]:
        """
        Wait for an intervention to be resolved.

        Args:
            intervention_id: Intervention to wait for
            timeout_seconds: Custom timeout

        Returns:
            Tuple of (resolution, updated intervention) or (None, intervention) on timeout
        """
        if intervention_id not in self._interventions:
            logger.warning(f"Intervention {intervention_id} not found")
            return None, None

        intervention = self._interventions[intervention_id]
        event = self._resolution_events.get(intervention_id)

        if not event:
            return None, intervention

        # Calculate timeout
        if timeout_seconds is not None:
            timeout = timeout_seconds
        elif intervention.timeout_at:
            remaining = (intervention.timeout_at - datetime.utcnow()).total_seconds()
            timeout = max(0, remaining)
        else:
            timeout = self._default_timeout.total_seconds()

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            resolution = self._resolutions.get(intervention_id)
            return resolution, self._interventions.get(intervention_id)
        except TimeoutError:
            logger.info(f"Intervention {intervention_id} timed out")
            intervention.status = InterventionStatus.TIMED_OUT
            return None, intervention

    async def resolve(
        self,
        intervention_id: str,
        action: str,
        notes: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Resolve an intervention.

        Args:
            intervention_id: Intervention to resolve
            action: Resolution action (continue, submit, cancel, retry)
            notes: Optional notes
            metadata: Additional metadata

        Returns:
            True if resolved, False if not found
        """
        if intervention_id not in self._interventions:
            logger.warning(f"Intervention {intervention_id} not found")
            return False

        intervention = self._interventions[intervention_id]
        intervention.status = InterventionStatus.RESOLVED
        intervention.resolved_at = datetime.utcnow()
        intervention.resolution_action = action
        intervention.resolution_notes = notes

        resolution = InterventionResolution(
            action=action,
            notes=notes,
            metadata=metadata or {},
        )
        self._resolutions[intervention_id] = resolution

        # Signal waiting tasks
        event = self._resolution_events.get(intervention_id)
        if event:
            event.set()

        logger.info(f"Intervention {intervention_id} resolved with action: {action}")

        # Notify resolution callbacks
        for callback in self._resolution_callbacks:
            try:
                await callback(intervention, resolution)
            except Exception as e:
                logger.error(f"Resolution callback failed: {e}")

        return True

    def get_intervention(self, intervention_id: str) -> InterventionRequest | None:
        """Get an intervention by ID."""
        return self._interventions.get(intervention_id)

    def get_pending_interventions(
        self,
        user_id: str | None = None,
    ) -> list[InterventionRequest]:
        """
        Get pending interventions.

        Args:
            user_id: Filter by user ID (optional)

        Returns:
            List of pending interventions
        """
        pending = [
            i for i in self._interventions.values() if i.status == InterventionStatus.PENDING
        ]

        if user_id:
            pending = [i for i in pending if i.user_id == user_id]

        return sorted(pending, key=lambda i: i.created_at, reverse=True)

    def get_interventions_for_session(
        self,
        session_id: str,
    ) -> list[InterventionRequest]:
        """Get all interventions for a session."""
        return [i for i in self._interventions.values() if i.session_id == session_id]

    async def cancel(self, intervention_id: str) -> bool:
        """Cancel an intervention."""
        if intervention_id not in self._interventions:
            return False

        intervention = self._interventions[intervention_id]
        intervention.status = InterventionStatus.CANCELLED

        # Signal waiting tasks
        event = self._resolution_events.get(intervention_id)
        if event:
            event.set()

        logger.info(f"Intervention {intervention_id} cancelled")
        return True

    async def _cleanup_loop(self) -> None:
        """Background task to clean up timed-out interventions."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_timed_out()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

    async def _cleanup_timed_out(self) -> None:
        """Mark timed-out interventions."""
        now = datetime.utcnow()
        timed_out = []

        for intervention in self._interventions.values():
            if (
                intervention.status == InterventionStatus.PENDING
                and intervention.timeout_at
                and intervention.timeout_at < now
            ):
                timed_out.append(intervention.id)

        for intervention_id in timed_out:
            intervention = self._interventions[intervention_id]
            intervention.status = InterventionStatus.TIMED_OUT
            logger.info(f"Intervention {intervention_id} timed out during cleanup")

            # Signal waiting tasks
            event = self._resolution_events.get(intervention_id)
            if event:
                event.set()


# =============================================================================
# Singleton instance
# =============================================================================

_intervention_manager: InterventionManager | None = None


def get_intervention_manager() -> InterventionManager:
    """Get the global intervention manager instance."""
    global _intervention_manager
    if _intervention_manager is None:
        _intervention_manager = InterventionManager()
    return _intervention_manager

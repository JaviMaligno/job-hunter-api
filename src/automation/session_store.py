"""
Session persistence for job application automation.

Stores session state to allow resume after:
- Browser close/crash
- Server restart
- Network interruption
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.db.models import ApplicationMode, ApplicationStatus, BlockerType

logger = logging.getLogger(__name__)


class SessionState(BaseModel):
    """Persistable session state."""

    session_id: str
    user_id: str = "default"
    job_url: str
    status: ApplicationStatus = ApplicationStatus.PENDING
    mode: ApplicationMode = ApplicationMode.ASSISTED

    # Progress tracking
    current_step: int = 1
    total_steps: int | None = None
    steps_completed: list[str] = Field(default_factory=list)

    # Form state
    fields_filled: dict[str, str] = Field(default_factory=dict)
    fields_remaining: list[str] = Field(default_factory=list)

    # Blocker info
    blocker_type: BlockerType | None = None
    blocker_message: str | None = None
    intervention_id: str | None = None

    # Browser state
    browser_session_id: str | None = None
    current_url: str | None = None
    cookies: list[dict[str, Any]] = Field(default_factory=list)
    local_storage: dict[str, str] = Field(default_factory=dict)

    # User data (for resume)
    user_data_json: str | None = None
    cv_content: str | None = None
    cv_file_path: str | None = None
    cover_letter: str | None = None

    # Error tracking
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 3

    # Screenshots
    last_screenshot_path: str | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    paused_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        use_enum_values = True


class SessionStore:
    """
    File-based session store for persistence.

    Stores sessions as JSON files in a directory.
    Could be extended to use SQLite or Redis.
    """

    def __init__(self, storage_dir: str | Path = "data/sessions"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, SessionState] = {}
        logger.info(f"Session store initialized at {self.storage_dir}")

    def _session_path(self, session_id: str) -> Path:
        """Get file path for a session."""
        return self.storage_dir / f"{session_id}.json"

    async def save(self, session: SessionState) -> bool:
        """
        Save session state to disk.

        Args:
            session: Session state to persist

        Returns:
            True if saved successfully
        """
        try:
            session.updated_at = datetime.utcnow()
            path = self._session_path(session.session_id)

            # Write to disk
            with open(path, "w", encoding="utf-8") as f:
                json.dump(session.model_dump(mode="json"), f, indent=2, default=str)

            # Update cache
            self._cache[session.session_id] = session

            logger.debug(f"Session {session.session_id} saved")
            return True

        except Exception as e:
            logger.error(f"Failed to save session {session.session_id}: {e}")
            return False

    async def load(self, session_id: str) -> SessionState | None:
        """
        Load session state from disk.

        Args:
            session_id: Session to load

        Returns:
            SessionState if found, None otherwise
        """
        # Check cache first
        if session_id in self._cache:
            return self._cache[session_id]

        try:
            path = self._session_path(session_id)
            if not path.exists():
                return None

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Parse dates
            for date_field in ["created_at", "updated_at", "paused_at", "completed_at"]:
                if data.get(date_field):
                    data[date_field] = datetime.fromisoformat(data[date_field])

            session = SessionState(**data)
            self._cache[session_id] = session

            logger.debug(f"Session {session_id} loaded from disk")
            return session

        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None

    async def delete(self, session_id: str) -> bool:
        """Delete a session."""
        try:
            path = self._session_path(session_id)
            if path.exists():
                path.unlink()

            if session_id in self._cache:
                del self._cache[session_id]

            logger.info(f"Session {session_id} deleted")
            return True

        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    async def list_sessions(
        self,
        status: ApplicationStatus | None = None,
        user_id: str | None = None,
    ) -> list[SessionState]:
        """
        List all sessions, optionally filtered.

        Args:
            status: Filter by status
            user_id: Filter by user

        Returns:
            List of matching sessions
        """
        sessions = []

        for path in self.storage_dir.glob("*.json"):
            try:
                session = await self.load(path.stem)
                if session:
                    if status and session.status != status:
                        continue
                    if user_id and session.user_id != user_id:
                        continue
                    sessions.append(session)
            except Exception as e:
                logger.warning(f"Failed to load session from {path}: {e}")

        return sorted(sessions, key=lambda s: s.created_at, reverse=True)

    async def list_resumable(self, user_id: str | None = None) -> list[SessionState]:
        """
        List sessions that can be resumed.

        A session is resumable if:
        - Status is PAUSED or NEEDS_INTERVENTION
        - Has browser state (cookies, URL)
        - Not expired (< 24 hours old)
        """
        sessions = await self.list_sessions(user_id=user_id)
        resumable = []

        cutoff = datetime.utcnow()

        for session in sessions:
            # Check status
            if session.status not in [
                ApplicationStatus.PAUSED,
                ApplicationStatus.NEEDS_INTERVENTION,
            ]:
                continue

            # Check age (sessions expire after 24 hours)
            if session.paused_at:
                age_hours = (cutoff - session.paused_at).total_seconds() / 3600
                if age_hours > 24:
                    continue

            # Has some state to resume from
            if session.current_url or session.cookies:
                resumable.append(session)

        return resumable

    async def update_status(
        self,
        session_id: str,
        status: ApplicationStatus,
        error: str | None = None,
    ) -> bool:
        """Update just the status of a session."""
        session = await self.load(session_id)
        if not session:
            return False

        session.status = status
        if error:
            session.error = error

        if status == ApplicationStatus.PAUSED:
            session.paused_at = datetime.utcnow()
        elif status in [ApplicationStatus.SUBMITTED, ApplicationStatus.FAILED]:
            session.completed_at = datetime.utcnow()

        return await self.save(session)

    async def update_progress(
        self,
        session_id: str,
        step: str,
        fields_filled: dict[str, str] | None = None,
        current_url: str | None = None,
    ) -> bool:
        """Update progress of a session."""
        session = await self.load(session_id)
        if not session:
            return False

        if step and step not in session.steps_completed:
            session.steps_completed.append(step)
            session.current_step = len(session.steps_completed)

        if fields_filled:
            session.fields_filled.update(fields_filled)

        if current_url:
            session.current_url = current_url

        return await self.save(session)

    async def save_browser_state(
        self,
        session_id: str,
        cookies: list[dict[str, Any]],
        local_storage: dict[str, str] | None = None,
        current_url: str | None = None,
    ) -> bool:
        """Save browser state for later restoration."""
        session = await self.load(session_id)
        if not session:
            return False

        session.cookies = cookies
        if local_storage:
            session.local_storage = local_storage
        if current_url:
            session.current_url = current_url

        return await self.save(session)

    async def cleanup_old_sessions(self, max_age_hours: int = 48) -> int:
        """
        Clean up old completed/failed sessions.

        Returns number of sessions deleted.
        """
        sessions = await self.list_sessions()
        deleted = 0
        cutoff = datetime.utcnow()

        for session in sessions:
            # Only clean up terminal states
            if session.status not in [
                ApplicationStatus.SUBMITTED,
                ApplicationStatus.FAILED,
                ApplicationStatus.CANCELLED,
            ]:
                continue

            # Check age
            check_time = session.completed_at or session.updated_at
            age_hours = (cutoff - check_time).total_seconds() / 3600

            if age_hours > max_age_hours:
                if await self.delete(session.session_id):
                    deleted += 1

        if deleted:
            logger.info(f"Cleaned up {deleted} old sessions")

        return deleted


# Global singleton
_session_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Get the global session store instance."""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store

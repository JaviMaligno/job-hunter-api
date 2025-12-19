"""Rate limiting service for application submissions."""

from datetime import datetime, timedelta
from typing import Dict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import Application, ApplicationMode, ApplicationStatus


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, limit: int, period: str, reset_at: datetime):
        self.limit = limit
        self.period = period
        self.reset_at = reset_at
        super().__init__(
            f"Rate limit exceeded: {limit} applications per {period}. "
            f"Resets at {reset_at.isoformat()}"
        )


class RateLimiter:
    """Rate limiter for application submissions.

    Enforces per-user, per-mode daily limits:
    - SEMI_AUTO + AUTO combined: max_applications_per_day (10)
    - AUTO only: max_auto_applications_per_day (5)
    - ASSISTED: No limit (user is in control)
    """

    async def check_limit(
        self,
        db: AsyncSession,
        user_id: UUID,
        mode: ApplicationMode,
    ) -> None:
        """Check if user can submit an application in the given mode.

        Args:
            db: Database session
            user_id: User ID
            mode: Application mode

        Raises:
            RateLimitExceeded: If rate limit exceeded
        """
        if mode == ApplicationMode.ASSISTED:
            # No limit for assisted mode (user is in control)
            return

        today_start = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        tomorrow_start = today_start + timedelta(days=1)

        # Count today's automated applications (SEMI_AUTO + AUTO)
        query = (
            select(func.count(Application.id))
            .where(Application.user_id == user_id)
            .where(
                Application.mode.in_([ApplicationMode.SEMI_AUTO, ApplicationMode.AUTO])
            )
            .where(Application.status == ApplicationStatus.SUBMITTED)
            .where(Application.completed_at >= today_start)
            .where(Application.completed_at < tomorrow_start)
        )
        total_auto_count = await db.scalar(query) or 0

        # Check total automated limit
        if total_auto_count >= settings.max_applications_per_day:
            raise RateLimitExceeded(
                limit=settings.max_applications_per_day,
                period="day",
                reset_at=tomorrow_start,
            )

        # If mode is AUTO, check AUTO-specific limit
        if mode == ApplicationMode.AUTO:
            query = (
                select(func.count(Application.id))
                .where(Application.user_id == user_id)
                .where(Application.mode == ApplicationMode.AUTO)
                .where(Application.status == ApplicationStatus.SUBMITTED)
                .where(Application.completed_at >= today_start)
                .where(Application.completed_at < tomorrow_start)
            )
            auto_count = await db.scalar(query) or 0

            if auto_count >= settings.max_auto_applications_per_day:
                raise RateLimitExceeded(
                    limit=settings.max_auto_applications_per_day,
                    period="day (AUTO mode)",
                    reset_at=tomorrow_start,
                )

    async def get_usage(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> Dict[str, int | str]:
        """Get current rate limit usage for a user.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Dict with counts and limits
        """
        today_start = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        tomorrow_start = today_start + timedelta(days=1)

        # Count automated applications
        query = (
            select(func.count(Application.id))
            .where(Application.user_id == user_id)
            .where(
                Application.mode.in_([ApplicationMode.SEMI_AUTO, ApplicationMode.AUTO])
            )
            .where(Application.status == ApplicationStatus.SUBMITTED)
            .where(Application.completed_at >= today_start)
            .where(Application.completed_at < tomorrow_start)
        )
        total_auto = await db.scalar(query) or 0

        # Count AUTO only
        query = (
            select(func.count(Application.id))
            .where(Application.user_id == user_id)
            .where(Application.mode == ApplicationMode.AUTO)
            .where(Application.status == ApplicationStatus.SUBMITTED)
            .where(Application.completed_at >= today_start)
            .where(Application.completed_at < tomorrow_start)
        )
        auto_only = await db.scalar(query) or 0

        return {
            "total_automated_today": total_auto,
            "max_automated_per_day": settings.max_applications_per_day,
            "auto_mode_today": auto_only,
            "max_auto_per_day": settings.max_auto_applications_per_day,
            "remaining_automated": settings.max_applications_per_day - total_auto,
            "remaining_auto": settings.max_auto_applications_per_day - auto_only,
            "resets_at": tomorrow_start.isoformat(),
        }


# Singleton instance
rate_limiter = RateLimiter()

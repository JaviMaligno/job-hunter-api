"""Application repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Application, ApplicationStatus
from src.db.repositories.base import BaseRepository


class ApplicationRepository(BaseRepository[Application]):
    """Repository for Application operations.

    Extends BaseRepository with application-specific queries like
    finding by job and completing applications.
    """

    def __init__(self, db: AsyncSession):
        """Initialize application repository.

        Args:
            db: Database session
        """
        super().__init__(Application, db)

    async def get_by_job(self, job_id: UUID) -> list[Application]:
        """Get all applications for a job.

        Args:
            job_id: Job ID

        Returns:
            List of applications for the job, ordered by most recent first
        """
        result = await self.db.execute(
            select(Application)
            .where(Application.job_id == job_id)
            .order_by(Application.started_at.desc())
        )
        return list(result.scalars().all())

    async def complete(
        self,
        application_id: UUID,
        status: ApplicationStatus,
        form_fields_filled: dict | None = None,
        form_questions_answered: list | None = None,
        error_message: str | None = None,
    ) -> Application | None:
        """Mark application as completed with results.

        Args:
            application_id: Application ID
            status: Final status (SUBMITTED, FAILED, etc.)
            form_fields_filled: Dict of filled form fields
            form_questions_answered: List of answered questions
            error_message: Error message if failed

        Returns:
            Updated application if found, None otherwise
        """
        app = await self.get(application_id)
        if not app:
            return None

        app.status = status
        app.completed_at = datetime.utcnow()

        if form_fields_filled:
            app.form_fields_filled = form_fields_filled
        if form_questions_answered:
            app.form_questions_answered = form_questions_answered
        if error_message:
            app.error_message = error_message

        await self.db.flush()
        await self.db.refresh(app)
        return app

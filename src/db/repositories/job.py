"""Job repository."""

from typing import Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Job, JobStatus
from src.db.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    """Repository for Job operations.

    Extends BaseRepository with job-specific queries like filtering
    by user and status.
    """

    def __init__(self, db: AsyncSession):
        """Initialize job repository.

        Args:
            db: Database session
        """
        super().__init__(Job, db)

    async def get_by_user(
        self,
        user_id: UUID,
        status: JobStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[list[Job], int]:
        """Get jobs for a user with optional status filter.

        Args:
            user_id: User ID
            status: Optional status filter
            skip: Number of jobs to skip
            limit: Maximum number of jobs to return

        Returns:
            Tuple of (jobs list, total count)
        """
        query = select(Job).where(Job.user_id == user_id)

        if status:
            query = query.where(Job.status == status)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query) or 0

        # Get paginated results
        query = query.offset(skip).limit(limit).order_by(Job.created_at.desc())
        result = await self.db.execute(query)
        jobs = list(result.scalars().all())

        return jobs, total

    async def update_status(
        self,
        job_id: UUID,
        status: JobStatus,
        blocker_type=None,
        blocker_details=None,
    ) -> Job | None:
        """Update job status and optionally blocker info.

        Args:
            job_id: Job ID
            status: New status
            blocker_type: Optional blocker type
            blocker_details: Optional blocker details

        Returns:
            Updated job if found, None otherwise
        """
        job = await self.get(job_id)
        if not job:
            return None

        job.status = status
        if blocker_type is not None:
            job.blocker_type = blocker_type
        if blocker_details is not None:
            job.blocker_details = blocker_details

        await self.db.flush()
        await self.db.refresh(job)
        return job

    async def search(
        self,
        user_id: UUID,
        query: str | None = None,
        status: JobStatus | None = None,
        company: str | None = None,
        location: str | None = None,
        min_match_score: int | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[list[Job], int]:
        """Search jobs with filters.

        Args:
            user_id: User ID
            query: Text search query (searches title, company, location, description)
            status: Filter by status
            company: Filter by company name (partial match)
            location: Filter by location (partial match)
            min_match_score: Minimum match score filter
            skip: Number of jobs to skip
            limit: Maximum number of jobs to return

        Returns:
            Tuple of (jobs list, total count)
        """
        base_query = select(Job).where(Job.user_id == user_id)

        # Text search across multiple fields
        if query:
            search_pattern = f"%{query}%"
            base_query = base_query.where(
                (Job.title.ilike(search_pattern))
                | (Job.company.ilike(search_pattern))
                | (Job.location.ilike(search_pattern))
                | (Job.description_raw.ilike(search_pattern))
            )

        # Status filter
        if status:
            base_query = base_query.where(Job.status == status)

        # Company filter
        if company:
            base_query = base_query.where(Job.company.ilike(f"%{company}%"))

        # Location filter
        if location:
            base_query = base_query.where(Job.location.ilike(f"%{location}%"))

        # Match score filter
        if min_match_score is not None:
            base_query = base_query.where(Job.match_score >= min_match_score)

        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        total = await self.db.scalar(count_query) or 0

        # Get paginated results
        base_query = base_query.offset(skip).limit(limit).order_by(Job.created_at.desc())
        result = await self.db.execute(base_query)
        jobs = list(result.scalars().all())

        return jobs, total

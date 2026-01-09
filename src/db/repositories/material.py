"""Material repository."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Material, MaterialType
from src.db.repositories.base import BaseRepository


class MaterialRepository(BaseRepository[Material]):
    """Repository for Material operations.

    Extends BaseRepository with material-specific queries like filtering
    by job, user, and material type.
    """

    def __init__(self, db: AsyncSession):
        """Initialize material repository.

        Args:
            db: Database session
        """
        super().__init__(Material, db)

    async def get_by_job(
        self,
        job_id: UUID,
        material_type: MaterialType | None = None,
        current_only: bool = True,
    ) -> list[Material]:
        """Get materials for a job.

        Args:
            job_id: Job ID
            material_type: Optional filter by material type
            current_only: If True, only return current versions

        Returns:
            List of materials
        """
        query = select(Material).where(Material.job_id == job_id)

        if material_type:
            query = query.where(Material.material_type == material_type)

        if current_only:
            query = query.where(Material.is_current == True)  # noqa: E712

        query = query.order_by(Material.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_user(
        self,
        user_id: UUID,
        material_type: MaterialType | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Material]:
        """Get materials for a user.

        Args:
            user_id: User ID
            material_type: Optional filter by material type
            skip: Number of items to skip
            limit: Maximum number of items to return

        Returns:
            List of materials
        """
        query = select(Material).where(Material.user_id == user_id)

        if material_type:
            query = query.where(Material.material_type == material_type)

        query = (
            query.where(Material.is_current == True)  # noqa: E712
            .offset(skip)
            .limit(limit)
            .order_by(Material.created_at.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_current_version(
        self,
        job_id: UUID,
        material_type: MaterialType,
    ) -> Material | None:
        """Get the current version of a specific material type for a job.

        Args:
            job_id: Job ID
            material_type: Material type

        Returns:
            Current material or None
        """
        query = (
            select(Material)
            .where(Material.job_id == job_id)
            .where(Material.material_type == material_type)
            .where(Material.is_current == True)  # noqa: E712
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_new_version(
        self,
        job_id: UUID,
        user_id: UUID,
        material_type: MaterialType,
        content: str,
        changes_made: list[str] | None = None,
        changes_explanation: str | None = None,
        langfuse_trace_id: str | None = None,
    ) -> Material:
        """Create a new version of a material, marking previous as non-current.

        Args:
            job_id: Job ID
            user_id: User ID
            material_type: Material type
            content: Material content
            changes_made: List of changes made
            changes_explanation: Explanation of changes
            langfuse_trace_id: Optional Langfuse trace ID

        Returns:
            New material
        """
        # Get current version number
        current = await self.get_current_version(job_id, material_type)
        new_version = (current.version + 1) if current else 1

        # Mark previous versions as non-current
        if current:
            stmt = (
                update(Material)
                .where(Material.job_id == job_id)
                .where(Material.material_type == material_type)
                .values(is_current=False)
            )
            await self.db.execute(stmt)

        # Create new material
        material = Material(
            job_id=job_id,
            user_id=user_id,
            material_type=material_type,
            content=content,
            changes_made=changes_made,
            changes_explanation=changes_explanation,
            version=new_version,
            is_current=True,
            langfuse_trace_id=langfuse_trace_id,
        )

        self.db.add(material)
        await self.db.flush()
        await self.db.refresh(material)
        return material

    async def get_all_versions(
        self,
        job_id: UUID,
        material_type: MaterialType,
    ) -> list[Material]:
        """Get all versions of a material for a job.

        Args:
            job_id: Job ID
            material_type: Material type

        Returns:
            List of all versions, newest first
        """
        query = (
            select(Material)
            .where(Material.job_id == job_id)
            .where(Material.material_type == material_type)
            .order_by(Material.version.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

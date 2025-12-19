"""Base repository with common CRUD operations."""

from typing import Generic, List, Type, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository with common CRUD operations.

    Provides standard database operations for any SQLAlchemy model.
    Subclasses can extend with model-specific queries.

    Example:
        class UserRepository(BaseRepository[User]):
            def __init__(self, db: AsyncSession):
                super().__init__(User, db)

            async def get_by_email(self, email: str) -> User | None:
                result = await self.db.execute(
                    select(User).where(User.email == email)
                )
                return result.scalar_one_or_none()
    """

    def __init__(self, model: Type[ModelType], db: AsyncSession):
        """Initialize repository.

        Args:
            model: SQLAlchemy model class
            db: Database session
        """
        self.model = model
        self.db = db

    async def get(self, id: UUID) -> ModelType | None:
        """Get entity by ID.

        Args:
            id: Entity ID

        Returns:
            Entity if found, None otherwise
        """
        result = await self.db.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> List[ModelType]:
        """Get multiple entities with pagination.

        Args:
            skip: Number of entities to skip
            limit: Maximum number of entities to return

        Returns:
            List of entities
        """
        result = await self.db.execute(
            select(self.model).offset(skip).limit(limit).order_by(self.model.id)
        )
        return list(result.scalars().all())

    async def create(self, **kwargs) -> ModelType:
        """Create new entity.

        Args:
            **kwargs: Entity attributes

        Returns:
            Created entity
        """
        obj = self.model(**kwargs)
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def update(self, id: UUID, **kwargs) -> ModelType | None:
        """Update entity.

        Args:
            id: Entity ID
            **kwargs: Attributes to update (only non-None values)

        Returns:
            Updated entity if found, None otherwise
        """
        obj = await self.get(id)
        if not obj:
            return None

        for key, value in kwargs.items():
            if value is not None and hasattr(obj, key):
                setattr(obj, key, value)

        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, id: UUID) -> bool:
        """Delete entity.

        Args:
            id: Entity ID

        Returns:
            True if deleted, False if not found
        """
        obj = await self.get(id)
        if not obj:
            return False

        await self.db.delete(obj)
        await self.db.flush()
        return True

"""User repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.db.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User operations.

    Extends BaseRepository with user-specific queries like finding by email.
    """

    def __init__(self, db: AsyncSession):
        """Initialize user repository.

        Args:
            db: Database session
        """
        super().__init__(User, db)

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email address.

        Args:
            email: User's email address

        Returns:
            User if found, None otherwise
        """
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

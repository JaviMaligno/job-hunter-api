"""User-related API routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from src.api.schemas import UserCreate, UserResponse, UserUpdate

router = APIRouter()


@router.post("/", response_model=UserResponse)
async def create_user(user: UserCreate):
    """
    Create a new user profile.

    TODO: Implement with database integration.
    """
    raise HTTPException(
        status_code=501,
        detail="Database integration coming soon",
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID):
    """
    Get user profile by ID.

    TODO: Implement with database integration.
    """
    raise HTTPException(
        status_code=501,
        detail="Database integration coming soon",
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: UUID, user: UserUpdate):
    """
    Update user profile.

    TODO: Implement with database integration.
    """
    raise HTTPException(
        status_code=501,
        detail="Database integration coming soon",
    )


@router.post("/{user_id}/cv")
async def upload_cv(user_id: UUID):
    """
    Upload base CV for a user.

    Accepts PDF, DOCX, or plain text.

    TODO: Implement with file handling.
    """
    raise HTTPException(
        status_code=501,
        detail="CV upload coming soon",
    )


@router.get("/{user_id}/preferences")
async def get_preferences(user_id: UUID):
    """
    Get user job preferences.

    TODO: Implement with database integration.
    """
    raise HTTPException(
        status_code=501,
        detail="Database integration coming soon",
    )


@router.put("/{user_id}/preferences")
async def update_preferences(user_id: UUID):
    """
    Update user job preferences.

    TODO: Implement with database integration.
    """
    raise HTTPException(
        status_code=501,
        detail="Database integration coming soon",
    )

"""User-related API routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm.attributes import flag_modified

from src.api.dependencies import DbDep
from src.api.schemas import (
    EmailSender,
    EmailSenderPreferences,
    EmailSenderPreferencesResponse,
    EmailSenderPreferencesUpdate,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from src.config import DEFAULT_JOB_EMAIL_SENDERS
from src.db.repositories.user import UserRepository

router = APIRouter()


@router.post("/", response_model=UserResponse)
async def create_user(user: UserCreate, db: DbDep):
    """Create a new user profile."""
    repo = UserRepository(db)

    # Check if email already exists
    existing = await repo.get_by_email(user.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = await repo.create(**user.model_dump())
    return new_user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, db: DbDep):
    """Get user profile by ID."""
    repo = UserRepository(db)
    user = await repo.get(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: UUID, user: UserUpdate, db: DbDep):
    """Update user profile."""
    repo = UserRepository(db)
    updated = await repo.update(user_id, **user.model_dump(exclude_unset=True))

    if not updated:
        raise HTTPException(status_code=404, detail="User not found")

    return updated


@router.post("/{user_id}/cv")
async def upload_cv(user_id: UUID):
    """Upload base CV for a user."""
    raise HTTPException(status_code=501, detail="CV upload coming soon")


@router.get("/{user_id}/preferences")
async def get_preferences(user_id: UUID, db: DbDep):
    """Get user job preferences."""
    repo = UserRepository(db)
    user = await repo.get(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user.preferences or {}


@router.put("/{user_id}/preferences")
async def update_preferences(user_id: UUID, preferences: dict, db: DbDep):
    """Update user job preferences."""
    repo = UserRepository(db)
    user = await repo.get(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.preferences = preferences
    flag_modified(user, "preferences")
    await db.flush()
    await db.refresh(user)

    return user.preferences


# ============================================================================
# Email Sender Preferences
# ============================================================================


def _get_default_senders() -> list[EmailSender]:
    """Get default email senders as EmailSender objects."""
    return [
        EmailSender(
            id=s["id"],
            name=s["name"],
            pattern=s["pattern"],
            enabled=s.get("enabled", True),
            is_custom=False,
        )
        for s in DEFAULT_JOB_EMAIL_SENDERS
    ]


def _merge_sender_preferences(
    defaults: list[EmailSender],
    user_prefs: EmailSenderPreferences | None,
) -> list[EmailSender]:
    """Merge default senders with user preferences to get effective list."""
    if not user_prefs:
        return [s for s in defaults if s.enabled]

    effective = []

    for sender in defaults:
        # Check if user has overridden the default enabled state
        if sender.id in (user_prefs.disabled_sender_ids or []):
            continue  # User disabled this default
        elif sender.id in (user_prefs.enabled_sender_ids or []):
            effective.append(sender)  # User enabled this default
        elif sender.enabled:
            effective.append(sender)  # Default is enabled

    # Add user's custom senders
    for custom in user_prefs.senders or []:
        if custom.enabled:
            effective.append(custom)

    return effective


@router.get("/{user_id}/email-senders", response_model=EmailSenderPreferencesResponse)
async def get_email_sender_preferences(user_id: UUID, db: DbDep):
    """Get user's email sender preferences."""
    repo = UserRepository(db)
    user = await repo.get(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    defaults = _get_default_senders()

    # Extract email preferences from user.preferences JSON
    user_email_prefs = None
    if user.preferences and "email_senders" in user.preferences:
        user_email_prefs = EmailSenderPreferences(**user.preferences["email_senders"])

    effective = _merge_sender_preferences(defaults, user_email_prefs)

    return EmailSenderPreferencesResponse(
        default_senders=defaults,
        user_preferences=user_email_prefs or EmailSenderPreferences(),
        effective_senders=effective,
    )


@router.put("/{user_id}/email-senders", response_model=EmailSenderPreferencesResponse)
async def update_email_sender_preferences(
    user_id: UUID,
    updates: EmailSenderPreferencesUpdate,
    db: DbDep,
):
    """Update user's email sender preferences."""
    repo = UserRepository(db)
    user = await repo.get(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get current preferences or create new
    current_prefs = dict(user.preferences) if user.preferences else {}
    email_prefs = current_prefs.get("email_senders", {
        "senders": [],
        "enabled_sender_ids": [],
        "disabled_sender_ids": [],
    })

    # Track enabled/disabled sender IDs
    enabled_ids = set(email_prefs.get("enabled_sender_ids", []))
    disabled_ids = set(email_prefs.get("disabled_sender_ids", []))
    custom_senders = list(email_prefs.get("senders", []))

    # Apply updates
    if updates.enabled_sender_ids:
        enabled_ids.update(updates.enabled_sender_ids)
        disabled_ids -= set(updates.enabled_sender_ids)

    if updates.disabled_sender_ids:
        disabled_ids.update(updates.disabled_sender_ids)
        enabled_ids -= set(updates.disabled_sender_ids)

    if updates.custom_senders:
        for sender in updates.custom_senders:
            sender_dict = sender.model_dump()
            sender_dict["is_custom"] = True
            # Only add if not already exists
            if not any(s.get("id") == sender.id for s in custom_senders):
                custom_senders.append(sender_dict)

    if updates.remove_sender_ids:
        custom_senders = [
            s for s in custom_senders
            if s.get("id") not in updates.remove_sender_ids
        ]

    # Update preferences
    email_prefs["enabled_sender_ids"] = list(enabled_ids)
    email_prefs["disabled_sender_ids"] = list(disabled_ids)
    email_prefs["senders"] = custom_senders

    current_prefs["email_senders"] = email_prefs

    # Save to database - need to flag JSON field as modified for SQLAlchemy
    user.preferences = current_prefs
    flag_modified(user, "preferences")
    await db.flush()
    await db.refresh(user)

    # Return updated state
    return await get_email_sender_preferences(user_id, db)

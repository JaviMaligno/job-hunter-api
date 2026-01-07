"""Email ingest routes for processing forwarded emails."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from src.api.dependencies import DbDep
from src.config import settings
from src.db.models import User
from src.services.email_pipeline import EmailPipelineService, PipelineOptions

router = APIRouter()


async def get_webhook_user(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
    x_webhook_api_key: Annotated[str | None, Header(alias="X-Webhook-API-Key")] = None,
) -> User:
    """
    Get user for webhook requests. Supports either:
    1. JWT Bearer token in Authorization header
    2. Webhook API key in X-Webhook-API-Key header

    For API key auth, uses the first user or creates a webhook user.
    """
    from src.auth.jwt import TokenError, verify_token

    # Try JWT auth first if Authorization header present
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        try:
            payload = verify_token(token)
            user_id = UUID(payload["sub"])
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user:
                return user
        except (TokenError, ValueError):
            pass  # Fall through to API key auth

    # Try API key auth
    if x_webhook_api_key and settings.webhook_api_key:
        if x_webhook_api_key == settings.webhook_api_key:
            # Get or create webhook user
            result = await db.execute(
                select(User).where(User.email == "webhook@jobhunter.system")
            )
            user = result.scalar_one_or_none()
            if user:
                return user

            # Find the most recently created user (likely the active user)
            result = await db.execute(
                select(User).order_by(User.created_at.desc()).limit(1)
            )
            user = result.scalar_one_or_none()
            if user:
                return user

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No users exist. Please create a user first via the dashboard.",
            )

    # No valid auth
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication. Provide either 'Authorization: Bearer <token>' or 'X-Webhook-API-Key: <key>' header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


WebhookUser = Annotated[User, Depends(get_webhook_user)]


# ============================================================================
# Schemas
# ============================================================================


class EmailIngestRequest(BaseModel):
    """Request schema for ingesting a forwarded email."""

    subject: str
    body: str  # HTML or plain text email body
    sender_email: str | None = None

    # Pipeline options
    save_job: bool = True
    adapt_cv: bool = False
    generate_cover_letter: bool = False
    start_application: bool = False
    language: str = "en"
    devtools_url: str | None = None


class ExtractedJobInfo(BaseModel):
    """Info about an extracted job from email."""

    title: str
    company: str
    location: str | None = None
    job_url: str | None = None
    source_platform: str | None = None


class EmailIngestResponse(BaseModel):
    """Response from ingesting an email."""

    success: bool
    jobs_extracted: list[ExtractedJobInfo] = []
    job_id: str | None = None
    job_title: str | None = None
    job_company: str | None = None
    job_url: str | None = None
    adapted_cv: str | None = None
    cover_letter: str | None = None
    match_score: int | None = None
    skills_matched: list[str] | None = None
    skills_missing: list[str] | None = None
    application_session_id: str | None = None
    application_status: str | None = None
    errors: list[str] = []


# ============================================================================
# Routes
# ============================================================================


@router.post("/ingest", response_model=EmailIngestResponse)
async def ingest_email(
    request: EmailIngestRequest,
    db: DbDep,
    current_user: WebhookUser,
) -> EmailIngestResponse:
    """
    Ingest a forwarded email for processing through the job pipeline.

    This endpoint allows you to submit email content directly (e.g., from Zapier,
    Make.com, or other automation tools) for job extraction and optional pipeline
    processing.

    **Authentication:** Supports two methods:
    1. JWT Bearer token: `Authorization: Bearer <your-jwt-token>`
    2. Webhook API key: `X-Webhook-API-Key: <your-api-key>`

    **Pipeline steps (all optional except extraction):**
    1. Extract job information from email content
    2. Save job to database (default: true)
    3. Adapt CV for the job (requires adapt_cv=true)
    4. Generate cover letter (requires generate_cover_letter=true)
    5. Start automatic application (requires start_application=true)

    **Example webhook configuration (Make.com/Zapier):**
    ```
    POST https://your-api.com/api/emails/ingest
    Headers:
        X-Webhook-API-Key: <your-api-key>
        Content-Type: application/json
    Body:
        {
            "subject": "{{email.subject}}",
            "body": "{{email.body}}",
            "sender_email": "{{email.from}}",
            "adapt_cv": true,
            "generate_cover_letter": true
        }
    ```
    """
    # Build email content dict
    email_content = {
        "subject": request.subject,
        "body": request.body,
        "sender": request.sender_email or "",
        "message_id": None,  # No Gmail message ID for forwarded emails
        "received_at": None,
    }

    # Build pipeline options
    options = PipelineOptions(
        save_job=request.save_job,
        adapt_cv=request.adapt_cv,
        generate_cover_letter=request.generate_cover_letter,
        start_application=request.start_application,
        language=request.language,
        devtools_url=request.devtools_url,
    )

    # Process through pipeline
    pipeline = EmailPipelineService(db)
    result = await pipeline.process_email(email_content, current_user.id, options)

    # Convert extracted jobs to response format
    jobs_info = [
        ExtractedJobInfo(
            title=j.get("title", ""),
            company=j.get("company", ""),
            location=j.get("location"),
            job_url=j.get("job_url"),
            source_platform=j.get("source_platform"),
        )
        for j in (result.jobs_extracted or [])
    ]

    return EmailIngestResponse(
        success=result.success,
        jobs_extracted=jobs_info,
        job_id=str(result.job_id) if result.job_id else None,
        job_title=result.job_title,
        job_company=result.job_company,
        job_url=result.job_url,
        adapted_cv=result.adapted_cv,
        cover_letter=result.cover_letter,
        match_score=result.match_score,
        skills_matched=result.skills_matched,
        skills_missing=result.skills_missing,
        application_session_id=result.application_session_id,
        application_status=result.application_status,
        errors=result.errors or [],
    )

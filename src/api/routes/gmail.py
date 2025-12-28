"""Gmail OAuth routes for connecting user's Gmail account."""

import secrets
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from src.api.dependencies import DbDep
from src.config import settings
from src.db.models import EmailConnection, EmailProvider, User

router = APIRouter()

# Gmail API scopes
# Required scopes (always requested)
GMAIL_REQUIRED_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",  # Read emails
    "email",  # Get user's email address
]

# Optional scopes (user can choose)
GMAIL_OPTIONAL_SCOPES = {
    "labels": "https://www.googleapis.com/auth/gmail.labels",  # Manage labels
    "modify": "https://www.googleapis.com/auth/gmail.modify",  # Mark as read, etc.
}

# OAuth state storage (in production, use Redis or database)
_gmail_oauth_states: dict[str, dict] = {}


# ============================================================================
# Schemas
# ============================================================================


class GmailStatusResponse(BaseModel):
    """Response for Gmail connection status."""

    connected: bool
    email: str | None = None
    last_sync_at: datetime | None = None
    # Granted optional scopes
    can_manage_labels: bool = False
    can_modify: bool = False


class GmailConnectionResponse(BaseModel):
    """Response after successful Gmail connection."""

    success: bool
    message: str


class EmailScanRequest(BaseModel):
    """Request for scanning emails."""

    max_emails: int = 20
    unread_only: bool = False


class ExtractedJobInfo(BaseModel):
    """Info about an extracted job from email."""

    title: str
    company: str
    location: str | None = None
    job_url: str | None = None
    source_platform: str | None = None


class ScannedEmail(BaseModel):
    """Info about a scanned email."""

    message_id: str
    subject: str
    sender: str
    received_at: str
    jobs_extracted: list[ExtractedJobInfo] = []


class EmailScanResponse(BaseModel):
    """Response from email scanning."""

    success: bool
    emails_scanned: int
    jobs_extracted: int
    jobs_skipped_duplicates: int = 0
    emails: list[ScannedEmail] = []
    message: str | None = None


# ============================================================================
# Helper Functions
# ============================================================================


def _get_gmail_authorization_url(state: str, scopes: list[str]) -> str:
    """Generate Gmail OAuth authorization URL."""
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.gmail_redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "access_type": "offline",  # Get refresh token
        "prompt": "consent",  # Always show consent to get refresh token
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


async def _exchange_code_for_tokens(code: str) -> dict:
    """Exchange authorization code for Gmail tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "redirect_uri": settings.gmail_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()


async def _refresh_gmail_token(refresh_token: str) -> dict:
    """Refresh Gmail access token using refresh token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        return response.json()


async def _get_gmail_user_email(access_token: str) -> str:
    """Get the email address associated with the Gmail token."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("email", "")


# ============================================================================
# Routes
# ============================================================================


@router.get("/connect/{user_id}")
async def initiate_gmail_connection(
    user_id: UUID,
    db: DbDep,
    labels: Annotated[bool, Query(description="Request labels management permission")] = False,
    modify: Annotated[bool, Query(description="Request modify permission (mark as read)")] = False,
) -> RedirectResponse:
    """
    Initiate Gmail OAuth flow for a user.

    This redirects the user to Google's authorization page.
    After authorization, Google redirects back to /api/gmail/callback.

    Query params:
    - labels: Request permission to manage labels
    - modify: Request permission to mark emails as read
    """
    # Verify user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )

    # Build scopes list
    scopes = GMAIL_REQUIRED_SCOPES.copy()
    requested_optional = []
    if labels:
        scopes.append(GMAIL_OPTIONAL_SCOPES["labels"])
        requested_optional.append("labels")
    if modify:
        scopes.append(GMAIL_OPTIONAL_SCOPES["modify"])
        requested_optional.append("modify")

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    _gmail_oauth_states[state] = {
        "user_id": str(user_id),
        "created_at": datetime.now(UTC),
        "requested_scopes": scopes,
        "requested_optional": requested_optional,
    }

    auth_url = _get_gmail_authorization_url(state, scopes)
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def gmail_oauth_callback(
    db: DbDep,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """
    Handle Gmail OAuth callback from Google.

    Exchanges the authorization code for tokens and stores them.
    """
    # Handle errors from Google
    if error:
        error_url = f"{settings.frontend_url}/profile?gmail_error={error}"
        return RedirectResponse(url=error_url)

    if not code or not state:
        error_url = f"{settings.frontend_url}/profile?gmail_error=missing_params"
        return RedirectResponse(url=error_url)

    # Verify state
    state_data = _gmail_oauth_states.pop(state, None)
    if not state_data:
        error_url = f"{settings.frontend_url}/profile?gmail_error=invalid_state"
        return RedirectResponse(url=error_url)

    user_id = UUID(state_data["user_id"])
    state_data.get("requested_scopes", GMAIL_REQUIRED_SCOPES)
    state_data.get("requested_optional", [])

    try:
        # Exchange code for tokens
        token_data = await _exchange_code_for_tokens(code)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        # Google returns the actual granted scopes
        granted_scope_str = token_data.get("scope", "")

        if not access_token:
            raise ValueError("No access token received")

        # Get the Gmail email address
        gmail_email = await _get_gmail_user_email(access_token)

        # Calculate token expiry
        token_expires_at = datetime.now(UTC).replace(tzinfo=None) + __import__(
            "datetime"
        ).timedelta(seconds=expires_in)

        # Find or create EmailConnection
        result = await db.execute(
            select(EmailConnection).where(
                EmailConnection.user_id == user_id,
                EmailConnection.provider == EmailProvider.GMAIL,
            )
        )
        connection = result.scalar_one_or_none()

        if connection:
            # Update existing connection
            connection.access_token_encrypted = access_token  # TODO: encrypt
            connection.refresh_token_encrypted = refresh_token  # TODO: encrypt
            connection.token_expires_at = token_expires_at
            connection.granted_scopes = granted_scope_str
            connection.is_active = True
        else:
            # Create new connection
            connection = EmailConnection(
                user_id=user_id,
                provider=EmailProvider.GMAIL,
                access_token_encrypted=access_token,  # TODO: encrypt
                refresh_token_encrypted=refresh_token,  # TODO: encrypt
                token_expires_at=token_expires_at,
                granted_scopes=granted_scope_str,
                is_active=True,
            )
            db.add(connection)

        await db.flush()

        # Redirect to frontend with success
        success_url = (
            f"{settings.frontend_url}/profile?gmail_connected=true&gmail_email={gmail_email}"
        )
        return RedirectResponse(url=success_url)

    except Exception as e:
        error_url = f"{settings.frontend_url}/profile?gmail_error={str(e)}"
        return RedirectResponse(url=error_url)


@router.get("/status/{user_id}", response_model=GmailStatusResponse)
async def get_gmail_status(user_id: UUID, db: DbDep) -> GmailStatusResponse:
    """
    Check if a user has Gmail connected.

    Returns connection status and email if connected.
    """
    # Find Gmail connection
    result = await db.execute(
        select(EmailConnection).where(
            EmailConnection.user_id == user_id,
            EmailConnection.provider == EmailProvider.GMAIL,
            EmailConnection.is_active == True,  # noqa: E712
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        return GmailStatusResponse(connected=False)

    # Try to get email from token (if still valid)
    email = None
    if connection.access_token_encrypted:
        try:
            # Check if token is expired
            if connection.token_expires_at and connection.token_expires_at < datetime.utcnow():
                # Refresh token
                if connection.refresh_token_encrypted:
                    token_data = await _refresh_gmail_token(connection.refresh_token_encrypted)
                    connection.access_token_encrypted = token_data.get("access_token")
                    expires_in = token_data.get("expires_in", 3600)
                    connection.token_expires_at = datetime.utcnow() + __import__(
                        "datetime"
                    ).timedelta(seconds=expires_in)
                    await db.flush()

            email = await _get_gmail_user_email(connection.access_token_encrypted)
        except Exception:
            # Token might be revoked
            pass

    # Check granted scopes
    granted_scopes = connection.granted_scopes or ""
    can_manage_labels = GMAIL_OPTIONAL_SCOPES["labels"] in granted_scopes
    can_modify = GMAIL_OPTIONAL_SCOPES["modify"] in granted_scopes

    return GmailStatusResponse(
        connected=True,
        email=email,
        last_sync_at=connection.last_sync_at,
        can_manage_labels=can_manage_labels,
        can_modify=can_modify,
    )


@router.delete("/disconnect/{user_id}")
async def disconnect_gmail(user_id: UUID, db: DbDep) -> GmailConnectionResponse:
    """
    Disconnect Gmail from a user's account.

    This revokes tokens and removes the connection.
    """
    # Find Gmail connection
    result = await db.execute(
        select(EmailConnection).where(
            EmailConnection.user_id == user_id,
            EmailConnection.provider == EmailProvider.GMAIL,
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Gmail connection found",
        )

    # Try to revoke token at Google (best effort)
    if connection.access_token_encrypted:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": connection.access_token_encrypted},
                )
        except Exception:
            pass  # Continue even if revocation fails

    # Delete the connection
    await db.delete(connection)
    await db.flush()

    return GmailConnectionResponse(
        success=True,
        message="Gmail disconnected successfully",
    )


@router.post("/scan/{user_id}", response_model=EmailScanResponse)
async def scan_emails(
    user_id: UUID,
    db: DbDep,
    request: EmailScanRequest | None = None,
    save_jobs: Annotated[bool, Query(description="Save extracted jobs to database")] = True,
) -> EmailScanResponse:
    """
    Scan Gmail for job alert emails and extract job information.

    This fetches emails from known job platforms (LinkedIn, Indeed, etc.)
    and parses them to extract job postings.

    Query params:
    - save_jobs: If true (default), saves extracted jobs to database
    """
    from src.db.models import Job, JobStatus
    from src.integrations.email.gmail import GmailClient
    from src.integrations.email.parser import parse_job_email

    # Get request params with defaults
    max_emails = request.max_emails if request else 20
    unread_only = request.unread_only if request else False

    # Get Gmail client for user
    gmail_client = await GmailClient.for_user(db, user_id)

    if not gmail_client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail not connected. Please connect Gmail first.",
        )

    try:
        # Fetch emails
        if unread_only:
            emails = gmail_client.get_all_unread_emails(max_results=max_emails)
        else:
            emails = gmail_client.get_job_alert_emails(max_results=max_emails)

        # Update last sync timestamp
        result = await db.execute(
            select(EmailConnection).where(
                EmailConnection.user_id == user_id,
                EmailConnection.provider == EmailProvider.GMAIL,
            )
        )
        connection = result.scalar_one_or_none()
        if connection:
            connection.last_sync_at = datetime.now(UTC).replace(tzinfo=None)
            await db.flush()

        # Get existing job URLs for this user to avoid duplicates
        existing_urls = set()
        if save_jobs:
            existing_jobs_result = await db.execute(
                select(Job.source_url).where(Job.user_id == user_id)
            )
            existing_urls = {row[0] for row in existing_jobs_result.fetchall() if row[0]}

        # Parse emails and extract jobs
        total_jobs_extracted = 0
        total_skipped_duplicates = 0
        scanned_emails = []

        for email in emails:
            body = email.get("body", "")
            sender = email.get("sender", "")
            subject = email.get("subject", "")

            # Parse email to extract jobs
            extracted_jobs = parse_job_email(body, sender, subject)
            print(f"[DEBUG] Email: {subject[:50]}... - Body length: {len(body)} chars")
            print(f"[DEBUG] Parser found {len(extracted_jobs)} jobs")
            for ej in extracted_jobs[:3]:
                print(
                    f"[DEBUG]   Job: {ej.title} at {ej.company} - {ej.job_url[:60] if ej.job_url else 'No URL'}..."
                )

            # Convert to response format
            jobs_info = []
            for extracted in extracted_jobs:
                # Skip if URL already exists
                if extracted.job_url and extracted.job_url in existing_urls:
                    total_skipped_duplicates += 1
                    continue

                jobs_info.append(
                    ExtractedJobInfo(
                        title=extracted.title,
                        company=extracted.company,
                        location=extracted.location,
                        job_url=extracted.job_url,
                        source_platform=extracted.source_platform,
                    )
                )

                # Save job to database if requested
                if save_jobs and extracted.job_url:
                    job = Job(
                        user_id=user_id,
                        source_url=extracted.job_url,
                        title=extracted.title,
                        company=extracted.company,
                        location=extracted.location,
                        source_platform=extracted.source_platform,
                        status=JobStatus.INBOX,
                    )
                    db.add(job)
                    existing_urls.add(extracted.job_url)  # Prevent duplicates within same scan

            total_jobs_extracted += len(jobs_info)

            scanned_emails.append(
                ScannedEmail(
                    message_id=email.get("message_id", ""),
                    subject=subject,
                    sender=sender,
                    received_at=email.get("received_at", ""),
                    jobs_extracted=jobs_info,
                )
            )

        # Flush all new jobs
        if save_jobs and total_jobs_extracted > 0:
            await db.flush()

        # Build informative message
        msg_parts = [f"Scanned {len(scanned_emails)} emails"]
        if total_jobs_extracted > 0:
            msg_parts.append(f"extracted {total_jobs_extracted} new jobs")
        if total_skipped_duplicates > 0:
            msg_parts.append(f"skipped {total_skipped_duplicates} duplicates")
        if total_jobs_extracted == 0 and total_skipped_duplicates == 0:
            msg_parts.append("no new jobs found")

        return EmailScanResponse(
            success=True,
            emails_scanned=len(scanned_emails),
            jobs_extracted=total_jobs_extracted,
            jobs_skipped_duplicates=total_skipped_duplicates,
            emails=scanned_emails,
            message=", ".join(msg_parts),
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error scanning emails: {str(e)}",
        )

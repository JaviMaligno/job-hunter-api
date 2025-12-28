"""Gmail integration using OAuth2 with per-user token storage."""

import base64
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from uuid import UUID

import httpx
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import DEFAULT_JOB_EMAIL_SENDERS, settings
from src.db.models import EmailConnection, EmailProvider

# Gmail API scopes - only readonly is required
# Labels scope is optional - app works without it
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]


async def get_user_gmail_credentials(db: AsyncSession, user_id: UUID) -> Credentials | None:
    """
    Get Gmail credentials for a specific user from the database.

    Returns None if user has no Gmail connection or tokens are invalid.
    """
    result = await db.execute(
        select(EmailConnection).where(
            EmailConnection.user_id == user_id,
            EmailConnection.provider == EmailProvider.GMAIL,
            EmailConnection.is_active == True,  # noqa: E712
        )
    )
    connection = result.scalar_one_or_none()

    if not connection or not connection.access_token_encrypted:
        return None

    # Check if token is expired and refresh if needed
    if connection.token_expires_at and connection.token_expires_at < datetime.utcnow():
        if connection.refresh_token_encrypted:
            try:
                new_tokens = await _refresh_token(connection.refresh_token_encrypted)
                connection.access_token_encrypted = new_tokens["access_token"]
                expires_in = new_tokens.get("expires_in", 3600)
                connection.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                await db.flush()
            except Exception:
                # Token refresh failed - connection may be revoked
                connection.is_active = False
                await db.flush()
                return None

    # Build credentials object
    return Credentials(
        token=connection.access_token_encrypted,
        refresh_token=connection.refresh_token_encrypted,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )


async def _refresh_token(refresh_token: str) -> dict:
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


async def is_gmail_connected(db: AsyncSession, user_id: UUID) -> bool:
    """Check if user has an active Gmail connection."""
    result = await db.execute(
        select(EmailConnection).where(
            EmailConnection.user_id == user_id,
            EmailConnection.provider == EmailProvider.GMAIL,
            EmailConnection.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none() is not None


class GmailClient:
    """Gmail client for fetching and parsing emails per user."""

    def __init__(self, credentials: Credentials):
        """
        Initialize Gmail client with user credentials.

        Args:
            credentials: OAuth2 credentials for the user's Gmail account.
        """
        self.credentials = credentials
        self.service = build("gmail", "v1", credentials=credentials)

    @classmethod
    async def for_user(cls, db: AsyncSession, user_id: UUID) -> "GmailClient | None":
        """
        Create a GmailClient for a specific user.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            GmailClient instance or None if user has no Gmail connection.
        """
        credentials = await get_user_gmail_credentials(db, user_id)
        if not credentials:
            return None
        return cls(credentials)

    def get_job_alert_emails(
        self,
        max_results: int = 50,
        after_date: datetime | None = None,
        labels: list[str] | None = None,
        custom_senders: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch emails that are likely job alerts.

        Args:
            max_results: Maximum number of emails to fetch.
            after_date: Only fetch emails after this date.
            labels: Gmail labels to filter by (default: INBOX).
            custom_senders: List of sender patterns to use instead of defaults.

        Returns:
            List of parsed email dictionaries.
        """
        # Build query for job-related emails
        query_parts = []

        # Use custom senders if provided, otherwise use defaults
        if custom_senders:
            sender_patterns = custom_senders
        else:
            sender_patterns = [
                s["pattern"] for s in DEFAULT_JOB_EMAIL_SENDERS if s.get("enabled", True)
            ]

        job_senders = [f"from:{pattern}" for pattern in sender_patterns]
        query_parts.append(f"({' OR '.join(job_senders)})")

        # Date filter
        if after_date:
            date_str = after_date.strftime("%Y/%m/%d")
            query_parts.append(f"after:{date_str}")

        query = " ".join(query_parts)

        # DEBUG: Print the query being used
        print(f"[DEBUG] Gmail query: {query}")
        print(f"[DEBUG] Sender patterns: {sender_patterns}")

        # Fetch message IDs
        label_ids = labels or ["INBOX"]
        try:
            results = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    labelIds=label_ids,
                    maxResults=max_results,
                )
                .execute()
            )
            print(f"[DEBUG] Gmail API response keys: {results.keys()}")
            print(
                f"[DEBUG] Gmail API resultSizeEstimate: {results.get('resultSizeEstimate', 'N/A')}"
            )
        except Exception as e:
            print(f"[DEBUG] Gmail API error: {e}")
            raise

        messages = results.get("messages", [])
        print(f"[DEBUG] Found {len(messages)} messages matching query")

        # Fetch full message content
        emails = []
        for msg in messages:
            email_data = self._get_email_content(msg["id"])
            if email_data:
                emails.append(email_data)

        return emails

    def get_all_unread_emails(
        self,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Fetch all unread emails from inbox."""
        results = (
            self.service.users()
            .messages()
            .list(
                userId="me",
                labelIds=["INBOX", "UNREAD"],
                maxResults=max_results,
            )
            .execute()
        )

        messages = results.get("messages", [])

        emails = []
        for msg in messages:
            email_data = self._get_email_content(msg["id"])
            if email_data:
                emails.append(email_data)

        return emails

    def _get_email_content(self, message_id: str) -> dict[str, Any] | None:
        """Fetch and parse a single email by ID."""
        try:
            message = (
                self.service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="full",
                )
                .execute()
            )

            headers = {h["name"]: h["value"] for h in message["payload"]["headers"]}

            # Extract body
            body = self._extract_body(message["payload"])

            # Parse date
            date_str = headers.get("Date", "")
            try:
                received_at = parsedate_to_datetime(date_str).isoformat()
            except Exception:
                received_at = datetime.now().isoformat()

            return {
                "message_id": message_id,
                "subject": headers.get("Subject", ""),
                "sender": headers.get("From", ""),
                "to": headers.get("To", ""),
                "body": body,
                "received_at": received_at,
                "labels": message.get("labelIds", []),
                "snippet": message.get("snippet", ""),
            }

        except Exception as e:
            print(f"Error fetching email {message_id}: {e}")
            return None

    def _extract_body(self, payload: dict) -> str:
        """Extract email body from payload, preferring HTML."""
        body = ""

        if "body" in payload and payload["body"].get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

        elif "parts" in payload:
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")

                if mime_type == "text/html":
                    if "body" in part and part["body"].get("data"):
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                        break

                elif mime_type == "text/plain" and not body:
                    if "body" in part and part["body"].get("data"):
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")

                elif "parts" in part:
                    # Nested multipart
                    body = self._extract_body(part)
                    if body:
                        break

        return body

    def mark_as_read(self, message_id: str) -> bool:
        """
        Mark an email as read.

        Note: This requires gmail.modify scope. If the user only granted
        gmail.readonly, this will fail gracefully and return False.
        """
        try:
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
            return True
        except Exception:
            # May fail if user only granted readonly scope - that's OK
            return False

    def add_label(self, message_id: str, label_name: str) -> bool:
        """
        Add a label to an email (creates label if needed).

        Note: This requires gmail.labels scope. If the user only granted
        gmail.readonly, this will fail gracefully and return False.
        """
        try:
            # Get or create label
            label_id = self._get_or_create_label(label_name)
            if not label_id:
                return False

            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"addLabelIds": [label_id]},
            ).execute()
            return True
        except Exception:
            # May fail if user only granted readonly scope - that's OK
            return False

    def _get_or_create_label(self, label_name: str) -> str | None:
        """
        Get label ID, creating if it doesn't exist.

        Returns None if labels scope is not available.
        """
        try:
            # List existing labels
            results = self.service.users().labels().list(userId="me").execute()
            labels = results.get("labels", [])

            for label in labels:
                if label["name"] == label_name:
                    return label["id"]

            # Create new label
            label_body = {
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            }
            created = (
                self.service.users()
                .labels()
                .create(
                    userId="me",
                    body=label_body,
                )
                .execute()
            )

            return created["id"]
        except Exception:
            # May fail if user only granted readonly scope
            return None

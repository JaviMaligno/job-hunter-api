"""Gmail integration using OAuth2 for Desktop Apps."""

import base64
import json
import os
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.config import settings

# Gmail API scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
]

# Token storage path
TOKEN_PATH = Path("data/gmail_token.json")
CREDENTIALS_PATH = Path("data/gmail_credentials.json")


def get_credentials_config() -> dict[str, Any]:
    """Build credentials config from environment variables."""
    return {
        "installed": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost"],
        }
    }


def authenticate_gmail() -> Credentials:
    """
    Authenticate with Gmail using OAuth2 Desktop App flow.

    Returns:
        Credentials object for Gmail API.

    This will:
    1. Check for existing valid token
    2. Refresh token if expired
    3. Run OAuth flow if no token exists (opens browser)
    """
    creds = None

    # Check for existing token
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Run OAuth flow - opens browser
            if not settings.google_client_id or not settings.google_client_secret:
                raise ValueError(
                    "Google OAuth credentials not configured. "
                    "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env"
                )

            flow = InstalledAppFlow.from_client_config(
                get_credentials_config(),
                SCOPES,
            )
            creds = flow.run_local_server(port=0)

        # Save credentials for next run
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    return creds


def get_gmail_service():
    """Get authenticated Gmail API service."""
    creds = authenticate_gmail()
    return build("gmail", "v1", credentials=creds)


def is_authenticated() -> bool:
    """Check if Gmail is authenticated with valid token."""
    if not TOKEN_PATH.exists():
        return False

    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        return creds.valid or (creds.expired and creds.refresh_token)
    except Exception:
        return False


def logout_gmail() -> bool:
    """Remove Gmail authentication token."""
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
        return True
    return False


class GmailClient:
    """Gmail client for fetching and parsing emails."""

    def __init__(self):
        self.service = get_gmail_service()

    def get_job_alert_emails(
        self,
        max_results: int = 50,
        after_date: datetime | None = None,
        labels: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch emails that are likely job alerts.

        Args:
            max_results: Maximum number of emails to fetch.
            after_date: Only fetch emails after this date.
            labels: Gmail labels to filter by (default: INBOX).

        Returns:
            List of parsed email dictionaries.
        """
        # Build query for job-related emails
        query_parts = []

        # Common job alert senders
        job_senders = [
            "from:linkedin.com",
            "from:indeed.com",
            "from:glassdoor.com",
            "from:infojobs.net",
            "from:jobs-noreply@linkedin.com",
            "from:jobalert-noreply@linkedin.com",
        ]
        query_parts.append(f"({' OR '.join(job_senders)})")

        # Date filter
        if after_date:
            date_str = after_date.strftime("%Y/%m/%d")
            query_parts.append(f"after:{date_str}")

        query = " ".join(query_parts)

        # Fetch message IDs
        label_ids = labels or ["INBOX"]
        results = self.service.users().messages().list(
            userId="me",
            q=query,
            labelIds=label_ids,
            maxResults=max_results,
        ).execute()

        messages = results.get("messages", [])

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
        results = self.service.users().messages().list(
            userId="me",
            labelIds=["INBOX", "UNREAD"],
            maxResults=max_results,
        ).execute()

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
            message = self.service.users().messages().get(
                userId="me",
                id=message_id,
                format="full",
            ).execute()

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
        """Mark an email as read."""
        try:
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
            return True
        except Exception:
            return False

    def add_label(self, message_id: str, label_name: str) -> bool:
        """Add a label to an email (creates label if needed)."""
        try:
            # Get or create label
            label_id = self._get_or_create_label(label_name)

            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"addLabelIds": [label_id]},
            ).execute()
            return True
        except Exception:
            return False

    def _get_or_create_label(self, label_name: str) -> str:
        """Get label ID, creating if it doesn't exist."""
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
        created = self.service.users().labels().create(
            userId="me",
            body=label_body,
        ).execute()

        return created["id"]

"""Email integrations (Gmail, Outlook)."""

from src.integrations.email.gmail import (
    GmailClient,
    get_user_gmail_credentials,
    is_gmail_connected,
)

__all__ = [
    "GmailClient",
    "get_user_gmail_credentials",
    "is_gmail_connected",
]

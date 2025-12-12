"""Email integrations (Gmail, Outlook)."""

from src.integrations.email.gmail import (
    GmailClient,
    authenticate_gmail,
    is_authenticated,
    logout_gmail,
)

__all__ = [
    "GmailClient",
    "authenticate_gmail",
    "is_authenticated",
    "logout_gmail",
]

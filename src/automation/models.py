"""Shared models for automation module."""

from pydantic import BaseModel


class UserFormData(BaseModel):
    """User data for form filling - maps from User model.

    This model is shared between:
    - FormFillerAgent (agents/form_filler.py)
    - ATS Strategies (automation/strategies/)

    Moved to this module to avoid circular imports.
    """

    first_name: str
    last_name: str
    email: str
    phone: str
    phone_country_code: str = "+44"
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    county_state: str | None = None
    country: str = "United Kingdom"
    postal_code: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None

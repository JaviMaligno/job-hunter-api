"""Pydantic schemas for API requests and responses."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.db.models import ApplicationMode, BlockerType, JobStatus, MaterialType


# ============================================================================
# User Schemas
# ============================================================================


class UserBase(BaseModel):
    """Base user schema."""

    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    phone_country_code: str = "+44"
    address_line_1: str | None = None
    city: str | None = None
    country: str = "United Kingdom"
    linkedin_url: str | None = None
    github_url: str | None = None


class UserCreate(UserBase):
    """Schema for creating a user."""

    base_cv_content: str | None = None


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    address_line_1: str | None = None
    city: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    base_cv_content: str | None = None
    preferences: dict[str, Any] | None = None


class UserResponse(UserBase):
    """Schema for user response."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Job Schemas
# ============================================================================


class JobBase(BaseModel):
    """Base job schema."""

    source_url: str
    title: str
    company: str | None = None
    location: str | None = None
    job_type: str | None = None
    description_raw: str | None = None


class JobCreate(JobBase):
    """Schema for creating a job."""

    source_platform: str | None = None


class JobUpdate(BaseModel):
    """Schema for updating a job."""

    status: JobStatus | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description_raw: str | None = None
    blocker_type: BlockerType | None = None
    blocker_details: str | None = None


class JobResponse(JobBase):
    """Schema for job response."""

    id: UUID
    user_id: UUID
    status: JobStatus
    match_score: int | None = None
    skills_matched: list[str] | None = None
    skills_missing: list[str] | None = None
    blocker_type: BlockerType | None = None
    ats_type: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    """Schema for job list response."""

    jobs: list[JobResponse]
    total: int
    page: int
    page_size: int


# ============================================================================
# Material Schemas
# ============================================================================


class MaterialResponse(BaseModel):
    """Schema for material response."""

    id: UUID
    job_id: UUID
    material_type: MaterialType
    content: str
    changes_made: list[str] | None = None
    changes_explanation: str | None = None
    version: int
    is_current: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Application Schemas
# ============================================================================


class ApplicationCreate(BaseModel):
    """Schema for creating an application."""

    job_id: UUID
    mode: ApplicationMode = ApplicationMode.ASSISTED


class ApplicationResponse(BaseModel):
    """Schema for application response."""

    id: UUID
    job_id: UUID
    mode: ApplicationMode
    status: str
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


# ============================================================================
# CV Adaptation Schemas
# ============================================================================


class CVAdaptRequest(BaseModel):
    """Request schema for CV adaptation."""

    job_url: str | None = None
    job_description: str | None = None
    job_title: str
    company: str
    cv_content: str | None = None  # Uses user's base CV if not provided
    language: str = Field(default="en", pattern="^(en|es)$")


class CVAdaptResponse(BaseModel):
    """Response schema for CV adaptation."""

    adapted_cv: str
    cover_letter: str
    match_score: int
    changes_made: list[str]
    skills_matched: list[str]
    skills_missing: list[str]
    key_highlights: list[str]
    job_id: UUID | None = None  # If saved to database
    material_ids: list[UUID] | None = None  # Created materials

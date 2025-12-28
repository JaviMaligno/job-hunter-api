"""SQLAlchemy database models."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


# ============================================================================
# Enums
# ============================================================================


class EmailProvider(str, enum.Enum):
    """Email provider types (also used for OAuth connections like LinkedIn)."""

    GMAIL = "gmail"
    OUTLOOK = "outlook"
    LINKEDIN = "linkedin"  # For LinkedIn OAuth job applications


class JobStatus(str, enum.Enum):
    """Job pipeline status."""

    INBOX = "inbox"
    INTERESTING = "interesting"
    ADAPTED = "adapted"
    READY = "ready"
    APPLIED = "applied"
    BLOCKED = "blocked"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class BlockerType(str, enum.Enum):
    """Types of blockers that prevent application."""

    CAPTCHA = "captcha"
    FILE_UPLOAD = "file_upload"
    LOGIN_REQUIRED = "login_required"
    MULTI_STEP_FORM = "multi_step_form"
    LOCATION_MISMATCH = "location_mismatch"
    NONE = "none"


class MaterialType(str, enum.Enum):
    """Types of generated materials."""

    CV = "cv"
    COVER_LETTER = "cover_letter"
    TALKING_POINTS = "talking_points"


class ApplicationMode(str, enum.Enum):
    """Application automation modes."""

    ASSISTED = "assisted"
    SEMI_AUTO = "semi_auto"
    AUTO = "auto"


class ApplicationStatus(str, enum.Enum):
    """Application submission status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    SUBMITTED = "submitted"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_INTERVENTION = "needs_intervention"


class AuthProvider(str, enum.Enum):
    """Authentication provider types."""

    EMAIL = "email"
    GOOGLE = "google"
    LINKEDIN = "linkedin"
    GITHUB = "github"


# ============================================================================
# Models
# ============================================================================


class User(Base):
    """User profile with all personal data for form filling."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)

    # Authentication
    password_hash = Column(Text, nullable=True)  # For email/password auth
    auth_provider = Column(Enum(AuthProvider), default=AuthProvider.EMAIL)
    provider_user_id = Column(String(255), nullable=True)  # OAuth provider's user ID
    avatar_url = Column(String(500), nullable=True)
    email_verified = Column(Boolean, default=False)

    # Encrypted Claude API key (optional - user can provide per-request)
    claude_api_key_encrypted = Column(Text, nullable=True)

    # Personal information for forms
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(50))
    phone_country_code = Column(String(10), default="+44")

    # Address (for multi-step forms like Phenom)
    address_line_1 = Column(String(255))
    address_line_2 = Column(String(255))
    city = Column(String(100))
    county_state = Column(String(100))
    country = Column(String(100), default="United Kingdom")
    postal_code = Column(String(20))

    # Professional links
    linkedin_url = Column(String(500))
    github_url = Column(String(500))
    portfolio_url = Column(String(500))

    # Preferences (stored as JSON)
    # Example: {"roles": ["AI Engineer", "ML Engineer"], "languages": ["en", "es"],
    #           "locations": ["Remote", "London"], "min_salary": 80000}
    preferences = Column(JSON, default=dict)

    # Base CV content (parsed text)
    base_cv_content = Column(Text)
    base_cv_file_path = Column(String(500))

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    jobs = relationship("Job", back_populates="user", cascade="all, delete-orphan")
    materials = relationship("Material", back_populates="user", cascade="all, delete-orphan")
    email_connections = relationship(
        "EmailConnection", back_populates="user", cascade="all, delete-orphan"
    )
    skill_discoveries = relationship(
        "SkillDiscovery", back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )


class EmailConnection(Base):
    """OAuth connection for email providers."""

    __tablename__ = "email_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    provider = Column(Enum(EmailProvider), nullable=False)

    # OAuth tokens (encrypted)
    access_token_encrypted = Column(Text)
    refresh_token_encrypted = Column(Text)
    token_expires_at = Column(DateTime)

    # Granted OAuth scopes (comma-separated)
    granted_scopes = Column(Text, default="")

    is_active = Column(Boolean, default=True)
    last_sync_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="email_connections")


class RefreshToken(Base):
    """Refresh tokens for JWT authentication."""

    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    token_hash = Column(String(64), nullable=False, index=True)  # SHA256 hash
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")


class Job(Base):
    """Job opportunity in the pipeline."""

    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Source information
    source_email_id = Column(String(255))  # Email message ID
    source_platform = Column(String(100))  # LinkedIn, InfoJobs, Jack&Jill, etc.
    source_url = Column(String(1000), nullable=False)

    # Job details (parsed)
    title = Column(String(500), nullable=False)
    company = Column(String(255))
    location = Column(String(255))
    job_type = Column(String(50))  # remote, hybrid, onsite
    salary_range = Column(String(100))

    # Full job description
    description_raw = Column(Text)
    description_summary = Column(Text)  # AI-generated summary
    requirements_extracted = Column(JSON)  # Parsed requirements as list

    # Matching
    match_score = Column(Integer)  # 0-100
    match_explanation = Column(Text)
    skills_matched = Column(JSON)  # List of matched skills
    skills_missing = Column(JSON)  # List of missing skills

    # Pipeline status
    status = Column(Enum(JobStatus), default=JobStatus.INBOX)

    # Blocker information
    blocker_type = Column(Enum(BlockerType), default=BlockerType.NONE)
    blocker_details = Column(Text)

    # ATS detection
    ats_type = Column(String(50))  # workable, lever, bamboohr, etc.

    # Deadline
    deadline = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="jobs")
    materials = relationship("Material", back_populates="job", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="job", cascade="all, delete-orphan")


class Material(Base):
    """Generated materials (CV, cover letter, talking points) per job."""

    __tablename__ = "materials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)

    material_type = Column(Enum(MaterialType), nullable=False)

    # Content
    content = Column(Text, nullable=False)  # Markdown/text content
    file_path = Column(String(500))  # Generated PDF/DOCX path if any

    # Change tracking for transparency
    changes_made = Column(JSON)  # List of changes from base CV
    changes_explanation = Column(Text)  # Why changes were made

    # Versioning
    version = Column(Integer, default=1)
    is_current = Column(Boolean, default=True)

    # LLM trace reference
    langfuse_trace_id = Column(String(255))

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="materials")
    job = relationship("Job", back_populates="materials")


class Application(Base):
    """Application submission tracking."""

    __tablename__ = "applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)

    # Application mode
    mode = Column(Enum(ApplicationMode), default=ApplicationMode.ASSISTED)

    # Status
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.PENDING)

    # Form filling details
    form_fields_filled = Column(JSON)  # Fields that were filled
    form_questions_answered = Column(JSON)  # Custom questions & answers

    # Error tracking
    error_type = Column(String(100))
    error_message = Column(Text)
    screenshot_path = Column(String(500))  # Screenshot on failure

    # Timing
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Browser session reference
    browser_session_id = Column(String(255))

    # Relationships
    job = relationship("Job", back_populates="applications")


class SkillDiscovery(Base):
    """Skills discovered through contextual questions."""

    __tablename__ = "skill_discoveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    skill_name = Column(String(255), nullable=False)
    proficiency = Column(String(50))  # beginner, intermediate, expert
    context = Column(Text)  # How user described it
    source_job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=True)

    is_confirmed = Column(Boolean, default=False)
    should_include_in_cv = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="skill_discoveries")

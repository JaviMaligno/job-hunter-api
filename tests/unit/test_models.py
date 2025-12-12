"""Tests for database models."""

import uuid
from datetime import datetime

import pytest

from src.db.models import (
    Application,
    ApplicationMode,
    ApplicationStatus,
    BlockerType,
    EmailConnection,
    EmailProvider,
    Job,
    JobStatus,
    Material,
    MaterialType,
    SkillDiscovery,
    User,
)


class TestUserModel:
    """Tests for User model."""

    def test_user_creation(self):
        """Test creating a user instance."""
        user = User(
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            phone="+44123456789",
            city="London",
            country="United Kingdom",
        )

        assert user.email == "test@example.com"
        assert user.first_name == "John"
        assert user.country == "United Kingdom"

    def test_user_explicit_values(self):
        """Test user with explicit values (SQL defaults apply at DB insert time)."""
        user = User(
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            phone_country_code="+44",
            country="United Kingdom",
            preferences={},
        )

        assert user.phone_country_code == "+44"
        assert user.country == "United Kingdom"
        assert user.preferences == {}


class TestJobModel:
    """Tests for Job model."""

    def test_job_creation(self):
        """Test creating a job instance."""
        job = Job(
            user_id=uuid.uuid4(),
            source_url="https://example.com/job/123",
            title="AI Engineer",
            company="TechCorp",
            location="Remote",
            status=JobStatus.INBOX,  # Explicitly set (SQL default applies at DB insert)
        )

        assert job.title == "AI Engineer"
        assert job.status == JobStatus.INBOX

    def test_job_status_transitions(self):
        """Test job status values."""
        assert JobStatus.INBOX.value == "inbox"
        assert JobStatus.INTERESTING.value == "interesting"
        assert JobStatus.ADAPTED.value == "adapted"
        assert JobStatus.READY.value == "ready"
        assert JobStatus.APPLIED.value == "applied"
        assert JobStatus.BLOCKED.value == "blocked"

    def test_blocker_types(self):
        """Test blocker type enum."""
        assert BlockerType.CAPTCHA.value == "captcha"
        assert BlockerType.FILE_UPLOAD.value == "file_upload"
        assert BlockerType.LOGIN_REQUIRED.value == "login_required"


class TestMaterialModel:
    """Tests for Material model."""

    def test_material_types(self):
        """Test material type enum."""
        assert MaterialType.CV.value == "cv"
        assert MaterialType.COVER_LETTER.value == "cover_letter"
        assert MaterialType.TALKING_POINTS.value == "talking_points"

    def test_material_creation(self):
        """Test creating a material instance."""
        material = Material(
            user_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            material_type=MaterialType.CV,
            content="Adapted CV content...",
            changes_made=["Reordered sections", "Added keywords"],
            version=1,  # Explicitly set (SQL default applies at DB insert)
            is_current=True,  # Explicitly set (SQL default applies at DB insert)
        )

        assert material.material_type == MaterialType.CV
        assert material.version == 1
        assert material.is_current is True


class TestApplicationModel:
    """Tests for Application model."""

    def test_application_modes(self):
        """Test application mode enum."""
        assert ApplicationMode.ASSISTED.value == "assisted"
        assert ApplicationMode.SEMI_AUTO.value == "semi_auto"
        assert ApplicationMode.AUTO.value == "auto"

    def test_application_statuses(self):
        """Test application status enum."""
        assert ApplicationStatus.PENDING.value == "pending"
        assert ApplicationStatus.IN_PROGRESS.value == "in_progress"
        assert ApplicationStatus.SUBMITTED.value == "submitted"
        assert ApplicationStatus.FAILED.value == "failed"
        assert ApplicationStatus.NEEDS_INTERVENTION.value == "needs_intervention"


class TestEmailConnectionModel:
    """Tests for EmailConnection model."""

    def test_email_providers(self):
        """Test email provider enum."""
        assert EmailProvider.GMAIL.value == "gmail"
        assert EmailProvider.OUTLOOK.value == "outlook"

    def test_email_connection_creation(self):
        """Test creating email connection."""
        connection = EmailConnection(
            user_id=uuid.uuid4(),
            provider=EmailProvider.GMAIL,
            is_active=True,
        )

        assert connection.provider == EmailProvider.GMAIL
        assert connection.is_active is True


class TestSkillDiscoveryModel:
    """Tests for SkillDiscovery model."""

    def test_skill_discovery_creation(self):
        """Test creating skill discovery."""
        skill = SkillDiscovery(
            user_id=uuid.uuid4(),
            skill_name="Kubernetes",
            proficiency="intermediate",
            context="Used K8s for ML model deployment",
            is_confirmed=False,  # Explicitly set (SQL default applies at DB insert)
            should_include_in_cv=False,  # Explicitly set (SQL default applies at DB insert)
        )

        assert skill.skill_name == "Kubernetes"
        assert skill.is_confirmed is False
        assert skill.should_include_in_cv is False

"""Tests for Application Pipeline improvements."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from src.automation.application_pipeline import (
    ApplicationPipeline,
    ApplicationResult,
    ApplicationAttempt,
    PipelineReport,
)


class TestPipelineConfiguration:
    """Tests for pipeline configuration."""

    def test_default_delay_is_60_seconds(self):
        """Test that default delay between applications is 60 seconds."""
        pipeline = ApplicationPipeline(user_id="test-user")
        assert pipeline.delay_between_apps == 60

    def test_default_max_retries_is_3(self):
        """Test that default max retries is 3."""
        pipeline = ApplicationPipeline(user_id="test-user")
        assert pipeline.max_retries == 3

    def test_default_retry_delay_is_120_seconds(self):
        """Test that default retry delay is 120 seconds."""
        pipeline = ApplicationPipeline(user_id="test-user")
        assert pipeline.retry_delay == 120

    def test_custom_configuration(self):
        """Test that custom configuration is applied."""
        pipeline = ApplicationPipeline(
            user_id="test-user",
            delay_between_apps=90,
            max_retries=5,
            retry_delay=180,
        )

        assert pipeline.delay_between_apps == 90
        assert pipeline.max_retries == 5
        assert pipeline.retry_delay == 180


class TestRetryableErrors:
    """Tests for retryable error detection."""

    def test_retryable_errors_list_exists(self):
        """Test that RETRYABLE_ERRORS class attribute exists."""
        assert hasattr(ApplicationPipeline, "RETRYABLE_ERRORS")
        assert len(ApplicationPipeline.RETRYABLE_ERRORS) > 0

    def test_429_is_retryable(self):
        """Test that 429 errors are considered retryable."""
        pipeline = ApplicationPipeline(user_id="test-user")

        assert pipeline._is_retryable_error("Error 429: Too Many Requests")
        assert pipeline._is_retryable_error("HTTP 429")
        assert pipeline._is_retryable_error("API returned 429")

    def test_rate_limit_is_retryable(self):
        """Test that rate limit errors are retryable."""
        pipeline = ApplicationPipeline(user_id="test-user")

        assert pipeline._is_retryable_error("Rate limit exceeded")
        assert pipeline._is_retryable_error("rate limit reached")
        assert pipeline._is_retryable_error("Too Many Requests")

    def test_taskgroup_is_retryable(self):
        """Test that TaskGroup errors are retryable."""
        pipeline = ApplicationPipeline(user_id="test-user")

        assert pipeline._is_retryable_error("unhandled errors in a TaskGroup (1 sub-exception)")
        assert pipeline._is_retryable_error("TaskGroup failed")

    def test_timeout_is_retryable(self):
        """Test that timeout errors are retryable."""
        pipeline = ApplicationPipeline(user_id="test-user")

        assert pipeline._is_retryable_error("Connection timeout")
        assert pipeline._is_retryable_error("Request timeout after 30s")

    def test_connection_is_retryable(self):
        """Test that connection errors are retryable."""
        pipeline = ApplicationPipeline(user_id="test-user")

        assert pipeline._is_retryable_error("Connection refused")
        assert pipeline._is_retryable_error("connection reset by peer")

    def test_none_is_not_retryable(self):
        """Test that None error is not retryable."""
        pipeline = ApplicationPipeline(user_id="test-user")

        assert not pipeline._is_retryable_error(None)

    def test_permanent_errors_not_retryable(self):
        """Test that permanent errors are not retryable."""
        pipeline = ApplicationPipeline(user_id="test-user")

        assert not pipeline._is_retryable_error("Invalid API key")
        assert not pipeline._is_retryable_error("User not found")
        assert not pipeline._is_retryable_error("Job already applied")


class TestLinkedInSkipLogic:
    """Tests for LinkedIn job skip logic."""

    def test_linkedin_jobs_skipped_without_session(self):
        """Test that LinkedIn jobs are skipped when no session."""
        pipeline = ApplicationPipeline(user_id="test-user")
        pipeline._has_linkedin_session = False

        assert pipeline._should_skip_job("https://linkedin.com/jobs/view/123")
        assert pipeline._should_skip_job("https://www.linkedin.com/jobs/view/456")
        assert pipeline._should_skip_job("https://linkedin.com/comm/jobs/789")

    def test_linkedin_jobs_not_skipped_with_session(self):
        """Test that LinkedIn jobs are attempted when session exists."""
        pipeline = ApplicationPipeline(user_id="test-user")
        pipeline._has_linkedin_session = True

        assert not pipeline._should_skip_job("https://linkedin.com/jobs/view/123")
        assert not pipeline._should_skip_job("https://www.linkedin.com/jobs/view/456")

    def test_indeed_jobs_always_skipped(self):
        """Test that Indeed jobs are always skipped."""
        pipeline = ApplicationPipeline(user_id="test-user")

        # Even with LinkedIn session, Indeed should be skipped
        pipeline._has_linkedin_session = True
        assert pipeline._should_skip_job("https://indeed.com/job/123")
        assert pipeline._should_skip_job("https://www.indeed.com/viewjob?id=456")

        pipeline._has_linkedin_session = False
        assert pipeline._should_skip_job("https://indeed.com/job/123")

    def test_other_jobs_not_skipped(self):
        """Test that other job URLs are not skipped."""
        pipeline = ApplicationPipeline(user_id="test-user")
        pipeline._has_linkedin_session = False

        assert not pipeline._should_skip_job("https://greenhouse.io/job/123")
        assert not pipeline._should_skip_job("https://lever.co/company/job")
        assert not pipeline._should_skip_job("https://workable.com/j/abc")
        assert not pipeline._should_skip_job("https://app.jackandjill.ai/jobs/xyz")


class TestApplicationResult:
    """Tests for ApplicationResult enum."""

    def test_all_result_types_exist(self):
        """Test that all expected result types exist."""
        assert ApplicationResult.SUCCESS.value == "success"
        assert ApplicationResult.PAUSED.value == "paused"
        assert ApplicationResult.BLOCKED.value == "blocked"
        assert ApplicationResult.FAILED.value == "failed"
        assert ApplicationResult.SKIPPED.value == "skipped"
        assert ApplicationResult.JOB_CLOSED.value == "job_closed"


class TestApplicationAttempt:
    """Tests for ApplicationAttempt model."""

    def test_application_attempt_creation(self):
        """Test that ApplicationAttempt can be created."""
        attempt = ApplicationAttempt(
            job_id="test-job-id",
            job_url="https://example.com/job",
            job_title="Software Engineer",
            company="Test Co",
            result=ApplicationResult.SUCCESS,
        )

        assert attempt.job_id == "test-job-id"
        assert attempt.result == ApplicationResult.SUCCESS
        assert attempt.fields_filled == {}
        assert attempt.blocker_type is None

    def test_application_attempt_with_blocker(self):
        """Test ApplicationAttempt with blocker information."""
        attempt = ApplicationAttempt(
            job_id="test-job-id",
            job_url="https://example.com/job",
            job_title="Software Engineer",
            company="Test Co",
            result=ApplicationResult.BLOCKED,
            blocker_type="captcha",
            blocker_message="CAPTCHA detected on page",
        )

        assert attempt.result == ApplicationResult.BLOCKED
        assert attempt.blocker_type == "captcha"
        assert attempt.blocker_message == "CAPTCHA detected on page"


class TestPipelineReport:
    """Tests for PipelineReport model."""

    def test_pipeline_report_creation(self):
        """Test that PipelineReport can be created."""
        report = PipelineReport(started_at="2025-01-01T00:00:00")

        assert report.total_jobs == 0
        assert report.successful == 0
        assert report.paused == 0
        assert report.blocked == 0
        assert report.failed == 0
        assert report.skipped == 0
        assert report.job_closed == 0
        assert report.attempts == []

    def test_pipeline_report_with_attempts(self):
        """Test PipelineReport with attempts."""
        attempt1 = ApplicationAttempt(
            job_id="job1",
            job_url="https://example.com/1",
            job_title="Job 1",
            company="Co1",
            result=ApplicationResult.SUCCESS,
        )
        attempt2 = ApplicationAttempt(
            job_id="job2",
            job_url="https://example.com/2",
            job_title="Job 2",
            company="Co2",
            result=ApplicationResult.BLOCKED,
        )

        report = PipelineReport(
            started_at="2025-01-01T00:00:00",
            total_jobs=2,
            successful=1,
            blocked=1,
            attempts=[attempt1, attempt2],
        )

        assert report.total_jobs == 2
        assert report.successful == 1
        assert report.blocked == 1
        assert len(report.attempts) == 2

"""Tests for Email Parser Agent."""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.email_parser import (
    EmailBatchParserAgent,
    EmailBatchParserInput,
    EmailBatchParserOutput,
    EmailContent,
    EmailParserAgent,
    EmailParserInput,
    EmailParserOutput,
    ExtractedJob,
)


class TestEmailParserAgent:
    """Tests for EmailParserAgent."""

    def test_email_parser_properties(self):
        """Test agent properties."""
        agent = EmailParserAgent(claude_api_key="test-key")

        assert agent.name == "email_parser"
        assert agent.model  # Model is set from settings (Anthropic or Bedrock)
        assert agent.max_tokens == 4096

    def test_email_content_validation(self):
        """Test EmailContent model validation."""
        email = EmailContent(
            subject="New job alert: AI Engineer",
            sender="jobs@linkedin.com",
            body="<html>Job posting content</html>",
            received_at="2024-01-15T10:00:00Z",
            message_id="abc123",
        )

        assert email.subject == "New job alert: AI Engineer"
        assert email.sender == "jobs@linkedin.com"
        assert email.message_id == "abc123"

    def test_email_content_optional_message_id(self):
        """Test EmailContent with optional message_id."""
        email = EmailContent(
            subject="Job alert",
            sender="jobs@indeed.com",
            body="Content here",
            received_at="2024-01-15T10:00:00Z",
        )

        assert email.message_id is None

    def test_extracted_job_validation(self):
        """Test ExtractedJob model validation."""
        job = ExtractedJob(
            title="Senior AI Engineer",
            company="TechCorp",
            location="Remote, Spain",
            job_url="https://linkedin.com/jobs/123",
            source_platform="LinkedIn",
            salary_range="80k-100k EUR",
            job_type="remote",
            brief_description="Build AI systems",
        )

        assert job.title == "Senior AI Engineer"
        assert job.company == "TechCorp"
        assert job.job_type == "remote"

    def test_extracted_job_minimal(self):
        """Test ExtractedJob with minimal required fields."""
        job = ExtractedJob(
            title="ML Engineer",
            company="Startup Inc",
            job_url="https://jobs.lever.co/startup/123",
            source_platform="Lever",
        )

        assert job.title == "ML Engineer"
        assert job.location is None
        assert job.salary_range is None

    def test_email_parser_input_validation(self):
        """Test EmailParserInput validation."""
        email = EmailContent(
            subject="Test",
            sender="test@test.com",
            body="Content",
            received_at="2024-01-15T10:00:00Z",
        )
        parser_input = EmailParserInput(email=email, extract_all=True)

        assert parser_input.extract_all is True

    def test_email_parser_output_validation(self):
        """Test EmailParserOutput validation."""
        output = EmailParserOutput(
            jobs=[
                ExtractedJob(
                    title="AI Engineer",
                    company="TechCorp",
                    job_url="https://example.com/job",
                    source_platform="LinkedIn",
                )
            ],
            source_platform="LinkedIn",
            is_job_alert=True,
            confidence=0.95,
            raw_job_count=1,
        )

        assert len(output.jobs) == 1
        assert output.is_job_alert is True
        assert output.confidence == 0.95

    def test_confidence_bounds(self):
        """Test confidence score bounds validation."""
        # Valid confidence
        output = EmailParserOutput(
            jobs=[],
            source_platform="Unknown",
            is_job_alert=False,
            confidence=0.5,
            raw_job_count=0,
        )
        assert output.confidence == 0.5

        # Edge cases
        output_min = EmailParserOutput(
            jobs=[],
            source_platform="Unknown",
            is_job_alert=False,
            confidence=0.0,
            raw_job_count=0,
        )
        assert output_min.confidence == 0.0

        output_max = EmailParserOutput(
            jobs=[],
            source_platform="Unknown",
            is_job_alert=False,
            confidence=1.0,
            raw_job_count=0,
        )
        assert output_max.confidence == 1.0

    @pytest.mark.asyncio
    async def test_email_parser_run(self):
        """Test email parser execution with mocked Claude response."""
        mock_response = EmailParserOutput(
            jobs=[
                ExtractedJob(
                    title="Data Scientist",
                    company="DataCo",
                    location="Remote",
                    job_url="https://linkedin.com/jobs/456",
                    source_platform="LinkedIn",
                    job_type="remote",
                )
            ],
            source_platform="LinkedIn",
            is_job_alert=True,
            confidence=0.9,
            raw_job_count=1,
        )

        agent = EmailParserAgent(claude_api_key="test-key")

        with patch.object(agent, "_call_claude_json", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response

            email = EmailContent(
                subject="LinkedIn: Data Scientist at DataCo",
                sender="jobs-noreply@linkedin.com",
                body="<html>New job matching your preferences...</html>",
                received_at="2024-01-15T10:00:00Z",
            )
            result = await agent.run(EmailParserInput(email=email))

            assert result.is_job_alert is True
            assert len(result.jobs) == 1
            assert result.jobs[0].title == "Data Scientist"
            mock_call.assert_called_once()


class TestEmailBatchParserAgent:
    """Tests for EmailBatchParserAgent."""

    def test_batch_parser_properties(self):
        """Test batch agent properties."""
        agent = EmailBatchParserAgent(claude_api_key="test-key")

        assert agent.name == "email_batch_parser"
        assert agent.model  # Model is set from settings (Anthropic or Bedrock)
        assert agent.max_tokens == 8192

    def test_batch_input_validation(self):
        """Test EmailBatchParserInput validation."""
        emails = [
            EmailContent(
                subject="Job 1",
                sender="jobs@linkedin.com",
                body="Content 1",
                received_at="2024-01-15T10:00:00Z",
            ),
            EmailContent(
                subject="Job 2",
                sender="jobs@indeed.com",
                body="Content 2",
                received_at="2024-01-15T11:00:00Z",
            ),
        ]
        batch_input = EmailBatchParserInput(emails=emails, filter_job_alerts_only=True)

        assert len(batch_input.emails) == 2
        assert batch_input.filter_job_alerts_only is True

    def test_batch_output_validation(self):
        """Test EmailBatchParserOutput validation."""
        output = EmailBatchParserOutput(
            results=[
                EmailParserOutput(
                    jobs=[],
                    source_platform="LinkedIn",
                    is_job_alert=True,
                    confidence=0.8,
                    raw_job_count=0,
                )
            ],
            total_jobs_found=5,
            platforms_detected=["LinkedIn", "Indeed"],
        )

        assert len(output.results) == 1
        assert output.total_jobs_found == 5
        assert "LinkedIn" in output.platforms_detected


class TestEmailParserPrompt:
    """Tests for email parser prompt building."""

    def test_prompt_contains_email_metadata(self):
        """Test that prompt includes email metadata."""
        agent = EmailParserAgent(claude_api_key="test-key")
        email = EmailContent(
            subject="New AI Jobs",
            sender="alerts@jobsite.com",
            body="Here are new jobs for you...",
            received_at="2024-01-15T10:00:00Z",
        )
        input_data = EmailParserInput(email=email)

        prompt = agent._build_prompt(input_data)

        assert "New AI Jobs" in prompt
        assert "alerts@jobsite.com" in prompt
        assert "Here are new jobs for you..." in prompt

    def test_system_prompt_content(self):
        """Test system prompt contains key instructions."""
        agent = EmailParserAgent(claude_api_key="test-key")

        system_prompt = agent.system_prompt

        assert "job alerts" in system_prompt.lower()
        assert "LinkedIn" in system_prompt
        assert "InfoJobs" in system_prompt
        assert "confidence" in system_prompt.lower()

"""Unit tests for agents."""

from unittest.mock import MagicMock, patch

import pytest

from src.agents.cv_adapter import (
    CoverLetterAgent,
    CoverLetterInput,
    CoverLetterOutput,
    CVAdapterAgent,
    CVAdapterInput,
    CVAdapterOutput,
)


class TestCVAdapterAgent:
    """Tests for CV Adapter Agent."""

    @pytest.mark.asyncio
    async def test_cv_adapter_properties(self):
        """Test agent properties."""
        with patch("src.agents.base.get_claude_client"):
            agent = CVAdapterAgent(claude_api_key="test-key")

        assert agent.name == "cv-adapter"
        assert "CV optimization" in agent.system_prompt

    @pytest.mark.asyncio
    async def test_cv_adapter_input_validation(self, sample_cv, sample_job_description):
        """Test input model validation."""
        input_data = CVAdapterInput(
            base_cv=sample_cv,
            job_description=sample_job_description,
            job_title="AI Engineer",
            company="SOULCHI",
            language="en",
        )

        assert input_data.base_cv == sample_cv
        assert input_data.language == "en"

    @pytest.mark.asyncio
    async def test_cv_adapter_output_validation(self, cv_adapter_output_json):
        """Test output model validation."""
        output = CVAdapterOutput.model_validate_json(cv_adapter_output_json)

        assert output.match_score == 85
        assert len(output.changes_made) == 3
        assert "Python" in output.skills_matched
        assert len(output.key_highlights) == 3

    @pytest.mark.asyncio
    async def test_cv_adapter_run(self, sample_cv, sample_job_description, cv_adapter_output_json):
        """Test full CV adaptation run with mocked Claude."""
        with patch("src.agents.base.get_claude_client") as mock_get_client:
            # Setup mock
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(type="text", text=cv_adapter_output_json)]
            mock_response.usage = MagicMock(input_tokens=500, output_tokens=800)
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            # Run agent
            agent = CVAdapterAgent(claude_api_key="test-key")
            input_data = CVAdapterInput(
                base_cv=sample_cv,
                job_description=sample_job_description,
                job_title="AI Engineer",
                company="SOULCHI",
            )

            # Patch the langfuse context to avoid tracing during tests
            with patch("src.agents.base.langfuse_context"):
                result = await agent.run(input_data)

            assert isinstance(result, CVAdapterOutput)
            assert result.match_score == 85
            assert "Python" in result.skills_matched

    @pytest.mark.asyncio
    async def test_cv_adapter_language_spanish(self):
        """Test CV adaptation with Spanish language."""
        input_data = CVAdapterInput(
            base_cv="CV en español...",
            job_description="Descripción del puesto...",
            job_title="Ingeniero de IA",
            company="Empresa",
            language="es",
        )

        assert input_data.language == "es"


class TestCoverLetterAgent:
    """Tests for Cover Letter Agent."""

    @pytest.mark.asyncio
    async def test_cover_letter_properties(self):
        """Test agent properties."""
        with patch("src.agents.base.get_claude_client"):
            agent = CoverLetterAgent(claude_api_key="test-key")

        assert agent.name == "cover-letter"
        assert "cover letter" in agent.system_prompt.lower()

    @pytest.mark.asyncio
    async def test_cover_letter_input_validation(self, sample_cv, sample_job_description):
        """Test input model validation."""
        input_data = CoverLetterInput(
            cv_content=sample_cv,
            job_description=sample_job_description,
            job_title="AI Engineer",
            company="SOULCHI",
            language="en",
            tone="professional",
        )

        assert input_data.tone == "professional"
        assert input_data.language == "en"

    @pytest.mark.asyncio
    async def test_cover_letter_output_validation(self):
        """Test output model validation."""
        output_json = """{
            "cover_letter": "Dear Hiring Manager,\\n\\nI am excited to apply...",
            "key_points": ["Multi-agent experience", "PhD background"],
            "talking_points": ["Discuss LangGraph project", "Explain RAG pipeline work"]
        }"""

        output = CoverLetterOutput.model_validate_json(output_json)

        assert "Dear Hiring Manager" in output.cover_letter
        assert len(output.key_points) == 2
        assert len(output.talking_points) == 2


class TestCVAdapterOutputModel:
    """Tests for CVAdapterOutput Pydantic model."""

    def test_match_score_validation(self):
        """Test match score bounds."""
        # Valid scores
        output = CVAdapterOutput(
            adapted_cv="test",
            match_score=85,
            changes_made=[],
            skills_matched=[],
            skills_missing=[],
            key_highlights=[],
        )
        assert output.match_score == 85

        # Boundary values
        output_min = CVAdapterOutput(
            adapted_cv="test",
            match_score=0,
            changes_made=[],
            skills_matched=[],
            skills_missing=[],
            key_highlights=[],
        )
        assert output_min.match_score == 0

        output_max = CVAdapterOutput(
            adapted_cv="test",
            match_score=100,
            changes_made=[],
            skills_matched=[],
            skills_missing=[],
            key_highlights=[],
        )
        assert output_max.match_score == 100

    def test_match_score_out_of_bounds(self):
        """Test match score rejects out of bounds values."""
        with pytest.raises(ValueError):
            CVAdapterOutput(
                adapted_cv="test",
                match_score=101,  # Over 100
                changes_made=[],
                skills_matched=[],
                skills_missing=[],
                key_highlights=[],
            )

        with pytest.raises(ValueError):
            CVAdapterOutput(
                adapted_cv="test",
                match_score=-1,  # Below 0
                changes_made=[],
                skills_matched=[],
                skills_missing=[],
                key_highlights=[],
            )

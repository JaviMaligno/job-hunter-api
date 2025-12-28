"""Pytest configuration and fixtures."""

import os
from unittest.mock import MagicMock, patch

import pytest
from anthropic import Anthropic

# Set test environment
os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_data/test.db"


@pytest.fixture
def mock_anthropic_response():
    """Create a mock Anthropic API response."""

    def _create_response(text: str, input_tokens: int = 100, output_tokens: int = 200):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text=text)]
        mock_response.usage = MagicMock(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        return mock_response

    return _create_response


@pytest.fixture
def mock_claude_client(mock_anthropic_response):
    """Create a mock Claude client."""
    with patch("src.integrations.claude.client.Anthropic") as mock_class:
        mock_client = MagicMock(spec=Anthropic)
        mock_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def sample_cv():
    """Sample CV content for testing."""
    return """
# Javier Aguilar Martín

**AI & ML Engineer** | London, UK | javiecija96@gmail.com

## Summary
AI & ML Engineer with 5+ years of experience building intelligent systems.
PhD in Mathematics with focus on optimization algorithms.

## Experience

### Senior ML Engineer | TechCorp | 2021-Present
- Designed and deployed multi-agent AI systems using LangGraph
- Built RAG pipelines with PydanticAI and Langfuse for observability
- Reduced inference latency by 40% through model optimization

### ML Engineer | DataStart | 2019-2021
- Developed NLP models for document classification
- Implemented MLOps pipelines with Azure ML

## Skills
- Languages: Python, TypeScript, SQL
- ML/AI: PyTorch, LangChain, PydanticAI, LangGraph
- Cloud: Azure, GCP, AWS
- Tools: Docker, Kubernetes, Git

## Education
- PhD Mathematics, University of Seville, 2019
- MSc Computer Science, University of Seville, 2016
"""


@pytest.fixture
def sample_job_description():
    """Sample job description for testing."""
    return """
# AI Engineer - Conversational AI

**Company:** SOULCHI
**Location:** Remote (Europe)

## About the Role
We're looking for an AI Engineer to build next-generation conversational AI systems.

## Requirements
- 3+ years experience with LLMs and NLP
- Strong Python skills
- Experience with multi-agent systems
- Familiarity with LangChain, LangGraph, or similar frameworks
- Cloud experience (AWS/GCP/Azure)

## Nice to Have
- PhD in relevant field
- Experience with RAG systems
- Startup experience

## What We Offer
- Competitive equity compensation
- Remote-first culture
- Cutting-edge AI projects
"""


@pytest.fixture
def cv_adapter_output_json():
    """Expected JSON output from CV adapter."""
    return """{
    "adapted_cv": "# Javier Aguilar Martín\\n\\n**AI & ML Engineer specialized in Conversational AI**...",
    "match_score": 85,
    "changes_made": [
        "Reordered experience to highlight multi-agent systems work",
        "Added emphasis on LangGraph and PydanticAI experience",
        "Updated summary to focus on conversational AI"
    ],
    "skills_matched": [
        "Python",
        "LangGraph",
        "Multi-agent systems",
        "Cloud (Azure, GCP, AWS)",
        "PhD"
    ],
    "skills_missing": [
        "Direct conversational AI experience not explicitly mentioned"
    ],
    "key_highlights": [
        "Multi-agent AI systems experience directly relevant",
        "PhD in Mathematics shows strong analytical foundation",
        "RAG pipeline experience aligns with their tech stack"
    ]
}"""

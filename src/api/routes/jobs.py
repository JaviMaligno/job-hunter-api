"""Job-related API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from src.agents.cv_adapter import (
    CoverLetterAgent,
    CoverLetterInput,
    CVAdapterAgent,
    CVAdapterInput,
)
from src.api.dependencies import ClaudeDep
from src.api.schemas import CVAdaptRequest, CVAdaptResponse

router = APIRouter()


@router.post("/adapt", response_model=CVAdaptResponse)
async def adapt_cv_for_job(
    request: CVAdaptRequest,
    claude: ClaudeDep,
):
    """
    Adapt a CV for a specific job posting.

    This endpoint:
    1. Takes a job description and CV content
    2. Uses AI to analyze requirements and adapt the CV
    3. Generates a cover letter
    4. Returns adapted materials with match analysis

    Requires X-Anthropic-Api-Key header or configured ANTHROPIC_API_KEY.
    """
    if not request.job_description and not request.job_url:
        raise HTTPException(
            status_code=400,
            detail="Either job_description or job_url must be provided",
        )

    if not request.cv_content:
        raise HTTPException(
            status_code=400,
            detail="cv_content is required (user base CV support coming soon)",
        )

    # Get job description from URL if needed
    job_description = request.job_description
    if not job_description and request.job_url:
        # TODO: Implement web scraping for job description
        raise HTTPException(
            status_code=501,
            detail="Job URL scraping not yet implemented. Please provide job_description directly.",
        )

    # Adapt CV
    cv_agent = CVAdapterAgent(claude_api_key=claude.api_key)
    cv_input = CVAdapterInput(
        base_cv=request.cv_content,
        job_description=job_description,
        job_title=request.job_title,
        company=request.company,
        language=request.language,
    )
    cv_result = await cv_agent.run(cv_input)

    # Generate cover letter
    cover_agent = CoverLetterAgent(claude_api_key=claude.api_key)
    cover_input = CoverLetterInput(
        cv_content=cv_result.adapted_cv,
        job_description=job_description,
        job_title=request.job_title,
        company=request.company,
        language=request.language,
    )
    cover_result = await cover_agent.run(cover_input)

    return CVAdaptResponse(
        adapted_cv=cv_result.adapted_cv,
        cover_letter=cover_result.cover_letter,
        match_score=cv_result.match_score,
        changes_made=cv_result.changes_made,
        skills_matched=cv_result.skills_matched,
        skills_missing=cv_result.skills_missing,
        key_highlights=cv_result.key_highlights + cover_result.talking_points,
    )


@router.get("/")
async def list_jobs(
    status: Annotated[str | None, Query(description="Filter by status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """
    List jobs in the pipeline.

    TODO: Implement with database integration.
    """
    return {
        "jobs": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "message": "Database integration coming soon",
    }


@router.get("/{job_id}")
async def get_job(job_id: UUID):
    """
    Get a specific job by ID.

    TODO: Implement with database integration.
    """
    raise HTTPException(
        status_code=501,
        detail="Database integration coming soon",
    )


@router.post("/")
async def create_job():
    """
    Create a new job in the pipeline.

    TODO: Implement with database integration.
    """
    raise HTTPException(
        status_code=501,
        detail="Database integration coming soon",
    )


@router.patch("/{job_id}")
async def update_job(job_id: UUID):
    """
    Update a job's status or details.

    TODO: Implement with database integration.
    """
    raise HTTPException(
        status_code=501,
        detail="Database integration coming soon",
    )

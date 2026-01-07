"""Job-related API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from src.agents.cv_adapter import (
    CoverLetterAgent,
    CoverLetterInput,
    CVAdapterAgent,
    CVAdapterInput,
)
from src.api.dependencies import ClaudeDep, DbDep
from src.api.schemas import (
    CVAdaptRequest,
    CVAdaptResponse,
    JobCreate,
    JobListResponse,
    JobResponse,
    JobUpdate,
)
from src.db.models import Job, JobStatus

router = APIRouter()


# ============================================================================
# Job Import Schema
# ============================================================================


class JobImportRequest(BaseModel):
    """Request to import a job from URL."""

    url: str


class JobImportResponse(BaseModel):
    """Response from job import."""

    job: JobResponse
    message: str
    scraped_fields: list[str]  # Fields successfully scraped from the URL


# ============================================================================
# Job CRUD Endpoints
# ============================================================================


@router.get("/", response_model=JobListResponse)
async def list_jobs(
    db: DbDep,
    user_id: Annotated[UUID, Query(description="User ID to filter jobs")],
    status: Annotated[str | None, Query(description="Filter by status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """List jobs in the pipeline for a user."""
    # Build query
    query = select(Job).where(Job.user_id == user_id)

    if status:
        try:
            status_enum = JobStatus(status)
            query = query.filter(Job.status == status_enum)
        except ValueError:
            pass  # Invalid status, ignore filter

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(Job.created_at.desc()).offset(offset).limit(page_size)

    # Execute query
    result = await db.execute(query)
    jobs = result.scalars().all()

    return JobListResponse(
        jobs=[JobResponse.model_validate(job) for job in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: UUID, db: DbDep):
    """Get a specific job by ID."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse.model_validate(job)


@router.post("/", response_model=JobResponse)
async def create_job(
    job_data: JobCreate,
    db: DbDep,
    user_id: Annotated[UUID, Query(description="User ID for the job")],
):
    """Create a new job in the pipeline."""
    job = Job(
        user_id=user_id,
        source_url=job_data.source_url,
        title=job_data.title,
        company=job_data.company,
        location=job_data.location,
        job_type=job_data.job_type,
        description_raw=job_data.description_raw,
        source_platform=job_data.source_platform,
        status=JobStatus.INBOX,
    )

    db.add(job)
    await db.flush()
    await db.refresh(job)

    return JobResponse.model_validate(job)


@router.post("/import-url", response_model=JobImportResponse)
async def import_job_from_url(
    request: JobImportRequest,
    db: DbDep,
    user_id: Annotated[UUID, Query(description="User ID for the job")],
    skip_scraping: Annotated[bool, Query(description="Skip scraping and just save URL")] = False,
):
    """
    Import a job from a URL.

    Scrapes the job page to extract title, company, description, and other details.
    Set skip_scraping=true to skip scraping and just save the URL.
    """
    from src.integrations.jobs.scraper import scrape_job_url

    # Scrape job details from URL
    scraped = None
    scrape_message = ""

    if not skip_scraping:
        scraped = await scrape_job_url(request.url)
        if not scraped.success:
            scrape_message = f" (Scraping failed: {scraped.error})"

    # Create job with scraped or placeholder data
    job = Job(
        user_id=user_id,
        source_url=request.url,
        title=scraped.title if scraped and scraped.title else "Job Opening",
        company=scraped.company if scraped else None,
        location=scraped.location if scraped else None,
        job_type=scraped.job_type if scraped else None,
        description_raw=scraped.description if scraped else None,
        source_platform=scraped.platform if scraped else "unknown",
        status=JobStatus.INBOX,
    )

    db.add(job)
    await db.flush()
    await db.refresh(job)

    # Build list of successfully scraped fields
    scraped_fields: list[str] = []
    if scraped and scraped.success:
        if scraped.title:
            scraped_fields.append("title")
        if scraped.company:
            scraped_fields.append("company")
        if scraped.location:
            scraped_fields.append("location")
        if scraped.description:
            scraped_fields.append("description")
        if scraped.job_type:
            scraped_fields.append("job_type")
        if scraped.salary:
            scraped_fields.append("salary")

    platform = scraped.platform if scraped else "unknown"
    if scraped and scraped.success and scraped.title:
        message = f"Job imported successfully from {platform.title()}."
    else:
        message = f"Job imported from {platform.title()}.{scrape_message} You can edit the job to add more details."

    return JobImportResponse(
        job=JobResponse.model_validate(job),
        message=message,
        scraped_fields=scraped_fields,
    )


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(job_id: UUID, updates: JobUpdate, db: DbDep):
    """Update a job's status or details."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Apply updates
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(job, field, value)

    await db.flush()
    await db.refresh(job)

    return JobResponse.model_validate(job)


@router.delete("/{job_id}")
async def delete_job(job_id: UUID, db: DbDep):
    """Delete a job from the pipeline."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    await db.delete(job)
    await db.flush()

    return {"message": "Job deleted successfully"}


# ============================================================================
# CV Adaptation Endpoint
# ============================================================================


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
    import logging

    logger = logging.getLogger(__name__)
    logger.info("CV adapt endpoint called")

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
        # Scrape job description from URL
        from src.integrations.jobs.scraper import scrape_job_url

        logger.info(f"Scraping job description from URL: {request.job_url}")
        scraped = await scrape_job_url(request.job_url)

        if scraped.success and scraped.description:
            job_description = scraped.description
            logger.info(f"Successfully scraped job description ({len(job_description)} chars)")
            # Also use scraped title/company if not provided
            if not request.job_title and scraped.title:
                request.job_title = scraped.title
            if not request.company and scraped.company:
                request.company = scraped.company
        else:
            error_msg = scraped.error or "Could not extract job description from URL"
            logger.warning(f"Scraping failed: {error_msg}")
            raise HTTPException(
                status_code=422,
                detail=f"Could not scrape job from URL: {error_msg}. Please provide job_description directly.",
            )

    # Get API key if available (Anthropic has api_key, AnthropicBedrock doesn't)
    api_key = getattr(claude, "api_key", None)

    try:
        # Adapt CV
        logger.info("Creating CV adapter agent")
        cv_agent = CVAdapterAgent(claude_api_key=api_key)
        cv_input = CVAdapterInput(
            base_cv=request.cv_content,
            job_description=job_description,
            job_title=request.job_title,
            company=request.company,
            language=request.language,
        )
        logger.info("Running CV adapter agent")
        cv_result = await cv_agent.run(cv_input)
        logger.info(f"CV adaptation complete, match_score: {cv_result.match_score}")

        # Generate cover letter
        logger.info("Creating cover letter agent")
        cover_agent = CoverLetterAgent(claude_api_key=api_key)
        cover_input = CoverLetterInput(
            cv_content=cv_result.adapted_cv,
            job_description=job_description,
            job_title=request.job_title,
            company=request.company,
            language=request.language,
        )
        logger.info("Running cover letter agent")
        cover_result = await cover_agent.run(cover_input)
        logger.info("Cover letter generation complete")

        return CVAdaptResponse(
            adapted_cv=cv_result.adapted_cv,
            cover_letter=cover_result.cover_letter,
            match_score=cv_result.match_score,
            changes_made=cv_result.changes_made,
            skills_matched=cv_result.skills_matched,
            skills_missing=cv_result.skills_missing,
            key_highlights=cv_result.key_highlights + cover_result.talking_points,
        )
    except Exception as e:
        logger.exception(f"Error in CV adaptation: {e}")
        raise HTTPException(status_code=500, detail=f"CV adaptation failed: {str(e)}")

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
    MaterialCreate,
    MaterialListResponse,
    MaterialResponse,
)
from src.db.models import Job, JobStatus, MaterialType
from src.db.repositories.material import MaterialRepository

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


@router.get("/search", response_model=JobListResponse)
async def search_jobs(
    db: DbDep,
    user_id: Annotated[UUID, Query(description="User ID to filter jobs")],
    q: Annotated[str | None, Query(description="Search query for title, company, location")] = None,
    status: Annotated[str | None, Query(description="Filter by status")] = None,
    company: Annotated[str | None, Query(description="Filter by company")] = None,
    location: Annotated[str | None, Query(description="Filter by location")] = None,
    min_match_score: Annotated[int | None, Query(description="Minimum match score")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Search jobs with text query and filters."""
    from sqlalchemy import or_

    # Build query
    query = select(Job).where(Job.user_id == user_id)

    # Apply text search
    if q:
        search_term = f"%{q}%"
        query = query.where(
            or_(
                Job.title.ilike(search_term),
                Job.company.ilike(search_term),
                Job.location.ilike(search_term),
                Job.description_raw.ilike(search_term),
            )
        )

    # Apply status filter
    if status:
        try:
            status_enum = JobStatus(status)
            query = query.where(Job.status == status_enum)
        except ValueError:
            pass  # Invalid status, ignore filter

    # Apply company filter
    if company:
        query = query.where(Job.company.ilike(f"%{company}%"))

    # Apply location filter
    if location:
        query = query.where(Job.location.ilike(f"%{location}%"))

    # Apply match score filter
    if min_match_score is not None:
        query = query.where(Job.match_score >= min_match_score)

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
    db: DbDep,
):
    """
    Adapt a CV for a specific job posting.

    This endpoint:
    1. Takes a job description and CV content
    2. Uses AI to analyze requirements and adapt the CV
    3. Generates a cover letter
    4. Optionally saves materials to database if job_id provided
    5. Returns adapted materials with match analysis

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
        # Adapt CV (language auto-detected if not specified)
        logger.info("Creating CV adapter agent")
        cv_agent = CVAdapterAgent(claude_api_key=api_key)
        cv_input = CVAdapterInput(
            base_cv=request.cv_content,
            job_description=job_description,
            job_title=request.job_title,
            company=request.company,
            language=request.language,  # None for auto-detect, or user override
        )
        logger.info("Running CV adapter agent")
        cv_result = await cv_agent.run(cv_input)
        logger.info(f"CV adaptation complete, match_score: {cv_result.match_score}, detected_language: {cv_result.detected_language}")

        # Generate cover letter using detected language
        logger.info("Creating cover letter agent")
        cover_agent = CoverLetterAgent(claude_api_key=api_key)
        cover_input = CoverLetterInput(
            cv_content=cv_result.adapted_cv,
            job_description=job_description,
            job_title=request.job_title,
            company=request.company,
            language=cv_result.detected_language,  # Use detected language from CV adapter
        )
        logger.info("Running cover letter agent")
        cover_result = await cover_agent.run(cover_input)
        logger.info("Cover letter generation complete")

        # Save materials to database if job_id is provided
        material_ids: list[UUID] = []
        saved_job_id = request.job_id

        if request.job_id:
            logger.info(f"Saving materials to job {request.job_id}")
            # Verify job exists and get user_id
            job = await db.get(Job, request.job_id)
            if not job:
                logger.warning(f"Job {request.job_id} not found, materials will not be saved")
            else:
                repo = MaterialRepository(db)

                # Save adapted CV
                cv_material = await repo.create_new_version(
                    job_id=request.job_id,
                    user_id=job.user_id,
                    material_type=MaterialType.CV,
                    content=cv_result.adapted_cv,
                    changes_made=cv_result.changes_made,
                    changes_explanation=f"Match score: {cv_result.match_score}%. Skills matched: {', '.join(cv_result.skills_matched)}",
                )
                material_ids.append(cv_material.id)
                logger.info(f"Saved CV material {cv_material.id}")

                # Save cover letter
                cover_material = await repo.create_new_version(
                    job_id=request.job_id,
                    user_id=job.user_id,
                    material_type=MaterialType.COVER_LETTER,
                    content=cover_result.cover_letter,
                    changes_made=cover_result.talking_points,
                    changes_explanation=f"Generated for {request.company} - {request.job_title}",
                )
                material_ids.append(cover_material.id)
                logger.info(f"Saved cover letter material {cover_material.id}")

                await db.commit()
                logger.info(f"Committed {len(material_ids)} materials to database")

        return CVAdaptResponse(
            detected_language=cv_result.detected_language,
            adapted_cv=cv_result.adapted_cv,
            cover_letter=cover_result.cover_letter,
            match_score=cv_result.match_score,
            changes_made=cv_result.changes_made,
            skills_matched=cv_result.skills_matched,
            skills_missing=cv_result.skills_missing,
            key_highlights=cv_result.key_highlights + cover_result.talking_points,
            job_id=saved_job_id,
            material_ids=material_ids if material_ids else None,
        )
    except Exception as e:
        logger.exception(f"Error in CV adaptation: {e}")
        raise HTTPException(status_code=500, detail=f"CV adaptation failed: {str(e)}")


# ============================================================================
# Material Endpoints
# ============================================================================


@router.get("/{job_id}/materials", response_model=MaterialListResponse)
async def get_job_materials(
    job_id: UUID,
    db: DbDep,
    material_type: MaterialType | None = None,
):
    """Get all materials for a job.

    Returns all current versions of materials (CV, cover letter, etc.)
    generated for this job.
    """
    # Verify job exists
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    repo = MaterialRepository(db)
    materials = await repo.get_by_job(job_id, material_type=material_type)

    return MaterialListResponse(
        materials=[MaterialResponse.model_validate(m) for m in materials],
        job_id=job_id,
    )


@router.post("/{job_id}/materials", response_model=MaterialResponse)
async def create_job_material(
    job_id: UUID,
    request: MaterialCreate,
    db: DbDep,
):
    """Create or update a material for a job.

    Creates a new version of the material. If a previous version exists,
    it will be marked as non-current.
    """
    # Verify job exists and get user_id
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    repo = MaterialRepository(db)
    material = await repo.create_new_version(
        job_id=job_id,
        user_id=job.user_id,
        material_type=request.material_type,
        content=request.content,
        changes_made=request.changes_made,
        changes_explanation=request.changes_explanation,
    )

    await db.commit()
    return MaterialResponse.model_validate(material)


@router.get("/{job_id}/materials/{material_type}", response_model=MaterialResponse)
async def get_job_material_by_type(
    job_id: UUID,
    material_type: MaterialType,
    db: DbDep,
):
    """Get the current version of a specific material type for a job."""
    repo = MaterialRepository(db)
    material = await repo.get_current_version(job_id, material_type)

    if not material:
        raise HTTPException(
            status_code=404,
            detail=f"No {material_type.value} found for this job",
        )

    return MaterialResponse.model_validate(material)


@router.get("/{job_id}/materials/{material_type}/versions", response_model=list[MaterialResponse])
async def get_material_versions(
    job_id: UUID,
    material_type: MaterialType,
    db: DbDep,
):
    """Get all versions of a specific material type for a job."""
    repo = MaterialRepository(db)
    materials = await repo.get_all_versions(job_id, material_type)

    return [MaterialResponse.model_validate(m) for m in materials]


# ============================================================================
# Skill Enhancement Endpoint
# ============================================================================


class EnhanceMaterialRequest(BaseModel):
    """Request to enhance a CV with a new skill."""

    skill: str
    explanation: str
    material_id: UUID | None = None  # If not provided, use current CV


@router.post("/{job_id}/materials/enhance", response_model=MaterialResponse)
async def enhance_material_with_skill(
    job_id: UUID,
    request: EnhanceMaterialRequest,
    db: DbDep,
    claude: ClaudeDep,
):
    """
    Enhance a CV material by adding a new skill.

    This endpoint:
    1. Gets the current CV material for the job (or specified material)
    2. Uses SkillEnhancerAgent to enhance the CV with the new skill
    3. Saves the result as a new material version
    4. Returns the new material

    Requires X-Anthropic-Api-Key header or configured ANTHROPIC_API_KEY.
    """
    import logging

    from src.agents.skill_enhancer import SkillEnhancerAgent, SkillEnhancerInput

    logger = logging.getLogger(__name__)
    logger.info(f"Enhance material endpoint called for job {job_id}")

    # Verify job exists and get user_id
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    repo = MaterialRepository(db)

    # Get the material to enhance
    if request.material_id:
        # Get specific material by ID
        material = await repo.get(request.material_id)
        if not material:
            raise HTTPException(status_code=404, detail="Material not found")
        if material.job_id != job_id:
            raise HTTPException(
                status_code=400,
                detail="Material does not belong to this job",
            )
    else:
        # Get current CV for the job
        material = await repo.get_current_version(job_id, MaterialType.CV)
        if not material:
            raise HTTPException(
                status_code=404,
                detail="No CV found for this job. Please create an adapted CV first.",
            )

    # Get API key if available (Anthropic has api_key, AnthropicBedrock doesn't)
    api_key = getattr(claude, "api_key", None)

    try:
        # Enhance the CV with the new skill
        logger.info(f"Creating skill enhancer agent for skill: {request.skill}")
        enhancer_agent = SkillEnhancerAgent(claude_api_key=api_key)
        enhancer_input = SkillEnhancerInput(
            cv_content=material.content,
            skill=request.skill,
            explanation=request.explanation,
        )
        logger.info("Running skill enhancer agent")
        result = await enhancer_agent.run(enhancer_input)
        logger.info("Skill enhancement complete")

        # Save the enhanced CV as a new version
        new_material = await repo.create_new_version(
            job_id=job_id,
            user_id=job.user_id,
            material_type=MaterialType.CV,
            content=result.enhanced_cv,
            changes_made=result.changes_made,
            changes_explanation=f"Added skill: {request.skill}",
        )

        await db.commit()
        logger.info(f"Saved enhanced CV material {new_material.id}")

        return MaterialResponse.model_validate(new_material)

    except Exception as e:
        logger.exception(f"Error in skill enhancement: {e}")
        raise HTTPException(status_code=500, detail=f"Skill enhancement failed: {str(e)}")


# ============================================================================
# Document Generation Endpoint
# ============================================================================


class DocumentGenerateRequest(BaseModel):
    """Request to generate a downloadable document."""

    content: str
    format: str  # "docx" or "pdf"
    doc_type: str  # "cv" or "cover_letter"
    job_title: str | None = None
    company: str | None = None
    candidate_name: str | None = None


@router.post("/documents/generate")
async def generate_document(request: DocumentGenerateRequest):
    """
    Generate a downloadable document (DOCX or PDF) from content.

    This endpoint:
    1. Takes adapted CV or cover letter content
    2. Generates a formatted document in the requested format
    3. Returns the document as a downloadable file
    """
    from fastapi.responses import Response

    from src.services.document_generator import (
        DocumentFormat,
        DocumentGenerator,
        DocumentMetadata,
        DocumentType,
    )

    # Validate format
    try:
        doc_format = DocumentFormat(request.format)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format: {request.format}. Must be 'docx' or 'pdf'",
        )

    # Validate document type
    try:
        doc_type = DocumentType(request.doc_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid doc_type: {request.doc_type}. Must be 'cv' or 'cover_letter'",
        )

    # Create metadata
    metadata = DocumentMetadata(
        job_title=request.job_title,
        company=request.company,
        candidate_name=request.candidate_name,
    )

    # Generate document
    generator = DocumentGenerator()
    doc_bytes = generator.generate(request.content, doc_format, doc_type, metadata)

    # Set content type and filename
    if doc_format == DocumentFormat.DOCX:
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"
    else:
        content_type = "application/pdf"
        ext = "pdf"

    # Create filename
    type_name = "CV" if doc_type == DocumentType.CV else "CoverLetter"
    company_slug = request.company.replace(" ", "_") if request.company else "document"
    filename = f"{type_name}_{company_slug}.{ext}"

    return Response(
        content=doc_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

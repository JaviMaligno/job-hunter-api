"""Email processing pipeline service.

Orchestrates the full pipeline: email parsing -> job extraction -> CV adaptation
-> cover letter generation -> application automation.
"""

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from anthropic import Anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.cv_adapter import (
    CoverLetterAgent,
    CoverLetterInput,
    CVAdapterAgent,
    CVAdapterInput,
)
from src.config import settings
from src.db.models import Job, JobStatus, User
from src.integrations.email.parser import ExtractedJob, parse_job_email

logger = logging.getLogger(__name__)


def _clean_email_html(html_content: str, max_length: int = 15000) -> str:
    """Simple HTML cleaning for email content using BeautifulSoup only."""
    import re
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_content, "html.parser")

    # Remove script, style, and other noise elements
    for tag in soup.find_all(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    # Extract text with some structure preserved
    text = soup.get_text(separator="\n", strip=True)

    # Clean up excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)

    # Truncate if needed
    if len(text) > max_length:
        text = text[:max_length]

    return text.strip()


async def parse_email_with_gemini(
    body: str, subject: str, sender: str
) -> list[ExtractedJob]:
    """Parse email content using Gemini AI for better extraction.

    Falls back to empty list if Gemini is not configured or fails.
    """
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY not configured, skipping AI parsing")
        return []

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)

        # Clean HTML for better parsing (using simple BeautifulSoup-based cleaning)
        cleaned_body = _clean_email_html(body, max_length=15000)

        prompt = f"""Extract job postings from this email alert.

Email Subject: {subject}
Email From: {sender}

Email Content:
{cleaned_body}

For each job found, extract:
- title: Job title
- company: Company name
- location: Location (city, country, or "Remote")
- job_url: Application URL if available

Return a JSON array of jobs. Example:
[{{"title": "Software Engineer", "company": "Google", "location": "London, UK", "job_url": "https://..."}}]

If no jobs are found, return an empty array: []
Only return valid JSON, no markdown or explanation."""

        # Try with available Gemini models
        models = ["gemini-2.0-flash", "gemini-1.5-flash"]

        for model_name in models:
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=4096,
                    ),
                )

                if response.text:
                    import json
                    # Clean response
                    text = response.text.strip()
                    if text.startswith("```json"):
                        text = text[7:]
                    if text.startswith("```"):
                        text = text[3:]
                    if text.endswith("```"):
                        text = text[:-3]
                    text = text.strip()

                    jobs_data = json.loads(text)

                    if not isinstance(jobs_data, list):
                        jobs_data = [jobs_data]

                    extracted = []
                    for job in jobs_data:
                        if job.get("title"):
                            extracted.append(ExtractedJob(
                                title=job.get("title", ""),
                                company=job.get("company", "Unknown"),
                                location=job.get("location"),
                                job_url=job.get("job_url"),
                                source_platform="linkedin" if "linkedin" in sender.lower() else "email",
                            ))

                    if extracted:
                        logger.info(f"Gemini extracted {len(extracted)} jobs from email")
                        return extracted

            except Exception as e:
                logger.warning(f"Gemini model {model_name} failed: {e}")
                continue

        return []

    except Exception as e:
        logger.exception(f"Gemini email parsing failed: {e}")
        return []


@dataclass
class PipelineOptions:
    """Options for controlling the email processing pipeline."""

    save_job: bool = True
    adapt_cv: bool = False
    generate_cover_letter: bool = False
    start_application: bool = False
    language: str = "en"
    devtools_url: str | None = None


@dataclass
class PipelineResult:
    """Result from processing an email through the pipeline."""

    success: bool
    email_subject: str | None = None
    email_sender: str | None = None
    email_received_at: str | None = None
    message_id: str | None = None

    # Extraction results
    jobs_extracted: list[dict[str, Any]] | None = None
    job_id: UUID | None = None
    job_title: str | None = None
    job_company: str | None = None
    job_url: str | None = None

    # CV adaptation results
    adapted_cv: str | None = None
    match_score: int | None = None
    skills_matched: list[str] | None = None
    skills_missing: list[str] | None = None

    # Cover letter results
    cover_letter: str | None = None

    # Application results
    application_session_id: str | None = None
    application_status: str | None = None

    # Errors
    errors: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "email_subject": self.email_subject,
            "email_sender": self.email_sender,
            "email_received_at": self.email_received_at,
            "message_id": self.message_id,
            "jobs_extracted": self.jobs_extracted,
            "job_id": str(self.job_id) if self.job_id else None,
            "job_title": self.job_title,
            "job_company": self.job_company,
            "job_url": self.job_url,
            "adapted_cv": self.adapted_cv,
            "match_score": self.match_score,
            "skills_matched": self.skills_matched,
            "skills_missing": self.skills_missing,
            "cover_letter": self.cover_letter,
            "application_session_id": self.application_session_id,
            "application_status": self.application_status,
            "errors": self.errors,
        }


class EmailPipelineService:
    """Orchestrates single email processing through the job pipeline.

    This service handles:
    1. Email parsing to extract job information
    2. Job saving to database
    3. CV adaptation for the job
    4. Cover letter generation
    5. Application automation (optional)
    """

    def __init__(
        self,
        db: AsyncSession,
        claude_client: Anthropic | None = None,
    ):
        """Initialize the pipeline service.

        Args:
            db: Database session for persistence
            claude_client: Optional Anthropic client (uses default if not provided)
        """
        self.db = db
        self.claude_client = claude_client

    async def process_email(
        self,
        email_content: dict[str, Any],
        user_id: UUID,
        options: PipelineOptions,
    ) -> PipelineResult:
        """Process a single email through the job pipeline.

        Args:
            email_content: Email data with keys: subject, body, sender, message_id, received_at
            user_id: User ID for database operations
            options: Pipeline options controlling which steps to run

        Returns:
            PipelineResult with extraction and processing results
        """
        errors: list[str] = []

        # Initialize result with email info
        result = PipelineResult(
            success=True,
            email_subject=email_content.get("subject"),
            email_sender=email_content.get("sender"),
            email_received_at=email_content.get("received_at"),
            message_id=email_content.get("message_id"),
        )

        # Step 1: Extract jobs from email
        try:
            body = email_content.get("body", "")
            sender = email_content.get("sender", "")
            subject = email_content.get("subject", "")

            # Try regex parsing first (fast, no API cost)
            extracted_jobs = parse_job_email(
                body=body,
                sender=sender,
                subject=subject,
            )

            # If regex fails, try Gemini AI parsing
            if not extracted_jobs:
                logger.info("Regex parsing found no jobs, trying Gemini AI...")
                extracted_jobs = await parse_email_with_gemini(body, subject, sender)

            result.jobs_extracted = [
                {
                    "title": j.title,
                    "company": j.company,
                    "location": j.location,
                    "job_url": j.job_url,
                    "source_platform": j.source_platform,
                }
                for j in extracted_jobs
            ]

            if not extracted_jobs:
                result.errors = ["No jobs found in email"]
                return result

            logger.info(f"Extracted {len(extracted_jobs)} jobs from email")

        except Exception as e:
            logger.exception(f"Error extracting jobs from email: {e}")
            result.success = False
            result.errors = [f"Job extraction failed: {str(e)}"]
            return result

        # Use the first job with a URL (or first job if none have URLs)
        job = next((j for j in extracted_jobs if j.job_url), extracted_jobs[0])
        result.job_title = job.title
        result.job_company = job.company
        result.job_url = job.job_url

        # Step 2: Save job to database if requested
        if options.save_job and job.job_url:
            try:
                # Check for duplicates
                existing = await self.db.execute(
                    select(Job).where(
                        Job.user_id == user_id,
                        Job.source_url == job.job_url,
                    )
                )
                existing_job = existing.scalar_one_or_none()

                if existing_job:
                    result.job_id = existing_job.id
                    errors.append(f"Job already exists: {existing_job.id}")
                else:
                    db_job = Job(
                        user_id=user_id,
                        source_url=job.job_url,
                        title=job.title,
                        company=job.company,
                        location=job.location,
                        source_platform=job.source_platform,
                        source_email_id=email_content.get("message_id"),
                        status=JobStatus.INBOX,
                    )
                    self.db.add(db_job)
                    await self.db.flush()
                    await self.db.refresh(db_job)
                    result.job_id = db_job.id
                    logger.info(f"Saved job to database: {db_job.id}")

            except Exception as e:
                logger.exception(f"Error saving job to database: {e}")
                errors.append(f"Failed to save job: {str(e)}")

        # Step 3: Adapt CV if requested
        if options.adapt_cv:
            try:
                cv_result = await self._adapt_cv(
                    user_id=user_id,
                    job_title=job.title,
                    job_company=job.company,
                    job_description=None,  # We don't have description yet
                    job_url=job.job_url,
                    language=options.language,
                    generate_cover_letter=options.generate_cover_letter,
                )

                result.adapted_cv = cv_result.get("adapted_cv")
                result.match_score = cv_result.get("match_score")
                result.skills_matched = cv_result.get("skills_matched")
                result.skills_missing = cv_result.get("skills_missing")

                if options.generate_cover_letter:
                    result.cover_letter = cv_result.get("cover_letter")

                logger.info(f"CV adapted with match score: {result.match_score}")

            except Exception as e:
                logger.exception(f"Error adapting CV: {e}")
                errors.append(f"CV adaptation failed: {str(e)}")

        # Step 4: Start application if requested
        if options.start_application and result.job_id:
            try:
                app_result = await self._start_application(
                    user_id=user_id,
                    job_id=result.job_id,
                    devtools_url=options.devtools_url,
                )
                result.application_session_id = app_result.get("session_id")
                result.application_status = app_result.get("status")
                logger.info(f"Application started: {result.application_session_id}")

            except Exception as e:
                logger.exception(f"Error starting application: {e}")
                errors.append(f"Application start failed: {str(e)}")

        if errors:
            result.errors = errors

        return result

    async def _adapt_cv(
        self,
        user_id: UUID,
        job_title: str,
        job_company: str,
        job_description: str | None,
        job_url: str | None,
        language: str,
        generate_cover_letter: bool = True,
    ) -> dict[str, Any]:
        """Adapt CV for a job using AI agents.

        Args:
            user_id: User to get base CV from
            job_title: Job title
            job_company: Company name
            job_description: Full job description (if available)
            job_url: Job URL to scrape if no description
            language: Output language (en/es)
            generate_cover_letter: Whether to also generate cover letter

        Returns:
            Dictionary with adapted_cv, cover_letter, match_score, etc.
        """
        # Get user's base CV
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user or not user.base_cv_content:
            raise ValueError("User has no base CV configured")

        # Get job description if not provided
        if not job_description and job_url:
            # Try to scrape job description
            try:
                from src.integrations.jobs.scraper import scrape_job_url

                scraped = await scrape_job_url(job_url)
                if scraped:
                    job_description = scraped.get("description", "")
            except Exception as e:
                logger.warning(f"Could not scrape job URL: {e}")

        # If still no description, use minimal info
        if not job_description:
            job_description = f"Job Title: {job_title}\nCompany: {job_company}"

        # Get API key from Claude client
        api_key = getattr(self.claude_client, "api_key", None) if self.claude_client else None

        # Adapt CV
        cv_agent = CVAdapterAgent(claude_api_key=api_key)
        cv_input = CVAdapterInput(
            base_cv=user.base_cv_content,
            job_description=job_description,
            job_title=job_title,
            company=job_company,
            language=language,
        )
        cv_result = await cv_agent.run(cv_input)

        result = {
            "adapted_cv": cv_result.adapted_cv,
            "match_score": cv_result.match_score,
            "skills_matched": cv_result.skills_matched,
            "skills_missing": cv_result.skills_missing,
            "changes_made": cv_result.changes_made,
        }

        # Generate cover letter if requested
        if generate_cover_letter:
            cover_agent = CoverLetterAgent(claude_api_key=api_key)
            cover_input = CoverLetterInput(
                cv_content=cv_result.adapted_cv,
                job_description=job_description,
                job_title=job_title,
                company=job_company,
                language=language,
            )
            cover_result = await cover_agent.run(cover_input)
            result["cover_letter"] = cover_result.cover_letter

        return result

    async def _start_application(
        self,
        user_id: UUID,
        job_id: UUID,
        devtools_url: str | None = None,
    ) -> dict[str, Any]:
        """Start an automatic application for a job.

        Args:
            user_id: User ID
            job_id: Job ID to apply for
            devtools_url: Chrome DevTools URL (default: http://localhost:9222)

        Returns:
            Dictionary with session_id and status
        """
        # This would integrate with the existing application system
        # For now, return a placeholder indicating it's not fully implemented
        logger.warning("Application automation not yet integrated in pipeline")

        return {
            "session_id": None,
            "status": "not_implemented",
            "message": "Application automation not yet integrated. Use /api/applications/v2/start directly.",
        }

"""
Job Application Automation Pipeline.

This module provides automated job application capabilities:
1. Fetch jobs from database (extracted from Gmail)
2. Attempt to apply using Gemini + Chrome MCP
3. Track results with detailed logging
4. Update job status based on outcomes
"""

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("application_pipeline")


class ApplicationResult(str, Enum):
    """Result of an application attempt."""
    SUCCESS = "success"  # Application submitted
    PAUSED = "paused"  # Paused for review before submit
    BLOCKED = "blocked"  # Hit a blocker (CAPTCHA, login, etc.)
    FAILED = "failed"  # Error during application
    SKIPPED = "skipped"  # Job not suitable for automation
    JOB_CLOSED = "job_closed"  # Position no longer available


class ApplicationAttempt(BaseModel):
    """Record of a single application attempt."""
    job_id: str
    job_url: str
    job_title: str
    company: str | None
    result: ApplicationResult
    session_id: str | None = None
    fields_filled: dict[str, str] = Field(default_factory=dict)
    blocker_type: str | None = None
    blocker_message: str | None = None
    error_message: str | None = None
    duration_seconds: float = 0
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class PipelineReport(BaseModel):
    """Summary report of pipeline execution."""
    started_at: str
    completed_at: str | None = None
    total_jobs: int = 0
    successful: int = 0
    paused: int = 0
    blocked: int = 0
    failed: int = 0
    skipped: int = 0
    job_closed: int = 0
    attempts: list[ApplicationAttempt] = Field(default_factory=list)


class ApplicationPipeline:
    """
    Automated job application pipeline.

    Connects email-extracted jobs with the automation system.
    """

    # Errors that should trigger automatic retry
    RETRYABLE_ERRORS = [
        "429",
        "too many requests",
        "rate limit",
        "taskgroup",
        "timeout",
        "connection",
        "temporary",
    ]

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        user_id: str | None = None,
        max_applications: int = 5,
        delay_between_apps: int = 60,  # Increased from 30 to avoid rate limiting
        auto_submit: bool = False,
        max_retries: int = 3,
        retry_delay: int = 120,  # Base delay between retries (2 minutes)
    ):
        """
        Initialize the pipeline.

        Args:
            api_url: Backend API URL
            user_id: User ID for fetching jobs
            max_applications: Maximum applications per run
            delay_between_apps: Seconds between applications
            auto_submit: Whether to auto-submit (False = pause for review)
            max_retries: Maximum retry attempts for temporary errors
            retry_delay: Base delay between retries (exponential backoff applied)
        """
        self.api_url = api_url
        self.user_id = user_id
        self.max_applications = max_applications
        self.delay_between_apps = delay_between_apps
        self.auto_submit = auto_submit
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self.report = PipelineReport(started_at=datetime.utcnow().isoformat())
        self._user_data: dict | None = None
        self._cv_content: str | None = None
        self._has_linkedin_session: bool = False  # Will be set when LinkedIn is connected

    async def _get_http_client(self):
        """Get HTTP client."""
        import httpx
        return httpx.AsyncClient(timeout=300.0)

    async def load_user_data(self) -> bool:
        """Load user profile and CV from database."""
        if not self.user_id:
            logger.error("No user_id provided")
            return False

        async with await self._get_http_client() as client:
            # Get user profile
            try:
                response = await client.get(f"{self.api_url}/api/users/{self.user_id}")
                if response.status_code != 200:
                    logger.error(f"Failed to load user: {response.status_code}")
                    return False

                user = response.json()
                self._user_data = {
                    "first_name": user.get("first_name", ""),
                    "last_name": user.get("last_name", ""),
                    "email": user.get("email", ""),
                    "phone": user.get("phone", ""),
                    "phone_country_code": user.get("phone_country_code", "+44"),
                    "linkedin_url": user.get("linkedin_url"),
                    "github_url": user.get("github_url"),
                    "portfolio_url": user.get("portfolio_url"),
                    "country": user.get("country", "United Kingdom"),
                    "city": user.get("city"),
                }
                self._cv_content = user.get("base_cv_content", "")

                logger.info(f"Loaded user: {self._user_data['first_name']} {self._user_data['last_name']}")

                # Check if LinkedIn is connected
                try:
                    linkedin_response = await client.get(
                        f"{self.api_url}/api/linkedin/status/{self.user_id}"
                    )
                    if linkedin_response.status_code == 200:
                        linkedin_status = linkedin_response.json()
                        self._has_linkedin_session = linkedin_status.get("connected", False)
                        if self._has_linkedin_session:
                            logger.info("LinkedIn connected - will attempt LinkedIn job applications")
                        else:
                            logger.info("LinkedIn not connected - LinkedIn jobs will be skipped")
                except Exception as e:
                    logger.warning(f"Could not check LinkedIn status: {e}")
                    self._has_linkedin_session = False

                return True

            except Exception as e:
                logger.error(f"Error loading user: {e}")
                return False

    async def get_jobs_to_apply(self, statuses: list[str] = None) -> list[dict]:
        """
        Fetch jobs that are ready for application.

        Args:
            statuses: Job statuses to include (default: inbox, interesting)
        """
        if statuses is None:
            statuses = ["inbox", "interesting"]

        jobs = []
        async with await self._get_http_client() as client:
            for status in statuses:
                try:
                    response = await client.get(
                        f"{self.api_url}/api/jobs/",
                        params={
                            "user_id": self.user_id,
                            "status": status,
                            "page_size": 50,
                        }
                    )
                    if response.status_code == 200:
                        data = response.json()
                        jobs.extend(data.get("jobs", []))
                except Exception as e:
                    logger.warning(f"Error fetching {status} jobs: {e}")

        logger.info(f"Found {len(jobs)} jobs to process")
        return jobs

    def _is_retryable_error(self, error_message: str | None) -> bool:
        """Check if an error is temporary and should be retried."""
        if not error_message:
            return False
        error_lower = error_message.lower()
        return any(pattern in error_lower for pattern in self.RETRYABLE_ERRORS)

    async def apply_to_job(self, job: dict, retry_count: int = 0) -> ApplicationAttempt:
        """
        Attempt to apply to a single job with automatic retry for temporary errors.

        Args:
            job: Job data from database
            retry_count: Current retry attempt (0 = first try)

        Returns:
            ApplicationAttempt with results
        """
        start_time = datetime.utcnow()
        job_id = job["id"]
        job_url = job["source_url"]
        job_title = job.get("title", "Unknown")
        company = job.get("company")

        logger.info(f"=" * 60)
        logger.info(f"Applying to: {job_title} at {company or 'Unknown'}")
        logger.info(f"URL: {job_url}")
        logger.info(f"=" * 60)

        attempt = ApplicationAttempt(
            job_id=job_id,
            job_url=job_url,
            job_title=job_title,
            company=company,
            result=ApplicationResult.FAILED,
        )

        # Skip certain URLs that can't be automated
        if self._should_skip_job(job_url):
            attempt.result = ApplicationResult.SKIPPED
            attempt.error_message = "URL not suitable for automation"
            logger.warning(f"Skipping: {attempt.error_message}")
            return attempt

        async with await self._get_http_client() as client:
            try:
                # Call v2/start endpoint
                request_data = {
                    "job_url": job_url,
                    "user_data": self._user_data,
                    "cv_content": self._cv_content,
                    "agent": "gemini",
                    "mode": "auto" if self.auto_submit else "assisted",
                    "auto_solve_captcha": True,
                    "max_steps": 30,
                }

                logger.info("Sending application request...")
                response = await client.post(
                    f"{self.api_url}/api/applications/v2/start",
                    json=request_data,
                )

                if response.status_code != 200:
                    attempt.result = ApplicationResult.FAILED
                    attempt.error_message = f"API error: {response.status_code} - {response.text}"
                    logger.error(attempt.error_message)
                else:
                    result = response.json()
                    attempt.session_id = result.get("session_id")
                    attempt.fields_filled = {
                        f.get("field_name", "unknown"): f.get("value", "")
                        for f in result.get("fields_filled", [])
                    } if isinstance(result.get("fields_filled"), list) else result.get("fields_filled", {})

                    # Determine result based on status
                    status = result.get("status", "failed")
                    blocker = result.get("blocker_type")
                    blocker_details = result.get("blocker_details")

                    if status == "submitted":
                        attempt.result = ApplicationResult.SUCCESS
                        logger.info(f"✅ SUCCESS: Application submitted!")
                    elif status == "paused":
                        attempt.result = ApplicationResult.PAUSED
                        logger.info(f"⏸️ PAUSED: Ready for review")
                    elif status == "needs_intervention":
                        attempt.result = ApplicationResult.BLOCKED
                        attempt.blocker_type = blocker
                        attempt.blocker_message = blocker_details
                        if "no longer" in (blocker_details or "").lower() or "closed" in (blocker_details or "").lower():
                            attempt.result = ApplicationResult.JOB_CLOSED
                            logger.warning(f"🚫 JOB CLOSED: {blocker_details}")
                        else:
                            logger.warning(f"⚠️ BLOCKED: {blocker} - {blocker_details}")
                    else:
                        attempt.result = ApplicationResult.FAILED
                        attempt.error_message = result.get("error") or f"Status: {status}"
                        logger.error(f"❌ FAILED: {attempt.error_message}")

                    # Log fields filled
                    if attempt.fields_filled:
                        logger.info(f"Fields filled: {len(attempt.fields_filled)}")
                        for field, value in attempt.fields_filled.items():
                            logger.debug(f"  - {field}: {value[:50]}..." if len(str(value)) > 50 else f"  - {field}: {value}")

                # Update job status in database
                await self._update_job_status(client, job_id, attempt)

            except Exception as e:
                attempt.result = ApplicationResult.FAILED
                attempt.error_message = str(e)
                logger.exception(f"Exception during application: {e}")

        # Calculate duration
        attempt.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Duration: {attempt.duration_seconds:.1f}s")

        # Check if we should retry on temporary errors
        if (
            attempt.result == ApplicationResult.FAILED
            and self._is_retryable_error(attempt.error_message)
            and retry_count < self.max_retries
        ):
            retry_wait = self.retry_delay * (retry_count + 1)  # Exponential backoff
            logger.warning(
                f"🔄 Retryable error detected. Waiting {retry_wait}s before retry "
                f"({retry_count + 1}/{self.max_retries})..."
            )
            await asyncio.sleep(retry_wait)
            return await self.apply_to_job(job, retry_count + 1)

        return attempt

    def _should_skip_job(self, url: str) -> bool:
        """Check if job URL should be skipped."""
        url_lower = url.lower()

        # LinkedIn jobs - only skip if user doesn't have LinkedIn connected
        if "linkedin.com" in url_lower:
            if self._has_linkedin_session:
                # User has LinkedIn OAuth, we can try to apply
                return False
            else:
                # No LinkedIn connection, skip
                return True

        # Indeed still requires manual login - always skip
        if "indeed.com" in url_lower:
            return True

        return False

    async def _update_job_status(self, client, job_id: str, attempt: ApplicationAttempt):
        """Update job status based on application result."""
        status_map = {
            ApplicationResult.SUCCESS: "applied",
            ApplicationResult.PAUSED: "ready",
            ApplicationResult.BLOCKED: "blocked",
            ApplicationResult.FAILED: "inbox",  # Keep in inbox for retry
            ApplicationResult.SKIPPED: "inbox",
            ApplicationResult.JOB_CLOSED: "archived",
        }

        new_status = status_map.get(attempt.result, "inbox")
        blocker_type = None
        blocker_details = None

        if attempt.result == ApplicationResult.BLOCKED:
            blocker_type = attempt.blocker_type or "unknown"
            blocker_details = attempt.blocker_message

        try:
            update_data = {"status": new_status}
            if blocker_type:
                update_data["blocker_type"] = blocker_type
            if blocker_details:
                update_data["blocker_details"] = blocker_details

            await client.patch(
                f"{self.api_url}/api/jobs/{job_id}",
                json=update_data,
            )
            logger.info(f"Updated job status to: {new_status}")
        except Exception as e:
            logger.warning(f"Failed to update job status: {e}")

    async def run(self, job_ids: list[str] = None) -> PipelineReport:
        """
        Run the application pipeline.

        Args:
            job_ids: Specific job IDs to process (None = all eligible)

        Returns:
            PipelineReport with results
        """
        logger.info("=" * 60)
        logger.info("STARTING APPLICATION PIPELINE")
        logger.info("=" * 60)

        # Load user data
        if not await self.load_user_data():
            logger.error("Failed to load user data, aborting")
            self.report.completed_at = datetime.utcnow().isoformat()
            return self.report

        # Get jobs to process
        if job_ids:
            # Fetch specific jobs
            jobs = []
            async with await self._get_http_client() as client:
                for job_id in job_ids:
                    try:
                        response = await client.get(f"{self.api_url}/api/jobs/{job_id}")
                        if response.status_code == 200:
                            jobs.append(response.json())
                    except Exception as e:
                        logger.warning(f"Failed to fetch job {job_id}: {e}")
        else:
            jobs = await self.get_jobs_to_apply()

        # Filter out already applied/blocked
        jobs = [j for j in jobs if j.get("status") not in ["applied", "blocked", "rejected", "archived"]]

        # Limit to max_applications
        jobs = jobs[:self.max_applications]
        self.report.total_jobs = len(jobs)

        logger.info(f"Processing {len(jobs)} jobs")

        # Process each job
        for i, job in enumerate(jobs, 1):
            logger.info(f"\n[{i}/{len(jobs)}] Processing job...")

            attempt = await self.apply_to_job(job)
            self.report.attempts.append(attempt)

            # Update counters
            if attempt.result == ApplicationResult.SUCCESS:
                self.report.successful += 1
            elif attempt.result == ApplicationResult.PAUSED:
                self.report.paused += 1
            elif attempt.result == ApplicationResult.BLOCKED:
                self.report.blocked += 1
            elif attempt.result == ApplicationResult.FAILED:
                self.report.failed += 1
            elif attempt.result == ApplicationResult.SKIPPED:
                self.report.skipped += 1
            elif attempt.result == ApplicationResult.JOB_CLOSED:
                self.report.job_closed += 1

            # Delay between applications
            if i < len(jobs):
                logger.info(f"Waiting {self.delay_between_apps}s before next application...")
                await asyncio.sleep(self.delay_between_apps)

        self.report.completed_at = datetime.utcnow().isoformat()

        # Print summary
        self._print_summary()

        return self.report

    def _print_summary(self):
        """Print pipeline summary."""
        logger.info("\n" + "=" * 60)
        logger.info("PIPELINE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total jobs processed: {self.report.total_jobs}")
        logger.info(f"✅ Successful:        {self.report.successful}")
        logger.info(f"⏸️  Paused (review):   {self.report.paused}")
        logger.info(f"⚠️  Blocked:          {self.report.blocked}")
        logger.info(f"❌ Failed:            {self.report.failed}")
        logger.info(f"⏭️  Skipped:          {self.report.skipped}")
        logger.info(f"🚫 Job closed:        {self.report.job_closed}")
        logger.info("=" * 60)

        # List blocked jobs with reasons
        blocked = [a for a in self.report.attempts if a.result == ApplicationResult.BLOCKED]
        if blocked:
            logger.info("\nBLOCKED JOBS:")
            for a in blocked:
                logger.info(f"  - {a.job_title}: {a.blocker_type} - {a.blocker_message}")

    def save_report(self, path: str | Path = None) -> Path:
        """Save report to JSON file."""
        if path is None:
            path = Path("data/reports")
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        filename = f"pipeline_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = path / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.report.model_dump(), f, indent=2, default=str)

        logger.info(f"Report saved to: {filepath}")
        return filepath


async def run_pipeline(
    user_id: str,
    max_applications: int = 5,
    delay_seconds: int = 30,
    auto_submit: bool = False,
    job_ids: list[str] = None,
) -> PipelineReport:
    """
    Convenience function to run the pipeline.

    Args:
        user_id: User ID
        max_applications: Max applications per run
        delay_seconds: Delay between applications
        auto_submit: Auto-submit without review
        job_ids: Specific job IDs (None = all eligible)
    """
    pipeline = ApplicationPipeline(
        user_id=user_id,
        max_applications=max_applications,
        delay_between_apps=delay_seconds,
        auto_submit=auto_submit,
    )

    report = await pipeline.run(job_ids=job_ids)
    pipeline.save_report()

    return report

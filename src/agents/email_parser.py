"""Email Parser Agent for extracting job postings from email alerts."""

from pydantic import BaseModel, Field

from src.agents.base import BaseAgent


class EmailContent(BaseModel):
    """Raw email content to parse."""

    subject: str = Field(description="Email subject line")
    sender: str = Field(description="Email sender address")
    body: str = Field(description="Email body content (HTML or plain text)")
    received_at: str = Field(description="Timestamp when email was received")
    message_id: str | None = Field(default=None, description="Unique email message ID")


class ExtractedJob(BaseModel):
    """A single job extracted from an email."""

    title: str = Field(description="Job title")
    company: str = Field(description="Company name")
    location: str | None = Field(default=None, description="Job location")
    job_url: str = Field(description="URL to the job posting")
    source_platform: str = Field(description="Platform that sent the alert (LinkedIn, InfoJobs, etc.)")
    salary_range: str | None = Field(default=None, description="Salary range if mentioned")
    job_type: str | None = Field(default=None, description="Remote, hybrid, onsite")
    brief_description: str | None = Field(default=None, description="Brief job description if available")


class EmailParserInput(BaseModel):
    """Input for email parser agent."""

    email: EmailContent = Field(description="Email content to parse")
    extract_all: bool = Field(
        default=True,
        description="Extract all jobs from email (newsletters may have multiple)",
    )


class EmailParserOutput(BaseModel):
    """Output from email parser agent."""

    jobs: list[ExtractedJob] = Field(description="List of extracted jobs")
    source_platform: str = Field(description="Detected email source (LinkedIn, InfoJobs, etc.)")
    is_job_alert: bool = Field(description="Whether this email is a job alert")
    confidence: float = Field(ge=0, le=1, description="Confidence score for extraction")
    raw_job_count: int = Field(description="Number of jobs found in the email")


class EmailParserAgent(BaseAgent[EmailParserOutput]):
    """Agent that parses job alert emails and extracts job information."""

    def __init__(self, claude_api_key: str | None = None):
        super().__init__(
            claude_api_key=claude_api_key,
            max_tokens=4096,
        )

    @property
    def name(self) -> str:
        return "email_parser"

    @property
    def system_prompt(self) -> str:
        return """You are an expert email parser specializing in job alerts and recruitment emails.

Your task is to:
1. Determine if the email is a job alert/newsletter from a job platform
2. Extract all job postings mentioned in the email
3. Identify the source platform (LinkedIn, InfoJobs, Indeed, Glassdoor, Jack&Jill, etc.)
4. Extract as much information as possible for each job

IMPORTANT EXTRACTION RULES:
- Job URLs must be complete and valid - extract the actual application URL when possible
- If the email contains tracking URLs (e.g., LinkedIn redirects), try to identify the actual job URL
- Company names should be cleaned (remove "hiring" or similar suffixes)
- Location should be normalized (e.g., "Remote - Spain" → "Remote, Spain")
- Detect job type from context (remote, hybrid, onsite)

COMMON JOB ALERT FORMATS:
- LinkedIn: Multiple jobs per email, uses tracking URLs
- InfoJobs: Usually single job per email, Spanish format
- Indeed: Digest format with multiple jobs
- Glassdoor: Similar to LinkedIn
- Recruiter emails: Usually single opportunity

OUTPUT REQUIREMENTS:
- Set is_job_alert=false for non-job emails
- If is_job_alert=false, return empty jobs list
- confidence should reflect extraction quality (1.0 = perfect, 0.5 = partial, 0.0 = failed)"""

    async def _execute(self, input_data: EmailParserInput) -> EmailParserOutput:
        """Parse email and extract job postings."""
        prompt = self._build_prompt(input_data)
        return await self._call_claude_json(
            prompt=prompt,
            output_model=EmailParserOutput,
        )

    def _build_prompt(self, input_data: EmailParserInput) -> str:
        email = input_data.email
        return f"""Parse the following email and extract job posting information.

EMAIL METADATA:
- Subject: {email.subject}
- From: {email.sender}
- Received: {email.received_at}

EMAIL BODY:
{email.body}

---

Instructions:
1. First, determine if this is a job alert email
2. If yes, extract ALL job postings {"" if input_data.extract_all else "(only the first/main one)"}
3. For each job, extract: title, company, location, URL, job type, salary (if available)
4. Identify the source platform from the sender/content
5. Provide a confidence score for your extraction

Return the results in the specified JSON format."""


class EmailBatchParserInput(BaseModel):
    """Input for batch email parsing."""

    emails: list[EmailContent] = Field(description="List of emails to parse")
    filter_job_alerts_only: bool = Field(
        default=True,
        description="Only return results for actual job alerts",
    )


class EmailBatchParserOutput(BaseModel):
    """Output from batch email parsing."""

    results: list[EmailParserOutput] = Field(description="Parsing results per email")
    total_jobs_found: int = Field(description="Total jobs found across all emails")
    platforms_detected: list[str] = Field(description="Unique platforms detected")


class EmailBatchParserAgent(BaseAgent[EmailBatchParserOutput]):
    """Agent that parses multiple emails in batch."""

    def __init__(self, claude_api_key: str | None = None):
        super().__init__(
            claude_api_key=claude_api_key,
            max_tokens=8192,
        )
        self._single_parser = EmailParserAgent(claude_api_key)

    @property
    def name(self) -> str:
        return "email_batch_parser"

    @property
    def system_prompt(self) -> str:
        return "Batch email parser - delegates to individual parser."

    async def _execute(self, input_data: EmailBatchParserInput) -> EmailBatchParserOutput:
        """Parse multiple emails and aggregate results."""
        results = []
        total_jobs = 0
        platforms = set()

        for email in input_data.emails:
            parser_input = EmailParserInput(email=email, extract_all=True)
            result = await self._single_parser.run(parser_input)

            if input_data.filter_job_alerts_only and not result.is_job_alert:
                continue

            results.append(result)
            total_jobs += result.raw_job_count
            platforms.add(result.source_platform)

        return EmailBatchParserOutput(
            results=results,
            total_jobs_found=total_jobs,
            platforms_detected=list(platforms),
        )

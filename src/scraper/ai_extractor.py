"""AI-powered job extraction using Google Gemini (google-genai SDK).

Uses function calling for guaranteed structured JSON output.
"""

import json
import logging
from dataclasses import dataclass

from google import genai
from google.genai import types

from src.config import settings
from src.scraper.content_cleaner import clean_html_for_extraction

logger = logging.getLogger(__name__)


@dataclass
class AIExtractedJob:
    """AI-extracted job data."""

    title: str
    company: str | None = None
    location: str | None = None
    description: str | None = None
    salary_range: str | None = None
    job_type: str | None = None
    requirements: list[str] | None = None
    remote_type: str | None = None  # "remote", "hybrid", "onsite"
    easy_apply: bool | None = None  # True if LinkedIn Easy Apply or similar
    employment_type: str | None = None  # "full-time", "part-time", "contract", "internship"
    model_used: str | None = None


# Model priority list - Best quality first, with fallbacks for availability
GEMINI_MODELS = [
    "gemini-3-flash-preview",  # Best quality, 3x faster than 2.5 Pro (free tier: 5k/month)
    "gemini-2.5-flash",  # Very good fallback
    "gemini-2.5-pro",  # High quality fallback
    "gemini-2.0-flash",  # Stable fallback
]

# Function declaration for structured output via tool calling
EXTRACT_JOB_FUNCTION = types.FunctionDeclaration(
    name="extract_job_data",
    description="Extract structured job posting information from the content",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "title": types.Schema(
                type=types.Type.STRING,
                description="The job title (e.g., 'Senior Software Engineer')",
            ),
            "company": types.Schema(
                type=types.Type.STRING,
                description="The company or organization name",
                nullable=True,
            ),
            "location": types.Schema(
                type=types.Type.STRING,
                description="Job location (city, state, country, or 'Remote')",
                nullable=True,
            ),
            "description": types.Schema(
                type=types.Type.STRING,
                description="Summary of job responsibilities and role description",
                nullable=True,
            ),
            "salary_range": types.Schema(
                type=types.Type.STRING,
                description="Salary range if mentioned (e.g., '$100k - $150k')",
                nullable=True,
            ),
            "job_type": types.Schema(
                type=types.Type.STRING,
                description="Employment type (Full-time, Part-time, Contract, etc.)",
                nullable=True,
            ),
            "requirements": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description="List of key requirements, skills, and qualifications",
                nullable=True,
            ),
            "remote_type": types.Schema(
                type=types.Type.STRING,
                enum=["remote", "hybrid", "onsite"],
                description="Work arrangement type",
                nullable=True,
            ),
            "easy_apply": types.Schema(
                type=types.Type.BOOLEAN,
                description="True if LinkedIn Easy Apply or similar quick apply is available",
                nullable=True,
            ),
            "employment_type": types.Schema(
                type=types.Type.STRING,
                enum=["full-time", "part-time", "contract", "internship"],
                description="Type of employment",
                nullable=True,
            ),
        },
        required=["title"],
    ),
)

EXTRACTION_PROMPT = """You are a job posting data extractor. Analyze the following content from a job posting page.

Extract the job information and call the extract_job_data function with the extracted data.

Important guidelines:
- Extract the actual job title, not the page title
- For description, provide a concise summary of the role and responsibilities
- For requirements, extract specific skills, experience, and qualifications mentioned
- For remote_type, determine if the job is "remote", "hybrid", or "onsite" based on the content
- For easy_apply, set to true if LinkedIn Easy Apply, quick apply, or similar one-click application is available
- For employment_type, determine if it's "full-time", "part-time", "contract", or "internship"
- If a field is not clearly stated, pass null

Content to analyze:
"""


class GeminiExtractor:
    """Extracts job data from HTML using Google Gemini with function calling."""

    def __init__(self):
        """Initialize the Gemini extractor."""
        self._client: genai.Client | None = None

    def _ensure_client(self) -> genai.Client:
        """Ensure Gemini client is created with API key."""
        if self._client is not None:
            return self._client

        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not configured")

        self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    async def extract(self, html_content: str, url: str) -> AIExtractedJob:
        """
        Extract job data from HTML content using Gemini.

        Args:
            html_content: The HTML or text content of the job page
            url: The source URL (for context)

        Returns:
            AIExtractedJob with extracted data

        Raises:
            ValueError: If extraction fails with all models
        """
        client = self._ensure_client()

        # Clean and optimize the content for LLM extraction
        cleaned_content = clean_html_for_extraction(html_content, max_length=25000)
        logger.debug(f"Cleaned content: {len(html_content)} -> {len(cleaned_content)} chars")

        prompt = f"{EXTRACTION_PROMPT}\n\nURL: {url}\n\n{cleaned_content}"

        last_error = None

        for model_name in GEMINI_MODELS:
            try:
                logger.info(f"Trying Gemini model: {model_name}")

                # Try function calling first (guaranteed structured output)
                result = await self._try_function_calling(client, model_name, prompt)
                if result:
                    result.model_used = model_name
                    logger.info(f"Successfully extracted with {model_name} (function calling)")
                    return result

                # Fallback to text-based extraction
                result = await self._try_text_extraction(client, model_name, prompt)
                if result:
                    result.model_used = model_name
                    logger.info(f"Successfully extracted with {model_name} (text)")
                    return result

            except Exception as e:
                logger.warning(f"Model {model_name} failed: {e}")
                last_error = e
                continue

        raise ValueError(f"All Gemini models failed. Last error: {last_error}")

    async def _try_function_calling(
        self, client: genai.Client, model_name: str, prompt: str
    ) -> AIExtractedJob | None:
        """Try extraction using function calling for structured output."""
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=4096,
                    tools=[types.Tool(function_declarations=[EXTRACT_JOB_FUNCTION])],
                    tool_config=types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(
                            mode="ANY",
                        )
                    ),
                ),
            )

            # Extract function call result
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        args = dict(part.function_call.args)

                        if not args.get("title"):
                            logger.warning("No title in function call response")
                            return None

                        return AIExtractedJob(
                            title=args.get("title"),
                            company=args.get("company"),
                            location=args.get("location"),
                            description=args.get("description"),
                            salary_range=args.get("salary_range"),
                            job_type=args.get("job_type"),
                            requirements=args.get("requirements"),
                            remote_type=args.get("remote_type"),
                            easy_apply=args.get("easy_apply"),
                            employment_type=args.get("employment_type"),
                        )

            return None

        except Exception as e:
            logger.debug(f"Function calling failed for {model_name}: {e}")
            return None

    async def _try_text_extraction(
        self, client: genai.Client, model_name: str, prompt: str
    ) -> AIExtractedJob | None:
        """Fallback to text-based JSON extraction."""
        # Use a simpler prompt for text extraction
        text_prompt = prompt.replace(
            "call the extract_job_data function with the extracted data",
            "return ONLY a JSON object with the extracted data (no markdown)",
        )

        response = await client.aio.models.generate_content(
            model=model_name,
            contents=text_prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=4096,
            ),
        )

        if not response.text:
            return None

        # Parse JSON response
        json_text = response.text.strip()

        # Remove markdown code blocks if present
        if json_text.startswith("```json"):
            json_text = json_text[7:]
        if json_text.startswith("```"):
            json_text = json_text[3:]
        if json_text.endswith("```"):
            json_text = json_text[:-3]
        json_text = json_text.strip()

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from {model_name}: {e}")
            logger.debug(f"Raw response: {response.text}")
            return None

        if not data.get("title"):
            logger.warning(f"No title extracted from {model_name}")
            return None

        return AIExtractedJob(
            title=data.get("title"),
            company=data.get("company"),
            location=data.get("location"),
            description=data.get("description"),
            salary_range=data.get("salary_range"),
            job_type=data.get("job_type"),
            requirements=data.get("requirements"),
            remote_type=data.get("remote_type"),
            easy_apply=data.get("easy_apply"),
            employment_type=data.get("employment_type"),
        )


# Singleton instance
_extractor: GeminiExtractor | None = None


def get_gemini_extractor() -> GeminiExtractor:
    """Get or create the Gemini extractor instance."""
    global _extractor
    if _extractor is None:
        _extractor = GeminiExtractor()
    return _extractor

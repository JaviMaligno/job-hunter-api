"""
Gemini-based Job Application Orchestrator Agent.

This agent uses Gemini 2.5 with Chrome DevTools MCP for browser automation
to fill job application forms.
"""

import asyncio
import json
import os
from typing import Any

from pydantic import BaseModel, Field

from google import genai
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Try to import langfuse, but make it optional
try:
    from langfuse.decorators import langfuse_context, observe
    LANGFUSE_AVAILABLE = True
except Exception:
    LANGFUSE_AVAILABLE = False

    def observe():
        def decorator(func):
            return func
        return decorator

    class DummyContext:
        def update_current_trace(self, **kwargs):
            pass

        def update_current_observation(self, **kwargs):
            pass

    langfuse_context = DummyContext()


# =============================================================================
# Models
# =============================================================================


class UserFormData(BaseModel):
    """User data for form filling."""
    first_name: str
    last_name: str
    email: str
    phone: str
    phone_country_code: str = "+44"
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    address_line_1: str | None = None
    city: str | None = None
    country: str = "United Kingdom"
    postal_code: str | None = None


class OrchestratorInput(BaseModel):
    """Input for the orchestrator agent."""
    job_url: str = Field(description="URL of the job posting or application form")
    user_data: UserFormData
    cv_content: str = Field(description="CV/Resume content as text")
    cv_file_path: str | None = Field(default=None, description="Path to CV file for upload")
    cover_letter: str | None = Field(default=None, description="Optional cover letter")
    headless: bool = Field(default=False, description="Run browser in headless mode")


class FieldFilled(BaseModel):
    """Record of a filled form field."""
    field_name: str
    field_type: str
    value: str
    success: bool


class BlockerDetected(BaseModel):
    """Information about a detected blocker."""
    blocker_type: str  # captcha, login_required, file_upload, multi_step
    description: str
    screenshot_path: str | None = None
    can_auto_resolve: bool = False


class OrchestratorOutput(BaseModel):
    """Output from the orchestrator agent."""
    success: bool
    status: str  # completed, paused, failed, needs_intervention
    fields_filled: list[FieldFilled] = Field(default_factory=list)
    blocker: BlockerDetected | None = None
    final_url: str | None = None
    screenshot_path: str | None = None
    error_message: str | None = None
    steps_completed: list[str] = Field(default_factory=list)


# =============================================================================
# Agent
# =============================================================================


class GeminiOrchestratorAgent:
    """
    Gemini-based orchestrator for job application automation.

    Uses Gemini 2.5 Flash/Pro with Chrome DevTools MCP for browser control.
    """

    # Model priorities
    MODEL_PRIMARY = "gemini-2.5-pro"
    MODEL_FALLBACK = "gemini-2.5-flash"

    # System prompt for form analysis and filling
    SYSTEM_PROMPT = """You are a job application form filling assistant.

Your task is to help fill out job application forms accurately and professionally.

When analyzing a page snapshot:
1. Identify if it's a job listing page, application form, or something else
2. Find form fields and their UIDs from the accessibility tree
3. Match user data to appropriate fields
4. Identify any blockers (CAPTCHA, login requirements, file uploads)

When filling forms:
- Use exact user data, never fabricate information
- For text fields, use the 'fill' tool with the field's UID
- For dropdowns/selects, analyze options and choose the best match
- For file uploads, note the field UID for later handling

Always be thorough but cautious - don't submit until all required fields are filled.
"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int = 3,
    ):
        """
        Initialize the Gemini orchestrator.

        Args:
            api_key: Gemini API key (uses GEMINI_API_KEY env var if not provided)
            model: Model to use (defaults to MODEL_FALLBACK for reliability)
            max_retries: Maximum retries for failed operations
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found")

        self.client = genai.Client(api_key=self.api_key)
        self.model = model or self.MODEL_FALLBACK
        self.max_retries = max_retries

        # MCP session (initialized during run)
        self._mcp_session: ClientSession | None = None

    @property
    def name(self) -> str:
        return "gemini-job-orchestrator"

    @observe()
    async def run(self, input_data: OrchestratorInput) -> OrchestratorOutput:
        """
        Execute the job application automation.

        Args:
            input_data: Input containing job URL, user data, and CV

        Returns:
            Output with success status, filled fields, and any blockers
        """
        langfuse_context.update_current_trace(
            name=f"{self.name}-execution",
            metadata={"model": self.model, "job_url": input_data.job_url},
        )

        steps_completed = []
        fields_filled = []

        server_params = StdioServerParameters(
            command="npx",
            args=["chrome-devtools-mcp@latest"],
            env=None,
        )

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as mcp:
                    await mcp.initialize()
                    self._mcp_session = mcp

                    # Step 1: Navigate to job URL
                    steps_completed.append("mcp_connected")
                    await self._navigate(input_data.job_url)
                    steps_completed.append("navigated_to_url")

                    # Wait for page load
                    await asyncio.sleep(3)

                    # Step 2: Analyze page
                    snapshot = await self._take_snapshot()
                    analysis = await self._analyze_page(snapshot)
                    steps_completed.append("page_analyzed")

                    # Check for blockers
                    blocker = await self._check_blockers(snapshot, analysis)
                    if blocker and not blocker.can_auto_resolve:
                        return OrchestratorOutput(
                            success=False,
                            status="needs_intervention",
                            blocker=blocker,
                            steps_completed=steps_completed,
                        )

                    # Step 3: If on job listing, click apply button
                    if "job_listing" in analysis.lower():
                        apply_clicked = await self._click_apply_button(snapshot)
                        if apply_clicked:
                            steps_completed.append("clicked_apply")
                            await asyncio.sleep(2)
                            snapshot = await self._take_snapshot()

                    # Step 4: Fill form fields
                    filled = await self._fill_form_fields(
                        snapshot, input_data.user_data, input_data.cv_content
                    )
                    fields_filled.extend(filled)
                    steps_completed.append("fields_filled")

                    # Step 5: Handle file upload if needed
                    if input_data.cv_file_path:
                        upload_success = await self._upload_cv(
                            snapshot, input_data.cv_file_path
                        )
                        if upload_success:
                            steps_completed.append("cv_uploaded")

                    # Step 6: Take final screenshot
                    screenshot_path = await self._take_screenshot()
                    steps_completed.append("screenshot_taken")

                    # Get final URL
                    final_url = await self._get_current_url()

                    return OrchestratorOutput(
                        success=True,
                        status="paused",  # Always pause before submit for review
                        fields_filled=fields_filled,
                        final_url=final_url,
                        screenshot_path=screenshot_path,
                        steps_completed=steps_completed,
                    )

        except Exception as e:
            langfuse_context.update_current_observation(
                level="ERROR",
                status_message=str(e),
            )
            return OrchestratorOutput(
                success=False,
                status="failed",
                error_message=str(e),
                steps_completed=steps_completed,
                fields_filled=fields_filled,
            )

    # =========================================================================
    # Browser Control Methods
    # =========================================================================

    async def _navigate(self, url: str) -> None:
        """Navigate to a URL."""
        await self._mcp_session.call_tool("navigate_page", {"url": url})

    async def _take_snapshot(self) -> str:
        """Take an accessibility snapshot of the page."""
        result = await self._mcp_session.call_tool("take_snapshot", {})
        return str(result)

    async def _take_screenshot(self) -> str | None:
        """Take a screenshot and return the path."""
        try:
            result = await self._mcp_session.call_tool("take_screenshot", {})
            # Screenshot is returned as base64, we'd need to save it
            return "screenshot_captured"
        except Exception:
            return None

    async def _get_current_url(self) -> str | None:
        """Get the current page URL from the snapshot."""
        try:
            snapshot = await self._take_snapshot()
            # Parse URL from snapshot (it's in the RootWebArea line)
            if 'url="' in snapshot:
                start = snapshot.index('url="') + 5
                end = snapshot.index('"', start)
                return snapshot[start:end]
        except Exception:
            pass
        return None

    async def _click(self, uid: str) -> bool:
        """Click an element by UID."""
        try:
            await self._mcp_session.call_tool("click", {"uid": uid})
            return True
        except Exception:
            return False

    async def _fill(self, uid: str, value: str) -> bool:
        """Fill a form field by UID."""
        try:
            await self._mcp_session.call_tool("fill", {"uid": uid, "value": value})
            return True
        except Exception:
            return False

    # =========================================================================
    # AI-Powered Analysis Methods
    # =========================================================================

    async def _analyze_page(self, snapshot: str) -> str:
        """Use Gemini to analyze the page content."""
        prompt = f"""Analyze this page accessibility snapshot and classify it:

1. Is this a job listing page (shows job details with Apply button)?
2. Is this a job application form (has input fields for name, email, etc)?
3. Is this something else (login page, error page, etc)?

Return one of: "job_listing", "application_form", "login_required", "error_page", "other"

Snapshot (first 3000 chars):
{snapshot[:3000]}
"""
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        return response.text.strip().lower()

    async def _check_blockers(
        self, snapshot: str, analysis: str
    ) -> BlockerDetected | None:
        """Check for blockers like CAPTCHA, login requirements, etc."""
        blocker_check_prompt = f"""Analyze this page for blockers:

1. CAPTCHA: Look for "captcha", "cf-turnstile", "hcaptcha", "recaptcha"
2. Login Required: Look for "sign in", "log in", "login required"
3. Error: Look for error messages

Page analysis: {analysis}

Snapshot (first 2000 chars):
{snapshot[:2000]}

If a blocker is found, return JSON: {{"type": "...", "description": "..."}}
If no blocker, return: {{"type": "none"}}
"""
        response = self.client.models.generate_content(
            model=self.model,
            contents=blocker_check_prompt,
        )

        try:
            result_text = response.text.strip()
            # Clean markdown
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            result = json.loads(result_text)

            if result.get("type") and result["type"] != "none":
                return BlockerDetected(
                    blocker_type=result["type"],
                    description=result.get("description", ""),
                    can_auto_resolve=result["type"] == "captcha",  # Could use 2captcha
                )
        except Exception:
            pass

        return None

    async def _click_apply_button(self, snapshot: str) -> bool:
        """Find and click the Apply button."""
        prompt = f"""In this accessibility snapshot, find the UID of the "Apply", "Apply Now", or "Aplicar" button.
Return ONLY the uid value (like "1_5" or "2_3"), nothing else.
If not found, return "NOT_FOUND".

Snapshot (first 4000 chars):
{snapshot[:4000]}
"""
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        uid = response.text.strip()

        if uid and "_" in uid and "NOT_FOUND" not in uid:
            return await self._click(uid)
        return False

    async def _fill_form_fields(
        self, snapshot: str, user_data: UserFormData, cv_content: str
    ) -> list[FieldFilled]:
        """Identify and fill form fields."""
        filled = []

        # Use Gemini to map fields
        prompt = f"""In this accessibility snapshot, identify form input fields and match them to user data.

User data available:
- first_name: {user_data.first_name}
- last_name: {user_data.last_name}
- email: {user_data.email}
- phone: {user_data.phone}
- linkedin: {user_data.linkedin_url or 'N/A'}
- github: {user_data.github_url or 'N/A'}

Return a JSON array of fields to fill:
[{{"uid": "1_5", "field_type": "first_name", "value": "John"}}, ...]

Only include fields you can confidently match. Return [] if no form fields found.

Snapshot:
{snapshot[:5000]}
"""
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        try:
            result_text = response.text.strip()
            # Clean markdown
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]

            fields = json.loads(result_text)

            for field in fields:
                uid = field.get("uid")
                value = field.get("value")
                field_type = field.get("field_type", "unknown")

                if uid and value:
                    success = await self._fill(uid, value)
                    filled.append(FieldFilled(
                        field_name=field_type,
                        field_type=field_type,
                        value=value,
                        success=success,
                    ))
                    await asyncio.sleep(0.3)  # Small delay between fills

        except json.JSONDecodeError:
            pass

        return filled

    async def _upload_cv(self, snapshot: str, cv_path: str) -> bool:
        """Find file upload field and upload CV."""
        # Find file input UID
        prompt = f"""Find the UID of the file upload field for CV/Resume in this snapshot.
Return ONLY the uid value, or "NOT_FOUND" if not present.

Snapshot (first 3000 chars):
{snapshot[:3000]}
"""
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        uid = response.text.strip()

        if uid and "_" in uid and "NOT_FOUND" not in uid:
            try:
                await self._mcp_session.call_tool(
                    "upload_file",
                    {"uid": uid, "paths": [cv_path]}
                )
                return True
            except Exception:
                pass

        return False


# =============================================================================
# Convenience function
# =============================================================================


async def run_job_application(
    job_url: str,
    user_data: dict,
    cv_content: str,
    cv_file_path: str | None = None,
) -> OrchestratorOutput:
    """
    Convenience function to run job application automation.

    Args:
        job_url: URL of the job posting
        user_data: Dict with user information
        cv_content: CV text content
        cv_file_path: Optional path to CV file

    Returns:
        OrchestratorOutput with results
    """
    agent = GeminiOrchestratorAgent()

    input_data = OrchestratorInput(
        job_url=job_url,
        user_data=UserFormData(**user_data),
        cv_content=cv_content,
        cv_file_path=cv_file_path,
    )

    return await agent.run(input_data)

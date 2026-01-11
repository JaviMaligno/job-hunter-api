"""
Gemini-based Job Application Orchestrator Agent with HTTP Browser Service.

This agent uses Gemini 2.5 with the Browser Service HTTP API for browser automation
to fill job application forms. Works in cloud environments without local Chrome.
"""

import asyncio
import json
import logging
import os
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field

from src.automation.browserless_client import BrowserlessClient
from src.config import settings

# CAPTCHA solver (optional)
try:
    from src.integrations.captcha.solver import CaptchaSolver, CaptchaType

    CAPTCHA_SOLVER_AVAILABLE = True
except ImportError:
    CAPTCHA_SOLVER_AVAILABLE = False
    CaptchaSolver = None
    CaptchaType = None

# Import intervention manager for manual intervention support
try:
    from src.automation.intervention_manager import (
        InterventionManager,
        InterventionType,
        get_intervention_manager,
    )

    INTERVENTION_AVAILABLE = True
except ImportError:
    INTERVENTION_AVAILABLE = False
    InterventionManager = None
    InterventionType = None
    get_intervention_manager = None

logger = logging.getLogger(__name__)

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
# Models (reuse from original)
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
    headless: bool = Field(default=True, description="Run browser in headless mode")
    # Session info for intervention management
    session_id: str | None = Field(default=None, description="Session ID for intervention tracking")
    user_id: str | None = Field(default=None, description="User ID for intervention tracking")
    wait_for_intervention: bool = Field(
        default=True, description="Keep browser open and wait for user to resolve blockers"
    )
    intervention_timeout_seconds: float = Field(
        default=1800, description="Max time to wait for intervention (30 min)"
    )


class FieldFilled(BaseModel):
    """Record of a filled form field."""

    field_name: str
    field_type: str
    value: str
    success: bool


class BlockerDetected(BaseModel):
    """Information about a detected blocker."""

    blocker_type: str  # captcha, login_required, file_upload, multi_step
    captcha_subtype: str | None = None  # turnstile, hcaptcha, recaptcha
    description: str
    screenshot_path: str | None = None
    can_auto_resolve: bool = False
    auto_resolved: bool = False
    resolution_error: str | None = None


class CaptchaSolveInfo(BaseModel):
    """Information about CAPTCHA solving attempt."""

    attempted: bool = False
    success: bool = False
    captcha_type: str | None = None
    solve_time_seconds: float = 0.0
    cost_usd: float = 0.0
    error: str | None = None


class OrchestratorOutput(BaseModel):
    """Output from the orchestrator agent."""

    success: bool
    status: str  # completed, paused, failed, needs_intervention
    fields_filled: list[FieldFilled] = Field(default_factory=list)
    blocker: BlockerDetected | None = None
    captcha_info: CaptchaSolveInfo | None = None
    final_url: str | None = None
    screenshot_path: str | None = None
    error_message: str | None = None
    steps_completed: list[str] = Field(default_factory=list)


# =============================================================================
# Agent
# =============================================================================


class GeminiHTTPOrchestratorAgent:
    """
    Gemini-based orchestrator for job application automation using HTTP Browser Service.

    Uses Gemini 2.5 Flash/Pro with Browser Service HTTP API for browser control.
    Works in cloud environments without requiring local Chrome installation.
    """

    # Model priorities
    MODEL_PRIMARY = "gemini-2.5-flash"
    MODEL_FALLBACK = "gemini-2.0-flash"

    # System prompt for form analysis and filling
    SYSTEM_PROMPT = """You are a job application form filling assistant.

Your task is to help fill out job application forms accurately and professionally.

When analyzing page HTML:
1. Identify if it's a job listing page, application form, or something else
2. Find form fields by their CSS selectors (id, name, class)
3. Match user data to appropriate fields
4. Identify any blockers (CAPTCHA, login requirements, file uploads)

When filling forms:
- Use exact user data, never fabricate information
- For text fields, provide the CSS selector and value
- For dropdowns/selects, analyze options and choose the best match
- For file uploads, note the selector for later handling

Always be thorough but cautious - don't submit until all required fields are filled.
"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int = 3,
        captcha_api_key: str | None = None,
        auto_solve_captcha: bool = True,
        browser_service_url: str | None = None,
    ):
        """
        Initialize the Gemini HTTP orchestrator.

        Args:
            api_key: Gemini API key (uses GEMINI_API_KEY env var if not provided)
            model: Model to use (defaults to MODEL_PRIMARY for reliability)
            max_retries: Maximum retries for failed operations
            captcha_api_key: 2captcha API key (uses TWOCAPTCHA_API_KEY env var if not provided)
            auto_solve_captcha: Whether to automatically solve CAPTCHAs
            browser_service_url: Browser Service URL (uses settings if not provided)
        """
        # Import settings for fallback API keys
        from src.config import settings

        self.api_key = api_key or settings.gemini_api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found")

        self.client = genai.Client(api_key=self.api_key)
        self.model = model or self.MODEL_PRIMARY
        self.max_retries = max_retries
        self.auto_solve_captcha = auto_solve_captcha
        self.browser_service_url = browser_service_url

        # Browser client (initialized during run)
        self._browser: BrowserServiceClient | None = None

        # Initialize CAPTCHA solver if available
        self._captcha_solver: CaptchaSolver | None = None
        if CAPTCHA_SOLVER_AVAILABLE and auto_solve_captcha:
            captcha_key = (
                captcha_api_key or settings.twocaptcha_api_key or os.getenv("TWOCAPTCHA_API_KEY")
            )
            if captcha_key:
                self._captcha_solver = CaptchaSolver(api_key=captcha_key)
                logger.info("CAPTCHA solver initialized")
            else:
                logger.warning("No 2captcha API key - CAPTCHA auto-solve disabled")

    def _generate_with_retry(
        self,
        contents: str,
        model: str | None = None,
        max_retries: int | None = None,
    ) -> Any:
        """
        Generate content with retry logic and model fallback.
        """
        current_model = model or self.model
        retries = max_retries or self.max_retries
        models_to_try = [current_model]

        # Add fallback model if not already in list
        if current_model == self.MODEL_PRIMARY and self.MODEL_FALLBACK not in models_to_try:
            models_to_try.append(self.MODEL_FALLBACK)
        elif current_model == self.MODEL_FALLBACK and self.MODEL_PRIMARY not in models_to_try:
            models_to_try.append(self.MODEL_PRIMARY)

        last_error = None

        for model_name in models_to_try:
            for attempt in range(retries):
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=contents,
                    )
                    if attempt > 0 or model_name != current_model:
                        logger.info(
                            f"Gemini call succeeded with {model_name} on attempt {attempt + 1}"
                        )
                    return response

                except genai_errors.ClientError as e:
                    error_str = str(e).lower()
                    last_error = e

                    # Check for rate limit (429)
                    if (
                        "429" in str(e)
                        or "resource exhausted" in error_str
                        or "too many requests" in error_str
                    ):
                        wait_time = min(2**attempt * 2, 30)
                        logger.warning(
                            f"Rate limited on {model_name} (attempt {attempt + 1}/{retries}), "
                            f"waiting {wait_time}s before retry"
                        )
                        import time
                        time.sleep(wait_time)
                        continue

                    logger.error(f"Gemini ClientError on {model_name}: {e}")
                    raise

                except genai_errors.ServerError as e:
                    last_error = e
                    wait_time = min(2**attempt * 2, 30)
                    logger.warning(
                        f"Server error on {model_name} (attempt {attempt + 1}/{retries}), "
                        f"waiting {wait_time}s before retry: {e}"
                    )
                    import time
                    time.sleep(wait_time)
                    continue

                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    if (
                        "429" in str(e)
                        or "resource exhausted" in error_str
                        or "too many requests" in error_str
                    ):
                        wait_time = min(2**attempt * 2, 30)
                        logger.warning(
                            f"Rate limited on {model_name} (attempt {attempt + 1}/{retries}), "
                            f"waiting {wait_time}s before retry"
                        )
                        import time
                        time.sleep(wait_time)
                        continue

                    logger.warning(
                        f"Unexpected error on {model_name} (attempt {attempt + 1}/{retries}): {e}"
                    )
                    if attempt < retries - 1:
                        import time
                        time.sleep(2)
                        continue
                    break

            logger.warning(f"All retries exhausted for {model_name}, trying fallback model")

        logger.error(f"All Gemini models failed after retries: {last_error}")
        raise last_error or Exception("All Gemini models failed")

    @property
    def name(self) -> str:
        return "gemini-http-orchestrator"

    @observe()
    async def run(self, input_data: OrchestratorInput) -> OrchestratorOutput:
        """
        Execute the job application automation using HTTP Browser Service.

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

        try:
            # Connect directly to Browserless.io via CDP
            logger.info("Connecting to Browserless.io...")
            async with BrowserlessClient() as browser:
                self._browser = browser
                logger.info(f"Connected to Browserless.io, session: {browser.session_id}")
                steps_completed.append("browser_connected")

                # Step 1: Navigate to job URL
                await browser.navigate(input_data.job_url)
                steps_completed.append("navigated_to_url")

                # Wait for page load
                await asyncio.sleep(3)

                # Step 2: Analyze page
                page_info = await self._get_page_info()
                analysis = await self._analyze_page(page_info)
                steps_completed.append("page_analyzed")

                # Check for blockers
                captcha_info = None
                blocker = await self._check_blockers(page_info, analysis)

                if blocker:
                    # Try to auto-resolve CAPTCHA
                    if blocker.blocker_type == "captcha" and self._captcha_solver:
                        steps_completed.append("captcha_detected")
                        logger.info(f"Attempting to solve {blocker.captcha_subtype} CAPTCHA")

                        captcha_result = await self._solve_captcha(page_info, input_data.job_url)
                        captcha_info = CaptchaSolveInfo(
                            attempted=True,
                            success=captcha_result.get("success", False),
                            captcha_type=captcha_result.get("captcha_type"),
                            solve_time_seconds=captcha_result.get("solve_time", 0),
                            cost_usd=captcha_result.get("cost", 0),
                            error=captcha_result.get("error"),
                        )

                        if captcha_result.get("success"):
                            blocker.auto_resolved = True
                            steps_completed.append("captcha_solved")
                            await asyncio.sleep(2)
                            page_info = await self._get_page_info()
                        else:
                            blocker.resolution_error = captcha_result.get("error")

                    # If blocker not resolved, handle manual intervention
                    if not blocker.auto_resolved and not blocker.can_auto_resolve:
                        if (
                            input_data.wait_for_intervention
                            and input_data.session_id
                            and input_data.user_id
                            and INTERVENTION_AVAILABLE
                        ):
                            steps_completed.append("waiting_for_intervention")
                            logger.info(
                                f"Blocker detected ({blocker.blocker_type}). "
                                f"Waiting for manual intervention. "
                                f"Session: {input_data.session_id}"
                            )

                            current_url = await browser.get_current_url()

                            intervention_mgr = get_intervention_manager()
                            intervention = await intervention_mgr.request_intervention(
                                session_id=input_data.session_id,
                                user_id=input_data.user_id,
                                intervention_type=(
                                    InterventionType.CAPTCHA
                                    if blocker.blocker_type == "captcha"
                                    else InterventionType.OTHER
                                ),
                                title=f"Manual intervention required: {blocker.blocker_type}",
                                description=blocker.description,
                                instructions=(
                                    "Please resolve the blocker and then click "
                                    "'Continue' in the UI when done."
                                ),
                                current_url=current_url,
                                captcha_type=blocker.captcha_subtype,
                                captcha_solve_attempted=captcha_info.attempted
                                if captcha_info
                                else False,
                                captcha_solve_error=captcha_info.error
                                if captcha_info
                                else None,
                                timeout_minutes=int(
                                    input_data.intervention_timeout_seconds / 60
                                ),
                            )

                            logger.info(
                                f"Waiting for intervention {intervention.id} resolution..."
                            )
                            (
                                resolution,
                                updated_intervention,
                            ) = await intervention_mgr.wait_for_resolution(
                                intervention.id,
                                timeout_seconds=input_data.intervention_timeout_seconds,
                            )

                            if resolution and resolution.action == "continue":
                                steps_completed.append("intervention_resolved")
                                logger.info(
                                    "Intervention resolved by user, continuing automation"
                                )
                                await asyncio.sleep(1)
                                page_info = await self._get_page_info()
                                blocker = None
                            elif resolution and resolution.action == "cancel":
                                return OrchestratorOutput(
                                    success=False,
                                    status="cancelled",
                                    blocker=blocker,
                                    captcha_info=captcha_info,
                                    steps_completed=steps_completed,
                                    error_message="User cancelled intervention",
                                )
                            else:
                                return OrchestratorOutput(
                                    success=False,
                                    status="needs_intervention",
                                    blocker=blocker,
                                    captcha_info=captcha_info,
                                    steps_completed=steps_completed,
                                    error_message="Intervention timed out",
                                )
                        else:
                            return OrchestratorOutput(
                                success=False,
                                status="needs_intervention",
                                blocker=blocker,
                                captcha_info=captcha_info,
                                steps_completed=steps_completed,
                            )

                # Step 3: If on job listing, click apply button
                if "job_listing" in analysis.lower():
                    apply_clicked = await self._click_apply_button(page_info)
                    if apply_clicked:
                        steps_completed.append("clicked_apply")
                        await asyncio.sleep(2)
                        page_info = await self._get_page_info()

                # Step 4: Fill form fields
                filled = await self._fill_form_fields(
                    page_info, input_data.user_data, input_data.cv_content
                )
                fields_filled.extend(filled)
                steps_completed.append("fields_filled")

                # Step 5: Handle file upload if needed
                if input_data.cv_file_path:
                    upload_success = await self._upload_cv(page_info, input_data.cv_file_path)
                    if upload_success:
                        steps_completed.append("cv_uploaded")

                # Step 6: Take final screenshot
                screenshot_result = await browser.screenshot()
                screenshot_path = "screenshot_captured" if screenshot_result.success else None
                steps_completed.append("screenshot_taken")

                # Get final URL
                final_url = await browser.get_current_url()

                return OrchestratorOutput(
                    success=True,
                    status="paused",  # Always pause before submit for review
                    fields_filled=fields_filled,
                    captcha_info=captcha_info,
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
    # Browser Control Methods (HTTP API)
    # =========================================================================

    async def _get_page_info(self) -> dict:
        """Get page information including HTML and form fields."""
        if not self._browser:
            raise RuntimeError("Browser not initialized")

        # Get page content and form fields in parallel
        html_content = await self._browser.get_page_content()
        dom_response = await self._browser.get_dom(form_fields_only=True)
        current_url = await self._browser.get_current_url()

        # Format form fields for Gemini
        form_fields_info = []
        for field in dom_response.form_fields:
            form_fields_info.append({
                "selector": field.selector,
                "type": field.field_type,
                "name": field.field_name,
                "label": field.label,
                "required": field.required,
                "value": field.current_value,
            })

        return {
            "html": html_content[:15000],  # Limit HTML size
            "url": current_url,
            "form_fields": form_fields_info,
        }

    async def _click(self, selector: str) -> bool:
        """Click an element by CSS selector."""
        if not self._browser:
            return False
        try:
            result = await self._browser.click(selector)
            return result.get("success", False)
        except Exception as e:
            logger.warning(f"Click failed for {selector}: {e}")
            return False

    async def _click_by_text(self, text: str) -> bool:
        """Click a button by its text."""
        if not self._browser:
            return False
        try:
            result = await self._browser.click_by_text(text)
            return result.get("success", False)
        except Exception as e:
            logger.warning(f"Click by text failed for '{text}': {e}")
            return False

    async def _fill(self, selector: str, value: str) -> bool:
        """Fill a form field by CSS selector."""
        if not self._browser:
            return False
        try:
            result = await self._browser.fill(selector, value)
            return result.get("success", False)
        except Exception as e:
            logger.warning(f"Fill failed for {selector}: {e}")
            return False

    # =========================================================================
    # AI-Powered Analysis Methods
    # =========================================================================

    async def _analyze_page(self, page_info: dict) -> str:
        """Use Gemini to analyze the page content."""
        form_fields_text = json.dumps(page_info.get("form_fields", []), indent=2)

        prompt = f"""Analyze this web page and classify it:

1. Is this a job listing page (shows job details with Apply button)?
2. Is this a job application form (has input fields for name, email, etc)?
3. Is this something else (login page, error page, etc)?

Return one of: "job_listing", "application_form", "login_required", "error_page", "other"

Page URL: {page_info.get('url', 'unknown')}

Form fields found:
{form_fields_text}

HTML content (first 5000 chars):
{page_info.get('html', '')[:5000]}
"""
        response = self._generate_with_retry(contents=prompt)
        return response.text.strip().lower()

    async def _check_blockers(self, page_info: dict, analysis: str) -> BlockerDetected | None:
        """Check for blockers like CAPTCHA, login requirements, etc."""
        html = page_info.get("html", "")

        blocker_check_prompt = f"""Analyze this page for blockers:

1. CAPTCHA: Look for "captcha", "cf-turnstile", "hcaptcha", "recaptcha", "challenge"
   - If found, identify subtype: "turnstile", "hcaptcha", or "recaptcha"
2. Login Required: Look for "sign in", "log in", "login required", "please login"
3. Error: Look for error messages, "access denied", "forbidden"

Page analysis: {analysis}

HTML (first 3000 chars):
{html[:3000]}

If a blocker is found, return JSON: {{"type": "captcha|login_required|error", "subtype": "turnstile|hcaptcha|recaptcha|null", "description": "..."}}
If no blocker, return: {{"type": "none"}}
"""
        response = self._generate_with_retry(contents=blocker_check_prompt)

        try:
            result_text = response.text.strip()
            # Clean markdown
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            result = json.loads(result_text)

            if result.get("type") and result["type"] != "none":
                captcha_subtype = result.get("subtype")
                can_auto = result["type"] == "captcha" and self._captcha_solver is not None
                return BlockerDetected(
                    blocker_type=result["type"],
                    captcha_subtype=captcha_subtype,
                    description=result.get("description", ""),
                    can_auto_resolve=can_auto,
                )
        except Exception:
            pass

        return None

    async def _solve_captcha(self, page_info: dict, page_url: str) -> dict:
        """Attempt to solve a CAPTCHA using 2captcha."""
        if not self._captcha_solver or not self._browser:
            return {"success": False, "error": "CAPTCHA solver not configured"}

        try:
            page_html = page_info.get("html", "")

            result = await self._captcha_solver.solve_from_html(
                page_html=page_html,
                page_url=page_url,
            )

            if result.success and result.token:
                captcha_type = result.captcha_type
                if captcha_type and CAPTCHA_SOLVER_AVAILABLE:
                    injection_script = self._captcha_solver.get_injection_script(
                        captcha_type, result.token
                    )
                    await self._browser.evaluate(injection_script)
                    logger.info(f"Injected {captcha_type.value} token into page")

                return {
                    "success": True,
                    "captcha_type": result.captcha_type.value if result.captcha_type else None,
                    "token": result.token,
                    "solve_time": result.solve_time_seconds,
                    "cost": result.cost_usd,
                }
            else:
                return {
                    "success": False,
                    "captcha_type": result.captcha_type.value if result.captcha_type else None,
                    "error": result.error,
                    "solve_time": result.solve_time_seconds,
                }

        except Exception as e:
            logger.error(f"CAPTCHA solve error: {e}")
            return {"success": False, "error": str(e)}

    async def _click_apply_button(self, page_info: dict) -> bool:
        """Find and click the Apply button."""
        # Try common apply button texts
        apply_texts = ["Apply", "Apply Now", "Aplicar", "Apply for this job", "Quick Apply", "Easy Apply"]

        for text in apply_texts:
            if await self._click_by_text(text):
                logger.info(f"Clicked apply button with text: {text}")
                return True

        # If no button found by text, ask Gemini to find the selector
        html = page_info.get("html", "")
        prompt = f"""In this HTML, find the CSS selector for the "Apply", "Apply Now", or similar button.
Return ONLY the CSS selector (like "#apply-btn" or ".apply-button"), nothing else.
If not found, return "NOT_FOUND".

HTML (first 5000 chars):
{html[:5000]}
"""
        response = self._generate_with_retry(contents=prompt)
        selector = response.text.strip()

        if selector and selector != "NOT_FOUND" and not selector.startswith("NOT"):
            return await self._click(selector)

        return False

    async def _fill_form_fields(
        self, page_info: dict, user_data: UserFormData, cv_content: str
    ) -> list[FieldFilled]:
        """Identify and fill form fields."""
        filled = []
        form_fields = page_info.get("form_fields", [])

        if not form_fields:
            logger.info("No form fields found on page")
            return filled

        # Use Gemini to map fields to user data
        user_data_dict = {
            "first_name": user_data.first_name,
            "last_name": user_data.last_name,
            "full_name": f"{user_data.first_name} {user_data.last_name}",
            "email": user_data.email,
            "phone": user_data.phone,
            "linkedin": user_data.linkedin_url or "",
            "github": user_data.github_url or "",
            "portfolio": user_data.portfolio_url or "",
            "address": user_data.address_line_1 or "",
            "city": user_data.city or "",
            "country": user_data.country,
            "postal_code": user_data.postal_code or "",
        }

        prompt = f"""Match these form fields to user data and return fields to fill.

Form fields:
{json.dumps(form_fields, indent=2)}

User data available:
{json.dumps(user_data_dict, indent=2)}

Return a JSON array of fields to fill:
[{{"selector": "#email", "field_type": "email", "value": "john@example.com"}}, ...]

Rules:
- Use the exact selector from form_fields
- Only include fields you can confidently match to user data
- Don't fill fields that already have values
- Return [] if no form fields can be matched

Return ONLY the JSON array, no explanation.
"""
        response = self._generate_with_retry(contents=prompt)

        try:
            result_text = response.text.strip()
            # Clean markdown
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            # Find the array
            if "[" in result_text:
                start = result_text.index("[")
                end = result_text.rindex("]") + 1
                result_text = result_text[start:end]

            fields = json.loads(result_text)

            for field in fields:
                selector = field.get("selector")
                value = field.get("value")
                field_type = field.get("field_type", "unknown")

                if selector and value:
                    success = await self._fill(selector, value)
                    filled.append(
                        FieldFilled(
                            field_name=field_type,
                            field_type=field_type,
                            value=value,
                            success=success,
                        )
                    )
                    if success:
                        logger.info(f"Filled field {selector} with {field_type}")
                    await asyncio.sleep(0.3)  # Small delay between fills

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Gemini response: {e}")

        return filled

    async def _upload_cv(self, page_info: dict, cv_path: str) -> bool:
        """Find file upload field and upload CV."""
        if not self._browser:
            return False

        form_fields = page_info.get("form_fields", [])

        # Find file input
        file_inputs = [f for f in form_fields if f.get("type") == "file"]

        if file_inputs:
            selector = file_inputs[0].get("selector")
            if selector:
                try:
                    result = await self._browser.upload(selector, cv_path)
                    return result.get("success", False)
                except Exception as e:
                    logger.warning(f"CV upload failed: {e}")

        # If no file input found, ask Gemini
        html = page_info.get("html", "")
        prompt = f"""Find the CSS selector for the file upload field for CV/Resume.
Return ONLY the selector, or "NOT_FOUND" if not present.

HTML (first 3000 chars):
{html[:3000]}
"""
        response = self._generate_with_retry(contents=prompt)
        selector = response.text.strip()

        if selector and selector != "NOT_FOUND" and not selector.startswith("NOT"):
            try:
                result = await self._browser.upload(selector, cv_path)
                return result.get("success", False)
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
    agent = GeminiHTTPOrchestratorAgent()

    input_data = OrchestratorInput(
        job_url=job_url,
        user_data=UserFormData(**user_data),
        cv_content=cv_content,
        cv_file_path=cv_file_path,
    )

    return await agent.run(input_data)

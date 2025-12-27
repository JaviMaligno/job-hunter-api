"""Form Filler Agent for job application automation."""

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.agents.base import BaseAgent
from src.automation.models import UserFormData  # Shared model to avoid circular import
from src.browser_service.models import BrowserMode, FormField
from src.db.models import ApplicationMode, ApplicationStatus, BlockerType

if TYPE_CHECKING:
    from src.automation.client import BrowserServiceClient

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependency
_browser_client_class = None


def _get_browser_client_class() -> type:
    """Get BrowserServiceClient class lazily to avoid circular import."""
    global _browser_client_class
    if _browser_client_class is None:
        from src.automation.client import BrowserServiceClient
        _browser_client_class = BrowserServiceClient
    return _browser_client_class


# ============================================================================
# Input/Output Models
# ============================================================================


# Re-export UserFormData for backwards compatibility
__all__ = ["UserFormData", "FormFillerInput", "FormFillerOutput", "FormFillerAgent"]


class FormFillerInput(BaseModel):
    """Input for Form Filler Agent."""

    job_id: UUID | None = None
    application_url: str
    user_data: UserFormData
    cv_content: str
    cv_file_path: str | None = None  # Path to CV file for upload
    cover_letter: str | None = None
    mode: ApplicationMode = ApplicationMode.ASSISTED
    ats_type: str | None = None  # Auto-detected if None
    headless: bool = True
    browser_mode: BrowserMode = BrowserMode.PLAYWRIGHT
    devtools_url: str | None = None  # Required for chrome-devtools mode


class FormAnalysis(BaseModel):
    """Analysis of a form page."""

    page_url: str
    page_title: str
    form_fields: list[FormField] = []
    detected_ats: str | None = None
    is_multi_step: bool = False
    current_step: int = 1
    total_steps: int | None = None
    has_file_upload: bool = False
    has_captcha: bool = False
    captcha_type: str | None = None
    has_login_required: bool = False
    submit_button_selector: str | None = None


class FieldMapping(BaseModel):
    """Mapping from form field to user data."""

    field_selector: str
    field_label: str | None
    field_type: str
    user_data_key: str | None = None  # Key in UserFormData
    value: str | None = None  # Value to fill
    is_custom_question: bool = False
    requires_ai_answer: bool = False


class CustomQuestion(BaseModel):
    """Custom question requiring AI-generated answer."""

    selector: str
    question_text: str
    field_type: str  # text, textarea, select, radio
    options: list[str] | None = None
    answer: str | None = None


class FormFillerOutput(BaseModel):
    """Output from Form Filler Agent."""

    status: ApplicationStatus
    fields_filled: dict[str, str] = Field(default_factory=dict)  # selector -> value
    questions_answered: list[CustomQuestion] = Field(default_factory=list)
    blocker_detected: BlockerType | None = None
    blocker_details: str | None = None
    screenshot_path: str | None = None
    browser_session_id: str | None = None
    requires_user_action: bool = False
    user_action_message: str | None = None
    current_step: int = 1
    total_steps: int | None = None
    detected_ats: str | None = None
    page_url: str | None = None
    error_message: str | None = None


# ============================================================================
# Form Filler Agent
# ============================================================================


class FormFillerAgent(BaseAgent[FormFillerOutput]):
    """Agent for filling job application forms.

    This agent:
    1. Navigates to the application URL
    2. Analyzes the form structure
    3. Detects blockers (CAPTCHA, login required)
    4. Maps user data to form fields
    5. Generates AI answers for custom questions
    6. Fills the form
    7. Pauses before submit for user review (in ASSISTED mode)

    Usage:
        agent = FormFillerAgent()
        result = await agent.run(FormFillerInput(...))
    """

    def __init__(
        self,
        claude_api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        browser_client: "BrowserServiceClient | None" = None,
    ) -> None:
        """Initialize agent.

        Args:
            claude_api_key: Optional API key
            model: Claude model to use
            max_tokens: Max tokens for responses
            temperature: Sampling temperature
            browser_client: Optional pre-initialized browser client
        """
        super().__init__(claude_api_key, model, max_tokens, temperature)
        self._browser_client = browser_client
        self._owns_client = browser_client is None

    @property
    def name(self) -> str:
        """Agent name."""
        return "form-filler"

    @property
    def system_prompt(self) -> str:
        """System prompt for form analysis and question answering."""
        return """You are an expert at analyzing job application forms and helping users fill them out.

Your responsibilities:
1. Analyze form fields and map them to user data
2. Generate professional, honest answers to custom questions
3. Detect common ATS platforms from page structure
4. Identify blockers like CAPTCHAs and login requirements

When answering custom questions:
- Be professional and concise
- Be truthful - do not fabricate experience or skills
- Tailor answers to the job when context is available
- Match the tone expected by the company
- Keep answers focused and relevant

When mapping form fields:
- Match labels/placeholders to user data fields
- Identify required vs optional fields
- Note any fields that need special handling (file uploads, dropdowns)

Always respond with valid JSON matching the requested schema."""

    async def _execute(self, input_data: FormFillerInput, **kwargs: Any) -> FormFillerOutput:
        """Execute form filling process.

        Args:
            input_data: Form filler input with URL and user data

        Returns:
            FormFillerOutput with status and filled fields
        """
        # Initialize browser client if needed (lazy import to avoid circular dependency)
        if self._browser_client is None:
            BrowserServiceClient = _get_browser_client_class()
            self._browser_client = BrowserServiceClient()

        try:
            async with self._browser_client:
                return await self._fill_form(input_data)
        except Exception as e:
            logger.error(f"Form filling failed: {e}")
            return FormFillerOutput(
                status=ApplicationStatus.FAILED,
                error_message=str(e),
            )

    async def _fill_form(self, input_data: FormFillerInput) -> FormFillerOutput:
        """Main form filling logic.

        Args:
            input_data: Form filler input

        Returns:
            FormFillerOutput with results
        """
        client = self._browser_client
        assert client is not None

        # Create browser session
        logger.info(f"Creating browser session for {input_data.application_url} (mode={input_data.browser_mode.value})")
        session = await client.create_session(
            mode=input_data.browser_mode,
            headless=input_data.headless,
            devtools_url=input_data.devtools_url,
        )

        # Navigate to application URL
        logger.info(f"Navigating to {input_data.application_url}")
        nav_result = await client.navigate(input_data.application_url)

        if not nav_result.success:
            return FormFillerOutput(
                status=ApplicationStatus.FAILED,
                browser_session_id=session.session_id,
                error_message=f"Failed to navigate: {nav_result.error}",
            )

        # Wait a bit for JS-loaded content (CAPTCHAs, dynamic forms)
        import asyncio
        await asyncio.sleep(2)
        logger.info("Waited for page content to fully load")

        # Analyze the form
        logger.info("Analyzing form structure")
        analysis = await self._analyze_form(client)

        # Check for blockers
        if analysis.has_captcha:
            screenshot = await client.screenshot()
            return FormFillerOutput(
                status=ApplicationStatus.NEEDS_INTERVENTION,
                browser_session_id=session.session_id,
                blocker_detected=BlockerType.CAPTCHA,
                blocker_details=f"CAPTCHA detected: {analysis.captcha_type}",
                requires_user_action=True,
                user_action_message="Please complete the CAPTCHA manually and resume",
                screenshot_path=screenshot.screenshot_path,
                detected_ats=analysis.detected_ats,
                page_url=analysis.page_url,
            )

        if analysis.has_login_required:
            screenshot = await client.screenshot()
            return FormFillerOutput(
                status=ApplicationStatus.NEEDS_INTERVENTION,
                browser_session_id=session.session_id,
                blocker_detected=BlockerType.LOGIN_REQUIRED,
                blocker_details="Login required to access application form",
                requires_user_action=True,
                user_action_message="Please log in to the platform and resume",
                screenshot_path=screenshot.screenshot_path,
                detected_ats=analysis.detected_ats,
                page_url=analysis.page_url,
            )

        # Map fields to user data
        logger.info("Mapping form fields to user data")
        field_mappings = await self._map_fields(analysis.form_fields, input_data.user_data)

        # Identify custom questions
        custom_questions = await self._identify_custom_questions(
            analysis.form_fields,
            field_mappings,
        )

        # Generate AI answers for custom questions
        if custom_questions:
            logger.info(f"Generating answers for {len(custom_questions)} custom questions")
            custom_questions = await self._answer_questions(
                custom_questions,
                input_data.cv_content,
                input_data.user_data,
            )

        # Fill the form fields
        logger.info("Filling form fields")
        filled_fields = await self._fill_fields(client, field_mappings, input_data)

        # Fill custom question answers
        for question in custom_questions:
            if question.answer:
                result = await client.fill(question.selector, question.answer)
                if result.get("success"):
                    filled_fields[question.selector] = question.answer

        # Upload CV if needed
        if analysis.has_file_upload and input_data.cv_file_path:
            logger.info("Uploading CV")
            await self._upload_cv(client, analysis.form_fields, input_data.cv_file_path)

        # Take pre-submit screenshot
        screenshot = await client.screenshot()

        # In ASSISTED mode, pause before submit
        if input_data.mode == ApplicationMode.ASSISTED:
            return FormFillerOutput(
                status=ApplicationStatus.NEEDS_INTERVENTION,
                browser_session_id=session.session_id,
                fields_filled=filled_fields,
                questions_answered=custom_questions,
                requires_user_action=True,
                user_action_message="Form filled - please review and confirm submission",
                screenshot_path=screenshot.screenshot_path,
                detected_ats=analysis.detected_ats,
                page_url=analysis.page_url,
                current_step=analysis.current_step,
                total_steps=analysis.total_steps,
            )

        # For SEMI_AUTO and AUTO modes, submit
        # TODO: Implement submit logic with ATS strategies

        return FormFillerOutput(
            status=ApplicationStatus.IN_PROGRESS,
            browser_session_id=session.session_id,
            fields_filled=filled_fields,
            questions_answered=custom_questions,
            screenshot_path=screenshot.screenshot_path,
            detected_ats=analysis.detected_ats,
            page_url=analysis.page_url,
            current_step=analysis.current_step,
            total_steps=analysis.total_steps,
        )

    async def _analyze_form(self, client: "BrowserServiceClient") -> FormAnalysis:
        """Analyze form structure and detect blockers.

        Args:
            client: Browser service client

        Returns:
            FormAnalysis with detected fields and blockers
        """
        # Get DOM information
        dom = await client.get_dom(form_fields_only=True)
        page_content = await client.get_page_content()
        page_url = await client.get_current_url()

        # Detect ATS type
        detected_ats = self._detect_ats(page_url, page_content)

        # Detect blockers
        has_captcha, captcha_type = self._detect_captcha(page_content)
        has_login_required = self._detect_login_required(page_url, page_content)

        logger.info(f"Form analysis: has_captcha={has_captcha}, captcha_type={captcha_type}, has_login={has_login_required}")
        logger.debug(f"Page content length: {len(page_content)}, contains 'recaptcha': {'recaptcha' in page_content.lower()}")

        # Check for file upload fields
        has_file_upload = any(
            f.field_type == "file" for f in dom.form_fields
        )

        # Detect multi-step form
        is_multi_step, current_step, total_steps = self._detect_multi_step(page_content)

        # Find submit button
        submit_selector = await self._find_submit_button(client)

        return FormAnalysis(
            page_url=page_url,
            page_title=dom.page_title,
            form_fields=dom.form_fields,
            detected_ats=detected_ats,
            is_multi_step=is_multi_step,
            current_step=current_step,
            total_steps=total_steps,
            has_file_upload=has_file_upload,
            has_captcha=has_captcha,
            captcha_type=captcha_type,
            has_login_required=has_login_required,
            submit_button_selector=submit_selector,
        )

    def _detect_ats(self, url: str, content: str) -> str | None:
        """Detect ATS platform from URL and page content.

        Args:
            url: Page URL
            content: Page HTML content

        Returns:
            ATS name if detected, None otherwise
        """
        url_lower = url.lower()
        content_lower = content.lower()

        ats_patterns = {
            "breezy": ["breezy.hr", "breezyhr"],
            "workable": ["workable.com", "jobs.workable"],
            "lever": ["lever.co", "jobs.lever"],
            "greenhouse": ["greenhouse.io", "boards.greenhouse"],
            "bamboohr": ["bamboohr.com"],
            "workday": ["workday.com", "myworkday"],
            "phenom": ["phenom.com", "phenompeople"],
        }

        for ats_name, patterns in ats_patterns.items():
            for pattern in patterns:
                if pattern in url_lower or pattern in content_lower:
                    return ats_name

        return None

    def _detect_captcha(self, content: str) -> tuple[bool, str | None]:
        """Detect CAPTCHA on page.

        Args:
            content: Page HTML content

        Returns:
            Tuple of (has_captcha, captcha_type)
        """
        content_lower = content.lower()

        # Expanded CAPTCHA detection patterns
        captcha_patterns = {
            "cloudflare": [
                "cf-turnstile", "challenge-platform", "cloudflare-challenge",
                "cf-chl-widget", "turnstile", "challenge-running",
            ],
            "hcaptcha": [
                "h-captcha", "hcaptcha.com", "hcaptcha-box", "data-hcaptcha",
            ],
            "recaptcha": [
                "g-recaptcha", "recaptcha.net", "grecaptcha", "recaptcha-token",
                "recaptcha/api", "google.com/recaptcha", "recaptcha-anchor",
                "recaptcha_challenge", "rc-anchor", "recaptcha-checkbox",
            ],
            "funcaptcha": [
                "funcaptcha", "arkoselabs.com", "arkose",
            ],
        }

        for captcha_type, patterns in captcha_patterns.items():
            for pattern in patterns:
                if pattern in content_lower:
                    logger.info(f"CAPTCHA detected: type={captcha_type}, pattern={pattern}")
                    return True, captcha_type

        return False, None

    def _detect_login_required(self, url: str, content: str) -> bool:
        """Detect if login is required.

        Args:
            url: Page URL
            content: Page HTML content

        Returns:
            True if login is required
        """
        url_lower = url.lower()
        content_lower = content.lower()

        login_patterns = [
            "/sign-in",
            "/login",
            "/auth/",
            "please log in",
            "sign in to continue",
            "login required",
        ]

        for pattern in login_patterns:
            if pattern in url_lower or pattern in content_lower:
                return True

        return False

    def _detect_multi_step(self, content: str) -> tuple[bool, int, int | None]:
        """Detect multi-step form.

        Args:
            content: Page HTML content

        Returns:
            Tuple of (is_multi_step, current_step, total_steps)
        """
        # Simple heuristic - look for step indicators
        content_lower = content.lower()

        step_patterns = [
            "step 1 of",
            "step 2 of",
            "step 1/",
            "page 1 of",
        ]

        for pattern in step_patterns:
            if pattern in content_lower:
                return True, 1, None  # TODO: Extract actual step numbers

        return False, 1, None

    async def _find_submit_button(self, client: "BrowserServiceClient") -> str | None:
        """Find the submit button selector.

        Args:
            client: Browser service client

        Returns:
            CSS selector for submit button or None
        """
        # First try standard CSS selectors
        css_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
        ]

        for selector in css_selectors:
            if await client.is_element_visible(selector):
                return selector

        # Then try finding buttons by text content using JavaScript
        text_patterns = ["Submit", "Apply", "Send", "Continue", "Next"]
        result = await client.evaluate(f"""
            (() => {{
                const patterns = {text_patterns};
                for (const text of patterns) {{
                    const buttons = document.querySelectorAll('button, input[type="button"]');
                    for (const btn of buttons) {{
                        if (btn.textContent && btn.textContent.trim().toLowerCase().includes(text.toLowerCase())) {{
                            if (btn.offsetParent !== null) {{
                                return btn.textContent.trim();
                            }}
                        }}
                    }}
                }}
                return null;
            }})()
        """)

        if result:
            # Return a selector that can find this button by its text
            # Using an attribute selector won't work, so we return a special marker
            return f'button:text-match("{result}")'

        return None

    async def _map_fields(
        self,
        form_fields: list[FormField],
        user_data: UserFormData,
    ) -> list[FieldMapping]:
        """Map form fields to user data using AI.

        Args:
            form_fields: Detected form fields
            user_data: User data for filling

        Returns:
            List of field mappings
        """
        # Prepare field info for Claude
        field_info = [
            {
                "selector": f.selector,
                "label": f.label,
                "placeholder": f.placeholder,
                "field_type": f.field_type,
                "required": f.required,
            }
            for f in form_fields
            if f.is_visible and f.is_enabled
        ]

        user_data_keys = list(user_data.model_dump().keys())

        prompt = f"""Analyze these form fields and map them to the user data fields.

Form fields:
{field_info}

Available user data keys:
{user_data_keys}

For each form field, determine:
1. Which user_data_key it maps to (or null if it's a custom question)
2. Whether it's a custom question requiring an AI-generated answer

Return a JSON array of objects with:
- field_selector: the selector from the form field
- field_label: the label from the form field
- field_type: the type from the form field
- user_data_key: the matching user data key, or null
- is_custom_question: true if this is a custom question
- requires_ai_answer: true if AI should generate an answer

Common mappings:
- first_name, firstname, fname -> first_name
- last_name, lastname, lname -> last_name
- email, e-mail -> email
- phone, telephone, tel -> phone
- linkedin, linkedin_url -> linkedin_url
- github, github_url -> github_url
- portfolio, website -> portfolio_url
- cover_letter, coverletter -> (mark as custom question)
"""

        response = await self._call_claude_json(
            prompt,
            output_model=_FieldMappingsResponse,
        )

        # Convert to FieldMapping objects with values
        user_dict = user_data.model_dump()
        mappings = []

        for m in response.mappings:  # type: ignore
            value = None
            if m.user_data_key and m.user_data_key in user_dict:
                value = user_dict[m.user_data_key]

            mappings.append(
                FieldMapping(
                    field_selector=m.field_selector,
                    field_label=m.field_label,
                    field_type=m.field_type,
                    user_data_key=m.user_data_key,
                    value=str(value) if value else None,
                    is_custom_question=m.is_custom_question,
                    requires_ai_answer=m.requires_ai_answer,
                )
            )

        return mappings

    async def _identify_custom_questions(
        self,
        form_fields: list[FormField],
        mappings: list[FieldMapping],
    ) -> list[CustomQuestion]:
        """Identify custom questions that need AI answers.

        Args:
            form_fields: Detected form fields
            mappings: Field mappings

        Returns:
            List of custom questions
        """
        questions = []

        mapped_selectors = {m.field_selector for m in mappings if not m.is_custom_question}

        for field in form_fields:
            if field.selector in mapped_selectors:
                continue

            # Check if this is a text/textarea field that might be a question
            if field.field_type in ("text", "textarea") and (field.label or field.placeholder):
                questions.append(
                    CustomQuestion(
                        selector=field.selector,
                        question_text=field.label or field.placeholder or "",
                        field_type=field.field_type,
                        options=field.options,
                    )
                )

        return questions

    async def _answer_questions(
        self,
        questions: list[CustomQuestion],
        cv_content: str,
        user_data: UserFormData,
    ) -> list[CustomQuestion]:
        """Generate AI answers for custom questions.

        Args:
            questions: Questions to answer
            cv_content: User's CV content for context
            user_data: User's personal data

        Returns:
            Questions with answers filled in
        """
        for question in questions:
            prompt = f"""Generate a professional answer for this job application question.

Question: {question.question_text}
Field type: {question.field_type}
{'Options: ' + str(question.options) if question.options else ''}

Context from CV:
{cv_content[:2000]}

User info:
- Name: {user_data.first_name} {user_data.last_name}
- Location: {user_data.city}, {user_data.country}

Guidelines:
- Be professional and concise
- Be truthful - don't fabricate
- Keep the answer appropriate for the field type
- If textarea, aim for 2-3 paragraphs max
- If text field, keep it under 200 characters

Return JSON with: {{"answer": "your answer here"}}"""

            try:
                response = await self._call_claude_json(
                    prompt,
                    output_model=_QuestionAnswerResponse,
                )
                question.answer = response.answer  # type: ignore
            except Exception as e:
                logger.warning(f"Failed to generate answer for question: {e}")

        return questions

    async def _fill_fields(
        self,
        client: "BrowserServiceClient",
        mappings: list[FieldMapping],
        input_data: FormFillerInput,
    ) -> dict[str, str]:
        """Fill form fields with mapped values.

        Args:
            client: Browser service client
            mappings: Field mappings with values
            input_data: Form filler input

        Returns:
            Dict of filled fields (selector -> value)
        """
        filled = {}

        for mapping in mappings:
            if not mapping.value:
                continue

            try:
                result = await client.fill(mapping.field_selector, mapping.value)
                if result.get("success"):
                    filled[mapping.field_selector] = mapping.value
                    logger.debug(f"Filled {mapping.field_selector} with {mapping.value[:20]}...")
            except Exception as e:
                logger.warning(f"Failed to fill {mapping.field_selector}: {e}")

        return filled

    async def _upload_cv(
        self,
        client: "BrowserServiceClient",
        form_fields: list[FormField],
        cv_file_path: str,
    ) -> bool:
        """Upload CV file.

        Args:
            client: Browser service client
            form_fields: Form fields
            cv_file_path: Path to CV file

        Returns:
            True if upload successful
        """
        # Find file input
        file_inputs = [f for f in form_fields if f.field_type == "file"]

        if not file_inputs:
            logger.warning("No file input found for CV upload")
            return False

        try:
            result = await client.upload(file_inputs[0].selector, cv_file_path)
            return result.get("success", False)
        except Exception as e:
            logger.error(f"CV upload failed: {e}")
            return False


# ============================================================================
# Helper Models for JSON Parsing
# ============================================================================


class _FieldMappingItem(BaseModel):
    """Single field mapping from Claude response."""

    field_selector: str
    field_label: str | None = None
    field_type: str
    user_data_key: str | None = None
    is_custom_question: bool = False
    requires_ai_answer: bool = False


class _FieldMappingsResponse(BaseModel):
    """Response from field mapping request."""

    mappings: list[_FieldMappingItem]


class _QuestionAnswerResponse(BaseModel):
    """Response from question answering request."""

    answer: str

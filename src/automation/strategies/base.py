"""Base ATS strategy interface."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from src.automation.models import UserFormData  # Shared model to avoid circular import
from src.automation.client import BrowserServiceClient
from src.browser_service.models import FormField


class CaptchaResult(BaseModel):
    """Result of CAPTCHA handling attempt."""

    resolved: bool = False
    requires_user: bool = True
    captcha_type: str | None = None
    message: str | None = None


class FormFillResult(BaseModel):
    """Result of form filling."""

    success: bool
    fields_filled: dict[str, str] = {}
    errors: list[str] = []


class SubmitResult(BaseModel):
    """Result of form submission."""

    success: bool
    confirmation_message: str | None = None
    redirect_url: str | None = None
    error: str | None = None


class ATSStrategy(ABC):
    """Base strategy for ATS-specific form handling.

    Subclasses implement platform-specific logic for:
    - Detecting the ATS from page content
    - Analyzing form structure
    - Filling forms with appropriate selectors
    - Handling submission

    Usage:
        strategy = BreezyStrategy()
        if await strategy.detect(page_html, page_url):
            analysis = await strategy.analyze_form(client)
            result = await strategy.fill_form(client, user_data, cv_path)
    """

    @property
    @abstractmethod
    def ats_name(self) -> str:
        """ATS identifier (e.g., 'breezy', 'workable', 'lever')."""
        ...

    @property
    @abstractmethod
    def url_patterns(self) -> list[str]:
        """URL patterns to match this ATS (regex patterns)."""
        ...

    @property
    def field_selectors(self) -> dict[str, str]:
        """Common field selectors for this ATS.

        Returns a dict mapping field names to CSS selectors.
        Override in subclasses for platform-specific selectors.
        """
        return {}

    @abstractmethod
    async def detect(self, page_html: str, page_url: str) -> bool:
        """Detect if page belongs to this ATS.

        Args:
            page_html: Page HTML content
            page_url: Page URL

        Returns:
            True if this strategy should handle the page
        """
        ...

    @abstractmethod
    async def analyze_form(
        self,
        client: BrowserServiceClient,
    ) -> dict[str, Any]:
        """Analyze form structure specific to this ATS.

        Args:
            client: Browser service client

        Returns:
            Dict with form analysis data
        """
        ...

    @abstractmethod
    async def fill_form(
        self,
        client: BrowserServiceClient,
        user_data: UserFormData,
        cv_path: str | None,
        cover_letter: str | None,
    ) -> FormFillResult:
        """Fill form using ATS-specific selectors/logic.

        Args:
            client: Browser service client
            user_data: User data for form filling
            cv_path: Path to CV file
            cover_letter: Cover letter content

        Returns:
            FormFillResult with filled fields
        """
        ...

    @abstractmethod
    async def submit(self, client: BrowserServiceClient) -> SubmitResult:
        """Submit the application.

        Args:
            client: Browser service client

        Returns:
            SubmitResult with success status
        """
        ...

    async def handle_captcha(
        self,
        client: BrowserServiceClient,
    ) -> CaptchaResult:
        """Handle CAPTCHA if present.

        Default implementation pauses for user intervention.
        Override in subclasses for auto-solving capabilities.

        Args:
            client: Browser service client

        Returns:
            CaptchaResult indicating if CAPTCHA was resolved
        """
        return CaptchaResult(
            resolved=False,
            requires_user=True,
            message="CAPTCHA detected - manual intervention required",
        )

    async def handle_custom_questions(
        self,
        client: BrowserServiceClient,
        questions: list[FormField],
        user_data: UserFormData,
        job_context: str | None = None,
    ) -> dict[str, str]:
        """Generate answers for custom questions.

        Default implementation returns empty dict.
        Should be overridden to use FormFillerAgent's question answering.

        Args:
            client: Browser service client
            questions: Custom question fields
            user_data: User data for context
            job_context: Optional job description for context

        Returns:
            Dict mapping selector to answer
        """
        return {}

    async def fill_field_with_js(
        self,
        client: BrowserServiceClient,
        selector: str,
        value: str,
    ) -> bool:
        """Fill field using JavaScript (workaround for difficult forms).

        Some ATS platforms (like Breezy.hr) have timing issues with
        native fill methods. This method uses JavaScript DOM manipulation.

        Args:
            client: Browser service client
            selector: CSS selector
            value: Value to fill

        Returns:
            True if successful
        """
        # Escape special characters in value
        escaped_value = value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")

        script = f"""
            const el = document.querySelector('{selector}');
            if (el) {{
                el.value = '{escaped_value}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
            return false;
        """

        result = await client.evaluate(script)
        return bool(result.result) if result.success else False

    async def click_with_js(
        self,
        client: BrowserServiceClient,
        selector: str,
    ) -> bool:
        """Click element using JavaScript.

        Args:
            client: Browser service client
            selector: CSS selector

        Returns:
            True if successful
        """
        script = f"""
            const el = document.querySelector('{selector}');
            if (el) {{
                el.click();
                return true;
            }}
            return false;
        """

        result = await client.evaluate(script)
        return bool(result.result) if result.success else False

    async def wait_for_navigation(
        self,
        client: BrowserServiceClient,
        timeout: int = 5000,
    ) -> bool:
        """Wait for page navigation/reload.

        Args:
            client: Browser service client
            timeout: Timeout in ms

        Returns:
            True if navigation occurred
        """
        # Simple implementation - wait and check URL change
        import asyncio

        initial_url = await client.get_current_url()
        await asyncio.sleep(timeout / 1000)
        current_url = await client.get_current_url()

        return current_url != initial_url

"""Breezy.hr ATS strategy.

Based on POC findings:
- Breezy.hr forms require JavaScript-based filling due to timeout issues
  with native MCP/Playwright methods
- Form structure is relatively standard
- No CAPTCHA typically present
- Successful submissions confirmed in POC
"""

import logging
from typing import Any

from src.automation.models import UserFormData
from src.automation.client import BrowserServiceClient
from src.automation.strategies.base import ATSStrategy, FormFillResult, SubmitResult
from src.automation.strategies.registry import ATSStrategyRegistry

logger = logging.getLogger(__name__)


@ATSStrategyRegistry.register
class BreezyStrategy(ATSStrategy):
    """Strategy for Breezy.hr application forms.

    Breezy.hr is a popular ATS with generally straightforward forms.
    This strategy uses JavaScript-based filling for reliability,
    as native methods can timeout on Breezy's forms.
    """

    @property
    def ats_name(self) -> str:
        """ATS identifier."""
        return "breezy"

    @property
    def url_patterns(self) -> list[str]:
        """URL patterns for Breezy.hr."""
        return [
            r".*\.breezy\.hr/.*",
            r".*breezyhr\.com/.*",
        ]

    @property
    def field_selectors(self) -> dict[str, str]:
        """Breezy-specific field selectors.

        Based on analysis of Breezy.hr form structures.
        """
        return {
            "first_name": 'input[name*="first_name"], input[placeholder*="First name"]',
            "last_name": 'input[name*="last_name"], input[placeholder*="Last name"]',
            "email": 'input[type="email"], input[name*="email"]',
            "phone": 'input[type="tel"], input[name*="phone"]',
            "resume": 'input[type="file"][name*="resume"], input[accept*="pdf,doc"]',
            "cover_letter": 'textarea[name*="cover"], textarea[placeholder*="Cover"]',
            "linkedin": 'input[name*="linkedin"], input[placeholder*="LinkedIn"]',
            "portfolio": 'input[name*="portfolio"], input[name*="website"]',
        }

    async def detect(self, page_html: str, page_url: str) -> bool:
        """Detect Breezy.hr from page content.

        Args:
            page_html: Page HTML content
            page_url: Page URL

        Returns:
            True if this is a Breezy.hr page
        """
        breezy_indicators = [
            "breezy.hr" in page_url.lower(),
            "breezyhr" in page_url.lower(),
            "data-breezy" in page_html,
            "Powered by Breezy" in page_html,
            "breezy-career" in page_html.lower(),
        ]
        return any(breezy_indicators)

    async def analyze_form(
        self,
        client: BrowserServiceClient,
    ) -> dict[str, Any]:
        """Analyze Breezy form structure.

        Args:
            client: Browser service client

        Returns:
            Form analysis dict with Breezy-specific info
        """
        dom = await client.get_dom(form_fields_only=True)

        # Breezy-specific analysis
        has_resume_upload = any(
            f.field_type == "file" and
            ("resume" in (f.field_name or "").lower() or
             "cv" in (f.field_name or "").lower())
            for f in dom.form_fields
        )

        has_cover_letter = any(
            f.field_type == "textarea" and
            "cover" in (f.field_name or f.label or "").lower()
            for f in dom.form_fields
        )

        # Check for custom questions (non-standard fields)
        standard_names = {
            "first_name", "last_name", "email", "phone",
            "linkedin", "resume", "cover", "portfolio",
        }
        custom_questions = [
            f for f in dom.form_fields
            if f.is_visible and f.is_enabled and
            not any(s in (f.field_name or f.label or "").lower() for s in standard_names)
        ]

        return {
            "ats": "breezy",
            "page_url": dom.page_url,
            "page_title": dom.page_title,
            "total_fields": len(dom.form_fields),
            "has_resume_upload": has_resume_upload,
            "has_cover_letter": has_cover_letter,
            "custom_questions": custom_questions,
            "custom_question_count": len(custom_questions),
        }

    async def fill_form(
        self,
        client: BrowserServiceClient,
        user_data: UserFormData,
        cv_path: str | None,
        cover_letter: str | None,
    ) -> FormFillResult:
        """Fill Breezy form using JavaScript for reliability.

        Breezy.hr forms have timing issues with native fill methods,
        so we use JavaScript DOM manipulation.

        Args:
            client: Browser service client
            user_data: User data
            cv_path: Path to CV file
            cover_letter: Cover letter content

        Returns:
            FormFillResult with filled fields
        """
        filled_fields: dict[str, str] = {}
        errors: list[str] = []

        # Field mapping: (selector_key, user_data_attr, transform_func)
        field_mapping = [
            ("first_name", "first_name", None),
            ("last_name", "last_name", None),
            ("email", "email", None),
            ("phone", "phone", lambda u: f"{u.phone_country_code} {u.phone}"),
            ("linkedin", "linkedin_url", None),
            ("portfolio", "portfolio_url", None),
        ]

        for selector_key, attr, transform in field_mapping:
            selector = self.field_selectors.get(selector_key)
            if not selector:
                continue

            value = getattr(user_data, attr, None)
            if not value:
                continue

            if transform:
                value = transform(user_data)

            # Try each selector
            for sel in selector.split(", "):
                sel = sel.strip()
                try:
                    # Use JavaScript fill for Breezy.hr reliability
                    success = await self.fill_field_with_js(client, sel, value)
                    if success:
                        filled_fields[sel] = value
                        logger.info(f"Filled {selector_key} via JS: {sel}")
                        break
                except Exception as e:
                    logger.debug(f"Failed selector {sel}: {e}")

            if selector_key not in [s for s, v in filled_fields.items()]:
                # Fallback to native fill if JS fails
                for sel in selector.split(", "):
                    sel = sel.strip()
                    try:
                        if await client.is_element_visible(sel):
                            result = await client.fill(sel, value)
                            if result.get("success"):
                                filled_fields[sel] = value
                                logger.info(f"Filled {selector_key} via native: {sel}")
                                break
                    except Exception:
                        pass

        # Fill cover letter
        if cover_letter:
            selector = self.field_selectors.get("cover_letter")
            if selector:
                for sel in selector.split(", "):
                    sel = sel.strip()
                    success = await self.fill_field_with_js(client, sel, cover_letter)
                    if success:
                        filled_fields[sel] = f"{cover_letter[:50]}..."
                        logger.info(f"Filled cover letter via JS: {sel}")
                        break

        # Upload resume
        if cv_path:
            selector = self.field_selectors.get("resume")
            if selector:
                for sel in selector.split(", "):
                    sel = sel.strip()
                    try:
                        result = await client.upload(sel, cv_path)
                        if result.get("success"):
                            filled_fields[sel] = cv_path
                            logger.info(f"Uploaded resume: {sel}")
                            break
                    except Exception as e:
                        errors.append(f"Resume upload failed: {e}")

        return FormFillResult(
            success=len(filled_fields) > 0,
            fields_filled=filled_fields,
            errors=errors,
        )

    async def submit(self, client: BrowserServiceClient) -> SubmitResult:
        """Submit Breezy.hr application.

        Args:
            client: Browser service client

        Returns:
            SubmitResult with success status
        """
        # Breezy-specific submit button selectors
        submit_selectors = [
            'button[type="submit"]',
            'button.btn-primary',
            'button:has-text("Submit Application")',
            'button:has-text("Apply")',
            'input[type="submit"]',
        ]

        for selector in submit_selectors:
            try:
                # Try JS click first (more reliable for Breezy)
                success = await self.click_with_js(client, selector)
                if success:
                    logger.info(f"Clicked submit via JS: {selector}")

                    # Wait for confirmation
                    import asyncio
                    await asyncio.sleep(2)

                    current_url = await client.get_current_url()
                    page_content = await client.get_page_content()

                    # Check for success indicators
                    success_indicators = [
                        "thank you",
                        "application received",
                        "successfully submitted",
                        "we'll be in touch",
                    ]

                    is_success = any(
                        ind in page_content.lower()
                        for ind in success_indicators
                    )

                    if is_success:
                        return SubmitResult(
                            success=True,
                            confirmation_message="Application submitted successfully",
                            redirect_url=current_url,
                        )
            except Exception as e:
                logger.debug(f"Submit selector {selector} failed: {e}")

        # Fallback: try native click
        for selector in submit_selectors:
            try:
                if await client.is_element_visible(selector):
                    result = await client.click(selector)
                    if result.get("success"):
                        await self.wait_for_navigation(client)
                        return SubmitResult(
                            success=True,
                            redirect_url=await client.get_current_url(),
                        )
            except Exception:
                continue

        return SubmitResult(
            success=False,
            error="Could not find or click submit button",
        )

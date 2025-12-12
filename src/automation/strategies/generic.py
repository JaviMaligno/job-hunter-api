"""Generic strategy for unknown ATS platforms."""

import logging
from typing import Any

from src.automation.models import UserFormData
from src.automation.client import BrowserServiceClient
from src.automation.strategies.base import ATSStrategy, FormFillResult, SubmitResult
from src.automation.strategies.registry import ATSStrategyRegistry

logger = logging.getLogger(__name__)


@ATSStrategyRegistry.register
class GenericStrategy(ATSStrategy):
    """Generic fallback strategy for unknown ATS platforms.

    Uses common form field patterns and selectors that work
    across most job application forms.
    """

    @property
    def ats_name(self) -> str:
        """ATS identifier."""
        return "generic"

    @property
    def url_patterns(self) -> list[str]:
        """URL patterns - empty since this is the fallback."""
        return []

    @property
    def field_selectors(self) -> dict[str, str]:
        """Common field selectors."""
        return {
            "first_name": ", ".join([
                'input[name*="first_name"]',
                'input[name*="firstname"]',
                'input[name*="fname"]',
                'input[placeholder*="First"]',
                'input[id*="first_name"]',
                'input[id*="firstName"]',
            ]),
            "last_name": ", ".join([
                'input[name*="last_name"]',
                'input[name*="lastname"]',
                'input[name*="lname"]',
                'input[placeholder*="Last"]',
                'input[id*="last_name"]',
                'input[id*="lastName"]',
            ]),
            "email": ", ".join([
                'input[type="email"]',
                'input[name*="email"]',
                'input[placeholder*="email"]',
                'input[id*="email"]',
            ]),
            "phone": ", ".join([
                'input[type="tel"]',
                'input[name*="phone"]',
                'input[name*="telephone"]',
                'input[placeholder*="phone"]',
                'input[id*="phone"]',
            ]),
            "linkedin": ", ".join([
                'input[name*="linkedin"]',
                'input[placeholder*="LinkedIn"]',
                'input[id*="linkedin"]',
            ]),
            "resume": ", ".join([
                'input[type="file"][name*="resume"]',
                'input[type="file"][name*="cv"]',
                'input[type="file"][accept*="pdf"]',
                'input[type="file"]',
            ]),
            "cover_letter": ", ".join([
                'textarea[name*="cover"]',
                'textarea[placeholder*="cover"]',
                'textarea[id*="cover"]',
            ]),
        }

    async def detect(self, page_html: str, page_url: str) -> bool:
        """Generic strategy always returns True as fallback.

        Args:
            page_html: Page HTML content
            page_url: Page URL

        Returns:
            Always True (fallback strategy)
        """
        return True

    async def analyze_form(
        self,
        client: BrowserServiceClient,
    ) -> dict[str, Any]:
        """Analyze form using generic selectors.

        Args:
            client: Browser service client

        Returns:
            Form analysis dict
        """
        dom = await client.get_dom(form_fields_only=True)

        # Categorize fields
        standard_fields = []
        custom_fields = []

        standard_types = {"text", "email", "tel", "file", "hidden"}
        standard_names = {
            "first_name", "last_name", "email", "phone",
            "linkedin", "github", "resume", "cv",
        }

        for field in dom.form_fields:
            name_lower = (field.field_name or "").lower()
            label_lower = (field.label or "").lower()

            is_standard = (
                field.field_type in standard_types and
                any(s in name_lower or s in label_lower for s in standard_names)
            )

            if is_standard:
                standard_fields.append(field)
            else:
                custom_fields.append(field)

        return {
            "page_url": dom.page_url,
            "page_title": dom.page_title,
            "total_fields": len(dom.form_fields),
            "standard_fields": standard_fields,
            "custom_fields": custom_fields,
            "has_file_upload": any(f.field_type == "file" for f in dom.form_fields),
        }

    async def fill_form(
        self,
        client: BrowserServiceClient,
        user_data: UserFormData,
        cv_path: str | None,
        cover_letter: str | None,
    ) -> FormFillResult:
        """Fill form using generic selectors.

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

        # Field mapping: selector_key -> (user_data_attr, transform)
        field_mapping = [
            ("first_name", "first_name", None),
            ("last_name", "last_name", None),
            ("email", "email", None),
            ("phone", "phone", lambda u: f"{u.phone_country_code} {u.phone}"),
            ("linkedin", "linkedin_url", None),
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

            try:
                # Try each selector in the comma-separated list
                for sel in selector.split(", "):
                    sel = sel.strip()
                    if await client.is_element_visible(sel):
                        result = await client.fill(sel, value)
                        if result.get("success"):
                            filled_fields[sel] = value
                            logger.debug(f"Filled {selector_key}: {sel}")
                            break
            except Exception as e:
                errors.append(f"Failed to fill {selector_key}: {e}")
                logger.warning(f"Failed to fill {selector_key}: {e}")

        # Fill cover letter if provided
        if cover_letter:
            selector = self.field_selectors.get("cover_letter")
            if selector:
                for sel in selector.split(", "):
                    sel = sel.strip()
                    try:
                        if await client.is_element_visible(sel):
                            result = await client.fill(sel, cover_letter)
                            if result.get("success"):
                                filled_fields[sel] = cover_letter[:50] + "..."
                                break
                    except Exception:
                        pass

        # Upload CV if provided
        if cv_path:
            selector = self.field_selectors.get("resume")
            if selector:
                for sel in selector.split(", "):
                    sel = sel.strip()
                    try:
                        result = await client.upload(sel, cv_path)
                        if result.get("success"):
                            filled_fields[sel] = cv_path
                            break
                    except Exception:
                        pass

        return FormFillResult(
            success=len(filled_fields) > 0,
            fields_filled=filled_fields,
            errors=errors,
        )

    async def submit(self, client: BrowserServiceClient) -> SubmitResult:
        """Submit form using generic submit button selectors.

        Args:
            client: Browser service client

        Returns:
            SubmitResult with success status
        """
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Submit")',
            'button:has-text("Apply")',
            'button:has-text("Send")',
            'button.submit',
            '.submit-button',
        ]

        for selector in submit_selectors:
            try:
                if await client.is_element_visible(selector):
                    result = await client.click(selector)
                    if result.get("success"):
                        # Wait for potential navigation
                        await self.wait_for_navigation(client)

                        return SubmitResult(
                            success=True,
                            confirmation_message="Form submitted",
                            redirect_url=await client.get_current_url(),
                        )
            except Exception:
                continue

        return SubmitResult(
            success=False,
            error="Could not find submit button",
        )

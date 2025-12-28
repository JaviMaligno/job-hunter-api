"""Blocker detection for browser automation."""

import logging
import re

from pydantic import BaseModel

from src.db.models import BlockerType

logger = logging.getLogger(__name__)


class DetectedBlocker(BaseModel):
    """A detected blocker."""

    type: BlockerType
    subtype: str | None = None
    message: str
    element_selector: str | None = None
    suggested_action: str | None = None


class BlockerDetector:
    """Detects blockers that prevent automatic form submission.

    Blockers include:
    - CAPTCHAs (Cloudflare Turnstile, hCaptcha, reCAPTCHA)
    - Login requirements
    - File upload issues
    - Multi-step form complexity
    """

    # CAPTCHA detection patterns
    CAPTCHA_PATTERNS: dict[str, list[str]] = {
        "cloudflare": [
            "cf-turnstile",
            "challenge-platform",
            "cloudflare",
            "__cf_bm",
            "turnstile",
        ],
        "hcaptcha": [
            "h-captcha",
            "hcaptcha.com",
            "hcaptcha-response",
        ],
        "recaptcha": [
            "g-recaptcha",
            "recaptcha.net",
            "grecaptcha",
            "recaptcha-response",
        ],
    }

    # Login required patterns
    LOGIN_PATTERNS: list[str] = [
        r"/sign[-_]?in",
        r"/log[-_]?in",
        r"/auth/",
        r"please\s+(log|sign)\s+in",
        r"(log|sign)\s+in\s+to\s+continue",
        r"login\s+required",
        r"authentication\s+required",
        r"session\s+expired",
    ]

    # Patterns that indicate we're on a login page
    LOGIN_PAGE_INDICATORS: list[str] = [
        'input[type="password"]',
        'form[action*="login"]',
        'form[action*="signin"]',
        'button:has-text("Sign in")',
        'button:has-text("Log in")',
    ]

    async def detect_all(
        self,
        page_html: str,
        page_url: str,
    ) -> list[DetectedBlocker]:
        """Detect all blockers on page.

        Args:
            page_html: Page HTML content
            page_url: Page URL

        Returns:
            List of detected blockers
        """
        blockers = []

        # Check for CAPTCHA
        captcha = self.detect_captcha(page_html)
        if captcha:
            blockers.append(captcha)

        # Check for login required
        login = self.detect_login_required(page_html, page_url)
        if login:
            blockers.append(login)

        # Check for file upload issues (would need browser context)
        # This is handled separately in form filling

        return blockers

    def detect_captcha(self, page_html: str) -> DetectedBlocker | None:
        """Detect CAPTCHA type from page HTML.

        Args:
            page_html: Page HTML content

        Returns:
            DetectedBlocker if CAPTCHA found, None otherwise
        """
        html_lower = page_html.lower()

        for captcha_type, patterns in self.CAPTCHA_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in html_lower:
                    logger.info(f"Detected {captcha_type} CAPTCHA")
                    return DetectedBlocker(
                        type=BlockerType.CAPTCHA,
                        subtype=captcha_type,
                        message=f"{captcha_type.title()} CAPTCHA detected",
                        suggested_action="Please complete the CAPTCHA manually",
                    )

        return None

    def detect_login_required(
        self,
        page_html: str,
        page_url: str,
    ) -> DetectedBlocker | None:
        """Detect if login is required.

        Args:
            page_html: Page HTML content
            page_url: Page URL

        Returns:
            DetectedBlocker if login required, None otherwise
        """
        url_lower = page_url.lower()
        html_lower = page_html.lower()

        # Check URL patterns
        for pattern in self.LOGIN_PATTERNS:
            if re.search(pattern, url_lower, re.IGNORECASE):
                logger.info(f"Login required detected (URL pattern: {pattern})")
                return DetectedBlocker(
                    type=BlockerType.LOGIN_REQUIRED,
                    message="Login required to access application form",
                    suggested_action="Please log in to the platform",
                )

        # Check content patterns
        for pattern in self.LOGIN_PATTERNS:
            if re.search(pattern, html_lower, re.IGNORECASE):
                logger.info(f"Login required detected (content pattern: {pattern})")
                return DetectedBlocker(
                    type=BlockerType.LOGIN_REQUIRED,
                    message="Login required - page content indicates authentication needed",
                    suggested_action="Please log in to the platform",
                )

        # Check for login page indicators (presence of password field, etc.)
        login_indicators = [
            'type="password"' in html_lower,
            'action="login"' in html_lower or 'action="signin"' in html_lower,
        ]

        if any(login_indicators):
            # But make sure it's not just a login form on the application page
            if not any(
                form_indicator in html_lower
                for form_indicator in [
                    "apply",
                    "application",
                    "resume",
                    "cover letter",
                ]
            ):
                logger.info("Login required detected (page structure)")
                return DetectedBlocker(
                    type=BlockerType.LOGIN_REQUIRED,
                    message="Page appears to be a login page",
                    suggested_action="Please log in to access the application",
                )

        return None

    def detect_multi_step_form(self, page_html: str) -> DetectedBlocker | None:
        """Detect multi-step form complexity.

        Args:
            page_html: Page HTML content

        Returns:
            DetectedBlocker if complex multi-step form, None otherwise
        """
        html_lower = page_html.lower()

        multi_step_indicators = [
            r"step\s+\d+\s+of\s+\d+",
            r"page\s+\d+\s+of\s+\d+",
            r'class=".*step.*progress.*"',
            r'class=".*wizard.*"',
            r'class=".*multi.*step.*"',
        ]

        for pattern in multi_step_indicators:
            if re.search(pattern, html_lower):
                logger.info(f"Multi-step form detected (pattern: {pattern})")
                return DetectedBlocker(
                    type=BlockerType.MULTI_STEP_FORM,
                    message="Complex multi-step form detected",
                    suggested_action="Form may require multiple pages - will handle step by step",
                )

        return None

    def detect_location_mismatch(
        self,
        page_html: str,
        user_location: str | None,
    ) -> DetectedBlocker | None:
        """Detect location mismatch warnings.

        Args:
            page_html: Page HTML content
            user_location: User's location

        Returns:
            DetectedBlocker if location mismatch detected, None otherwise
        """
        html_lower = page_html.lower()

        location_warnings = [
            r"location\s+requirement",
            r"must\s+be\s+located\s+in",
            r"eligibility.*location",
            r"work\s+authorization",
        ]

        for pattern in location_warnings:
            if re.search(pattern, html_lower):
                return DetectedBlocker(
                    type=BlockerType.LOCATION_MISMATCH,
                    message="Job may have location requirements",
                    suggested_action="Please verify you meet location requirements",
                )

        return None

    @staticmethod
    def get_captcha_selector(captcha_type: str) -> str | None:
        """Get CSS selector for CAPTCHA element.

        Args:
            captcha_type: Type of CAPTCHA (cloudflare, hcaptcha, recaptcha)

        Returns:
            CSS selector or None
        """
        selectors = {
            "cloudflare": ".cf-turnstile, [data-cf-turnstile], iframe[src*='turnstile']",
            "hcaptcha": ".h-captcha, [data-hcaptcha], iframe[src*='hcaptcha']",
            "recaptcha": ".g-recaptcha, [data-recaptcha], iframe[src*='recaptcha']",
        }
        return selectors.get(captcha_type)

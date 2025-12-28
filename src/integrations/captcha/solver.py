"""
CAPTCHA solving integration using 2captcha service.

Supports:
- Cloudflare Turnstile
- hCaptcha
- reCAPTCHA v2/v3

Usage:
    solver = CaptchaSolver()
    token = await solver.solve(captcha_type="turnstile", sitekey="xxx", url="https://...")
"""

import asyncio
import logging
import os
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel
from TwoCaptcha import TwoCaptcha

logger = logging.getLogger(__name__)


class CaptchaType(str, Enum):
    """Supported CAPTCHA types."""

    TURNSTILE = "turnstile"  # Cloudflare
    HCAPTCHA = "hcaptcha"
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"


class CaptchaSolveResult(BaseModel):
    """Result of a CAPTCHA solve attempt."""

    success: bool
    token: str | None = None
    captcha_type: CaptchaType | None = None
    solve_time_seconds: float = 0.0
    cost_usd: float = 0.0
    error: str | None = None


class CaptchaConfig(BaseModel):
    """Configuration for CAPTCHA solving."""

    api_key: str
    # Pricing per solve (approximate, varies by type)
    price_turnstile: float = 0.002
    price_hcaptcha: float = 0.002
    price_recaptcha_v2: float = 0.003
    price_recaptcha_v3: float = 0.002
    # Timeouts
    timeout_seconds: int = 120
    polling_interval: float = 5.0


class CaptchaSolver:
    """
    CAPTCHA solver using 2captcha service.

    Supports automatic sitekey extraction and token injection.
    """

    # Sitekey extraction patterns
    SITEKEY_PATTERNS = {
        CaptchaType.TURNSTILE: [
            r'data-sitekey=["\']([^"\']+)["\']',
            r'sitekey:\s*["\']([^"\']+)["\']',
            r'turnstile.*?sitekey["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        ],
        CaptchaType.HCAPTCHA: [
            r'data-sitekey=["\']([^"\']+)["\']',
            r'h-captcha.*?data-sitekey=["\']([^"\']+)["\']',
            r'hcaptcha.*?sitekey["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        ],
        CaptchaType.RECAPTCHA_V2: [
            r'data-sitekey=["\']([^"\']+)["\']',
            r'grecaptcha\.render.*?["\']sitekey["\']\s*:\s*["\']([^"\']+)["\']',
            r'g-recaptcha.*?data-sitekey=["\']([^"\']+)["\']',
        ],
        CaptchaType.RECAPTCHA_V3: [
            r'grecaptcha\.execute\s*\(\s*["\']([^"\']+)["\']',
            r'recaptcha/api\.js\?render=([^"\'&]+)',
        ],
    }

    # Response field names for injecting solved tokens
    RESPONSE_FIELDS = {
        CaptchaType.TURNSTILE: "cf-turnstile-response",
        CaptchaType.HCAPTCHA: "h-captcha-response",
        CaptchaType.RECAPTCHA_V2: "g-recaptcha-response",
        CaptchaType.RECAPTCHA_V3: "g-recaptcha-response",
    }

    def __init__(self, api_key: str | None = None, config: CaptchaConfig | None = None):
        """
        Initialize the CAPTCHA solver.

        Args:
            api_key: 2captcha API key (uses TWOCAPTCHA_API_KEY env var if not provided)
            config: Optional full configuration
        """
        self.api_key = api_key or os.getenv("TWOCAPTCHA_API_KEY")

        if not self.api_key:
            logger.warning("No 2captcha API key provided - solver will return errors")
            self._solver = None
        else:
            self._solver = TwoCaptcha(self.api_key)

        if config:
            self.config = config
        else:
            self.config = CaptchaConfig(api_key=self.api_key or "")

    @property
    def is_configured(self) -> bool:
        """Check if solver is properly configured."""
        return self._solver is not None

    def extract_sitekey(
        self,
        page_html: str,
        captcha_type: CaptchaType,
    ) -> str | None:
        """
        Extract sitekey from page HTML.

        Args:
            page_html: Page HTML content
            captcha_type: Type of CAPTCHA to look for

        Returns:
            Sitekey if found, None otherwise
        """
        patterns = self.SITEKEY_PATTERNS.get(captcha_type, [])

        for pattern in patterns:
            match = re.search(pattern, page_html, re.IGNORECASE)
            if match:
                sitekey = match.group(1)
                logger.info(f"Extracted {captcha_type.value} sitekey: {sitekey[:20]}...")
                return sitekey

        logger.warning(f"Could not extract sitekey for {captcha_type.value}")
        return None

    def detect_captcha_type(self, page_html: str) -> CaptchaType | None:
        """
        Detect CAPTCHA type from page HTML.

        Args:
            page_html: Page HTML content

        Returns:
            Detected CaptchaType or None
        """
        html_lower = page_html.lower()

        # Check in order of likelihood based on POC findings
        if "turnstile" in html_lower or "cf-turnstile" in html_lower:
            return CaptchaType.TURNSTILE
        elif "hcaptcha" in html_lower or "h-captcha" in html_lower:
            return CaptchaType.HCAPTCHA
        elif "grecaptcha.execute" in html_lower:
            return CaptchaType.RECAPTCHA_V3
        elif "g-recaptcha" in html_lower or "recaptcha" in html_lower:
            return CaptchaType.RECAPTCHA_V2

        return None

    async def solve(
        self,
        captcha_type: CaptchaType,
        sitekey: str,
        page_url: str,
        action: str | None = None,  # For reCAPTCHA v3
        min_score: float = 0.9,  # For reCAPTCHA v3
        **kwargs: Any,
    ) -> CaptchaSolveResult:
        """
        Solve a CAPTCHA and return the token.

        Args:
            captcha_type: Type of CAPTCHA
            sitekey: Site key extracted from page
            page_url: URL where CAPTCHA appears
            action: Action name (for reCAPTCHA v3)
            min_score: Minimum score (for reCAPTCHA v3)
            **kwargs: Additional parameters for specific CAPTCHA types

        Returns:
            CaptchaSolveResult with token or error
        """
        if not self._solver:
            return CaptchaSolveResult(
                success=False,
                error="2captcha API key not configured",
            )

        import time

        start_time = time.time()

        try:
            result = await self._solve_async(
                captcha_type=captcha_type,
                sitekey=sitekey,
                page_url=page_url,
                action=action,
                min_score=min_score,
                **kwargs,
            )

            solve_time = time.time() - start_time
            cost = self._get_cost(captcha_type)

            logger.info(f"Solved {captcha_type.value} in {solve_time:.1f}s " f"(cost: ${cost:.4f})")

            return CaptchaSolveResult(
                success=True,
                token=result["code"],
                captcha_type=captcha_type,
                solve_time_seconds=solve_time,
                cost_usd=cost,
            )

        except Exception as e:
            solve_time = time.time() - start_time
            logger.error(f"CAPTCHA solve failed: {e}")

            return CaptchaSolveResult(
                success=False,
                error=str(e),
                captcha_type=captcha_type,
                solve_time_seconds=solve_time,
            )

    async def _solve_async(
        self,
        captcha_type: CaptchaType,
        sitekey: str,
        page_url: str,
        action: str | None = None,
        min_score: float = 0.9,
        **kwargs: Any,
    ) -> dict:
        """Run the synchronous 2captcha solve in a thread pool."""
        loop = asyncio.get_event_loop()

        def _solve():
            if captcha_type == CaptchaType.TURNSTILE:
                return self._solver.turnstile(
                    sitekey=sitekey,
                    url=page_url,
                    **kwargs,
                )
            elif captcha_type == CaptchaType.HCAPTCHA:
                return self._solver.hcaptcha(
                    sitekey=sitekey,
                    url=page_url,
                    **kwargs,
                )
            elif captcha_type == CaptchaType.RECAPTCHA_V2:
                return self._solver.recaptcha(
                    sitekey=sitekey,
                    url=page_url,
                    version="v2",
                    **kwargs,
                )
            elif captcha_type == CaptchaType.RECAPTCHA_V3:
                return self._solver.recaptcha(
                    sitekey=sitekey,
                    url=page_url,
                    version="v3",
                    action=action or "submit",
                    score=min_score,
                    **kwargs,
                )
            else:
                raise ValueError(f"Unsupported CAPTCHA type: {captcha_type}")

        return await loop.run_in_executor(None, _solve)

    async def solve_from_html(
        self,
        page_html: str,
        page_url: str,
        **kwargs: Any,
    ) -> CaptchaSolveResult:
        """
        Detect CAPTCHA type, extract sitekey, and solve.

        Convenience method that handles detection and extraction automatically.

        Args:
            page_html: Page HTML content
            page_url: Page URL
            **kwargs: Additional parameters

        Returns:
            CaptchaSolveResult with token or error
        """
        # Detect type
        captcha_type = self.detect_captcha_type(page_html)
        if not captcha_type:
            return CaptchaSolveResult(
                success=False,
                error="Could not detect CAPTCHA type",
            )

        # Extract sitekey
        sitekey = self.extract_sitekey(page_html, captcha_type)
        if not sitekey:
            return CaptchaSolveResult(
                success=False,
                error=f"Could not extract sitekey for {captcha_type.value}",
                captcha_type=captcha_type,
            )

        # Solve
        return await self.solve(
            captcha_type=captcha_type,
            sitekey=sitekey,
            page_url=page_url,
            **kwargs,
        )

    def get_response_field_name(self, captcha_type: CaptchaType) -> str:
        """Get the form field name for injecting the solved token."""
        return self.RESPONSE_FIELDS.get(captcha_type, "captcha-response")

    def get_injection_script(
        self,
        captcha_type: CaptchaType,
        token: str,
    ) -> str:
        """
        Generate JavaScript to inject solved token into page.

        Args:
            captcha_type: Type of CAPTCHA
            token: Solved token

        Returns:
            JavaScript code to inject token
        """
        field_name = self.get_response_field_name(captcha_type)

        # Base injection - set hidden field value
        script = f"""
        (function() {{
            // Find response field by name
            var fields = document.querySelectorAll('[name="{field_name}"], [id="{field_name}"]');
            fields.forEach(function(field) {{
                field.value = "{token}";
            }});

            // Also try textarea (common for these CAPTCHAs)
            var textareas = document.querySelectorAll('textarea[name*="response"], textarea[name*="captcha"]');
            textareas.forEach(function(ta) {{
                ta.value = "{token}";
            }});
        """

        # Add type-specific injection
        if captcha_type == CaptchaType.TURNSTILE:
            script += f"""
            // Cloudflare specific
            if (typeof turnstile !== 'undefined' && turnstile.getResponse) {{
                // Turnstile widget callback
                var widgets = document.querySelectorAll('[data-callback]');
                widgets.forEach(function(w) {{
                    var callback = w.getAttribute('data-callback');
                    if (window[callback]) window[callback]("{token}");
                }});
            }}
            """
        elif captcha_type == CaptchaType.HCAPTCHA:
            script += f"""
            // hCaptcha specific
            if (typeof hcaptcha !== 'undefined') {{
                // Try to trigger callback
                var widgets = document.querySelectorAll('[data-callback]');
                widgets.forEach(function(w) {{
                    var callback = w.getAttribute('data-callback');
                    if (window[callback]) window[callback]("{token}");
                }});
            }}
            """
        elif captcha_type in (CaptchaType.RECAPTCHA_V2, CaptchaType.RECAPTCHA_V3):
            script += f"""
            // reCAPTCHA specific
            if (typeof grecaptcha !== 'undefined') {{
                // Set response in grecaptcha
                document.querySelectorAll('.g-recaptcha-response').forEach(function(el) {{
                    el.innerHTML = "{token}";
                    el.value = "{token}";
                }});

                // Try callback
                var widgets = document.querySelectorAll('[data-callback]');
                widgets.forEach(function(w) {{
                    var callback = w.getAttribute('data-callback');
                    if (window[callback]) window[callback]("{token}");
                }});
            }}
            """

        script += """
            console.log('CAPTCHA token injected');
            return true;
        })();
        """

        return script

    def _get_cost(self, captcha_type: CaptchaType) -> float:
        """Get approximate cost for solving this CAPTCHA type."""
        costs = {
            CaptchaType.TURNSTILE: self.config.price_turnstile,
            CaptchaType.HCAPTCHA: self.config.price_hcaptcha,
            CaptchaType.RECAPTCHA_V2: self.config.price_recaptcha_v2,
            CaptchaType.RECAPTCHA_V3: self.config.price_recaptcha_v3,
        }
        return costs.get(captcha_type, 0.002)

    async def get_balance(self) -> float | None:
        """Get current 2captcha account balance."""
        if not self._solver:
            return None

        try:
            loop = asyncio.get_event_loop()
            balance = await loop.run_in_executor(None, self._solver.balance)
            return float(balance)
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return None


# =============================================================================
# Convenience functions
# =============================================================================


async def solve_captcha(
    page_html: str,
    page_url: str,
    api_key: str | None = None,
) -> CaptchaSolveResult:
    """
    Convenience function to solve CAPTCHA from page HTML.

    Args:
        page_html: Page HTML content
        page_url: Page URL
        api_key: Optional 2captcha API key

    Returns:
        CaptchaSolveResult with token or error
    """
    solver = CaptchaSolver(api_key=api_key)
    return await solver.solve_from_html(page_html, page_url)

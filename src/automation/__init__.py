"""Browser automation module for job applications.

This module provides:
- BrowserServiceClient: HTTP client for the Browser Service
- ATS Strategies: Platform-specific form handling
- Blocker Detection: CAPTCHA, login, etc. detection and handling
"""

from src.automation.blockers import (
    BlockerDetector,
    BlockerHandler,
    BlockerResolution,
    DetectedBlocker,
)
from src.automation.client import BrowserServiceClient

# Import strategies to register them
from src.automation.strategies import (  # noqa: F401
    ATSStrategy,
    ATSStrategyRegistry,
    CaptchaResult,
    breezy,
    generic,
)

__all__ = [
    # Client
    "BrowserServiceClient",
    # Strategies
    "ATSStrategy",
    "ATSStrategyRegistry",
    "CaptchaResult",
    # Blockers
    "BlockerDetector",
    "BlockerHandler",
    "BlockerResolution",
    "DetectedBlocker",
]

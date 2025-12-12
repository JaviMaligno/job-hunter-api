"""ATS-specific strategies for form filling.

Each ATS platform may have unique form structures, selectors,
and submission processes. Strategies encapsulate this platform-specific
logic while sharing common interfaces.
"""

from src.automation.strategies.base import ATSStrategy, CaptchaResult
from src.automation.strategies.registry import ATSStrategyRegistry

__all__ = [
    "ATSStrategy",
    "ATSStrategyRegistry",
    "CaptchaResult",
]

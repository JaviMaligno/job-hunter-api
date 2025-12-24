"""CAPTCHA solving integration."""

from src.integrations.captcha.solver import (
    CaptchaSolver,
    CaptchaSolveResult,
    CaptchaType,
    solve_captcha,
)

__all__ = [
    "CaptchaSolver",
    "CaptchaSolveResult",
    "CaptchaType",
    "solve_captcha",
]

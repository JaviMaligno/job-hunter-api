"""Browser adapters for different automation backends."""

from src.browser_service.adapters.base import BrowserAdapter
from src.browser_service.adapters.playwright_adapter import PlaywrightAdapter

__all__ = [
    "BrowserAdapter",
    "PlaywrightAdapter",
]
